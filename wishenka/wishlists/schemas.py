"""Pydantic schemas and DTOs with strict role-aware projections."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from wishenka.items.models import ItemPriority
from wishenka.wishlists.models import WishlistRole, WishlistStatus


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
    is_archived: bool = False
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
    priority: ItemPriority = ItemPriority.MEDIUM
    category: str | None = None
    is_archived: bool = False
    recipient_name: str | None = None
    is_recipient: bool = False


WishItemViewDTO = WishItemRecipientViewDTO | WishItemGifterViewDTO


class WishlistDetailViewDTO(BaseModel):
    """Detailed view of a wishlist tailored to caller's context and role."""

    model_config = ConfigDict(frozen=True)

    id: int
    title: str
    description: str | None = None
    event_title: str | None = None
    event_date: datetime | None = None
    is_collaborative: bool = False
    status: WishlistStatus = WishlistStatus.ACTIVE
    user_role: WishlistRole | None = None
    can_edit: bool = False
    can_archive: bool = False
    can_delete: bool = False
    public_token: str
    invite_token: str | None = None
    items: list[WishItemRecipientViewDTO | WishItemGifterViewDTO] = Field(default_factory=list)


WishlistViewDTO = WishlistDetailViewDTO
