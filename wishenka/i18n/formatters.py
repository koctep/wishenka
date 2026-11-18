"""Locale-aware date and count formatting helpers without OS locale dependence."""

from __future__ import annotations

from datetime import UTC, date, datetime

from wishenka.i18n.locale import DEFAULT_LOCALE, SupportedLocale, resolve_telegram_locale

_EN_MONTHS: tuple[str, ...] = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)


def format_date(
    value: datetime | date | None,
    locale: SupportedLocale | str | None = DEFAULT_LOCALE,
) -> str:
    """Format a date or datetime for ``'ru'`` (DD.MM.YYYY) or ``'en'`` (MMM D, YYYY)."""
    if value is None:
        return ""

    if isinstance(value, datetime):
        aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        target = aware.date()
    else:
        target = value

    resolved = resolve_telegram_locale(locale)
    if resolved == "ru":
        return f"{target.day:02d}.{target.month:02d}.{target.year:04d}"
    return f"{_EN_MONTHS[target.month - 1]} {target.day}, {target.year:04d}"
