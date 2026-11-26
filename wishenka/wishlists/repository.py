"""Async repository providing granular queries and mutations for wishlist entities."""

import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Row, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from wishenka.currency import DEFAULT_CURRENCY
from wishenka.items.models import ItemPriority
from wishenka.wishlists.exceptions import TokenCollision
from wishenka.wishlists.models import (
    ReceiptRecord,
    Reservation,
    ReservationStatus,
    ShareAccessGrant,
    ViewHistoryEntry,
    WishItem,
    Wishlist,
    WishlistFavorite,
    WishlistMember,
    WishlistRole,
    WishlistStatus,
)
from wishenka.wishlists.service import PendingCommitLog, flush_pending_commit_logs

logger = logging.getLogger(__name__)

_ID_BATCH_SIZE = 500


def _chunked_unique_ids(ids: Sequence[int], chunk_size: int = _ID_BATCH_SIZE) -> list[list[int]]:
    """Deduplicate IDs preserving order and split into bounded chunks."""
    unique_ids = list(dict.fromkeys(ids))
    return [unique_ids[i : i + chunk_size] for i in range(0, len(unique_ids), chunk_size)]


def _in_clause_params(ids: Sequence[int], prefix: str = "id") -> tuple[str, dict[str, int]]:
    """Build parameterized IN-clause placeholders and bind dict."""
    placeholders = ", ".join(f":{prefix}_{idx}" for idx in range(len(ids)))
    params = {f"{prefix}_{idx}": value for idx, value in enumerate(ids)}
    return placeholders, params


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


def _row_to_wishlist(row: Row[Any]) -> Wishlist:
    created = _parse_dt(row.created_at) or datetime.now(UTC)
    updated = _parse_dt(row.updated_at) or datetime.now(UTC)
    warn_pref = (
        bool(row.warn_on_delete_reserved) if row.warn_on_delete_reserved is not None else True
    )
    return Wishlist(
        id=int(row.id),
        owner_id=int(row.owner_id),
        owner_name=str(row.owner_name or ""),
        title=str(row.title),
        description=str(row.description) if row.description is not None else None,
        event_title=str(row.event_title) if row.event_title is not None else None,
        event_date=_parse_dt(row.event_date),
        is_collaborative=bool(row.is_collaborative),
        warn_on_delete_reserved=warn_pref,
        status=WishlistStatus(row.status),
        public_token=str(row.public_token),
        invite_token=str(row.invite_token),
        invite_token_expires_at=_parse_dt(row.invite_token_expires_at),
        created_at=created,
        updated_at=updated,
        members=[],
        items=[],
    )


def _row_to_member(row: Row[Any]) -> WishlistMember:
    joined = _parse_dt(row.joined_at) or datetime.now(UTC)
    return WishlistMember(
        id=int(row.id),
        wishlist_id=int(row.wishlist_id),
        user_id=int(row.user_id),
        role=WishlistRole(row.role),
        joined_at=joined,
    )


def _row_to_item(row: Row[Any]) -> WishItem:
    created = _parse_dt(row.created_at) or datetime.now(UTC)
    updated = _parse_dt(row.updated_at) or datetime.now(UTC)
    rec_uid = int(row.recipient_user_id) if row.recipient_user_id is not None else None
    price = row.price if row.price is not None else None
    return WishItem(
        id=int(row.id),
        wishlist_id=int(row.wishlist_id),
        recipient_user_id=rec_uid,
        recipient_name=str(row.recipient_name) if row.recipient_name is not None else None,
        title=str(row.title),
        description=str(row.description) if row.description is not None else None,
        link=str(row.link) if row.link is not None else None,
        price=price,
        currency=str(row.currency or DEFAULT_CURRENCY),
        quantity=int(row.quantity),
        received_quantity=int(row.received_quantity),
        image_url=str(row.image_url) if row.image_url is not None else None,
        store_name=str(row.store_name) if row.store_name is not None else None,
        store_icon_url=str(row.store_icon_url) if row.store_icon_url is not None else None,
        priority=ItemPriority(row.priority),
        category=str(row.category) if row.category is not None else None,
        display_order=int(row.display_order or 0),
        is_archived=bool(row.is_archived),
        created_at=created,
        updated_at=updated,
        reservations=[],
    )


def _row_to_reservation(row: Row[Any]) -> Reservation:
    created = _parse_dt(row.created_at) or datetime.now(UTC)
    updated = _parse_dt(row.updated_at) or datetime.now(UTC)
    return Reservation(
        id=int(row.id),
        wish_item_id=int(row.wish_item_id),
        user_id=int(row.user_id),
        quantity=int(row.quantity),
        status=ReservationStatus(row.status),
        created_at=created,
        updated_at=updated,
    )


class WishlistRepository:
    """Async repository providing targeted queries for wishlist entities."""

    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn
        self._pending_commit_logs: list[PendingCommitLog] = []

    def defer_commit_log(
        self,
        level: int,
        message: str,
        *args: Any,
        extra: dict[str, Any],
    ) -> None:
        """Queue a domain log record to be emitted only after the transaction commits."""
        self._pending_commit_logs.append(
            PendingCommitLog(level=level, message=message, args=args, extra=extra)
        )

    def flush_commit_logs(self) -> None:
        """Emit and clear all queued post-commit log records."""
        if not self._pending_commit_logs:
            return
        pending = list(self._pending_commit_logs)
        self._pending_commit_logs.clear()
        flush_pending_commit_logs(pending)

    def clear_commit_logs(self) -> None:
        """Discard queued post-commit log records (e.g. on transaction rollback)."""
        self._pending_commit_logs.clear()

    async def _allocate_id(self, counter_name: str, table_name: str) -> int:
        """Allocate the next sequential integer primary key using wl_counters."""
        current = await self.conn.scalar(
            text("SELECT value FROM wl_counters WHERE name = :name"),
            {"name": counter_name},
        )
        max_existing = await self.conn.scalar(
            text(f"SELECT COALESCE(MAX(id), 0) FROM {table_name}")
        )
        next_val = max(int(current or 0), int(max_existing or 0)) + 1
        await self.conn.execute(
            text(
                "INSERT INTO wl_counters (name, value) VALUES (:name, :value) "
                "ON CONFLICT(name) DO UPDATE SET value = excluded.value"
            ),
            {"name": counter_name, "value": next_val},
        )
        return next_val

    async def _next_sequence(self, counter_name: str) -> int:
        """Allocate the next counter value. Row ids are not part of this sequence."""
        current = await self.conn.scalar(
            text("SELECT value FROM wl_counters WHERE name = :name"),
            {"name": counter_name},
        )
        next_val = int(current or 0) + 1
        await self.conn.execute(
            text(
                "INSERT INTO wl_counters (name, value) VALUES (:name, :value) "
                "ON CONFLICT(name) DO UPDATE SET value = excluded.value"
            ),
            {"name": counter_name, "value": next_val},
        )
        return next_val

    async def _ensure_tokens_available(
        self,
        *,
        public_token: str | None = None,
        invite_token: str | None = None,
    ) -> None:
        """Raise TokenCollision if either token already exists in wl_tokens or wl_invite_tokens."""
        if public_token is not None:
            in_public = await self.conn.scalar(
                text("SELECT 1 FROM wl_tokens WHERE token = :token"),
                {"token": public_token},
            )
            in_invite = await self.conn.scalar(
                text("SELECT 1 FROM wl_invite_tokens WHERE token = :token"),
                {"token": public_token},
            )
            if in_public or in_invite:
                raise TokenCollision
        if invite_token is not None:
            in_public = await self.conn.scalar(
                text("SELECT 1 FROM wl_tokens WHERE token = :token"),
                {"token": invite_token},
            )
            in_invite = await self.conn.scalar(
                text("SELECT 1 FROM wl_invite_tokens WHERE token = :token"),
                {"token": invite_token},
            )
            if in_public or in_invite:
                raise TokenCollision

    async def create_wishlist(self, wishlist: Wishlist) -> Wishlist:
        """Allocate an ID, register capability tokens, and insert a new wishlist."""
        if wishlist.public_token == wishlist.invite_token:
            raise TokenCollision
        await self._ensure_tokens_available(
            public_token=wishlist.public_token,
            invite_token=wishlist.invite_token,
        )
        if wishlist.id <= 0:
            wishlist.id = await self._allocate_id("wishlist", "wl_lists")
        try:
            await self.upsert_wishlist(wishlist)
            await self.conn.execute(
                text("INSERT INTO wl_tokens (token, wishlist_id, active) VALUES (:token, :id, 1)"),
                {"token": wishlist.public_token, "id": wishlist.id},
            )
            await self.conn.execute(
                text("INSERT INTO wl_invite_tokens (token, wishlist_id) VALUES (:token, :id)"),
                {"token": wishlist.invite_token, "id": wishlist.id},
            )
        except IntegrityError as exc:
            if any(name in str(exc.orig) for name in ("wl_tokens.token", "wl_invite_tokens.token")):
                raise TokenCollision from exc
            raise
        for member in wishlist.members:
            member.wishlist_id = wishlist.id
            await self.upsert_member(member)
        return wishlist

    async def rotate_public_token(
        self, wishlist_id: int, new_token: str, updated_at: datetime
    ) -> None:
        """Deactivate previous public tokens and record a new unique public token."""
        await self._ensure_tokens_available(public_token=new_token)
        try:
            await self.conn.execute(
                text("UPDATE wl_tokens SET active = 0 WHERE wishlist_id = :id"),
                {"id": wishlist_id},
            )
            await self.conn.execute(
                text("INSERT INTO wl_tokens (token, wishlist_id, active) VALUES (:token, :id, 1)"),
                {"token": new_token, "id": wishlist_id},
            )
        except IntegrityError as exc:
            if "wl_tokens.token" in str(exc.orig):
                raise TokenCollision from exc
            raise
        await self.conn.execute(
            text(
                "UPDATE wl_lists SET public_token = :token, updated_at = :updated_at WHERE id = :id"
            ),
            {"token": new_token, "updated_at": _format_dt(updated_at), "id": wishlist_id},
        )
        logger.info(
            "Wishlist repository mutation: rotate public_token for wishlist %s",
            wishlist_id,
            extra={
                "event": "wishlist_repo_mutation",
                "entity": "wishlist_public_token",
                "operation": "rotate",
                "entity_id": wishlist_id,
            },
        )

    async def rotate_invite_token(
        self,
        wishlist_id: int,
        new_token: str,
        expires_at: datetime | None,
        updated_at: datetime,
    ) -> None:
        """Register and set a new unique invite token for a wishlist."""
        await self._ensure_tokens_available(invite_token=new_token)
        try:
            await self.conn.execute(
                text("INSERT INTO wl_invite_tokens (token, wishlist_id) VALUES (:token, :id)"),
                {"token": new_token, "id": wishlist_id},
            )
        except IntegrityError as exc:
            if "wl_invite_tokens.token" in str(exc.orig):
                raise TokenCollision from exc
            raise
        await self.conn.execute(
            text(
                "UPDATE wl_lists SET invite_token = :token, "
                "invite_token_expires_at = :expires_at, updated_at = :updated_at "
                "WHERE id = :id"
            ),
            {
                "token": new_token,
                "expires_at": _format_dt(expires_at),
                "updated_at": _format_dt(updated_at),
                "id": wishlist_id,
            },
        )
        logger.info(
            "Wishlist repository mutation: rotate invite_token for wishlist %s",
            wishlist_id,
            extra={
                "event": "wishlist_repo_mutation",
                "entity": "wishlist_invite_token",
                "operation": "rotate",
                "entity_id": wishlist_id,
                "has_expiry": expires_at is not None,
            },
        )

    async def get_wishlist_header(self, wishlist_id: int) -> Wishlist | None:
        """Load only the list metadata required for a cabinet row."""
        stmt = text(
            "SELECT id, owner_id, owner_name, title, description, event_title, "
            "event_date, is_collaborative, warn_on_delete_reserved, status, "
            "public_token, invite_token, invite_token_expires_at, "
            "created_at, updated_at FROM wl_lists WHERE id = :id"
        )
        row = (await self.conn.execute(stmt, {"id": wishlist_id})).one_or_none()
        return _row_to_wishlist(row) if row is not None else None

    async def get_wishlist_headers_by_ids(self, wishlist_ids: Sequence[int]) -> dict[int, Wishlist]:
        """Batch-load wishlist headers for the given IDs, chunked to bound bind variables."""
        if not wishlist_ids:
            return {}
        chunks = _chunked_unique_ids(wishlist_ids)
        wishlists: dict[int, Wishlist] = {}
        for chunk in chunks:
            placeholders, params = _in_clause_params(chunk, "wl")
            stmt = text(
                "SELECT id, owner_id, owner_name, title, description, event_title, "
                "event_date, is_collaborative, warn_on_delete_reserved, status, "
                "public_token, invite_token, invite_token_expires_at, "
                f"created_at, updated_at FROM wl_lists WHERE id IN ({placeholders})"
            )
            rows = (await self.conn.execute(stmt, params)).all()
            for row in rows:
                wl = _row_to_wishlist(row)
                wishlists[wl.id] = wl
        logger.debug(
            "Wishlist repository batch read: %d/%d wishlist headers (%d chunks)",
            len(wishlists),
            len(wishlist_ids),
            len(chunks),
            extra={
                "event": "wishlist_repo_batch_read",
                "entity": "wishlist_header",
                "requested_count": len(wishlist_ids),
                "chunks_count": len(chunks),
                "found_count": len(wishlists),
            },
        )
        return wishlists

    async def list_user_memberships_by_wishlist_ids(
        self, user_id: int, wishlist_ids: Sequence[int]
    ) -> dict[int, WishlistMember]:
        """Return this user's membership keyed by wishlist id.

        Empty input yields an empty dict. IDs are chunked with the existing
        500-id helper. A wishlist with no row for this user is absent.
        """
        if not wishlist_ids:
            return {}
        chunks = _chunked_unique_ids(wishlist_ids)
        memberships: dict[int, WishlistMember] = {}
        for chunk in chunks:
            placeholders, params = _in_clause_params(chunk, "wl")
            params["uid"] = user_id
            stmt = text(
                "SELECT id, wishlist_id, user_id, role, joined_at "
                "FROM wl_members "
                f"WHERE user_id = :uid AND wishlist_id IN ({placeholders})"
            )
            rows = (await self.conn.execute(stmt, params)).all()
            for row in rows:
                member = _row_to_member(row)
                memberships[member.wishlist_id] = member
        logger.debug(
            "Wishlist repository batch read: %d/%d wishlist members (%d chunks)",
            len(memberships),
            len(wishlist_ids),
            len(chunks),
            extra={
                "event": "wishlist_repo_batch_read",
                "entity": "wishlist_member",
                "requested_count": len(wishlist_ids),
                "chunks_count": len(chunks),
                "found_count": len(memberships),
            },
        )
        return memberships

    async def get_wishlist(self, wishlist_id: int) -> Wishlist | None:
        """Fetch a single wishlist aggregate with members, items, and reservations."""
        stmt = text(
            "SELECT id, owner_id, owner_name, title, description, event_title, "
            "event_date, is_collaborative, warn_on_delete_reserved, status, "
            "public_token, invite_token, invite_token_expires_at, "
            "created_at, updated_at FROM wl_lists WHERE id = :id"
        )
        row = (await self.conn.execute(stmt, {"id": wishlist_id})).one_or_none()
        if row is None:
            return None

        wishlist = _row_to_wishlist(row)

        m_stmt = text(
            "SELECT id, wishlist_id, user_id, role, joined_at "
            "FROM wl_members WHERE wishlist_id = :id ORDER BY id ASC"
        )
        m_rows = (await self.conn.execute(m_stmt, {"id": wishlist_id})).all()
        for m_row in m_rows:
            member = _row_to_member(m_row)
            member.wishlist = wishlist
            wishlist.members.append(member)

        i_stmt = text(
            "SELECT id, wishlist_id, recipient_user_id, recipient_name, title, "
            "description, link, price, currency, quantity, received_quantity, "
            "image_url, store_name, store_icon_url, priority, category, "
            "display_order, is_archived, created_at, updated_at "
            "FROM wl_items WHERE wishlist_id = :id ORDER BY display_order ASC, id ASC"
        )
        i_rows = (await self.conn.execute(i_stmt, {"id": wishlist_id})).all()
        items_map: dict[int, WishItem] = {}
        for i_row in i_rows:
            item = _row_to_item(i_row)
            item.wishlist = wishlist
            wishlist.items.append(item)
            items_map[item.id] = item

        if items_map:
            placeholders = ", ".join(f":i_{k}" for k in range(len(items_map)))
            params = {f"i_{k}": item_id for k, item_id in enumerate(items_map.keys())}
            r_stmt = text(
                "SELECT id, wish_item_id, user_id, quantity, status, created_at, updated_at "
                f"FROM wl_reservations WHERE wish_item_id IN ({placeholders}) ORDER BY id ASC"
            )
            r_rows = (await self.conn.execute(r_stmt, params)).all()
            for r_row in r_rows:
                res = _row_to_reservation(r_row)
                target_item = items_map.get(res.wish_item_id)
                if target_item is not None:
                    res.wish_item = target_item
                    target_item.reservations.append(res)

        return wishlist

    async def get_wishlist_by_id(self, wishlist_id: int) -> Wishlist | None:
        """Alias for get_wishlist."""
        return await self.get_wishlist(wishlist_id)

    async def get_by_public_token(self, token: str) -> Wishlist | None:
        """Fetch wishlist aggregate by its unique public share capability token."""
        stmt = text("SELECT id FROM wl_lists WHERE public_token = :token")
        wl_id = (await self.conn.execute(stmt, {"token": token})).scalar_one_or_none()
        if wl_id is None:
            return None
        return await self.get_wishlist(wl_id)

    async def get_by_invite_token(self, token: str) -> Wishlist | None:
        """Fetch wishlist aggregate by its unique invite capability token."""
        stmt = text("SELECT id FROM wl_lists WHERE invite_token = :token")
        wl_id = (await self.conn.execute(stmt, {"token": token})).scalar_one_or_none()
        if wl_id is None:
            return None
        return await self.get_wishlist(wl_id)

    async def list_by_owner(self, owner_id: int) -> list[Wishlist]:
        """List all non-deleted wishlists owned by the specified user."""
        stmt = text(
            "SELECT id FROM wl_lists WHERE owner_id = :owner_id AND status != 'deleted' "
            "ORDER BY id ASC"
        )
        ids = (await self.conn.execute(stmt, {"owner_id": owner_id})).scalars().all()
        results: list[Wishlist] = []
        for wl_id in ids:
            wl = await self.get_wishlist(wl_id)
            if wl is not None:
                results.append(wl)
        return results

    async def list_user_wishlists(self, owner_id: int) -> list[Wishlist]:
        """Alias for list_by_owner."""
        return await self.list_by_owner(owner_id)

    async def list_accessible_wishlists(
        self, user_id: int, *, include_archived: bool = False
    ) -> list[Wishlist]:
        """List non-deleted wishlists where the user is owner or member."""
        status_clause = "l.status != 'deleted'" if include_archived else "l.status = 'active'"
        stmt = text(
            "SELECT DISTINCT l.id FROM wl_lists l "
            "LEFT JOIN wl_members m ON m.wishlist_id = l.id AND m.user_id = :user_id "
            f"WHERE (l.owner_id = :user_id OR m.user_id IS NOT NULL) AND {status_clause} "
            "ORDER BY l.id ASC"
        )
        ids = (await self.conn.execute(stmt, {"user_id": user_id})).scalars().all()
        results: list[Wishlist] = []
        for wl_id in ids:
            wl = await self.get_wishlist(wl_id)
            if wl is not None:
                results.append(wl)
        return results

    async def list_deleted_by_owner(self, owner_id: int) -> list[Wishlist]:
        """List soft-deleted wishlists owned by the specified user."""
        stmt = text(
            "SELECT id FROM wl_lists WHERE owner_id = :owner_id AND status = 'deleted' "
            "ORDER BY updated_at DESC, id ASC"
        )
        ids = (await self.conn.execute(stmt, {"owner_id": owner_id})).scalars().all()
        results: list[Wishlist] = []
        for wl_id in ids:
            wl = await self.get_wishlist(wl_id)
            if wl is not None:
                results.append(wl)
        return results

    async def upsert_member(self, member: WishlistMember) -> WishlistMember:
        """Insert or update a wishlist membership row."""
        existing_id = await self.conn.scalar(
            text(
                "SELECT id FROM wl_members WHERE wishlist_id = :wishlist_id AND user_id = :user_id"
            ),
            {"wishlist_id": member.wishlist_id, "user_id": member.user_id},
        )
        if existing_id is not None:
            member.id = int(existing_id)
            await self.conn.execute(
                text("UPDATE wl_members SET role = :role, joined_at = :joined_at WHERE id = :id"),
                {
                    "id": member.id,
                    "role": member.role.value,
                    "joined_at": _format_dt(member.joined_at),
                },
            )
        else:
            if member.id <= 0:
                member.id = await self._allocate_id("member", "wl_members")
            await self.conn.execute(
                text(
                    "INSERT INTO wl_members (id, wishlist_id, user_id, role, joined_at) "
                    "VALUES (:id, :wishlist_id, :user_id, :role, :joined_at)"
                ),
                {
                    "id": member.id,
                    "wishlist_id": member.wishlist_id,
                    "user_id": member.user_id,
                    "role": member.role.value,
                    "joined_at": _format_dt(member.joined_at),
                },
            )
        logger.info(
            "Wishlist repository mutation: upsert member user %s wishlist %s",
            member.user_id,
            member.wishlist_id,
            extra={
                "event": "wishlist_repo_mutation",
                "entity": "member",
                "operation": "upsert",
                "entity_id": member.id,
                "wishlist_id": member.wishlist_id,
                "user_id": member.user_id,
                "role": member.role.value,
            },
        )
        return member

    async def delete_member(self, wishlist_id: int, user_id: int) -> None:
        """Remove a member from a wishlist."""
        await self.conn.execute(
            text("DELETE FROM wl_members WHERE wishlist_id = :wishlist_id AND user_id = :user_id"),
            {"wishlist_id": wishlist_id, "user_id": user_id},
        )
        logger.info(
            "Wishlist repository mutation: delete member user %s wishlist %s",
            user_id,
            wishlist_id,
            extra={
                "event": "wishlist_repo_mutation",
                "entity": "member",
                "operation": "delete",
                "wishlist_id": wishlist_id,
                "user_id": user_id,
            },
        )

    async def update_member_role(self, wishlist_id: int, user_id: int, role: WishlistRole) -> None:
        """Update an existing member's role in a wishlist."""
        await self.conn.execute(
            text(
                "UPDATE wl_members SET role = :role "
                "WHERE wishlist_id = :wishlist_id AND user_id = :user_id"
            ),
            {"wishlist_id": wishlist_id, "user_id": user_id, "role": role.value},
        )
        logger.info(
            "Wishlist repository mutation: update member role user %s wishlist %s -> %s",
            user_id,
            wishlist_id,
            role.value,
            extra={
                "event": "wishlist_repo_mutation",
                "entity": "member",
                "operation": "update_role",
                "wishlist_id": wishlist_id,
                "user_id": user_id,
                "role": role.value,
            },
        )

    async def list_collaborative(self, user_id: int) -> list[Wishlist]:
        """List collaborative wishlists where the specified user is a member."""
        stmt = text(
            "SELECT l.id FROM wl_lists l "
            "JOIN wl_members m ON l.id = m.wishlist_id "
            "WHERE m.user_id = :user_id AND l.is_collaborative = 1 AND l.status != 'deleted' "
            "ORDER BY l.id ASC"
        )
        ids = (await self.conn.execute(stmt, {"user_id": user_id})).scalars().all()
        results: list[Wishlist] = []
        for wl_id in ids:
            wl = await self.get_wishlist(wl_id)
            if wl is not None:
                results.append(wl)
        return results

    async def upsert_wishlist(self, wishlist: Wishlist) -> None:
        """Insert or update a wishlist row."""
        params = {
            "id": wishlist.id,
            "owner_id": wishlist.owner_id,
            "owner_name": wishlist.owner_name,
            "title": wishlist.title,
            "description": wishlist.description,
            "event_title": wishlist.event_title,
            "event_date": _format_dt(wishlist.event_date),
            "is_collaborative": 1 if wishlist.is_collaborative else 0,
            "warn_on_delete_reserved": 1 if wishlist.warn_on_delete_reserved else 0,
            "status": wishlist.status.value,
            "public_token": wishlist.public_token,
            "invite_token": wishlist.invite_token,
            "invite_token_expires_at": _format_dt(wishlist.invite_token_expires_at),
            "created_at": _format_dt(wishlist.created_at),
            "updated_at": _format_dt(wishlist.updated_at),
        }
        exists = (
            await self.conn.execute(
                text("SELECT 1 FROM wl_lists WHERE id = :id"), {"id": wishlist.id}
            )
        ).scalar()
        if exists:
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
        await self.conn.execute(stmt, params)
        logger.info(
            "Wishlist repository mutation: upsert wishlist %s",
            wishlist.id,
            extra={
                "event": "wishlist_repo_mutation",
                "entity": "wishlist",
                "operation": "upsert",
                "entity_id": wishlist.id,
                "owner_id": wishlist.owner_id,
                "is_collaborative": wishlist.is_collaborative,
                "status": wishlist.status.value,
            },
        )

    async def save_wishlist(self, wishlist: Wishlist) -> None:
        """Alias for upsert_wishlist."""
        await self.upsert_wishlist(wishlist)

    async def delete_wishlist(self, wishlist_id: int) -> None:
        """Delete a single wishlist row (cascades to members, items, reservations)."""
        await self.conn.execute(text("DELETE FROM wl_lists WHERE id = :id"), {"id": wishlist_id})
        logger.info(
            "Wishlist repository mutation: delete wishlist %s",
            wishlist_id,
            extra={
                "event": "wishlist_repo_mutation",
                "entity": "wishlist",
                "operation": "delete",
                "entity_id": wishlist_id,
            },
        )

    async def get_item(self, item_id: int) -> WishItem | None:
        """Fetch a single wish item with its reservations."""
        stmt = text(
            "SELECT id, wishlist_id, recipient_user_id, recipient_name, title, "
            "description, link, price, currency, quantity, received_quantity, "
            "image_url, store_name, store_icon_url, priority, category, "
            "display_order, is_archived, created_at, updated_at FROM wl_items WHERE id = :id"
        )
        row = (await self.conn.execute(stmt, {"id": item_id})).one_or_none()
        if row is None:
            return None
        item = _row_to_item(row)
        r_stmt = text(
            "SELECT id, wish_item_id, user_id, quantity, status, created_at, updated_at "
            "FROM wl_reservations WHERE wish_item_id = :item_id ORDER BY id ASC"
        )
        r_rows = (await self.conn.execute(r_stmt, {"item_id": item_id})).all()
        for r_row in r_rows:
            res = _row_to_reservation(r_row)
            res.wish_item = item
            item.reservations.append(res)
        return item

    async def get_items_by_ids(self, item_ids: Sequence[int]) -> dict[int, WishItem]:
        """Batch-load wish items and their reservations, chunked to bound bind variables."""
        if not item_ids:
            return {}
        item_chunks = _chunked_unique_ids(item_ids)
        items_map: dict[int, WishItem] = {}
        for chunk in item_chunks:
            placeholders, params = _in_clause_params(chunk, "item")
            stmt = text(
                "SELECT id, wishlist_id, recipient_user_id, recipient_name, title, "
                "description, link, price, currency, quantity, received_quantity, "
                "image_url, store_name, store_icon_url, priority, category, "
                "display_order, is_archived, created_at, updated_at "
                f"FROM wl_items WHERE id IN ({placeholders})"
            )
            rows = (await self.conn.execute(stmt, params)).all()
            for row in rows:
                item = _row_to_item(row)
                items_map[item.id] = item

        if items_map:
            for chunk in _chunked_unique_ids(list(items_map.keys())):
                placeholders, params = _in_clause_params(chunk, "item")
                r_stmt = text(
                    "SELECT id, wish_item_id, user_id, quantity, status, created_at, updated_at "
                    f"FROM wl_reservations WHERE wish_item_id IN ({placeholders}) ORDER BY id ASC"
                )
                r_rows = (await self.conn.execute(r_stmt, params)).all()
                for r_row in r_rows:
                    res = _row_to_reservation(r_row)
                    target_item = items_map.get(res.wish_item_id)
                    if target_item is not None:
                        res.wish_item = target_item
                        target_item.reservations.append(res)

        logger.debug(
            "Wishlist repository batch read: %d/%d items (%d chunks)",
            len(items_map),
            len(item_ids),
            len(item_chunks),
            extra={
                "event": "wishlist_repo_batch_read",
                "entity": "item",
                "requested_count": len(item_ids),
                "chunks_count": len(item_chunks),
                "found_count": len(items_map),
            },
        )
        return items_map

    async def upsert_item(self, item: WishItem) -> None:
        """Insert or update a wish item row."""
        params = {
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
        exists = (
            await self.conn.execute(text("SELECT 1 FROM wl_items WHERE id = :id"), {"id": item.id})
        ).scalar()
        if exists:
            stmt = text(
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
            stmt = text(
                "INSERT INTO wl_items (id, wishlist_id, recipient_user_id, recipient_name, "
                "title, description, link, price, currency, quantity, received_quantity, "
                "image_url, store_name, store_icon_url, priority, category, "
                "display_order, is_archived, created_at, updated_at) "
                "VALUES (:id, :wishlist_id, :recipient_user_id, "
                ":recipient_name, :title, :description, :link, :price, :currency, "
                ":quantity, :received_quantity, :image_url, :store_name, :store_icon_url, "
                ":priority, :category, :display_order, :is_archived, :created_at, :updated_at)"
            )
        await self.conn.execute(stmt, params)
        logger.info(
            "Wishlist repository mutation: upsert item %s for wishlist %s",
            item.id,
            item.wishlist_id,
            extra={
                "event": "wishlist_repo_mutation",
                "entity": "item",
                "operation": "upsert",
                "entity_id": item.id,
                "wishlist_id": item.wishlist_id,
                "priority": item.priority.value,
                "is_archived": item.is_archived,
            },
        )

    async def create_item(self, item: WishItem) -> WishItem:
        """Allocate an item ID if needed and insert the wish item."""
        if item.id <= 0:
            item.id = await self._allocate_id("item", "wl_items")
        await self.upsert_item(item)
        return item

    async def reorder_items(
        self, wishlist_id: int, order_map: dict[int, int], updated_at: datetime
    ) -> None:
        """Update display_order for items in a wishlist."""
        updated_str = _format_dt(updated_at)
        for item_id, display_order in order_map.items():
            await self.conn.execute(
                text(
                    "UPDATE wl_items SET display_order = :display_order, updated_at = :updated_at "
                    "WHERE id = :id AND wishlist_id = :wishlist_id"
                ),
                {
                    "id": item_id,
                    "wishlist_id": wishlist_id,
                    "display_order": display_order,
                    "updated_at": updated_str,
                },
            )
        logger.info(
            "Wishlist repository mutation: reorder %d items in wishlist %s",
            len(order_map),
            wishlist_id,
            extra={
                "event": "wishlist_repo_mutation",
                "entity": "item",
                "operation": "reorder",
                "wishlist_id": wishlist_id,
                "count": len(order_map),
            },
        )

    async def list_item_receipts(self, item_id: int) -> list[ReceiptRecord]:
        """List receipt records for a single wish item."""
        stmt = text(
            "SELECT id, wish_item_id, quantity, received_at, is_approximate "
            "FROM wl_receipts WHERE wish_item_id = :item_id ORDER BY received_at ASC, id ASC"
        )
        rows = (await self.conn.execute(stmt, {"item_id": item_id})).all()
        return [
            ReceiptRecord(
                id=int(r.id),
                wish_item_id=int(r.wish_item_id),
                quantity=int(r.quantity),
                received_at=_parse_dt(r.received_at) or datetime.now(UTC),
                is_approximate=bool(r.is_approximate),
            )
            for r in rows
        ]

    async def list_receipts_for_wishlist(self, wishlist_id: int) -> dict[int, list[ReceiptRecord]]:
        """List receipt records grouped by wish_item_id for all items in a wishlist."""
        stmt = text(
            "SELECT r.id, r.wish_item_id, r.quantity, r.received_at, r.is_approximate "
            "FROM wl_receipts r JOIN wl_items i ON i.id = r.wish_item_id "
            "WHERE i.wishlist_id = :wishlist_id ORDER BY r.received_at ASC, r.id ASC"
        )
        rows = (await self.conn.execute(stmt, {"wishlist_id": wishlist_id})).all()
        grouped: dict[int, list[ReceiptRecord]] = {}
        for r in rows:
            rec = ReceiptRecord(
                id=int(r.id),
                wish_item_id=int(r.wish_item_id),
                quantity=int(r.quantity),
                received_at=_parse_dt(r.received_at) or datetime.now(UTC),
                is_approximate=bool(r.is_approximate),
            )
            grouped.setdefault(rec.wish_item_id, []).append(rec)
        return grouped

    async def is_favorite(self, user_id: int, wishlist_id: int) -> bool:
        """Return True if the user has bookmarked the wishlist."""
        row = await self.conn.scalar(
            text("SELECT 1 FROM wl_favorites WHERE user_id = :uid AND wishlist_id = :wlid"),
            {"uid": user_id, "wlid": wishlist_id},
        )
        return row is not None

    async def list_favorite_ids(self, user_id: int) -> set[int]:
        """Return the set of accessible non-deleted wishlist IDs bookmarked by the user."""
        rows = (
            (
                await self.conn.execute(
                    text(
                        "SELECT f.wishlist_id FROM wl_favorites f "
                        "JOIN wl_lists l ON l.id = f.wishlist_id "
                        "WHERE f.user_id = :uid AND l.status != 'deleted' "
                        "AND l.owner_id != :uid "
                        "AND ("
                        "  EXISTS (SELECT 1 FROM wl_members m "
                        "          WHERE m.wishlist_id = f.wishlist_id AND m.user_id = :uid) "
                        "  OR EXISTS (SELECT 1 FROM wl_share_access sa "
                        "             WHERE sa.wishlist_id = f.wishlist_id "
                        "               AND sa.user_id = :uid "
                        "               AND sa.public_token = l.public_token)"
                        ")"
                    ),
                    {"uid": user_id},
                )
            )
            .scalars()
            .all()
        )
        return {int(wl_id) for wl_id in rows}

    async def list_favorite_wishlists(self, user_id: int) -> list[Wishlist]:
        """List accessible non-deleted wishlists bookmarked by the user in most-recent order."""
        stmt = text(
            "SELECT f.wishlist_id FROM wl_favorites f "
            "JOIN wl_lists l ON l.id = f.wishlist_id "
            "WHERE f.user_id = :uid AND l.status != 'deleted' "
            "AND l.owner_id != :uid "
            "AND ("
            "  EXISTS (SELECT 1 FROM wl_members m "
            "          WHERE m.wishlist_id = f.wishlist_id AND m.user_id = :uid) "
            "  OR EXISTS (SELECT 1 FROM wl_share_access sa "
            "             WHERE sa.wishlist_id = f.wishlist_id "
            "               AND sa.user_id = :uid "
            "               AND sa.public_token = l.public_token)"
            ") "
            "ORDER BY f.created_at DESC"
        )
        ids = (await self.conn.execute(stmt, {"uid": user_id})).scalars().all()
        results: list[Wishlist] = []
        for wl_id in ids:
            wl = await self.get_wishlist(wl_id)
            if wl is not None:
                results.append(wl)
        return results

    async def save_item(self, item: WishItem) -> None:
        """Alias for upsert_item."""
        await self.upsert_item(item)

    async def delete_item(self, item_id: int) -> None:
        """Delete a single wish item row (cascades to reservations)."""
        await self.conn.execute(text("DELETE FROM wl_items WHERE id = :id"), {"id": item_id})
        logger.info(
            "Wishlist repository mutation: delete item %s",
            item_id,
            extra={
                "event": "wishlist_repo_mutation",
                "entity": "item",
                "operation": "delete",
                "entity_id": item_id,
            },
        )

    async def upsert_reservation(self, res: Reservation) -> None:
        """Insert or update a reservation row."""
        params = {
            "id": res.id,
            "wish_item_id": res.wish_item_id,
            "user_id": res.user_id,
            "quantity": res.quantity,
            "status": res.status.value,
            "created_at": _format_dt(res.created_at),
            "updated_at": _format_dt(res.updated_at),
        }
        exists = (
            await self.conn.execute(
                text("SELECT 1 FROM wl_reservations WHERE id = :id"), {"id": res.id}
            )
        ).scalar()
        if exists:
            stmt = text(
                "UPDATE wl_reservations SET "
                "quantity = :quantity, status = :status, updated_at = :updated_at "
                "WHERE id = :id"
            )
        else:
            stmt = text(
                "INSERT INTO wl_reservations (id, wish_item_id, user_id, quantity, "
                "status, created_at, updated_at) "
                "VALUES (:id, :wish_item_id, :user_id, :quantity, :status, "
                ":created_at, :updated_at)"
            )
        await self.conn.execute(stmt, params)
        logger.info(
            "Wishlist repository mutation: upsert reservation %s for item %s",
            res.id,
            res.wish_item_id,
            extra={
                "event": "wishlist_repo_mutation",
                "entity": "reservation",
                "operation": "upsert",
                "entity_id": res.id,
                "item_id": res.wish_item_id,
                "user_id": res.user_id,
                "status": res.status.value,
            },
        )

    async def create_reservation(self, res: Reservation) -> None:
        """Alias for upsert_reservation."""
        await self.upsert_reservation(res)

    async def cancel_wishlist_reservations(self, wishlist_id: int, updated_at: datetime) -> int:
        """Cancel all active or purchased reservations for items in a wishlist."""
        res = await self.conn.execute(
            text(
                "UPDATE wl_reservations SET status = 'cancelled', updated_at = :updated_at "
                "WHERE wish_item_id IN (SELECT id FROM wl_items WHERE wishlist_id = :wishlist_id) "
                "AND status IN ('active', 'purchased')"
            ),
            {"wishlist_id": wishlist_id, "updated_at": _format_dt(updated_at)},
        )
        cancelled_count = int(res.rowcount or 0)
        logger.info(
            "Wishlist repository mutation: cancel reservations for wishlist %s (count=%s)",
            wishlist_id,
            cancelled_count,
            extra={
                "event": "wishlist_repo_mutation",
                "entity": "reservation",
                "operation": "cancel_for_wishlist",
                "wishlist_id": wishlist_id,
                "cancelled_count": cancelled_count,
            },
        )
        return cancelled_count

    async def delete_reservation(self, res_id: int) -> None:
        """Delete a single reservation row."""
        await self.conn.execute(text("DELETE FROM wl_reservations WHERE id = :id"), {"id": res_id})
        logger.info(
            "Wishlist repository mutation: delete reservation %s",
            res_id,
            extra={
                "event": "wishlist_repo_mutation",
                "entity": "reservation",
                "operation": "delete",
                "entity_id": res_id,
            },
        )

    async def cancel_reservation(self, res_id: int) -> None:
        """Alias for delete_reservation."""
        await self.delete_reservation(res_id)

    async def list_user_reservations(self, user_id: int) -> list[Reservation]:
        """List all active or purchased reservations made by the specified user."""
        stmt = text(
            "SELECT id, wish_item_id, user_id, quantity, status, created_at, updated_at "
            "FROM wl_reservations WHERE user_id = :user_id "
            "AND status IN ('active', 'purchased') ORDER BY id ASC"
        )
        rows = (await self.conn.execute(stmt, {"user_id": user_id})).all()
        return [_row_to_reservation(r) for r in rows]

    async def upsert_favorite(self, fav: WishlistFavorite) -> None:
        """Add a wishlist favorite bookmark."""
        stmt = text(
            "INSERT INTO wl_favorites (user_id, wishlist_id, created_at) "
            "VALUES (:user_id, :wishlist_id, :created_at) "
            "ON CONFLICT(user_id, wishlist_id) DO NOTHING"
        )
        await self.conn.execute(
            stmt,
            {
                "user_id": fav.user_id,
                "wishlist_id": fav.wishlist_id,
                "created_at": _format_dt(fav.created_at),
            },
        )
        logger.info(
            "Wishlist repository mutation: upsert favorite user %s wishlist %s",
            fav.user_id,
            fav.wishlist_id,
            extra={
                "event": "wishlist_repo_mutation",
                "entity": "favorite",
                "operation": "upsert",
                "user_id": fav.user_id,
                "wishlist_id": fav.wishlist_id,
            },
        )

    async def delete_favorite(self, user_id: int, wishlist_id: int) -> None:
        """Remove a wishlist favorite bookmark."""
        await self.conn.execute(
            text("DELETE FROM wl_favorites WHERE user_id = :uid AND wishlist_id = :wlid"),
            {"uid": user_id, "wlid": wishlist_id},
        )
        logger.info(
            "Wishlist repository mutation: delete favorite user %s wishlist %s",
            user_id,
            wishlist_id,
            extra={
                "event": "wishlist_repo_mutation",
                "entity": "favorite",
                "operation": "delete",
                "user_id": user_id,
                "wishlist_id": wishlist_id,
            },
        )

    async def list_favorites(self, user_id: int) -> list[WishlistFavorite]:
        """List favorites for the specified user."""
        stmt = text(
            "SELECT user_id, wishlist_id, created_at FROM wl_favorites "
            "WHERE user_id = :uid ORDER BY created_at DESC"
        )
        rows = (await self.conn.execute(stmt, {"uid": user_id})).all()
        return [
            WishlistFavorite(
                user_id=int(r.user_id),
                wishlist_id=int(r.wishlist_id),
                created_at=_parse_dt(r.created_at) or datetime.now(UTC),
            )
            for r in rows
        ]

    async def upsert_share_access(self, grant: ShareAccessGrant) -> bool:
        """Record or refresh a verified share-link access grant; return True if persisted."""
        stmt = text(
            "INSERT INTO wl_share_access (user_id, wishlist_id, public_token, granted_at) "
            "SELECT :user_id, :wishlist_id, :public_token, :granted_at "
            "WHERE EXISTS (SELECT 1 FROM users WHERE telegram_id = :user_id) "
            "ON CONFLICT(user_id, wishlist_id) DO UPDATE SET "
            "public_token = excluded.public_token, granted_at = excluded.granted_at"
        )
        result = await self.conn.execute(
            stmt,
            {
                "user_id": grant.user_id,
                "wishlist_id": grant.wishlist_id,
                "public_token": grant.public_token,
                "granted_at": _format_dt(grant.granted_at),
            },
        )
        return int(result.rowcount or 0) > 0

    async def has_valid_share_access(
        self, user_id: int, wishlist_id: int, public_token: str
    ) -> bool:
        """Return True if the user has a share-access grant matching the active public_token."""
        row = await self.conn.scalar(
            text(
                "SELECT 1 FROM wl_share_access "
                "WHERE user_id = :uid AND wishlist_id = :wlid AND public_token = :tok"
            ),
            {"uid": user_id, "wlid": wishlist_id, "tok": public_token},
        )
        return row is not None

    async def user_exists(self, user_id: int) -> bool:
        """Return True if a user row exists in users for the given telegram_id."""
        row = await self.conn.scalar(
            text("SELECT 1 FROM users WHERE telegram_id = :uid"),
            {"uid": user_id},
        )
        return row is not None

    async def revoke_share_access_for_wishlist(self, wishlist_id: int) -> int:
        """Delete all share-link access grants for a wishlist and return the deleted count."""
        result = await self.conn.execute(
            text("DELETE FROM wl_share_access WHERE wishlist_id = :wlid"),
            {"wlid": wishlist_id},
        )
        return int(result.rowcount or 0)

    async def delete_non_member_favorites(self, wishlist_id: int) -> int:
        """Delete favorite rows for non-members of a wishlist and return the deleted count."""
        result = await self.conn.execute(
            text(
                "DELETE FROM wl_favorites "
                "WHERE wishlist_id = :wlid "
                "AND NOT EXISTS ("
                "  SELECT 1 FROM wl_members m "
                "  WHERE m.wishlist_id = wl_favorites.wishlist_id "
                "    AND m.user_id = wl_favorites.user_id"
                ")"
            ),
            {"wlid": wishlist_id},
        )
        return int(result.rowcount or 0)

    async def delete_favorite_if_no_share_access(
        self, user_id: int, wishlist_id: int, public_token: str
    ) -> int:
        """Delete a user's favorite row unless they hold a valid grant; return deleted count."""
        result = await self.conn.execute(
            text(
                "DELETE FROM wl_favorites "
                "WHERE user_id = :uid AND wishlist_id = :wlid "
                "AND NOT EXISTS ("
                "  SELECT 1 FROM wl_share_access sa "
                "  WHERE sa.user_id = :uid AND sa.wishlist_id = :wlid "
                "    AND sa.public_token = :tok"
                ")"
            ),
            {"uid": user_id, "wlid": wishlist_id, "tok": public_token},
        )
        return int(result.rowcount or 0)

    async def delete_non_member_history(self, wishlist_id: int) -> int:
        """Delete view history rows for non-owners/non-members of a wishlist."""
        result = await self.conn.execute(
            text(
                "DELETE FROM wl_view_history "
                "WHERE wishlist_id = :wlid "
                "AND NOT EXISTS ("
                "  SELECT 1 FROM wl_lists l "
                "  WHERE l.id = wl_view_history.wishlist_id "
                "    AND l.owner_id = wl_view_history.user_id"
                ") "
                "AND NOT EXISTS ("
                "  SELECT 1 FROM wl_members m "
                "  WHERE m.wishlist_id = wl_view_history.wishlist_id "
                "    AND m.user_id = wl_view_history.user_id"
                ")"
            ),
            {"wlid": wishlist_id},
        )
        return int(result.rowcount or 0)

    async def delete_history_if_no_share_access(
        self, user_id: int, wishlist_id: int, public_token: str
    ) -> int:
        """Delete a user's view history row unless owner/member or holding a valid grant."""
        result = await self.conn.execute(
            text(
                "DELETE FROM wl_view_history "
                "WHERE user_id = :uid AND wishlist_id = :wlid "
                "AND NOT EXISTS ("
                "  SELECT 1 FROM wl_lists l "
                "  WHERE l.id = :wlid AND l.owner_id = :uid"
                ") "
                "AND NOT EXISTS ("
                "  SELECT 1 FROM wl_members m "
                "  WHERE m.wishlist_id = :wlid AND m.user_id = :uid"
                ") "
                "AND NOT EXISTS ("
                "  SELECT 1 FROM wl_share_access sa "
                "  WHERE sa.user_id = :uid AND sa.wishlist_id = :wlid "
                "    AND sa.public_token = :tok"
                ")"
            ),
            {"uid": user_id, "wlid": wishlist_id, "tok": public_token},
        )
        return int(result.rowcount or 0)

    async def record_view(self, entry: ViewHistoryEntry) -> None:
        """Record or refresh a user's wishlist view and assign the next recording sequence."""
        entry.recorded_seq = await self._next_sequence("view_history_seq")
        stmt = text(
            "INSERT INTO wl_view_history (user_id, wishlist_id, viewed_at, recorded_seq) "
            "VALUES (:user_id, :wishlist_id, :viewed_at, :recorded_seq) "
            "ON CONFLICT(user_id, wishlist_id) DO UPDATE SET "
            "viewed_at = excluded.viewed_at, recorded_seq = excluded.recorded_seq"
        )
        await self.conn.execute(
            stmt,
            {
                "user_id": entry.user_id,
                "wishlist_id": entry.wishlist_id,
                "viewed_at": _format_dt(entry.viewed_at),
                "recorded_seq": entry.recorded_seq,
            },
        )
        logger.info(
            "Wishlist repository mutation: record view user %s wishlist %s",
            entry.user_id,
            entry.wishlist_id,
            extra={
                "event": "wishlist_repo_mutation",
                "entity": "view_history",
                "operation": "record",
                "user_id": entry.user_id,
                "wishlist_id": entry.wishlist_id,
            },
        )

    async def list_view_history(self, user_id: int, limit: int = 20) -> list[ViewHistoryEntry]:
        """List recent accessible viewing history for user up to limit."""
        stmt = text(
            "SELECT vh.id, vh.user_id, vh.wishlist_id, vh.viewed_at, vh.recorded_seq "
            "FROM wl_view_history vh "
            "JOIN wl_lists l ON l.id = vh.wishlist_id "
            "WHERE vh.user_id = :uid "
            "  AND l.status != :deleted_status "
            "  AND ("
            "    l.owner_id = :uid "
            "    OR EXISTS ("
            "      SELECT 1 FROM wl_members m "
            "      WHERE m.wishlist_id = l.id AND m.user_id = :uid"
            "    ) "
            "    OR EXISTS ("
            "      SELECT 1 FROM wl_share_access sa "
            "      WHERE sa.wishlist_id = l.id "
            "        AND sa.user_id = :uid "
            "        AND sa.public_token = l.public_token"
            "    )"
            "  ) "
            "ORDER BY vh.viewed_at DESC, vh.recorded_seq DESC LIMIT :lim"
        )
        rows = (
            await self.conn.execute(
                stmt,
                {
                    "uid": user_id,
                    "deleted_status": WishlistStatus.DELETED.value,
                    "lim": limit,
                },
            )
        ).all()
        return [
            ViewHistoryEntry(
                id=int(r.id),
                user_id=int(r.user_id),
                wishlist_id=int(r.wishlist_id),
                viewed_at=_parse_dt(r.viewed_at) or datetime.now(UTC),
                recorded_seq=int(r.recorded_seq),
            )
            for r in rows
        ]

    async def clear_view_history(self, user_id: int) -> int:
        """Clear all viewing history entries for the specified user."""
        res = await self.conn.execute(
            text("DELETE FROM wl_view_history WHERE user_id = :uid"), {"uid": user_id}
        )
        removed_count = int(res.rowcount) if res.rowcount is not None and res.rowcount >= 0 else 0
        logger.info(
            "Wishlist repository mutation: clear view history user %s",
            user_id,
            extra={
                "event": "wishlist_repo_mutation",
                "entity": "view_history",
                "operation": "clear",
                "user_id": user_id,
                "removed_count": removed_count,
            },
        )
        return removed_count

    async def cleanup_expired_tokens(self, now: datetime | None = None) -> int:
        """Revoke expired invite tokens and remove them from wl_invite_tokens."""
        if now is None:
            now = datetime.now(UTC)
        now_str = _format_dt(now)

        stmt_select = text(
            "SELECT invite_token FROM wl_lists "
            "WHERE invite_token_expires_at IS NOT NULL "
            "AND invite_token_expires_at <= :now"
        )
        rows = (await self.conn.execute(stmt_select, {"now": now_str})).fetchall()
        if not rows:
            return 0

        stmt_del_invites = text(
            "DELETE FROM wl_invite_tokens "
            "WHERE token IN ("
            "  SELECT invite_token FROM wl_lists "
            "  WHERE invite_token_expires_at IS NOT NULL "
            "  AND invite_token_expires_at <= :now"
            ")"
        )
        await self.conn.execute(stmt_del_invites, {"now": now_str})

        stmt_update = text(
            "UPDATE wl_lists "
            "SET invite_token = CASE "
            "  WHEN invite_token LIKE 'revoked:%' THEN invite_token "
            "  ELSE 'revoked:' || invite_token "
            "END, "
            "invite_token_expires_at = NULL "
            "WHERE invite_token_expires_at IS NOT NULL "
            "AND invite_token_expires_at <= :now"
        )
        res = await self.conn.execute(stmt_update, {"now": now_str})
        cleaned_count = (
            res.rowcount if res.rowcount is not None and res.rowcount >= 0 else len(rows)
        )

        logger.info(
            "Wishlist repository mutation: cleanup %s expired invite tokens",
            cleaned_count,
            extra={
                "event": "wishlist_repo_mutation",
                "entity": "invite_token",
                "operation": "cleanup_expired",
                "count": cleaned_count,
            },
        )
        return cleaned_count

    async def purge_archived_wishlists(self, threshold: datetime) -> int:
        """Permanently purge soft-deleted wishlists older than threshold."""
        threshold_str = _format_dt(threshold)
        stmt_select = text(
            "SELECT id FROM wl_lists WHERE status = 'deleted' AND updated_at <= :threshold"
        )
        rows = (await self.conn.execute(stmt_select, {"threshold": threshold_str})).fetchall()
        if not rows:
            return 0

        await self.conn.exec_driver_sql("PRAGMA foreign_keys = ON")

        stmt_del_tokens = text(
            "DELETE FROM wl_tokens "
            "WHERE wishlist_id IN ("
            "  SELECT id FROM wl_lists "
            "  WHERE status = 'deleted' AND updated_at <= :threshold"
            ")"
        )
        await self.conn.execute(stmt_del_tokens, {"threshold": threshold_str})

        stmt_del_invites = text(
            "DELETE FROM wl_invite_tokens "
            "WHERE token IN ("
            "  SELECT invite_token FROM wl_lists "
            "  WHERE status = 'deleted' AND updated_at <= :threshold"
            ")"
        )
        await self.conn.execute(stmt_del_invites, {"threshold": threshold_str})

        stmt_del_lists = text(
            "DELETE FROM wl_lists WHERE status = 'deleted' AND updated_at <= :threshold"
        )
        res = await self.conn.execute(stmt_del_lists, {"threshold": threshold_str})
        purged_count = res.rowcount if res.rowcount is not None and res.rowcount >= 0 else len(rows)

        logger.info(
            "Wishlist repository mutation: purge %s archived wishlists older than %s",
            purged_count,
            threshold_str,
            extra={
                "event": "wishlist_repo_mutation",
                "entity": "wishlist",
                "operation": "purge_archived",
                "count": purged_count,
                "threshold": threshold_str,
            },
        )
        return purged_count

    async def purge_deleted_wishlists(self, threshold: datetime) -> int:
        """Alias for purge_archived_wishlists."""
        return await self.purge_archived_wishlists(threshold)
