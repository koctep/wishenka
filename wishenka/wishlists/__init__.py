"""Wishlists domain package providing roles, permissions, lifecycle, and projections.

Exports stay available on the package, and they load on first use. Importing a
submodule such as ``retention`` must not pull ``Settings`` back through this
package while ``config`` is still initializing.
"""

from __future__ import annotations

import importlib
from typing import Any

__all__ = [
    "CannotReduceQuantityBelowReservedError",
    "InsufficientQuantityError",
    "InvalidInviteTokenError",
    "InventoryBusyError",
    "ItemConcurrencyCoordinator",
    "ItemNotFoundError",
    "MyReservationItemDTO",
    "PermissionDeniedError",
    "Reservation",
    "ReservationError",
    "ReservationNotFoundError",
    "ReservationStatus",
    "SelfReservationError",
    "UserReservationsSummaryDTO",
    "UserWishlistContext",
    "WishItem",
    "WishItemGifterViewDTO",
    "WishItemRecipientViewDTO",
    "WishItemViewDTO",
    "Wishlist",
    "WishlistAccessPolicy",
    "WishlistArchivedError",
    "WishlistDeletedError",
    "WishlistDetailViewDTO",
    "WishlistError",
    "WishlistFormat",
    "WishlistMember",
    "WishlistNotFoundError",
    "WishlistRole",
    "WishlistService",
    "WishlistStatus",
    "WishlistTimeType",
    "WishlistViewDTO",
]

_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "CannotReduceQuantityBelowReservedError": (
        "wishenka.wishlists.exceptions",
        "CannotReduceQuantityBelowReservedError",
    ),
    "InsufficientQuantityError": ("wishenka.wishlists.exceptions", "InsufficientQuantityError"),
    "InvalidInviteTokenError": ("wishenka.wishlists.exceptions", "InvalidInviteTokenError"),
    "InventoryBusyError": ("wishenka.wishlists.exceptions", "InventoryBusyError"),
    "ItemConcurrencyCoordinator": (
        "wishenka.wishlists.concurrency",
        "ItemConcurrencyCoordinator",
    ),
    "ItemNotFoundError": ("wishenka.wishlists.exceptions", "ItemNotFoundError"),
    "MyReservationItemDTO": ("wishenka.wishlists.schemas", "MyReservationItemDTO"),
    "PermissionDeniedError": ("wishenka.wishlists.exceptions", "PermissionDeniedError"),
    "Reservation": ("wishenka.wishlists.models", "Reservation"),
    "ReservationError": ("wishenka.wishlists.exceptions", "ReservationError"),
    "ReservationNotFoundError": ("wishenka.wishlists.exceptions", "ReservationNotFoundError"),
    "ReservationStatus": ("wishenka.wishlists.models", "ReservationStatus"),
    "SelfReservationError": ("wishenka.wishlists.exceptions", "SelfReservationError"),
    "UserReservationsSummaryDTO": ("wishenka.wishlists.schemas", "UserReservationsSummaryDTO"),
    "UserWishlistContext": ("wishenka.wishlists.policy", "UserWishlistContext"),
    "WishItem": ("wishenka.wishlists.models", "WishItem"),
    "WishItemGifterViewDTO": ("wishenka.wishlists.schemas", "WishItemGifterViewDTO"),
    "WishItemRecipientViewDTO": ("wishenka.wishlists.schemas", "WishItemRecipientViewDTO"),
    "WishItemViewDTO": ("wishenka.wishlists.schemas", "WishItemViewDTO"),
    "Wishlist": ("wishenka.wishlists.models", "Wishlist"),
    "WishlistAccessPolicy": ("wishenka.wishlists.policy", "WishlistAccessPolicy"),
    "WishlistArchivedError": ("wishenka.wishlists.exceptions", "WishlistArchivedError"),
    "WishlistDeletedError": ("wishenka.wishlists.exceptions", "WishlistDeletedError"),
    "WishlistDetailViewDTO": ("wishenka.wishlists.schemas", "WishlistDetailViewDTO"),
    "WishlistError": ("wishenka.wishlists.exceptions", "WishlistError"),
    "WishlistFormat": ("wishenka.wishlists.models", "WishlistFormat"),
    "WishlistMember": ("wishenka.wishlists.models", "WishlistMember"),
    "WishlistNotFoundError": ("wishenka.wishlists.exceptions", "WishlistNotFoundError"),
    "WishlistRole": ("wishenka.wishlists.models", "WishlistRole"),
    "WishlistService": ("wishenka.wishlists.service", "WishlistService"),
    "WishlistStatus": ("wishenka.wishlists.models", "WishlistStatus"),
    "WishlistTimeType": ("wishenka.wishlists.models", "WishlistTimeType"),
    "WishlistViewDTO": ("wishenka.wishlists.schemas", "WishlistViewDTO"),
}


def __getattr__(name: str) -> Any:
    """Load a public name from its module the first time it is used."""
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr = target
    value = getattr(importlib.import_module(module_name), attr)
    globals()[name] = value
    return value
