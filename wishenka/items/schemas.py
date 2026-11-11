"""Pydantic v2 schemas and DTOs for item preview, creation, and update."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from wishenka.items.models import InputType, ItemPriority


class ItemPreviewDTO(BaseModel):
    """Rich or fallback preview extracted from user input."""

    model_config = ConfigDict(frozen=True)

    input_type: InputType = InputType.PLAIN_TEXT
    url: str | None = None
    title: str | None = None
    description: str | None = None
    image_url: str | None = None
    price: int | None = None
    currency: str = "RUB"
    store_name: str | None = None
    store_icon_url: str | None = None
    is_fallback: bool = False
    fallback_reason: str | None = None


class CreateItemDTO(BaseModel):
    """Payload for creating a wish item with multi-quantity and priority."""

    model_config = ConfigDict(frozen=True)

    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    link: str | None = Field(default=None, max_length=2048)
    image_url: str | None = Field(default=None, max_length=2048)
    price: int | None = Field(default=None, ge=0, le=999_999_999)
    currency: str = Field(default="RUB", max_length=10)
    quantity: int = Field(default=1, ge=1, le=1000)
    priority: ItemPriority = Field(default=ItemPriority.MEDIUM)
    category: str | None = Field(default=None, max_length=50)
    recipient_user_id: int | None = None
    recipient_name: str | None = Field(default=None, max_length=100)

    @field_validator("title")
    @classmethod
    def validate_title_not_whitespace(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Title cannot be empty or whitespace only")
        return v


class UpdateItemDTO(BaseModel):
    """Payload for updating wish item attributes with multi-quantity constraints."""

    model_config = ConfigDict(frozen=True)

    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    link: str | None = Field(default=None, max_length=2048)
    image_url: str | None = Field(default=None, max_length=2048)
    price: int | None = Field(default=None, ge=0, le=999_999_999)
    currency: str | None = Field(default=None, max_length=10)
    quantity: int | None = Field(default=None, ge=1, le=1000)
    priority: ItemPriority | None = None
    category: str | None = Field(default=None, max_length=50)
    recipient_user_id: int | None = None
    recipient_name: str | None = Field(default=None, max_length=100)

    @field_validator("title")
    @classmethod
    def validate_title_not_whitespace(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("Title cannot be empty or whitespace only")
        return v


class ReorderItemsDTO(BaseModel):
    """Payload for updating item display order in a wishlist."""

    model_config = ConfigDict(frozen=True)

    item_ids: list[int] = Field(..., min_length=1)


__all__ = [
    "CreateItemDTO",
    "ItemPreviewDTO",
    "ReorderItemsDTO",
    "UpdateItemDTO",
]
