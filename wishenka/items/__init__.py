"""Items domain package: input classification, metadata parsing, and preview service."""

from wishenka.items.classifier import UniversalInputClassifier
from wishenka.items.exceptions import (
    CannotReduceQuantityBelowReservedError,
    InsufficientQuantityError,
    InvalidItemDataError,
    InvalidUrlSchemeError,
    ItemError,
    ItemParsingError,
    ResponseBodyTooLargeError,
    SSRFBlockedError,
    SSRFError,
)
from wishenka.items.fetcher import (
    DEFAULT_HEADERS,
    DEFAULT_TIMEOUT,
    UrlMetadataService,
)
from wishenka.items.models import (
    ExtractedMetadata,
    InputClassificationResult,
    InputType,
    ItemPriority,
)
from wishenka.items.parser import (
    HtmlMetadataExtractor,
    clean_title,
    derive_store_name,
    normalize_currency,
    parse_price,
)
from wishenka.items.schemas import (
    CreateItemDTO,
    ItemPreviewDTO,
    UpdateItemDTO,
)
from wishenka.items.service import ItemPreviewService
from wishenka.items.ssrf import (
    ALLOWED_SCHEMES,
    MAX_RESPONSE_BYTES,
    SSRFSafeTransport,
    is_ip_safe,
    resolve_and_validate_host,
)

__all__ = [
    "ALLOWED_SCHEMES",
    "CannotReduceQuantityBelowReservedError",
    "CreateItemDTO",
    "DEFAULT_HEADERS",
    "DEFAULT_TIMEOUT",
    "ExtractedMetadata",
    "HtmlMetadataExtractor",
    "InputClassificationResult",
    "InputType",
    "InsufficientQuantityError",
    "InvalidItemDataError",
    "InvalidUrlSchemeError",
    "ItemError",
    "ItemParsingError",
    "ItemPreviewDTO",
    "ItemPreviewService",
    "ItemPriority",
    "MAX_RESPONSE_BYTES",
    "ResponseBodyTooLargeError",
    "SSRFBlockedError",
    "SSRFError",
    "SSRFSafeTransport",
    "UniversalInputClassifier",
    "UpdateItemDTO",
    "UrlMetadataService",
    "clean_title",
    "derive_store_name",
    "is_ip_safe",
    "normalize_currency",
    "parse_price",
    "resolve_and_validate_host",
]
