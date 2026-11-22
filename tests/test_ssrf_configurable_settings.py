"""Automated failing repro tests for WISHENKA-93 (Configurable SSRF Settings).

Verifies:
1. Default SSRF settings on ``Settings()`` and backward compatibility of
   ``wishenka.items`` / ``wishenka.items.ssrf`` constants.
2. Independent ``WISHENKA_SSRF_*`` env overrides in both CSV and JSON array formats.
3. Fail-fast ``pydantic.ValidationError`` on invalid sizes, schemes, and CIDRs.
4. Enforcement across ``is_ip_safe`` (including IPv4-mapped IPv6),
   ``resolve_and_validate_host`` + ``DNSCache`` policy isolation, baseline invariant
   preservation when ``ssrf_forbidden_cidrs`` is empty, and ``SSRFSafeTransport``.
5. End-to-end policy propagation through ``UrlMetadataService``, ``ItemPreviewService``,
   ``PreviewCache`` revalidation, ``create_app(settings)`` / ``items_ui`` fallback, and
   ``wishenka.bot.__main__.run()``.
"""

from __future__ import annotations

import asyncio
import importlib
import ipaddress
import json
import logging
import socket
import ssl
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import httpcore
import httpx
import pytest
from aiogram import Dispatcher, Router
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

import wishenka.bot.__main__ as bot_main
from wishenka.auth.models import AuthenticatedUser
from wishenka.auth.session import SessionTokenService
from wishenka.config import Settings
from wishenka.items.exceptions import (
    InvalidUrlSchemeError,
    ResponseBodyTooLargeError,
    SSRFBlockedError,
)
from wishenka.items.preview_cache import PreviewCache
from wishenka.items.schemas import ItemPreviewDTO
from wishenka.items.service import ItemPreviewService
from wishenka.logging import JsonFormatter
from wishenka.web.app import create_app

pytestmark = pytest.mark.timeout(30)

config_mod: Any = importlib.import_module("wishenka.config")
items_mod: Any = importlib.import_module("wishenka.items")
ssrf_mod: Any = importlib.import_module("wishenka.items.ssrf")
fetcher_mod: Any = importlib.import_module("wishenka.items.fetcher")

EXPECTED_DEFAULT_FORBIDDEN_CIDRS: tuple[str, ...] = (
    "0.0.0.0/8",
    "10.0.0.0/8",
    "100.64.0.0/10",
    "127.0.0.0/8",
    "169.254.0.0/16",
    "172.16.0.0/12",
    "192.0.0.0/24",
    "192.0.2.0/24",
    "192.168.0.0/16",
    "198.18.0.0/15",
    "198.51.100.0/24",
    "203.0.113.0/24",
    "224.0.0.0/4",
    "240.0.0.0/4",
    "255.255.255.255/32",
    "::/128",
    "::1/128",
    "fc00::/7",
    "fe80::/10",
    "ff00::/8",
)


@pytest.fixture(autouse=True)
def _clear_ssrf_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep ambient WISHENKA_SSRF_* environment variables from leaking across tests."""
    for env_name in (
        "WISHENKA_SSRF_MAX_RESPONSE_BYTES",
        "WISHENKA_SSRF_ALLOWED_SCHEMES",
        "WISHENKA_SSRF_FORBIDDEN_CIDRS",
    ):
        monkeypatch.delenv(env_name, raising=False)


def _new_settings(**kwargs: Any) -> Any:
    """Construct Settings with dynamic kwargs before Step 4 adds fields."""
    settings_cls: Any = Settings
    return settings_cls(**kwargs)


def _make_addrinfo(ip: str, port: int) -> list[tuple[Any, ...]]:
    family = socket.AF_INET6 if ":" in ip else socket.AF_INET
    sockaddr = (ip, port, 0, 0) if family == socket.AF_INET6 else (ip, port)
    return [(family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", sockaddr)]


class _ChunkedStream(httpx.AsyncByteStream):
    """Stream discrete byte chunks for streaming size-limit tests."""

    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            yield chunk


class _FakeAsyncNetworkStream(httpcore.AsyncNetworkStream):
    """In-memory HTTP/1.1 AsyncNetworkStream for offline SSRFSafeTransport tests."""

    def __init__(self, raw_response: bytes) -> None:
        self._response = raw_response
        self._read_pos = 0
        self.closed = False

    async def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        if self._read_pos >= len(self._response):
            return b""
        chunk = self._response[self._read_pos : self._read_pos + max_bytes]
        self._read_pos += len(chunk)
        return chunk

    async def write(self, buffer: bytes, timeout: float | None = None) -> None:
        return None

    async def aclose(self) -> None:
        self.closed = True

    async def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> httpcore.AsyncNetworkStream:
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


# ============================================================================
# 1. Defaults & Backward Compatibility
# ============================================================================


def test_settings_defaults_and_backward_compatibility() -> None:
    """Settings exposes SSRF defaults matching wishenka.items and wishenka.items.ssrf."""
    settings: Any = Settings()

    assert settings.ssrf_max_response_bytes == 2 * 1024 * 1024
    assert settings.ssrf_allowed_schemes == ("http", "https")
    assert settings.ssrf_forbidden_cidrs == EXPECTED_DEFAULT_FORBIDDEN_CIDRS

    assert getattr(config_mod, "DEFAULT_SSRF_MAX_RESPONSE_BYTES", None) == 2 * 1024 * 1024
    assert getattr(config_mod, "DEFAULT_SSRF_ALLOWED_SCHEMES", None) == ("http", "https")
    assert getattr(config_mod, "SUPPORTED_SSRF_SCHEMES", None) == frozenset({"http", "https"})
    assert getattr(config_mod, "DEFAULT_SSRF_FORBIDDEN_CIDRS", None) == (
        EXPECTED_DEFAULT_FORBIDDEN_CIDRS
    )

    assert settings.ssrf_max_response_bytes == ssrf_mod.MAX_RESPONSE_BYTES
    assert settings.ssrf_max_response_bytes == items_mod.MAX_RESPONSE_BYTES
    assert frozenset(settings.ssrf_allowed_schemes) == ssrf_mod.ALLOWED_SCHEMES
    assert frozenset(settings.ssrf_allowed_schemes) == items_mod.ALLOWED_SCHEMES
    assert (
        tuple(ipaddress.ip_network(cidr) for cidr in settings.ssrf_forbidden_cidrs)
        == ssrf_mod.FORBIDDEN_NETWORKS
    )


def test_ssrf_policy_from_settings_immutable_and_matches_fields() -> None:
    """SSRFPolicy builds an immutable policy snapshot from default and custom Settings."""
    policy_cls = getattr(ssrf_mod, "SSRFPolicy", None)
    assert policy_cls is not None, "wishenka.items.ssrf.SSRFPolicy is not implemented"

    default_policy = policy_cls.from_settings(Settings())
    assert default_policy.max_response_bytes == 2 * 1024 * 1024
    assert default_policy.allowed_schemes == frozenset({"http", "https"})
    assert default_policy.forbidden_networks == ssrf_mod.FORBIDDEN_NETWORKS

    with pytest.raises(AttributeError):
        default_policy.max_response_bytes = 123

    custom_settings = _new_settings(
        ssrf_max_response_bytes=4096,
        ssrf_allowed_schemes=("https",),
        ssrf_forbidden_cidrs=("93.184.216.0/24", "2001:db8::/32"),
    )
    custom_policy = policy_cls.from_settings(custom_settings)
    assert custom_policy.max_response_bytes == 4096
    assert custom_policy.allowed_schemes == frozenset({"https"})
    assert custom_policy.forbidden_networks == (
        ipaddress.ip_network("93.184.216.0/24"),
        ipaddress.ip_network("2001:db8::/32"),
    )


# ============================================================================
# 2. Independent WISHENKA_SSRF_* Env Overrides (CSV & JSON)
# ============================================================================


def test_env_override_max_response_bytes_preserves_other_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Overriding WISHENKA_SSRF_MAX_RESPONSE_BYTES leaves schemes and CIDRs at defaults."""
    monkeypatch.setenv("WISHENKA_SSRF_MAX_RESPONSE_BYTES", "1024")
    settings: Any = Settings()

    assert settings.ssrf_max_response_bytes == 1024
    assert settings.ssrf_allowed_schemes == ("http", "https")
    assert settings.ssrf_forbidden_cidrs == EXPECTED_DEFAULT_FORBIDDEN_CIDRS


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("https", ("https",)),
        ("HTTP, https", ("http", "https")),
        ("https, HTTPS", ("https",)),
        ('["HTTPS"]', ("https",)),
        ('["https", "http"]', ("https", "http")),
    ],
)
def test_env_override_allowed_schemes_csv_and_json(
    monkeypatch: pytest.MonkeyPatch,
    raw_value: str,
    expected: tuple[str, ...],
) -> None:
    """WISHENKA_SSRF_ALLOWED_SCHEMES accepts both CSV and JSON arrays and normalizes case."""
    monkeypatch.setenv("WISHENKA_SSRF_ALLOWED_SCHEMES", raw_value)
    settings: Any = Settings()

    assert settings.ssrf_allowed_schemes == expected
    assert settings.ssrf_max_response_bytes == 2 * 1024 * 1024
    assert settings.ssrf_forbidden_cidrs == EXPECTED_DEFAULT_FORBIDDEN_CIDRS


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("93.184.216.0/24, 2001:db8::/32", ("93.184.216.0/24", "2001:db8::/32")),
        ('["93.184.216.0/24"]', ("93.184.216.0/24",)),
        ('["93.184.216.34/24", "93.184.216.0/24"]', ("93.184.216.0/24",)),
        ("[]", ()),
    ],
)
def test_env_override_forbidden_cidrs_csv_and_json(
    monkeypatch: pytest.MonkeyPatch,
    raw_value: str,
    expected: tuple[str, ...],
) -> None:
    """WISHENKA_SSRF_FORBIDDEN_CIDRS accepts CSV, JSON arrays, canonicalization, and '[]'."""
    monkeypatch.setenv("WISHENKA_SSRF_FORBIDDEN_CIDRS", raw_value)
    settings: Any = Settings()

    assert settings.ssrf_forbidden_cidrs == expected
    assert settings.ssrf_max_response_bytes == 2 * 1024 * 1024
    assert settings.ssrf_allowed_schemes == ("http", "https")


def test_dotenv_file_overrides_default_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Default policy helpers respect SSRF settings loaded from a .env file in cwd."""
    (tmp_path / ".env").write_text(
        "WISHENKA_SSRF_MAX_RESPONSE_BYTES=2048\n"
        "WISHENKA_SSRF_ALLOWED_SCHEMES=https\n"
        "WISHENKA_SSRF_FORBIDDEN_CIDRS=93.184.216.0/24\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    service: Any = fetcher_mod.UrlMetadataService()
    assert service.max_bytes == 2048
    assert not ssrf_mod.is_ip_safe("93.184.216.34")


# ============================================================================
# 3. Fail-Fast Startup Validation (pydantic.ValidationError)
# ============================================================================


@pytest.mark.parametrize("bad_value", [0, -1, "0", "-5", "", "not-an-int", True, False, 1.5])
def test_invalid_max_response_bytes_direct_raises_validation_error(bad_value: Any) -> None:
    """Invalid ssrf_max_response_bytes values fail fast on Settings instantiation."""
    with pytest.raises(ValidationError):
        _new_settings(ssrf_max_response_bytes=bad_value)


@pytest.mark.parametrize("bad_env", ["0", "-5", "", "   ", "not-an-int", "1.5", "true"])
def test_invalid_max_response_bytes_env_raises_validation_error(
    monkeypatch: pytest.MonkeyPatch, bad_env: str
) -> None:
    """Invalid WISHENKA_SSRF_MAX_RESPONSE_BYTES env overrides fail fast on Settings()."""
    monkeypatch.setenv("WISHENKA_SSRF_MAX_RESPONSE_BYTES", bad_env)
    with pytest.raises(ValidationError):
        Settings()


@pytest.mark.parametrize(
    "bad_value",
    [
        (),
        [],
        "",
        "   ",
        "http, ",
        ",https",
        ("ftp",),
        ("file",),
        ("javascript",),
        ("data",),
        ("gopher",),
        ("https://",),
        ("http ",),
        ("http\t",),
        [123],
    ],
)
def test_invalid_allowed_schemes_direct_raises_validation_error(bad_value: Any) -> None:
    """Empty, blank, malformed, or unsupported ssrf_allowed_schemes fail fast."""
    with pytest.raises(ValidationError):
        _new_settings(ssrf_allowed_schemes=bad_value)


@pytest.mark.parametrize(
    "bad_env",
    [
        "[]",
        "",
        "   ",
        "http, ",
        ",https",
        "ftp",
        '["ftp"]',
        '["file"]',
        '["javascript"]',
        '["data"]',
        '["https://"]',
        '["http "]',
        "[123]",
        "[not-json",
        '{"scheme": "https"}',
    ],
)
def test_invalid_allowed_schemes_env_raises_validation_error(
    monkeypatch: pytest.MonkeyPatch, bad_env: str
) -> None:
    """Invalid WISHENKA_SSRF_ALLOWED_SCHEMES env overrides fail fast on Settings()."""
    monkeypatch.setenv("WISHENKA_SSRF_ALLOWED_SCHEMES", bad_env)
    with pytest.raises(ValidationError):
        Settings()


@pytest.mark.parametrize(
    "bad_value",
    [
        "",
        "   ",
        "10.0.0.0/8, ",
        ["10.0.0.0/8", ""],
        ("not-a-cidr",),
        ("999.999.999.999/24",),
        ("10.0.0.0/33",),
        ("10.0.0.0/8 ",),
        [123],
        {"10.0.0.0/8": True},
    ],
)
def test_invalid_forbidden_cidrs_direct_raises_validation_error(bad_value: Any) -> None:
    """Blank or malformed ssrf_forbidden_cidrs fail fast on Settings instantiation."""
    with pytest.raises(ValidationError):
        _new_settings(ssrf_forbidden_cidrs=bad_value)


@pytest.mark.parametrize(
    "bad_env",
    [
        "",
        "   ",
        "10.0.0.0/8, ",
        ",10.0.0.0/8",
        '["10.0.0.0/8", ""]',
        "not-a-cidr",
        "999.999.999.999/24",
        "[123]",
        "[bad-json",
        '["10.0.0.0/8 "]',
    ],
)
def test_invalid_forbidden_cidrs_env_raises_validation_error(
    monkeypatch: pytest.MonkeyPatch, bad_env: str
) -> None:
    """Invalid WISHENKA_SSRF_FORBIDDEN_CIDRS env overrides fail fast on Settings()."""
    monkeypatch.setenv("WISHENKA_SSRF_FORBIDDEN_CIDRS", bad_env)
    with pytest.raises(ValidationError):
        Settings()


def test_invalid_env_fails_fast_on_zero_arg_ssrf_consumers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Zero-arg service/transport entrypoints propagate ValidationError on invalid env."""
    monkeypatch.setenv("WISHENKA_SSRF_ALLOWED_SCHEMES", "ftp")
    with pytest.raises(ValidationError):
        fetcher_mod.UrlMetadataService()
    with pytest.raises(ValidationError):
        ssrf_mod.SSRFSafeTransport()


# ============================================================================
# 4. IP Validation, DNS Cache Policy Isolation, and SSRFSafeTransport
# ============================================================================


def test_is_ip_safe_enforces_custom_cidrs_and_ipv4_mapped_ipv6() -> None:
    """Custom forbidden_networks block IPv4, IPv4-mapped IPv6, and public IPv6 CIDRs."""
    custom_networks = (
        ipaddress.ip_network("93.184.216.0/24"),
        ipaddress.ip_network("2606:2800::/32"),
    )

    assert not ssrf_mod.is_ip_safe("93.184.216.34", forbidden_networks=custom_networks)
    assert not ssrf_mod.is_ip_safe(
        ipaddress.ip_address("93.184.216.34"), forbidden_networks=custom_networks
    )
    assert not ssrf_mod.is_ip_safe("::ffff:93.184.216.34", forbidden_networks=custom_networks)
    assert not ssrf_mod.is_ip_safe(
        ipaddress.ip_address("::ffff:93.184.216.34"), forbidden_networks=custom_networks
    )
    assert not ssrf_mod.is_ip_safe(
        "2606:2800:220:1:248:1893:25c8:1946", forbidden_networks=custom_networks
    )
    assert ssrf_mod.is_ip_safe("8.8.8.8", forbidden_networks=custom_networks)


def test_is_ip_safe_honors_env_forbidden_cidrs(monkeypatch: pytest.MonkeyPatch) -> None:
    """One-arg is_ip_safe honors WISHENKA_SSRF_FORBIDDEN_CIDRS overrides."""
    monkeypatch.setenv("WISHENKA_SSRF_FORBIDDEN_CIDRS", "93.184.216.0/24")

    assert not ssrf_mod.is_ip_safe("93.184.216.34")
    assert not ssrf_mod.is_ip_safe("::ffff:93.184.216.34")
    assert ssrf_mod.is_ip_safe("8.8.8.8")


def test_baseline_protections_always_blocked_when_forbidden_cidrs_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Clearing ssrf_forbidden_cidrs never permits loopback, private, or metadata IPs."""
    monkeypatch.setenv("WISHENKA_SSRF_FORBIDDEN_CIDRS", "[]")
    settings: Any = Settings()
    assert settings.ssrf_forbidden_cidrs == ()

    baseline_blocked = (
        "127.0.0.1",
        "10.0.0.1",
        "172.16.0.1",
        "192.168.1.1",
        "100.64.0.1",
        "169.254.169.254",
        "0.0.0.0",
        "255.255.255.255",
        "::1",
        "::",
        "fe80::1",
        "fc00::1",
        "fd00::1",
        "::ffff:127.0.0.1",
        "::ffff:169.254.169.254",
    )
    for addr in baseline_blocked:
        assert not ssrf_mod.is_ip_safe(addr, forbidden_networks=()), (
            f"Baseline address {addr} must remain blocked with empty forbidden_networks"
        )
        assert not ssrf_mod.is_ip_safe(addr), (
            f"Baseline address {addr} must remain blocked when WISHENKA_SSRF_FORBIDDEN_CIDRS=[]"
        )


@pytest.mark.asyncio
async def test_resolve_and_validate_host_revalidates_dns_cache_across_policies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Warm DNSCache entries are re-validated against the caller's active CIDR policy."""
    mock_getaddrinfo = AsyncMock(return_value=_make_addrinfo("93.184.216.34", 443))
    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", mock_getaddrinfo)

    assert await ssrf_mod.resolve_and_validate_host("shared.example.com", 443) == ["93.184.216.34"]
    assert mock_getaddrinfo.await_count == 1

    # Stricter explicit forbidden_networks must reject the cached IP without evicting it.
    strict_nets = (ipaddress.ip_network("93.184.216.0/24"),)
    with pytest.raises(SSRFBlockedError):
        await ssrf_mod.resolve_and_validate_host(
            "shared.example.com", 443, forbidden_networks=strict_nets
        )

    # Stricter env CIDR override must also reject the cached IP.
    monkeypatch.setenv("WISHENKA_SSRF_FORBIDDEN_CIDRS", "93.184.216.0/24")
    with pytest.raises(SSRFBlockedError):
        await ssrf_mod.resolve_and_validate_host("shared.example.com", 443)

    # Default policy still hits the warm cache cleanly.
    monkeypatch.delenv("WISHENKA_SSRF_FORBIDDEN_CIDRS")
    assert await ssrf_mod.resolve_and_validate_host("shared.example.com", 443) == ["93.184.216.34"]
    assert mock_getaddrinfo.await_count == 1

    # Direct IPv4 and IPv4-mapped IPv6 literals respect custom forbidden_networks too.
    with pytest.raises(SSRFBlockedError):
        await ssrf_mod.resolve_and_validate_host(
            "93.184.216.34", 443, forbidden_networks=strict_nets
        )
    with pytest.raises(SSRFBlockedError):
        await ssrf_mod.resolve_and_validate_host(
            "::ffff:93.184.216.34", 443, forbidden_networks=strict_nets
        )


@pytest.mark.asyncio
async def test_resolve_and_validate_host_single_flight_isolates_differing_policies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Concurrent lookups under differing CIDR policies do not share one in-flight verdict."""

    async def slow_getaddrinfo(
        host: str, port: Any, *args: Any, **kwargs: Any
    ) -> list[tuple[Any, ...]]:
        await asyncio.sleep(0)
        return _make_addrinfo("93.184.216.34", int(port))

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", slow_getaddrinfo)
    strict_nets = (ipaddress.ip_network("93.184.216.0/24"),)

    coro_default: Any = ssrf_mod.resolve_and_validate_host("race.example.com", 443)
    try:
        coro_strict: Any = ssrf_mod.resolve_and_validate_host(
            "race.example.com", 443, forbidden_networks=strict_nets
        )
    except Exception:
        coro_default.close()
        raise

    default_res: Any
    strict_res: Any
    default_res, strict_res = await asyncio.gather(
        coro_default,
        coro_strict,
        return_exceptions=True,
    )
    assert default_res == ["93.184.216.34"]
    assert isinstance(strict_res, SSRFBlockedError)


@pytest.mark.asyncio
async def test_ssrf_safe_transport_enforces_configured_schemes_cidrs_and_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SSRFSafeTransport enforces scheme, custom CIDR, and baseline protections."""
    connect_calls: list[tuple[str, int]] = []

    async def fake_getaddrinfo(
        host: str, port: Any, *args: Any, **kwargs: Any
    ) -> list[tuple[Any, ...]]:
        ip = "93.184.216.34" if "blocked" in host else "8.8.8.8"
        return _make_addrinfo(ip, int(port))

    async def fake_connect_tcp(
        self_backend: Any,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> httpcore.AsyncNetworkStream:
        connect_calls.append((host, port))
        return _FakeAsyncNetworkStream(_http_response("200 OK", b"ok"))

    loop = asyncio.get_running_loop()
    monkeypatch.setattr(loop, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr("httpcore._backends.auto.AutoBackend.connect_tcp", fake_connect_tcp)

    https_only = _new_settings(
        ssrf_allowed_schemes=("https",),
        ssrf_forbidden_cidrs=("93.184.216.0/24",),
    )
    transport = ssrf_mod.SSRFSafeTransport(settings=https_only)
    try:
        with pytest.raises(InvalidUrlSchemeError):
            await transport.handle_async_request(httpx.Request("GET", "http://ok.example/item"))
        with pytest.raises(SSRFBlockedError):
            await transport.handle_async_request(
                httpx.Request("GET", "https://blocked.example/item")
            )
        # Defense-in-depth on backend pinned-cache miss must enforce the transport's policy.
        with pytest.raises(SSRFBlockedError):
            await transport._pool._network_backend.connect_tcp("93.184.216.34", 443)
        assert connect_calls == []

        response = await transport.handle_async_request(
            httpx.Request("GET", "https://ok.example/item")
        )
        await response.aread()
        assert response.status_code == 200
        assert connect_calls == [("8.8.8.8", 443)]
    finally:
        await transport.aclose()

    # Zero-arg transport honors WISHENKA_SSRF_* env overrides dynamically.
    monkeypatch.setenv("WISHENKA_SSRF_ALLOWED_SCHEMES", "https")
    monkeypatch.setenv("WISHENKA_SSRF_FORBIDDEN_CIDRS", "93.184.216.0/24")
    env_transport = ssrf_mod.SSRFSafeTransport()
    try:
        with pytest.raises(InvalidUrlSchemeError):
            await env_transport.handle_async_request(httpx.Request("GET", "http://ok.example/"))
        with pytest.raises(SSRFBlockedError):
            await env_transport.handle_async_request(
                httpx.Request("GET", "https://blocked.example/")
            )
    finally:
        await env_transport.aclose()

    # Empty ssrf_forbidden_cidrs still blocks baseline private/loopback/metadata IPs.
    monkeypatch.delenv("WISHENKA_SSRF_ALLOWED_SCHEMES", raising=False)
    monkeypatch.delenv("WISHENKA_SSRF_FORBIDDEN_CIDRS", raising=False)
    empty_cidr_transport = ssrf_mod.SSRFSafeTransport(
        settings=_new_settings(ssrf_forbidden_cidrs=())
    )
    try:
        with pytest.raises(SSRFBlockedError):
            await empty_cidr_transport.handle_async_request(
                httpx.Request("GET", "http://127.0.0.1/")
            )
        with pytest.raises(SSRFBlockedError):
            await empty_cidr_transport._pool._network_backend.connect_tcp("169.254.169.254", 80)
    finally:
        await empty_cidr_transport.aclose()


# ============================================================================
# 5. End-to-End Policy Propagation (Fetcher, Service, Web App, Bot)
# ============================================================================


@pytest.mark.asyncio
async def test_url_metadata_service_max_bytes_env_settings_and_explicit_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """UrlMetadataService honors env, explicit Settings, and explicit max_bytes precedence."""
    monkeypatch.setenv("WISHENKA_SSRF_MAX_RESPONSE_BYTES", "64")
    env_service: Any = fetcher_mod.UrlMetadataService()
    assert env_service.max_bytes == 64

    # Early rejection via Content-Length > 64
    cl_response = httpx.Response(
        200,
        headers={"Content-Length": "65"},
        request=httpx.Request("GET", "https://example.com/cl.html"),
    )
    cl_client = AsyncMock(spec=httpx.AsyncClient)
    cl_client.stream.return_value.__aenter__.return_value = cl_response
    with pytest.raises(ResponseBodyTooLargeError) as cl_exc:
        await env_service._stream_and_read(cl_client, "https://example.com/cl.html")
    assert cl_exc.value.max_allowed == 64

    # Streaming chunk overflow > 64 without Content-Length
    stream_response = httpx.Response(
        200,
        headers={"Transfer-Encoding": "chunked"},
        request=httpx.Request("GET", "https://example.com/stream.html"),
        stream=_ChunkedStream([b"a" * 40, b"b" * 40]),
    )
    stream_client = AsyncMock(spec=httpx.AsyncClient)
    stream_client.stream.return_value.__aenter__.return_value = stream_response
    with pytest.raises(ResponseBodyTooLargeError) as stream_exc:
        await env_service._stream_and_read(stream_client, "https://example.com/stream.html")
    assert stream_exc.value.max_allowed == 64

    # Under 64-byte limit succeeds
    small_body = b"<html><title>Ok</title></html>"
    ok_response = httpx.Response(
        200,
        headers={"Content-Length": str(len(small_body))},
        request=httpx.Request("GET", "https://example.com/ok.html"),
        stream=_ChunkedStream([small_body]),
    )
    ok_client = AsyncMock(spec=httpx.AsyncClient)
    ok_client.stream.return_value.__aenter__.return_value = ok_response
    html, _ = await env_service._stream_and_read(ok_client, "https://example.com/ok.html")
    assert "<title>Ok</title>" in html

    # Explicit Settings overrides env; explicit max_bytes overrides Settings.
    settings_service: Any = fetcher_mod.UrlMetadataService(
        settings=_new_settings(ssrf_max_response_bytes=128)
    )
    assert settings_service.max_bytes == 128

    explicit_service: Any = fetcher_mod.UrlMetadataService(
        max_bytes=16,
        settings=_new_settings(ssrf_max_response_bytes=1024),
    )
    assert explicit_service.max_bytes == 16

    with pytest.raises(ValueError):
        fetcher_mod.UrlMetadataService(max_bytes=0)
    with pytest.raises(ValueError):
        fetcher_mod.UrlMetadataService(max_bytes=-5)


@pytest.mark.asyncio
async def test_url_metadata_service_enforces_scheme_and_cidrs_on_redirects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """UrlMetadataService enforces configured schemes and CIDRs on initial and redirect hops."""

    async def fake_getaddrinfo(
        host: str, port: Any, *args: Any, **kwargs: Any
    ) -> list[tuple[Any, ...]]:
        ip = "93.184.216.34" if host == "cdn.example.com" else "8.8.8.8"
        return _make_addrinfo(ip, int(port))

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", fake_getaddrinfo)

    settings = _new_settings(
        ssrf_allowed_schemes=("https",),
        ssrf_forbidden_cidrs=("93.184.216.0/24",),
    )
    service: Any = fetcher_mod.UrlMetadataService(settings=settings)

    with pytest.raises(InvalidUrlSchemeError):
        await service._fetch_html("http://shop.example.com/item")

    start_url = "https://shop.example.com/start"
    insecure_hop = "http://shop.example.com/insecure"
    scheme_routes = fetcher_mod.PreviewTransportConfig(
        default=fetcher_mod.offline_replay_route(
            {
                start_url: (302, {"Location": insecure_hop}, b""),
                insecure_hop: (200, {}, b"<title>Should Not Fetch</title>"),
            }
        ),
        mounts={},
    )
    with pytest.raises(InvalidUrlSchemeError):
        await service._fetch_html(start_url, routes=scheme_routes)

    forbidden_hop = "https://cdn.example.com/asset"
    cidr_routes = fetcher_mod.PreviewTransportConfig(
        default=fetcher_mod.offline_replay_route(
            {
                start_url: (302, {"Location": forbidden_hop}, b""),
                forbidden_hop: (200, {}, b"<title>Should Not Fetch</title>"),
            }
        ),
        mounts={},
    )
    with pytest.raises(SSRFBlockedError):
        await service._fetch_html(start_url, routes=cidr_routes)


@pytest.mark.asyncio
async def test_validate_url_honors_settings_and_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """validate_url enforces explicit Settings/SSRFPolicy and rejects ambiguous args."""
    policy_cls = getattr(ssrf_mod, "SSRFPolicy", None)
    assert policy_cls is not None, "wishenka.items.ssrf.SSRFPolicy is not implemented"

    async def fake_getaddrinfo(
        host: str, port: Any, *args: Any, **kwargs: Any
    ) -> list[tuple[Any, ...]]:
        return _make_addrinfo("93.184.216.34", int(port))

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", fake_getaddrinfo)

    https_only = _new_settings(ssrf_allowed_schemes=("https",))
    with pytest.raises(InvalidUrlSchemeError):
        await fetcher_mod.validate_url("http://shop.example.com/item", settings=https_only)

    strict_policy = policy_cls.from_settings(
        _new_settings(ssrf_forbidden_cidrs=("93.184.216.0/24",))
    )
    with pytest.raises(SSRFBlockedError):
        await fetcher_mod.validate_url("https://shop.example.com/item", policy=strict_policy)

    with pytest.raises(ValueError):
        await fetcher_mod.validate_url(
            "https://shop.example.com/item", settings=https_only, policy=strict_policy
        )


@pytest.mark.asyncio
async def test_safe_direct_route_forwards_settings_to_transport() -> None:
    """safe_direct_route forwards Settings so its transport enforces configured schemes."""
    settings = _new_settings(ssrf_allowed_schemes=("https",))
    route = fetcher_mod.safe_direct_route(settings=settings)
    try:
        with pytest.raises(InvalidUrlSchemeError):
            await route.transport.handle_async_request(httpx.Request("GET", "http://8.8.8.8/"))
    finally:
        await route.transport.aclose()


@pytest.mark.asyncio
async def test_item_preview_service_zero_arg_honors_env_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Zero-arg ItemPreviewService honors env overrides across scheme, CIDR, and size limits."""

    async def fake_getaddrinfo(
        host: str, port: Any, *args: Any, **kwargs: Any
    ) -> list[tuple[Any, ...]]:
        ip = "93.184.216.34" if host == "cdn.example.com" else "8.8.8.8"
        return _make_addrinfo(ip, int(port))

    async def fake_connect_tcp(
        self_backend: Any,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> httpcore.AsyncNetworkStream:
        return _FakeAsyncNetworkStream(_http_response("200 OK", b"<html><title>Ok</title></html>"))

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr("httpcore._backends.auto.AutoBackend.connect_tcp", fake_connect_tcp)
    monkeypatch.setenv("WISHENKA_SSRF_MAX_RESPONSE_BYTES", "100")
    monkeypatch.setenv("WISHENKA_SSRF_ALLOWED_SCHEMES", "https")
    monkeypatch.setenv("WISHENKA_SSRF_FORBIDDEN_CIDRS", "93.184.216.0/24")

    service = ItemPreviewService()

    http_preview = await service.fetch_preview("http://shop.example.com/item")
    assert http_preview.is_fallback is True
    assert http_preview.fallback_reason == "ssrf_blocked"

    redirect_http_routes = fetcher_mod.PreviewTransportConfig(
        default=fetcher_mod.offline_replay_route(
            {
                "https://shop.example.com/start": (
                    302,
                    {"Location": "http://shop.example.com/next"},
                    b"",
                ),
                "http://shop.example.com/next": (200, {}, b"<title>No</title>"),
            }
        ),
        mounts={},
    )
    redirect_preview = await service.fetch_preview(
        "https://shop.example.com/start", routes=redirect_http_routes
    )
    assert redirect_preview.is_fallback is True
    assert redirect_preview.fallback_reason == "ssrf_blocked"

    cidr_preview = await service.fetch_preview("https://cdn.example.com/item")
    assert cidr_preview.is_fallback is True
    assert cidr_preview.fallback_reason == "ssrf_blocked"

    oversize_url = "https://shop.example.com/big"
    oversize_routes = fetcher_mod.PreviewTransportConfig(
        default=fetcher_mod.offline_replay_route(
            {oversize_url: (200, {}, b"<title>Too Big</title>" + b"X" * 200)}
        ),
        mounts={},
    )
    oversize_preview = await service.fetch_preview(oversize_url, routes=oversize_routes)
    assert oversize_preview.is_fallback is True
    assert oversize_preview.fallback_reason == "response_too_large"

    ok_url = "https://shop.example.com/tiny"
    ok_routes = fetcher_mod.PreviewTransportConfig(
        default=fetcher_mod.offline_replay_route({ok_url: (200, {}, b"<title>Tiny</title>")}),
        mounts={},
    )
    ok_preview = await service.fetch_preview(ok_url, routes=ok_routes)
    assert ok_preview.is_fallback is False
    assert ok_preview.title == "Tiny"


@pytest.mark.asyncio
async def test_item_preview_service_preview_cache_revalidates_against_active_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PreviewCache hits fail closed and evict when active SSRFPolicy disallows cached URLs."""
    dispatched: list[str] = []

    async def fake_getaddrinfo(
        host: str, port: Any, *args: Any, **kwargs: Any
    ) -> list[tuple[Any, ...]]:
        ip = "93.184.216.34" if host == "cdn.example.com" else "8.8.8.8"
        return _make_addrinfo(ip, int(port))

    async def fake_handle_async_request(
        transport: httpx.AsyncHTTPTransport, request: httpx.Request
    ) -> httpx.Response:
        url = str(request.url)
        dispatched.append(url)
        if url == "http://shop.example.com/cached":
            return httpx.Response(
                200,
                headers={"Cache-Control": "public, max-age=300"},
                text="<title>Cached HTTP</title>",
                request=request,
            )
        if url == "https://shop.example.com/redirect":
            return httpx.Response(
                302,
                headers={
                    "Location": "https://cdn.example.com/final",
                    "Cache-Control": "public, max-age=300",
                },
                request=request,
            )
        return httpx.Response(
            200,
            headers={"Cache-Control": "public, max-age=300"},
            text="<title>Cached Redirect</title>",
            request=request,
        )

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", fake_handle_async_request)

    cache = PreviewCache()
    service_cls: Any = ItemPreviewService
    permissive = service_cls(cache=cache, settings=_new_settings())

    http_first = await permissive.fetch_preview("http://shop.example.com/cached")
    redirect_first = await permissive.fetch_preview("https://shop.example.com/redirect")
    assert http_first.title == "Cached HTTP"
    assert redirect_first.title == "Cached Redirect"
    assert len(cache.entries) == 2
    dispatch_count_after_seed = len(dispatched)

    https_only = service_cls(
        cache=cache,
        settings=_new_settings(ssrf_allowed_schemes=("https",)),
    )
    blocked_http = await https_only.fetch_preview("http://shop.example.com/cached")
    assert isinstance(blocked_http, ItemPreviewDTO)
    assert blocked_http.is_fallback is True
    assert blocked_http.fallback_reason == "ssrf_blocked"
    assert "http://shop.example.com/cached" not in cache.entries
    assert len(dispatched) == dispatch_count_after_seed

    cidr_strict = service_cls(
        cache=cache,
        settings=_new_settings(ssrf_forbidden_cidrs=("93.184.216.0/24",)),
    )
    blocked_redirect = await cidr_strict.fetch_preview("https://shop.example.com/redirect")
    assert blocked_redirect.is_fallback is True
    assert blocked_redirect.fallback_reason == "ssrf_blocked"
    assert "https://shop.example.com/redirect" not in cache.entries
    assert len(dispatched) == dispatch_count_after_seed


def test_item_preview_service_preserves_mock_fetcher_compatibility() -> None:
    """MagicMock url_metadata_service doubles must not break ItemPreviewService policy lookup."""
    policy_cls = getattr(ssrf_mod, "SSRFPolicy", None)
    assert policy_cls is not None, "wishenka.items.ssrf.SSRFPolicy is not implemented"

    service: Any = ItemPreviewService(MagicMock())
    assert isinstance(service.policy, policy_cls)


def test_create_app_wires_settings_into_preview_and_items_ui_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """create_app(settings) and items_ui fallback enforce configured SSRF rules end-to-end."""
    connect_calls: list[tuple[str, int]] = []

    async def fake_base_getaddrinfo(
        self_loop: Any, host: str, port: Any, *args: Any, **kwargs: Any
    ) -> list[tuple[Any, ...]]:
        if host == "blocked.example.com":
            ip = "93.184.216.34"
        elif host == "oversized.example.com":
            ip = "8.8.4.4"
        else:
            ip = "8.8.8.8"
        return _make_addrinfo(ip, int(port))

    async def fake_connect_tcp(
        self_backend: Any,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> httpcore.AsyncNetworkStream:
        connect_calls.append((host, port))
        if host == "8.8.4.4":
            body = b"<html><title>Too Big</title></html>" + b"X" * 300
        else:
            body = b"<html><title>Allowed</title></html>"
        return _FakeAsyncNetworkStream(_http_response("200 OK", body))

    monkeypatch.setattr(asyncio.BaseEventLoop, "getaddrinfo", fake_base_getaddrinfo)
    monkeypatch.setattr("httpcore._backends.auto.AutoBackend.connect_tcp", fake_connect_tcp)

    settings = _new_settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'ssrf_app.db'}",
        secret_key="ssrf-app-test-secret",
        background_cleanup_enabled=False,
        receipt_notice_worker_enabled=False,
        ssrf_max_response_bytes=128,
        ssrf_allowed_schemes=("https",),
        ssrf_forbidden_cidrs=("93.184.216.0/24",),
    )
    app = create_app(settings)

    with TestClient(app) as client:
        owner = AuthenticatedUser(telegram_id=101, first_name="Alice", auth_method="session_token")
        wishlist = asyncio.run(
            cast(FastAPI, client.app).state.domain_service.create_wishlist(
                owner=owner, title="SSRF Check"
            )
        )
        token = SessionTokenService(settings.secret_key).create_token(101, "Alice")
        headers = {"Authorization": f"Bearer {token}", "HX-Request": "true"}
        endpoint = f"/web/wishlists/{wishlist.id}/items/preview"

        # Lifespan-owned SSRFSafeTransport itself must reject http:// when https-only.
        preview_service = cast(FastAPI, client.app).state.item_preview_service
        app_transport = preview_service.routes.default.transport
        with pytest.raises(InvalidUrlSchemeError):
            asyncio.run(app_transport.handle_async_request(httpx.Request("GET", "http://8.8.8.8/")))

        resp_http = client.post(
            endpoint, data={"raw_input": "http://ok.example.com/item"}, headers=headers
        )
        assert resp_http.status_code == 200
        assert "preview-fallback" in resp_http.text
        assert "Allowed" not in resp_http.text

        resp_cidr = client.post(
            endpoint, data={"raw_input": "https://blocked.example.com/item"}, headers=headers
        )
        assert resp_cidr.status_code == 200
        assert "preview-fallback" in resp_cidr.text
        assert connect_calls == []

        resp_oversize = client.post(
            endpoint, data={"raw_input": "https://oversized.example.com/item"}, headers=headers
        )
        assert resp_oversize.status_code == 200
        assert "preview-fallback" in resp_oversize.text
        assert "Too Big" not in resp_oversize.text
        assert ("8.8.4.4", 443) in connect_calls

        resp_ok = client.post(
            endpoint, data={"raw_input": "https://ok.example.com/item"}, headers=headers
        )
        assert resp_ok.status_code == 200
        assert "Allowed" in resp_ok.text
        assert "preview-fallback" not in resp_ok.text
        assert ("8.8.8.8", 443) in connect_calls

        # items_ui fallback when app.state.item_preview_service is absent must still use settings.
        connect_calls.clear()
        saved_service = cast(FastAPI, client.app).state.item_preview_service
        cast(FastAPI, client.app).state.item_preview_service = None
        try:
            resp_fallback_route = client.post(
                endpoint, data={"raw_input": "http://ok.example.com/item"}, headers=headers
            )
            assert resp_fallback_route.status_code == 200
            assert "preview-fallback" in resp_fallback_route.text
            assert "Allowed" not in resp_fallback_route.text
            assert connect_calls == []
        finally:
            cast(FastAPI, client.app).state.item_preview_service = saved_service


@pytest.mark.asyncio
async def test_bot_entrypoint_wires_settings_into_item_preview_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """wishenka.bot.__main__.run() passes configured Settings to ItemPreviewService."""
    monkeypatch.setenv("WISHENKA_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'bot_ssrf.db'}")
    monkeypatch.setenv("WISHENKA_BOT_TOKEN", "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")
    monkeypatch.setenv("WISHENKA_SSRF_MAX_RESPONSE_BYTES", "512")
    monkeypatch.setenv("WISHENKA_SSRF_ALLOWED_SCHEMES", "https")
    monkeypatch.setenv("WISHENKA_SSRF_FORBIDDEN_CIDRS", "93.184.216.0/24")

    captured_deps: list[Any] = []
    init_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    real_service_cls: Any = ItemPreviewService

    def spy_preview_service(*args: Any, **kwargs: Any) -> Any:
        init_calls.append((args, kwargs))
        return real_service_cls(*args, **kwargs)

    def fake_create_router(deps: Any) -> Router:
        captured_deps.append(deps)
        return Router()

    monkeypatch.setattr(bot_main, "ItemPreviewService", spy_preview_service)
    monkeypatch.setattr(bot_main, "create_router", fake_create_router)
    monkeypatch.setattr(Dispatcher, "start_polling", AsyncMock(return_value=None))

    await bot_main.run()

    assert len(init_calls) == 1
    assert "settings" in init_calls[0][1]
    passed_settings: Any = init_calls[0][1]["settings"]
    assert passed_settings.ssrf_max_response_bytes == 512

    assert len(captured_deps) == 1
    preview_service: Any = captured_deps[0].preview_service
    assert preview_service.url_metadata_service.max_bytes == 512
    assert preview_service.policy.allowed_schemes == frozenset({"https"})
    assert ipaddress.ip_network("93.184.216.0/24") in preview_service.policy.forbidden_networks

    blocked_preview = await preview_service.fetch_preview("http://shop.example.com/item")
    assert blocked_preview.is_fallback is True
    assert blocked_preview.fallback_reason == "ssrf_blocked"


# ============================================================================
# 6. Structured Observability (Policy Init, Rejections, Revalidation, No Leaks)
# ============================================================================


def test_ssrf_policy_startup_and_env_loading_observability(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Startup and ambient policy loads emit bounded scalar SSRF metadata without CIDR dumps."""
    monkeypatch.setenv("WISHENKA_SSRF_MAX_RESPONSE_BYTES", "777")
    monkeypatch.setenv("WISHENKA_SSRF_ALLOWED_SCHEMES", "https")
    monkeypatch.setenv("WISHENKA_SSRF_FORBIDDEN_CIDRS", "93.184.216.0/24, 198.51.100.0/24")

    with caplog.at_level(logging.DEBUG, logger="wishenka.items"):
        loaded_policy = ssrf_mod.get_default_ssrf_policy()

    assert loaded_policy.max_response_bytes == 777
    load_records = [r for r in caplog.records if getattr(r, "event", None) == "ssrf_policy_loaded"]
    assert len(load_records) == 1
    load_payload = json.loads(JsonFormatter().format(load_records[0]))["extra"]
    assert load_payload["max_response_bytes"] == 777
    assert load_payload["allowed_schemes"] == ["https"]
    assert load_payload["forbidden_cidr_count"] == 2
    assert "93.184.216.0/24" not in json.dumps(load_payload)
    assert "198.51.100.0/24" not in json.dumps(load_payload)

    caplog.clear()
    settings = _new_settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'ssrf_obs.db'}",
        secret_key="ssrf-obs-secret-key",
        log_level="DEBUG",
        background_cleanup_enabled=False,
        receipt_notice_worker_enabled=False,
        ssrf_max_response_bytes=256,
        ssrf_allowed_schemes=("https",),
        ssrf_forbidden_cidrs=("93.184.216.0/24", "198.51.100.0/24"),
    )
    app = create_app(settings)
    with caplog.at_level(logging.DEBUG), TestClient(app):
        pass

    startup_rec = next(
        r
        for r in caplog.records
        if r.name == "wishenka.web" and "Wishenka web application starting up" in r.getMessage()
    )
    assert startup_rec.levelno == logging.INFO
    startup_rendered = JsonFormatter().format(startup_rec)
    startup_extra = json.loads(startup_rendered)["extra"]
    assert startup_extra["ssrf_max_response_bytes"] == 256
    assert startup_extra["ssrf_allowed_schemes"] == ["https"]
    assert startup_extra["ssrf_forbidden_cidr_count"] == 2
    assert "93.184.216.0/24" not in startup_rendered
    assert "ssrf-obs-secret-key" not in startup_rendered

    configured_records = [
        r
        for r in caplog.records
        if r.name == "wishenka.items" and getattr(r, "event", None) == "ssrf_policy_configured"
    ]
    configured_components = {getattr(r, "component", None) for r in configured_records}
    assert {"SSRFSafeTransport", "ItemPreviewService", "UrlMetadataService"} <= (
        configured_components
    )
    for rec in configured_records:
        rendered = JsonFormatter().format(rec)
        parsed = json.loads(rendered)["extra"]
        assert parsed["max_response_bytes"] == 256
        assert parsed["allowed_schemes"] == ["https"]
        assert parsed["forbidden_cidr_count"] == 2
        assert "93.184.216.0/24" not in rendered


@pytest.mark.asyncio
async def test_ssrf_configured_policy_rejection_and_size_limit_observability(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Configured scheme rejections, redirect hooks, and size cutoffs emit structured WARNINGs."""

    async def fake_getaddrinfo(
        host: str, port: Any, *args: Any, **kwargs: Any
    ) -> list[tuple[Any, ...]]:
        return _make_addrinfo("8.8.8.8", int(port))

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", fake_getaddrinfo)
    settings = _new_settings(
        ssrf_max_response_bytes=64,
        ssrf_allowed_schemes=("https",),
        ssrf_forbidden_cidrs=("93.184.216.0/24",),
    )

    # 1. validate_url emits ssrf_blocked when configured scheme disallows http://.
    with (
        caplog.at_level(logging.WARNING, logger="wishenka.items"),
        pytest.raises(InvalidUrlSchemeError),
    ):
        await fetcher_mod.validate_url("http://shop.example.com/item", settings=settings)

    validate_rec = next(r for r in caplog.records if getattr(r, "event", None) == "ssrf_blocked")
    assert getattr(validate_rec, "reason", None) == "invalid_scheme"
    assert getattr(validate_rec, "scheme", None) == "http"
    assert getattr(validate_rec, "allowed_schemes", None) == ["https"]

    caplog.clear()
    service = ItemPreviewService(settings=settings)

    # 2. Redirect hop to disallowed scheme emits both ssrf_blocked and item_preview_invalid_scheme.
    redirect_routes = fetcher_mod.PreviewTransportConfig(
        default=fetcher_mod.offline_replay_route(
            {
                "https://shop.example.com/start": (
                    302,
                    {"Location": "http://shop.example.com/next"},
                    b"",
                ),
                "http://shop.example.com/next": (200, {}, b"<title>Blocked</title>"),
            }
        ),
        mounts={},
    )
    with caplog.at_level(logging.WARNING, logger="wishenka.items"):
        redirect_preview = await service.fetch_preview(
            "https://shop.example.com/start", routes=redirect_routes
        )
    assert redirect_preview.is_fallback is True
    assert redirect_preview.fallback_reason == "ssrf_blocked"

    events = {getattr(r, "event", None) for r in caplog.records}
    assert {"ssrf_blocked", "item_preview_invalid_scheme"} <= events
    scheme_rec = next(
        r for r in caplog.records if getattr(r, "event", None) == "item_preview_invalid_scheme"
    )
    assert getattr(scheme_rec, "allowed_schemes", None) == ["https"]
    assert getattr(scheme_rec, "scheme", None) == "http"
    assert getattr(scheme_rec, "fallback_reason", None) == "ssrf_blocked"

    caplog.clear()

    # 3. Custom size limit emits payload_size_violation and item_preview_response_too_large.
    oversize_url = "https://shop.example.com/oversized"
    oversize_routes = fetcher_mod.PreviewTransportConfig(
        default=fetcher_mod.offline_replay_route(
            {oversize_url: (200, {}, b"<title>Too Big</title>" + b"X" * 128)}
        ),
        mounts={},
    )
    with caplog.at_level(logging.WARNING, logger="wishenka.items"):
        oversize_preview = await service.fetch_preview(oversize_url, routes=oversize_routes)
    assert oversize_preview.is_fallback is True
    assert oversize_preview.fallback_reason == "response_too_large"

    size_rec = next(
        r for r in caplog.records if getattr(r, "event", None) == "payload_size_violation"
    )
    assert getattr(size_rec, "max_allowed", None) == 64
    assert getattr(size_rec, "reason", None) == "content_length_exceeded"
    preview_size_rec = next(
        r for r in caplog.records if getattr(r, "event", None) == "item_preview_response_too_large"
    )
    assert getattr(preview_size_rec, "max_allowed", None) == 64
    for rec in caplog.records:
        parsed = json.loads(JsonFormatter().format(rec))
        assert "93.184.216.0/24" not in json.dumps(parsed)

    # Streaming chunk overflow without Content-Length also logs max_allowed=64.
    caplog.clear()
    stream_response = httpx.Response(
        200,
        headers={"Transfer-Encoding": "chunked"},
        request=httpx.Request("GET", "https://shop.example.com/stream"),
        stream=_ChunkedStream([b"a" * 40, b"b" * 40]),
    )
    stream_client = AsyncMock(spec=httpx.AsyncClient)
    stream_client.stream.return_value.__aenter__.return_value = stream_response
    with (
        caplog.at_level(logging.WARNING, logger="wishenka.items"),
        pytest.raises(ResponseBodyTooLargeError),
    ):
        await service.url_metadata_service._stream_and_read(
            stream_client, "https://shop.example.com/stream"
        )
    stream_rec = next(
        r for r in caplog.records if getattr(r, "event", None) == "payload_size_violation"
    )
    assert getattr(stream_rec, "max_allowed", None) == 64
    assert getattr(stream_rec, "reason", None) == "stream_chunk_overflow"


@pytest.mark.asyncio
async def test_ssrf_dns_cache_and_preview_cache_revalidation_observability(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """DNS cache hits, pinned misses, and PreviewCache revalidation blocks emit bounded logs."""
    mock_getaddrinfo = AsyncMock(return_value=_make_addrinfo("93.184.216.34", 443))
    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", mock_getaddrinfo)

    assert await ssrf_mod.resolve_and_validate_host("cached-obs.example.com", 443) == [
        "93.184.216.34"
    ]

    with caplog.at_level(logging.DEBUG, logger="wishenka.items"):
        assert await ssrf_mod.resolve_and_validate_host("cached-obs.example.com", 443) == [
            "93.184.216.34"
        ]
        strict_nets = (ipaddress.ip_network("93.184.216.0/24"),)
        with pytest.raises(SSRFBlockedError):
            await ssrf_mod.resolve_and_validate_host(
                "cached-obs.example.com", 443, forbidden_networks=strict_nets
            )

    hit_rec = next(r for r in caplog.records if getattr(r, "event", None) == "dns_cache_hit")
    assert getattr(hit_rec, "forbidden_cidr_count", None) == len(EXPECTED_DEFAULT_FORBIDDEN_CIDRS)

    reval_block_rec = next(
        r
        for r in caplog.records
        if getattr(r, "event", None) == "ssrf_blocked"
        and getattr(r, "cache_revalidation", None) is True
    )
    assert reval_block_rec.levelno == logging.WARNING
    assert getattr(reval_block_rec, "forbidden_cidr_count", None) == 1

    # Pinned-cache miss in SSRFSafeNetworkBackend emits policy source and CIDR count.
    caplog.clear()
    strict_settings = _new_settings(ssrf_forbidden_cidrs=("93.184.216.0/24",))
    transport = ssrf_mod.SSRFSafeTransport(settings=strict_settings)
    try:
        with (
            caplog.at_level(logging.DEBUG, logger="wishenka.items"),
            pytest.raises(SSRFBlockedError),
        ):
            await transport._pool._network_backend.connect_tcp("93.184.216.34", 443)
    finally:
        await transport.aclose()

    miss_rec = next(
        r for r in caplog.records if getattr(r, "event", None) == "ssrf_pinned_cache_miss"
    )
    assert getattr(miss_rec, "policy_source", None) == "pinned"
    assert getattr(miss_rec, "forbidden_cidr_count", None) == 1

    # PreviewCache revalidation eviction emits DEBUG eviction + WARNING SSRF events.
    async def fake_handle_async_request(
        transport_self: httpx.AsyncHTTPTransport, request: httpx.Request
    ) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Cache-Control": "public, max-age=300"},
            text="<title>Cached Public</title>",
            request=request,
        )

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", fake_handle_async_request)
    cache = PreviewCache()
    permissive = ItemPreviewService(cache=cache, settings=_new_settings())
    seeded = await permissive.fetch_preview("https://cached-obs.example.com/item")
    assert seeded.is_fallback is False

    caplog.clear()
    strict_service = ItemPreviewService(cache=cache, settings=strict_settings)
    with caplog.at_level(logging.DEBUG, logger="wishenka.items"):
        blocked = await strict_service.fetch_preview("https://cached-obs.example.com/item")

    assert blocked.is_fallback is True
    assert blocked.fallback_reason == "ssrf_blocked"
    evicted_rec = next(
        r
        for r in caplog.records
        if getattr(r, "event", None) == "preview_cache_revalidation_evicted"
    )
    assert getattr(evicted_rec, "url_domain", None) == "cached-obs.example.com"
    assert getattr(evicted_rec, "destination_count", None) == 1
    preview_block_rec = next(
        r for r in caplog.records if getattr(r, "event", None) == "item_preview_ssrf_blocked"
    )
    assert getattr(preview_block_rec, "forbidden_cidr_count", None) == 1
    assert "93.184.216.0/24" not in JsonFormatter().format(preview_block_rec)


@pytest.mark.asyncio
async def test_ssrf_observability_never_logs_url_credentials(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Credential-bearing URLs emit ssrf_blocked without leaking username or password."""
    secret_user = "alice-secret-user"
    secret_pass = "super-secret-password-987"
    credential_url = f"https://{secret_user}:{secret_pass}@shop.example.com/item"

    transport = ssrf_mod.SSRFSafeTransport()
    try:
        with caplog.at_level(logging.DEBUG, logger="wishenka.items"):
            with pytest.raises(SSRFBlockedError):
                await fetcher_mod.validate_url(credential_url)
            with pytest.raises(SSRFBlockedError):
                await transport.handle_async_request(httpx.Request("GET", credential_url))
            await fetcher_mod.UrlMetadataService().fetch_and_extract(credential_url)
            preview = await ItemPreviewService().fetch_preview(credential_url)
    finally:
        await transport.aclose()

    assert preview.is_fallback is True
    assert preview.fallback_reason == "ssrf_blocked"

    cred_records = [
        r
        for r in caplog.records
        if getattr(r, "event", None) == "ssrf_blocked"
        and getattr(r, "reason", None) == "credentials"
    ]
    assert len(cred_records) >= 4
    preview_block = next(
        r
        for r in caplog.records
        if getattr(r, "event", None) == "item_preview_ssrf_blocked"
        and getattr(r, "reason", None) == "credentials"
    )
    assert getattr(preview_block, "url_domain", None) == "shop.example.com"
    assert getattr(preview_block, "url", None) == "https://shop.example.com/item"

    formatter = JsonFormatter()
    for rec in caplog.records:
        if getattr(rec, "event", None) == "input_classified":
            continue
        formatted = formatter.format(rec)
        assert secret_user not in rec.getMessage()
        assert secret_pass not in rec.getMessage()
        assert secret_user not in formatted
        assert secret_pass not in formatted
        assert secret_user not in str(rec.__dict__)
        assert secret_pass not in str(rec.__dict__)
