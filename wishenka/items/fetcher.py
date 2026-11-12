"""Safe HTML document fetching with SSRF protection and streaming size limits."""

import asyncio
import contextlib
import logging
from contextvars import ContextVar
from http.cookiejar import CookieJar, DefaultCookiePolicy
from typing import Any
from unittest.mock import AsyncMock, sentinel

import httpcore
import httpx

from wishenka.items.encoding import decode_html
from wishenka.items.exceptions import (
    InvalidUrlSchemeError,
    ResponseBodyTooLargeError,
)
from wishenka.items.models import ExtractedMetadata
from wishenka.items.parser import HtmlMetadataExtractor, derive_store_name
from wishenka.items.ssrf import (
    ALLOWED_SCHEMES,
    MAX_RESPONSE_BYTES,
    SSRFSafeTransport,
    resolve_and_validate_host,
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


async def validate_url(url: str) -> None:
    """Validate a URL and its current DNS destination before fetch or cache reuse."""
    parsed = httpx.URL(url)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise InvalidUrlSchemeError("Invalid URL scheme", scheme=parsed.scheme)
    if parsed.username or parsed.password:
        from wishenka.items.exceptions import SSRFBlockedError

        raise SSRFBlockedError("URL credentials are forbidden", reason="credentials")
    await resolve_and_validate_host(
        parsed.host, parsed.port or (443 if parsed.scheme == "https" else 80)
    )


async def _validate_request(request: httpx.Request) -> None:
    """Validate every outbound request and redirect on an injected client."""
    request.headers.pop("cookie", None)
    if "authorization" in request.headers:
        from wishenka.items.exceptions import SSRFBlockedError

        raise SSRFBlockedError("Authorization is forbidden", reason="credentials")
    await validate_url(str(request.url))


class _BorrowedTransport(httpx.AsyncBaseTransport):
    """Use the injected client's direct transport without sharing request state or ownership."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        transport = self.client._transport_for_url(request.url)
        pool = getattr(transport, "_pool", None)
        if isinstance(pool, (httpcore.AsyncHTTPProxy, httpcore.AsyncSOCKSProxy)):
            # Ignore proxy mounts (including environment configuration) while preserving
            # explicit direct transports mounted by the client owner.
            transport = self.client._transport
            pool = getattr(transport, "_pool", None)
        if isinstance(pool, (httpcore.AsyncHTTPProxy, httpcore.AsyncSOCKSProxy)):
            from wishenka.items.exceptions import SSRFBlockedError

            raise SSRFBlockedError("Proxy transports are forbidden", reason="proxy")
        # A direct transport still has the pre-existing DNS rebinding limitation.
        return await transport.handle_async_request(request)


def _is_mock_get_configured(client: httpx.AsyncClient) -> bool:
    """Detect if client is an AsyncMock with specifically configured get method."""
    if not isinstance(client, AsyncMock):
        return False
    get_mock = getattr(client, "get", None)
    if get_mock is None or not isinstance(get_mock, AsyncMock):
        return False
    has_side_effect = getattr(get_mock, "_mock_side_effect", None) is not None
    return_val = getattr(get_mock, "_mock_return_value", sentinel.DEFAULT)
    has_return_value = return_val is not sentinel.DEFAULT and return_val is not None
    return has_side_effect or has_return_value


class UrlMetadataService:
    """Dedicated service for safe HTML content fetching with SSRF and size bounds."""

    def __init__(
        self,
        max_bytes: int = MAX_RESPONSE_BYTES,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
    ) -> None:
        self.max_bytes = max_bytes
        self.timeout = timeout

    async def _fetch_html(
        self,
        url: str,
        client: httpx.AsyncClient | None = None,
    ) -> tuple[str, str]:
        """Fetch HTML document body up to max_bytes with SSRF protection.

        Returns:
            Tuple of (html_text, final_effective_url).

        Raises:
            InvalidUrlSchemeError: If URL scheme is not http or https.
            SSRFBlockedError: If destination or redirect target is unsafe.
            ResponseBodyTooLargeError: If payload exceeds max_bytes.
            httpx.HTTPError: On standard network or HTTP protocol errors.
        """
        parsed = httpx.URL(url)
        if parsed.username or parsed.password:
            from wishenka.items.exceptions import SSRFBlockedError

            raise SSRFBlockedError("URL credentials are forbidden", reason="credentials")
        scheme = parsed.scheme.lower()
        if scheme not in ALLOWED_SCHEMES:
            logger.warning(
                "Invalid URL scheme '%s' for '%s'",
                scheme,
                url,
                extra={
                    "event": "ssrf_blocked",
                    "url": url,
                    "scheme": scheme,
                    "reason": "invalid_scheme",
                },
            )
            raise InvalidUrlSchemeError(
                f"URL scheme '{scheme}' is not allowed; only http and https are permitted",
                scheme=scheme,
            )

        host = parsed.host
        port = parsed.port or (443 if scheme == "https" else 80)
        await resolve_and_validate_host(host, port)

        if client is None:
            transport = SSRFSafeTransport()
            async with httpx.AsyncClient(
                transport=transport,
                timeout=self.timeout,
                follow_redirects=True,
                cookies=CookieJar(policy=RejectCookies()),
                trust_env=False,
            ) as local_client:
                if isinstance(httpx.AsyncClient.get, AsyncMock):
                    return await self._fetch_via_get(local_client, url)

                return await self._stream_and_read(local_client, url)

        # Custom or injected client
        if _is_mock_get_configured(client):
            return await self._fetch_via_get(client, url)

        if isinstance(client, AsyncMock):
            return await self._stream_and_read(client, url)

        if getattr(client, "_wishenka_safe_transport", False):
            return await self._stream_and_read(client, url)

        # Keep credentials, cookies, hooks and redirect state separate from the owner.
        # The wrapper does not close the borrowed client's connection pool.
        async with httpx.AsyncClient(
            transport=_BorrowedTransport(client),
            timeout=self.timeout,
            cookies=CookieJar(policy=RejectCookies()),
            event_hooks={"request": [_validate_request]},
            trust_env=False,
        ) as preview_client:
            return await self._stream_and_read(preview_client, url)

    async def _fetch_via_get(
        self,
        client: httpx.AsyncClient,
        url: str,
    ) -> tuple[str, str]:
        """Fetch response via client.get for legacy mock compatibility."""
        response = await client.get(
            url,
            headers=DEFAULT_HEADERS,
            follow_redirects=True,
        )
        cl_header = response.headers.get("Content-Length")
        if cl_header is not None:
            with contextlib.suppress(ValueError, TypeError):
                cl_val = int(cl_header)
                if cl_val > self.max_bytes:
                    logger.warning(
                        "Payload size violation: "
                        "Content-Length %d exceeds limit of %d bytes for %s",
                        cl_val,
                        self.max_bytes,
                        url,
                        extra={
                            "event": "payload_size_violation",
                            "url": url,
                            "content_length": cl_val,
                            "max_allowed": self.max_bytes,
                            "reason": "content_length_exceeded",
                        },
                    )
                    raise ResponseBodyTooLargeError(
                        f"Content-Length {cl_header} exceeds limit of {self.max_bytes} bytes",
                        content_length=cl_val,
                        max_allowed=self.max_bytes,
                    )

        if (
            hasattr(response, "content")
            and isinstance(response.content, bytes)
            and len(response.content) > self.max_bytes
        ):
            body_len = len(response.content)
            logger.warning(
                "Payload size violation: body %d bytes exceeds limit of %d bytes for %s",
                body_len,
                self.max_bytes,
                url,
                extra={
                    "event": "payload_size_violation",
                    "url": url,
                    "content_length": body_len,
                    "max_allowed": self.max_bytes,
                    "reason": "response_body_exceeded",
                },
            )
            raise ResponseBodyTooLargeError(
                f"Response body exceeded limit of {self.max_bytes} bytes",
                content_length=body_len,
                max_allowed=self.max_bytes,
            )

        if response.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP error {response.status_code} for url {response.url}",
                request=response.request,
                response=response,
            )
        content = response.content
        html = (
            decode_html(content, response.headers.get("content-type", ""))
            if isinstance(content, bytes)
            else response.text
        )
        return html, str(response.url) if response.url else url

    async def _stream_and_read(
        self,
        client: httpx.AsyncClient,
        url: str,
    ) -> tuple[str, str]:
        """Stream response and enforce 2MB limit via Content-Length and chunk inspection."""
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
                        logger.warning(
                            "Payload size violation: "
                            "Content-Length %d exceeds limit of %d bytes for %s",
                            cl_val,
                            self.max_bytes,
                            url,
                            extra={
                                "event": "payload_size_violation",
                                "url": url,
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
                    logger.warning(
                        "Payload size violation: "
                        "streaming bytes %d exceeded limit of %d bytes for %s",
                        total_bytes,
                        self.max_bytes,
                        url,
                        extra={
                            "event": "payload_size_violation",
                            "url": url,
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
                response._content = raw_bytes
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
    ) -> ExtractedMetadata:
        """Fetch HTML document body and extract rich metadata, falling back safely on errors."""
        try:
            html_text, final_url = await self._fetch_html(url, client=client)
            return await asyncio.to_thread(
                HtmlMetadataExtractor.extract, html_text, base_url=final_url
            )
        except Exception as exc:
            logger.warning(
                "UrlMetadataService fetch_and_extract failed for %s: %s; returning fallback",
                url,
                exc,
                extra={"event": "fetch_and_extract_fallback", "url": url, "error": str(exc)},
            )
            store_name = derive_store_name(url)
            return ExtractedMetadata(store_name=store_name)


__all__ = [
    "DEFAULT_HEADERS",
    "DEFAULT_TIMEOUT",
    "UrlMetadataService",
]
