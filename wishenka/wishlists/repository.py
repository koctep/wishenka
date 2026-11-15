"""Async repository providing granular queries and mutations for wishlist entities."""

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Row, text
from sqlalchemy.ext.asyncio import AsyncConnection

from wishenka.currency import DEFAULT_CURRENCY
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

logger = logging.getLogger(__name__)


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
    price = int(row.price) if row.price is not None else None
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

    async def record_view(self, entry: ViewHistoryEntry) -> None:
        """Record or update viewing timestamp for a user and wishlist."""
        stmt = text(
            "INSERT INTO wl_view_history (user_id, wishlist_id, viewed_at) "
            "VALUES (:user_id, :wishlist_id, :viewed_at) "
            "ON CONFLICT(user_id, wishlist_id) DO UPDATE SET viewed_at = excluded.viewed_at"
        )
        await self.conn.execute(
            stmt,
            {
                "user_id": entry.user_id,
                "wishlist_id": entry.wishlist_id,
                "viewed_at": _format_dt(entry.viewed_at),
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
        """List recent viewing history for user up to limit."""
        stmt = text(
            "SELECT id, user_id, wishlist_id, viewed_at FROM wl_view_history "
            "WHERE user_id = :uid ORDER BY viewed_at DESC LIMIT :lim"
        )
        rows = (await self.conn.execute(stmt, {"uid": user_id, "lim": limit})).all()
        return [
            ViewHistoryEntry(
                id=int(r.id),
                user_id=int(r.user_id),
                wishlist_id=int(r.wishlist_id),
                viewed_at=_parse_dt(r.viewed_at) or datetime.now(UTC),
            )
            for r in rows
        ]

    async def clear_view_history(self, user_id: int) -> None:
        """Clear all viewing history entries for the specified user."""
        await self.conn.execute(
            text("DELETE FROM wl_view_history WHERE user_id = :uid"), {"uid": user_id}
        )
        logger.info(
            "Wishlist repository mutation: clear view history user %s",
            user_id,
            extra={
                "event": "wishlist_repo_mutation",
                "entity": "view_history",
                "operation": "clear",
                "user_id": user_id,
            },
        )

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
