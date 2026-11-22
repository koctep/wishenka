"""Safe HTML document fetching with SSRF protection and streaming size limits."""

import asyncio
import contextlib
import logging
import weakref
from collections.abc import Mapping
from contextvars import ContextVar
from dataclasses import dataclass, replace
from http.cookiejar import CookieJar, DefaultCookiePolicy
from types import MappingProxyType
from typing import Any
from uuid import uuid4

import httpx

from wishenka.config import Settings
from wishenka.items.encoding import decode_html
from wishenka.items.exceptions import (
    CassetteError,
    CassetteMissError,
    InvalidUrlSchemeError,
    ResponseBodyTooLargeError,
)
from wishenka.items.models import ExtractedMetadata
from wishenka.items.parser import HtmlMetadataExtractor, derive_store_name
from wishenka.items.ssrf import (
    SSRFPolicy,
    SSRFSafeTransport,
    _use_ssrf_policy,
    log_ssrf_credentials_blocked,
    log_ssrf_invalid_scheme,
    log_ssrf_policy_event,
    redact_url_credentials,
    resolve_and_validate_host,
    resolve_ssrf_policy,
)

logger = logging.getLogger("wishenka.items")

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}

DEFAULT_TIMEOUT = httpx.Timeout(4.0, connect=2.0)


class RejectCookies(DefaultCookiePolicy):
    """Prevent origin cookies from being stored or sent across redirects."""

    def set_ok(self, cookie: Any, request: Any) -> bool:
        return False

    def return_ok(self, cookie: Any, request: Any) -> bool:
        return False


# Per-task response information; never shared across concurrent requests.
fetch_provenance: ContextVar[tuple[tuple[str, httpx.Headers], ...]] = ContextVar(
    "fetch_provenance", default=()
)


async def validate_url(
    url: str,
    *,
    policy: SSRFPolicy | None = None,
    settings: Settings | None = None,
) -> None:
    """Validate a URL and its current DNS destination before fetch or cache reuse."""
    active_policy = resolve_ssrf_policy(settings=settings, policy=policy)
    parsed = httpx.URL(url)
    if parsed.username or parsed.password:
        from wishenka.items.exceptions import SSRFBlockedError

        log_ssrf_credentials_blocked(host=parsed.host)
        raise SSRFBlockedError("URL credentials are forbidden", reason="credentials")
    scheme = parsed.scheme.lower()
    if scheme not in active_policy.allowed_schemes:
        allowed_display = ", ".join(sorted(active_policy.allowed_schemes))
        log_ssrf_invalid_scheme(
            url=url,
            host=parsed.host,
            scheme=scheme,
            allowed_schemes=active_policy.allowed_schemes,
        )
        raise InvalidUrlSchemeError(
            f"URL scheme '{scheme}' is not allowed; permitted schemes: {allowed_display}",
            scheme=parsed.scheme,
        )
    port = parsed.port or (443 if scheme == "https" else 80)
    with _use_ssrf_policy(active_policy):
        await resolve_and_validate_host(parsed.host, port)


async def _validate_request(request: httpx.Request) -> None:
    """Validate every outbound request and redirect on an injected client."""
    request.headers.pop("cookie", None)
    if "authorization" in request.headers:
        from wishenka.items.exceptions import SSRFBlockedError

        log_ssrf_credentials_blocked(host=request.url.host)
        raise SSRFBlockedError("Authorization is forbidden", reason="credentials")
    await validate_url(str(request.url))


class _ReplayTransport(httpx.AsyncBaseTransport):
    """Replay immutable response fixtures without a network delegate."""

    def __init__(
        self,
        responses: Mapping[str, tuple[int, Mapping[str, str], bytes]],
        marketplace: str | None = None,
        scenario: str | None = None,
    ) -> None:
        self._marketplace = marketplace
        self._scenario = scenario
        self._responses = MappingProxyType(
            {
                url: (status, dict(headers), bytes(body))
                for url, (status, headers, body) in responses.items()
            }
        )

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        item = self._responses.get(str(request.url))
        if item is None:
            from wishenka.items.cassettes import sanitize_uri

            target = sanitize_uri(str(request.url))
            item = next(
                (
                    response
                    for url, response in self._responses.items()
                    if sanitize_uri(url) == target
                ),
                None,
            )
        if item is None:
            from wishenka.items.cassettes import sanitize_uri

            uri = sanitize_uri(str(request.url))
            logger.warning(
                "Cassette miss in offline replay for %s %s",
                request.method,
                uri,
                extra={"event": "cassette_miss", "method": request.method, "uri": uri},
            )
            raise CassetteMissError(method=request.method, uri=uri)
        status, headers, body = item
        logger.debug(
            "Cassette replay hit for %s (status=%d)",
            request.method,
            status,
            extra={
                "event": "cassette_replay_hit",
                "method": request.method,
                "status_code": status,
                "mode": "replay",
                "marketplace": self._marketplace,
                "scenario": self._scenario,
            },
        )
        return httpx.Response(status, headers=headers, content=body, request=request)


class _DenyTransport(httpx.AsyncBaseTransport):
    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        from wishenka.items.exceptions import SSRFBlockedError

        raise SSRFBlockedError("Preview route denied", reason="route_denied")


@dataclass(frozen=True)
class PreviewRoute:
    """A route created by a controlled factory, not an arbitrary HTTPX transport."""

    transport: httpx.AsyncBaseTransport
    _token: object


_ROUTE_TOKEN = object()
_ISSUED_ROUTES: dict[int, tuple[weakref.ReferenceType[PreviewRoute], httpx.AsyncBaseTransport]] = {}


def _issue_route(transport: httpx.AsyncBaseTransport) -> PreviewRoute:
    """Bind a factory-created route to its original transport by identity."""
    route = PreviewRoute(transport, _ROUTE_TOKEN)
    key = id(route)
    _ISSUED_ROUTES[key] = (
        weakref.ref(route, lambda _ref: _ISSUED_ROUTES.pop(key, None)),
        transport,
    )
    return route


def offline_replay_route(
    responses: Mapping[str, tuple[int, Mapping[str, str], bytes]],
    *,
    marketplace: str | None = None,
    scenario: str | None = None,
) -> PreviewRoute:
    """Construct a fixture-only route that never performs network I/O."""
    return _issue_route(_ReplayTransport(responses, marketplace, scenario))


def deny_route() -> PreviewRoute:
    """Construct an explicit fail-closed route."""
    return _issue_route(_DenyTransport())


def safe_direct_route(
    *,
    limits: httpx.Limits | None = None,
    settings: Settings | None = None,
    policy: SSRFPolicy | None = None,
) -> PreviewRoute:
    """Construct an owned pinned-IP direct route without proxy configuration."""
    kwargs: dict[str, Any] = {}
    if limits is not None:
        kwargs["limits"] = limits
    if settings is not None:
        kwargs["settings"] = settings
    if policy is not None:
        kwargs["policy"] = policy
    return _issue_route(SSRFSafeTransport(**kwargs))


@dataclass(frozen=True, init=False)
class PreviewTransportConfig:
    """Immutable route snapshot; route transports remain owned by their creator."""

    default: PreviewRoute
    mounts: Mapping[str, PreviewRoute]
    cache_identity: str

    def __init__(self, default: PreviewRoute, mounts: Mapping[str, PreviewRoute]) -> None:
        snapshot = dict(mounts)
        for pattern, route in snapshot.items():
            httpx.URL(pattern)
            if not pattern or not isinstance(pattern, str):
                raise ValueError("Invalid preview mount pattern")
            self._validate_route(route)
        self._validate_route(default)
        object.__setattr__(self, "cache_identity", uuid4().hex)
        object.__setattr__(self, "default", default)
        object.__setattr__(self, "mounts", MappingProxyType(snapshot))

    @staticmethod
    def _validate_route(route: PreviewRoute) -> None:
        issued = _ISSUED_ROUTES.get(id(route))
        if (
            type(route) is not PreviewRoute
            or route._token is not _ROUTE_TOKEN
            or issued is None
            or issued[0]() is not route
            or issued[1] is not route.transport
            or type(route.transport) not in (SSRFSafeTransport, _ReplayTransport, _DenyTransport)
        ):
            raise ValueError("Unapproved preview route")


class _BorrowedTransport(httpx.AsyncBaseTransport):
    """Delegate through the public transport interface without taking ownership."""

    def __init__(self, route: PreviewRoute) -> None:
        self.route = route

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        PreviewTransportConfig._validate_route(self.route)
        return await self.route.transport.handle_async_request(request)


class UrlMetadataService:
    """Dedicated service for safe HTML content fetching with SSRF and size bounds."""

    def __init__(
        self,
        max_bytes: int | None = None,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
        *,
        settings: Settings | None = None,
        policy: SSRFPolicy | None = None,
    ) -> None:
        base_policy = resolve_ssrf_policy(settings=settings, policy=policy)
        if max_bytes is not None:
            if isinstance(max_bytes, bool) or max_bytes < 1:
                raise ValueError("max_bytes must be >= 1")
            effective_policy = replace(base_policy, max_response_bytes=max_bytes)
        else:
            effective_policy = base_policy
        self.policy = effective_policy
        self.max_bytes = effective_policy.max_response_bytes
        self.timeout = timeout
        if settings is not None or policy is not None or max_bytes is not None:
            if max_bytes is not None:
                source = "max_bytes_override"
            elif settings is not None:
                source = "settings"
            else:
                source = "policy"
            log_ssrf_policy_event(
                event="ssrf_policy_configured",
                component="UrlMetadataService",
                policy=self.policy,
                source=source,
            )

    async def _fetch_html(
        self,
        url: str,
        client: httpx.AsyncClient | None = None,
        routes: PreviewTransportConfig | None = None,
    ) -> tuple[str, str]:
        """Fetch HTML document body up to max_bytes with SSRF protection.

        Returns:
            Tuple of (html_text, final_effective_url).

        Raises:
            InvalidUrlSchemeError: If URL scheme is disallowed by the active SSRF policy.
            SSRFBlockedError: If destination or redirect target is unsafe.
            ResponseBodyTooLargeError: If payload exceeds max_bytes.
            httpx.HTTPError: On standard network or HTTP protocol errors.
        """
        parsed = httpx.URL(url)
        if parsed.username or parsed.password:
            from wishenka.items.exceptions import SSRFBlockedError

            log_ssrf_credentials_blocked(host=parsed.host)
            raise SSRFBlockedError("URL credentials are forbidden", reason="credentials")
        scheme = parsed.scheme.lower()
        if scheme not in self.policy.allowed_schemes:
            allowed_display = ", ".join(sorted(self.policy.allowed_schemes))
            log_ssrf_invalid_scheme(
                url=url,
                host=parsed.host,
                scheme=scheme,
                allowed_schemes=self.policy.allowed_schemes,
            )
            raise InvalidUrlSchemeError(
                f"URL scheme '{scheme}' is not allowed; permitted schemes: {allowed_display}",
                scheme=scheme,
            )

        if client is not None:
            from wishenka.items.exceptions import SSRFBlockedError

            raise SSRFBlockedError("Opaque preview client is unsupported", reason="unknown_route")

        host = parsed.host
        port = parsed.port or (443 if scheme == "https" else 80)
        with _use_ssrf_policy(self.policy):
            await resolve_and_validate_host(host, port)

            owned_route: PreviewRoute | None = None
            if routes is None:
                owned_route = safe_direct_route(policy=self.policy)
                selected = PreviewTransportConfig(default=owned_route, mounts={})
            else:
                selected = routes
            try:
                async with httpx.AsyncClient(
                    transport=_BorrowedTransport(selected.default),
                    mounts={
                        key: _BorrowedTransport(route) for key, route in selected.mounts.items()
                    },
                    timeout=self.timeout,
                    cookies=CookieJar(policy=RejectCookies()),
                    event_hooks={"request": [_validate_request]},
                    trust_env=False,
                ) as preview_client:
                    return await self._stream_and_read(preview_client, url)
            finally:
                if owned_route is not None:
                    await owned_route.transport.aclose()

    async def _stream_and_read(
        self,
        client: httpx.AsyncClient,
        url: str,
    ) -> tuple[str, str]:
        """Stream response and enforce max_bytes limit via Content-Length and chunk inspection."""
        async with client.stream(
            "GET",
            url,
            headers=DEFAULT_HEADERS,
            follow_redirects=True,
        ) as response:
            cl_header = response.headers.get("Content-Length")
            if cl_header is not None:
                with contextlib.suppress(ValueError, TypeError):
                    cl_val = int(cl_header)
                    if cl_val > self.max_bytes:
                        safe_url = redact_url_credentials(url)
                        logger.warning(
                            "Payload size violation: "
                            "Content-Length %d exceeds limit of %d bytes for %s",
                            cl_val,
                            self.max_bytes,
                            safe_url,
                            extra={
                                "event": "payload_size_violation",
                                "url": safe_url,
                                "content_length": cl_val,
                                "max_allowed": self.max_bytes,
                                "reason": "content_length_exceeded",
                            },
                        )
                        raise ResponseBodyTooLargeError(
                            f"Content-Length {cl_val} exceeds limit of {self.max_bytes} bytes",
                            content_length=cl_val,
                            max_allowed=self.max_bytes,
                        )

            chunks: list[bytes] = []
            total_bytes = 0
            async for chunk in response.aiter_bytes():
                total_bytes += len(chunk)
                if total_bytes > self.max_bytes:
                    safe_url = redact_url_credentials(url)
                    logger.warning(
                        "Payload size violation: "
                        "streaming bytes %d exceeded limit of %d bytes for %s",
                        total_bytes,
                        self.max_bytes,
                        safe_url,
                        extra={
                            "event": "payload_size_violation",
                            "url": safe_url,
                            "streamed_bytes": total_bytes,
                            "max_allowed": self.max_bytes,
                            "reason": "stream_chunk_overflow",
                        },
                    )
                    raise ResponseBodyTooLargeError(
                        f"Response body exceeded limit of {self.max_bytes} bytes while streaming",
                        content_length=total_bytes,
                        max_allowed=self.max_bytes,
                    )
                chunks.append(chunk)

            raw_bytes = b"".join(chunks)

            if response.status_code >= 400:
                # aiter_bytes() has already decoded content encodings. Retaining those
                # headers would cause HTTPX to decode the reconstructed body again.
                headers = httpx.Headers(response.headers)
                headers.pop("content-encoding", None)
                headers.pop("content-length", None)
                headers.pop("transfer-encoding", None)
                response = httpx.Response(
                    response.status_code,
                    headers=headers,
                    content=raw_bytes,
                    request=response.request,
                    history=response.history,
                )
                raise httpx.HTTPStatusError(
                    f"HTTP error {response.status_code} for url {response.url}",
                    request=response.request,
                    response=response,
                )

            html_text = decode_html(raw_bytes, response.headers.get("content-type", ""))

            final_effective_url = str(response.url) if response.url else url
            if response.is_success:
                fetch_provenance.set(
                    tuple(
                        (str(item.url), httpx.Headers(item.headers))
                        for item in [*response.history, response]
                    )
                )
            logger.info(
                "Successfully fetched %s (bytes=%d, effective_url=%s)",
                url,
                len(raw_bytes),
                final_effective_url,
                extra={
                    "event": "url_fetch_success",
                    "url": url,
                    "effective_url": final_effective_url,
                    "bytes": len(raw_bytes),
                },
            )
            return html_text, final_effective_url

    async def fetch_and_extract(
        self,
        url: str,
        client: httpx.AsyncClient | None = None,
        *,
        routes: PreviewTransportConfig | None = None,
    ) -> ExtractedMetadata:
        """Fetch HTML document body and extract rich metadata, falling back safely on errors."""
        try:
            html_text, final_url = await self._fetch_html(url, client=client, routes=routes)
            return await asyncio.to_thread(
                HtmlMetadataExtractor.extract, html_text, base_url=final_url
            )
        except CassetteError:
            raise
        except Exception as exc:
            safe_url = redact_url_credentials(url)
            logger.warning(
                "UrlMetadataService fetch_and_extract failed for %s: %s; returning fallback",
                safe_url,
                exc,
                extra={"event": "fetch_and_extract_fallback", "url": safe_url, "error": str(exc)},
            )
            store_name = derive_store_name(url)
            return ExtractedMetadata(store_name=store_name)


__all__ = [
    "DEFAULT_HEADERS",
    "DEFAULT_TIMEOUT",
    "UrlMetadataService",
]
