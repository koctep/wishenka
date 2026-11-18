"""Jinja2 template configuration and rendering helpers."""

import html
from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from wishenka.currency import CURRENCY_OPTIONS, DEFAULT_CURRENCY
from wishenka.i18n import DEFAULT_LOCALE, LOCALE_LABELS, SUPPORTED_LOCALES, format_date, t

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def _locale_context_processor(request: Request) -> dict[str, Any]:
    """Provide the resolved request locale (defaulting to ``'en'``) to templates."""
    return {"locale": getattr(request.state, "locale", DEFAULT_LOCALE)}


templates = Jinja2Templates(
    directory=str(TEMPLATES_DIR),
    context_processors=[_locale_context_processor],
)


def _text_escape(value: object) -> Markup:
    """Escape HTML-significant characters for element text content (quotes kept as-is)."""
    return Markup(html.escape("" if value is None else str(value), quote=False))  # noqa: S704


templates.env.filters["text_escape"] = _text_escape
templates.env.filters["format_date"] = format_date
templates.env.globals["range"] = range

templates.env.globals["DEFAULT_CURRENCY"] = DEFAULT_CURRENCY
templates.env.globals["CURRENCY_OPTIONS"] = CURRENCY_OPTIONS
templates.env.globals["DEFAULT_LOCALE"] = DEFAULT_LOCALE
templates.env.globals["SUPPORTED_LOCALES"] = SUPPORTED_LOCALES
templates.env.globals["LOCALE_LABELS"] = LOCALE_LABELS
templates.env.globals["t"] = t
templates.env.globals["format_date"] = format_date
