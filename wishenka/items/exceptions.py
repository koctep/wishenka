"""Domain exceptions for items, input parsing, piece accounting, and network security."""

from wishenka.wishlists.exceptions import (
    CannotReduceQuantityBelowReservedError,
    InsufficientQuantityError,
    WishlistError,
)


class ItemError(WishlistError):
    """Base exception for all item domain errors."""


class InvalidItemDataError(ItemError):
    """Raised when item input or update data fails validation."""


class ItemParsingError(ItemError):
    """Base exception for item parsing, URL extraction, and network fetch limits."""


class SSRFError(ItemParsingError):
    """Base exception for SSRF validation errors and blocked destination targets."""


class SSRFBlockedError(SSRFError):
    """Raised when an outbound request targets a loopback, private, or forbidden IP/host."""

    def __init__(
        self,
        message: str = "Outbound request to private/forbidden network address blocked",
        *,
        ip_address: str | None = None,
        host: str | None = None,
        reason: str | None = None,
    ) -> None:
        super().__init__(message)
        self.ip_address = ip_address
        self.host = host
        self.reason = reason


class InvalidUrlSchemeError(SSRFError):
    """Raised when a URL scheme is not allowed (only http and https are permitted)."""

    def __init__(
        self,
        message: str = "Disallowed URL scheme; only http and https are permitted",
        *,
        scheme: str | None = None,
    ) -> None:
        super().__init__(message)
        self.scheme = scheme


class ResponseBodyTooLargeError(ItemParsingError):
    """Raised when response body exceeds the maximum permitted size limit."""

    def __init__(
        self,
        message: str = "Response body exceeds maximum allowed size limit",
        *,
        content_length: int | None = None,
        max_allowed: int | None = None,
    ) -> None:
        super().__init__(message)
        self.content_length = content_length
        self.max_allowed = max_allowed


__all__ = [
    "CannotReduceQuantityBelowReservedError",
    "InsufficientQuantityError",
    "InvalidItemDataError",
    "InvalidUrlSchemeError",
    "ItemError",
    "ItemParsingError",
    "ResponseBodyTooLargeError",
    "SSRFBlockedError",
    "SSRFError",
]
