"""CSRF protection for cookie-authenticated requests."""

import hashlib
import hmac
import logging

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

logger = logging.getLogger("wishenka.web.security")


def csrf_value(secret: str, session: str) -> str:
    """Bind an opaque CSRF value to the exact session cookie."""
    return hmac.new(
        secret.encode(), b"wishenka-csrf-v1:" + session.encode(), hashlib.sha256
    ).hexdigest()


class BrowserSecurityMiddleware(BaseHTTPMiddleware):
    """Require origin and session-bound token for browser credential mutations."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        settings = request.app.state.settings
        method = request.method
        origin = request.headers.get("origin")
        unsafe = method not in {"GET", "HEAD", "OPTIONS"}
        bearer = bool(
            request.headers.get("authorization", "").removeprefix("Bearer ").strip()
        ) and (request.headers.get("authorization", "").startswith("Bearer "))
        cookie = (
            request.cookies.get(settings.session_cookie_name)
            or request.cookies.get("session_id")
            or request.cookies.get("wishenka_session")
        )
        if unsafe and request.url.path == "/api/auth/telegram":
            if origin != settings.application_origin:
                logger.warning(
                    "Telegram auth rejected: invalid origin %s (expected %s)",
                    origin,
                    settings.application_origin,
                    extra={
                        "event": "origin_mismatch",
                        "path": request.url.path,
                        "origin": origin,
                    },
                )
                return JSONResponse({"detail": "Invalid origin"}, status_code=403)
        elif unsafe and cookie and not bearer:
            token = request.headers.get("x-csrf-token", "")
            expected = csrf_value(settings.csrf_secret_key, cookie)
            if origin != settings.application_origin:
                logger.warning(
                    "CSRF check failed: origin mismatch %s (expected %s) on %s",
                    origin,
                    settings.application_origin,
                    request.url.path,
                    extra={
                        "event": "csrf_origin_mismatch",
                        "path": request.url.path,
                        "origin": origin,
                    },
                )
                return JSONResponse({"detail": "Invalid CSRF token"}, status_code=403)
            if not hmac.compare_digest(token, expected):
                logger.warning(
                    "CSRF check failed: invalid token on %s",
                    request.url.path,
                    extra={
                        "event": "csrf_token_invalid",
                        "path": request.url.path,
                    },
                )
                return JSONResponse({"detail": "Invalid CSRF token"}, status_code=403)
        response = await call_next(request)
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response
