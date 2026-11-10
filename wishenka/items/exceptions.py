"""Domain exceptions for items, input parsing, and piece accounting."""

from wishenka.wishlists.exceptions import (
    CannotReduceQuantityBelowReservedError,
    InsufficientQuantityError,
    WishlistError,
)


class ItemError(WishlistError):
    """Base exception for all item domain errors."""


class InvalidItemDataError(ItemError):
    """Raised when item input or update data fails validation."""


__all__ = [
    "CannotReduceQuantityBelowReservedError",
    "InsufficientQuantityError",
    "InvalidItemDataError",
    "ItemError",
]
