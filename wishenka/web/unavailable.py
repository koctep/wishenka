"""Localized HTML page for unavailable server-rendered links (WISHENKA-294)."""

import logging
import re

from fastapi import FastAPI, Request, Response
from fastapi.exception_handlers import http_exception_handler
from starlette.exceptions import HTTPException as StarletteHTTPException

from wishenka.auth.dependencies import get_settings, get_user_store
from wishenka.i18n import SupportedLocale
from wishenka.i18n.dependencies import get_request_locale
from wishenka.i18n.locale import resolve_accept_language
from wishenka.web.templates import templates

logger = logging.getLogger("wishenka.web")

# Only the three page URLs a person can open directly; sub-paths and /api stay JSON.
PAGE_PATHS = re.compile(r"^/(share/[^/]+|web/wishlists/[^/]+|web/reservations)$")
_MEDIA_RANGE = re.compile(r"^\s*([^;\s]+)\s*(?:;\s*q\s*=\s*([0-9.]+))?", re.IGNORECASE)


def prefers_html(accept: str | None) -> bool:
    """Return True when ``Accept`` lists ``text/html`` ahead of (or above) ``application/json``.

    ``*/*``, a missing header and wildcards alone never select HTML.
    """
    ranks: dict[str, tuple[float, int]] = {}
    for position, part in enumerate((accept or "").split(",")):
        match = _MEDIA_RANGE.match(part)
        if match is None:
            continue
        try:
            quality = float(match.group(2) if match.group(2) is not None else 1)
        except ValueError:
            quality = 0.0
        ranks.setdefault(match.group(1).lower(), (quality, position))
    html = ranks.get("text/html")
    if html is None or html[0] <= 0:
        return False
    other = ranks.get("application/json")
    return other is None or (html[0], -html[1]) > (other[0], -other[1])


def _route_kind(path: str) -> str:
    """Name the page family without any identifier or token from the URL."""
    if path.startswith("/share/"):
        return "share"
    return "reservations" if path == "/web/reservations" else "wishlist"


async def _locale(request: Request) -> SupportedLocale:
    try:
        return await get_request_locale(request, get_settings(request), get_user_store(request))
    except Exception:  # noqa: BLE001 - an error page must render whatever failed
        logger.warning("Locale lookup failed for the unavailable page", exc_info=True)
        return resolve_accept_language(request.headers.get("accept-language"))


def install_unavailable_page(app: FastAPI) -> None:
    """Render ``unavailable.html`` for GET 404/401 on the page URLs when HTML is preferred."""

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> Response:
        if (
            request.method == "GET"
            and exc.status_code in (401, 404)
            and PAGE_PATHS.match(request.url.path)
            and "hx-request" not in request.headers
            and prefers_html(request.headers.get("accept"))
        ):
            locale = await _locale(request)
            request.state.locale = locale
            logger.info(
                "Unavailable page rendered",
                extra={
                    "event": "unavailable_page_rendered",
                    "status_code": exc.status_code,
                    "route_kind": _route_kind(request.url.path),
                    "locale": str(locale),
                },
            )
            return templates.TemplateResponse(
                request=request,
                name="unavailable.html",
                context={"locale": locale, "unauthenticated": exc.status_code == 401},
                status_code=exc.status_code,
                headers=exc.headers,
            )
        return await http_exception_handler(request, exc)
