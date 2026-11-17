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


class ReservationNotFoundError(ReservationError):
    """Raised when requested reservation is not found."""


class CannotReduceQuantityBelowReservedError(WishlistError):
    """Raised when attempting to reduce desired quantity below active reserved + fulfilled units."""


class InsufficientQuantityError(ReservationError):
    """Raised when requested reservation quantity exceeds available quantity."""


class InventoryBusyError(WishlistError):
    """Raised when a wish is busy and the inventory attempt changed nothing."""

    def __init__(
        self,
        message: str = "The wish was busy and the attempt changed nothing",
    ) -> None:
        super().__init__(message)


class WishRefusalError(WishlistError):
    """Base of the closed set of receipt refusals; ``reason`` is the stable machine code."""

    reason = ""


class QuantityInvalidError(WishRefusalError, ValueError):
    """Raised when a received quantity is below one."""

    reason = "quantity_invalid"

    def __init__(self, message: str = "Quantity must be a positive whole number") -> None:
        super().__init__(message)


class QuantityAboveRemainingError(WishRefusalError, ValueError):
    """Raised when a received quantity exceeds what remains to be received."""

    reason = "quantity_above_remaining"

    def __init__(
        self, remaining_quantity: int, message: str = "Quantity is above the remaining quantity"
    ) -> None:
        super().__init__(message)
        self.remaining_quantity = remaining_quantity


class NothingRemainingError(WishRefusalError):
    """Raised when a wish is fully received and nothing is left to receive or restore."""

    reason = "nothing_remaining"

    def __init__(self, message: str = "Nothing remains to receive") -> None:
        super().__init__(message)
        self.remaining_quantity = 0


class WishArchivedError(WishRefusalError):
    """Raised when a receipt is recorded on an archived wish."""

    reason = "wish_archived"

    def __init__(self, message: str = "The wish is archived") -> None:
        super().__init__(message)


class InvalidIdempotencyKeyError(WishlistError, ValueError):
    """Raised when a client-supplied Idempotency-Key header is empty or malformed."""

    def __init__(
        self,
        message: str = "Idempotency-Key must be 1..128 characters matching [A-Za-z0-9._:-]",
    ) -> None:
        super().__init__(message)


class IdempotencyConflictError(WishlistError):
    """Raised when an Idempotency-Key is reused with different operation or payload."""

    def __init__(
        self,
        message: str = "Idempotency-Key was already used with a different request payload",
    ) -> None:
        super().__init__(message)
