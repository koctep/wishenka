"""Targeted repository-backed wishlist operations for FastAPI web routes."""

from __future__ import annotations

import logging
import math
import secrets
from datetime import UTC, datetime, timedelta

from wishenka.auth.models import AuthenticatedUser
from wishenka.currency import DEFAULT_CURRENCY
from wishenka.items.models import ItemPriority
from wishenka.notices.events import EventProducer, SharedEvent
from wishenka.wishlists.exceptions import (
    InvalidInviteTokenError,
    ItemNotFoundError,
    NothingRemainingError,
    PermissionDeniedError,
    TokenCollision,
    WishlistArchivedError,
    WishlistDeletedError,
    WishlistNotFoundError,
    WishlistRetentionExpiredError,
)
from wishenka.wishlists.models import (
    ReservationStatus,
    ViewHistoryEntry,
    WishItem,
    Wishlist,
    WishlistFavorite,
    WishlistFormat,
    WishlistMember,
    WishlistRole,
    WishlistStatus,
    WishlistTimeType,
)
from wishenka.wishlists.policy import WishlistAccessPolicy
from wishenka.wishlists.repository import WishlistRepository
from wishenka.wishlists.schemas import (
    GiftedItemDTO,
    ReceiptEntryDTO,
    WishItemGifterViewDTO,
    WishItemRecipientViewDTO,
    WishlistDetailViewDTO,
)
from wishenka.wishlists.service import WishlistService, project_wish_item, recipient_view

logger = logging.getLogger("wishenka.wishlists")

DEFAULT_INVITE_TTL = timedelta(days=7)
_TOKEN_ATTEMPTS = 5


class RepoWishlistOps:
    """Execute wishlist domain operations via targeted WishlistRepository queries."""

    def __init__(self, repo: WishlistRepository) -> None:
        self.repo = repo

    @staticmethod
    def _ensure_wishlist_active(wishlist: Wishlist) -> None:
        if wishlist.status == WishlistStatus.ARCHIVED:
            raise WishlistArchivedError(f"Wishlist {wishlist.id} is archived")
        if wishlist.status == WishlistStatus.DELETED:
            raise WishlistDeletedError(f"Wishlist {wishlist.id} is deleted")

    async def record_shared_event(
        self,
        kind: str,
        wishlist: Wishlist,
        item: WishItem | None,
        actor_id: int,
        *,
        exclude_recipients: frozenset[int] = frozenset(),
    ) -> None:
        """Persist candidate shared-list notification intents in the current transaction."""
        recipients = {wishlist.owner_id, *(member.user_id for member in wishlist.members)}
        items = (
            wishlist.items
            if kind in ("list_archived", "list_restored", "list_updated")
            else ([item] if item is not None else [])
        )
        for wish in items:
            recipients.update(
                reservation.user_id
                for reservation in wish.reservations
                if reservation.status in (ReservationStatus.ACTIVE, ReservationStatus.PURCHASED)
                and not WishlistAccessPolicy.is_recipient_id(reservation.user_id, wish)
            )
        recipients.discard(actor_id)
        recipients.difference_update(exclude_recipients)
        if not recipients:
            return
        event = SharedEvent(
            kind,
            wishlist.id,
            item.id if item else None,
            secrets.token_hex(16),
            tuple(sorted(recipients)),
            frozenset(member.user_id for member in wishlist.members),
        )
        await EventProducer().record(self.repo.conn, event, int(datetime.now(UTC).timestamp()))

    async def get_wishlist_by_id(
        self, wishlist_id: int, *, allow_deleted: bool = False
    ) -> Wishlist:
        """Load a single wishlist aggregate or raise not-found/deleted error."""
        wl = await self.repo.get_wishlist(wishlist_id)
        if wl is None:
            raise WishlistNotFoundError(f"Wishlist {wishlist_id} not found")
        if not allow_deleted and wl.status == WishlistStatus.DELETED:
            raise WishlistDeletedError(f"Wishlist {wishlist_id} has been deleted")
        return wl

    async def create_wishlist(
        self,
        owner: AuthenticatedUser | None = None,
        title: str = "",
        description: str | None = None,
        event_title: str | None = None,
        event_date: datetime | None = None,
        invite_token_expires_in: timedelta | None = None,
        owner_id: int | None = None,
    ) -> Wishlist:
        """Create a new personal wishlist with unique capability tokens."""
        effective_owner_id = owner.telegram_id if owner is not None else (owner_id or 0)
        effective_owner_name = owner.first_name if owner is not None else ""
        ttl = invite_token_expires_in if invite_token_expires_in is not None else DEFAULT_INVITE_TTL
        now = datetime.now(UTC)

        wishlist: Wishlist | None = None
        for attempt in range(_TOKEN_ATTEMPTS):
            candidate = Wishlist(
                id=0,
                owner_id=effective_owner_id,
                owner_name=effective_owner_name,
                title=title,
                description=description,
                event_title=event_title,
                event_date=event_date,
                is_collaborative=False,
                status=WishlistStatus.ACTIVE,
                public_token=secrets.token_urlsafe(16),
                invite_token=secrets.token_urlsafe(24),
                invite_token_expires_at=now + ttl,
                created_at=now,
                updated_at=now,
                members=[],
                items=[],
            )
            try:
                wishlist = await self.repo.create_wishlist(candidate)
                break
            except TokenCollision:
                if attempt == _TOKEN_ATTEMPTS - 1:
                    raise

        assert wishlist is not None
        time_type = (
            WishlistTimeType.EVENT.value
            if event_date is not None
            else WishlistTimeType.ONGOING.value
        )
        logger.info(
            "Wishlist %s created by user %s",
            wishlist.id,
            effective_owner_id,
            extra={
                "event": "wishlist_created",
                "wishlist_id": wishlist.id,
                "owner_id": effective_owner_id,
                "format": WishlistFormat.PERSONAL.value,
                "time_type": time_type,
                "event_date": event_date.isoformat() if event_date is not None else None,
            },
        )
        return wishlist

    async def get_wishlist_view(
        self,
        wishlist_id: int,
        current_user: AuthenticatedUser | None = None,
    ) -> WishlistDetailViewDTO:
        """Project wishlist and items applying Surprise Invariant rules."""
        wl = await self.get_wishlist_by_id(wishlist_id)
        return self.project_wishlist_view(wl, current_user)

    @staticmethod
    def project_wishlist_view(
        wl: Wishlist,
        current_user: AuthenticatedUser | None = None,
    ) -> WishlistDetailViewDTO:
        """Project an already-loaded wishlist aggregate applying Surprise Invariant rules."""
        active_items = sorted(
            [item for item in wl.items if item.is_active],
            key=lambda it: (it.display_order, it.created_at, it.id),
        )
        item_views: list[WishItemRecipientViewDTO | WishItemGifterViewDTO] = [
            project_wish_item(item, current_user) for item in active_items
        ]
        ctx = WishlistAccessPolicy.resolve_context(current_user, wl)
        archived_views: list[WishItemRecipientViewDTO] = []
        if ctx.is_member:
            archived_raw = sorted(
                [item for item in wl.items if item.is_in_archive],
                key=lambda it: (it.display_order, it.created_at, it.id),
            )
            archived_views = [recipient_view(item) for item in archived_raw]

        return WishlistDetailViewDTO(
            id=wl.id,
            title=wl.title,
            owner_name=wl.owner_name,
            description=wl.description,
            event_title=wl.event_title,
            event_date=wl.event_date,
            is_collaborative=wl.is_collaborative,
            warn_on_delete_reserved=wl.warn_on_delete_reserved,
            status=wl.status,
            user_role=ctx.role,
            can_edit=WishlistAccessPolicy.can_edit_settings(ctx, wl),
            can_archive=WishlistAccessPolicy.can_archive(ctx, wl),
            can_delete=WishlistAccessPolicy.can_delete(ctx, wl),
            public_token=wl.public_token,
            invite_token=wl.invite_token if (ctx.is_owner or ctx.is_admin) else None,
            items=item_views,
            archived_items=archived_views,
        )

    async def get_wishlist_by_public_token(
        self,
        public_token: str,
        current_user: AuthenticatedUser | None = None,
    ) -> WishlistDetailViewDTO:
        """Retrieve wishlist projection via public token for gift viewing."""
        wl = await self.repo.get_by_public_token(public_token)
        if wl is None:
            logger.warning(
                "Public token lookup failed: token not found",
                extra={"event": "public_token_not_found"},
            )
            raise WishlistNotFoundError("Wishlist not found")
        if wl.status == WishlistStatus.DELETED:
            logger.warning(
                "Public token lookup failed: wishlist %s is deleted",
                wl.id,
                extra={"event": "deleted_wishlist_access_attempt", "wishlist_id": wl.id},
            )
            raise WishlistDeletedError(f"Wishlist {wl.id} has been deleted")
        view = self.project_wishlist_view(wl, current_user)
        has_gifter_view = any(isinstance(item, WishItemGifterViewDTO) for item in view.items) or (
            not view.items and view.user_role is None
        )
        projection_mode = (
            "anonymous_safe"
            if current_user is None
            else ("gifter" if has_gifter_view else "recipient_safe")
        )
        logger.info(
            "Public wishlist resolved: wishlist_id=%s identified=%s projection_mode=%s",
            wl.id,
            current_user is not None,
            projection_mode,
            extra={
                "event": "public_wishlist_resolved",
                "wishlist_id": wl.id,
                "identified": current_user is not None,
                "user_id": current_user.telegram_id if current_user is not None else None,
                "projection_mode": projection_mode,
                "items_count": len(view.items),
            },
        )
        return view

    async def get_wishlist_by_invite_token(self, invite_token: str) -> Wishlist | None:
        """Find non-deleted wishlist by invite token."""
        wl = await self.repo.get_by_invite_token(invite_token)
        if wl is None or wl.status == WishlistStatus.DELETED:
            return None
        return wl

    async def add_member(
        self,
        wishlist_id: int,
        actor: AuthenticatedUser,
        user_id: int,
        role: WishlistRole = WishlistRole.MEMBER,
    ) -> WishlistMember:
        """Add or update a collaborator in the wishlist."""
        wl = await self.get_wishlist_by_id(wishlist_id)
        ctx = WishlistAccessPolicy.resolve_context(actor, wl)
        if not WishlistAccessPolicy.can_manage_members(ctx, wl):
            raise PermissionDeniedError("Actor cannot manage members")
        if role == WishlistRole.ADMIN and not WishlistAccessPolicy.can_change_member_role(ctx, wl):
            raise PermissionDeniedError("Only owner can assign admin role")

        existing = next((m for m in wl.members if m.user_id == user_id), None)
        if existing is not None:
            if existing.role != role:
                await self.record_shared_event("membership_changed", wl, None, actor.telegram_id)
                existing.role = role
                await self.repo.update_member_role(wl.id, user_id, role)
            return existing

        member = WishlistMember(
            id=0,
            wishlist_id=wl.id,
            user_id=user_id,
            role=role,
            wishlist=wl,
        )
        member = await self.repo.upsert_member(member)
        wl.members.append(member)
        await self.record_shared_event("membership_changed", wl, None, actor.telegram_id)
        if not wl.is_collaborative:
            wl.is_collaborative = True
            wl.updated_at = datetime.now(UTC)
            await self.repo.upsert_wishlist(wl)
        return member

    async def remove_member(
        self,
        wishlist_id: int,
        actor: AuthenticatedUser,
        user_id: int,
    ) -> None:
        """Remove a collaborator from the wishlist."""
        wl = await self.get_wishlist_by_id(wishlist_id)
        self._ensure_wishlist_active(wl)
        ctx = WishlistAccessPolicy.resolve_context(actor, wl)
        if not WishlistAccessPolicy.can_manage_members(ctx, wl) and actor.telegram_id != user_id:
            raise PermissionDeniedError("Actor cannot remove this member")

        if any(m.user_id == user_id for m in wl.members):
            await self.record_shared_event("membership_changed", wl, None, actor.telegram_id)
            await self.repo.delete_member(wl.id, user_id)
        wl.members = [m for m in wl.members if m.user_id != user_id]
        new_collab = len(wl.members) > 0
        if wl.is_collaborative != new_collab:
            wl.is_collaborative = new_collab
            wl.updated_at = datetime.now(UTC)
            await self.repo.upsert_wishlist(wl)

    async def get_members(
        self,
        wishlist_id: int,
        actor: AuthenticatedUser,
    ) -> list[WishlistMember]:
        """Retrieve collaborators belonging to the wishlist."""
        wl = await self.get_wishlist_by_id(wishlist_id)
        ctx = WishlistAccessPolicy.resolve_context(actor, wl)
        if not (ctx.is_owner or ctx.is_admin or ctx.is_member):
            raise PermissionDeniedError("Actor cannot view members")
        return list(wl.members)

    async def archive_wishlist(self, wishlist_id: int, actor: AuthenticatedUser) -> Wishlist:
        """Archive an active wishlist."""
        wl = await self.get_wishlist_by_id(wishlist_id)
        self._ensure_wishlist_active(wl)
        ctx = WishlistAccessPolicy.resolve_context(actor, wl)
        if not WishlistAccessPolicy.can_archive(ctx, wl):
            raise PermissionDeniedError("Actor cannot archive wishlist")

        old_status = wl.status.value
        wl.status = WishlistStatus.ARCHIVED
        wl.updated_at = datetime.now(UTC)
        await self.repo.upsert_wishlist(wl)
        await self.record_shared_event("list_archived", wl, None, actor.telegram_id)
        logger.info(
            "Wishlist %s transitioned from %s to %s by actor %s",
            wishlist_id,
            old_status,
            WishlistStatus.ARCHIVED.value,
            actor.telegram_id,
            extra={
                "event": "wishlist_status_changed",
                "wishlist_id": wishlist_id,
                "actor_id": actor.telegram_id,
                "from_status": old_status,
                "to_status": WishlistStatus.ARCHIVED.value,
            },
        )
        return wl

    async def unarchive_wishlist(self, wishlist_id: int, actor: AuthenticatedUser) -> Wishlist:
        """Unarchive a wishlist back to active state."""
        wl = await self.get_wishlist_by_id(wishlist_id)
        ctx = WishlistAccessPolicy.resolve_context(actor, wl)
        if not WishlistAccessPolicy.can_archive(ctx, wl):
            raise PermissionDeniedError("Actor cannot unarchive wishlist")

        old_status = wl.status
        wl.status = WishlistStatus.ACTIVE
        wl.updated_at = datetime.now(UTC)
        await self.repo.upsert_wishlist(wl)
        if old_status != WishlistStatus.ACTIVE:
            await self.record_shared_event("list_restored", wl, None, actor.telegram_id)
        logger.info(
            "Wishlist %s transitioned from %s to %s by actor %s",
            wishlist_id,
            old_status.value,
            WishlistStatus.ACTIVE.value,
            actor.telegram_id,
            extra={
                "event": "wishlist_status_changed",
                "wishlist_id": wishlist_id,
                "actor_id": actor.telegram_id,
                "from_status": old_status.value,
                "to_status": WishlistStatus.ACTIVE.value,
            },
        )
        return wl

    async def delete_wishlist(self, wishlist_id: int, actor: AuthenticatedUser) -> None:
        """Soft delete a wishlist and cancel all active/purchased reservations."""
        wl = await self.get_wishlist_by_id(wishlist_id)
        self._ensure_wishlist_active(wl)
        ctx = WishlistAccessPolicy.resolve_context(actor, wl)
        if not WishlistAccessPolicy.can_delete(ctx, wl):
            raise PermissionDeniedError("Actor cannot delete wishlist")

        old_status = wl.status.value
        now = datetime.now(UTC)
        wl.status = WishlistStatus.DELETED
        wl.updated_at = now
        await self.repo.upsert_wishlist(wl)
        await self.repo.cancel_wishlist_reservations(wishlist_id, now)
        for item in wl.items:
            for res in item.reservations:
                if res.status in (ReservationStatus.ACTIVE, ReservationStatus.PURCHASED):
                    res.status = ReservationStatus.CANCELLED
                    res.updated_at = now
        logger.info(
            "Wishlist %s transitioned from %s to %s by actor %s",
            wishlist_id,
            old_status,
            WishlistStatus.DELETED.value,
            actor.telegram_id,
            extra={
                "event": "wishlist_status_changed",
                "wishlist_id": wishlist_id,
                "actor_id": actor.telegram_id,
                "from_status": old_status,
                "to_status": WishlistStatus.DELETED.value,
            },
        )

    async def list_deleted_wishlists(
        self,
        actor: AuthenticatedUser,
        retention_days: int = 30,
        now: datetime | None = None,
    ) -> list[tuple[Wishlist, datetime, int]]:
        """List owner's soft-deleted wishlists that are still within the retention window."""
        effective_now = now if now is not None else datetime.now(UTC)
        threshold = effective_now - timedelta(days=retention_days)
        results: list[tuple[Wishlist, datetime, int]] = []
        for wl in await self.repo.list_deleted_by_owner(actor.telegram_id):
            ctx = WishlistAccessPolicy.resolve_context(actor, wl)
            if not WishlistAccessPolicy.can_restore_deleted(ctx, wl):
                continue
            deleted_at = (
                wl.updated_at
                if wl.updated_at.tzinfo is not None
                else wl.updated_at.replace(tzinfo=UTC)
            )
            if deleted_at <= threshold:
                continue
            expires_at = deleted_at + timedelta(days=retention_days)
            remaining_seconds = (expires_at - effective_now).total_seconds()
            days_remaining = max(1, math.ceil(remaining_seconds / 86400))
            results.append((wl, expires_at, days_remaining))
        results.sort(key=lambda entry: entry[0].updated_at, reverse=True)
        logger.info(
            "Listed %s deleted wishlists for actor %s",
            len(results),
            actor.telegram_id,
            extra={
                "event": "wishlist_deleted_listed",
                "actor_id": actor.telegram_id,
                "count": len(results),
                "retention_days": retention_days,
            },
        )
        return results

    async def restore_deleted_wishlist(
        self,
        wishlist_id: int,
        actor: AuthenticatedUser,
        retention_days: int = 30,
        now: datetime | None = None,
    ) -> Wishlist:
        """Restore owner's soft-deleted wishlist within the retention window with token rotation."""
        wl = await self.get_wishlist_by_id(wishlist_id, allow_deleted=True)
        ctx = WishlistAccessPolicy.resolve_context(actor, wl)
        if not WishlistAccessPolicy.can_restore_deleted(ctx, wl):
            raise PermissionDeniedError("Actor cannot restore deleted wishlist")

        if wl.status == WishlistStatus.ACTIVE:
            return wl
        if wl.status != WishlistStatus.DELETED:
            raise WishlistArchivedError("Wishlist is archived and cannot be restored as deleted")

        effective_now = now if now is not None else datetime.now(UTC)
        deleted_at = (
            wl.updated_at if wl.updated_at.tzinfo is not None else wl.updated_at.replace(tzinfo=UTC)
        )
        threshold = effective_now - timedelta(days=retention_days)
        if deleted_at <= threshold:
            logger.warning(
                "Restore rejected for deleted wishlist %s: retention window (%s days) expired",
                wishlist_id,
                retention_days,
                extra={
                    "event": "wishlist_restore_retention_expired",
                    "wishlist_id": wishlist_id,
                    "actor_id": actor.telegram_id,
                    "retention_days": retention_days,
                },
            )
            raise WishlistRetentionExpiredError("Wishlist retention window has expired")

        for attempt in range(_TOKEN_ATTEMPTS):
            new_public_token = secrets.token_urlsafe(16)
            new_invite_token = secrets.token_urlsafe(24)
            if new_public_token == new_invite_token:
                continue
            try:
                await self.repo.rotate_public_token(wl.id, new_public_token, effective_now)
                await self.repo.rotate_invite_token(
                    wl.id, new_invite_token, effective_now + DEFAULT_INVITE_TTL, effective_now
                )
                wl.public_token = new_public_token
                wl.invite_token = new_invite_token
                wl.invite_token_expires_at = effective_now + DEFAULT_INVITE_TTL
                wl.status = WishlistStatus.ACTIVE
                wl.updated_at = effective_now
                await self.repo.upsert_wishlist(wl)
                break
            except TokenCollision:
                if attempt == _TOKEN_ATTEMPTS - 1:
                    raise
        logger.info(
            "Deleted wishlist %s restored to %s by actor %s",
            wishlist_id,
            WishlistStatus.ACTIVE.value,
            actor.telegram_id,
            extra={
                "event": "wishlist_restored_from_deleted",
                "wishlist_id": wishlist_id,
                "actor_id": actor.telegram_id,
                "from_status": WishlistStatus.DELETED.value,
                "to_status": WishlistStatus.ACTIVE.value,
                "retention_days": retention_days,
            },
        )
        return wl

    async def add_wish_item(
        self,
        wishlist_id: int,
        actor: AuthenticatedUser,
        title: str,
        description: str | None = None,
        link: str | None = None,
        price: int | float | None = None,
        currency: str = DEFAULT_CURRENCY,
        quantity: int = 1,
        recipient_user_id: int | None = None,
        recipient_name: str | None = None,
        image_url: str | None = None,
        store_name: str | None = None,
        store_icon_url: str | None = None,
        priority: ItemPriority = ItemPriority.MEDIUM,
        category: str | None = None,
    ) -> WishItem:
        """Add a new wish item to the wishlist."""
        wl = await self.get_wishlist_by_id(wishlist_id)
        self._ensure_wishlist_active(wl)
        ctx = WishlistAccessPolicy.resolve_context(actor, wl)
        if not WishlistAccessPolicy.can_add_or_edit_item(ctx, wl):
            logger.warning(
                "Actor %s denied permission to add item to wishlist %s",
                actor.telegram_id,
                wishlist_id,
                extra={
                    "event": "item_access_denied",
                    "actor_id": actor.telegram_id,
                    "wishlist_id": wishlist_id,
                    "action": "add_item",
                    "role": ctx.role.value if ctx.role else None,
                },
            )
            raise PermissionDeniedError("Actor cannot add items to this wishlist")

        if recipient_user_id is not None:
            member_uids = {wl.owner_id} | {m.user_id for m in wl.members}
            if recipient_user_id not in member_uids:
                raise ValueError(
                    f"Recipient user {recipient_user_id} is not a member of wishlist {wishlist_id}"
                )

        next_order = max([it.display_order for it in wl.items], default=-1) + 1
        item = WishItem(
            id=0,
            wishlist_id=wl.id,
            title=title,
            description=description,
            link=link,
            price=price,
            currency=currency,
            quantity=quantity,
            received_quantity=0,
            image_url=image_url,
            store_name=store_name,
            store_icon_url=store_icon_url,
            priority=priority,
            category=category,
            display_order=next_order,
            is_archived=False,
            recipient_user_id=recipient_user_id,
            recipient_name=recipient_name,
            wishlist=wl,
        )
        item = await self.repo.create_item(item)
        wl.items.append(item)
        await self.record_shared_event("item_created", wl, item, actor.telegram_id)
        has_recip = recipient_user_id is not None or bool(recipient_name and recipient_name.strip())
        logger.info(
            "Item %s added to wishlist %s by actor %s",
            item.id,
            wl.id,
            actor.telegram_id,
            extra={
                "event": "item_created",
                "item_id": item.id,
                "wishlist_id": wl.id,
                "actor_id": actor.telegram_id,
                "recipient_user_id": recipient_user_id,
                "quantity": item.quantity,
                "display_order": item.display_order,
                "has_recipient": has_recip,
            },
        )
        return item

    async def get_wish_item(
        self,
        wishlist_id: int,
        item_id: int,
        actor: AuthenticatedUser | None = None,
    ) -> WishItemRecipientViewDTO | WishItemGifterViewDTO:
        """Retrieve a single wish item projected for the caller."""
        wl = await self.get_wishlist_by_id(wishlist_id)
        item = next((it for it in wl.items if it.id == item_id), None)
        if item is None:
            raise ItemNotFoundError(f"Item {item_id} not found")
        return project_wish_item(item, actor)

    async def list_wish_items(
        self,
        wishlist_id: int,
        actor: AuthenticatedUser | None = None,
        include_archived: bool = False,
    ) -> list[WishItemRecipientViewDTO | WishItemGifterViewDTO]:
        """List wishlist items sorted by display_order adhering to Surprise Invariant."""
        wl = await self.get_wishlist_by_id(wishlist_id)
        ctx = WishlistAccessPolicy.resolve_context(actor, wl)
        items = [it for it in wl.items if (include_archived and ctx.is_member) or it.is_active]
        items.sort(key=lambda it: (it.display_order, it.created_at, it.id))
        return [project_wish_item(it, actor) for it in items]

    async def list_gifted_items(
        self,
        wishlist_id: int,
        actor: AuthenticatedUser | None,
    ) -> list[GiftedItemDTO]:
        """List received wishes with dated receipts for the list authors only."""
        wl = await self.get_wishlist_by_id(wishlist_id)
        ctx = WishlistAccessPolicy.resolve_context(actor, wl)
        if not WishlistAccessPolicy.can_view_gifted(ctx, wl):
            raise PermissionDeniedError("Only list authors can read the gifted wishes")
        receipts_by_item = await self.repo.list_receipts_for_wishlist(wishlist_id)
        gifted = [item for item in wl.items if item.is_gifted]
        for item in gifted:
            item.receipts = receipts_by_item.get(item.id, [])
        gifted.sort(
            key=lambda it: (
                -max((r.received_at for r in it.receipts), default=it.updated_at).timestamp(),
                it.id,
            )
        )
        return [
            GiftedItemDTO(
                id=item.id,
                title=item.title,
                description=item.description,
                link=item.link,
                image_url=item.image_url,
                price=item.price,
                currency=item.currency,
                store_name=item.store_name,
                store_icon_url=item.store_icon_url,
                recipient_user_id=item.recipient_user_id,
                recipient_name=item.recipient_name,
                quantity=item.quantity,
                received_quantity=item.received_quantity,
                remaining_quantity=item.remaining_quantity,
                is_archived=item.is_archived,
                receipts=[
                    ReceiptEntryDTO(
                        id=r.id,
                        received_at=r.received_at,
                        quantity=r.quantity,
                        is_approximate=r.is_approximate,
                    )
                    for r in sorted(item.receipts, key=lambda r: (r.received_at, r.id))
                ],
            )
            for item in gifted
        ]

    async def reorder_wish_items(
        self,
        wishlist_id: int,
        actor: AuthenticatedUser,
        item_ids: list[int],
    ) -> list[WishItemRecipientViewDTO | WishItemGifterViewDTO]:
        """Atomically reorder active items in a wishlist enforcing 1:1 permutation integrity."""
        wl = await self.get_wishlist_by_id(wishlist_id)
        self._ensure_wishlist_active(wl)
        ctx = WishlistAccessPolicy.resolve_context(actor, wl)
        if not WishlistAccessPolicy.can_add_or_edit_item(ctx, wl):
            logger.warning(
                "Actor %s denied permission to reorder items in wishlist %s",
                actor.telegram_id,
                wl.id,
                extra={
                    "event": "item_access_denied",
                    "actor_id": actor.telegram_id,
                    "wishlist_id": wl.id,
                    "action": "reorder_items",
                    "role": ctx.role.value if ctx.role else None,
                },
            )
            raise PermissionDeniedError("Actor cannot reorder items in this wishlist")

        active_items = [it for it in wl.items if it.is_active]
        if len(item_ids) != len(set(item_ids)):
            reason = "Duplicate item IDs in reorder request"
            logger.warning(
                "Invalid reorder request for wishlist %s by actor %s: %s",
                wl.id,
                actor.telegram_id,
                reason,
                extra={
                    "event": "item_reorder_invalid",
                    "wishlist_id": wl.id,
                    "actor_id": actor.telegram_id,
                    "reason": reason,
                },
            )
            raise ValueError(reason)
        if set(item_ids) != {it.id for it in active_items}:
            reason = "Reorder list must contain exactly all active item IDs for this wishlist"
            logger.warning(
                "Invalid reorder request for wishlist %s by actor %s: %s",
                wl.id,
                actor.telegram_id,
                reason,
                extra={
                    "event": "item_reorder_invalid",
                    "wishlist_id": wl.id,
                    "actor_id": actor.telegram_id,
                    "reason": reason,
                },
            )
            raise ValueError(reason)

        now = datetime.now(UTC)
        item_map = {it.id: it for it in active_items}
        order_map: dict[int, int] = {}
        for order, it_id in enumerate(item_ids):
            item = item_map[it_id]
            item.display_order = order
            item.updated_at = now
            order_map[it_id] = order

        await self.repo.reorder_items(wl.id, order_map, now)
        logger.info(
            "Items in wishlist %s reordered by actor %s (count=%s)",
            wl.id,
            actor.telegram_id,
            len(item_ids),
            extra={
                "event": "items_reordered",
                "wishlist_id": wl.id,
                "actor_id": actor.telegram_id,
                "item_count": len(item_ids),
                "count": len(item_ids),
                "item_ids": item_ids,
            },
        )
        return [project_wish_item(item_map[it_id], actor) for it_id in item_ids]

    async def archive_wish_item(
        self,
        wishlist_id: int,
        item_id: int,
        actor: AuthenticatedUser,
        warn_on_delete_reserved: bool | None = None,
    ) -> WishItemRecipientViewDTO | WishItemGifterViewDTO:
        """Safely archive a wish item, preserving reservations and blocking new ones."""
        wl = await self.get_wishlist_by_id(wishlist_id)
        self._ensure_wishlist_active(wl)
        ctx = WishlistAccessPolicy.resolve_context(actor, wl)
        if not WishlistAccessPolicy.can_add_or_edit_item(ctx, wl):
            raise PermissionDeniedError("Actor cannot archive items in this wishlist")

        item = next((it for it in wl.items if it.id == item_id), None)
        if item is None:
            raise ItemNotFoundError(f"Item {item_id} not found in wishlist {wishlist_id}")
        if item.is_fully_received:
            WishlistService._log_archive_refused(wl.id, item.id, actor)
            raise NothingRemainingError()

        now = datetime.now(UTC)
        if warn_on_delete_reserved is not None:
            wl.warn_on_delete_reserved = warn_on_delete_reserved
            wl.updated_at = now
            await self.repo.upsert_wishlist(wl)

        was_archived = item.is_archived
        item.is_archived = True
        item.updated_at = now
        await self.repo.upsert_item(item)
        if not was_archived:
            await self.record_shared_event("item_archived", wl, item, actor.telegram_id)
        logger.info(
            "Item %s archived in wishlist %s by actor %s",
            item.id,
            wl.id,
            actor.telegram_id,
            extra={
                "event": "item_archived",
                "item_id": item.id,
                "wishlist_id": wl.id,
                "actor_id": actor.telegram_id,
            },
        )
        return project_wish_item(item, actor)

    async def restore_wish_item(
        self,
        wishlist_id: int,
        item_id: int,
        actor: AuthenticatedUser,
    ) -> WishItemRecipientViewDTO | WishItemGifterViewDTO:
        """Restore an archived wish item to the end of the active display order."""
        wl = await self.get_wishlist_by_id(wishlist_id)
        self._ensure_wishlist_active(wl)
        ctx = WishlistAccessPolicy.resolve_context(actor, wl)
        if not WishlistAccessPolicy.can_add_or_edit_item(ctx, wl):
            raise PermissionDeniedError("Actor cannot restore items in this wishlist")

        item = next((it for it in wl.items if it.id == item_id), None)
        if item is None:
            raise ItemNotFoundError(f"Item {item_id} not found in wishlist {wishlist_id}")
        if item.remaining_quantity == 0:
            WishlistService._log_archive_refused(wl.id, item.id, actor)
            raise NothingRemainingError()

        was_archived = item.is_archived
        item.is_archived = False
        active_orders = [it.display_order for it in wl.items if it.is_active and it.id != item.id]
        item.display_order = max(active_orders, default=-1) + 1
        item.updated_at = datetime.now(UTC)
        await self.repo.upsert_item(item)
        if was_archived:
            await self.record_shared_event("item_restored", wl, item, actor.telegram_id)
        logger.info(
            "Item %s restored in wishlist %s by actor %s (new_display_order=%s)",
            item.id,
            wl.id,
            actor.telegram_id,
            item.display_order,
            extra={
                "event": "item_restored",
                "item_id": item.id,
                "wishlist_id": wl.id,
                "actor_id": actor.telegram_id,
                "display_order": item.display_order,
                "new_display_order": item.display_order,
            },
        )
        return project_wish_item(item, actor)

    async def join_by_invite(self, invite_token: str, user: AuthenticatedUser) -> WishlistMember:
        """Join a wishlist as Member using an invite token."""
        wl = await self.repo.get_by_invite_token(invite_token)
        if wl is None:
            logger.warning(
                "Invite join failed: token not found",
                extra={
                    "event": "wishlist_invite_join_failed",
                    "user_id": user.telegram_id,
                    "reason": "not_found",
                },
            )
            raise InvalidInviteTokenError("Invalid invite token")
        self._ensure_wishlist_active(wl)
        if wl.invite_token_expires_at is not None and wl.invite_token_expires_at < datetime.now(
            UTC
        ):
            logger.warning(
                "Invite join failed: token expired for wishlist %s",
                wl.id,
                extra={
                    "event": "wishlist_invite_join_failed",
                    "wishlist_id": wl.id,
                    "user_id": user.telegram_id,
                    "reason": "expired",
                },
            )
            raise InvalidInviteTokenError("Invite token has expired")

        existing = next((m for m in wl.members if m.user_id == user.telegram_id), None)
        if existing is not None:
            return existing

        member = WishlistMember(
            id=0,
            wishlist_id=wl.id,
            user_id=user.telegram_id,
            role=WishlistRole.MEMBER,
            wishlist=wl,
        )
        member = await self.repo.upsert_member(member)
        wl.members.append(member)
        if not wl.is_collaborative:
            wl.is_collaborative = True
            wl.updated_at = datetime.now(UTC)
            await self.repo.upsert_wishlist(wl)
        await self.record_shared_event("membership_changed", wl, None, user.telegram_id)
        logger.info(
            "User %s joined wishlist %s via invite",
            user.telegram_id,
            wl.id,
            extra={
                "event": "wishlist_member_joined",
                "wishlist_id": wl.id,
                "user_id": user.telegram_id,
            },
        )
        return member

    async def regenerate_public_token(self, wishlist_id: int, actor: AuthenticatedUser) -> str:
        """Revoke existing public token and generate a new one."""
        wl = await self.get_wishlist_by_id(wishlist_id)
        self._ensure_wishlist_active(wl)
        ctx = WishlistAccessPolicy.resolve_context(actor, wl)
        if not (ctx.is_owner or ctx.is_admin):
            logger.warning(
                "Public token rotation denied for wishlist %s by user %s",
                wl.id,
                actor.telegram_id,
                extra={
                    "event": "public_token_rotate_denied",
                    "wishlist_id": wl.id,
                    "actor_id": actor.telegram_id,
                },
            )
            raise PermissionDeniedError("Actor cannot regenerate public token")

        now = datetime.now(UTC)
        for attempt in range(_TOKEN_ATTEMPTS):
            new_token = secrets.token_urlsafe(16)
            if new_token == wl.public_token:
                continue
            try:
                await self.repo.rotate_public_token(wl.id, new_token, now)
                wl.public_token = new_token
                wl.updated_at = now
                logger.info(
                    "Public token rotated for wishlist %s by user %s",
                    wl.id,
                    actor.telegram_id,
                    extra={
                        "event": "public_token_rotated",
                        "wishlist_id": wl.id,
                        "actor_id": actor.telegram_id,
                    },
                )
                return new_token
            except TokenCollision:
                if attempt == _TOKEN_ATTEMPTS - 1:
                    raise
        raise RuntimeError("Unable to generate a new public token")

    async def regenerate_invite_token(
        self,
        wishlist_id: int,
        actor: AuthenticatedUser,
        expires_in: timedelta | None = None,
    ) -> str:
        """Revoke existing invite token and generate a new one."""
        wl = await self.get_wishlist_by_id(wishlist_id)
        self._ensure_wishlist_active(wl)
        ctx = WishlistAccessPolicy.resolve_context(actor, wl)
        if not (ctx.is_owner or ctx.is_admin):
            logger.warning(
                "Invite token rotation denied for wishlist %s by user %s",
                wl.id,
                actor.telegram_id,
                extra={
                    "event": "invite_token_rotate_denied",
                    "wishlist_id": wl.id,
                    "actor_id": actor.telegram_id,
                },
            )
            raise PermissionDeniedError("Actor cannot regenerate invite token")

        now = datetime.now(UTC)
        ttl = expires_in if expires_in is not None else DEFAULT_INVITE_TTL
        expires_at = now + ttl
        for attempt in range(_TOKEN_ATTEMPTS):
            new_token = secrets.token_urlsafe(24)
            if new_token in {wl.invite_token, wl.public_token}:
                continue
            try:
                await self.repo.rotate_invite_token(wl.id, new_token, expires_at, now)
                wl.invite_token = new_token
                wl.invite_token_expires_at = expires_at
                wl.updated_at = now
                logger.info(
                    "Invite token rotated for wishlist %s by user %s",
                    wl.id,
                    actor.telegram_id,
                    extra={
                        "event": "invite_token_rotated",
                        "wishlist_id": wl.id,
                        "actor_id": actor.telegram_id,
                    },
                )
                return new_token
            except TokenCollision:
                if attempt == _TOKEN_ATTEMPTS - 1:
                    raise
        raise RuntimeError("Unable to generate a new invitation token")

    async def add_favorite(self, user: AuthenticatedUser, wishlist_id: int) -> WishlistFavorite:
        """Add a wishlist to user's favorites."""
        wl = await self.repo.get_wishlist_header(wishlist_id)
        if wl is None or wl.status == WishlistStatus.DELETED:
            if wl is not None and wl.status == WishlistStatus.DELETED:
                logger.warning(
                    "Favorite attempt on deleted wishlist %s by user %s denied",
                    wishlist_id,
                    user.telegram_id,
                    extra={
                        "event": "favorite_deleted_wishlist_denied",
                        "wishlist_id": wishlist_id,
                        "user_id": user.telegram_id,
                    },
                )
            raise WishlistNotFoundError(f"Wishlist {wishlist_id} not found")
        if wl.owner_id == user.telegram_id:
            logger.warning(
                "Self-favoriting attempt by user %s on wishlist %s denied",
                user.telegram_id,
                wishlist_id,
                extra={
                    "event": "favorite_own_wishlist_denied",
                    "wishlist_id": wishlist_id,
                    "user_id": user.telegram_id,
                },
            )
            raise ValueError("Cannot favorite own wishlist")
        fav = WishlistFavorite(user_id=user.telegram_id, wishlist_id=wishlist_id)
        await self.repo.upsert_favorite(fav)
        return fav

    async def remove_favorite(self, user: AuthenticatedUser, wishlist_id: int) -> None:
        """Remove a wishlist from user's favorites."""
        await self.repo.delete_favorite(user.telegram_id, wishlist_id)

    async def list_favorites(self, user: AuthenticatedUser) -> list[Wishlist]:
        """List user's favorited wishlists in reverse-chronological order."""
        return await self.repo.list_favorite_wishlists(user.telegram_id)

    async def record_view(self, user: AuthenticatedUser, wishlist_id: int) -> ViewHistoryEntry:
        """Record or update a wishlist view event for user."""
        wl = await self.repo.get_wishlist_header(wishlist_id)
        if wl is None or wl.status == WishlistStatus.DELETED:
            if wl is not None and wl.status == WishlistStatus.DELETED:
                logger.warning(
                    "View history record denied: wishlist %s is deleted",
                    wishlist_id,
                    extra={
                        "event": "favorite_deleted_wishlist_denied",
                        "wishlist_id": wishlist_id,
                        "user_id": user.telegram_id,
                    },
                )
            raise WishlistNotFoundError(f"Wishlist {wishlist_id} not found")
        entry = ViewHistoryEntry(
            id=0,
            user_id=user.telegram_id,
            wishlist_id=wishlist_id,
            viewed_at=datetime.now(UTC),
        )
        await self.repo.record_view(entry)
        return entry

    async def get_history(
        self, user: AuthenticatedUser, limit: int = 20
    ) -> list[tuple[Wishlist, datetime]]:
        """Retrieve up to limit recent wishlists viewed by user, reverse-chronologically."""
        entries = await self.repo.list_view_history(user.telegram_id, limit=limit)
        results: list[tuple[Wishlist, datetime]] = []
        for entry in entries:
            wl = await self.repo.get_wishlist(entry.wishlist_id)
            if wl is not None and wl.status != WishlistStatus.DELETED:
                results.append((wl, entry.viewed_at))
        return results

    async def clear_history(self, user: AuthenticatedUser) -> None:
        """Clear all viewing history entries for user."""
        removed_count = await self.repo.clear_view_history(user.telegram_id)
        logger.info(
            "Viewing history cleared for user %s",
            user.telegram_id,
            extra={
                "event": "view_history_cleared",
                "user_id": user.telegram_id,
                "removed_count": removed_count,
            },
        )
