"""Locale normalization, validation, and HTTP Accept-Language parsing."""

from __future__ import annotations

import math
from typing import Literal

SupportedLocale = Literal["ru", "en"]
LocaleSource = Literal["auto", "explicit"]

DEFAULT_LOCALE: SupportedLocale = "en"
SUPPORTED_LOCALES: tuple[SupportedLocale, ...] = ("ru", "en")
LOCALE_LABELS: dict[SupportedLocale, str] = {
    "ru": "Русский",
    "en": "English",
}


def resolve_optional_locale(language_code: str | None) -> SupportedLocale | None:
    """Normalize a language tag to ``'ru'`` or ``'en'`` if supported, otherwise ``None``."""
    if not isinstance(language_code, str):
        return None
    normalized = language_code.strip().lower().replace("_", "-")
    if not normalized:
        return None
    primary = normalized.split("-", 1)[0]
    if primary == "ru":
        return "ru"
    if primary == "en":
        return "en"
    return None


def resolve_telegram_locale(language_code: str | None) -> SupportedLocale:
    """Normalize a Telegram or client language code to ``'ru'`` or ``'en'``."""
    return resolve_optional_locale(language_code) or DEFAULT_LOCALE


def _parse_quality(params: list[str]) -> float | None:
    """Parse the ``q=`` quality factor from an Accept-Language tag's parameters."""
    quality = 1.0
    for param in params:
        stripped = param.strip().lower()
        if not stripped.startswith("q="):
            continue
        try:
            parsed = float(stripped[2:])
        except ValueError:
            return None
        if math.isnan(parsed) or parsed < 0.0 or parsed > 1.0:
            return None
        quality = parsed
    return quality


def resolve_accept_language(header: str | None) -> SupportedLocale:
    """Resolve the highest-priority tag from an HTTP ``Accept-Language`` header."""
    if not isinstance(header, str) or not header.strip():
        return DEFAULT_LOCALE

    candidates: list[tuple[float, int, str]] = []
    for index, entry in enumerate(header.split(",")):
        parts = entry.split(";")
        tag = parts[0].strip()
        if not tag or tag == "*":
            continue
        quality = _parse_quality(parts[1:])
        if quality is None or quality <= 0.0:
            continue
        candidates.append((-quality, index, tag))

    if not candidates:
        return DEFAULT_LOCALE

    candidates.sort()
    top_tag = candidates[0][2]
    return resolve_telegram_locale(top_tag)


def validate_locale(raw: object) -> SupportedLocale:
    """Validate an explicit user locale choice (``'ru'`` or ``'en'``)."""
    if raw == "ru":
        return "ru"
    if raw == "en":
        return "en"
    raise ValueError("Unsupported locale; expected 'ru' or 'en'")
