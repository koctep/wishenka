"""Transactional SQLite storage for the wishlist domain service."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from wishenka.items.models import ItemPriority
from wishenka.wishlists.models import (
    Reservation,
    ReservationStatus,
    ViewHistoryEntry,
    WishItem,
    Wishlist,
    WishlistFavorite,
    WishlistMember,
    WishlistRole,
    WishlistStatus,
)
from wishenka.wishlists.repository import WishlistRepository
from wishenka.wishlists.service import WishlistService

T = TypeVar("T")

# aiosqlite DEBUG logs include SQL bound parameters, including capabilities.
logging.getLogger("aiosqlite").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


class TokenCollision(Exception):
    """A generated capability was previously used for either access purpose."""


def _parse_dt(val: str | datetime | None) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    return datetime.fromisoformat(val)


def _format_dt(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


@dataclass
class _StorageSnapshot:
    wishlists: set[int]
    members: set[int]
    items: set[int]
    reservations: set[int]
    favorites: set[tuple[int, int]]
    history_ids: set[int]


class WishlistStore:
    """Load domain objects inside SQLite WAL transactions with granular row mutations."""

    def __init__(self, database_url: str) -> None:
        prefix = "sqlite+aiosqlite:///"
        if not database_url.startswith(prefix):
            raise ValueError("Wishlist storage requires SQLite")
        path = database_url[len(prefix) :]
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_async_engine(
            database_url, connect_args={"timeout": 5}, hide_parameters=True
        )

    async def initialize(self) -> None:
        """Create the normalized schema without modifying existing records."""
        try:
            await self._initialize()
        except SQLAlchemyError:
            pass
        else:
            return
        raise RuntimeError("Unable to initialize wishlist storage")

    async def _initialize(self) -> None:
        async with self.engine.begin() as conn:
            await conn.exec_driver_sql("PRAGMA journal_mode=WAL")
            await conn.exec_driver_sql("PRAGMA foreign_keys=ON")
            await conn.exec_driver_sql("PRAGMA busy_timeout=5000")

            # Check if legacy schema with JSON payload is present and migrate
            cursor = await conn.execute(text("PRAGMA table_info(wl_lists)"))
            existing_cols = [r[1] for r in cursor.fetchall()]
            if "payload" in existing_cols:
                for tbl in (
                    "wl_reservations",
                    "wl_items",
                    "wl_members",
                    "wl_favorites",
                    "wl_view_history",
                    "wl_tokens",
                    "wl_invite_tokens",
                    "wl_counters",
                    "wl_lists",
                ):
                    await conn.exec_driver_sql(f"DROP TABLE IF EXISTS {tbl}")

            ddl_statements = (
                """
                CREATE TABLE IF NOT EXISTS wl_lists (
                    id INTEGER PRIMARY KEY,
                    owner_id INTEGER NOT NULL,
                    owner_name TEXT NOT NULL DEFAULT '',
                    title TEXT NOT NULL,
                    description TEXT,
                    event_title TEXT,
                    event_date TEXT,
                    is_collaborative INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'active',
                    public_token TEXT NOT NULL,
                    invite_token TEXT NOT NULL,
                    invite_token_expires_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """,
                "CREATE INDEX IF NOT EXISTS idx_wl_lists_owner ON wl_lists(owner_id)",
                (
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_wl_lists_public_token "
                    "ON wl_lists(public_token)"
                ),
                (
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_wl_lists_invite_token "
                    "ON wl_lists(invite_token)"
                ),
                "CREATE INDEX IF NOT EXISTS idx_wl_lists_status ON wl_lists(status)",
                """
                CREATE TABLE IF NOT EXISTS wl_members (
                    id INTEGER PRIMARY KEY,
                    wishlist_id INTEGER NOT NULL REFERENCES wl_lists(id) ON DELETE CASCADE,
                    user_id INTEGER NOT NULL,
                    role TEXT NOT NULL DEFAULT 'member',
                    joined_at TEXT NOT NULL
                )
                """,
                (
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_wl_members_unique "
                    "ON wl_members(wishlist_id, user_id)"
                ),
                "CREATE INDEX IF NOT EXISTS idx_wl_members_user ON wl_members(user_id)",
                """
                CREATE TABLE IF NOT EXISTS wl_items (
                    id INTEGER PRIMARY KEY,
                    wishlist_id INTEGER NOT NULL REFERENCES wl_lists(id) ON DELETE CASCADE,
                    recipient_user_id INTEGER,
                    recipient_name TEXT,
                    title TEXT NOT NULL,
                    description TEXT,
                    link TEXT,
                    price INTEGER,
                    currency TEXT NOT NULL DEFAULT 'RUB',
                    quantity INTEGER NOT NULL DEFAULT 1,
                    received_quantity INTEGER NOT NULL DEFAULT 0,
                    image_url TEXT,
                    store_name TEXT,
                    store_icon_url TEXT,
                    priority TEXT NOT NULL DEFAULT 'medium',
                    category TEXT,
                    is_archived INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """,
                "CREATE INDEX IF NOT EXISTS idx_wl_items_wishlist ON wl_items(wishlist_id)",
                "CREATE INDEX IF NOT EXISTS idx_wl_items_recipient ON wl_items(recipient_user_id)",
                """
                CREATE TABLE IF NOT EXISTS wl_reservations (
                    id INTEGER PRIMARY KEY,
                    wish_item_id INTEGER NOT NULL REFERENCES wl_items(id) ON DELETE CASCADE,
                    user_id INTEGER NOT NULL,
                    quantity INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """,
                (
                    "CREATE INDEX IF NOT EXISTS idx_wl_reservations_item "
                    "ON wl_reservations(wish_item_id)"
                ),
                "CREATE INDEX IF NOT EXISTS idx_wl_reservations_user ON wl_reservations(user_id)",
                (
                    "CREATE INDEX IF NOT EXISTS idx_wl_reservations_status "
                    "ON wl_reservations(status)"
                ),
                """
                CREATE TABLE IF NOT EXISTS wl_favorites (
                    user_id INTEGER NOT NULL,
                    wishlist_id INTEGER NOT NULL REFERENCES wl_lists(id) ON DELETE CASCADE,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, wishlist_id)
                )
                """,
                "CREATE INDEX IF NOT EXISTS idx_wl_favorites_user ON wl_favorites(user_id)",
                """
                CREATE TABLE IF NOT EXISTS wl_view_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    wishlist_id INTEGER NOT NULL REFERENCES wl_lists(id) ON DELETE CASCADE,
                    viewed_at TEXT NOT NULL
                )
                """,
                (
                    "CREATE UNIQUE INDEX IF NOT EXISTS wl_view_history_user_wl "
                    "ON wl_view_history(user_id, wishlist_id)"
                ),
                (
                    "CREATE INDEX IF NOT EXISTS idx_wl_view_history_user_time "
                    "ON wl_view_history(user_id, viewed_at DESC)"
                ),
                """
                CREATE TABLE IF NOT EXISTS wl_tokens (
                    token TEXT PRIMARY KEY,
                    wishlist_id INTEGER NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1
                )
                """,
                (
                    "CREATE INDEX IF NOT EXISTS idx_wl_tokens_wishlist "
                    "ON wl_tokens(wishlist_id, active)"
                ),
                "CREATE TABLE IF NOT EXISTS wl_invite_tokens (token TEXT PRIMARY KEY)",
                (
                    "CREATE TABLE IF NOT EXISTS wl_counters "
                    "(name TEXT PRIMARY KEY, value INTEGER NOT NULL)"
                ),
            )
            for statement in ddl_statements:
                await conn.exec_driver_sql(statement)

    async def _read(self, conn: AsyncConnection) -> tuple[WishlistService, _StorageSnapshot]:
        service = WishlistService()

        l_stmt = text(
            "SELECT id, owner_id, owner_name, title, description, event_title, "
            "event_date, is_collaborative, status, public_token, invite_token, "
            "invite_token_expires_at, created_at, updated_at FROM wl_lists ORDER BY id ASC"
        )
        l_rows = (await conn.execute(l_stmt)).all()
        for r in l_rows:
            wl = Wishlist(
                id=int(r.id),
                owner_id=int(r.owner_id),
                owner_name=str(r.owner_name or ""),
                title=str(r.title),
                description=str(r.description) if r.description is not None else None,
                event_title=str(r.event_title) if r.event_title is not None else None,
                event_date=_parse_dt(r.event_date),
                is_collaborative=bool(r.is_collaborative),
                status=WishlistStatus(r.status),
                public_token=str(r.public_token),
                invite_token=str(r.invite_token),
                invite_token_expires_at=_parse_dt(r.invite_token_expires_at),
                created_at=_parse_dt(r.created_at) or datetime.now(UTC),
                updated_at=_parse_dt(r.updated_at) or datetime.now(UTC),
                members=[],
                items=[],
            )
            service._wishlists[wl.id] = wl

        m_stmt = text(
            "SELECT id, wishlist_id, user_id, role, joined_at FROM wl_members ORDER BY id ASC"
        )
        m_rows = (await conn.execute(m_stmt)).all()
        member_ids: set[int] = set()
        for mr in m_rows:
            member = WishlistMember(
                id=int(mr.id),
                wishlist_id=int(mr.wishlist_id),
                user_id=int(mr.user_id),
                role=WishlistRole(mr.role),
                joined_at=_parse_dt(mr.joined_at) or datetime.now(UTC),
            )
            member_ids.add(member.id)
            if member.wishlist_id in service._wishlists:
                member.wishlist = service._wishlists[member.wishlist_id]
                member.wishlist.members.append(member)

        i_stmt = text(
            "SELECT id, wishlist_id, recipient_user_id, recipient_name, title, "
            "description, link, price, currency, quantity, received_quantity, "
            "image_url, store_name, store_icon_url, priority, category, is_archived, "
            "created_at, updated_at FROM wl_items ORDER BY id ASC"
        )
        i_rows = (await conn.execute(i_stmt)).all()
        for ir in i_rows:
            rec_uid = int(ir.recipient_user_id) if ir.recipient_user_id is not None else None
            price = int(ir.price) if ir.price is not None else None
            item = WishItem(
                id=int(ir.id),
                wishlist_id=int(ir.wishlist_id),
                recipient_user_id=rec_uid,
                recipient_name=str(ir.recipient_name) if ir.recipient_name is not None else None,
                title=str(ir.title),
                description=str(ir.description) if ir.description is not None else None,
                link=str(ir.link) if ir.link is not None else None,
                price=price,
                currency=str(ir.currency or "RUB"),
                quantity=int(ir.quantity),
                received_quantity=int(ir.received_quantity),
                image_url=str(ir.image_url) if ir.image_url is not None else None,
                store_name=str(ir.store_name) if ir.store_name is not None else None,
                store_icon_url=str(ir.store_icon_url) if ir.store_icon_url is not None else None,
                priority=ItemPriority(ir.priority),
                category=str(ir.category) if ir.category is not None else None,
                is_archived=bool(ir.is_archived),
                created_at=_parse_dt(ir.created_at) or datetime.now(UTC),
                updated_at=_parse_dt(ir.updated_at) or datetime.now(UTC),
                reservations=[],
            )
            service._items[item.id] = item
            if item.wishlist_id in service._wishlists:
                item.wishlist = service._wishlists[item.wishlist_id]
                item.wishlist.items.append(item)

        r_stmt = text(
            "SELECT id, wish_item_id, user_id, quantity, status, created_at, updated_at "
            "FROM wl_reservations ORDER BY id ASC"
        )
        r_rows = (await conn.execute(r_stmt)).all()
        for rr in r_rows:
            res = Reservation(
                id=int(rr.id),
                wish_item_id=int(rr.wish_item_id),
                user_id=int(rr.user_id),
                quantity=int(rr.quantity),
                status=ReservationStatus(rr.status),
                created_at=_parse_dt(rr.created_at) or datetime.now(UTC),
                updated_at=_parse_dt(rr.updated_at) or datetime.now(UTC),
            )
            service._reservations[res.id] = res
            if res.wish_item_id in service._items:
                res.wish_item = service._items[res.wish_item_id]
                res.wish_item.reservations.append(res)

        fav_rows = (
            await conn.execute(text("SELECT user_id, wishlist_id, created_at FROM wl_favorites"))
        ).all()
        for f_row in fav_rows:
            fav = WishlistFavorite(
                user_id=int(f_row[0]),
                wishlist_id=int(f_row[1]),
                created_at=_parse_dt(f_row[2]) or datetime.now(UTC),
            )
            service._favorites[(fav.user_id, fav.wishlist_id)] = fav

        hist_rows = (
            await conn.execute(
                text(
                    "SELECT id, user_id, wishlist_id, viewed_at "
                    "FROM wl_view_history ORDER BY id ASC"
                )
            )
        ).all()
        history_ids: set[int] = set()
        for h_row in hist_rows:
            entry = ViewHistoryEntry(
                id=int(h_row[0]),
                user_id=int(h_row[1]),
                wishlist_id=int(h_row[2]),
                viewed_at=_parse_dt(h_row[3]) or datetime.now(UTC),
            )
            history_ids.add(entry.id)
            service._view_history.append(entry)

        counters: dict[str, int] = dict(
            (await conn.execute(text("SELECT name, value FROM wl_counters"))).all()
        )
        for name in ("wishlist", "member", "item", "reservation", "view_history"):
            setattr(service, f"_next_{name}_id", counters.get(name, 0))

        snapshot = _StorageSnapshot(
            wishlists=set(service._wishlists.keys()),
            members=member_ids,
            items=set(service._items.keys()),
            reservations=set(service._reservations.keys()),
            favorites=set(service._favorites.keys()),
            history_ids=history_ids,
        )
        logger.info(
            "Wishlist store snapshot loaded: %d wishlists, %d items",
            len(service._wishlists),
            len(service._items),
            extra={
                "event": "wishlist_store_read",
                "wishlists_count": len(service._wishlists),
                "items_count": len(service._items),
                "reservations_count": len(service._reservations),
                "members_count": len(member_ids),
                "favorites_count": len(service._favorites),
                "history_count": len(service._view_history),
            },
        )
        return service, snapshot

    async def _write(
        self,
        conn: AsyncConnection,
        service: WishlistService,
        snapshot: _StorageSnapshot,
    ) -> None:
        current_wls = service._wishlists
        deleted_wls = snapshot.wishlists - set(current_wls.keys())
        for wid in deleted_wls:
            await conn.execute(text("DELETE FROM wl_lists WHERE id = :id"), {"id": wid})

        for wl in current_wls.values():
            params = {
                "id": wl.id,
                "owner_id": wl.owner_id,
                "owner_name": wl.owner_name,
                "title": wl.title,
                "description": wl.description,
                "event_title": wl.event_title,
                "event_date": _format_dt(wl.event_date),
                "is_collaborative": 1 if wl.is_collaborative else 0,
                "status": wl.status.value,
                "public_token": wl.public_token,
                "invite_token": wl.invite_token,
                "invite_token_expires_at": _format_dt(wl.invite_token_expires_at),
                "created_at": _format_dt(wl.created_at),
                "updated_at": _format_dt(wl.updated_at),
            }
            if wl.id in snapshot.wishlists:
                stmt = text(
                    "UPDATE wl_lists SET "
                    "owner_id = :owner_id, owner_name = :owner_name, title = :title, "
                    "description = :description, event_title = :event_title, "
                    "event_date = :event_date, is_collaborative = :is_collaborative, "
                    "status = :status, public_token = :public_token, "
                    "invite_token = :invite_token, "
                    "invite_token_expires_at = :invite_token_expires_at, "
                    "updated_at = :updated_at WHERE id = :id"
                )
            else:
                stmt = text(
                    "INSERT INTO wl_lists (id, owner_id, owner_name, title, description, "
                    "event_title, event_date, is_collaborative, status, public_token, "
                    "invite_token, invite_token_expires_at, created_at, updated_at) "
                    "VALUES (:id, :owner_id, :owner_name, :title, :description, "
                    ":event_title, :event_date, :is_collaborative, :status, :public_token, "
                    ":invite_token, :invite_token_expires_at, :created_at, :updated_at)"
                )
            await conn.execute(stmt, params)

        current_members = {m.id: m for wl in current_wls.values() for m in wl.members}
        deleted_members = snapshot.members - set(current_members.keys())
        for mid in deleted_members:
            await conn.execute(text("DELETE FROM wl_members WHERE id = :id"), {"id": mid})

        for member in current_members.values():
            m_params = {
                "id": member.id,
                "wishlist_id": member.wishlist_id,
                "user_id": member.user_id,
                "role": member.role.value,
                "joined_at": _format_dt(member.joined_at),
            }
            if member.id in snapshot.members:
                m_stmt = text(
                    "UPDATE wl_members SET role = :role, joined_at = :joined_at WHERE id = :id"
                )
            else:
                m_stmt = text(
                    "INSERT INTO wl_members (id, wishlist_id, user_id, role, joined_at) "
                    "VALUES (:id, :wishlist_id, :user_id, :role, :joined_at)"
                )
            await conn.execute(m_stmt, m_params)

        current_items = service._items
        deleted_items = snapshot.items - set(current_items.keys())
        for iid in deleted_items:
            await conn.execute(text("DELETE FROM wl_items WHERE id = :id"), {"id": iid})

        for item in current_items.values():
            i_params = {
                "id": item.id,
                "wishlist_id": item.wishlist_id,
                "recipient_user_id": item.recipient_user_id,
                "recipient_name": item.recipient_name,
                "title": item.title,
                "description": item.description,
                "link": item.link,
                "price": item.price,
                "currency": item.currency,
                "quantity": item.quantity,
                "received_quantity": item.received_quantity,
                "image_url": item.image_url,
                "store_name": item.store_name,
                "store_icon_url": item.store_icon_url,
                "priority": item.priority.value,
                "category": item.category,
                "is_archived": 1 if item.is_archived else 0,
                "created_at": _format_dt(item.created_at),
                "updated_at": _format_dt(item.updated_at),
            }
            if item.id in snapshot.items:
                i_stmt = text(
                    "UPDATE wl_items SET "
                    "recipient_user_id = :recipient_user_id, recipient_name = :recipient_name, "
                    "title = :title, description = :description, link = :link, "
                    "price = :price, currency = :currency, quantity = :quantity, "
                    "received_quantity = :received_quantity, image_url = :image_url, "
                    "store_name = :store_name, store_icon_url = :store_icon_url, "
                    "priority = :priority, category = :category, is_archived = :is_archived, "
                    "updated_at = :updated_at WHERE id = :id"
                )
            else:
                i_stmt = text(
                    "INSERT INTO wl_items (id, wishlist_id, recipient_user_id, recipient_name, "
                    "title, description, link, price, currency, quantity, received_quantity, "
                    "image_url, store_name, store_icon_url, priority, category, is_archived, "
                    "created_at, updated_at) VALUES (:id, :wishlist_id, :recipient_user_id, "
                    ":recipient_name, :title, :description, :link, :price, :currency, "
                    ":quantity, :received_quantity, :image_url, :store_name, :store_icon_url, "
                    ":priority, :category, :is_archived, :created_at, :updated_at)"
                )
            await conn.execute(i_stmt, i_params)

        current_res = service._reservations
        deleted_res = snapshot.reservations - set(current_res.keys())
        for rid in deleted_res:
            await conn.execute(text("DELETE FROM wl_reservations WHERE id = :id"), {"id": rid})

        for res in current_res.values():
            r_params = {
                "id": res.id,
                "wish_item_id": res.wish_item_id,
                "user_id": res.user_id,
                "quantity": res.quantity,
                "status": res.status.value,
                "created_at": _format_dt(res.created_at),
                "updated_at": _format_dt(res.updated_at),
            }
            if res.id in snapshot.reservations:
                r_stmt = text(
                    "UPDATE wl_reservations SET "
                    "quantity = :quantity, status = :status, updated_at = :updated_at "
                    "WHERE id = :id"
                )
            else:
                r_stmt = text(
                    "INSERT INTO wl_reservations (id, wish_item_id, user_id, quantity, "
                    "status, created_at, updated_at) "
                    "VALUES (:id, :wish_item_id, :user_id, :quantity, :status, "
                    ":created_at, :updated_at)"
                )
            await conn.execute(r_stmt, r_params)

        current_favs = set(service._favorites.keys())
        deleted_favs = snapshot.favorites - current_favs
        for uid, wid in deleted_favs:
            await conn.execute(
                text("DELETE FROM wl_favorites WHERE user_id = :uid AND wishlist_id = :wid"),
                {"uid": uid, "wid": wid},
            )
        for (uid, wid), fav in service._favorites.items():
            if wid in current_wls and (uid, wid) not in snapshot.favorites:
                await conn.execute(
                    text(
                        "INSERT INTO wl_favorites (user_id, wishlist_id, created_at) "
                        "VALUES (:user_id, :wishlist_id, :created_at) "
                        "ON CONFLICT(user_id, wishlist_id) DO NOTHING"
                    ),
                    {
                        "user_id": fav.user_id,
                        "wishlist_id": fav.wishlist_id,
                        "created_at": _format_dt(fav.created_at),
                    },
                )

        current_hist_ids = {e.id for e in service._view_history if e.id > 0}
        deleted_hist = snapshot.history_ids - current_hist_ids
        for hid in deleted_hist:
            await conn.execute(text("DELETE FROM wl_view_history WHERE id = :id"), {"id": hid})

        for entry in service._view_history:
            if entry.wishlist_id in current_wls:
                h_params = {
                    "id": entry.id if entry.id > 0 else None,
                    "user_id": entry.user_id,
                    "wishlist_id": entry.wishlist_id,
                    "viewed_at": _format_dt(entry.viewed_at),
                }
                if entry.id in snapshot.history_ids:
                    await conn.execute(
                        text("UPDATE wl_view_history SET viewed_at = :viewed_at WHERE id = :id"),
                        h_params,
                    )
                else:
                    await conn.execute(
                        text(
                            "INSERT INTO wl_view_history (id, user_id, wishlist_id, viewed_at) "
                            "VALUES (:id, :user_id, :wishlist_id, :viewed_at) "
                            "ON CONFLICT(user_id, wishlist_id) "
                            "DO UPDATE SET viewed_at = excluded.viewed_at"
                        ),
                        h_params,
                    )

        for name in ("wishlist", "member", "item", "reservation", "view_history"):
            await conn.execute(
                text(
                    "INSERT INTO wl_counters (name, value) VALUES (:name, :value) "
                    "ON CONFLICT(name) DO UPDATE SET value = excluded.value"
                ),
                {"name": name, "value": getattr(service, f"_next_{name}_id", 0)},
            )
        logger.info(
            "Wishlist store committed changes: %d wishlists, %d items",
            len(current_wls),
            len(current_items),
            extra={
                "event": "wishlist_store_write",
                "wishlists_count": len(current_wls),
                "members_count": len(current_members),
                "items_count": len(current_items),
                "reservations_count": len(current_res),
                "deleted_wishlists_count": len(deleted_wls),
                "deleted_members_count": len(deleted_members),
                "deleted_items_count": len(deleted_items),
                "deleted_reservations_count": len(deleted_res),
            },
        )

    async def execute(self, operation: Callable[[WishlistService], Awaitable[T]]) -> T:
        """Serialize reads and writes across workers and commit state atomically."""
        for attempt in range(5):
            try:
                return await self._execute_once(operation)
            except TokenCollision:
                logger.warning(
                    "Capability token collision encountered, retrying operation",
                    extra={
                        "event": "wishlist_token_collision_retry",
                        "attempt": attempt + 1,
                    },
                )
                if attempt < 4:
                    continue
                message = "Unable to allocate a unique capability"
            except IntegrityError as exc:
                if not any(
                    name in str(exc.orig) for name in ("wl_tokens.token", "wl_invite_tokens.token")
                ):
                    logger.error(
                        "Wishlist storage integrity error",
                        extra={"event": "wishlist_store_integrity_error"},
                    )
                    message = "Wishlist storage operation failed"
                elif attempt < 4:
                    logger.warning(
                        "Capability token collision encountered, retrying operation",
                        extra={
                            "event": "wishlist_token_collision_retry",
                            "attempt": attempt + 1,
                        },
                    )
                    continue
                else:
                    message = "Unable to allocate a unique public token"
            except SQLAlchemyError:
                logger.error(
                    "Wishlist storage operation failed due to database error",
                    extra={"event": "wishlist_store_error"},
                )
                message = "Wishlist storage operation failed"
            raise RuntimeError(message)
        raise RuntimeError("Unable to allocate a unique public token")

    async def _execute_once(self, operation: Callable[[WishlistService], Awaitable[T]]) -> T:
        async with self.engine.connect() as conn:
            await conn.exec_driver_sql("PRAGMA foreign_keys=ON")
            await conn.exec_driver_sql("PRAGMA busy_timeout=5000")
            await conn.commit()
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                service, snapshot = await self._read(conn)
                previous = {wl.id: wl.public_token for wl in service._wishlists.values()}
                prior_invites = {wl.id: wl.invite_token for wl in service._wishlists.values()}
                for token in prior_invites.values():
                    await conn.execute(
                        text("INSERT OR IGNORE INTO wl_invite_tokens VALUES (:token)"),
                        {"token": token},
                    )
                result = await operation(service)
                for wl in service._wishlists.values():
                    if prior_invites.get(wl.id) != wl.invite_token:
                        matching_public = await conn.scalar(
                            text("SELECT 1 FROM wl_tokens WHERE token=:token"),
                            {"token": wl.invite_token},
                        )
                        if matching_public or wl.invite_token == wl.public_token:
                            raise TokenCollision
                        await conn.execute(
                            text("INSERT INTO wl_invite_tokens VALUES (:token)"),
                            {"token": wl.invite_token},
                        )
                    old = previous.get(wl.id)
                    if old != wl.public_token:
                        matching_invite = await conn.scalar(
                            text("SELECT 1 FROM wl_invite_tokens WHERE token=:token"),
                            {"token": wl.public_token},
                        )
                        if matching_invite:
                            raise TokenCollision
                        await conn.execute(
                            text("UPDATE wl_tokens SET active=0 WHERE wishlist_id=:id"),
                            {"id": wl.id},
                        )
                        await conn.execute(
                            text("INSERT INTO wl_tokens VALUES (:token, :id, 1)"),
                            {"token": wl.public_token, "id": wl.id},
                        )
                await self._write(conn, service, snapshot)
                await conn.commit()
                return result
            except BaseException:
                await conn.rollback()
                raise

    async def cleanup_expired_tokens(self, now: datetime | None = None) -> int:
        """Revoke expired invite tokens across all wishlists."""
        async with self.engine.begin() as conn:
            await conn.exec_driver_sql("PRAGMA foreign_keys = ON")
            await conn.exec_driver_sql("PRAGMA busy_timeout = 5000")
            repo = WishlistRepository(conn)
            return await repo.cleanup_expired_tokens(now)

    async def purge_archived_wishlists(self, threshold: datetime) -> int:
        """Permanently purge soft-deleted wishlists older than threshold."""
        async with self.engine.begin() as conn:
            await conn.exec_driver_sql("PRAGMA foreign_keys = ON")
            await conn.exec_driver_sql("PRAGMA busy_timeout = 5000")
            repo = WishlistRepository(conn)
            return await repo.purge_archived_wishlists(threshold)

    async def purge_deleted_wishlists(self, threshold: datetime) -> int:
        """Alias for purge_archived_wishlists."""
        return await self.purge_archived_wishlists(threshold)


__all__ = ["TokenCollision", "WishlistRepository", "WishlistStore"]
