"""Jinja2 template configuration and rendering helpers."""

import html
from pathlib import Path

from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from wishenka.currency import CURRENCY_OPTIONS, DEFAULT_CURRENCY

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _text_escape(value: object) -> Markup:
    """Escape HTML-significant characters for element text content (quotes kept as-is)."""
    return Markup(html.escape("" if value is None else str(value), quote=False))  # noqa: S704


templates.env.filters["text_escape"] = _text_escape
templates.env.globals["range"] = range

templates.env.globals["DEFAULT_CURRENCY"] = DEFAULT_CURRENCY
templates.env.globals["CURRENCY_OPTIONS"] = CURRENCY_OPTIONS
