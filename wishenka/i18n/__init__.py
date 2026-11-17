"""Centralized bilingual localization (RU/EN) for Mini App, Bot, and Notices."""

from wishenka.i18n.catalog import CATALOG, t
from wishenka.i18n.locale import (
    DEFAULT_LOCALE,
    LOCALE_LABELS,
    SUPPORTED_LOCALES,
    LocaleSource,
    SupportedLocale,
    resolve_accept_language,
    resolve_telegram_locale,
    validate_locale,
)

__all__ = [
    "CATALOG",
    "DEFAULT_LOCALE",
    "LOCALE_LABELS",
    "SUPPORTED_LOCALES",
    "LocaleSource",
    "SupportedLocale",
    "resolve_accept_language",
    "resolve_telegram_locale",
    "t",
    "validate_locale",
]
