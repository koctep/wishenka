"""Rate limiting for unauthenticated public wishlist and invite links."""

from __future__ import annotations

import html
import logging
import math
import time
from collections import OrderedDict, deque
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from wishenka.i18n import t
from wishenka.i18n.locale import resolve_accept_language, resolve_optional_locale

logger = logging.getLogger("wishenka.web.rate_limit")


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    """Result of a rate-limit check for a single client request."""

    allowed: bool
    retry_after_seconds: int
    remaining: int


class SlidingWindowRateLimiter:
    """In-memory sliding-window log rate limiter with bounded client tracking."""

    def __init__(
        self,
        *,
        max_requests: int,
        window_seconds: int,
        max_clients: int = 10000,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if max_requests < 1:
            raise ValueError("max_requests must be >= 1")
        if window_seconds < 1:
            raise ValueError("window_seconds must be >= 1")
        if max_clients < 1:
            raise ValueError("max_clients must be >= 1")
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._max_clients = max_clients
        self._clock = clock
        self._buckets: OrderedDict[str, deque[float]] = OrderedDict()

    def _now(self) -> float:
        if self._clock is not None:
            return self._clock()
        return time.monotonic()

    def _prune_bucket(self, bucket: deque[float], cutoff: float) -> None:
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()

    def _evict_expired(self, cutoff: float) -> None:
        expired_keys: list[str] = []
        for key, bucket in self._buckets.items():
            self._prune_bucket(bucket, cutoff)
            if not bucket:
                expired_keys.append(key)
        for key in expired_keys:
            del self._buckets[key]

    @property
    def tracked_clients(self) -> int:
        """Return the number of client keys currently held in memory."""
        return len(self._buckets)

    def check_and_record(self, client_key: str) -> RateLimitDecision:
        """Check whether ``client_key`` is within its sliding window and record if allowed."""
        now = self._now()
        cutoff = now - self._window_seconds
        bucket = self._buckets.get(client_key)

        if bucket is not None:
            self._prune_bucket(bucket, cutoff)
            if not bucket:
                del self._buckets[client_key]
                bucket = None

        if bucket is not None and len(bucket) >= self._max_requests:
            retry_after = max(1, math.ceil(bucket[0] + self._window_seconds - now))
            self._buckets.move_to_end(client_key)
            return RateLimitDecision(
                allowed=False,
                retry_after_seconds=retry_after,
                remaining=0,
            )

        if bucket is None:
            if len(self._buckets) >= self._max_clients:
                self._evict_expired(cutoff)
            while len(self._buckets) >= self._max_clients:
                self._buckets.popitem(last=False)
            bucket = deque()
            self._buckets[client_key] = bucket
        else:
            self._buckets.move_to_end(client_key)

        bucket.append(now)
        remaining = max(0, self._max_requests - len(bucket))
        return RateLimitDecision(
            allowed=True,
            retry_after_seconds=0,
            remaining=remaining,
        )


def match_public_link_route(method: str, path: str) -> str | None:
    """Return a token-redacted route template for rate-limited public endpoints, or ``None``."""
    parts = path.lstrip("/").split("/")
    upper_method = method.upper()
    if upper_method == "GET" and len(parts) == 2 and parts[1]:
        if parts[0] == "share":
            return "/share/{token}"
        if parts[0] == "invite":
            return "/invite/{token}"
    if (
        upper_method == "POST"
        and len(parts) == 3
        and parts[0] == "invite"
        and parts[1]
        and parts[2] == "join"
    ):
        return "/invite/{token}/join"
    return None


def resolve_client_ip(request: Request, trust_proxy_headers: bool) -> str:
    """Resolve client IP from proxy headers when trusted, otherwise from socket peer."""
    if trust_proxy_headers:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            first_ip = xff.split(",", 1)[0].strip()
            if first_ip:
                return first_ip
        real_ip = request.headers.get("x-real-ip")
        if real_ip and real_ip.strip():
            return real_ip.strip()
    if request.client is not None and request.client.host:
        return request.client.host
    return "unknown"


def _build_rate_limit_response(
    request: Request,
    retry_after_seconds: int,
) -> Response:
    """Build a localized, token-free 429 response in JSON or HTML."""
    locale = resolve_optional_locale(request.query_params.get("lang")) or resolve_accept_language(
        request.headers.get("accept-language")
    )
    title = t("web.rate_limit.title", locale)
    message = t("web.rate_limit.message", locale, seconds=retry_after_seconds)
    headers = {"Retry-After": str(retry_after_seconds)}

    accept = request.headers.get("accept", "").lower()
    if "application/json" in accept:
        return JSONResponse(
            content={"detail": message, "retry_after": retry_after_seconds},
            status_code=429,
            headers=headers,
        )

    escaped_title = html.escape(title)
    escaped_message = html.escape(message)
    body = (
        "<!DOCTYPE html>"
        f'<html lang="{locale}">'
        "<head>"
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{escaped_title}</title>"
        "</head>"
        "<body>"
        "<main>"
        f"<h1>{escaped_title}</h1>"
        f"<p>{escaped_message}</p>"
        "</main>"
        "</body>"
        "</html>"
    )
    return HTMLResponse(content=body, status_code=429, headers=headers)


class PublicLinkRateLimitMiddleware(BaseHTTPMiddleware):
    """Enforce per-client sliding-window rate limits on public share and invite routes."""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        settings = request.app.state.settings
        if not settings.public_rate_limit_enabled:
            return await call_next(request)

        route = match_public_link_route(request.method, request.url.path)
        if route is None:
            return await call_next(request)

        limiter: SlidingWindowRateLimiter = request.app.state.public_link_rate_limiter
        client_ip = resolve_client_ip(request, settings.public_rate_limit_trust_proxy_headers)
        decision = limiter.check_and_record(client_ip)
        if decision.allowed:
            return await call_next(request)

        logger.warning(
            "Public link rate limit exceeded: %s %s client=%s retry_after=%ds",
            request.method,
            route,
            client_ip,
            decision.retry_after_seconds,
            extra={
                "event": "public_link_rate_limited",
                "route": route,
                "method": request.method,
                "client_ip": client_ip,
                "retry_after": decision.retry_after_seconds,
            },
        )
        return _build_rate_limit_response(request, decision.retry_after_seconds)
