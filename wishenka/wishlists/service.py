"""Wishlist service providing lifecycle management, access enforcement, and projections."""

import logging
import secrets
from datetime import UTC, datetime, timedelta

from wishenka.auth.models import AuthenticatedUser
from wishenka.wishlists.exceptions import (
    InsufficientQuantityError,
    InvalidInviteTokenError,
    ItemNotFoundError,
    PermissionDeniedError,
    ReservationError,
    SelfReservationError,
    WishlistArchivedError,
    WishlistDeletedError,
    WishlistNotFoundError,
)
from wishenka.wishlists.models import (
    Reservation,
    ReservationStatus,
    WishItem,
    Wishlist,
    WishlistFormat,
    WishlistMember,
    WishlistRole,
    WishlistStatus,
    WishlistTimeType,
)
from wishenka.wishlists.policy import WishlistAccessPolicy
from wishenka.wishlists.schemas import (
    WishItemGifterViewDTO,
    WishItemRecipientViewDTO,
    WishlistDetailViewDTO,
)

logger = logging.getLogger("wishenka.wishlists")


class WishlistService:
    """Domain service managing wishlists, members, items, and role-aware projections."""

    def __init__(self) -> None:
        self._wishlists: dict[int, Wishlist] = {}
        self._items: dict[int, WishItem] = {}
        self._reservations: dict[int, Reservation] = {}
        self._next_wishlist_id: int = 0
        self._next_member_id: int = 0
        self._next_item_id: int = 0
        self._next_reservation_id: int = 0

    async def create_wishlist(
        self,
        owner: AuthenticatedUser,
        title: str,
        description: str | None = None,
        event_title: str | None = None,
        event_date: datetime | None = None,
        invite_token_expires_in: timedelta | None = None,
    ) -> Wishlist:
        """Create a new personal wishlist with cryptographically secure tokens."""
        self._next_wishlist_id += 1
        public_token = secrets.token_urlsafe(16)
        invite_token = secrets.token_urlsafe(24)
        ttl = invite_token_expires_in if invite_token_expires_in is not None else timedelta(days=7)
        invite_token_expires_at = datetime.now(UTC) + ttl

        wishlist = Wishlist(
            id=self._next_wishlist_id,
            owner_id=owner.telegram_id,
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
            owner.telegram_id,
            extra={
                "event": "wishlist_created",
                "wishlist_id": wishlist.id,
                "owner_id": owner.telegram_id,
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
            raise WishlistNotFoundError(f"Wishlist with token '{public_token}' not found")
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
                        price=item.price,
                        currency=item.currency,
                        quantity=item.quantity,
                        received_quantity=item.received_quantity,
                        is_archived=item.is_archived,
                        recipient_name=item.recipient_name,
                        is_recipient=True,
                    )
                )
            else:
                active_reservations = [
                    r for r in item.reservations if r.status == ReservationStatus.ACTIVE
                ]
                reserved_qty = sum(r.quantity for r in active_reservations)
                available_qty = max(0, item.quantity - item.received_quantity - reserved_qty)
                my_reserved_qty = 0
                if current_user is not None:
                    my_reserved_qty = sum(
                        r.quantity
                        for r in active_reservations
                        if r.user_id == current_user.telegram_id
                    )
                item_views.append(
                    WishItemGifterViewDTO(
                        id=item.id,
                        title=item.title,
                        description=item.description,
                        link=item.link,
                        price=item.price,
                        currency=item.currency,
                        quantity=item.quantity,
                        received_quantity=item.received_quantity,
                        available_quantity=available_qty,
                        is_fully_reserved=(available_qty == 0),
                        is_reserved_by_me=(my_reserved_qty > 0),
                        my_reserved_quantity=my_reserved_qty,
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
                if res.status == ReservationStatus.ACTIVE:
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
                "Surprise Invariant trigger: recipient %s attempted self-reservation on item %s",
                gifter_id,
                item_id,
                extra={
                    "event": "surprise_invariant_violation_attempt",
                    "gifter_id": gifter_id,
                    "item_id": item_id,
                    "recipient_user_id": item.recipient_user_id,
                },
            )
            raise SelfReservationError("Recipient cannot reserve an item designated for themselves")

        active_reservations = [r for r in item.reservations if r.status == ReservationStatus.ACTIVE]
        reserved_qty = sum(r.quantity for r in active_reservations)
        available_qty = item.quantity - item.received_quantity - reserved_qty
        if quantity > available_qty:
            logger.warning(
                "Reservation failed: requested %s units of item %s, available %s (gifter %s)",
                quantity,
                item_id,
                available_qty,
                gifter_id,
                extra={
                    "event": "insufficient_quantity",
                    "item_id": item_id,
                    "requested_quantity": quantity,
                    "available_quantity": available_qty,
                    "gifter_id": gifter_id,
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
                "event": "reservation_created",
                "reservation_id": res.id,
                "item_id": item.id,
                "quantity": quantity,
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
            raise ReservationError(f"Reservation {reservation_id} not found")
        return self._reservations[reservation_id].status

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
            raise InvalidInviteTokenError(f"Invalid invite token: {invite_token}")
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

    async def regenerate_public_token(
        self,
        wishlist_id: int,
        actor: AuthenticatedUser,
    ) -> str:
        """Revoke existing public token and generate a new one."""
        wl = await self.get_wishlist_by_id(wishlist_id)
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
        wl.invite_token = new_token
        ttl = expires_in if expires_in is not None else timedelta(days=7)
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
