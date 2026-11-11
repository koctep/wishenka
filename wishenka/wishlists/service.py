"""Wishlist service providing lifecycle management, access enforcement, and projections."""

from __future__ import annotations

import logging
import secrets
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from functools import wraps
from inspect import iscoroutinefunction
from typing import TYPE_CHECKING, Any

from wishenka.auth.models import AuthenticatedUser
from wishenka.items.models import ItemPriority
from wishenka.wishlists.concurrency import ItemConcurrencyCoordinator
from wishenka.wishlists.exceptions import (
    CannotReduceQuantityBelowReservedError,
    InsufficientQuantityError,
    InvalidInviteTokenError,
    ItemNotFoundError,
    PermissionDeniedError,
    ReservationError,
    ReservationNotFoundError,
    SelfReservationError,
    WishlistArchivedError,
    WishlistDeletedError,
    WishlistNotFoundError,
)
from wishenka.wishlists.models import (
    Reservation,
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
from wishenka.wishlists.schemas import (
    MyReservationItemDTO,
    UserReservationsSummaryDTO,
    WishItemGifterViewDTO,
    WishItemRecipientViewDTO,
    WishlistDetailViewDTO,
)

logger = logging.getLogger("wishenka.wishlists")

if TYPE_CHECKING:
    from wishenka.wishlists.store import WishlistStore


def _transactional[T](method: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
    """Run a public domain operation in its configured persistent unit of work."""

    @wraps(method)
    async def invoke(self: WishlistService, *args: Any, **kwargs: Any) -> T:
        if self._store is None:
            return await method(self, *args, **kwargs)
        return await self._store.execute(lambda service: method(service, *args, **kwargs))

    return invoke


class WishlistService:
    """Domain service managing wishlists, members, items, and role-aware projections."""

    def __init__(
        self,
        store: WishlistStore | None = None,
        default_invite_ttl: timedelta | None = None,
    ) -> None:
        self._store = store
        self._default_invite_ttl = default_invite_ttl or timedelta(days=7)
        self._wishlists: dict[int, Wishlist] = {}
        self._items: dict[int, WishItem] = {}
        self._reservations: dict[int, Reservation] = {}
        self._concurrency_coordinator = ItemConcurrencyCoordinator()
        self._next_wishlist_id: int = 0
        self._next_member_id: int = 0
        self._next_item_id: int = 0
        self._next_reservation_id: int = 0
        self._favorites: dict[tuple[int, int], WishlistFavorite] = {}
        self._view_history: list[ViewHistoryEntry] = []
        self._next_view_history_id: int = 0

    @property
    def concurrency_coordinator(self) -> ItemConcurrencyCoordinator:
        """Expose item concurrency coordinator."""
        return self._concurrency_coordinator

    @staticmethod
    def _ensure_reservation_writable(reservation: Reservation) -> None:
        item = reservation.wish_item
        wishlist = item.wishlist if item is not None else None
        if wishlist is not None and wishlist.status == WishlistStatus.ARCHIVED:
            raise WishlistArchivedError("Cannot modify a reservation on an archived wishlist")
        if wishlist is not None and wishlist.status == WishlistStatus.DELETED:
            raise WishlistDeletedError("Cannot modify a reservation on a deleted wishlist")

    @staticmethod
    def _ensure_wishlist_active(wishlist: Wishlist) -> None:
        if wishlist.status == WishlistStatus.ARCHIVED:
            raise WishlistArchivedError("Cannot modify an archived wishlist")
        if wishlist.status == WishlistStatus.DELETED:
            raise WishlistDeletedError("Cannot modify a deleted wishlist")

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
        """Create a new personal wishlist with cryptographically secure tokens."""
        effective_owner_id = owner.telegram_id if owner is not None else (owner_id or 0)
        effective_owner_name = owner.first_name if owner is not None else ""
        self._next_wishlist_id += 1
        public_token = secrets.token_urlsafe(16)
        invite_token = secrets.token_urlsafe(24)
        ttl = (
            invite_token_expires_in
            if invite_token_expires_in is not None
            else self._default_invite_ttl
        )
        invite_token_expires_at = datetime.now(UTC) + ttl

        wishlist = Wishlist(
            id=self._next_wishlist_id,
            owner_id=effective_owner_id,
            owner_name=effective_owner_name,
            title=title,
            description=description,
            event_title=event_title,
            event_date=event_date,
            is_collaborative=False,
            status=WishlistStatus.ACTIVE,
            public_token=public_token,
            invite_token=invite_token,
            invite_token_expires_at=invite_token_expires_at,
            members=[],
            items=[],
        )
        self._wishlists[wishlist.id] = wishlist

        time_type = (
            WishlistTimeType.EVENT.value
            if event_date is not None
            else WishlistTimeType.ONGOING.value
        )
        format_type = (
            WishlistFormat.COLLABORATIVE.value
            if wishlist.is_collaborative
            else WishlistFormat.PERSONAL.value
        )
        logger.info(
            "Wishlist %s created by user %s",
            wishlist.id,
            effective_owner_id,
            extra={
                "event": "wishlist_created",
                "wishlist_id": wishlist.id,
                "owner_id": effective_owner_id,
                "format": format_type,
                "time_type": time_type,
                "event_date": event_date.isoformat() if event_date is not None else None,
            },
        )
        return wishlist

    async def get_wishlist_by_id(self, wishlist_id: int) -> Wishlist:
        """Retrieve a wishlist by its primary ID."""
        if wishlist_id not in self._wishlists:
            logger.warning(
                "Wishlist lookup failed: id %s not found",
                wishlist_id,
                extra={
                    "event": "wishlist_not_found",
                    "wishlist_id": wishlist_id,
                },
            )
            raise WishlistNotFoundError(f"Wishlist {wishlist_id} not found")
        wl = self._wishlists[wishlist_id]
        if wl.status == WishlistStatus.DELETED:
            logger.warning(
                "Wishlist lookup failed: id %s is deleted",
                wishlist_id,
                extra={
                    "event": "deleted_wishlist_access_attempt",
                    "wishlist_id": wishlist_id,
                },
            )
            raise WishlistDeletedError(f"Wishlist {wishlist_id} has been deleted")
        return wl

    async def get_wishlist_by_public_token(
        self,
        public_token: str,
        current_user: AuthenticatedUser | None = None,
    ) -> WishlistDetailViewDTO:
        """Retrieve wishlist projection via public token for gift viewing."""
        wl = next((w for w in self._wishlists.values() if w.public_token == public_token), None)
        if wl is None:
            logger.warning(
                "Public token lookup failed: token not found",
                extra={
                    "event": "public_token_not_found",
                },
            )
            raise WishlistNotFoundError("Wishlist not found")
        if wl.status == WishlistStatus.DELETED:
            logger.warning(
                "Public token lookup failed: wishlist %s is deleted",
                wl.id,
                extra={
                    "event": "deleted_wishlist_access_attempt",
                    "wishlist_id": wl.id,
                },
            )
            raise WishlistDeletedError(f"Wishlist {wl.id} has been deleted")
        return await self.get_wishlist_view(wl.id, current_user)

    async def get_wishlist_view(
        self,
        wishlist_id: int,
        current_user: AuthenticatedUser | None = None,
    ) -> WishlistDetailViewDTO:
        """Project wishlist and items applying Surprise Invariant rules."""
        wl = await self.get_wishlist_by_id(wishlist_id)

        item_views: list[WishItemRecipientViewDTO | WishItemGifterViewDTO] = []
        for item in wl.items:
            is_recip = WishlistAccessPolicy.is_recipient(current_user, item)
            if is_recip:
                item_views.append(
                    WishItemRecipientViewDTO(
                        id=item.id,
                        title=item.title,
                        description=item.description,
                        link=item.link,
                        image_url=item.image_url,
                        price=item.price,
                        currency=item.currency,
                        store_name=item.store_name,
                        store_icon_url=item.store_icon_url,
                        quantity=item.quantity,
                        received_quantity=item.received_quantity,
                        priority=item.priority,
                        category=item.category,
                        is_archived=item.is_archived,
                        recipient_name=item.recipient_name,
                        is_recipient=True,
                    )
                )
            else:
                active_or_purchased = [
                    r
                    for r in item.reservations
                    if r.status in (ReservationStatus.ACTIVE, ReservationStatus.PURCHASED)
                ]
                reserved_qty = sum(r.quantity for r in active_or_purchased)
                available_qty = max(0, item.quantity - item.received_quantity - reserved_qty)
                my_reserved_qty = 0
                my_reservation_status: ReservationStatus | None = None
                my_reservation_id: int | None = None
                if current_user is not None:
                    user_reservations = [
                        r for r in active_or_purchased if r.user_id == current_user.telegram_id
                    ]
                    my_reserved_qty = sum(r.quantity for r in user_reservations)
                    if user_reservations:
                        my_res = user_reservations[-1]
                        my_reservation_status = my_res.status
                        my_reservation_id = my_res.id
                item_views.append(
                    WishItemGifterViewDTO(
                        id=item.id,
                        title=item.title,
                        description=item.description,
                        link=item.link,
                        image_url=item.image_url,
                        price=item.price,
                        currency=item.currency,
                        store_name=item.store_name,
                        store_icon_url=item.store_icon_url,
                        quantity=item.quantity,
                        received_quantity=item.received_quantity,
                        available_quantity=available_qty,
                        is_fully_reserved=(available_qty == 0),
                        is_reserved_by_me=(my_reserved_qty > 0),
                        my_reserved_quantity=my_reserved_qty,
                        my_reservation_status=my_reservation_status,
                        my_reservation_id=my_reservation_id,
                        priority=item.priority,
                        category=item.category,
                        is_archived=item.is_archived,
                        recipient_name=item.recipient_name,
                        is_recipient=False,
                    )
                )

        ctx = WishlistAccessPolicy.resolve_context(current_user, wl)
        can_edit = WishlistAccessPolicy.can_edit_settings(ctx, wl)
        can_archive = WishlistAccessPolicy.can_archive(ctx, wl)
        can_delete = WishlistAccessPolicy.can_delete(ctx, wl)
        invite_token = wl.invite_token if (ctx.is_owner or ctx.is_admin) else None

        logger.debug(
            "Wishlist %s view projected for user %s (role=%s, items_count=%s)",
            wl.id,
            current_user.telegram_id if current_user else None,
            ctx.role,
            len(item_views),
            extra={
                "event": "wishlist_view_projected",
                "wishlist_id": wl.id,
                "user_id": current_user.telegram_id if current_user else None,
                "role": ctx.role,
            },
        )

        return WishlistDetailViewDTO(
            id=wl.id,
            title=wl.title,
            owner_name=wl.owner_name,
            description=wl.description,
            event_title=wl.event_title,
            event_date=wl.event_date,
            is_collaborative=wl.is_collaborative,
            status=wl.status,
            user_role=ctx.role,
            can_edit=can_edit,
            can_archive=can_archive,
            can_delete=can_delete,
            public_token=wl.public_token,
            invite_token=invite_token,
            items=item_views,
        )

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
            logger.warning(
                "Actor %s denied permission to manage members for wishlist %s",
                actor.telegram_id,
                wishlist_id,
                extra={
                    "event": "access_denied",
                    "actor_id": actor.telegram_id,
                    "wishlist_id": wishlist_id,
                    "action": "manage_members",
                },
            )
            raise PermissionDeniedError("Actor cannot manage members")
        if role == WishlistRole.ADMIN and not WishlistAccessPolicy.can_change_member_role(ctx, wl):
            logger.warning(
                "Actor %s denied permission to assign admin role for wishlist %s",
                actor.telegram_id,
                wishlist_id,
                extra={
                    "event": "access_denied",
                    "actor_id": actor.telegram_id,
                    "wishlist_id": wishlist_id,
                    "action": "assign_admin_role",
                },
            )
            raise PermissionDeniedError("Only owner can assign admin role")

        existing = next((m for m in wl.members if m.user_id == user_id), None)
        if existing is not None:
            existing.role = role
            logger.info(
                "Member %s role updated to %s in wishlist %s by actor %s",
                user_id,
                role.value,
                wishlist_id,
                actor.telegram_id,
                extra={
                    "event": "member_role_assigned",
                    "user_id": user_id,
                    "wishlist_id": wishlist_id,
                    "role": role.value,
                    "actor_id": actor.telegram_id,
                },
            )
            return existing

        self._next_member_id += 1
        member = WishlistMember(
            id=self._next_member_id,
            wishlist_id=wl.id,
            user_id=user_id,
            role=role,
            wishlist=wl,
        )
        wl.members.append(member)
        wl.is_collaborative = len(wl.members) > 0
        logger.info(
            "Member %s role assigned as %s in wishlist %s by actor %s",
            user_id,
            role.value,
            wishlist_id,
            actor.telegram_id,
            extra={
                "event": "member_role_assigned",
                "user_id": user_id,
                "wishlist_id": wishlist_id,
                "role": role.value,
                "actor_id": actor.telegram_id,
            },
        )
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
            logger.warning(
                "Actor %s denied permission to remove member %s from wishlist %s",
                actor.telegram_id,
                user_id,
                wishlist_id,
                extra={
                    "event": "access_denied",
                    "actor_id": actor.telegram_id,
                    "user_id": user_id,
                    "wishlist_id": wishlist_id,
                    "action": "remove_member",
                },
            )
            raise PermissionDeniedError("Actor cannot remove this member")

        wl.members = [m for m in wl.members if m.user_id != user_id]
        wl.is_collaborative = len(wl.members) > 0
        logger.info(
            "Member %s removed from wishlist %s by actor %s",
            user_id,
            wishlist_id,
            actor.telegram_id,
            extra={
                "event": "member_removed",
                "user_id": user_id,
                "wishlist_id": wishlist_id,
                "actor_id": actor.telegram_id,
            },
        )

    async def get_members(
        self,
        wishlist_id: int,
        actor: AuthenticatedUser,
    ) -> list[WishlistMember]:
        """Retrieve collaborators belonging to the wishlist."""
        wl = await self.get_wishlist_by_id(wishlist_id)
        ctx = WishlistAccessPolicy.resolve_context(actor, wl)
        if not (ctx.is_owner or ctx.is_admin or ctx.is_member):
            logger.warning(
                "Actor %s denied permission to view members of wishlist %s",
                actor.telegram_id,
                wishlist_id,
                extra={
                    "event": "access_denied",
                    "actor_id": actor.telegram_id,
                    "wishlist_id": wishlist_id,
                    "action": "get_members",
                },
            )
            raise PermissionDeniedError("Actor cannot view members")
        return list(wl.members)

    async def update_wishlist_settings(
        self,
        wishlist_id: int,
        actor: AuthenticatedUser,
        title: str | None = None,
        description: str | None = None,
        event_title: str | None = None,
        event_date: datetime | None = None,
    ) -> Wishlist:
        """Update metadata settings of an active wishlist."""
        wl = await self.get_wishlist_by_id(wishlist_id)
        ctx = WishlistAccessPolicy.resolve_context(actor, wl)
        if not WishlistAccessPolicy.can_edit_settings(ctx, wl):
            logger.warning(
                "Actor %s denied permission to edit settings for wishlist %s",
                actor.telegram_id,
                wishlist_id,
                extra={
                    "event": "access_denied",
                    "actor_id": actor.telegram_id,
                    "wishlist_id": wishlist_id,
                    "action": "edit_settings",
                },
            )
            raise PermissionDeniedError("Actor cannot edit wishlist settings")

        if title is not None:
            wl.title = title
        if description is not None:
            wl.description = description
        if event_title is not None:
            wl.event_title = event_title
        if event_date is not None:
            wl.event_date = event_date
        wl.updated_at = datetime.now(UTC)
        logger.info(
            "Wishlist %s settings updated by actor %s",
            wishlist_id,
            actor.telegram_id,
            extra={
                "event": "wishlist_settings_updated",
                "actor_id": actor.telegram_id,
                "wishlist_id": wishlist_id,
            },
        )
        return wl

    async def archive_wishlist(
        self,
        wishlist_id: int,
        actor: AuthenticatedUser,
    ) -> Wishlist:
        """Archive an active wishlist, locking items and reservations."""
        wl = await self.get_wishlist_by_id(wishlist_id)
        self._ensure_wishlist_active(wl)
        ctx = WishlistAccessPolicy.resolve_context(actor, wl)
        if not WishlistAccessPolicy.can_archive(ctx, wl):
            logger.warning(
                "Actor %s denied permission to archive wishlist %s",
                actor.telegram_id,
                wishlist_id,
                extra={
                    "event": "access_denied",
                    "actor_id": actor.telegram_id,
                    "wishlist_id": wishlist_id,
                    "action": "archive_wishlist",
                },
            )
            raise PermissionDeniedError("Actor cannot archive wishlist")

        old_status = wl.status.value
        wl.status = WishlistStatus.ARCHIVED
        wl.updated_at = datetime.now(UTC)
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

    async def unarchive_wishlist(
        self,
        wishlist_id: int,
        actor: AuthenticatedUser,
    ) -> Wishlist:
        """Unarchive a wishlist back to active state."""
        wl = await self.get_wishlist_by_id(wishlist_id)
        ctx = WishlistAccessPolicy.resolve_context(actor, wl)
        if not WishlistAccessPolicy.can_archive(ctx, wl):
            logger.warning(
                "Actor %s denied permission to unarchive wishlist %s",
                actor.telegram_id,
                wishlist_id,
                extra={
                    "event": "access_denied",
                    "actor_id": actor.telegram_id,
                    "wishlist_id": wishlist_id,
                    "action": "unarchive_wishlist",
                },
            )
            raise PermissionDeniedError("Actor cannot unarchive wishlist")

        old_status = wl.status.value
        wl.status = WishlistStatus.ACTIVE
        wl.updated_at = datetime.now(UTC)
        logger.info(
            "Wishlist %s transitioned from %s to %s by actor %s",
            wishlist_id,
            old_status,
            WishlistStatus.ACTIVE.value,
            actor.telegram_id,
            extra={
                "event": "wishlist_status_changed",
                "wishlist_id": wishlist_id,
                "actor_id": actor.telegram_id,
                "from_status": old_status,
                "to_status": WishlistStatus.ACTIVE.value,
            },
        )
        return wl

    async def delete_wishlist(
        self,
        wishlist_id: int,
        actor: AuthenticatedUser,
    ) -> None:
        """Soft delete a wishlist and cancel all active reservations."""
        wl = await self.get_wishlist_by_id(wishlist_id)
        self._ensure_wishlist_active(wl)
        ctx = WishlistAccessPolicy.resolve_context(actor, wl)
        if not WishlistAccessPolicy.can_delete(ctx, wl):
            logger.warning(
                "Actor %s denied permission to delete wishlist %s",
                actor.telegram_id,
                wishlist_id,
                extra={
                    "event": "access_denied",
                    "actor_id": actor.telegram_id,
                    "wishlist_id": wishlist_id,
                    "action": "delete_wishlist",
                },
            )
            raise PermissionDeniedError("Actor cannot delete wishlist")

        old_status = wl.status.value
        wl.status = WishlistStatus.DELETED
        wl.updated_at = datetime.now(UTC)
        for item in wl.items:
            for res in item.reservations:
                if res.status in (ReservationStatus.ACTIVE, ReservationStatus.PURCHASED):
                    res.status = ReservationStatus.CANCELLED
                    res.updated_at = datetime.now(UTC)
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

    async def transfer_ownership(
        self,
        wishlist_id: int,
        actor: AuthenticatedUser,
        new_owner_id: int,
    ) -> Wishlist:
        """Transfer wishlist ownership to a collaborator."""
        wl = await self.get_wishlist_by_id(wishlist_id)
        ctx = WishlistAccessPolicy.resolve_context(actor, wl)
        if not WishlistAccessPolicy.can_transfer_ownership(ctx, wl):
            logger.warning(
                "Actor %s denied permission to transfer ownership of wishlist %s",
                actor.telegram_id,
                wishlist_id,
                extra={
                    "event": "access_denied",
                    "actor_id": actor.telegram_id,
                    "wishlist_id": wishlist_id,
                    "action": "transfer_ownership",
                },
            )
            raise PermissionDeniedError("Actor cannot transfer ownership")

        old_owner_id = wl.owner_id
        wl.owner_id = new_owner_id
        wl.members = [m for m in wl.members if m.user_id != new_owner_id]
        self._next_member_id += 1
        wl.members.append(
            WishlistMember(
                id=self._next_member_id,
                wishlist_id=wl.id,
                user_id=old_owner_id,
                role=WishlistRole.ADMIN,
                wishlist=wl,
            )
        )
        wl.updated_at = datetime.now(UTC)
        logger.info(
            "Wishlist %s ownership transferred from %s to %s",
            wishlist_id,
            old_owner_id,
            new_owner_id,
            extra={
                "event": "ownership_transferred",
                "wishlist_id": wishlist_id,
                "previous_owner_id": old_owner_id,
                "new_owner_id": new_owner_id,
                "actor_id": actor.telegram_id,
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
        price: int | None = None,
        currency: str = "RUB",
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
        if wl.status == WishlistStatus.ARCHIVED:
            logger.warning(
                "Attempted to add item to archived wishlist %s by actor %s",
                wishlist_id,
                actor.telegram_id,
                extra={
                    "event": "wishlist_archived_mutation_blocked",
                    "wishlist_id": wishlist_id,
                    "actor_id": actor.telegram_id,
                },
            )
            raise WishlistArchivedError(f"Wishlist {wishlist_id} is archived")
        if wl.status == WishlistStatus.DELETED:
            logger.warning(
                "Attempted to add item to deleted wishlist %s by actor %s",
                wishlist_id,
                actor.telegram_id,
                extra={
                    "event": "wishlist_deleted_mutation_blocked",
                    "wishlist_id": wishlist_id,
                    "actor_id": actor.telegram_id,
                },
            )
            raise WishlistDeletedError(f"Wishlist {wishlist_id} is deleted")

        ctx = WishlistAccessPolicy.resolve_context(actor, wl)
        if not WishlistAccessPolicy.can_add_or_edit_item(ctx, wl):
            logger.warning(
                "Actor %s denied permission to add item to wishlist %s",
                actor.telegram_id,
                wishlist_id,
                extra={
                    "event": "access_denied",
                    "actor_id": actor.telegram_id,
                    "wishlist_id": wishlist_id,
                    "action": "add_item",
                },
            )
            raise PermissionDeniedError("Actor cannot add items to this wishlist")

        self._next_item_id += 1
        item = WishItem(
            id=self._next_item_id,
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
            is_archived=False,
            recipient_user_id=recipient_user_id,
            recipient_name=recipient_name,
            wishlist=wl,
        )
        wl.items.append(item)
        self._items[item.id] = item
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
            },
        )
        return item

    async def update_wish_item(
        self,
        item_id: int,
        actor: AuthenticatedUser,
        title: str | None = None,
        description: str | None = None,
        link: str | None = None,
        image_url: str | None = None,
        price: int | None = None,
        currency: str | None = None,
        quantity: int | None = None,
        priority: ItemPriority | None = None,
        category: str | None = None,
        recipient_user_id: int | None = None,
        recipient_name: str | None = None,
    ) -> WishItem:
        """Update wish item properties enforcing multi-quantity lock invariants."""
        if item_id not in self._items:
            logger.warning(
                "Item lookup failed: id %s not found",
                item_id,
                extra={
                    "event": "item_not_found",
                    "item_id": item_id,
                    "actor_id": actor.telegram_id,
                },
            )
            raise ItemNotFoundError(f"Item {item_id} not found")

        item = self._items[item_id]
        wl = item.wishlist
        if wl is not None:
            if wl.status == WishlistStatus.ARCHIVED:
                logger.warning(
                    "Attempted to edit item in archived wishlist %s by actor %s",
                    wl.id,
                    actor.telegram_id,
                    extra={
                        "event": "item_mutation_blocked_archived",
                        "item_id": item.id,
                        "wishlist_id": wl.id,
                        "actor_id": actor.telegram_id,
                    },
                )
                raise WishlistArchivedError(f"Wishlist {wl.id} is archived")
            if wl.status == WishlistStatus.DELETED:
                logger.warning(
                    "Attempted to edit item in deleted wishlist %s by actor %s",
                    wl.id,
                    actor.telegram_id,
                    extra={
                        "event": "item_mutation_blocked_deleted",
                        "item_id": item.id,
                        "wishlist_id": wl.id,
                        "actor_id": actor.telegram_id,
                    },
                )
                raise WishlistDeletedError(f"Wishlist {wl.id} is deleted")

            ctx = WishlistAccessPolicy.resolve_context(actor, wl)
            if not WishlistAccessPolicy.can_add_or_edit_item(ctx, wl):
                logger.warning(
                    "Actor %s denied permission to edit item %s in wishlist %s",
                    actor.telegram_id,
                    item.id,
                    wl.id,
                    extra={
                        "event": "access_denied",
                        "actor_id": actor.telegram_id,
                        "wishlist_id": wl.id,
                        "item_id": item.id,
                        "action": "edit_item",
                    },
                )
                raise PermissionDeniedError("Actor cannot edit this item")

        quantity_delta = 0
        if quantity is not None:
            active_locked = item.reserved_quantity + item.received_quantity
            if quantity < active_locked:
                logger.warning(
                    "Item %s quantity reduction rejected: requested %s, locked %s",
                    item.id,
                    quantity,
                    active_locked,
                    extra={
                        "event": "item_quantity_reduction_rejected",
                        "item_id": item.id,
                        "wishlist_id": wl.id if wl else None,
                        "actor_id": actor.telegram_id,
                        "requested_quantity": quantity,
                        "locked_quantity": active_locked,
                    },
                )
                raise CannotReduceQuantityBelowReservedError(
                    f"Cannot reduce quantity to {quantity}: {active_locked} units already locked"
                )
            quantity_delta = quantity - item.quantity
            item.quantity = quantity

        if title is not None:
            item.title = title
        if description is not None:
            item.description = description
        if link is not None:
            item.link = link
        if image_url is not None:
            item.image_url = image_url
        if price is not None:
            item.price = price
        if currency is not None:
            item.currency = currency
        if priority is not None:
            item.priority = priority
        if category is not None:
            item.category = category
        if recipient_user_id is not None:
            item.recipient_user_id = recipient_user_id
        if recipient_name is not None:
            item.recipient_name = recipient_name

        item.updated_at = datetime.now(UTC)
        logger.info(
            "Item %s updated by actor %s (delta=%s, new_qty=%s)",
            item.id,
            actor.telegram_id,
            quantity_delta,
            item.quantity,
            extra={
                "event": "item_updated",
                "item_id": item.id,
                "wishlist_id": wl.id if wl else None,
                "actor_id": actor.telegram_id,
                "quantity": item.quantity,
                "quantity_delta": quantity_delta,
            },
        )
        return item

    async def create_reservation(
        self,
        item_id: int,
        user: AuthenticatedUser | None,
        quantity: int = 1,
    ) -> Reservation:
        """Reserve quantity units of an item on behalf of a gifter."""
        gifter_id = user.telegram_id if user is not None else 0
        async with self._concurrency_coordinator.acquire(item_id):
            if item_id not in self._items:
                logger.warning(
                    "Reservation failed: item %s not found",
                    item_id,
                    extra={
                        "event": "item_not_found",
                        "item_id": item_id,
                        "gifter_id": gifter_id,
                    },
                )
                raise ItemNotFoundError(f"Item {item_id} not found")

            item = self._items[item_id]
            wl = item.wishlist
            if wl is not None:
                if wl.status == WishlistStatus.ARCHIVED:
                    logger.warning(
                        "Reservation blocked on archived wishlist %s for item %s by gifter %s",
                        wl.id,
                        item_id,
                        gifter_id,
                        extra={
                            "event": "reservation_blocked_archived",
                            "wishlist_id": wl.id,
                            "item_id": item_id,
                            "gifter_id": gifter_id,
                        },
                    )
                    raise WishlistArchivedError(f"Cannot reserve: wishlist {wl.id} is archived")
                if wl.status == WishlistStatus.DELETED:
                    logger.warning(
                        "Reservation blocked on deleted wishlist %s for item %s by gifter %s",
                        wl.id,
                        item_id,
                        gifter_id,
                        extra={
                            "event": "reservation_blocked_deleted",
                            "wishlist_id": wl.id,
                            "item_id": item_id,
                            "gifter_id": gifter_id,
                        },
                    )
                    raise WishlistDeletedError(f"Cannot reserve: wishlist {wl.id} is deleted")
            if item.is_archived:
                logger.warning(
                    "Reservation blocked on archived item %s by gifter %s",
                    item_id,
                    gifter_id,
                    extra={
                        "event": "reservation_blocked_archived_item",
                        "item_id": item_id,
                        "gifter_id": gifter_id,
                    },
                )
                raise WishlistArchivedError(f"Cannot reserve: item {item_id} is archived")

            ctx = WishlistAccessPolicy.resolve_context(user, wl) if wl is not None else None
            if ctx is not None and not WishlistAccessPolicy.can_reserve_item(user, ctx, item):
                logger.warning(
                    "Self-reservation blocked: recipient %s cannot reserve item %s",
                    gifter_id,
                    item_id,
                    extra={
                        "event": "self_reservation_blocked",
                        "wishlist_id": wl.id if wl else None,
                        "item_id": item_id,
                        "user_id": gifter_id,
                        "gifter_id": gifter_id,
                        "recipient_user_id": item.recipient_user_id,
                    },
                )
                raise SelfReservationError(
                    "Recipient cannot reserve an item designated for themselves"
                )

            available_qty = item.available_quantity
            if quantity > available_qty:
                logger.warning(
                    "Reservation blocked: requested %s units of item %s, available %s (gifter %s)",
                    quantity,
                    item_id,
                    available_qty,
                    gifter_id,
                    extra={
                        "event": "insufficient_quantity_blocked",
                        "wishlist_id": wl.id if wl else None,
                        "item_id": item_id,
                        "user_id": gifter_id,
                        "gifter_id": gifter_id,
                        "requested_quantity": quantity,
                        "available_quantity": available_qty,
                    },
                )
                raise InsufficientQuantityError(
                    f"Cannot reserve {quantity} units, available: {available_qty}"
                )

            self._next_reservation_id += 1
            res = Reservation(
                id=self._next_reservation_id,
                wish_item_id=item.id,
                user_id=gifter_id,
                quantity=quantity,
                status=ReservationStatus.ACTIVE,
                wish_item=item,
            )
            item.reservations.append(res)
            self._reservations[res.id] = res
            logger.info(
                "Reservation %s created for item %s (quantity=%s) by gifter %s",
                res.id,
                item.id,
                quantity,
                gifter_id,
                extra={
                    "event": "item_reserved",
                    "wishlist_id": wl.id if wl else None,
                    "reservation_id": res.id,
                    "item_id": item.id,
                    "quantity": quantity,
                    "user_id": gifter_id,
                    "gifter_id": gifter_id,
                },
            )
            return res

    async def get_reservation_status(self, reservation_id: int) -> ReservationStatus:
        """Query the lifecycle status of a reservation."""
        if reservation_id not in self._reservations:
            logger.warning(
                "Reservation status query failed: id %s not found",
                reservation_id,
                extra={
                    "event": "reservation_not_found",
                    "reservation_id": reservation_id,
                },
            )
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")
        return self._reservations[reservation_id].status

    async def mark_reservation_purchased(
        self,
        reservation_id: int,
        user: AuthenticatedUser,
    ) -> Reservation:
        """Transition reservation from ACTIVE to PURCHASED."""
        if reservation_id not in self._reservations:
            logger.warning(
                "Mark reservation purchased failed: id %s not found",
                reservation_id,
                extra={
                    "event": "reservation_not_found",
                    "reservation_id": reservation_id,
                    "actor_id": user.telegram_id,
                },
            )
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        res = self._reservations[reservation_id]
        if res.user_id != user.telegram_id:
            logger.warning(
                "Actor %s denied permission to mark reservation %s as purchased",
                user.telegram_id,
                reservation_id,
                extra={
                    "event": "access_denied",
                    "actor_id": user.telegram_id,
                    "reservation_id": reservation_id,
                    "action": "mark_reservation_purchased",
                },
            )
            raise PermissionDeniedError("Actor is not reservation owner")

        if res.status != ReservationStatus.ACTIVE:
            logger.warning(
                "Invalid reservation transition to PURCHASED from status %s for reservation %s",
                res.status,
                reservation_id,
                extra={
                    "event": "invalid_reservation_transition",
                    "reservation_id": reservation_id,
                    "from_status": res.status,
                    "to_status": ReservationStatus.PURCHASED,
                },
            )
            raise ReservationError(f"Cannot mark reservation in status {res.status} as purchased")

        async with self._concurrency_coordinator.acquire(res.wish_item_id):
            self._ensure_reservation_writable(res)
            res.status = ReservationStatus.PURCHASED
            res.updated_at = datetime.now(UTC)

        logger.info(
            "Reservation %s marked as PURCHASED by actor %s",
            reservation_id,
            user.telegram_id,
            extra={
                "event": "reservation_purchased",
                "wishlist_id": res.wish_item.wishlist_id if res.wish_item else None,
                "reservation_id": reservation_id,
                "item_id": res.wish_item_id,
                "wish_item_id": res.wish_item_id,
                "user_id": user.telegram_id,
                "actor_id": user.telegram_id,
                "quantity": res.quantity,
            },
        )
        return res

    async def revert_reservation_to_active(
        self,
        reservation_id: int,
        user: AuthenticatedUser,
    ) -> Reservation:
        """Transition reservation from PURCHASED back to ACTIVE."""
        if reservation_id not in self._reservations:
            logger.warning(
                "Revert reservation failed: id %s not found",
                reservation_id,
                extra={
                    "event": "reservation_not_found",
                    "reservation_id": reservation_id,
                    "actor_id": user.telegram_id,
                    "user_id": user.telegram_id,
                },
            )
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        res = self._reservations[reservation_id]
        if res.user_id != user.telegram_id:
            logger.warning(
                "Actor %s denied permission to revert reservation %s to active",
                user.telegram_id,
                reservation_id,
                extra={
                    "event": "access_denied",
                    "actor_id": user.telegram_id,
                    "user_id": user.telegram_id,
                    "reservation_id": reservation_id,
                    "action": "revert_reservation_to_active",
                },
            )
            raise PermissionDeniedError("Actor is not reservation owner")

        if res.status != ReservationStatus.PURCHASED:
            logger.warning(
                "Invalid reservation transition to ACTIVE from status %s for reservation %s",
                res.status,
                reservation_id,
                extra={
                    "event": "invalid_reservation_transition",
                    "reservation_id": reservation_id,
                    "from_status": res.status,
                    "to_status": ReservationStatus.ACTIVE,
                },
            )
            raise ReservationError(f"Cannot revert reservation in status {res.status} to active")

        async with self._concurrency_coordinator.acquire(res.wish_item_id):
            self._ensure_reservation_writable(res)
            res.status = ReservationStatus.ACTIVE
            res.updated_at = datetime.now(UTC)

        logger.info(
            "Reservation %s reverted to ACTIVE by actor %s",
            reservation_id,
            user.telegram_id,
            extra={
                "event": "reservation_reverted",
                "wishlist_id": res.wish_item.wishlist_id if res.wish_item else None,
                "reservation_id": reservation_id,
                "item_id": res.wish_item_id,
                "wish_item_id": res.wish_item_id,
                "user_id": user.telegram_id,
                "actor_id": user.telegram_id,
                "quantity": res.quantity,
            },
        )
        return res

    mark_reservation_unpurchased = revert_reservation_to_active

    async def cancel_reservation(
        self,
        reservation_id: int,
        user: AuthenticatedUser,
    ) -> Reservation:
        """Cancel reservation and immediately restock available inventory balance."""
        if reservation_id not in self._reservations:
            logger.warning(
                "Cancel reservation failed: id %s not found",
                reservation_id,
                extra={
                    "event": "reservation_not_found",
                    "reservation_id": reservation_id,
                    "actor_id": user.telegram_id,
                    "user_id": user.telegram_id,
                },
            )
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        res = self._reservations[reservation_id]
        if res.user_id != user.telegram_id:
            logger.warning(
                "Actor %s denied permission to cancel reservation %s",
                user.telegram_id,
                reservation_id,
                extra={
                    "event": "access_denied",
                    "actor_id": user.telegram_id,
                    "user_id": user.telegram_id,
                    "reservation_id": reservation_id,
                    "action": "cancel_reservation",
                },
            )
            raise PermissionDeniedError("Actor is not reservation owner")

        if res.status == ReservationStatus.CANCELLED:
            logger.warning(
                "Attempt to cancel already cancelled reservation %s by actor %s",
                reservation_id,
                user.telegram_id,
                extra={
                    "event": "reservation_already_cancelled",
                    "reservation_id": reservation_id,
                    "actor_id": user.telegram_id,
                    "user_id": user.telegram_id,
                },
            )
            raise ReservationError("Reservation is already cancelled")

        async with self._concurrency_coordinator.acquire(res.wish_item_id):
            self._ensure_reservation_writable(res)
            res.status = ReservationStatus.CANCELLED
            res.updated_at = datetime.now(UTC)

        logger.info(
            "Reservation %s cancelled by actor %s",
            reservation_id,
            user.telegram_id,
            extra={
                "event": "reservation_cancelled",
                "wishlist_id": res.wish_item.wishlist_id if res.wish_item else None,
                "reservation_id": reservation_id,
                "item_id": res.wish_item_id,
                "wish_item_id": res.wish_item_id,
                "user_id": user.telegram_id,
                "actor_id": user.telegram_id,
                "quantity": res.quantity,
            },
        )
        return res

    async def update_reservation_quantity(
        self,
        reservation_id: int,
        user: AuthenticatedUser,
        new_quantity: int,
    ) -> Reservation:
        """Adjust reserved quantity up or down with inventory bounds verification."""
        if reservation_id not in self._reservations:
            logger.warning(
                "Update reservation quantity failed: id %s not found",
                reservation_id,
                extra={
                    "event": "reservation_not_found",
                    "reservation_id": reservation_id,
                    "actor_id": user.telegram_id,
                    "user_id": user.telegram_id,
                },
            )
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        res = self._reservations[reservation_id]
        if res.user_id != user.telegram_id:
            logger.warning(
                "Actor %s denied permission to update quantity of reservation %s",
                user.telegram_id,
                reservation_id,
                extra={
                    "event": "access_denied",
                    "actor_id": user.telegram_id,
                    "user_id": user.telegram_id,
                    "reservation_id": reservation_id,
                    "action": "update_reservation_quantity",
                },
            )
            raise PermissionDeniedError("Actor is not reservation owner")

        if res.status not in (ReservationStatus.ACTIVE, ReservationStatus.PURCHASED):
            logger.warning(
                "Cannot update quantity for reservation %s in terminal status %s",
                reservation_id,
                res.status,
                extra={
                    "event": "reservation_update_blocked",
                    "reservation_id": reservation_id,
                    "status": res.status,
                },
            )
            raise ReservationError(f"Cannot update reservation in status {res.status}")

        if new_quantity < 1:
            raise ValueError("Reservation quantity must be at least 1")

        async with self._concurrency_coordinator.acquire(res.wish_item_id):
            self._ensure_reservation_writable(res)
            item = self._items[res.wish_item_id]
            delta = new_quantity - res.quantity
            if delta > 0 and delta > item.available_quantity:
                logger.warning(
                    "Cannot increase reservation %s by %s: %s available",
                    reservation_id,
                    delta,
                    item.available_quantity,
                    extra={
                        "event": "insufficient_quantity_blocked",
                        "wishlist_id": item.wishlist_id if item else None,
                        "item_id": res.wish_item_id,
                        "reservation_id": reservation_id,
                        "user_id": user.telegram_id,
                        "actor_id": user.telegram_id,
                        "requested_quantity": new_quantity,
                        "delta": delta,
                        "available_quantity": item.available_quantity,
                    },
                )
                raise InsufficientQuantityError(
                    f"Cannot increase reservation by {delta}: {item.available_quantity} available"
                )

            old_quantity = res.quantity
            res.quantity = new_quantity
            res.updated_at = datetime.now(UTC)

        logger.info(
            "Reservation %s quantity updated to %s by actor %s",
            reservation_id,
            new_quantity,
            user.telegram_id,
            extra={
                "event": "reservation_quantity_updated",
                "wishlist_id": res.wish_item.wishlist_id if res.wish_item else None,
                "reservation_id": reservation_id,
                "item_id": res.wish_item_id,
                "wish_item_id": res.wish_item_id,
                "user_id": user.telegram_id,
                "actor_id": user.telegram_id,
                "quantity": new_quantity,
                "old_quantity": old_quantity,
                "new_quantity": new_quantity,
            },
        )
        return res

    async def get_user_reservations(
        self,
        user_id: int,
    ) -> list[MyReservationItemDTO]:
        """Fetch all active and purchased reservations for a gifter."""
        results: list[MyReservationItemDTO] = []
        for res in self._reservations.values():
            if res.user_id == user_id and res.status in (
                ReservationStatus.ACTIVE,
                ReservationStatus.PURCHASED,
            ):
                item = self._items.get(res.wish_item_id)
                if item is None:
                    continue
                wl = item.wishlist
                recipient_name = item.recipient_name or (wl.owner_name if wl else "") or "Recipient"
                results.append(
                    MyReservationItemDTO(
                        reservation_id=res.id,
                        wish_item_id=item.id,
                        wishlist_id=item.wishlist_id,
                        wishlist_title=wl.title if wl else "",
                        recipient_name=recipient_name,
                        item_title=item.title,
                        item_link=item.link,
                        item_image_url=item.image_url,
                        item_price=item.price,
                        currency=item.currency,
                        reserved_quantity=res.quantity,
                        status=res.status,
                        event_title=wl.event_title if wl else None,
                        event_date=wl.event_date if wl else None,
                        is_item_archived=item.is_archived,
                        is_wishlist_archived=(
                            wl.status == WishlistStatus.ARCHIVED if wl else False
                        ),
                        created_at=res.created_at,
                        updated_at=res.updated_at,
                    )
                )
        return results

    async def get_user_reservations_summary(
        self,
        user_id: int,
    ) -> UserReservationsSummaryDTO:
        """Fetch summary counts for the user's reservations badge."""
        active_res = [
            res
            for res in self._reservations.values()
            if res.user_id == user_id
            and res.status in (ReservationStatus.ACTIVE, ReservationStatus.PURCHASED)
        ]
        distinct_items = {res.wish_item_id for res in active_res}
        return UserReservationsSummaryDTO(
            user_id=user_id,
            total_active_reservations=len(active_res),
            total_distinct_items=len(distinct_items),
        )

    async def record_item_fulfillment(
        self,
        item_id: int,
        actor: AuthenticatedUser,
        received_quantity: int,
    ) -> WishItem:
        """Record partial or full receipt of a gift by list author."""
        if item_id not in self._items:
            logger.warning(
                "Record fulfillment failed: item %s not found",
                item_id,
                extra={
                    "event": "item_not_found",
                    "item_id": item_id,
                    "actor_id": actor.telegram_id,
                    "user_id": actor.telegram_id,
                },
            )
            raise ItemNotFoundError(f"Item {item_id} not found")

        item = self._items[item_id]
        wl = item.wishlist
        if wl is not None:
            ctx = WishlistAccessPolicy.resolve_context(actor, wl)
            if not WishlistAccessPolicy.can_add_or_edit_item(ctx, wl):
                logger.warning(
                    "Actor %s denied permission to fulfill item %s in wishlist %s",
                    actor.telegram_id,
                    item_id,
                    wl.id,
                    extra={
                        "event": "access_denied",
                        "actor_id": actor.telegram_id,
                        "user_id": actor.telegram_id,
                        "wishlist_id": wl.id,
                        "item_id": item_id,
                        "action": "record_item_fulfillment",
                    },
                )
                raise PermissionDeniedError("Actor cannot fulfill items in this wishlist")

        if received_quantity < 1:
            raise ValueError("Received quantity must be at least 1")

        async with self._concurrency_coordinator.acquire(item_id):
            remaining_unfulfilled = item.quantity - item.received_quantity
            if received_quantity > remaining_unfulfilled:
                logger.warning(
                    "Fulfillment quantity %s exceeds remaining unfulfilled %s for item %s",
                    received_quantity,
                    remaining_unfulfilled,
                    item_id,
                    extra={
                        "event": "fulfillment_quantity_exceeded",
                        "item_id": item_id,
                        "wishlist_id": wl.id if wl else None,
                        "user_id": actor.telegram_id,
                        "received_quantity": received_quantity,
                        "remaining_unfulfilled": remaining_unfulfilled,
                    },
                )
                raise ValueError(
                    f"Received quantity {received_quantity} exceeds "
                    f"remaining unfulfilled {remaining_unfulfilled}"
                )
            item.received_quantity += received_quantity
            item.updated_at = datetime.now(UTC)

        logger.info(
            "Item %s fulfillment recorded: %s units by user %s",
            item_id,
            received_quantity,
            actor.telegram_id,
            extra={
                "event": "item_fulfilled",
                "wishlist_id": wl.id if wl else None,
                "item_id": item.id,
                "user_id": actor.telegram_id,
                "actor_id": actor.telegram_id,
                "quantity": received_quantity,
                "received_quantity": item.received_quantity,
                "total_quantity": item.quantity,
            },
        )
        return item

    async def join_by_invite(
        self,
        invite_token: str,
        user: AuthenticatedUser,
    ) -> WishlistMember:
        """Join a wishlist as Member using an invite token."""
        wl = next((w for w in self._wishlists.values() if w.invite_token == invite_token), None)
        if wl is None:
            logger.warning(
                "User %s attempted to join with non-existent invite token",
                user.telegram_id,
                extra={
                    "event": "invalid_invite_token",
                    "user_id": user.telegram_id,
                },
            )
            raise InvalidInviteTokenError("Invalid invite token")
        if wl.status == WishlistStatus.DELETED:
            logger.warning(
                "User %s attempted to join deleted wishlist %s",
                user.telegram_id,
                wl.id,
                extra={
                    "event": "join_deleted_wishlist",
                    "user_id": user.telegram_id,
                    "wishlist_id": wl.id,
                },
            )
            raise WishlistDeletedError(f"Wishlist {wl.id} is deleted")
        self._ensure_wishlist_active(wl)
        if wl.invite_token_expires_at is not None and wl.invite_token_expires_at < datetime.now(
            UTC
        ):
            logger.warning(
                "User %s attempted to join wishlist %s with expired invite token",
                user.telegram_id,
                wl.id,
                extra={
                    "event": "expired_invite_token",
                    "user_id": user.telegram_id,
                    "wishlist_id": wl.id,
                },
            )
            raise InvalidInviteTokenError("Invite token has expired")

        existing = next((m for m in wl.members if m.user_id == user.telegram_id), None)
        if existing is not None:
            return existing

        self._next_member_id += 1
        member = WishlistMember(
            id=self._next_member_id,
            wishlist_id=wl.id,
            user_id=user.telegram_id,
            role=WishlistRole.MEMBER,
            wishlist=wl,
        )
        wl.members.append(member)
        wl.is_collaborative = True
        logger.info(
            "User %s joined wishlist %s via invite token with role %s",
            user.telegram_id,
            wl.id,
            WishlistRole.MEMBER.value,
            extra={
                "event": "member_joined",
                "user_id": user.telegram_id,
                "wishlist_id": wl.id,
                "role": WishlistRole.MEMBER.value,
            },
        )
        return member

    async def get_wishlist_by_invite_token(
        self,
        invite_token: str,
    ) -> Wishlist | None:
        """Find active wishlist by invite token."""
        wl = next((w for w in self._wishlists.values() if w.invite_token == invite_token), None)
        if wl is None or wl.status == WishlistStatus.DELETED:
            return None
        return wl

    async def regenerate_public_token(
        self,
        wishlist_id: int,
        actor: AuthenticatedUser,
    ) -> str:
        """Revoke existing public token and generate a new one."""
        wl = await self.get_wishlist_by_id(wishlist_id)
        self._ensure_wishlist_active(wl)
        ctx = WishlistAccessPolicy.resolve_context(actor, wl)
        if not (ctx.is_owner or ctx.is_admin):
            logger.warning(
                "Actor %s denied permission to regenerate public token for wishlist %s",
                actor.telegram_id,
                wishlist_id,
                extra={
                    "event": "access_denied",
                    "actor_id": actor.telegram_id,
                    "wishlist_id": wishlist_id,
                    "action": "regenerate_public_token",
                },
            )
            raise PermissionDeniedError("Actor cannot regenerate public token")

        new_token = secrets.token_urlsafe(16)
        for _ in range(4):
            if new_token != wl.public_token:
                break
            new_token = secrets.token_urlsafe(16)
        if new_token == wl.public_token:
            raise RuntimeError("Unable to generate a new public token")
        wl.public_token = new_token
        wl.updated_at = datetime.now(UTC)
        logger.info(
            "Public token regenerated for wishlist %s by actor %s",
            wishlist_id,
            actor.telegram_id,
            extra={
                "event": "public_token_regenerated",
                "actor_id": actor.telegram_id,
                "wishlist_id": wishlist_id,
                "token_type": "public_token",
            },
        )
        return new_token

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
                "Actor %s denied permission to regenerate invite token for wishlist %s",
                actor.telegram_id,
                wishlist_id,
                extra={
                    "event": "access_denied",
                    "actor_id": actor.telegram_id,
                    "wishlist_id": wishlist_id,
                    "action": "regenerate_invite_token",
                },
            )
            raise PermissionDeniedError("Actor cannot regenerate invite token")

        new_token = secrets.token_urlsafe(24)
        for _ in range(4):
            if new_token != wl.invite_token and new_token != wl.public_token:
                break
            new_token = secrets.token_urlsafe(24)
        if new_token in {wl.invite_token, wl.public_token}:
            raise RuntimeError("Unable to generate a new invitation token")
        wl.invite_token = new_token
        ttl = expires_in if expires_in is not None else self._default_invite_ttl
        wl.invite_token_expires_at = datetime.now(UTC) + ttl
        wl.updated_at = datetime.now(UTC)
        logger.info(
            "Invite token regenerated for wishlist %s by actor %s",
            wishlist_id,
            actor.telegram_id,
            extra={
                "event": "invite_token_regenerated",
                "actor_id": actor.telegram_id,
                "wishlist_id": wishlist_id,
                "token_type": "invite_token",
            },
        )
        return new_token

    def has_favorite(self, user_id: int, wishlist_id: int) -> bool:
        """Check synchronously if a user has favorited a wishlist."""
        return (user_id, wishlist_id) in self._favorites

    async def is_favorite(self, user: AuthenticatedUser | None, wishlist_id: int) -> bool:
        """Check if a user has favorited a wishlist."""
        if user is None:
            return False
        return self.has_favorite(user.telegram_id, wishlist_id)

    async def add_favorite(self, user: AuthenticatedUser, wishlist_id: int) -> WishlistFavorite:
        """Add a wishlist to user's favorites."""
        wl = self._wishlists.get(wishlist_id)
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

        key = (user.telegram_id, wishlist_id)
        fav = self._favorites.get(key)
        if fav is None:
            fav = WishlistFavorite(user_id=user.telegram_id, wishlist_id=wishlist_id)
            self._favorites[key] = fav
            logger.info(
                "Wishlist %s favorited by user %s",
                wishlist_id,
                user.telegram_id,
                extra={
                    "event": "favorite_added",
                    "wishlist_id": wishlist_id,
                    "user_id": user.telegram_id,
                },
            )
        return fav

    async def remove_favorite(self, user: AuthenticatedUser, wishlist_id: int) -> None:
        """Remove a wishlist from user's favorites."""
        key = (user.telegram_id, wishlist_id)
        if self._favorites.pop(key, None) is not None:
            logger.info(
                "Wishlist %s unfavorited by user %s",
                wishlist_id,
                user.telegram_id,
                extra={
                    "event": "favorite_removed",
                    "wishlist_id": wishlist_id,
                    "user_id": user.telegram_id,
                },
            )

    async def list_favorites(self, user: AuthenticatedUser) -> list[Wishlist]:
        """List user's favorited wishlists in reverse-chronological order."""
        user_favs = [f for f in self._favorites.values() if f.user_id == user.telegram_id]
        user_favs.sort(key=lambda f: f.created_at, reverse=True)
        result: list[Wishlist] = []
        for f in user_favs:
            wl = self._wishlists.get(f.wishlist_id)
            if wl is not None and wl.status != WishlistStatus.DELETED:
                result.append(wl)
        logger.info(
            "Favorites listed for user %s (count=%s)",
            user.telegram_id,
            len(result),
            extra={
                "event": "favorites_listed",
                "user_id": user.telegram_id,
                "count": len(result),
            },
        )
        return result

    async def record_view(self, user: AuthenticatedUser, wishlist_id: int) -> ViewHistoryEntry:
        """Record or update a wishlist view event for user, bounding history to 20 entries."""
        wl = self._wishlists.get(wishlist_id)
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

        now = datetime.now(UTC)
        existing = next(
            (
                e
                for e in self._view_history
                if e.user_id == user.telegram_id and e.wishlist_id == wishlist_id
            ),
            None,
        )
        if existing is not None:
            self._view_history.remove(existing)
            existing.viewed_at = now
            self._view_history.append(existing)
            entry = existing
        else:
            self._next_view_history_id += 1
            entry = ViewHistoryEntry(
                id=self._next_view_history_id,
                user_id=user.telegram_id,
                wishlist_id=wishlist_id,
                viewed_at=now,
            )
            self._view_history.append(entry)

        user_entries = [e for e in self._view_history if e.user_id == user.telegram_id]
        if len(user_entries) > 20:
            user_entries.sort(key=lambda e: e.viewed_at)
            to_remove = {e.id for e in user_entries[:-20]}
            self._view_history = [e for e in self._view_history if e.id not in to_remove]

        logger.info(
            "Wishlist %s view recorded for user %s",
            wishlist_id,
            user.telegram_id,
            extra={
                "event": "view_history_recorded",
                "wishlist_id": wishlist_id,
                "user_id": user.telegram_id,
            },
        )
        return entry

    async def get_history(
        self, user: AuthenticatedUser, limit: int = 20
    ) -> list[tuple[Wishlist, datetime]]:
        """Retrieve up to limit recent wishlists viewed by user, reverse-chronologically."""
        user_entries = [e for e in self._view_history if e.user_id == user.telegram_id]
        user_entries.sort(key=lambda e: e.viewed_at, reverse=True)
        result: list[tuple[Wishlist, datetime]] = []
        for e in user_entries:
            wl = self._wishlists.get(e.wishlist_id)
            if wl is not None and wl.status != WishlistStatus.DELETED:
                result.append((wl, e.viewed_at))
                if len(result) >= limit:
                    break
        logger.info(
            "Viewing history listed for user %s (count=%s)",
            user.telegram_id,
            len(result),
            extra={
                "event": "view_history_listed",
                "user_id": user.telegram_id,
                "count": len(result),
            },
        )
        return result

    async def clear_history(self, user: AuthenticatedUser) -> None:
        """Clear all viewing history entries for user."""
        self._view_history = [e for e in self._view_history if e.user_id != user.telegram_id]
        logger.info(
            "Viewing history cleared for user %s",
            user.telegram_id,
            extra={
                "event": "view_history_cleared",
                "user_id": user.telegram_id,
            },
        )


# Wrap every public async domain operation so callers of the configured service share
# the same transaction boundary as HTTP. Plain WishlistService() remains available
# as an explicitly in-memory test implementation.
for _method_name, _method in tuple(vars(WishlistService).items()):
    if not _method_name.startswith("_") and iscoroutinefunction(_method):
        setattr(WishlistService, _method_name, _transactional(_method))
