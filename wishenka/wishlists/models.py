"""Domain models, enumerations, and dataclasses for wishlists."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from wishenka.currency import DEFAULT_CURRENCY
from wishenka.items.models import ItemPriority


class WishlistRole(StrEnum):
    """Membership roles within a collaborative wishlist."""

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class WishlistStatus(StrEnum):
    """Lifecycle status of a wishlist."""

    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"


class ReservationStatus(StrEnum):
    """Lifecycle status of an item reservation."""

    ACTIVE = "active"
    PURCHASED = "purchased"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class WishlistFormat(StrEnum):
    """Participation format of a wishlist."""

    PERSONAL = "personal"
    COLLABORATIVE = "collaborative"


class WishlistTimeType(StrEnum):
    """Time regime of a wishlist."""

    ONGOING = "ongoing"
    EVENT = "event"


@dataclass
class WishlistFavorite:
    """User favorite bookmark for an accessible wishlist."""

    user_id: int
    wishlist_id: int
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class ViewHistoryEntry:
    """Record of a user viewing a wishlist in the Mini App."""

    id: int = 0
    user_id: int = 0
    wishlist_id: int = 0
    viewed_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class WishlistMember:
    """Collaborator member record within a wishlist."""

    id: int = 0
    wishlist_id: int = 0
    user_id: int = 0
    role: WishlistRole = WishlistRole.MEMBER
    joined_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    wishlist: "Wishlist | None" = None


@dataclass
class Reservation:
    """Gifter reservation record for wish item quantities."""

    id: int = 0
    wish_item_id: int = 0
    user_id: int = 0
    quantity: int = 1
    status: ReservationStatus = ReservationStatus.ACTIVE
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    wish_item: "WishItem | None" = None


@dataclass
class ReceiptRecord:
    """One receipt act of a wish: how many units arrived and when.

    The record never names a giver and never links to a reservation (Surprise Invariant).
    ``is_approximate`` marks a date back-filled from legacy data, never an exact moment.
    """

    id: int = 0
    wish_item_id: int = 0
    quantity: int = 1
    received_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    is_approximate: bool = False


@dataclass
class WishItem:
    """Individual wish item within a wishlist."""

    id: int = 0
    wishlist_id: int = 0
    title: str = ""
    description: str | None = None
    link: str | None = None
    price: int | float | None = None
    currency: str = DEFAULT_CURRENCY
    quantity: int = 1
    received_quantity: int = 0
    image_url: str | None = None
    store_name: str | None = None
    store_icon_url: str | None = None
    priority: ItemPriority = ItemPriority.MEDIUM
    category: str | None = None
    is_archived: bool = False
    display_order: int = 0
    recipient_user_id: int | None = None
    recipient_name: str | None = None
    wishlist: "Wishlist | None" = None
    reservations: list[Reservation] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    receipts: list[ReceiptRecord] = field(default_factory=list)

    @property
    def remaining_quantity(self) -> int:
        """Units the recipient has not received yet (never negative)."""
        return max(0, self.quantity - self.received_quantity)

    @property
    def is_fully_received(self) -> bool:
        """Whether every requested unit has been received."""
        return self.received_quantity >= self.quantity

    @property
    def is_gifted(self) -> bool:
        """Whether at least one unit has been received (belongs to the gifted section)."""
        return self.received_quantity > 0

    @property
    def is_active(self) -> bool:
        """Shared active predicate: neither archived nor fully received."""
        return not self.is_archived and not self.is_fully_received

    @property
    def is_in_archive(self) -> bool:
        """Archive membership: archived by hand and not fully received."""
        return self.is_archived and not self.is_fully_received

    @property
    def reserved_quantity(self) -> int:
        """Sum of reserved quantity across all active and purchased reservations."""
        return sum(
            r.quantity
            for r in self.reservations
            if r.status in (ReservationStatus.ACTIVE, ReservationStatus.PURCHASED)
        )

    @property
    def available_quantity(self) -> int:
        """Available quantity remaining to be reserved by gifters."""
        return max(0, self.quantity - self.received_quantity - self.reserved_quantity)

    @property
    def desired_quantity(self) -> int:
        """Alias for quantity."""
        return self.quantity

    @desired_quantity.setter
    def desired_quantity(self, val: int) -> None:
        self.quantity = val

    @property
    def fulfilled_quantity(self) -> int:
        """Alias for received_quantity."""
        return self.received_quantity

    @fulfilled_quantity.setter
    def fulfilled_quantity(self, val: int) -> None:
        self.received_quantity = val


@dataclass
class Wishlist:
    """Wishlist aggregate root entity."""

    id: int = 0
    owner_id: int = 0
    owner_name: str = ""
    title: str = ""
    description: str | None = None
    event_title: str | None = None
    event_date: datetime | None = None
    is_collaborative: bool = False
    warn_on_delete_reserved: bool = True
    status: WishlistStatus = WishlistStatus.ACTIVE
    public_token: str = ""
    invite_token: str = ""
    invite_token_expires_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    members: list[WishlistMember] = field(default_factory=list)
    items: list[WishItem] = field(default_factory=list)


# Re-export schemas for convenience
from wishenka.wishlists.schemas import (  # noqa: E402
    WishItemGifterViewDTO,
    WishItemRecipientViewDTO,
    WishItemViewDTO,
    WishlistDetailViewDTO,
    WishlistViewDTO,
)

__all__ = [
    "ItemPriority",
    "ReceiptRecord",
    "Reservation",
    "ReservationStatus",
    "ViewHistoryEntry",
    "WishItem",
    "WishItemGifterViewDTO",
    "WishItemRecipientViewDTO",
    "WishItemViewDTO",
    "Wishlist",
    "WishlistDetailViewDTO",
    "WishlistFavorite",
    "WishlistFormat",
    "WishlistMember",
    "WishlistRole",
    "WishlistStatus",
    "WishlistTimeType",
    "WishlistViewDTO",
]
