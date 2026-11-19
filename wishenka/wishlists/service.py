"""Wishlist service providing lifecycle management, access enforcement, and projections."""

from __future__ import annotations

import logging
import math
import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import wraps
from inspect import iscoroutinefunction, signature
from typing import TYPE_CHECKING, Any

from wishenka.auth.models import AuthenticatedUser
from wishenka.currency import DEFAULT_CURRENCY
from wishenka.items.models import ItemPriority
from wishenka.notices.events import SharedEvent
from wishenka.notices.models import (
    EVENT_GIFT_RECEIVED,
    SKIP_SETTING_LIST,
    SKIP_SETTING_USER,
    STATUS_SKIPPED,
    NoticeDraft,
    NoticeSettings,
)
from wishenka.wishlists.concurrency import ItemConcurrencyCoordinator
from wishenka.wishlists.exceptions import (
    CannotReduceQuantityBelowReservedError,
    InsufficientQuantityError,
    InvalidInviteTokenError,
    ItemNotFoundError,
    NothingRemainingError,
    PermissionDeniedError,
    QuantityAboveRemainingError,
    QuantityInvalidError,
    ReceiptNotFoundError,
    ReservationError,
    ReservationNotFoundError,
    SelfReservationError,
    WishArchivedError,
    WishlistArchivedError,
    WishlistDeletedError,
    WishlistNotFoundError,
    WishlistRetentionExpiredError,
)
from wishenka.wishlists.models import (
    ReceiptRecord,
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
    GiftedItemDTO,
    MyReservationItemDTO,
    PromiseActionDTO,
    ReceiptEntryDTO,
    UserReservationsSummaryDTO,
    WishItemGifterViewDTO,
    WishItemRecipientViewDTO,
    WishlistDetailViewDTO,
)

RESERVATION_QUANTITY_MIN_ERROR = "Reservation quantity must be at least 1"

logger = logging.getLogger("wishenka.wishlists")


@dataclass(frozen=True)
class PendingCommitLog:
    """Domain log record deferred until the enclosing store transaction commits."""

    level: int
    message: str
    args: tuple[Any, ...]
    extra: dict[str, Any]


def flush_pending_commit_logs(logs: list[PendingCommitLog]) -> None:
    """Emit domain log records that were deferred until transaction commit."""
    for entry in logs:
        logger.log(entry.level, entry.message, *entry.args, extra=entry.extra)


_ITEM_INVENTORY_METHODS = frozenset(
    {
        "create_reservation",
        "update_wish_item",
        "record_item_fulfillment",
        "cancel_item_receipt",
        "correct_item_receipt",
    }
)
_RESERVATION_INVENTORY_METHODS = frozenset(
    {
        "cancel_reservation",
        "update_reservation_quantity",
        "mark_reservation_purchased",
        "revert_reservation_to_active",
    }
)

if TYPE_CHECKING:
    from wishenka.wishlists.store import WishlistStore


def _inventory_scope(
    method: Callable[..., Awaitable[Any]],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> tuple[int | None, int | None] | None:
    """Return the wish key for an inventory method, or None for a full snapshot."""
    name = method.__name__
    if name in _ITEM_INVENTORY_METHODS:
        key = "item_id"
        keyed_by_reservation = False
    elif name in _RESERVATION_INVENTORY_METHODS:
        key = "reservation_id"
        keyed_by_reservation = True
    else:
        return None
    bound = signature(method).bind(None, *args, **kwargs)
    value = int(bound.arguments[key])
    if keyed_by_reservation:
        return None, value
    return value, None


def _transactional[T](method: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
    """Run a public domain operation in its configured persistent unit of work."""

    @wraps(method)
    async def invoke(self: WishlistService, *args: Any, **kwargs: Any) -> T:
        if self._store is None:
            return await method(self, *args, **kwargs)
        scope = _inventory_scope(method, args, kwargs)

        async def call(service: WishlistService) -> T:
            return await method(service, *args, **kwargs)

        if scope is None:
            return await self._store.execute(call)
        item_id, reservation_id = scope
        return await self._store.execute_wish(
            call,
            item_id=item_id,
            reservation_id=reservation_id,
            operation_name=method.__name__,
        )

    return invoke


def recipient_view(item: WishItem) -> WishItemRecipientViewDTO:
    """Build the recipient-safe view of a wish: no promise or giver field exists on it."""
    return WishItemRecipientViewDTO(
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
        remaining_quantity=item.remaining_quantity,
        priority=item.priority,
        category=item.category,
        display_order=item.display_order,
        is_archived=item.is_archived,
        recipient_user_id=item.recipient_user_id,
        recipient_name=item.recipient_name,
        is_recipient=True,
    )


def project_wish_item(
    item: WishItem,
    current_user: AuthenticatedUser | None = None,
) -> WishItemRecipientViewDTO | WishItemGifterViewDTO:
    """Project a WishItem into Recipient or Gifter view based on Surprise Invariant."""
    if current_user is None or WishlistAccessPolicy.is_recipient(current_user, item):
        return recipient_view(item)

    active_or_purchased = [
        r
        for r in item.reservations
        if r.status in (ReservationStatus.ACTIVE, ReservationStatus.PURCHASED)
    ]
    reserved_qty = sum(r.quantity for r in active_or_purchased)
    available_qty = max(0, item.quantity - item.received_quantity - reserved_qty)
    user_reservations = [r for r in active_or_purchased if r.user_id == current_user.telegram_id]
    my_reserved_qty = sum(r.quantity for r in user_reservations)
    my_occupying_count = len(user_reservations)
    my_reservation_status: ReservationStatus | None = None
    my_reservation_id: int | None = None
    my_latest_quantity = 0
    if user_reservations:
        my_res = user_reservations[-1]
        my_reservation_status = my_res.status
        my_reservation_id = my_res.id
        my_latest_quantity = my_res.quantity
    return WishItemGifterViewDTO(
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
        remaining_quantity=item.remaining_quantity,
        is_fully_received=item.is_fully_received,
        available_quantity=available_qty,
        is_fully_reserved=(available_qty == 0),
        is_reserved_by_me=(my_reserved_qty > 0),
        my_reserved_quantity=my_reserved_qty,
        my_reservation_status=my_reservation_status,
        my_reservation_id=my_reservation_id,
        my_latest_reservation_quantity=my_latest_quantity,
        my_occupying_reservation_count=my_occupying_count,
        priority=item.priority,
        category=item.category,
        display_order=item.display_order,
        is_archived=item.is_archived,
        recipient_user_id=item.recipient_user_id,
        recipient_name=item.recipient_name,
        is_recipient=False,
    )


def project_reservation_action(
    reservation: Reservation,
    user: AuthenticatedUser | None,
) -> PromiseActionDTO:
    """Project the single promise an action just changed for a non-recipient."""
    item = reservation.wish_item
    if item is None or WishlistAccessPolicy.is_recipient(user, item):
        raise ReservationNotFoundError(f"Reservation {reservation.id} not found")
    projected = project_wish_item(item, user)
    if not isinstance(projected, WishItemGifterViewDTO):
        raise ReservationNotFoundError(f"Reservation {reservation.id} not found")
    return PromiseActionDTO(
        reservation_id=reservation.id,
        wish_item_id=reservation.wish_item_id,
        quantity=reservation.quantity,
        status=reservation.status,
        available_quantity=item.available_quantity,
        item=projected,
    )


class WishlistService:
    """Domain service managing wishlists, members, items, and role-aware projections."""

    def __init__(
        self,
        store: WishlistStore | None = None,
        default_invite_ttl: timedelta | None = None,
        *,
        _allow_in_memory: bool = False,
    ) -> None:
        if store is None and not _allow_in_memory:
            logger.error(
                "WishlistService constructed without persistent store",
                extra={"event": "wishlist_service_store_required"},
            )
            raise ValueError(
                "WishlistService requires an explicit store (WishlistStore); "
                "use WishlistService.in_memory() for isolated tests"
            )
        self._store = store
        self._default_invite_ttl = default_invite_ttl or timedelta(days=7)
        self._wishlists: dict[int, Wishlist] = {}
        self._items: dict[int, WishItem] = {}
        self._reservations: dict[int, Reservation] = {}
        self._reservations_by_user: dict[int, dict[int, None]] = {}
        self._concurrency_coordinator = ItemConcurrencyCoordinator()
        self._next_wishlist_id: int = 0
        self._next_member_id: int = 0
        self._next_item_id: int = 0
        self._next_reservation_id: int = 0
        self._favorites: dict[tuple[int, int], WishlistFavorite] = {}
        self._view_history: list[ViewHistoryEntry] = []
        self._next_view_history_id: int = 0
        # Effects of the current unit of work; the store flushes them with the transaction.
        self._new_receipts: list[ReceiptRecord] = []
        self._updated_receipts: list[ReceiptRecord] = []
        self._deleted_receipt_ids: list[int] = []
        self._new_notices: list[NoticeDraft] = []
        self._new_shared_item_events: list[SharedEvent] = []
        self._flushed_shared_events: list[tuple[str, int]] = []
        self._defer_commit_logs: bool = False
        self._pending_commit_logs: list[PendingCommitLog] = []
        self._notice_settings: NoticeSettings = NoticeSettings()

    def _emit_or_defer_commit_log(
        self,
        level: int,
        message: str,
        *args: Any,
        extra: dict[str, Any],
    ) -> None:
        if self._defer_commit_logs:
            self._pending_commit_logs.append(
                PendingCommitLog(level=level, message=message, args=args, extra=extra)
            )
        else:
            logger.log(level, message, *args, extra=extra)

    @classmethod
    def in_memory(
        cls,
        default_invite_ttl: timedelta | None = None,
    ) -> WishlistService:
        """Create an explicitly non-persistent service for isolated tests or store hydration."""
        logger.debug(
            "WishlistService in-memory instance created",
            extra={"event": "wishlist_service_in_memory_created"},
        )
        return cls(
            store=None,
            default_invite_ttl=default_invite_ttl,
            _allow_in_memory=True,
        )

    # Reservation mutations affect only the actor's own reservation. Notifying another
    # giver would disclose that person's activity by timing; receipt notices have a
    # separate producer for each genuinely affected reservation holder.
    def _record_reservation_confirmation(self, item: WishItem, actor_id: int) -> None:
        """Queue only explicitly requested confirmations of the actor's own action."""
        wl = item.wishlist
        if wl is None or WishlistAccessPolicy.is_recipient_id(actor_id, item):
            return
        self._new_shared_item_events.append(
            SharedEvent(
                "reservation_confirmation",
                wl.id,
                item.id,
                secrets.token_hex(16),
                (actor_id,),
                frozenset(member.user_id for member in wl.members),
            )
        )

    def _record_shared_event(
        self,
        kind: str,
        wishlist: Wishlist,
        item: WishItem | None,
        actor_id: int,
        *,
        exclude_recipients: frozenset[int] = frozenset(),
    ) -> None:
        """Snapshot event-time candidates before later changes in the same transaction."""
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
        self._new_shared_item_events.append(
            SharedEvent(
                kind,
                wishlist.id,
                item.id if item else None,
                secrets.token_hex(16),
                tuple(sorted(recipients)),
                frozenset(member.user_id for member in wishlist.members),
            )
        )

    def _notice_gate(
        self, user_id: int, wishlist_id: int, event_type: str
    ) -> tuple[bool, str | None]:
        """Decide whether a giver wants a notice: list row, else user row, else on.

        Returns ``(enabled, level)`` where ``level`` is ``"list"``, ``"user"`` or ``None`` for
        the default. Reads only the settings loaded in the current transaction.
        """
        settings = self._notice_settings
        by_list = settings.list.get((user_id, wishlist_id, event_type))
        if by_list is not None:
            return by_list, "list"
        by_user = settings.user.get((user_id, event_type))
        if by_user is not None:
            return by_user, "user"
        return True, None

    def _record_receipt_change_event(self, kind: str, item: WishItem) -> None:
        """Queue a SharedEvent for open-promise givers (excluding recipients) on receipt changes."""
        wl = item.wishlist
        if wl is None:
            return
        givers: list[int] = []
        for reservation in item.reservations:
            if (
                reservation.status in (ReservationStatus.ACTIVE, ReservationStatus.PURCHASED)
                and reservation.user_id not in givers
                and not WishlistAccessPolicy.is_recipient_id(reservation.user_id, item)
            ):
                givers.append(reservation.user_id)
        if not givers:
            return
        self._new_shared_item_events.append(
            SharedEvent(
                kind,
                wl.id,
                item.id,
                secrets.token_hex(16),
                tuple(sorted(givers)),
                frozenset(member.user_id for member in wl.members),
            )
        )

    def _draft_receipt_notices(self, item: WishItem, receipt: ReceiptRecord) -> None:
        """Queue one notice draft per distinct promising giver, skipped when a setting says so."""
        givers: list[int] = []
        for reservation in item.reservations:
            if (
                reservation.status in (ReservationStatus.ACTIVE, ReservationStatus.PURCHASED)
                and reservation.user_id not in givers
                and not WishlistAccessPolicy.is_recipient_id(reservation.user_id, item)
            ):
                givers.append(reservation.user_id)
        for giver_id in givers:
            enabled, level = self._notice_gate(giver_id, item.wishlist_id, EVENT_GIFT_RECEIVED)
            if enabled:
                self._new_notices.append(NoticeDraft(giver_id, receipt))
            else:
                reason = SKIP_SETTING_LIST if level == "list" else SKIP_SETTING_USER
                self._new_notices.append(NoticeDraft(giver_id, receipt, STATUS_SKIPPED, reason))

    @property
    def notice_drafts(self) -> tuple[NoticeDraft, ...]:
        """Notices decided so far in this service (read-only snapshot for callers and tests)."""
        return tuple(self._new_notices)

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

    def _guard_reservation_mutation(
        self,
        reservation: Reservation,
        user: AuthenticatedUser,
        *,
        wishlist_id: int | None,
        item_id: int | None,
    ) -> None:
        """Refuse a path, recipient, or closed list before the promise is written."""
        item = reservation.wish_item
        if item_id is not None and item_id != reservation.wish_item_id:
            raise ReservationNotFoundError(f"Reservation {reservation.id} not found")
        loaded_list_id = item.wishlist_id if item is not None else None
        if wishlist_id is not None and wishlist_id != loaded_list_id:
            raise ReservationNotFoundError(f"Reservation {reservation.id} not found")
        if item is not None and WishlistAccessPolicy.is_recipient(user, item):
            raise ReservationNotFoundError(f"Reservation {reservation.id} not found")
        # Deletion cancels the row first. The closed list has to refuse before
        # the status check, or a deleted list would surface as a status conflict.
        self._ensure_reservation_writable(reservation)

    @staticmethod
    def _ensure_wishlist_active(wishlist: Wishlist) -> None:
        if wishlist.status == WishlistStatus.ARCHIVED:
            raise WishlistArchivedError("Cannot modify an archived wishlist")
        if wishlist.status == WishlistStatus.DELETED:
            raise WishlistDeletedError("Cannot modify a deleted wishlist")

    @staticmethod
    def _require_item_wishlist(item: WishItem) -> Wishlist:
        """Return the item's parent wishlist or fail closed if context is missing."""
        if item.wishlist is None:
            logger.error(
                "Invariant violation: item %s has no parent wishlist (wishlist_id=%s)",
                item.id,
                item.wishlist_id,
                extra={
                    "event": "item_missing_parent_wishlist",
                    "item_id": item.id,
                    "wishlist_id": item.wishlist_id,
                },
            )
            raise WishlistNotFoundError(f"Wishlist {item.wishlist_id} not found")
        return item.wishlist

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
        view = await self.get_wishlist_view(wl.id, current_user)
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

    async def get_wishlist_view(
        self,
        wishlist_id: int,
        current_user: AuthenticatedUser | None = None,
    ) -> WishlistDetailViewDTO:
        """Project wishlist and items applying Surprise Invariant rules."""
        wl = await self.get_wishlist_by_id(wishlist_id)

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
                "items_count": len(item_views),
                "archived_items_count": len(archived_views),
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
            warn_on_delete_reserved=wl.warn_on_delete_reserved,
            status=wl.status,
            user_role=ctx.role,
            can_edit=can_edit,
            can_archive=can_archive,
            can_delete=can_delete,
            public_token=wl.public_token,
            invite_token=invite_token,
            items=item_views,
            archived_items=archived_views,
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
            if existing.role != role:
                self._record_shared_event("membership_changed", wl, None, actor.telegram_id)
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
        self._record_shared_event("membership_changed", wl, None, actor.telegram_id)
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

        if any(m.user_id == user_id for m in wl.members):
            self._record_shared_event("membership_changed", wl, None, actor.telegram_id)
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

        changed = any(
            (
                title is not None and title != wl.title,
                description is not None and description != wl.description,
                event_title is not None and event_title != wl.event_title,
                event_date is not None and event_date != wl.event_date,
            )
        )
        if title is not None:
            wl.title = title
        if description is not None:
            wl.description = description
        if event_title is not None:
            wl.event_title = event_title
        if event_date is not None:
            wl.event_date = event_date
        if changed:
            self._record_shared_event("list_updated", wl, None, actor.telegram_id)
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
        self._record_shared_event("list_archived", wl, None, actor.telegram_id)
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
        if old_status != WishlistStatus.ACTIVE.value:
            self._record_shared_event("list_restored", wl, None, actor.telegram_id)
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
        for wl in self._wishlists.values():
            if wl.status != WishlistStatus.DELETED:
                continue
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
        wl = self._wishlists.get(wishlist_id)
        if wl is None:
            raise WishlistNotFoundError(f"Wishlist {wishlist_id} not found")

        ctx = WishlistAccessPolicy.resolve_context(actor, wl)
        if not WishlistAccessPolicy.can_restore_deleted(ctx, wl):
            logger.warning(
                "Actor %s denied permission to restore deleted wishlist %s",
                actor.telegram_id,
                wishlist_id,
                extra={
                    "event": "access_denied",
                    "actor_id": actor.telegram_id,
                    "wishlist_id": wishlist_id,
                    "action": "restore_deleted_wishlist",
                },
            )
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

        new_public_token = secrets.token_urlsafe(16)
        for _ in range(4):
            if new_public_token not in {wl.public_token, wl.invite_token}:
                break
            new_public_token = secrets.token_urlsafe(16)
        if new_public_token in {wl.public_token, wl.invite_token}:
            raise RuntimeError("Unable to generate a new public token")

        new_invite_token = secrets.token_urlsafe(24)
        for _ in range(4):
            if new_invite_token not in {wl.invite_token, wl.public_token, new_public_token}:
                break
            new_invite_token = secrets.token_urlsafe(24)
        if new_invite_token in {wl.invite_token, wl.public_token, new_public_token}:
            raise RuntimeError("Unable to generate a new invitation token")

        wl.public_token = new_public_token
        wl.invite_token = new_invite_token
        wl.invite_token_expires_at = effective_now + self._default_invite_ttl
        wl.status = WishlistStatus.ACTIVE
        wl.updated_at = effective_now
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
        self._record_shared_event("membership_changed", wl, None, actor.telegram_id)
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
            display_order=next_order,
            is_archived=False,
            recipient_user_id=recipient_user_id,
            recipient_name=recipient_name,
            wishlist=wl,
        )
        wl.items.append(item)
        self._items[item.id] = item
        self._record_shared_event("item_created", wl, item, actor.telegram_id)
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
        wishlist_id: int | None = None,
    ) -> WishItem:
        """Update wish item properties enforcing multi-quantity lock invariants."""
        async with self._concurrency_coordinator.acquire(item_id):
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
            before_update = (
                item.title,
                item.description,
                item.link,
                item.image_url,
                item.price,
                item.currency,
                item.quantity,
                item.priority,
                item.category,
                item.recipient_user_id,
                item.recipient_name,
            )
            if wishlist_id is not None and item.wishlist_id != wishlist_id:
                raise ItemNotFoundError(f"Item {item_id} not found in wishlist {wishlist_id}")

            if item.is_archived:
                raise WishlistArchivedError(f"Cannot edit archived item {item_id}")

            wl = self._require_item_wishlist(item)
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
                        "event": "item_access_denied",
                        "actor_id": actor.telegram_id,
                        "wishlist_id": wl.id,
                        "item_id": item.id,
                        "action": "edit_item",
                        "role": ctx.role.value if ctx.role else None,
                    },
                )
                raise PermissionDeniedError("Actor cannot edit this item")

            if recipient_user_id is not None:
                member_uids = {wl.owner_id} | {m.user_id for m in wl.members}
                if recipient_user_id not in member_uids:
                    raise ValueError(
                        f"Recipient user {recipient_user_id} is not a member of wishlist {wl.id}"
                    )

            quantity_delta = 0
            updated_fields: list[str] = []
            if quantity is not None:
                min_allowed = max(1, item.received_quantity)
                if quantity < min_allowed:
                    reason = (
                        f"Cannot reduce quantity to {quantity}: "
                        f"{item.received_quantity} units already received"
                    )
                    logger.warning(
                        "Item %s quantity reduction rejected: requested %s, received %s",
                        item.id,
                        quantity,
                        item.received_quantity,
                        extra={
                            "event": "item_quantity_reduction_rejected",
                            "item_id": item.id,
                            "wishlist_id": wl.id,
                            "actor_id": actor.telegram_id,
                            "requested_quantity": quantity,
                            "received_quantity": item.received_quantity,
                            "reason": reason,
                        },
                    )
                    raise CannotReduceQuantityBelowReservedError(reason)
                quantity_delta = quantity - item.quantity
                item.quantity = quantity
                updated_fields.append("quantity")

            if title is not None:
                item.title = title
                updated_fields.append("title")
            if description is not None:
                item.description = description
                updated_fields.append("description")
            if link is not None:
                item.link = link
                updated_fields.append("link")
            if image_url is not None:
                item.image_url = image_url
                updated_fields.append("image_url")
            if price is not None:
                item.price = price
                updated_fields.append("price")
            if currency is not None:
                item.currency = currency
                updated_fields.append("currency")
            if priority is not None:
                item.priority = priority
                updated_fields.append("priority")
            if category is not None:
                item.category = category
                updated_fields.append("category")
            if recipient_user_id is not None:
                item.recipient_user_id = recipient_user_id
                updated_fields.append("recipient_user_id")
            if recipient_name is not None:
                item.recipient_name = recipient_name
                updated_fields.append("recipient_name")

            item.updated_at = datetime.now(UTC)
            after_update = (
                item.title,
                item.description,
                item.link,
                item.image_url,
                item.price,
                item.currency,
                item.quantity,
                item.priority,
                item.category,
                item.recipient_user_id,
                item.recipient_name,
            )
            if before_update != after_update:
                overbooked_givers: frozenset[int] = frozenset()
                if (
                    quantity_delta < 0
                    and item.received_quantity + item.reserved_quantity > item.quantity
                ):
                    givers = sorted(
                        {
                            reservation.user_id
                            for reservation in item.reservations
                            if reservation.status
                            in (ReservationStatus.ACTIVE, ReservationStatus.PURCHASED)
                            and not WishlistAccessPolicy.is_recipient_id(reservation.user_id, item)
                        }
                    )
                    if givers:
                        overbooked_givers = frozenset(givers)
                        self._new_shared_item_events.append(
                            SharedEvent(
                                "item_quantity_overbooked",
                                wl.id,
                                item.id,
                                secrets.token_hex(16),
                                tuple(givers),
                                frozenset(member.user_id for member in wl.members),
                            )
                        )
                    logger.warning(
                        "Item %s entered overbooked state (new_qty=%s, delta=%s, notices=%s)",
                        item.id,
                        item.quantity,
                        quantity_delta,
                        len(overbooked_givers),
                        extra={
                            "event": "item_quantity_overbooked",
                            "item_id": item.id,
                            "wishlist_id": wl.id,
                            "actor_id": actor.telegram_id,
                            "quantity": item.quantity,
                            "quantity_delta": quantity_delta,
                            "notified_givers_count": len(overbooked_givers),
                        },
                    )
                self._record_shared_event(
                    "item_updated",
                    wl,
                    item,
                    actor.telegram_id,
                    exclude_recipients=overbooked_givers,
                )
            logger.info(
                "Item %s updated by actor %s (delta=%s, new_qty=%s)",
                item.id,
                actor.telegram_id,
                quantity_delta,
                item.quantity,
                extra={
                    "event": "item_updated",
                    "item_id": item.id,
                    "wishlist_id": wl.id,
                    "actor_id": actor.telegram_id,
                    "updated_fields": sorted(updated_fields),
                    "quantity": item.quantity,
                    "quantity_delta": quantity_delta,
                },
            )
            return item

    async def get_wish_item(
        self,
        wishlist_id: int,
        item_id: int,
        actor: AuthenticatedUser | None = None,
    ) -> WishItemRecipientViewDTO | WishItemGifterViewDTO:
        """Retrieve a single wish item projected according to caller's context."""
        wl = await self.get_wishlist_by_id(wishlist_id)
        if item_id not in self._items:
            raise ItemNotFoundError(f"Item {item_id} not found")
        item = self._items[item_id]
        if item.wishlist_id != wl.id:
            raise ItemNotFoundError(f"Item {item_id} not found in wishlist {wishlist_id}")
        return project_wish_item(item, actor)

    async def list_wish_items(
        self,
        wishlist_id: int,
        actor: AuthenticatedUser | None = None,
        include_archived: bool = False,
    ) -> list[WishItemRecipientViewDTO | WishItemGifterViewDTO]:
        """List wishlist items projected according to caller's context and archive filter."""
        wl = await self.get_wishlist_by_id(wishlist_id)
        filtered = [
            item
            for item in wl.items
            if (not item.is_fully_received if include_archived else item.is_active)
        ]
        sorted_items = sorted(filtered, key=lambda it: (it.display_order, it.id))
        return [project_wish_item(it, actor) for it in sorted_items]

    async def list_gifted_items(
        self,
        wishlist_id: int,
        actor: AuthenticatedUser | None,
    ) -> list[GiftedItemDTO]:
        """List received wishes with dated receipts for the list authors only.

        Raises:
            WishlistNotFoundError: Unknown list.
            WishlistDeletedError: The list is deleted.
            PermissionDeniedError: The actor is not a member of the list.
        """
        wl = await self.get_wishlist_by_id(wishlist_id)
        ctx = WishlistAccessPolicy.resolve_context(actor, wl)
        if not WishlistAccessPolicy.can_view_gifted(ctx, wl):
            raise PermissionDeniedError("Only list authors can read the gifted wishes")
        gifted = [item for item in wl.items if item.is_gifted]
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
        if wl.status == WishlistStatus.ARCHIVED:
            raise WishlistArchivedError(f"Wishlist {wishlist_id} is archived")
        if wl.status == WishlistStatus.DELETED:
            raise WishlistDeletedError(f"Wishlist {wishlist_id} is deleted")

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

        active_ids_set = {it.id for it in active_items}
        if set(item_ids) != active_ids_set:
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

        item_map = {it.id: it for it in active_items}
        for order, it_id in enumerate(item_ids):
            item = item_map[it_id]
            item.display_order = order
            item.updated_at = datetime.now(UTC)

        wl.items.sort(key=lambda it: (it.display_order, it.id))
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

    @staticmethod
    def _log_archive_refused(wishlist_id: int, item_id: int, actor: AuthenticatedUser) -> None:
        """WARNING for an archive or restore refused because nothing remains to receive."""
        logger.warning(
            "Archive or restore refused: nothing remains",
            extra={
                "event": "wish_archive_refused",
                "wishlist_id": wishlist_id,
                "item_id": item_id,
                "actor_id": actor.telegram_id,
                "reason": "nothing_remaining",
            },
        )

    @staticmethod
    def _log_partial_move(
        event: str, verb: str, wishlist_id: int, item: WishItem, actor: AuthenticatedUser
    ) -> None:
        """INFO for archiving or restoring a partly received wish; silent for an untouched one."""
        if item.received_quantity <= 0:
            return
        logger.info(
            "Partly received wish %s",
            verb,
            extra={
                "event": event,
                "wishlist_id": wishlist_id,
                "item_id": item.id,
                "actor_id": actor.telegram_id,
                "received_quantity": item.received_quantity,
                "total_quantity": item.quantity,
            },
        )

    async def archive_wish_item(
        self,
        wishlist_id: int,
        item_id: int,
        actor: AuthenticatedUser,
        warn_on_delete_reserved: bool | None = None,
    ) -> WishItemRecipientViewDTO | WishItemGifterViewDTO:
        """Safely archive a wish item, preserving reservations and blocking new ones."""
        wl = await self.get_wishlist_by_id(wishlist_id)
        if wl.status == WishlistStatus.ARCHIVED:
            raise WishlistArchivedError(f"Wishlist {wishlist_id} is archived")
        if wl.status == WishlistStatus.DELETED:
            raise WishlistDeletedError(f"Wishlist {wishlist_id} is deleted")

        ctx = WishlistAccessPolicy.resolve_context(actor, wl)
        if not WishlistAccessPolicy.can_add_or_edit_item(ctx, wl):
            logger.warning(
                "Actor %s denied permission to archive item %s in wishlist %s",
                actor.telegram_id,
                item_id,
                wl.id,
                extra={
                    "event": "item_access_denied",
                    "actor_id": actor.telegram_id,
                    "wishlist_id": wl.id,
                    "item_id": item_id,
                    "action": "archive_item",
                    "role": ctx.role.value if ctx.role else None,
                },
            )
            raise PermissionDeniedError("Actor cannot archive items in this wishlist")

        if item_id not in self._items:
            raise ItemNotFoundError(f"Item {item_id} not found")
        item = self._items[item_id]
        if item.wishlist_id != wl.id:
            raise ItemNotFoundError(f"Item {item_id} not found in wishlist {wishlist_id}")
        if item.is_fully_received:
            self._log_archive_refused(wl.id, item.id, actor)
            raise NothingRemainingError()

        if warn_on_delete_reserved is not None:
            wl.warn_on_delete_reserved = warn_on_delete_reserved
            wl.updated_at = datetime.now(UTC)

        was_archived = item.is_archived
        item.is_archived = True
        if not was_archived:
            self._record_shared_event("item_archived", wl, item, actor.telegram_id)
        item.updated_at = datetime.now(UTC)
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
        self._log_partial_move("wish_archived_partial", "archived", wl.id, item, actor)
        return project_wish_item(item, actor)

    async def restore_wish_item(
        self,
        wishlist_id: int,
        item_id: int,
        actor: AuthenticatedUser,
    ) -> WishItemRecipientViewDTO | WishItemGifterViewDTO:
        """Restore an archived wish item to the end of the active display order."""
        wl = await self.get_wishlist_by_id(wishlist_id)
        if wl.status == WishlistStatus.ARCHIVED:
            raise WishlistArchivedError(f"Wishlist {wishlist_id} is archived")
        if wl.status == WishlistStatus.DELETED:
            raise WishlistDeletedError(f"Wishlist {wishlist_id} is deleted")

        ctx = WishlistAccessPolicy.resolve_context(actor, wl)
        if not WishlistAccessPolicy.can_add_or_edit_item(ctx, wl):
            logger.warning(
                "Actor %s denied permission to restore item %s in wishlist %s",
                actor.telegram_id,
                item_id,
                wl.id,
                extra={
                    "event": "item_access_denied",
                    "actor_id": actor.telegram_id,
                    "wishlist_id": wl.id,
                    "item_id": item_id,
                    "action": "restore_item",
                    "role": ctx.role.value if ctx.role else None,
                },
            )
            raise PermissionDeniedError("Actor cannot restore items in this wishlist")

        if item_id not in self._items:
            raise ItemNotFoundError(f"Item {item_id} not found")
        item = self._items[item_id]
        if item.wishlist_id != wl.id:
            raise ItemNotFoundError(f"Item {item_id} not found in wishlist {wishlist_id}")
        if item.remaining_quantity == 0:
            self._log_archive_refused(wl.id, item.id, actor)
            raise NothingRemainingError()

        was_archived = item.is_archived
        item.is_archived = False
        if was_archived:
            self._record_shared_event("item_restored", wl, item, actor.telegram_id)
        active_orders = [it.display_order for it in wl.items if it.is_active and it.id != item.id]
        item.display_order = max(active_orders, default=-1) + 1
        item.updated_at = datetime.now(UTC)
        wl.items.sort(key=lambda it: (it.display_order, it.id))
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
        self._log_partial_move("wish_restored_partial", "restored", wl.id, item, actor)
        return project_wish_item(item, actor)

    async def create_reservation(
        self,
        item_id: int,
        user: AuthenticatedUser | None,
        quantity: int = 1,
        *,
        wishlist_id: int | None = None,
    ) -> Reservation:
        """Reserve quantity units of an item on behalf of a gifter."""
        if quantity < 1:
            raise ValueError(RESERVATION_QUANTITY_MIN_ERROR)
        if user is None:
            raise PermissionDeniedError("Authentication required")
        gifter_id = user.telegram_id
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
            if wishlist_id is not None and item.wishlist_id != wishlist_id:
                raise ItemNotFoundError(f"Item {item_id} not found")
            wl = self._require_item_wishlist(item)
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

            ctx = WishlistAccessPolicy.resolve_context(user, wl)
            if not WishlistAccessPolicy.can_reserve_item(user, ctx, item):
                logger.warning(
                    "Self-reservation blocked: recipient %s cannot reserve item %s",
                    gifter_id,
                    item_id,
                    extra={
                        "event": "self_reservation_blocked",
                        "wishlist_id": wl.id,
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
                        "wishlist_id": wl.id,
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
            self._register_reservation(res)
            self._record_reservation_confirmation(item, gifter_id)
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
        *,
        wishlist_id: int | None = None,
        item_id: int | None = None,
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
        self._guard_reservation_mutation(
            res,
            user,
            wishlist_id=wishlist_id,
            item_id=item_id,
        )
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
            if res.wish_item is not None:
                self._record_reservation_confirmation(res.wish_item, user.telegram_id)

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
        *,
        wishlist_id: int | None = None,
        item_id: int | None = None,
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
        self._guard_reservation_mutation(
            res,
            user,
            wishlist_id=wishlist_id,
            item_id=item_id,
        )
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
            if res.wish_item is not None:
                self._record_reservation_confirmation(res.wish_item, user.telegram_id)

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
        *,
        wishlist_id: int | None = None,
        item_id: int | None = None,
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
        self._guard_reservation_mutation(
            res,
            user,
            wishlist_id=wishlist_id,
            item_id=item_id,
        )
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
            if res.wish_item is not None:
                self._record_reservation_confirmation(res.wish_item, user.telegram_id)

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
        *,
        wishlist_id: int | None = None,
        item_id: int | None = None,
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
        self._guard_reservation_mutation(
            res,
            user,
            wishlist_id=wishlist_id,
            item_id=item_id,
        )
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
            raise ValueError(RESERVATION_QUANTITY_MIN_ERROR)

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
            if old_quantity != new_quantity:
                self._record_reservation_confirmation(item, user.telegram_id)

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

    @staticmethod
    def _cabinet_recipient_name(item: WishItem, wishlist: Wishlist | None) -> str:
        """Name who the wish is for, without another gifter.

        A personal list names the owner. A collaborative list names the
        designated member, or the display name when nobody is designated.
        """
        if wishlist is None:
            return ""
        owner_name = wishlist.owner_name.strip()
        if not wishlist.is_collaborative:
            if owner_name:
                return owner_name
            return f"Участник #{wishlist.owner_id}"
        designated = item.recipient_user_id
        if designated is not None:
            if designated == wishlist.owner_id and owner_name:
                return owner_name
            return f"Участник #{designated}"
        return (item.recipient_name or "").strip()

    def _register_reservation(self, reservation: Reservation) -> None:
        """Keep the authoritative reservation and its ordered user index in sync."""
        previous = self._reservations.get(reservation.id)
        if previous is not None and previous.user_id != reservation.user_id:
            raise ValueError("A reservation cannot change its giver")
        self._reservations[reservation.id] = reservation
        self._reservations_by_user.setdefault(reservation.user_id, {})[reservation.id] = None

    def _remove_reservation(self, reservation_id: int) -> None:
        """Remove a reservation and its derived index membership."""
        reservation = self._reservations.pop(reservation_id)
        bucket = self._reservations_by_user[reservation.user_id]
        del bucket[reservation_id]
        if not bucket:
            del self._reservations_by_user[reservation.user_id]

    def _user_reservations(self, user_id: int) -> list[Reservation]:
        return [self._reservations[rid] for rid in self._reservations_by_user.get(user_id, {})]

    async def get_user_reservations(
        self,
        user_id: int,
    ) -> list[MyReservationItemDTO]:
        """Fetch all active and purchased reservations for a gifter."""
        results: list[MyReservationItemDTO] = []
        for res in self._user_reservations(user_id):
            if res.status in (
                ReservationStatus.ACTIVE,
                ReservationStatus.PURCHASED,
            ):
                item = self._items.get(res.wish_item_id)
                if item is None:
                    continue
                wl = item.wishlist
                results.append(
                    MyReservationItemDTO(
                        reservation_id=res.id,
                        wish_item_id=item.id,
                        wishlist_id=item.wishlist_id,
                        wishlist_title=wl.title if wl else "",
                        recipient_name=self._cabinet_recipient_name(item, wl),
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
                        is_fully_received=item.is_fully_received,
                        is_wishlist_archived=(
                            wl.status == WishlistStatus.ARCHIVED if wl else False
                        ),
                        created_at=res.created_at,
                        updated_at=res.updated_at,
                        change_ceiling=res.quantity + item.available_quantity,
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
            for res in self._user_reservations(user_id)
            if res.status in (ReservationStatus.ACTIVE, ReservationStatus.PURCHASED)
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
        *,
        wishlist_id: int | None = None,
    ) -> WishItem:
        """Record a partial or full receipt of a gift by a list author.

        Guards run in a fixed order, membership first so a non-author learns nothing about the
        list or wish state. Effects are the counter, one ``ReceiptRecord`` queued for the store
        and the notice drafts; the store persists all of them in the same transaction.

        Raises:
            ItemNotFoundError: Unknown wish, or ``wishlist_id`` does not match.
            PermissionDeniedError: The actor is not a list member.
            WishlistDeletedError: The list is deleted.
            WishlistArchivedError: The list is archived.
            WishArchivedError: The wish is archived.
            QuantityInvalidError: ``received_quantity`` is below one.
            NothingRemainingError: The wish is already fully received.
            QuantityAboveRemainingError: ``received_quantity`` exceeds what remains.
        """
        item = self._items.get(item_id)
        if item is None or (wishlist_id is not None and item.wishlist_id != wishlist_id):
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

        wl = self._require_item_wishlist(item)
        ctx = WishlistAccessPolicy.resolve_context(actor, wl)
        if not ctx.is_member:
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
        if wl.status == WishlistStatus.DELETED:
            raise WishlistDeletedError(f"Wishlist {wl.id} is deleted")
        if wl.status == WishlistStatus.ARCHIVED:
            raise WishlistArchivedError(f"Wishlist {wl.id} is archived")

        if item.is_archived:
            raise WishArchivedError("The wish is archived")
        if received_quantity < 1:
            raise QuantityInvalidError()

        async with self._concurrency_coordinator.acquire(item_id):
            remaining = item.remaining_quantity
            if remaining == 0:
                raise NothingRemainingError()
            if received_quantity > remaining:
                logger.warning(
                    "Fulfillment quantity exceeds the remaining quantity for item %s",
                    item_id,
                    extra={
                        "event": "fulfillment_quantity_exceeded",
                        "item_id": item_id,
                        "wishlist_id": wl.id,
                        "user_id": actor.telegram_id,
                        "received_quantity": received_quantity,
                        "remaining_unfulfilled": remaining,
                    },
                )
                raise QuantityAboveRemainingError(remaining)
            now = datetime.now(UTC)
            item.received_quantity += received_quantity
            item.updated_at = now
            receipt = ReceiptRecord(
                wish_item_id=item.id, quantity=received_quantity, received_at=now
            )
            item.receipts.append(receipt)
            self._new_receipts.append(receipt)
            self._draft_receipt_notices(item, receipt)

        self._emit_or_defer_commit_log(
            logging.INFO,
            "Item %s fulfillment recorded: %s units by user %s",
            item_id,
            received_quantity,
            actor.telegram_id,
            extra={
                "event": "item_fulfilled",
                "wishlist_id": wl.id,
                "item_id": item.id,
                "user_id": actor.telegram_id,
                "actor_id": actor.telegram_id,
                "quantity": received_quantity,
                "received_quantity": item.received_quantity,
                "total_quantity": item.quantity,
                "fully_received": item.is_fully_received,
            },
        )
        return item

    def _validate_receipt_mutation_access(
        self,
        item_id: int,
        actor: AuthenticatedUser,
        wishlist_id: int | None,
        action: str,
    ) -> WishItem:
        """Validate item existence, list membership, and active list status for receipt edits."""
        item = self._items.get(item_id)
        if item is None or (wishlist_id is not None and item.wishlist_id != wishlist_id):
            raise ItemNotFoundError(f"Item {item_id} not found")
        wl = self._require_item_wishlist(item)
        ctx = WishlistAccessPolicy.resolve_context(actor, wl)
        if not ctx.is_member:
            logger.warning(
                "Actor %s denied permission to %s item %s in wishlist %s",
                actor.telegram_id,
                action,
                item_id,
                wl.id,
                extra={
                    "event": "access_denied",
                    "actor_id": actor.telegram_id,
                    "user_id": actor.telegram_id,
                    "wishlist_id": wl.id,
                    "item_id": item_id,
                    "action": action,
                },
            )
            raise PermissionDeniedError("Actor cannot modify receipts in this wishlist")
        if wl.status == WishlistStatus.DELETED:
            raise WishlistDeletedError(f"Wishlist {wl.id} is deleted")
        if wl.status == WishlistStatus.ARCHIVED:
            raise WishlistArchivedError(f"Wishlist {wl.id} is archived")
        return item

    async def cancel_item_receipt(
        self,
        item_id: int,
        receipt_id: int,
        actor: AuthenticatedUser,
        *,
        wishlist_id: int | None = None,
    ) -> WishItem:
        """Cancel (undo) a single receipt record on a wish in an active list.

        Raises:
            ItemNotFoundError: Unknown wish, or ``wishlist_id`` does not match.
            PermissionDeniedError: The actor is not a list member.
            WishlistDeletedError: The list is deleted.
            WishlistArchivedError: The list is archived.
            ReceiptNotFoundError: ``receipt_id`` does not exist on this wish.
        """
        item = self._validate_receipt_mutation_access(
            item_id, actor, wishlist_id, "cancel_item_receipt"
        )
        async with self._concurrency_coordinator.acquire(item_id):
            receipt = next((r for r in item.receipts if r.id == receipt_id), None)
            if receipt is None:
                raise ReceiptNotFoundError(f"Receipt {receipt_id} not found for item {item_id}")
            item.receipts.remove(receipt)
            item.received_quantity = max(0, item.received_quantity - receipt.quantity)
            item.updated_at = datetime.now(UTC)
            self._deleted_receipt_ids.append(receipt.id)
            self._record_receipt_change_event("receipt_reverted", item)

        wl = item.wishlist
        logger.info(
            "Receipt %s cancelled on item %s by user %s",
            receipt_id,
            item_id,
            actor.telegram_id,
            extra={
                "event": "receipt_cancelled",
                "wishlist_id": wl.id if wl else None,
                "item_id": item.id,
                "receipt_id": receipt_id,
                "user_id": actor.telegram_id,
                "actor_id": actor.telegram_id,
                "received_quantity": item.received_quantity,
                "total_quantity": item.quantity,
            },
        )
        return item

    async def correct_item_receipt(
        self,
        item_id: int,
        receipt_id: int,
        actor: AuthenticatedUser,
        new_quantity: int,
        *,
        wishlist_id: int | None = None,
    ) -> WishItem:
        """Correct the quantity of an existing receipt record, preserving its original date.

        Raises:
            ItemNotFoundError: Unknown wish, or ``wishlist_id`` does not match.
            PermissionDeniedError: The actor is not a list member.
            WishlistDeletedError: The list is deleted.
            WishlistArchivedError: The list is archived.
            QuantityInvalidError: ``new_quantity`` is below one.
            ReceiptNotFoundError: ``receipt_id`` does not exist on this wish.
            QuantityAboveRemainingError: ``new_quantity`` would exceed requested quantity.
        """
        item = self._validate_receipt_mutation_access(
            item_id, actor, wishlist_id, "correct_item_receipt"
        )
        if new_quantity < 1:
            raise QuantityInvalidError()

        async with self._concurrency_coordinator.acquire(item_id):
            receipt = next((r for r in item.receipts if r.id == receipt_id), None)
            if receipt is None:
                raise ReceiptNotFoundError(f"Receipt {receipt_id} not found for item {item_id}")
            max_allowed = receipt.quantity + item.remaining_quantity
            if new_quantity > max_allowed:
                raise QuantityAboveRemainingError(max_allowed)
            if new_quantity == receipt.quantity:
                return item
            old_quantity = receipt.quantity
            receipt.quantity = new_quantity
            item.received_quantity = max(0, item.received_quantity - old_quantity + new_quantity)
            item.updated_at = datetime.now(UTC)
            self._updated_receipts.append(receipt)
            kind = "receipt_increased" if new_quantity > old_quantity else "receipt_reverted"
            self._record_receipt_change_event(kind, item)

        wl = item.wishlist
        logger.info(
            "Receipt %s corrected on item %s from %s to %s by user %s",
            receipt_id,
            item_id,
            old_quantity,
            new_quantity,
            actor.telegram_id,
            extra={
                "event": "receipt_corrected",
                "wishlist_id": wl.id if wl else None,
                "item_id": item.id,
                "receipt_id": receipt_id,
                "user_id": actor.telegram_id,
                "actor_id": actor.telegram_id,
                "old_quantity": old_quantity,
                "new_quantity": new_quantity,
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
        self._record_shared_event("membership_changed", wl, None, user.telegram_id)
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
# the same transaction boundary as HTTP. WishlistService.in_memory() remains available
# as an explicitly in-memory test implementation.
for _method_name, _method in tuple(vars(WishlistService).items()):
    if not _method_name.startswith("_") and iscoroutinefunction(_method):
        setattr(WishlistService, _method_name, _transactional(_method))
