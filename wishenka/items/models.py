"""Domain models and data structures for item input, classification, and parsing."""

from dataclasses import dataclass
from enum import StrEnum

from wishenka.currency import DEFAULT_CURRENCY


class ItemPriority(StrEnum):
    """Priority level for wish items."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class InputType(StrEnum):
    """Classification type of raw user input."""

    PLAIN_TEXT = "plain_text"
    EXPLICIT_URL = "explicit_url"
    IMPLICIT_URL = "implicit_url"
    COMPOSITE_SHARE = "composite_share"


@dataclass
class ExtractedMetadata:
    """Rich e-commerce metadata extracted from web pages."""

    title: str | None = None
    description: str | None = None
    image_url: str | None = None
    price: int | float | None = None
    currency: str = DEFAULT_CURRENCY
    store_name: str | None = None
    store_icon_url: str | None = None
    raw_html_title: str | None = None


@dataclass
class InputClassificationResult:
    """Result of universal input text classification."""

    input_type: InputType
    normalized_url: str | None = None
    residual_text: str | None = None
    raw_input: str = ""
