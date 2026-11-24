"""Transactional SQLite storage for the wishlist domain service."""

from __future__ import annotations

import logging
import os
import tempfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, NoReturn, TypeVar

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from wishenka.currency import DEFAULT_CURRENCY
from wishenka.items.models import ItemPriority
from wishenka.notices.events import EventProducer
from wishenka.notices.models import (
    EVENT_GIFT_RECEIVED,
    SKIP_SETTING_LIST,
    STATUS_SKIPPED,
    FlushedNotice,
    NoticeSettings,
)
from wishenka.sqlite import configure_immediate_transactions, is_sqlite_busy
from wishenka.wishlists.exceptions import (
    IdempotencyConflictError,
    InventoryBusyError,
    ItemNotFoundError,
    PermissionDeniedError,
    ReservationNotFoundError,
    SelfReservationError,
    TokenCollision,
    WishlistDeletedError,
    WishlistError,
    WishlistNotFoundError,
)
from wishenka.wishlists.migrations import migration_lock_path, upgrade_to_head
from wishenka.wishlists.models import (
    ReceiptRecord,
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
from wishenka.wishlists.schemas import MyReservationItemDTO, UserReservationsSummaryDTO
from wishenka.wishlists.service import PendingCommitLog, WishlistService, flush_pending_commit_logs

T = TypeVar("T")

# aiosqlite DEBUG logs include SQL bound parameters, including capabilities.
logging.getLogger("aiosqlite").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)
notice_logger = logging.getLogger("wishenka.wishlists.notices")


def _wish_scope(
    item_id: int | None,
    reservation_id: int | None,
    operation: str | None,
) -> dict[str, object]:
    scope: dict[str, object] = {}
    if item_id is not None:
        scope["item_id"] = item_id
    if reservation_id is not None:
        scope["reservation_id"] = reservation_id
    if operation is not None:
        scope["operation"] = operation
    return scope


def _wish_target(item_id: int | None, reservation_id: int | None) -> tuple[str, int] | None:
    if item_id is not None:
        return "item", item_id
    if reservation_id is not None:
        return "reservation", reservation_id
    return None


def _is_domain_refusal(exc: BaseException) -> bool:
    """A refused wish is not a storage failure, including quantity ValueError."""
    return isinstance(exc, WishlistError | ValueError)


def _log_wish_rollback(
    exc: BaseException,
    *,
    item_id: int | None,
    reservation_id: int | None,
    operation: str | None,
) -> None:
    """Record a rolled-back wish without row dumps, gifter ids, or driver text.

    Domain refusals are WARNING. A non-busy database failure stays ERROR.
    """
    scope = _wish_scope(item_id, reservation_id, operation)
    target = _wish_target(item_id, reservation_id)
    error_type = type(exc).__name__
    extra = {
        "event": "wishlist_inventory_rolled_back",
        "error_type": error_type,
        **scope,
    }
    log = logger.warning if _is_domain_refusal(exc) else logger.error
    if target is None:
        log(
            "Wishlist inventory transaction rolled back (%s)",
            error_type,
            extra=extra,
        )
        return
    kind, target_id = target
    log(
        "Wishlist inventory transaction rolled back (%s %s, %s)",
        kind,
        target_id,
        error_type,
        extra=extra,
    )


def _raise_for_storage_error(
    exc: SQLAlchemyError,
    *,
    item_id: int | None = None,
    reservation_id: int | None = None,
    operation: str | None = None,
    cabinet_operation: str | None = None,
) -> NoReturn:
    """Map a timed-out write lock before the generic storage failure."""
    if cabinet_operation is not None:
        if is_sqlite_busy(exc):
            logger.warning(
                "Reservation cabinet read failed because the database was busy",
                extra={"event": "reservation_cabinet_busy", "operation": cabinet_operation},
            )
            raise InventoryBusyError from exc
        logger.error(
            "Reservation cabinet read failed due to database error",
            extra={"event": "reservation_cabinet_error", "operation": cabinet_operation},
        )
        raise RuntimeError("Wishlist storage operation failed") from exc
    scope = _wish_scope(item_id, reservation_id, operation)
    target = _wish_target(item_id, reservation_id)
    if is_sqlite_busy(exc):
        extra = {"event": "wishlist_inventory_busy", **scope}
        if target is None:
            logger.warning(
                "Wishlist inventory change rolled back because the database was busy",
                extra=extra,
            )
        else:
            kind, target_id = target
            logger.warning(
                "Wishlist inventory change rolled back because the database was busy (%s %s)",
                kind,
                target_id,
                extra=extra,
            )
        raise InventoryBusyError from exc
    if scope:
        _log_wish_rollback(
            exc,
            item_id=item_id,
            reservation_id=reservation_id,
            operation=operation,
        )
    else:
        logger.error(
            "Wishlist storage operation failed due to database error",
            extra={"event": "wishlist_store_error"},
        )
    raise RuntimeError("Wishlist storage operation failed") from exc


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


def _item_state(item: WishItem) -> tuple[object, ...]:
    return (
        item.recipient_user_id,
        item.recipient_name,
        item.title,
        item.description,
        item.link,
        item.price,
        item.currency,
        item.quantity,
        item.received_quantity,
        item.image_url,
        item.store_name,
        item.store_icon_url,
        item.priority.value,
        item.category,
        item.display_order,
        item.is_archived,
        _format_dt(item.updated_at),
    )


def _reservation_state(reservation: Reservation) -> tuple[object, ...]:
    return (
        reservation.wish_item_id,
        reservation.user_id,
        reservation.quantity,
        reservation.status.value,
        _format_dt(reservation.created_at),
        _format_dt(reservation.updated_at),
    )


def _item_bind(item: WishItem) -> dict[str, Any]:
    return {
        "id": item.id,
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
        "display_order": item.display_order,
        "is_archived": 1 if item.is_archived else 0,
        "updated_at": _format_dt(item.updated_at),
    }


_ITEM_UPDATE = text(
    "UPDATE wl_items SET "
    "recipient_user_id = :recipient_user_id, recipient_name = :recipient_name, "
    "title = :title, description = :description, link = :link, "
    "price = :price, currency = :currency, quantity = :quantity, "
    "received_quantity = :received_quantity, image_url = :image_url, "
    "store_name = :store_name, store_icon_url = :store_icon_url, "
    "priority = :priority, category = :category, "
    "display_order = :display_order, is_archived = :is_archived, "
    "updated_at = :updated_at WHERE id = :id"
)
_RESERVATION_INSERT = text(
    "INSERT INTO wl_reservations (id, wish_item_id, user_id, quantity, "
    "status, created_at, updated_at) "
    "VALUES (:id, :wish_item_id, :user_id, :quantity, :status, "
    ":created_at, :updated_at)"
)
_RESERVATION_UPDATE = text(
    "UPDATE wl_reservations SET "
    "quantity = :quantity, status = :status, updated_at = :updated_at "
    "WHERE id = :id"
)


_RECEIPT_COLUMNS = "id, wish_item_id, quantity, received_at, is_approximate"


def _log_flushed_notices(flushed: list[FlushedNotice]) -> None:
    """Write the after-commit DEBUG record of each notice row; only the row id and gate."""
    for notice in flushed:
        if notice.status == STATUS_SKIPPED:
            notice_logger.debug(
                "Receipt notice skipped by a setting",
                extra={
                    "event": "receipt_notice_skipped",
                    "outbox_id": notice.outbox_id,
                    "gate": notice.gate,
                },
            )
        else:
            notice_logger.debug(
                "Receipt notice queued",
                extra={"event": "receipt_notice_created", "outbox_id": notice.outbox_id},
            )


def _log_flushed_shared_events(flushed_shared: list[tuple[str, int]]) -> None:
    """Write the after-commit DEBUG record of shared notice rows queued per event kind."""
    for kind, queued_count in flushed_shared:
        if queued_count > 0:
            notice_logger.debug(
                "Shared notice events queued: kind=%s count=%d",
                kind,
                queued_count,
                extra={
                    "event": "shared_notice_events_queued",
                    "kind": kind,
                    "queued_count": queued_count,
                },
            )


def _receipt_from_row(row: Any) -> ReceiptRecord:
    """Build a receipt record from a ``wl_receipts`` row."""
    return ReceiptRecord(
        id=int(row.id),
        wish_item_id=int(row.wish_item_id),
        quantity=int(row.quantity),
        received_at=_parse_dt(row.received_at) or datetime.now(UTC),
        is_approximate=bool(row.is_approximate),
    )


def _notice_settings_from_rows(user_rows: Any, list_rows: Any) -> NoticeSettings:
    """Build the notice switches from the two settings tables (rows of those queries)."""
    return NoticeSettings(
        user={(int(r.user_id), str(r.event_type)): bool(r.enabled) for r in user_rows},
        list={
            (int(r.user_id), int(r.wishlist_id), str(r.event_type)): bool(r.enabled)
            for r in list_rows
        },
    )


@dataclass
class _WishSnapshot:
    item_id: int
    item_state: tuple[object, ...]
    reservations: dict[int, tuple[object, ...]]
    reservation_counter: int


@dataclass
class _StorageSnapshot:
    wishlists: set[int]
    members: set[int]
    items: set[int]
    reservations: set[int]
    favorites: set[tuple[int, int]]
    history_ids: set[int]


@dataclass(frozen=True, slots=True)
class IdempotentResult:
    """Serialized HTTP outcome from execute_wish_idempotent."""

    status_code: int
    content_type: str
    body: str
    replayed: bool


class WishlistStore:
    """Load domain objects inside SQLite WAL transactions with granular row mutations."""

    def __init__(self, database_url: str) -> None:
        prefix = "sqlite+aiosqlite:///"
        if not database_url.startswith(prefix):
            raise ValueError("Wishlist storage requires SQLite")
        path = database_url[len(prefix) :]
        # Alembic opens a synchronous connection, while aiosqlite uses a distinct
        # asynchronous one.  SQLite's ``:memory:`` databases are connection-local,
        # so back it with an isolated temporary file and let both engines share it.
        self._temporary_database_path: Path | None = None
        if path == ":memory:":
            descriptor, temporary_path = tempfile.mkstemp(prefix="wishenka-", suffix=".sqlite")
            os.close(descriptor)
            self._temporary_database_path = Path(temporary_path)
            database_url = f"{prefix}{temporary_path}"
            path = temporary_path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.database_url = database_url
        self.engine = create_async_engine(
            database_url, connect_args={"timeout": 5}, hide_parameters=True
        )
        configure_immediate_transactions(self.engine.sync_engine)

    async def initialize(self) -> None:
        """Bring the wishlist database to Alembic head before it is used."""
        try:
            await upgrade_to_head(self.database_url)
        except (OSError, RuntimeError, ValueError, SQLAlchemyError) as exc:
            raise RuntimeError("Unable to initialize wishlist storage") from exc

    async def dispose(self) -> None:
        """Dispose connections and remove this store's owned temporary database."""
        await self.engine.dispose()
        if self._temporary_database_path is not None:
            try:
                self._temporary_database_path.unlink(missing_ok=True)
                migration_lock_path(self._temporary_database_path).unlink(missing_ok=True)
            finally:
                self._temporary_database_path = None

    async def _read(self, conn: AsyncConnection) -> tuple[WishlistService, _StorageSnapshot]:
        service = WishlistService.in_memory()
        service._defer_commit_logs = True

        l_stmt = text(
            "SELECT id, owner_id, owner_name, title, description, event_title, "
            "event_date, is_collaborative, warn_on_delete_reserved, status, "
            "public_token, invite_token, invite_token_expires_at, "
            "created_at, updated_at FROM wl_lists ORDER BY id ASC"
        )
        l_rows = (await conn.execute(l_stmt)).all()
        for r in l_rows:
            warn_pref = (
                bool(r.warn_on_delete_reserved) if r.warn_on_delete_reserved is not None else True
            )
            wl = Wishlist(
                id=int(r.id),
                owner_id=int(r.owner_id),
                owner_name=str(r.owner_name or ""),
                title=str(r.title),
                description=str(r.description) if r.description is not None else None,
                event_title=str(r.event_title) if r.event_title is not None else None,
                event_date=_parse_dt(r.event_date),
                is_collaborative=bool(r.is_collaborative),
                warn_on_delete_reserved=warn_pref,
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
            "image_url, store_name, store_icon_url, priority, category, "
            "display_order, is_archived, created_at, updated_at "
            "FROM wl_items ORDER BY display_order ASC, id ASC"
        )
        i_rows = (await conn.execute(i_stmt)).all()
        for ir in i_rows:
            rec_uid = int(ir.recipient_user_id) if ir.recipient_user_id is not None else None
            price = ir.price if ir.price is not None else None
            disp_order = int(ir.display_order) if ir.display_order is not None else 0
            item = WishItem(
                id=int(ir.id),
                wishlist_id=int(ir.wishlist_id),
                recipient_user_id=rec_uid,
                recipient_name=str(ir.recipient_name) if ir.recipient_name is not None else None,
                title=str(ir.title),
                description=str(ir.description) if ir.description is not None else None,
                link=str(ir.link) if ir.link is not None else None,
                price=price,
                currency=str(ir.currency or DEFAULT_CURRENCY),
                quantity=int(ir.quantity),
                received_quantity=int(ir.received_quantity),
                image_url=str(ir.image_url) if ir.image_url is not None else None,
                store_name=str(ir.store_name) if ir.store_name is not None else None,
                store_icon_url=str(ir.store_icon_url) if ir.store_icon_url is not None else None,
                priority=ItemPriority(ir.priority),
                category=str(ir.category) if ir.category is not None else None,
                display_order=disp_order,
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
            service._register_reservation(res)
            if res.wish_item_id in service._items:
                res.wish_item = service._items[res.wish_item_id]
                res.wish_item.reservations.append(res)

        receipt_rows = (
            await conn.execute(
                text(f"SELECT {_RECEIPT_COLUMNS} FROM wl_receipts ORDER BY received_at ASC, id ASC")
            )
        ).all()
        for receipt_row in receipt_rows:
            receipt = _receipt_from_row(receipt_row)
            if receipt.wish_item_id in service._items:
                service._items[receipt.wish_item_id].receipts.append(receipt)
        service._notice_settings = _notice_settings_from_rows(
            (
                await conn.execute(
                    text("SELECT user_id, event_type, enabled FROM user_notification_settings")
                )
            ).all(),
            (
                await conn.execute(
                    text(
                        "SELECT user_id, wishlist_id, event_type, enabled "
                        "FROM wl_list_notification_settings"
                    )
                )
            ).all(),
        )

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
    ) -> list[FlushedNotice]:
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
                "warn_on_delete_reserved": 1 if wl.warn_on_delete_reserved else 0,
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
                    "warn_on_delete_reserved = :warn_on_delete_reserved, "
                    "status = :status, public_token = :public_token, "
                    "invite_token = :invite_token, "
                    "invite_token_expires_at = :invite_token_expires_at, "
                    "updated_at = :updated_at WHERE id = :id"
                )
            else:
                stmt = text(
                    "INSERT INTO wl_lists (id, owner_id, owner_name, title, description, "
                    "event_title, event_date, is_collaborative, warn_on_delete_reserved, "
                    "status, public_token, invite_token, invite_token_expires_at, "
                    "created_at, updated_at) "
                    "VALUES (:id, :owner_id, :owner_name, :title, :description, "
                    ":event_title, :event_date, :is_collaborative, :warn_on_delete_reserved, "
                    ":status, :public_token, :invite_token, :invite_token_expires_at, "
                    ":created_at, :updated_at)"
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
                "display_order": item.display_order,
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
                    "priority = :priority, category = :category, "
                    "display_order = :display_order, is_archived = :is_archived, "
                    "updated_at = :updated_at WHERE id = :id"
                )
            else:
                i_stmt = text(
                    "INSERT INTO wl_items (id, wishlist_id, recipient_user_id, recipient_name, "
                    "title, description, link, price, currency, quantity, received_quantity, "
                    "image_url, store_name, store_icon_url, priority, category, "
                    "display_order, is_archived, created_at, updated_at) "
                    "VALUES (:id, :wishlist_id, :recipient_user_id, "
                    ":recipient_name, :title, :description, :link, :price, :currency, "
                    ":quantity, :received_quantity, :image_url, :store_name, :store_icon_url, "
                    ":priority, :category, :display_order, :is_archived, :created_at, :updated_at)"
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
        flushed = await self._flush_receipt_effects(conn, service)
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
        return flushed

    async def _flush_receipt_effects(
        self, conn: AsyncConnection, service: WishlistService
    ) -> list[FlushedNotice]:
        """Insert this transaction's receipt records and notice rows; return the notice rows.

        The lists belong to a service created for one transaction, so they hold exactly its
        effects. Any failure propagates and rolls the whole transaction back.
        """
        for receipt in service._new_receipts:
            result = await conn.execute(
                text(
                    "INSERT INTO wl_receipts (wish_item_id, quantity, received_at, is_approximate) "
                    "VALUES (:wish_item_id, :quantity, :received_at, :is_approximate)"
                ),
                {
                    "wish_item_id": receipt.wish_item_id,
                    "quantity": receipt.quantity,
                    "received_at": _format_dt(receipt.received_at),
                    "is_approximate": 1 if receipt.is_approximate else 0,
                },
            )
            receipt.id = int(result.lastrowid)
        for receipt in service._updated_receipts:
            await conn.execute(
                text(
                    "UPDATE wl_receipts SET quantity = :quantity "
                    "WHERE id = :id AND wish_item_id = :wish_item_id"
                ),
                {
                    "id": receipt.id,
                    "wish_item_id": receipt.wish_item_id,
                    "quantity": receipt.quantity,
                },
            )
        for receipt_id in service._deleted_receipt_ids:
            await conn.execute(
                text("DELETE FROM wl_receipts WHERE id = :id"),
                {"id": receipt_id},
            )
        flushed: list[FlushedNotice] = []
        now = datetime.now(UTC)
        producer = EventProducer()
        service._flushed_shared_events.clear()
        for shared_event in service._new_shared_item_events:
            queued = await producer.record(conn, shared_event, int(now.timestamp()))
            if queued > 0:
                service._flushed_shared_events.append((shared_event.kind, queued))
        try:
            for draft in service._new_notices:
                wishlist_id = service._items[draft.receipt.wish_item_id].wishlist_id
                is_member = await conn.scalar(
                    text("SELECT 1 FROM wl_members WHERE wishlist_id=:list AND user_id=:user"),
                    {"list": wishlist_id, "user": draft.giver_user_id},
                )
                key = await conn.execute(
                    text(
                        "INSERT OR IGNORE INTO notice_receipt_keys"
                        "(event_type,receipt_id,giver_user_id,created_at) "
                        "VALUES (:event,:receipt,:giver,:created_at)"
                    ),
                    {
                        "event": EVENT_GIFT_RECEIVED,
                        "receipt": draft.receipt.id,
                        "giver": draft.giver_user_id,
                        "created_at": int(now.timestamp()),
                    },
                )
                if not key.rowcount:
                    continue
                result = await conn.execute(
                    text(
                        "INSERT INTO notification_outbox (event_type, receipt_id, wishlist_id, "
                        "wish_item_id, giver_user_id, status, skip_reason, next_attempt_at, "
                        "created_at, updated_at, requires_membership) "
                        "VALUES (:event_type, :receipt_id, :wishlist_id, "
                        ":wish_item_id, :giver_user_id, :status, :skip_reason, :next_attempt_at, "
                        ":now, :now, :requires_membership)"
                    ),
                    {
                        "event_type": EVENT_GIFT_RECEIVED,
                        "receipt_id": draft.receipt.id,
                        "wishlist_id": wishlist_id,
                        "wish_item_id": draft.receipt.wish_item_id,
                        "giver_user_id": draft.giver_user_id,
                        "status": draft.status,
                        "skip_reason": draft.skip_reason,
                        "next_attempt_at": int(now.timestamp()),
                        "now": _format_dt(now),
                        "requires_membership": int(bool(is_member)),
                    },
                )
                gate = (
                    None
                    if draft.skip_reason is None
                    else "list"
                    if draft.skip_reason == SKIP_SETTING_LIST
                    else "user"
                )
                flushed.append(
                    FlushedNotice(
                        outbox_id=int(result.lastrowid),
                        status=draft.status,
                        gate=gate,
                    )
                )
        except Exception as exc:
            notice_logger.error(
                "Receipt notice enqueue failed",
                extra={
                    "event": "receipt_notice_enqueue_failed",
                    "error_class": type(exc).__name__,
                },
            )
            raise
        return flushed

    async def execute_wish(
        self,
        operation: Callable[[WishlistService], Awaitable[T]],
        *,
        item_id: int | None = None,
        reservation_id: int | None = None,
        operation_name: str = "wish_inventory",
    ) -> T:
        """Run one inventory change for a single wish and persist only changed rows."""
        if (item_id is None) == (reservation_id is None):
            raise ValueError("Wish inventory change requires item_id or reservation_id")

        resolved_item_id = item_id
        reservations_written = 0
        flushed: list[FlushedNotice] = []
        flushed_shared: list[tuple[str, int]] = []
        pending_commit_logs: list[PendingCommitLog] = []

        async def work(conn: AsyncConnection) -> T:
            nonlocal resolved_item_id, reservations_written, flushed, flushed_shared
            nonlocal pending_commit_logs
            resolved_item_id = await self._resolve_wish_item_id(
                conn,
                item_id=item_id,
                reservation_id=reservation_id,
            )
            service, snapshot = await self._load_wish(conn, resolved_item_id)
            result = await operation(service)
            reservations_written, flushed = await self._persist_wish(conn, service, snapshot)
            flushed_shared = list(service._flushed_shared_events)
            pending_commit_logs = list(service._pending_commit_logs)
            return result

        try:
            result = await self._immediate(work)
        except SQLAlchemyError as exc:
            _raise_for_storage_error(
                exc,
                item_id=item_id if item_id is not None else resolved_item_id,
                reservation_id=reservation_id,
                operation=operation_name,
            )
        except Exception as exc:
            _log_wish_rollback(
                exc,
                item_id=resolved_item_id,
                reservation_id=reservation_id,
                operation=operation_name,
            )
            raise
        logger.info(
            "Wishlist inventory transaction committed for item %s (%s)",
            resolved_item_id,
            operation_name,
            extra={
                "event": "wishlist_inventory_committed",
                "item_id": resolved_item_id,
                "operation": operation_name,
                "reservations_written": reservations_written,
            },
        )
        _log_flushed_notices(flushed)
        _log_flushed_shared_events(flushed_shared)
        flush_pending_commit_logs(pending_commit_logs)
        return result

    async def _verify_idempotent_replay_access(
        self,
        conn: AsyncConnection,
        *,
        actor_id: int,
        resolved_item_id: int,
        require_member: bool,
        check_not_recipient: bool,
    ) -> None:
        """Enforce wishlist existence, Surprise Invariant, and membership on replay."""
        row = (
            await conn.execute(
                text(
                    "SELECT i.wishlist_id, i.recipient_user_id, w.owner_id, w.status, "
                    "w.is_collaborative "
                    "FROM wl_items i JOIN wl_lists w ON w.id = i.wishlist_id "
                    "WHERE i.id = :item_id"
                ),
                {"item_id": resolved_item_id},
            )
        ).one_or_none()
        if row is None:
            raise ItemNotFoundError(f"Item {resolved_item_id} not found")
        if row.status == WishlistStatus.DELETED.value:
            raise WishlistDeletedError(f"Wishlist {row.wishlist_id} has been deleted")
        if check_not_recipient and (
            row.recipient_user_id == actor_id
            or (not row.is_collaborative and row.owner_id == actor_id)
        ):
            raise SelfReservationError("Recipient cannot access reservation replay")
        if require_member and row.owner_id != actor_id:
            is_member = await conn.scalar(
                text("SELECT 1 FROM wl_members WHERE wishlist_id = :wid AND user_id = :uid"),
                {"wid": row.wishlist_id, "uid": actor_id},
            )
            if not is_member:
                raise PermissionDeniedError("Actor is no longer a wishlist member")

    async def execute_wish_idempotent(
        self,
        operation: Callable[[WishlistService], Awaitable[tuple[int, str, str]]],
        *,
        actor_id: int,
        idempotency_key: str,
        request_hash: str,
        retention_hours: int = 24,
        item_id: int | None = None,
        reservation_id: int | None = None,
        operation_name: str = "wish_inventory",
        require_member: bool = False,
        check_not_recipient: bool = False,
        now: datetime | None = None,
    ) -> IdempotentResult:
        """Run one wish mutation with atomic idempotency lookup, replay, and persistence."""
        if (item_id is None) == (reservation_id is None):
            raise ValueError("Wish inventory change requires item_id or reservation_id")

        effective_now = now or datetime.now(UTC)
        resolved_item_id = item_id
        reservations_written = 0
        flushed: list[FlushedNotice] = []
        flushed_shared: list[tuple[str, int]] = []
        pending_commit_logs: list[PendingCommitLog] = []

        async def work(conn: AsyncConnection) -> IdempotentResult:
            nonlocal resolved_item_id, reservations_written, flushed, flushed_shared
            nonlocal pending_commit_logs
            resolved_item_id = await self._resolve_wish_item_id(
                conn,
                item_id=item_id,
                reservation_id=reservation_id,
            )
            existing = (
                await conn.execute(
                    text(
                        "SELECT request_hash, response_status, response_content_type, "
                        "response_body, expires_at "
                        "FROM wl_idempotency_records "
                        "WHERE actor_id = :actor_id AND idempotency_key = :key"
                    ),
                    {"actor_id": actor_id, "key": idempotency_key},
                )
            ).one_or_none()

            if existing is not None and datetime.fromisoformat(existing.expires_at) > effective_now:
                if existing.request_hash != request_hash:
                    raise IdempotencyConflictError()
                if operation_name == "complete_reservation":
                    owns = await conn.scalar(
                        text("SELECT 1 FROM wl_reservations WHERE id=:id AND user_id=:actor"),
                        {"id": reservation_id, "actor": actor_id},
                    )
                    if not owns:
                        raise ReservationNotFoundError("Reservation not found")
                await self._verify_idempotent_replay_access(
                    conn,
                    actor_id=actor_id,
                    resolved_item_id=resolved_item_id,
                    require_member=require_member,
                    check_not_recipient=check_not_recipient,
                )
                return IdempotentResult(
                    status_code=int(existing.response_status),
                    content_type=str(existing.response_content_type),
                    body=str(existing.response_body),
                    replayed=True,
                )

            service, snapshot = await self._load_wish(conn, resolved_item_id)
            resp_status, resp_content_type, resp_body = await operation(service)
            reservations_written, flushed = await self._persist_wish(conn, service, snapshot)
            flushed_shared = list(service._flushed_shared_events)
            pending_commit_logs = list(service._pending_commit_logs)

            expires_at = effective_now + timedelta(hours=retention_hours)
            await conn.execute(
                text(
                    "INSERT OR REPLACE INTO wl_idempotency_records ("
                    "actor_id, idempotency_key, request_hash, response_status, "
                    "response_content_type, response_body, created_at, expires_at"
                    ") VALUES ("
                    ":actor_id, :key, :request_hash, :status, :content_type, "
                    ":body, :created_at, :expires_at"
                    ")"
                ),
                {
                    "actor_id": actor_id,
                    "key": idempotency_key,
                    "request_hash": request_hash,
                    "status": resp_status,
                    "content_type": resp_content_type,
                    "body": resp_body,
                    "created_at": effective_now.isoformat(),
                    "expires_at": expires_at.isoformat(),
                },
            )
            return IdempotentResult(
                status_code=resp_status,
                content_type=resp_content_type,
                body=resp_body,
                replayed=False,
            )

        try:
            outcome = await self._immediate(work)
        except SQLAlchemyError as exc:
            _raise_for_storage_error(
                exc,
                item_id=item_id if item_id is not None else resolved_item_id,
                reservation_id=reservation_id,
                operation=operation_name,
            )
        except Exception as exc:
            _log_wish_rollback(
                exc,
                item_id=resolved_item_id,
                reservation_id=reservation_id,
                operation=operation_name,
            )
            raise

        if outcome.replayed:
            logger.info(
                "Idempotent wish mutation replayed for item %s (%s)",
                resolved_item_id,
                operation_name,
                extra={
                    "event": "idempotency_replay_hit",
                    "item_id": resolved_item_id,
                    "operation": operation_name,
                    "response_status": outcome.status_code,
                },
            )
        else:
            logger.info(
                "Wishlist inventory transaction committed for item %s (%s)",
                resolved_item_id,
                operation_name,
                extra={
                    "event": "wishlist_inventory_committed",
                    "item_id": resolved_item_id,
                    "operation": operation_name,
                    "reservations_written": reservations_written,
                },
            )
            _log_flushed_notices(flushed)
            _log_flushed_shared_events(flushed_shared)
            flush_pending_commit_logs(pending_commit_logs)
        return outcome

    async def _resolve_wish_item_id(
        self,
        conn: AsyncConnection,
        *,
        item_id: int | None,
        reservation_id: int | None,
    ) -> int:
        if item_id is not None:
            return item_id
        found = await conn.scalar(
            text("SELECT wish_item_id FROM wl_reservations WHERE id = :reservation_id"),
            {"reservation_id": reservation_id},
        )
        if found is None:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")
        return int(found)

    async def _load_wish(
        self,
        conn: AsyncConnection,
        item_id: int,
    ) -> tuple[WishlistService, _WishSnapshot]:
        item_row = (
            await conn.execute(
                text(
                    "SELECT id, wishlist_id, recipient_user_id, recipient_name, title, "
                    "description, link, price, currency, quantity, received_quantity, "
                    "image_url, store_name, store_icon_url, priority, category, "
                    "display_order, is_archived, created_at, updated_at "
                    "FROM wl_items WHERE id = :id"
                ),
                {"id": item_id},
            )
        ).one_or_none()
        if item_row is None:
            raise ItemNotFoundError(f"Item {item_id} not found")

        wishlist_row = (
            await conn.execute(
                text(
                    "SELECT id, owner_id, owner_name, title, description, event_title, "
                    "event_date, is_collaborative, warn_on_delete_reserved, status, "
                    "public_token, invite_token, invite_token_expires_at, "
                    "created_at, updated_at FROM wl_lists WHERE id = :id"
                ),
                {"id": int(item_row.wishlist_id)},
            )
        ).one_or_none()
        if wishlist_row is None:
            raise WishlistNotFoundError(f"Wishlist {item_row.wishlist_id} not found")

        warn_raw = wishlist_row.warn_on_delete_reserved
        wishlist = Wishlist(
            id=int(wishlist_row.id),
            owner_id=int(wishlist_row.owner_id),
            owner_name=str(wishlist_row.owner_name or ""),
            title=str(wishlist_row.title),
            description=(
                None if wishlist_row.description is None else str(wishlist_row.description)
            ),
            event_title=(
                None if wishlist_row.event_title is None else str(wishlist_row.event_title)
            ),
            event_date=_parse_dt(wishlist_row.event_date),
            is_collaborative=bool(wishlist_row.is_collaborative),
            warn_on_delete_reserved=True if warn_raw is None else bool(warn_raw),
            status=WishlistStatus(wishlist_row.status),
            public_token=str(wishlist_row.public_token),
            invite_token=str(wishlist_row.invite_token),
            invite_token_expires_at=_parse_dt(wishlist_row.invite_token_expires_at),
            created_at=_parse_dt(wishlist_row.created_at) or datetime.now(UTC),
            updated_at=_parse_dt(wishlist_row.updated_at) or datetime.now(UTC),
            members=[],
            items=[],
        )
        member_rows = (
            await conn.execute(
                text(
                    "SELECT id, wishlist_id, user_id, role, joined_at "
                    "FROM wl_members WHERE wishlist_id = :wishlist_id ORDER BY id ASC"
                ),
                {"wishlist_id": wishlist.id},
            )
        ).all()
        for member_row in member_rows:
            member = WishlistMember(
                id=int(member_row.id),
                wishlist_id=int(member_row.wishlist_id),
                user_id=int(member_row.user_id),
                role=WishlistRole(member_row.role),
                joined_at=_parse_dt(member_row.joined_at) or datetime.now(UTC),
            )
            member.wishlist = wishlist
            wishlist.members.append(member)

        display_order = 0 if item_row.display_order is None else int(item_row.display_order)
        item = WishItem(
            id=int(item_row.id),
            wishlist_id=int(item_row.wishlist_id),
            recipient_user_id=(
                None if item_row.recipient_user_id is None else int(item_row.recipient_user_id)
            ),
            recipient_name=(
                None if item_row.recipient_name is None else str(item_row.recipient_name)
            ),
            title=str(item_row.title),
            description=None if item_row.description is None else str(item_row.description),
            link=None if item_row.link is None else str(item_row.link),
            price=item_row.price,
            currency=str(item_row.currency or DEFAULT_CURRENCY),
            quantity=int(item_row.quantity),
            received_quantity=int(item_row.received_quantity),
            image_url=None if item_row.image_url is None else str(item_row.image_url),
            store_name=None if item_row.store_name is None else str(item_row.store_name),
            store_icon_url=(
                None if item_row.store_icon_url is None else str(item_row.store_icon_url)
            ),
            priority=ItemPriority(item_row.priority),
            category=None if item_row.category is None else str(item_row.category),
            display_order=display_order,
            is_archived=bool(item_row.is_archived),
            created_at=_parse_dt(item_row.created_at) or datetime.now(UTC),
            updated_at=_parse_dt(item_row.updated_at) or datetime.now(UTC),
            reservations=[],
            wishlist=wishlist,
        )
        wishlist.items.append(item)

        reservation_rows = (
            await conn.execute(
                text(
                    "SELECT id, wish_item_id, user_id, quantity, status, created_at, updated_at "
                    "FROM wl_reservations WHERE wish_item_id = :item_id ORDER BY id ASC"
                ),
                {"item_id": item.id},
            )
        ).all()
        service = WishlistService.in_memory()
        service._defer_commit_logs = True
        service._wishlists[wishlist.id] = wishlist
        service._items[item.id] = item
        for reservation_row in reservation_rows:
            reservation = Reservation(
                id=int(reservation_row.id),
                wish_item_id=int(reservation_row.wish_item_id),
                user_id=int(reservation_row.user_id),
                quantity=int(reservation_row.quantity),
                status=ReservationStatus(reservation_row.status),
                created_at=_parse_dt(reservation_row.created_at) or datetime.now(UTC),
                updated_at=_parse_dt(reservation_row.updated_at) or datetime.now(UTC),
                wish_item=item,
            )
            item.reservations.append(reservation)
            service._register_reservation(reservation)

        receipt_rows = (
            await conn.execute(
                text(
                    f"SELECT {_RECEIPT_COLUMNS} FROM wl_receipts "
                    "WHERE wish_item_id = :item_id ORDER BY received_at ASC, id ASC"
                ),
                {"item_id": item.id},
            )
        ).all()
        item.receipts.extend(_receipt_from_row(row) for row in receipt_rows)
        holders = "SELECT user_id FROM wl_reservations WHERE wish_item_id = :item_id"
        service._notice_settings = _notice_settings_from_rows(
            (
                await conn.execute(
                    text(
                        "SELECT user_id, event_type, enabled FROM user_notification_settings "
                        f"WHERE user_id IN ({holders})"
                    ),
                    {"item_id": item.id},
                )
            ).all(),
            (
                await conn.execute(
                    text(
                        "SELECT user_id, wishlist_id, event_type, enabled "
                        "FROM wl_list_notification_settings "
                        f"WHERE wishlist_id = :wishlist_id AND user_id IN ({holders})"
                    ),
                    {"item_id": item.id, "wishlist_id": wishlist.id},
                )
            ).all(),
        )

        counter = await conn.scalar(
            text("SELECT value FROM wl_counters WHERE name = 'reservation'")
        )
        service._next_reservation_id = int(counter or 0)
        snapshot = _WishSnapshot(
            item_id=item.id,
            item_state=_item_state(item),
            reservations={
                reservation.id: _reservation_state(reservation)
                for reservation in service._reservations.values()
            },
            reservation_counter=service._next_reservation_id,
        )
        return service, snapshot

    async def _persist_wish(
        self,
        conn: AsyncConnection,
        service: WishlistService,
        snapshot: _WishSnapshot,
    ) -> tuple[int, list[FlushedNotice]]:
        """Write the item, changed reservations, counter and receipt effects only.

        Returns the number of reservation rows written and the notice rows flushed.
        """
        item = service._items.get(snapshot.item_id)
        if item is not None and _item_state(item) != snapshot.item_state:
            await conn.execute(_ITEM_UPDATE, _item_bind(item))

        written = 0
        for reservation in service._reservations.values():
            if reservation.wish_item_id != snapshot.item_id:
                continue
            state = _reservation_state(reservation)
            previous = snapshot.reservations.get(reservation.id)
            if previous is None:
                await conn.execute(
                    _RESERVATION_INSERT,
                    {
                        "id": reservation.id,
                        "wish_item_id": reservation.wish_item_id,
                        "user_id": reservation.user_id,
                        "quantity": reservation.quantity,
                        "status": reservation.status.value,
                        "created_at": _format_dt(reservation.created_at),
                        "updated_at": _format_dt(reservation.updated_at),
                    },
                )
                written += 1
            elif previous != state:
                await conn.execute(
                    _RESERVATION_UPDATE,
                    {
                        "id": reservation.id,
                        "quantity": reservation.quantity,
                        "status": reservation.status.value,
                        "updated_at": _format_dt(reservation.updated_at),
                    },
                )
                written += 1

        for reservation in service._reservations.values():
            previous = snapshot.reservations.get(reservation.id)
            if (
                not previous
                or previous[3] != "purchased"
                or reservation.status.value != "completed"
            ):
                continue
            params = {"item": reservation.wish_item_id, "user": reservation.user_id}
            open_promise = await conn.scalar(
                text(
                    "SELECT 1 FROM wl_reservations WHERE wish_item_id=:item AND user_id=:user "
                    "AND status IN ('active','purchased') LIMIT 1"
                ),
                params,
            )
            if open_promise:
                continue
            gift_res = await conn.execute(
                text(
                    "UPDATE notification_outbox SET status='skipped',skip_reason='target_gone', "
                    "claim_token=NULL,claimed_at=NULL WHERE wish_item_id=:item "
                    "AND giver_user_id=:user AND status IN ('pending','sending')"
                ),
                params,
            )
            reminder_res = await conn.execute(
                text(
                    "UPDATE reminder_outbox SET status='skipped',claim_token=NULL,claimed_at=NULL "
                    "WHERE item_id=:item AND user_id=:user AND status IN ('pending','sending') "
                    "AND kind IN ('receipt_increased','receipt_reverted')"
                ),
                params,
            )
            if gift_res.rowcount or reminder_res.rowcount:
                notice_logger.info(
                    "Suppressed pending receipt notices after promise completion",
                    extra={
                        "event": "receipt_notices_suppressed",
                        "item_id": reservation.wish_item_id,
                        "user_id": reservation.user_id,
                        "gift_skipped": gift_res.rowcount,
                        "reminder_skipped": reminder_res.rowcount,
                    },
                )

        if service._next_reservation_id != snapshot.reservation_counter:
            await conn.execute(
                text(
                    "INSERT INTO wl_counters (name, value) VALUES ('reservation', :value) "
                    "ON CONFLICT(name) DO UPDATE SET value = excluded.value"
                ),
                {"value": service._next_reservation_id},
            )
        return written, await self._flush_receipt_effects(conn, service)

    async def _cabinet_service(
        self, conn: AsyncConnection, user_id: int, *, include_items: bool
    ) -> WishlistService:
        """Hydrate only the giver's reservations and their wishes in one transaction."""
        repository = WishlistRepository(conn)
        service = WishlistService.in_memory()
        reservations = await repository.list_user_reservations(user_id)
        for reservation in reservations:
            service._register_reservation(reservation)
        if include_items:
            wishlists: dict[int, Wishlist | None] = {}
            for item_id in dict.fromkeys(res.wish_item_id for res in reservations):
                item = await repository.get_item(item_id)
                if item is None:
                    continue
                if item.wishlist_id not in wishlists:
                    wishlists[item.wishlist_id] = await repository.get_wishlist_header(
                        item.wishlist_id
                    )
                item.wishlist = wishlists[item.wishlist_id]
                service._items[item.id] = item
        return service

    async def get_user_reservations(self, user_id: int) -> list[MyReservationItemDTO]:
        """Read a giver's cabinet using indexed, transactionally consistent queries."""

        async def work(conn: AsyncConnection) -> list[MyReservationItemDTO]:
            service = await self._cabinet_service(conn, user_id, include_items=True)
            return await service.get_user_reservations(user_id)

        try:
            return await self._immediate(work)
        except SQLAlchemyError as exc:
            _raise_for_storage_error(exc, cabinet_operation="reservations_list")

    async def get_user_reservations_summary(self, user_id: int) -> UserReservationsSummaryDTO:
        """Read a giver's reservation counts without hydrating unrelated data."""

        async def work(conn: AsyncConnection) -> UserReservationsSummaryDTO:
            service = await self._cabinet_service(conn, user_id, include_items=False)
            return await service.get_user_reservations_summary(user_id)

        try:
            return await self._immediate(work)
        except SQLAlchemyError as exc:
            _raise_for_storage_error(exc, cabinet_operation="reservations_summary")

    async def execute(self, operation: Callable[[WishlistService], Awaitable[T]]) -> T:
        """Serialize reads and writes across workers and commit state atomically."""

        async def adapter(service: WishlistService, _conn: AsyncConnection) -> T:
            return await operation(service)

        return await self.execute_with_connection(adapter)

    async def execute_with_connection(
        self,
        operation: Callable[[WishlistService, AsyncConnection], Awaitable[T]],
    ) -> T:
        """Serialize domain reads/writes and caller-scoped SQL in one atomic transaction."""
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
            except SQLAlchemyError as exc:
                _raise_for_storage_error(exc)
            raise RuntimeError(message)
        raise RuntimeError("Unable to allocate a unique public token")

    async def _immediate(self, work: Callable[[AsyncConnection], Awaitable[T]]) -> T:
        """Run work inside Connection.begin(); the listener emits BEGIN IMMEDIATE."""
        async with self.engine.connect() as conn:
            try:
                await conn.begin()
                result = await work(conn)
                await conn.commit()
                return result
            except BaseException:
                if conn.in_transaction():
                    await conn.rollback()
                raise

    async def transaction(self, work: Callable[[AsyncConnection], Awaitable[T]]) -> T:
        """Run ``work`` in one ``BEGIN IMMEDIATE`` transaction; commit on success, else roll back.

        Public seam for components outside the domain service (the notice queue store) that
        must serialise with receipts and promises without a second locking scheme.
        """
        return await self._immediate(work)

    async def execute_read(self, work: Callable[[AsyncConnection], Awaitable[T]]) -> T:
        """Run ``work`` in a read-only deferred transaction without ``BEGIN IMMEDIATE``."""
        async with self.engine.connect() as raw_conn:
            conn = await raw_conn.execution_options(read_only=True)
            try:
                await conn.begin()
                return await work(conn)
            finally:
                if conn.in_transaction():
                    await conn.rollback()

    async def _execute_once(
        self,
        operation: Callable[[WishlistService, AsyncConnection], Awaitable[T]],
    ) -> T:
        flushed: list[FlushedNotice] = []
        flushed_shared: list[tuple[str, int]] = []
        pending_commit_logs: list[PendingCommitLog] = []

        async def work(conn: AsyncConnection) -> T:
            nonlocal flushed, flushed_shared, pending_commit_logs
            service, snapshot = await self._read(conn)
            previous = {wl.id: wl.public_token for wl in service._wishlists.values()}
            prior_invites = {wl.id: wl.invite_token for wl in service._wishlists.values()}
            for token in prior_invites.values():
                await conn.execute(
                    text("INSERT OR IGNORE INTO wl_invite_tokens VALUES (:token)"),
                    {"token": token},
                )
            result = await operation(service, conn)
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
            flushed = await self._write(conn, service, snapshot)
            flushed_shared = list(service._flushed_shared_events)
            pending_commit_logs = list(service._pending_commit_logs)
            return result

        result = await self._immediate(work)
        _log_flushed_notices(flushed)
        _log_flushed_shared_events(flushed_shared)
        flush_pending_commit_logs(pending_commit_logs)
        return result

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

    async def cleanup_expired_idempotency_records(self, now: datetime | None = None) -> int:
        """Delete expired client idempotency records and return the number of rows removed."""
        effective_now = now or datetime.now(UTC)
        async with self.engine.begin() as conn:
            await conn.exec_driver_sql("PRAGMA foreign_keys = ON")
            await conn.exec_driver_sql("PRAGMA busy_timeout = 5000")
            result = await conn.execute(
                text("DELETE FROM wl_idempotency_records WHERE expires_at <= :now"),
                {"now": effective_now.isoformat()},
            )
            removed = int(result.rowcount or 0)
        if removed > 0:
            logger.info(
                "Expired idempotency records purged: %s",
                removed,
                extra={
                    "event": "idempotency_records_purged",
                    "purged_count": removed,
                },
            )
        return removed

    async def cleanup_expired_session_revocations(self, now: datetime | None = None) -> int:
        """Delete expired account-deletion session revocation markers."""
        effective_now = (now or datetime.now(UTC)).astimezone(UTC)
        now_epoch = int(effective_now.timestamp())
        async with self.engine.begin() as conn:
            await conn.exec_driver_sql("PRAGMA foreign_keys = ON")
            await conn.exec_driver_sql("PRAGMA busy_timeout = 5000")
            table_exists = await conn.scalar(
                text(
                    "SELECT 1 FROM sqlite_master "
                    "WHERE type = 'table' AND name = 'deleted_session_revocations'"
                )
            )
            if table_exists is None:
                return 0
            result = await conn.execute(
                text("DELETE FROM deleted_session_revocations WHERE expires_at <= :now_epoch"),
                {"now_epoch": now_epoch},
            )
            removed = int(result.rowcount or 0)
        if removed > 0:
            logger.info(
                "Expired session revocation markers purged: %s",
                removed,
                extra={
                    "event": "session_revocations_purged",
                    "purged_count": removed,
                },
            )
        return removed


__all__ = ["TokenCollision", "WishlistRepository", "WishlistStore"]
