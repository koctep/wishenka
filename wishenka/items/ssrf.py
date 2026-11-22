"""SSRF protection, IP classification, non-blocking DNS, and secure HTTPX transport."""

import asyncio
import ipaddress
import logging
import os
import socket
import time
from collections import OrderedDict
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from weakref import WeakKeyDictionary

import httpcore
import httpx

from wishenka.config import (
    DEFAULT_SSRF_ALLOWED_SCHEMES,
    DEFAULT_SSRF_FORBIDDEN_CIDRS,
    DEFAULT_SSRF_MAX_RESPONSE_BYTES,
    SUPPORTED_SSRF_SCHEMES,
    Settings,
)
from wishenka.items.exceptions import InvalidUrlSchemeError, SSRFBlockedError, SSRFError

logger = logging.getLogger("wishenka.items")

IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network

MAX_RESPONSE_BYTES: int = DEFAULT_SSRF_MAX_RESPONSE_BYTES
ALLOWED_SCHEMES: frozenset[str] = frozenset(DEFAULT_SSRF_ALLOWED_SCHEMES)
DEFAULT_DNS_CACHE_TTL_SECONDS: float = 60.0
DEFAULT_DNS_CACHE_CAPACITY: int = 512

FORBIDDEN_NETWORKS: tuple[IPNetwork, ...] = tuple(
    ipaddress.ip_network(cidr, strict=False) for cidr in DEFAULT_SSRF_FORBIDDEN_CIDRS
)


@dataclass(frozen=True, slots=True)
class SSRFPolicy:
    """Immutable network safety and payload size policy for link previews."""

    max_response_bytes: int = MAX_RESPONSE_BYTES
    allowed_schemes: frozenset[str] = ALLOWED_SCHEMES
    forbidden_networks: tuple[IPNetwork, ...] = FORBIDDEN_NETWORKS

    def __post_init__(self) -> None:
        if self.max_response_bytes < 1:
            raise ValueError("max_response_bytes must be >= 1")
        if not self.allowed_schemes:
            raise ValueError("allowed_schemes must not be empty")
        if not self.allowed_schemes.issubset(SUPPORTED_SSRF_SCHEMES):
            raise ValueError(
                f"allowed_schemes must be a subset of {sorted(SUPPORTED_SSRF_SCHEMES)}"
            )

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "SSRFPolicy":
        """Build an immutable SSRFPolicy from a Settings instance or current defaults."""
        resolved = Settings() if settings is None else settings
        return cls(
            max_response_bytes=resolved.ssrf_max_response_bytes,
            allowed_schemes=frozenset(resolved.ssrf_allowed_schemes),
            forbidden_networks=tuple(
                ipaddress.ip_network(cidr, strict=False) for cidr in resolved.ssrf_forbidden_cidrs
            ),
        )


_default_policy_cache: tuple[tuple[Any, ...], SSRFPolicy] | None = None
_active_policy_var: ContextVar[SSRFPolicy | None] = ContextVar(
    "wishenka_active_ssrf_policy",
    default=None,
)


def _current_ssrf_env_signature() -> tuple[Any, ...]:
    """Build a lightweight cache signature for SSRF env vars and cwd .env file state."""
    try:
        cwd = Path.cwd()
        dotenv_path = cwd / ".env"
        try:
            dotenv_stat = dotenv_path.stat()
            dotenv_sig: tuple[str, int | None, int | None] = (
                str(cwd),
                dotenv_stat.st_mtime_ns,
                dotenv_stat.st_size,
            )
        except OSError:
            dotenv_sig = (str(cwd), None, None)
    except OSError:
        dotenv_sig = ("", None, None)

    return (
        os.environ.get("WISHENKA_SSRF_MAX_RESPONSE_BYTES"),
        os.environ.get("WISHENKA_SSRF_ALLOWED_SCHEMES"),
        os.environ.get("WISHENKA_SSRF_FORBIDDEN_CIDRS"),
        dotenv_sig,
    )


def redact_url_credentials(url: str) -> str:
    """Strip userinfo credentials from a URL string before writing to logs."""
    try:
        parsed = httpx.URL(url)
    except (httpx.InvalidURL, ValueError):
        return "[invalid-url]"
    if parsed.userinfo or parsed.username or parsed.password:
        return str(parsed.copy_with(username="", password=""))
    return url


def log_ssrf_policy_event(
    *,
    event: str,
    component: str,
    policy: SSRFPolicy,
    source: str,
) -> None:
    """Emit a bounded DEBUG summary of the active SSRF policy without dumping CIDRs."""
    logger.debug(
        "Active SSRF policy (%s/%s): max_response_bytes=%d, allowed_schemes=%s, "
        "forbidden_cidr_count=%d",
        component,
        source,
        policy.max_response_bytes,
        ",".join(sorted(policy.allowed_schemes)),
        len(policy.forbidden_networks),
        extra={
            "event": event,
            "component": component,
            "source": source,
            "max_response_bytes": policy.max_response_bytes,
            "allowed_schemes": sorted(policy.allowed_schemes),
            "forbidden_cidr_count": len(policy.forbidden_networks),
        },
    )


def log_ssrf_credentials_blocked(*, host: str) -> None:
    """Emit a structured SSRF warning when URL credentials or Authorization are blocked."""
    logger.warning(
        "SSRF blocked: URL credentials or Authorization header forbidden for host '%s'",
        host,
        extra={
            "event": "ssrf_blocked",
            "host": host,
            "reason": "credentials",
        },
    )


def log_ssrf_invalid_scheme(
    *,
    url: str,
    host: str,
    scheme: str,
    allowed_schemes: frozenset[str],
) -> None:
    """Emit a structured SSRF warning when a URL scheme is disallowed by policy."""
    safe_url = redact_url_credentials(url)
    logger.warning(
        "SSRF blocked: URL scheme '%s' is not allowed for '%s'",
        scheme,
        safe_url,
        extra={
            "event": "ssrf_blocked",
            "url": safe_url,
            "host": host,
            "scheme": scheme,
            "allowed_schemes": sorted(allowed_schemes),
            "reason": "invalid_scheme",
        },
    )


def get_default_ssrf_policy() -> SSRFPolicy:
    """Return the active default SSRFPolicy, cached per env/.env snapshot."""
    global _default_policy_cache
    signature = _current_ssrf_env_signature()
    cached = _default_policy_cache
    if cached is not None and cached[0] == signature:
        return cached[1]
    policy = SSRFPolicy.from_settings(Settings())
    _default_policy_cache = (signature, policy)
    log_ssrf_policy_event(
        event="ssrf_policy_loaded",
        component="ssrf",
        policy=policy,
        source="default_settings",
    )
    return policy


@contextmanager
def _use_ssrf_policy(policy: SSRFPolicy | None) -> Iterator[None]:
    """Scope an active SSRFPolicy in a task-local ContextVar across await boundaries."""
    if policy is None:
        yield
        return
    token = _active_policy_var.set(policy)
    try:
        yield
    finally:
        _active_policy_var.reset(token)


def resolve_ssrf_policy(
    *,
    settings: Settings | None = None,
    policy: SSRFPolicy | None = None,
) -> SSRFPolicy:
    """Resolve an SSRFPolicy from explicit overrides, active ContextVar, or defaults."""
    if settings is not None and policy is not None:
        raise ValueError("Provide at most one of 'settings' or 'policy', not both")
    if policy is not None:
        return policy
    if settings is not None:
        return SSRFPolicy.from_settings(settings)
    active = _active_policy_var.get()
    if active is not None:
        return active
    return get_default_ssrf_policy()


def _resolve_forbidden_networks(
    forbidden_networks: Sequence[IPNetwork] | None,
) -> tuple[IPNetwork, ...]:
    """Resolve the active tuple of forbidden IP networks."""
    if forbidden_networks is not None:
        return tuple(forbidden_networks)
    return resolve_ssrf_policy().forbidden_networks


def _is_ip_safe_for_networks(
    ip: str | ipaddress.IPv4Address | ipaddress.IPv6Address,
    active_networks: tuple[IPNetwork, ...],
) -> bool:
    """Validate baseline IP safety invariants and membership in ``active_networks``."""
    if isinstance(ip, str):
        try:
            ip = ipaddress.ip_address(ip)
        except ValueError:
            return False

    if any(ip.version == net.version and ip in net for net in active_networks):
        return False

    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return _is_ip_safe_for_networks(ip.ipv4_mapped, active_networks)

    if not ip.is_global:
        return False

    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def is_ip_safe(
    ip: str | ipaddress.IPv4Address | ipaddress.IPv6Address,
    *,
    forbidden_networks: Sequence[IPNetwork] | None = None,
) -> bool:
    """Validate whether an IP address is safe for outbound external requests.

    Returns False for loopback, private RFC1918, link-local, cloud metadata,
    CGNAT (100.64.0.0/10), multicast, broadcast, and reserved addresses, as well
    as any address falling inside the active forbidden networks.
    """
    active_networks = _resolve_forbidden_networks(forbidden_networks)
    return _is_ip_safe_for_networks(ip, active_networks)


@dataclass(frozen=True, slots=True)
class DNSCacheEntry:
    """Cached, SSRF-validated IP addresses for a hostname and port."""

    ips: tuple[str, ...]
    expires_at: float


def _normalize_dns_key(host: str, port: int) -> tuple[str, int]:
    """Normalize a hostname/port pair for DNS cache and single-flight lookup."""
    return (host.strip("[]").lower().rstrip("."), port)


class DNSCache:
    """Bounded in-memory TTL and LRU cache for SSRF-validated DNS resolutions."""

    def __init__(
        self,
        capacity: int = DEFAULT_DNS_CACHE_CAPACITY,
        ttl: float = DEFAULT_DNS_CACHE_TTL_SECONDS,
    ) -> None:
        self.capacity = capacity
        self.ttl = ttl
        self._entries: OrderedDict[tuple[str, int], DNSCacheEntry] = OrderedDict()

    def get(self, host: str, port: int) -> list[str] | None:
        """Return a fresh copy of cached IPs if present and unexpired, else None."""
        key = _normalize_dns_key(host, port)
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry.expires_at <= time.monotonic():
            del self._entries[key]
            logger.debug(
                "DNS cache entry expired for host '%s' on port %d",
                key[0],
                key[1],
                extra={
                    "event": "dns_cache_expired",
                    "host": key[0],
                    "port": key[1],
                },
            )
            return None
        self._entries.move_to_end(key)
        return list(entry.ips)

    def put(self, host: str, port: int, ips: Sequence[str]) -> None:
        """Store a non-empty validated IP list, evicting LRU entries beyond capacity."""
        if not ips or self.capacity <= 0 or self.ttl <= 0:
            return
        key = _normalize_dns_key(host, port)
        self._entries[key] = DNSCacheEntry(
            ips=tuple(ips),
            expires_at=time.monotonic() + self.ttl,
        )
        self._entries.move_to_end(key)
        while len(self._entries) > self.capacity:
            evicted_key, _ = self._entries.popitem(last=False)
            logger.debug(
                "DNS cache LRU entry evicted for host '%s' on port %d",
                evicted_key[0],
                evicted_key[1],
                extra={
                    "event": "dns_cache_evicted",
                    "evicted_host": evicted_key[0],
                    "evicted_port": evicted_key[1],
                    "capacity": self.capacity,
                },
            )

    def clear(self) -> None:
        """Remove all cached DNS entries."""
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)


_dns_cache = DNSCache()
_in_flight_resolutions: WeakKeyDictionary[
    asyncio.AbstractEventLoop,
    dict[tuple[tuple[str, int], tuple[IPNetwork, ...]], asyncio.Future[list[str]]],
] = WeakKeyDictionary()


def clear_dns_cache() -> None:
    """Clear the process-local DNS cache (intended for tests and lifecycle resets)."""
    _dns_cache.clear()


async def _resolve_and_validate_uncached(
    host: str,
    clean_host: str,
    port: int,
    active_networks: tuple[IPNetwork, ...],
) -> list[str]:
    """Perform uncached async DNS resolution and SSRF validation for all returned IPs."""
    logger.debug(
        "Resolving host '%s' on port %d for SSRF validation",
        clean_host,
        port,
        extra={
            "event": "dns_resolution_start",
            "host": host,
            "clean_host": clean_host,
            "port": port,
        },
    )
    loop = asyncio.get_running_loop()
    try:
        addr_info = await loop.getaddrinfo(
            clean_host,
            port,
            proto=socket.IPPROTO_TCP,
        )
    except (socket.gaierror, OSError) as exc:
        logger.info(
            "DNS resolution failed for host '%s': %s",
            clean_host,
            exc,
            extra={
                "event": "dns_resolution_failed",
                "host": clean_host,
                "error": str(exc),
            },
        )
        addr_info = []

    resolved_ips: list[str] = []
    for entry in addr_info:
        sockaddr = entry[4]
        ip_str = str(sockaddr[0])
        resolved_ips.append(ip_str)
        try:
            ip_obj = ipaddress.ip_address(ip_str)
        except ValueError as exc:
            logger.warning(
                "SSRF blocked: resolved invalid IP address '%s' for host '%s'",
                ip_str,
                host,
                extra={
                    "event": "ssrf_blocked",
                    "host": host,
                    "ip": ip_str,
                    "reason": "forbidden_ip",
                    "forbidden_cidr_count": len(active_networks),
                },
            )
            raise SSRFBlockedError(
                f"Resolved invalid IP address '{ip_str}' for host '{host}'",
                ip_address=ip_str,
                host=host,
                reason="forbidden_ip",
            ) from exc
        if not _is_ip_safe_for_networks(ip_obj, active_networks):
            logger.warning(
                "SSRF blocked: host '%s' resolved to restricted IP address '%s'",
                host,
                ip_str,
                extra={
                    "event": "ssrf_blocked",
                    "host": host,
                    "ip": ip_str,
                    "reason": "forbidden_ip",
                    "forbidden_cidr_count": len(active_networks),
                },
            )
            raise SSRFBlockedError(
                f"Host '{host}' resolved to restricted IP address '{ip_str}'",
                ip_address=ip_str,
                host=host,
                reason="forbidden_ip",
            )

    logger.debug(
        "DNS resolution completed for host '%s': resolved to %s",
        clean_host,
        resolved_ips,
        extra={
            "event": "dns_resolution_success",
            "host": clean_host,
            "resolved_ips": resolved_ips,
        },
    )
    return resolved_ips


async def resolve_and_validate_host(
    host: str,
    port: int = 80,
    *,
    forbidden_networks: Sequence[IPNetwork] | None = None,
) -> list[str]:
    """Resolve hostname to IP addresses asynchronously and verify none are forbidden.

    Raises:
        SSRFBlockedError: If destination resolves to a private or forbidden IP.
        SSRFError: If host is empty or resolution encounters an unhandled error.
    """
    if not host:
        raise SSRFError("Host cannot be empty")

    active_networks = _resolve_forbidden_networks(forbidden_networks)
    clean_host = host.strip("[]")

    try:
        ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address | None = ipaddress.ip_address(
            clean_host
        )
    except ValueError:
        ip_obj = None

    if ip_obj is not None:
        if not _is_ip_safe_for_networks(ip_obj, active_networks):
            logger.warning(
                "SSRF blocked: host '%s' is restricted IP address '%s'",
                host,
                str(ip_obj),
                extra={
                    "event": "ssrf_blocked",
                    "host": host,
                    "ip": str(ip_obj),
                    "reason": "forbidden_ip",
                    "forbidden_cidr_count": len(active_networks),
                },
            )
            raise SSRFBlockedError(
                f"Destination IP '{clean_host}' is private or forbidden",
                ip_address=str(ip_obj),
                host=host,
                reason="forbidden_ip",
            )
        logger.debug(
            "Direct IP '%s' validated as safe",
            clean_host,
            extra={
                "event": "dns_resolution_success",
                "host": host,
                "resolved_ips": [str(ip_obj)],
            },
        )
        return [str(ip_obj)]

    cached_ips = _dns_cache.get(clean_host, port)
    if cached_ips is not None:
        for ip_str in cached_ips:
            if not _is_ip_safe_for_networks(ip_str, active_networks):
                logger.warning(
                    "SSRF blocked: cached IP '%s' for host '%s' is forbidden under active policy",
                    ip_str,
                    host,
                    extra={
                        "event": "ssrf_blocked",
                        "host": host,
                        "ip": ip_str,
                        "reason": "forbidden_ip",
                        "cache_revalidation": True,
                        "forbidden_cidr_count": len(active_networks),
                    },
                )
                raise SSRFBlockedError(
                    f"Host '{host}' resolved to restricted IP address '{ip_str}'",
                    ip_address=ip_str,
                    host=host,
                    reason="forbidden_ip",
                )
        logger.debug(
            "DNS cache hit for host '%s' on port %d",
            clean_host,
            port,
            extra={
                "event": "dns_cache_hit",
                "host": clean_host,
                "port": port,
                "ip_count": len(cached_ips),
                "forbidden_cidr_count": len(active_networks),
            },
        )
        return cached_ips

    loop = asyncio.get_running_loop()
    key = (_normalize_dns_key(clean_host, port), active_networks)
    loop_in_flight = _in_flight_resolutions.setdefault(loop, {})
    existing_future = loop_in_flight.get(key)
    if existing_future is not None:
        logger.debug(
            "DNS resolution coalesced onto in-flight lookup for host '%s' on port %d",
            clean_host,
            port,
            extra={
                "event": "dns_single_flight_coalesced",
                "host": clean_host,
                "port": port,
            },
        )
        return list(await asyncio.shield(existing_future))

    logger.debug(
        "DNS cache miss for host '%s' on port %d",
        clean_host,
        port,
        extra={
            "event": "dns_cache_miss",
            "host": clean_host,
            "port": port,
        },
    )
    future: asyncio.Future[list[str]] = loop.create_future()
    loop_in_flight[key] = future
    try:
        resolved_ips = await _resolve_and_validate_uncached(host, clean_host, port, active_networks)
    except Exception as exc:
        if not future.done():
            future.set_exception(exc)
            future.exception()
        raise
    except BaseException:
        if not future.done():
            future.cancel()
        raise
    else:
        if resolved_ips:
            _dns_cache.put(clean_host, port, resolved_ips)
        if not future.done():
            future.set_result(resolved_ips)
        return list(resolved_ips)
    finally:
        if loop_in_flight.get(key) is future:
            loop_in_flight.pop(key, None)


_pinned_ips_var: ContextVar[dict[tuple[str, int], list[str]] | None] = ContextVar(
    "wishenka_pinned_ips",
    default=None,
)


class SSRFSafeNetworkBackend(httpcore.AsyncNetworkBackend):
    """Network backend that connects strictly to validated pinned IP addresses."""

    def __init__(
        self,
        inner: httpcore.AsyncNetworkBackend,
        *,
        policy: SSRFPolicy | None = None,
    ) -> None:
        self._inner = inner
        self._policy = policy

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        """Open a TCP connection strictly using validated IP addresses without DNS re-lookup."""
        clean_host = host.strip("[]")
        pinned_map = _pinned_ips_var.get()
        if pinned_map is not None and (clean_host, port) in pinned_map:
            ips = pinned_map[(clean_host, port)]
        else:
            active_policy = resolve_ssrf_policy(policy=self._policy)
            logger.debug(
                "Pinned IP cache miss for '%s:%d'; resolving via defense-in-depth",
                clean_host,
                port,
                extra={
                    "event": "ssrf_pinned_cache_miss",
                    "host": clean_host,
                    "port": port,
                    "policy_source": "pinned" if self._policy is not None else "ambient",
                    "forbidden_cidr_count": len(active_policy.forbidden_networks),
                },
            )
            with _use_ssrf_policy(active_policy):
                ips = await resolve_and_validate_host(clean_host, port)

        if not ips:
            logger.warning(
                "SSRF connect aborted: no validated IP addresses for '%s:%d'",
                clean_host,
                port,
                extra={
                    "event": "ssrf_no_validated_ips",
                    "host": clean_host,
                    "port": port,
                },
            )
            raise httpcore.ConnectError(
                f"No validated IP addresses available for '{clean_host}:{port}'"
            )

        unique_ips = list(dict.fromkeys(ips))
        last_exc: Exception | None = None
        for ip in unique_ips:
            try:
                return await self._inner.connect_tcp(
                    host=ip,
                    port=port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except (httpcore.ConnectError, httpcore.ConnectTimeout, OSError) as exc:
                last_exc = exc
                logger.debug(
                    "Pinned TCP connect failed for %s (%s:%d): %s",
                    clean_host,
                    ip,
                    port,
                    exc,
                    extra={
                        "event": "ssrf_pinned_connect_failed",
                        "host": clean_host,
                        "ip": ip,
                        "port": port,
                        "error": str(exc),
                    },
                )

        assert last_exc is not None
        logger.warning(
            "All %d pinned IP connection attempts failed for '%s:%d': %s",
            len(unique_ips),
            clean_host,
            port,
            last_exc,
            extra={
                "event": "ssrf_all_pinned_connects_failed",
                "host": clean_host,
                "port": port,
                "attempted_count": len(unique_ips),
                "error": str(last_exc),
            },
        )
        if isinstance(last_exc, (httpcore.ConnectError, httpcore.ConnectTimeout)):
            raise last_exc
        raise httpcore.ConnectError(str(last_exc)) from last_exc

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        """Block Unix domain socket connections."""
        logger.warning(
            "SSRF blocked: Unix domain socket connection attempted for '%s'",
            path,
            extra={
                "event": "ssrf_blocked",
                "path": path,
                "reason": "uds",
            },
        )
        raise SSRFBlockedError("Unix domain sockets are forbidden", reason="uds")

    async def sleep(self, seconds: float) -> None:
        """Delegate async sleep to the wrapped network backend."""
        await self._inner.sleep(seconds)


class SSRFSafeTransport(httpx.AsyncHTTPTransport):
    """Custom HTTPX transport enforcing SSRF validation on every request and redirect hop."""

    def __init__(
        self,
        *args: Any,
        policy: SSRFPolicy | None = None,
        settings: Settings | None = None,
        **kwargs: Any,
    ) -> None:
        if settings is not None and policy is not None:
            raise ValueError("Provide at most one of 'settings' or 'policy', not both")
        if policy is not None:
            resolved_policy: SSRFPolicy | None = policy
            log_ssrf_policy_event(
                event="ssrf_policy_configured",
                component="SSRFSafeTransport",
                policy=policy,
                source="policy",
            )
        elif settings is not None:
            resolved_policy = SSRFPolicy.from_settings(settings)
            log_ssrf_policy_event(
                event="ssrf_policy_configured",
                component="SSRFSafeTransport",
                policy=resolved_policy,
                source="settings",
            )
        else:
            if _active_policy_var.get() is None:
                # Fail fast on invalid ambient env/.env settings at transport creation.
                get_default_ssrf_policy()
            resolved_policy = None
        super().__init__(*args, **kwargs)
        self._policy = resolved_policy
        pool = self._pool
        if type(pool) is not httpcore.AsyncConnectionPool:
            raise RuntimeError("Cannot install SSRF-safe network backend")
        backend = getattr(pool, "_network_backend", None)
        if not isinstance(backend, httpcore.AsyncNetworkBackend):
            raise RuntimeError("Cannot install SSRF-safe network backend")
        safe_backend = SSRFSafeNetworkBackend(backend, policy=self._policy)
        pool._network_backend = safe_backend
        if pool._network_backend is not safe_backend:
            raise RuntimeError("Cannot install SSRF-safe network backend")
        self._safe_pool = pool
        self._safe_backend = safe_backend

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Validate request URL scheme and destination IP before dispatching TCP connection."""
        if (
            self._pool is not self._safe_pool
            or self._pool._network_backend is not self._safe_backend
        ):
            logger.warning(
                "SSRF blocked: SSRF-safe network backend unavailable for host '%s'",
                request.url.host,
                extra={
                    "event": "ssrf_blocked",
                    "host": request.url.host,
                    "reason": "unsafe_backend",
                },
            )
            raise SSRFBlockedError("SSRF-safe network backend unavailable", reason="unsafe_backend")
        if request.url.username or request.url.password or "authorization" in request.headers:
            log_ssrf_credentials_blocked(host=request.url.host)
            raise SSRFBlockedError("URL credentials are forbidden", reason="credentials")
        active_policy = resolve_ssrf_policy(policy=self._policy)
        scheme = request.url.scheme.lower()
        if scheme not in active_policy.allowed_schemes:
            allowed_display = ", ".join(sorted(active_policy.allowed_schemes))
            log_ssrf_invalid_scheme(
                url=str(request.url),
                host=request.url.host,
                scheme=scheme,
                allowed_schemes=active_policy.allowed_schemes,
            )
            raise InvalidUrlSchemeError(
                f"URL scheme '{scheme}' is not allowed; permitted schemes: {allowed_display}",
                scheme=scheme,
            )

        host = request.url.host
        if not host:
            logger.warning(
                "SSRF blocked: URL '%s' has no valid host",
                request.url,
                extra={
                    "event": "ssrf_blocked",
                    "url": str(request.url),
                    "reason": "missing_host",
                },
            )
            raise SSRFError(f"URL '{request.url}' has no valid host")

        port = request.url.port or (443 if scheme == "https" else 80)
        with _use_ssrf_policy(active_policy):
            resolved_ips = await resolve_and_validate_host(host, port)
            clean_host = host.strip("[]")
            current_pinned = dict(_pinned_ips_var.get() or {})
            current_pinned[(clean_host, port)] = resolved_ips
            token = _pinned_ips_var.set(current_pinned)

            logger.debug(
                "SSRF check passed for %s; dispatching transport request",
                request.url,
                extra={
                    "event": "ssrf_request_dispatch",
                    "url": str(request.url),
                    "host": host,
                    "scheme": scheme,
                    "pinned_ip_count": len(resolved_ips),
                },
            )
            try:
                return await super().handle_async_request(request)
            finally:
                _pinned_ips_var.reset(token)


__all__ = [
    "ALLOWED_SCHEMES",
    "DEFAULT_DNS_CACHE_CAPACITY",
    "DEFAULT_DNS_CACHE_TTL_SECONDS",
    "DNSCache",
    "DNSCacheEntry",
    "FORBIDDEN_NETWORKS",
    "MAX_RESPONSE_BYTES",
    "SSRFPolicy",
    "SSRFSafeNetworkBackend",
    "SSRFSafeTransport",
    "clear_dns_cache",
    "get_default_ssrf_policy",
    "is_ip_safe",
    "resolve_and_validate_host",
    "resolve_ssrf_policy",
]
