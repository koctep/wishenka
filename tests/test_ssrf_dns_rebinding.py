"""Automated failing repro tests for WISHENKA-92 (DNS rebinding / TOCTOU prevention).

Verifies that SSRFSafeTransport pins the validated IP address from DNS resolution
directly into the underlying network backend without re-resolving the hostname at
TCP connect time, while preserving Host headers, TLS SNI/certificate verification,
redirect-hop pinning, and graceful fallback.
"""

import asyncio
import socket
import ssl
from typing import Any
from unittest.mock import patch

import httpcore
import httpx
import pytest

from wishenka.items.exceptions import SSRFBlockedError
from wishenka.items.fetcher import UrlMetadataService
from wishenka.items.models import ExtractedMetadata
from wishenka.items.ssrf import SSRFSafeNetworkBackend, SSRFSafeTransport, _pinned_ips_var

pytestmark = pytest.mark.timeout(30)


def test_transport_rejects_unexpected_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unsupported HTTPX pool must never produce an unpinned transport."""

    def init_with_unknown_pool(self: httpx.AsyncHTTPTransport, *args: Any, **kwargs: Any) -> None:
        self._pool = object()  # type: ignore[assignment]

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "__init__", init_with_unknown_pool)
    with pytest.raises(RuntimeError, match="SSRF-safe"):
        SSRFSafeTransport()


@pytest.mark.asyncio
async def test_transport_rejects_replaced_backend_before_dispatch() -> None:
    """Removing the installed backend after construction fails closed."""
    transport = SSRFSafeTransport()
    original_backend = transport._pool._network_backend
    assert isinstance(original_backend, SSRFSafeNetworkBackend)
    try:
        transport._pool._network_backend = original_backend._inner
        with pytest.raises(SSRFBlockedError, match="backend unavailable"):
            await transport.handle_async_request(httpx.Request("GET", "https://example.com"))
    finally:
        transport._pool._network_backend = original_backend
        await transport.aclose()


def _make_addrinfo(ip: str, port: int) -> list[tuple[Any, ...]]:
    family = socket.AF_INET6 if ":" in ip else socket.AF_INET
    sockaddr = (ip, port, 0, 0) if family == socket.AF_INET6 else (ip, port)
    return [(family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", sockaddr)]


class _FakeAsyncNetworkStream(httpcore.AsyncNetworkStream):
    """Minimal in-memory AsyncNetworkStream speaking HTTP/1.1 for transport tests."""

    def __init__(
        self,
        raw_response: bytes,
        *,
        tls_error: Exception | None = None,
    ) -> None:
        self._response = raw_response
        self._read_pos = 0
        self._tls_error = tls_error
        self.written_chunks: list[bytes] = []
        self.sni_hostnames: list[str | None] = []
        self.closed = False

    async def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        if self._read_pos >= len(self._response):
            return b""
        chunk = self._response[self._read_pos : self._read_pos + max_bytes]
        self._read_pos += len(chunk)
        return chunk

    async def write(self, buffer: bytes, timeout: float | None = None) -> None:
        self.written_chunks.append(buffer)

    async def aclose(self) -> None:
        self.closed = True

    async def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> httpcore.AsyncNetworkStream:
        self.sni_hostnames.append(server_hostname)
        if self._tls_error is not None:
            raise self._tls_error
        return self

    def get_extra_info(self, info: str) -> Any:
        if info == "is_readable":
            return self._read_pos < len(self._response)
        return None


def _http_response(
    status_line: str,
    body: bytes = b"",
    headers: dict[str, str] | None = None,
) -> bytes:
    all_headers = {"Content-Length": str(len(body)), "Connection": "close"}
    if headers:
        all_headers.update(headers)
    header_lines = "".join(f"{k}: {v}\r\n" for k, v in all_headers.items())
    return f"HTTP/1.1 {status_line}\r\n{header_lines}\r\n".encode("ascii") + body


class TestSSRFZeroToctouIpPinning:
    """Validate IP pinning at the network backend boundary to eliminate DNS rebinding."""

    async def test_zero_toctou_pinned_ip_passed_to_connect_tcp(self) -> None:
        """Validated IP must be passed to connect_tcp without re-resolving hostname."""
        dns_calls: list[str] = []
        connect_calls: list[tuple[str, int]] = []
        streams: list[_FakeAsyncNetworkStream] = []

        async def fake_getaddrinfo(
            host: str, port: Any, *args: Any, **kwargs: Any
        ) -> list[tuple[Any, ...]]:
            dns_calls.append(host)
            # Simulate DNS rebinding (TTL=0): 1st lookup returns public IP, 2nd returns loopback.
            if len(dns_calls) == 1:
                return _make_addrinfo("93.184.216.34", int(port))
            return _make_addrinfo("127.0.0.1", int(port))

        async def fake_connect_tcp(
            self_backend: Any,
            host: str,
            port: int,
            timeout: float | None = None,
            local_address: str | None = None,
            socket_options: Any = None,
        ) -> httpcore.AsyncNetworkStream:
            connect_calls.append((host, port))
            stream = _FakeAsyncNetworkStream(_http_response("200 OK", b"ok"))
            streams.append(stream)
            return stream

        loop = asyncio.get_running_loop()
        transport = SSRFSafeTransport()
        try:
            with (
                patch.object(loop, "getaddrinfo", side_effect=fake_getaddrinfo),
                patch("httpcore._backends.auto.AutoBackend.connect_tcp", fake_connect_tcp),
            ):
                response = await transport.handle_async_request(
                    httpx.Request("GET", "https://rebind.example/item")
                )
                await response.aread()
        finally:
            await transport.aclose()

        assert dns_calls == ["rebind.example"]
        assert connect_calls == [("93.184.216.34", 443)], (
            f"Expected connect_tcp to receive pinned IP '93.184.216.34', got {connect_calls}"
        )

    async def test_redirect_hop_pinning(self) -> None:
        """Each redirect hop must resolve and pin its own validated IP in connect_tcp."""
        connect_calls: list[tuple[str, int]] = []
        ip_map = {
            "shop.example": "93.184.216.34",
            "cdn.example": "151.101.1.69",
        }

        async def fake_getaddrinfo(
            host: str, port: Any, *args: Any, **kwargs: Any
        ) -> list[tuple[Any, ...]]:
            return _make_addrinfo(ip_map[host], int(port))

        async def fake_connect_tcp(
            self_backend: Any,
            host: str,
            port: int,
            timeout: float | None = None,
            local_address: str | None = None,
            socket_options: Any = None,
        ) -> httpcore.AsyncNetworkStream:
            connect_calls.append((host, port))
            if len(connect_calls) == 1:
                raw = _http_response(
                    "302 Found",
                    headers={"Location": "https://cdn.example/product"},
                )
            else:
                raw = _http_response("200 OK", b"<html><title>Item</title></html>")
            return _FakeAsyncNetworkStream(raw)

        loop = asyncio.get_running_loop()
        transport = SSRFSafeTransport()
        async with httpx.AsyncClient(transport=transport, follow_redirects=True) as client:
            with (
                patch.object(loop, "getaddrinfo", side_effect=fake_getaddrinfo),
                patch("httpcore._backends.auto.AutoBackend.connect_tcp", fake_connect_tcp),
            ):
                response = await client.get("https://shop.example/start")

        assert response.status_code == 200
        assert str(response.url) == "https://cdn.example/product"
        assert connect_calls == [
            ("93.184.216.34", 443),
            ("151.101.1.69", 443),
        ], f"Expected pinned IPs per redirect hop, got {connect_calls}"

    async def test_preserves_host_header_tls_sni_and_response_url(self) -> None:
        """Connecting by pinned IP must preserve Host header, TLS SNI, and response.url."""
        connect_calls: list[tuple[str, int]] = []
        streams: list[_FakeAsyncNetworkStream] = []

        async def fake_getaddrinfo(
            host: str, port: Any, *args: Any, **kwargs: Any
        ) -> list[tuple[Any, ...]]:
            return _make_addrinfo("93.184.216.34", int(port))

        async def fake_connect_tcp(
            self_backend: Any,
            host: str,
            port: int,
            timeout: float | None = None,
            local_address: str | None = None,
            socket_options: Any = None,
        ) -> httpcore.AsyncNetworkStream:
            connect_calls.append((host, port))
            stream = _FakeAsyncNetworkStream(_http_response("200 OK", b"ok"))
            streams.append(stream)
            return stream

        loop = asyncio.get_running_loop()
        transport = SSRFSafeTransport()
        async with httpx.AsyncClient(transport=transport) as client:
            with (
                patch.object(loop, "getaddrinfo", side_effect=fake_getaddrinfo),
                patch("httpcore._backends.auto.AutoBackend.connect_tcp", fake_connect_tcp),
            ):
                response = await client.get("https://shop.example/item")

        assert connect_calls == [("93.184.216.34", 443)]
        assert len(streams) == 1
        assert streams[0].sni_hostnames == ["shop.example"]
        raw_request = b"".join(streams[0].written_chunks).lower()
        assert b"host: shop.example\r\n" in raw_request
        assert str(response.url) == "https://shop.example/item"

    async def test_graceful_fallback_on_ssrf_or_tls_error(self) -> None:
        """UrlMetadataService.fetch_and_extract must return fallback on SSRF or TLS error."""
        service = UrlMetadataService()
        loop = asyncio.get_running_loop()

        # Case 1: SSRF blocked (loopback IP returned by DNS)
        async def fake_getaddrinfo_blocked(
            host: str, port: Any, *args: Any, **kwargs: Any
        ) -> list[tuple[Any, ...]]:
            return _make_addrinfo("127.0.0.1", int(port))

        with patch.object(loop, "getaddrinfo", side_effect=fake_getaddrinfo_blocked):
            result_ssrf = await service.fetch_and_extract("https://shop.example/item")

        assert isinstance(result_ssrf, ExtractedMetadata)
        assert result_ssrf.title is None
        assert result_ssrf.store_name == "shop.example"

        # Case 2: TLS certificate mismatch when connecting to pinned IP
        async def fake_getaddrinfo_public(
            host: str, port: Any, *args: Any, **kwargs: Any
        ) -> list[tuple[Any, ...]]:
            return _make_addrinfo("93.184.216.34", int(port))

        async def fake_connect_tcp_tls_fail(
            self_backend: Any,
            host: str,
            port: int,
            timeout: float | None = None,
            local_address: str | None = None,
            socket_options: Any = None,
        ) -> httpcore.AsyncNetworkStream:
            return _FakeAsyncNetworkStream(
                _http_response("200 OK", b"ok"),
                tls_error=ssl.SSLCertVerificationError("hostname mismatch"),
            )

        with (
            patch.object(loop, "getaddrinfo", side_effect=fake_getaddrinfo_public),
            patch("httpcore._backends.auto.AutoBackend.connect_tcp", fake_connect_tcp_tls_fail),
        ):
            result_tls = await service.fetch_and_extract("https://shop.example/item")

        assert isinstance(result_tls, ExtractedMetadata)
        assert result_tls.title is None
        assert result_tls.store_name == "shop.example"

    async def test_ipv6_pinning_domain_and_literal(self) -> None:
        """Public IPv6 addresses (resolved or literal) must be pinned unbracketed in connect_tcp."""
        ipv6_addr = "2606:2800:220:1:248:1893:25c8:1946"
        connect_calls: list[tuple[str, int]] = []
        streams: list[_FakeAsyncNetworkStream] = []

        async def fake_getaddrinfo(
            host: str, port: Any, *args: Any, **kwargs: Any
        ) -> list[tuple[Any, ...]]:
            return _make_addrinfo(ipv6_addr, int(port))

        async def fake_connect_tcp(
            self_backend: Any,
            host: str,
            port: int,
            timeout: float | None = None,
            local_address: str | None = None,
            socket_options: Any = None,
        ) -> httpcore.AsyncNetworkStream:
            connect_calls.append((host, port))
            stream = _FakeAsyncNetworkStream(_http_response("200 OK", b"ok-v6"))
            streams.append(stream)
            return stream

        loop = asyncio.get_running_loop()
        transport = SSRFSafeTransport()
        async with httpx.AsyncClient(transport=transport) as client:
            with (
                patch.object(loop, "getaddrinfo", side_effect=fake_getaddrinfo),
                patch("httpcore._backends.auto.AutoBackend.connect_tcp", fake_connect_tcp),
            ):
                resp_domain = await client.get("https://ipv6.example/item")
                resp_literal = await client.get(f"http://[{ipv6_addr}]:8080/direct")

        assert resp_domain.status_code == 200
        assert resp_literal.status_code == 200
        assert connect_calls == [
            (ipv6_addr, 443),
            (ipv6_addr, 8080),
        ]
        assert streams[0].sni_hostnames == ["ipv6.example"]
        assert b"host: ipv6.example\r\n" in b"".join(streams[0].written_chunks).lower()

    async def test_multi_ip_failover_without_re_resolving_dns(self) -> None:
        """If the first pinned IP fails to connect, backend tries the next pinned IP in order."""
        ipv6_addr = "2606:2800:220:1:248:1893:25c8:1946"
        ipv4_addr = "93.184.216.34"
        dns_calls: list[str] = []
        connect_calls: list[tuple[str, int]] = []

        async def fake_getaddrinfo(
            host: str, port: Any, *args: Any, **kwargs: Any
        ) -> list[tuple[Any, ...]]:
            dns_calls.append(host)
            return _make_addrinfo(ipv6_addr, int(port)) + _make_addrinfo(ipv4_addr, int(port))

        async def fake_connect_tcp(
            self_backend: Any,
            host: str,
            port: int,
            timeout: float | None = None,
            local_address: str | None = None,
            socket_options: Any = None,
        ) -> httpcore.AsyncNetworkStream:
            connect_calls.append((host, port))
            if host == ipv6_addr:
                raise httpcore.ConnectError("IPv6 unreachable")
            return _FakeAsyncNetworkStream(_http_response("200 OK", b"ok-fallback"))

        loop = asyncio.get_running_loop()
        transport = SSRFSafeTransport()
        async with httpx.AsyncClient(transport=transport) as client:
            with (
                patch.object(loop, "getaddrinfo", side_effect=fake_getaddrinfo),
                patch("httpcore._backends.auto.AutoBackend.connect_tcp", fake_connect_tcp),
            ):
                response = await client.get("https://dualstack.example/item")

        assert response.status_code == 200
        assert response.text == "ok-fallback"
        assert dns_calls == ["dualstack.example"]
        assert connect_calls == [
            (ipv6_addr, 443),
            (ipv4_addr, 443),
        ]

    async def test_concurrent_tasks_contextvar_isolation(self) -> None:
        """Concurrent requests on a shared transport must not leak pinned IPs across tasks."""
        ip_map = {
            "alpha.example": "93.184.216.34",
            "beta.example": "151.101.1.69",
        }
        observed: dict[str, list[str]] = {"alpha.example": [], "beta.example": []}

        async def fake_getaddrinfo(
            host: str, port: Any, *args: Any, **kwargs: Any
        ) -> list[tuple[Any, ...]]:
            await asyncio.sleep(0)
            return _make_addrinfo(ip_map[host], int(port))

        async def fake_connect_tcp(
            self_backend: Any,
            host: str,
            port: int,
            timeout: float | None = None,
            local_address: str | None = None,
            socket_options: Any = None,
        ) -> httpcore.AsyncNetworkStream:
            await asyncio.sleep(0)
            # Record which IP was connected; we will verify via response body & SNI below.
            return _FakeAsyncNetworkStream(_http_response("200 OK", host.encode("ascii")))

        loop = asyncio.get_running_loop()
        transport = SSRFSafeTransport()
        async with httpx.AsyncClient(transport=transport) as client:
            with (
                patch.object(loop, "getaddrinfo", side_effect=fake_getaddrinfo),
                patch("httpcore._backends.auto.AutoBackend.connect_tcp", fake_connect_tcp),
            ):
                resp_a, resp_b = await asyncio.gather(
                    client.get("https://alpha.example/1"),
                    client.get("https://beta.example/2"),
                )

        observed["alpha.example"].append(resp_a.text)
        observed["beta.example"].append(resp_b.text)
        assert observed == {
            "alpha.example": ["93.184.216.34"],
            "beta.example": ["151.101.1.69"],
        }
        assert _pinned_ips_var.get() is None

    async def test_backend_defense_in_depth_and_uds_blocked(self) -> None:
        """Backend blocks Unix domain sockets and validates IPs even if called directly."""
        transport = SSRFSafeTransport()
        try:
            backend = transport._pool._network_backend
            with pytest.raises(SSRFBlockedError):
                await backend.connect_unix_socket("/var/run/docker.sock")
            with pytest.raises(SSRFBlockedError):
                await backend.connect_tcp("127.0.0.1", 80)
        finally:
            await transport.aclose()
