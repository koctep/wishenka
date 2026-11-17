"""Serve the Telegram Mini App shell without embedding capabilities."""

import json
import logging
from html import escape

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from wishenka.i18n import miniapp_catalog, t
from wishenka.i18n.dependencies import LocaleDep

router = APIRouter()
logger = logging.getLogger("wishenka.web.miniapp")


@router.get("/", response_class=HTMLResponse)
async def miniapp(request: Request, locale: LocaleDep) -> HTMLResponse:
    """Return an accessible shell with configured Telegram link destinations."""
    logger.info("Mini App shell requested", extra={"event": "miniapp_shell_requested"})
    settings = request.app.state.settings
    bot = escape(settings.telegram_bot_username, quote=True)
    app_name = escape(settings.telegram_app_short_name, quote=True)
    loading_text = escape(t("nav.loading", locale))
    catalog = miniapp_catalog()
    logger.debug(
        "Mini App i18n catalog embedded",
        extra={
            "event": "miniapp_catalog_embedded",
            "locale": locale,
            "key_count": len(catalog.get(locale, {})),
        },
    )
    i18n_payload = (
        json.dumps(catalog, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    html = f"""<!doctype html>
<html lang="{locale}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Wishenka</title><link rel="stylesheet" href="/static/miniapp.css">
<script id="miniapp-i18n" type="application/json">{i18n_payload}</script>
<script src="/static/miniapp.js" defer></script></head>
<body><p id="status" role="status" aria-live="polite">{loading_text}</p>
<main id="app" data-bot="{bot}" data-miniapp="{app_name}"
 data-locale="{locale}"></main></body></html>"""
    response = HTMLResponse(html)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self' https://telegram.org; "
        "style-src 'self'; img-src 'self' https:; frame-ancestors https://web.telegram.org"
    )
    return response
