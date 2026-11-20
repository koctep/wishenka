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


class CassetteError(ItemError):
    """Base exception for web cassette recording and replay errors."""


class CassetteMissError(CassetteError):
    """Raised when a requested HTTP interaction is missing from the cassette in REPLAY mode."""

    def __init__(
        self,
        message: str = "No matching HTTP interaction found in cassette during offline replay",
        *,
        method: str | None = None,
        uri: str | None = None,
        cassette_path: str | None = None,
    ) -> None:
        super().__init__(message)
        self.method = method
        self.uri = uri
        self.cassette_path = cassette_path


__all__ = [
    "CannotReduceQuantityBelowReservedError",
    "CassetteError",
    "CassetteMissError",
    "InsufficientQuantityError",
    "InvalidItemDataError",
    "InvalidUrlSchemeError",
    "ItemError",
    "ItemParsingError",
    "ResponseBodyTooLargeError",
    "SSRFBlockedError",
    "SSRFError",
]
