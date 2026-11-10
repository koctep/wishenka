"""Domain exceptions for wishlists, roles, and reservations."""


class WishlistError(Exception):
    """Base exception for all wishlist domain errors."""


class PermissionDeniedError(WishlistError):
    """Raised when actor lacks required permissions for an operation."""


class WishlistNotFoundError(WishlistError):
    """Raised when requested wishlist is not found or has been revoked."""


class WishlistArchivedError(WishlistError):
    """Raised when attempting mutation or reservation on an archived wishlist."""


class WishlistDeletedError(WishlistError):
    """Raised when attempting access or mutation on a deleted wishlist."""


class InvalidInviteTokenError(WishlistError):
    """Raised when invite token is non-existent, revoked, or expired."""


class SelfReservationError(WishlistError):
    """Raised when a recipient attempts to reserve an item designated for themselves."""


class ItemNotFoundError(WishlistError):
    """Raised when a wish item is not found."""


class ReservationError(WishlistError):
    """Base exception for reservation failures."""


class CannotReduceQuantityBelowReservedError(WishlistError):
    """Raised when attempting to reduce desired quantity below active reserved + fulfilled units."""


class InsufficientQuantityError(ReservationError):
    """Raised when requested reservation quantity exceeds available quantity."""
