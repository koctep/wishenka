"""SSRF protection, IP classification, non-blocking DNS, and secure HTTPX transport."""

import asyncio
import ipaddress
import logging
import socket
from typing import Any

import httpx

from wishenka.items.exceptions import InvalidUrlSchemeError, SSRFBlockedError, SSRFError

logger = logging.getLogger("wishenka.items")

MAX_RESPONSE_BYTES: int = 2 * 1024 * 1024  # 2 MB (2,097,152 bytes)
ALLOWED_SCHEMES: frozenset[str] = frozenset({"http", "https"})

FORBIDDEN_NETWORKS: tuple[
    ipaddress.IPv4Network | ipaddress.IPv6Network,
    ...,
] = (
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
    ipaddress.ip_network("255.255.255.255/32"),
    ipaddress.ip_network("::/128"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("ff00::/8"),
)


def is_ip_safe(ip: str | ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Validate whether an IP address is safe for outbound external requests.

    Returns False for loopback, private RFC1918, link-local, cloud metadata,
    CGNAT (100.64.0.0/10), multicast, broadcast, and reserved addresses.
    """
    if isinstance(ip, str):
        try:
            ip = ipaddress.ip_address(ip)
        except ValueError:
            return False

    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return is_ip_safe(ip.ipv4_mapped)

    if not ip.is_global:
        return False

    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        return False

    return all(not (ip.version == net.version and ip in net) for net in FORBIDDEN_NETWORKS)


async def resolve_and_validate_host(host: str, port: int = 80) -> list[str]:
    """Resolve hostname to IP addresses asynchronously and verify none are forbidden.

    Raises:
        SSRFBlockedError: If destination resolves to a private or forbidden IP.
        SSRFError: If host is empty or resolution encounters an unhandled error.
    """
    if not host:
        raise SSRFError("Host cannot be empty")

    clean_host = host.strip("[]")

    try:
        ip_obj = ipaddress.ip_address(clean_host)
        if not is_ip_safe(ip_obj):
            logger.warning(
                "SSRF blocked: host '%s' is restricted IP address '%s'",
                host,
                str(ip_obj),
                extra={
                    "event": "ssrf_blocked",
                    "host": host,
                    "ip": str(ip_obj),
                    "reason": "forbidden_ip",
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
    except ValueError:
        pass

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
                },
            )
            raise SSRFBlockedError(
                f"Resolved invalid IP address '{ip_str}' for host '{host}'",
                ip_address=ip_str,
                host=host,
                reason="forbidden_ip",
            ) from exc
        if not is_ip_safe(ip_obj):
            logger.warning(
                "SSRF blocked: host '%s' resolved to restricted IP address '%s'",
                host,
                ip_str,
                extra={
                    "event": "ssrf_blocked",
                    "host": host,
                    "ip": ip_str,
                    "reason": "forbidden_ip",
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


class SSRFSafeTransport(httpx.AsyncHTTPTransport):
    """Custom HTTPX transport enforcing SSRF validation on every request and redirect hop."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Validate request URL scheme and destination IP before dispatching TCP connection."""
        scheme = request.url.scheme.lower()
        if scheme not in ALLOWED_SCHEMES:
            logger.warning(
                "SSRF blocked: URL scheme '%s' is not allowed for '%s'",
                scheme,
                request.url,
                extra={
                    "event": "ssrf_blocked",
                    "url": str(request.url),
                    "host": request.url.host,
                    "scheme": scheme,
                    "reason": "invalid_scheme",
                },
            )
            raise InvalidUrlSchemeError(
                f"URL scheme '{scheme}' is not allowed; only http and https are permitted",
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
        await resolve_and_validate_host(host, port)

        logger.debug(
            "SSRF check passed for %s; dispatching transport request",
            request.url,
            extra={
                "event": "ssrf_request_dispatch",
                "url": str(request.url),
                "host": host,
                "scheme": scheme,
            },
        )
        return await super().handle_async_request(request)


__all__ = [
    "ALLOWED_SCHEMES",
    "MAX_RESPONSE_BYTES",
    "SSRFSafeTransport",
    "is_ip_safe",
    "resolve_and_validate_host",
]
