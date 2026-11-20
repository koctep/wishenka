"""Automated failing repro tests for WISHENKA-94 (TTL/LRU DNS caching & single-flight).

Verifies that ``resolve_and_validate_host``:
1. Reuses validated DNS results within TTL (including case/trailing-dot normalization).
2. Expires cached entries after TTL and re-runs full SSRF validation.
3. Never caches SSRF-blocked resolutions or transient DNS errors.
4. Enforces bounded LRU capacity by evicting the least recently used domain.
5. Coalesces concurrent cold-cache misses for the same domain (single-flight).
"""

import asyncio
import logging
import socket
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from wishenka.items.exceptions import SSRFBlockedError
from wishenka.items.ssrf import resolve_and_validate_host

pytestmark = pytest.mark.timeout(30)


def _make_addrinfo(ip: str, port: int) -> list[tuple[Any, ...]]:
    family = socket.AF_INET6 if ":" in ip else socket.AF_INET
    sockaddr = (ip, port, 0, 0) if family == socket.AF_INET6 else (ip, port)
    return [(family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", sockaddr)]


class TestDNSCacheBehavior:
    """Behavioral failing repros for verified DNS caching in resolve_and_validate_host."""

    async def test_dns_cache_reuses_verified_ips_within_ttl(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Repeated lookups within TTL must hit cache and normalize host case/trailing dot."""
        mock_getaddrinfo = AsyncMock(return_value=_make_addrinfo("93.184.216.34", 443))
        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", mock_getaddrinfo)

        first = await resolve_and_validate_host("shop.example.com", 443)
        first.append("1.2.3.4")  # Mutating caller's list must not corrupt cached entry.
        second = await resolve_and_validate_host("SHOP.Example.COM.", 443)

        assert second == ["93.184.216.34"]
        assert mock_getaddrinfo.await_count == 1

    async def test_dns_cache_expires_after_ttl_and_revalidates_ssrf(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Entries must expire after TTL and re-run DNS resolution + SSRF validation."""
        clock = {"now": 1000.0}
        responses = [
            _make_addrinfo("93.184.216.34", 80),
            _make_addrinfo("127.0.0.1", 80),
        ]
        mock_getaddrinfo = AsyncMock(side_effect=responses)
        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", mock_getaddrinfo)

        with patch("time.monotonic", side_effect=lambda: clock["now"]):
            assert await resolve_and_validate_host("ttl.example.com", 80) == ["93.184.216.34"]
            assert mock_getaddrinfo.await_count == 1

            # Within 60s TTL: must use cached value without calling getaddrinfo.
            clock["now"] += 30.0
            assert await resolve_and_validate_host("ttl.example.com", 80) == ["93.184.216.34"]
            assert mock_getaddrinfo.await_count == 1

            # Past 60s TTL: must re-resolve and block the newly returned private IP.
            clock["now"] += 31.0
            with pytest.raises(SSRFBlockedError):
                await resolve_and_validate_host("ttl.example.com", 80)
            assert mock_getaddrinfo.await_count == 2

    async def test_dns_cache_does_not_cache_ssrf_blocked_or_dns_errors(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """SSRF-blocked domains and transient DNS errors must never be cached."""
        ssrf_mock = AsyncMock(
            side_effect=[
                _make_addrinfo("127.0.0.1", 443),
                _make_addrinfo("93.184.216.34", 443),
            ]
        )
        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", ssrf_mock)

        with pytest.raises(SSRFBlockedError):
            await resolve_and_validate_host("blocked-then-safe.example.com", 443)
        assert await resolve_and_validate_host("blocked-then-safe.example.com", 443) == [
            "93.184.216.34"
        ]
        assert ssrf_mock.await_count == 2

        dns_err_mock = AsyncMock(
            side_effect=[
                socket.gaierror("temporary failure in name resolution"),
                _make_addrinfo("93.184.216.34", 443),
            ]
        )
        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", dns_err_mock)

        assert await resolve_and_validate_host("flaky-dns.example.com", 443) == []
        assert await resolve_and_validate_host("flaky-dns.example.com", 443) == ["93.184.216.34"]
        assert dns_err_mock.await_count == 2

    async def test_dns_cache_evicts_lru_when_capacity_exceeded(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Exceeding default cache capacity (512) must evict the least recently used host."""
        mock_getaddrinfo = AsyncMock(
            side_effect=lambda host, port, *args, **kwargs: _make_addrinfo(
                "93.184.216.34", int(port)
            )
        )
        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", mock_getaddrinfo)

        for idx in range(512):
            await resolve_and_validate_host(f"lru-{idx}.example.com", 80)
        assert mock_getaddrinfo.await_count == 512

        # Touch lru-0 so it becomes MRU and lru-1 becomes LRU.
        await resolve_and_validate_host("lru-0.example.com", 80)
        assert mock_getaddrinfo.await_count == 512

        # Insert 513th distinct host, which must evict lru-1.
        await resolve_and_validate_host("lru-512.example.com", 80)
        assert mock_getaddrinfo.await_count == 513

        # lru-0 must still be cached; lru-1 must have been evicted.
        await resolve_and_validate_host("lru-0.example.com", 80)
        assert mock_getaddrinfo.await_count == 513

        await resolve_and_validate_host("lru-1.example.com", 80)
        assert mock_getaddrinfo.await_count == 514

    async def test_dns_cache_coalesces_concurrent_misses_single_flight(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Concurrent cold-cache misses for the same host/port must share one getaddrinfo call."""

        async def slow_getaddrinfo(
            host: str, port: Any, *args: Any, **kwargs: Any
        ) -> list[tuple[Any, ...]]:
            await asyncio.sleep(0.02)
            return _make_addrinfo("93.184.216.34", int(port))

        mock_getaddrinfo = AsyncMock(side_effect=slow_getaddrinfo)
        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", mock_getaddrinfo)

        results = await asyncio.gather(
            *(resolve_and_validate_host("burst.example.com", 443) for _ in range(10))
        )

        assert all(res == ["93.184.216.34"] for res in results)
        assert mock_getaddrinfo.await_count == 1

    async def test_dns_cache_structured_logging_events(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Structured debug logs must cover cache miss, hit, coalescing, expiry, and eviction."""
        clock = {"now": 2000.0}

        async def delayed_getaddrinfo(
            host: str, port: Any, *args: Any, **kwargs: Any
        ) -> list[tuple[Any, ...]]:
            await asyncio.sleep(0)
            return _make_addrinfo("93.184.216.34", int(port))

        mock_getaddrinfo = AsyncMock(side_effect=delayed_getaddrinfo)
        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", mock_getaddrinfo)

        with (
            patch("time.monotonic", side_effect=lambda: clock["now"]),
            caplog.at_level(logging.DEBUG, logger="wishenka.items"),
        ):
            # 1. Concurrent cold-cache lookups -> 1 miss + 1 coalesced
            await asyncio.gather(
                resolve_and_validate_host("log-test.example.com", 443),
                resolve_and_validate_host("log-test.example.com", 443),
            )
            # 2. Warm lookup -> cache hit
            await resolve_and_validate_host("log-test.example.com", 443)
            # 3. Expire TTL -> expired + miss
            clock["now"] += 61.0
            await resolve_and_validate_host("log-test.example.com", 443)
            # 4. Fill beyond capacity (512) to trigger LRU eviction
            for idx in range(512):
                await resolve_and_validate_host(f"evict-{idx}.example.com", 80)

        events = [getattr(record, "event", None) for record in caplog.records]
        assert "dns_cache_miss" in events
        assert "dns_single_flight_coalesced" in events
        assert "dns_cache_hit" in events
        assert "dns_cache_expired" in events
        assert "dns_cache_evicted" in events
