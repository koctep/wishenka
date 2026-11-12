"""Pydantic schemas and DTOs with strict role-aware projections."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from wishenka.items.models import ItemPriority
from wishenka.wishlists.models import ReservationStatus, WishlistRole, WishlistStatus


class WishItemRecipientViewDTO(BaseModel):
    """Projection for the item Recipient.

    Surprise Invariant: All reservation details and booking status are completely omitted.
    """

    model_config = ConfigDict(frozen=True)

    id: int
    title: str
    description: str | None = None
    link: str | None = None
    image_url: str | None = None
    price: int | None = None
    currency: str = "RUB"
    store_name: str | None = None
    store_icon_url: str | None = None
    quantity: int = 1
    received_quantity: int = 0
    priority: ItemPriority = ItemPriority.MEDIUM
    category: str | None = None
    display_order: int = 0
    is_archived: bool = False
    recipient_user_id: int | None = None
    recipient_name: str | None = None
    is_recipient: bool = True


class WishItemGifterViewDTO(BaseModel):
    """Projection for Gifters and Non-Recipient Collaborators.

    Includes availability and caller reservation status.
    """

    model_config = ConfigDict(frozen=True)

    id: int
    title: str
    description: str | None = None
    link: str | None = None
    image_url: str | None = None
    price: int | None = None
    currency: str = "RUB"
    store_name: str | None = None
    store_icon_url: str | None = None
    quantity: int = 1
    received_quantity: int = 0
    available_quantity: int
    is_fully_reserved: bool
    is_reserved_by_me: bool
    my_reserved_quantity: int
    my_reservation_status: ReservationStatus | None = None
    my_reservation_id: int | None = None
    my_latest_reservation_quantity: int = 0
    my_occupying_reservation_count: int = 0
    priority: ItemPriority = ItemPriority.MEDIUM
    category: str | None = None
    display_order: int = 0
    is_archived: bool = False
    recipient_user_id: int | None = None
    recipient_name: str | None = None
    is_recipient: bool = False


class MyReservationItemDTO(BaseModel):
    """Record within the gifter's aggregated 'My Reservations' cabinet."""

    model_config = ConfigDict(frozen=True)

    reservation_id: int
    wish_item_id: int
    wishlist_id: int
    wishlist_title: str
    recipient_name: str
    item_title: str
    item_link: str | None = None
    item_image_url: str | None = None
    item_price: int | None = None
    currency: str = "RUB"
    reserved_quantity: int
    status: ReservationStatus
    event_title: str | None = None
    event_date: datetime | None = None
    is_item_archived: bool = False
    is_wishlist_archived: bool = False
    created_at: datetime
    updated_at: datetime


class UserReservationsSummaryDTO(BaseModel):
    """Summary badge counter for user's active commitments."""

    model_config = ConfigDict(frozen=True)

    user_id: int
    total_active_reservations: int
    total_distinct_items: int


WishItemViewDTO = WishItemRecipientViewDTO | WishItemGifterViewDTO


class ReservationQuantityDTO(BaseModel):
    """Quantity for a new promise or a change to an existing one."""

    model_config = ConfigDict(extra="forbid")

    quantity: int


class PromiseActionDTO(BaseModel):
    """The promise an action just changed, plus the caller's wish view."""

    model_config = ConfigDict(frozen=True)

    reservation_id: int
    wish_item_id: int
    quantity: int
    status: ReservationStatus
    available_quantity: int
    item: WishItemGifterViewDTO


class WishlistDetailViewDTO(BaseModel):
    """Detailed view of a wishlist tailored to caller's context and role."""

    model_config = ConfigDict(frozen=True)

    id: int
    title: str
    owner_name: str = ""
    description: str | None = None
    event_title: str | None = None
    event_date: datetime | None = None
    is_collaborative: bool = False
    warn_on_delete_reserved: bool = True
    status: WishlistStatus = WishlistStatus.ACTIVE
    user_role: WishlistRole | None = None
    can_edit: bool = False
    can_archive: bool = False
    can_delete: bool = False
    public_token: str
    invite_token: str | None = None
    items: list[WishItemRecipientViewDTO | WishItemGifterViewDTO] = Field(default_factory=list)
    archived_items: list[WishItemRecipientViewDTO] = Field(default_factory=list)


WishlistViewDTO = WishlistDetailViewDTO
