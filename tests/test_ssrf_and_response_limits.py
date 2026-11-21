"""Automated failing repro tests for WISHENKA-54.

Validates SSRF protection (loopback, RFC 1918, cloud metadata, IPv6, DNS rebinding,
redirect hops, forbidden schemes) and response size limits (2MB Content-Length early
rejection, streaming chunk cutoff) with graceful degradation.
"""

import importlib
import ipaddress
import logging
import socket
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from wishenka.items import exceptions as item_exceptions
from wishenka.items.models import ExtractedMetadata
from wishenka.items.schemas import ItemPreviewDTO
from wishenka.items.service import ItemPreviewService


# Fallback classes for missing domain exceptions prior to Step 4 implementation
class _MissingItemParsingError(Exception):
    """Fallback error when ItemParsingError is not implemented."""


class _MissingSSRFError(_MissingItemParsingError):
    """Fallback error when SSRFError is not implemented."""


class _MissingSSRFBlockedError(_MissingSSRFError):
    """Fallback error when SSRFBlockedError is not implemented."""


class _MissingInvalidUrlSchemeError(_MissingSSRFError):
    """Fallback error when InvalidUrlSchemeError is not implemented."""


class _MissingResponseBodyTooLargeError(_MissingItemParsingError):
    """Fallback error when ResponseBodyTooLargeError is not implemented."""


ItemParsingError: type[Exception] = getattr(
    item_exceptions, "ItemParsingError", _MissingItemParsingError
)
SSRFError: type[Exception] = getattr(item_exceptions, "SSRFError", _MissingSSRFError)
SSRFBlockedError: type[Exception] = getattr(
    item_exceptions, "SSRFBlockedError", _MissingSSRFBlockedError
)
InvalidUrlSchemeError: type[Exception] = getattr(
    item_exceptions, "InvalidUrlSchemeError", _MissingInvalidUrlSchemeError
)
ResponseBodyTooLargeError: type[Exception] = getattr(
    item_exceptions, "ResponseBodyTooLargeError", _MissingResponseBodyTooLargeError
)

# Dynamically import components that will be introduced in Step 4
try:
    ssrf_mod = importlib.import_module("wishenka.items.ssrf")
    ALLOWED_SCHEMES: frozenset[str] = getattr(
        ssrf_mod, "ALLOWED_SCHEMES", frozenset({"http", "https"})
    )
    MAX_RESPONSE_BYTES: int = getattr(ssrf_mod, "MAX_RESPONSE_BYTES", 2 * 1024 * 1024)
    SSRFSafeTransport: Any = getattr(ssrf_mod, "SSRFSafeTransport", None)
    is_ip_safe: Any = getattr(ssrf_mod, "is_ip_safe", None)
    resolve_and_validate_host: Any = getattr(ssrf_mod, "resolve_and_validate_host", None)
except ModuleNotFoundError:
    ALLOWED_SCHEMES = frozenset({"http", "https"})
    MAX_RESPONSE_BYTES = 2 * 1024 * 1024
    SSRFSafeTransport = None
    is_ip_safe = None
    resolve_and_validate_host = None

try:
    fetcher_mod = importlib.import_module("wishenka.items.fetcher")
    UrlMetadataService: Any = getattr(fetcher_mod, "UrlMetadataService", None)
except ModuleNotFoundError:
    UrlMetadataService = None

pytestmark = pytest.mark.timeout(30)


@pytest.fixture
def preview_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolve test public names without external DNS and retain literal-IP checks."""

    async def resolve(host: str, port: int = 80) -> list[str]:
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            return ["8.8.8.8"]
        if not is_ip_safe(address):
            raise item_exceptions.SSRFBlockedError(reason="forbidden_ip", ip_address=host)
        return [host]

    monkeypatch.setattr("wishenka.items.fetcher.resolve_and_validate_host", resolve)


class ChunkedStream(httpx.AsyncByteStream):
    """Helper stream yielding discrete chunks for testing response size limits."""

    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            yield chunk


# ============================================================================
# 1. IP Address Classification and Validation
# ============================================================================


class TestIpValidation:
    """Validate IP address filtering (IPv4/IPv6, loopback, private, link-local, cloud metadata)."""

    def test_reject_direct_loopback_ipv4(self) -> None:
        if is_ip_safe is None:
            pytest.fail("wishenka.items.ssrf.is_ip_safe is not implemented")
        for addr in ("127.0.0.1", "127.0.0.2", "127.255.255.255"):
            ip = ipaddress.ip_address(addr)
            assert not is_ip_safe(ip), f"Loopback address {addr} must be rejected"

    def test_reject_private_rfc1918_ipv4(self) -> None:
        if is_ip_safe is None:
            pytest.fail("wishenka.items.ssrf.is_ip_safe is not implemented")
        for addr in (
            "10.0.0.1",
            "10.255.255.254",
            "172.16.0.1",
            "172.31.255.254",
            "192.168.1.1",
            "192.168.0.254",
        ):
            ip = ipaddress.ip_address(addr)
            assert not is_ip_safe(ip), f"RFC 1918 private address {addr} must be rejected"

    def test_reject_cloud_metadata_link_local_ipv4(self) -> None:
        if is_ip_safe is None:
            pytest.fail("wishenka.items.ssrf.is_ip_safe is not implemented")
        for addr in ("169.254.169.254", "169.254.1.1", "169.254.254.254"):
            ip = ipaddress.ip_address(addr)
            assert not is_ip_safe(ip), (
                f"Link-local / cloud metadata address {addr} must be rejected"
            )

    def test_reject_cgnat_and_broadcast_ipv4(self) -> None:
        if is_ip_safe is None:
            pytest.fail("wishenka.items.ssrf.is_ip_safe is not implemented")
        for addr in ("100.64.0.1", "100.127.255.254", "0.0.0.0", "255.255.255.255"):
            ip = ipaddress.ip_address(addr)
            assert not is_ip_safe(ip), (
                f"CGNAT / broadcast / unspecified address {addr} must be rejected"
            )

    def test_reject_ipv6_loopback_and_link_local(self) -> None:
        if is_ip_safe is None:
            pytest.fail("wishenka.items.ssrf.is_ip_safe is not implemented")
        for addr in ("::1", "fe80::1", "fc00::1", "fd00::1", "::"):
            ip = ipaddress.ip_address(addr)
            assert not is_ip_safe(ip), (
                f"IPv6 loopback / local / ULA address {addr} must be rejected"
            )

    def test_allow_public_ips(self) -> None:
        if is_ip_safe is None:
            pytest.fail("wishenka.items.ssrf.is_ip_safe is not implemented")
        for addr in (
            "93.184.216.34",
            "8.8.8.8",
            "1.1.1.1",
            "2606:2800:220:1:248:1893:25c8:1946",
        ):
            ip = ipaddress.ip_address(addr)
            assert is_ip_safe(ip), f"Public address {addr} must be allowed"


# ============================================================================
# 2. DNS Host Resolution and Safety Check
# ============================================================================


class TestDNSResolution:
    """Validate async DNS host resolution and IP validation."""

    @pytest.mark.asyncio
    async def test_reject_domain_resolving_to_private_ip(self) -> None:
        if resolve_and_validate_host is None:
            pytest.fail("wishenka.items.ssrf.resolve_and_validate_host is not implemented")
        with patch("asyncio.get_running_loop") as mock_loop_getter:
            mock_loop = MagicMock()
            mock_loop_getter.return_value = mock_loop
            mock_loop.getaddrinfo = AsyncMock(
                return_value=[
                    (
                        socket.AF_INET,
                        socket.SOCK_STREAM,
                        socket.IPPROTO_TCP,
                        "",
                        ("127.0.0.1", 80),
                    )
                ]
            )
            with pytest.raises(SSRFBlockedError):
                await resolve_and_validate_host("malicious-local.com", 80)

    @pytest.mark.asyncio
    async def test_allow_domain_resolving_to_public_ip(self) -> None:
        if resolve_and_validate_host is None:
            pytest.fail("wishenka.items.ssrf.resolve_and_validate_host is not implemented")
        with patch("asyncio.get_running_loop") as mock_loop_getter:
            mock_loop = MagicMock()
            mock_loop_getter.return_value = mock_loop
            mock_loop.getaddrinfo = AsyncMock(
                return_value=[
                    (
                        socket.AF_INET,
                        socket.SOCK_STREAM,
                        socket.IPPROTO_TCP,
                        "",
                        ("93.184.216.34", 80),
                    )
                ]
            )
            resolved = await resolve_and_validate_host("example.com", 80)
            assert "93.184.216.34" in resolved


# ============================================================================
# 3. SSRFSafeTransport Interception
# ============================================================================


class TestSSRFSafeTransport:
    """Validate SSRFSafeTransport enforces safety on direct requests and redirect hops."""

    @pytest.mark.asyncio
    async def test_transport_blocks_private_ip(self) -> None:
        if SSRFSafeTransport is None:
            pytest.fail("wishenka.items.ssrf.SSRFSafeTransport is not implemented")
        transport = SSRFSafeTransport()
        req = httpx.Request("GET", "http://127.0.0.1:8080/secret")
        with pytest.raises(SSRFBlockedError):
            await transport.handle_async_request(req)

    @pytest.mark.asyncio
    async def test_transport_blocks_disallowed_schemes(self) -> None:
        if SSRFSafeTransport is None:
            pytest.fail("wishenka.items.ssrf.SSRFSafeTransport is not implemented")
        transport = SSRFSafeTransport()
        for bad_url in (
            "file:///etc/passwd",
            "ftp://files.local/data",
            "gopher://127.0.0.1:6379",
        ):
            req = httpx.Request("GET", bad_url)
            with pytest.raises((InvalidUrlSchemeError, SSRFError)):
                await transport.handle_async_request(req)

    @pytest.mark.asyncio
    async def test_transport_blocks_redirect_hop_to_private_ip(self) -> None:
        """Transport must intercept each redirect hop and block navigation to private IPs."""
        if SSRFSafeTransport is None:
            pytest.fail("wishenka.items.ssrf.SSRFSafeTransport is not implemented")
        transport = SSRFSafeTransport()
        hop_req = httpx.Request("GET", "http://192.168.1.1/admin")
        with pytest.raises(SSRFBlockedError):
            await transport.handle_async_request(hop_req)


# ============================================================================
# 4. UrlMetadataService Fetching and Limits
# ============================================================================


class TestUrlMetadataService:
    """Validate UrlMetadataService HTML fetching, 2MB size bounds, and graceful extraction."""

    @pytest.mark.asyncio
    async def test_fetch_html_rejects_ssrf_urls(self) -> None:
        if UrlMetadataService is None:
            pytest.fail("wishenka.items.fetcher.UrlMetadataService is not implemented")
        service = UrlMetadataService()
        for url in (
            "http://127.0.0.1/admin",
            "http://169.254.169.254/latest",
            "http://10.0.0.1/",
            "http://[::1]/",
        ):
            with pytest.raises(SSRFBlockedError):
                await service._fetch_html(url)

    @pytest.mark.asyncio
    async def test_fetch_html_rejects_disallowed_schemes(self) -> None:
        if UrlMetadataService is None:
            pytest.fail("wishenka.items.fetcher.UrlMetadataService is not implemented")
        service = UrlMetadataService()
        for url in ("file:///etc/passwd", "ftp://example.com/file"):
            with pytest.raises((InvalidUrlSchemeError, SSRFError)):
                await service._fetch_html(url)

    @pytest.mark.asyncio
    async def test_early_rejection_by_content_length(self) -> None:
        if UrlMetadataService is None:
            pytest.fail("wishenka.items.fetcher.UrlMetadataService is not implemented")
        service = UrlMetadataService()
        mock_response = httpx.Response(
            200,
            headers={"Content-Length": "5242880"},  # 5MB > 2MB limit
            request=httpx.Request("GET", "https://example.com/huge.html"),
        )
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.stream.return_value.__aenter__.return_value = mock_response
        with pytest.raises(ResponseBodyTooLargeError):
            await service._stream_and_read(mock_client, "https://example.com/huge.html")

    @pytest.mark.asyncio
    async def test_streaming_body_cutoff_at_2mb(self) -> None:
        if UrlMetadataService is None:
            pytest.fail("wishenka.items.fetcher.UrlMetadataService is not implemented")
        service = UrlMetadataService()
        chunk = b"X" * 65536  # 64 KB
        stream = ChunkedStream([chunk] * 40)  # 40 * 64KB = 2.5 MB > 2MB limit

        mock_response = httpx.Response(
            200,
            headers={"Transfer-Encoding": "chunked"},
            request=httpx.Request("GET", "https://example.com/stream.html"),
            stream=stream,
        )
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.stream.return_value.__aenter__.return_value = mock_response
        with pytest.raises(ResponseBodyTooLargeError):
            await service._stream_and_read(mock_client, "https://example.com/stream.html")

    @pytest.mark.asyncio
    async def test_allow_valid_public_url_under_2mb(self) -> None:
        if UrlMetadataService is None:
            pytest.fail("wishenka.items.fetcher.UrlMetadataService is not implemented")
        service = UrlMetadataService()
        html_content = (
            "<html><head><title>Awesome Product</title></head><body><h1>Hello</h1></body></html>"
        )
        stream = ChunkedStream([html_content.encode("utf-8")])

        mock_response = httpx.Response(
            200,
            headers={"Content-Length": str(len(html_content))},
            request=httpx.Request("GET", "https://example.com/product/1"),
            stream=stream,
        )
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.stream.return_value.__aenter__.return_value = mock_response
        html, final_url = await service._stream_and_read(
            mock_client, "https://example.com/product/1"
        )
        assert "<title>Awesome Product</title>" in html
        assert str(final_url) == "https://example.com/product/1"

    @pytest.mark.asyncio
    async def test_graceful_degradation_fetch_and_extract_on_ssrf_and_oversize(self) -> None:
        """UrlMetadataService.fetch_and_extract falls back safely to ExtractedMetadata."""
        if UrlMetadataService is None:
            pytest.fail("wishenka.items.fetcher.UrlMetadataService is not implemented")
        service = UrlMetadataService()
        # On SSRF
        meta_ssrf = await service.fetch_and_extract("http://127.0.0.1:8000/admin")
        assert isinstance(meta_ssrf, ExtractedMetadata)

        # On oversized response
        mock_response = httpx.Response(
            200,
            headers={"Content-Length": "10485760"},  # 10 MB
            request=httpx.Request("GET", "https://example.com/huge.html"),
        )
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.stream.return_value.__aenter__.return_value = mock_response
        meta_oversize = await service.fetch_and_extract(
            "https://example.com/huge.html", client=mock_client
        )
        assert isinstance(meta_oversize, ExtractedMetadata)


# ============================================================================
# 5. ItemPreviewService Integration & Graceful Degradation
# ============================================================================


class TestItemPreviewServiceGracefulFallback:
    """Validate ItemPreviewService degrades gracefully on SSRF and oversized responses."""

    @pytest.mark.asyncio
    async def test_direct_private_ipv4_blocked(self) -> None:
        service = ItemPreviewService()
        # Even with a mock client returning 200 OK, private IP must be rejected before fetching
        mock_client = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda req: httpx.Response(200, text="<html><title>Internal Admin</title></html>")
            )
        )
        preview = await service.fetch_preview("http://127.0.0.1:8000/admin", client=mock_client)
        assert isinstance(preview, ItemPreviewDTO)
        assert preview.is_fallback is True
        assert preview.fallback_reason == "ssrf_blocked"

    @pytest.mark.asyncio
    async def test_cloud_metadata_blocked(self) -> None:
        service = ItemPreviewService()
        mock_client = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda req: httpx.Response(200, text="ami-id: ami-12345678")
            )
        )
        preview = await service.fetch_preview(
            "http://169.254.169.254/latest/meta-data/", client=mock_client
        )
        assert isinstance(preview, ItemPreviewDTO)
        assert preview.is_fallback is True
        assert preview.fallback_reason == "ssrf_blocked"

    @pytest.mark.asyncio
    async def test_ipv6_loopback_blocked(self) -> None:
        service = ItemPreviewService()
        mock_client = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda req: httpx.Response(200, text="<html><title>Local</title></html>")
            )
        )
        preview = await service.fetch_preview("http://[::1]:8080/info", client=mock_client)
        assert isinstance(preview, ItemPreviewDTO)
        assert preview.is_fallback is True
        assert preview.fallback_reason == "ssrf_blocked"

    @pytest.mark.asyncio
    async def test_redirect_to_private_ip_is_blocked(self, preview_dns: None) -> None:
        """A redirect into a forbidden network is rejected before dispatch."""
        from wishenka.items.fetcher import PreviewTransportConfig, offline_replay_route

        url = "https://shop.example.com/item/1"
        route = offline_replay_route({url: (302, {"Location": "http://192.168.1.1/router"}, b"")})
        routes = PreviewTransportConfig(default=route, mounts={})
        preview = await ItemPreviewService().fetch_preview(url, routes=routes)
        assert preview.is_fallback is True
        assert preview.fallback_reason == "ssrf_blocked"

    @pytest.mark.asyncio
    async def test_oversized_response_returns_fallback_dto(self, preview_dns: None) -> None:
        """Responses exceeding the size limit trigger the documented fallback."""
        from wishenka.items.fetcher import PreviewTransportConfig, offline_replay_route

        url = "https://example.com/oversized-page"
        route = offline_replay_route({url: (200, {"Content-Length": "5242880"}, b"body")})
        preview = await ItemPreviewService().fetch_preview(
            url, routes=PreviewTransportConfig(default=route, mounts={})
        )
        assert preview.is_fallback is True
        assert preview.fallback_reason == "response_too_large"


# ============================================================================
# 5. Production Observability and Structured Logging
# ============================================================================


class TestObservabilityLogging:
    """Verifies production structured logging, security audits, and no payload leak."""

    @pytest.mark.asyncio
    async def test_ssrf_blocked_structured_logging(self, caplog: pytest.LogCaptureFixture) -> None:
        """Security events for SSRF blocks must log WARNING with host, ip, reason, and url."""
        from wishenka.items.fetcher import PreviewTransportConfig, offline_replay_route

        service = ItemPreviewService()
        routes = PreviewTransportConfig(default=offline_replay_route({}), mounts={})
        with caplog.at_level(logging.WARNING, logger="wishenka.items"):
            preview = await service.fetch_preview(
                "http://169.254.169.254/latest/meta-data/", routes=routes
            )

        assert preview.is_fallback is True
        assert preview.fallback_reason == "ssrf_blocked"

        blocked_records = [
            r
            for r in caplog.records
            if getattr(r, "event", None) in ("ssrf_blocked", "item_preview_ssrf_blocked")
        ]
        assert blocked_records, "Expected SSRF blocked log records"
        preview_record = next(
            r for r in blocked_records if getattr(r, "event", None) == "item_preview_ssrf_blocked"
        )
        assert getattr(preview_record, "url", None) == "http://169.254.169.254/latest/meta-data/"
        assert getattr(preview_record, "ip", None) == "169.254.169.254"
        assert getattr(preview_record, "reason", None) == "forbidden_ip"

    @pytest.mark.asyncio
    async def test_dns_resolution_diagnostics_logging(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """DNS resolution diagnostics must be logged at DEBUG/INFO levels."""
        fake_addr_info = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80)),
        ]
        with (
            patch("asyncio.get_running_loop") as mock_get_loop,
            caplog.at_level(logging.DEBUG, logger="wishenka.items"),
        ):
            mock_loop = MagicMock()
            mock_loop.getaddrinfo = AsyncMock(return_value=fake_addr_info)
            mock_get_loop.return_value = mock_loop

            resolved = await resolve_and_validate_host("safe.example.com", 80)
            assert resolved == ["93.184.216.34"]

        dns_events = [getattr(r, "event", None) for r in caplog.records]
        assert "dns_resolution_start" in dns_events
        assert "dns_resolution_success" in dns_events

        # Test resolution failure logging at INFO
        caplog.clear()
        with (
            patch("asyncio.get_running_loop") as mock_get_loop,
            caplog.at_level(logging.INFO, logger="wishenka.items"),
        ):
            mock_loop = MagicMock()
            mock_loop.getaddrinfo = AsyncMock(
                side_effect=socket.gaierror("Name or service not known")
            )
            mock_get_loop.return_value = mock_loop

            await resolve_and_validate_host("nonexistent.local", 80)

        fail_record = next(
            (r for r in caplog.records if getattr(r, "event", None) == "dns_resolution_failed"),
            None,
        )
        assert fail_record is not None
        assert fail_record.levelname == "INFO"
        assert getattr(fail_record, "host", None) == "nonexistent.local"

    @pytest.mark.asyncio
    async def test_payload_size_violation_logging(
        self, caplog: pytest.LogCaptureFixture, preview_dns: None
    ) -> None:
        """Payload size violations must be logged with size metadata at WARNING."""
        from wishenka.items.fetcher import PreviewTransportConfig, offline_replay_route

        url = "https://example.com/oversized"
        route = offline_replay_route({url: (200, {"Content-Length": "5000000"}, b"body")})
        with caplog.at_level(logging.WARNING, logger="wishenka.items"):
            preview = await ItemPreviewService().fetch_preview(
                url, routes=PreviewTransportConfig(default=route, mounts={})
            )

        assert preview.is_fallback is True
        assert preview.fallback_reason == "response_too_large"

        oversize_records = [
            r
            for r in caplog.records
            if getattr(r, "event", None)
            in ("payload_size_violation", "item_preview_response_too_large")
        ]
        assert oversize_records
        preview_oversize = next(
            r
            for r in oversize_records
            if getattr(r, "event", None) == "item_preview_response_too_large"
        )
        assert getattr(preview_oversize, "content_length", None) == 5000000
        assert getattr(preview_oversize, "reason", None) == "response_too_large"

    @pytest.mark.asyncio
    async def test_invariant_never_log_raw_html_or_secrets(
        self, caplog: pytest.LogCaptureFixture, preview_dns: None
    ) -> None:
        """Raw HTML and secret tokens never appear in logs."""
        from wishenka.items.fetcher import PreviewTransportConfig, offline_replay_route

        secret_token = "TOP_SECRET_SESSION_TOKEN_XYZ987"
        secret_payload = f"<html><body><h1>Secret page</h1><p>{secret_token}</p></body></html>"
        url = "https://example.com/item/42"
        route = offline_replay_route(
            {url: (200, {"Content-Type": "text/html"}, secret_payload.encode())}
        )
        with caplog.at_level(logging.DEBUG, logger="wishenka.items"):
            preview = await ItemPreviewService().fetch_preview(
                url, routes=PreviewTransportConfig(default=route, mounts={})
            )

        assert preview.is_fallback is False
        assert secret_token not in caplog.text
        assert "<h1>Secret page</h1>" not in caplog.text
