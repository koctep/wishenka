"""One wishlist-name rule for create and edit, plus blank optional text.

Edge spaces are the characters ``str.isspace()`` removes. Invisible marks are
zero-width space, word joiner, the byte-order mark, and the two bidi marks.
A missing name is reported before length, so a long invisible-only value is
"required", not "too long". Description and event title have no ceiling.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic_core import PydanticCustomError

NAME_MAX_CODE_POINTS = 255
NAME_REQUIRED = "wishlist_name_required"
NAME_TOO_LONG = "wishlist_name_too_long"
_REQUIRED_MESSAGE = "A wishlist name is required"
_TOO_LONG_TEMPLATE = "Wishlist name must be at most {max_length} characters"

# U+200B, U+2060, U+FEFF, U+200E, U+200F.
_INVISIBLE_MARKS = frozenset("\u200b\u2060\ufeff\u200e\u200f")

NameFailure = Literal["required", "too_long"]


def _is_invisible_or_space(character: str) -> bool:
    return character in _INVISIBLE_MARKS or character.isspace()


def _decide(value: str) -> tuple[str | None, NameFailure | None]:
    """Return the kept name, or which failure blocks storing ``value``."""
    trimmed = value.strip()
    if not trimmed or all(_is_invisible_or_space(character) for character in trimmed):
        return None, "required"
    if len(trimmed) > NAME_MAX_CODE_POINTS:
        return None, "too_long"
    return trimmed, None


def name_required_error() -> PydanticCustomError:
    """Missing, blank, or invisible-only wishlist name."""
    return PydanticCustomError(NAME_REQUIRED, _REQUIRED_MESSAGE)


def name_too_long_error() -> PydanticCustomError:
    """Trimmed name longer than 255 code points."""
    return PydanticCustomError(
        NAME_TOO_LONG,
        _TOO_LONG_TEMPLATE,
        {"max_length": NAME_MAX_CODE_POINTS},
    )


def normalize_wishlist_name(value: str) -> str:
    """Edge-trim a name and return it, or raise the matching name error."""
    trimmed, failure = _decide(value)
    if failure == "too_long":
        raise name_too_long_error()
    if failure == "required" or trimmed is None:
        raise name_required_error()
    return trimmed


def classify_stored_name(title: str) -> NameFailure | None:
    """Classify a stored title. ``None`` means it already passes the contract."""
    _trimmed, failure = _decide(title)
    return failure


def normalize_optional_detail(value: str | None) -> str | None:
    """Trim edge spaces. Blank means unset. There is no length ceiling."""
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


def coerce_wishlist_name(value: object) -> object:
    """Reject ``None``. Leave non-strings for Pydantic's own type check."""
    if value is None:
        raise name_required_error()
    if not isinstance(value, str):
        return value
    return normalize_wishlist_name(value)


def coerce_optional_detail(value: object) -> object:
    """Normalize a string detail. Leave ``None`` and non-strings unchanged."""
    if not isinstance(value, str):
        return value
    return normalize_optional_detail(value)


def stored_name_error_detail(failure: NameFailure) -> list[dict[str, Any]]:
    """422 ``detail`` for a save that omits a stored name which fails the rule."""
    if failure == "too_long":
        return [
            {
                "type": NAME_TOO_LONG,
                "loc": ["body", "name"],
                "msg": _TOO_LONG_TEMPLATE.format(max_length=NAME_MAX_CODE_POINTS),
                "ctx": {"max_length": NAME_MAX_CODE_POINTS},
            }
        ]
    return [
        {
            "type": NAME_REQUIRED,
            "loc": ["body", "name"],
            "msg": _REQUIRED_MESSAGE,
        }
    ]
