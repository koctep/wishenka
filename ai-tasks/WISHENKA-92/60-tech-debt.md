# WISHENKA-92: Technical Debt Analysis

## Shortcuts Taken

1. **Private `httpcore` / `httpx` attribute injection in `SSRFSafeTransport.__init__`** (`wishenka/items/ssrf.py:338-341`):
   - `httpx.AsyncHTTPTransport` does not expose `network_backend` as a public `__init__` parameter. To inject `SSRFSafeNetworkBackend` without reimplementing the entire connection pool, `SSRFSafeTransport.__init__` mutates `self._pool._network_backend` when `isinstance(self._pool, httpcore.AsyncConnectionPool)`.
   - **Trade-off**: Tightly coupled to `httpx` 0.28.x / `httpcore` 1.0.x internal attribute names (`_pool`, `_network_backend`). Also, if a proxy were ever passed to `SSRFSafeTransport`, `self._pool` would not be `httpcore.AsyncConnectionPool` and the backend wrapper would be skipped.

2. **`ContextVar` side-channel for passing pinned IPs** (`wishenka/items/ssrf.py:212-215`, `390-409`):
   - Because `httpcore.AsyncNetworkBackend.connect_tcp(host, port, ...)` does not receive `httpx.Request.extensions`, validated IPs are passed from `SSRFSafeTransport.handle_async_request` to `SSRFSafeNetworkBackend.connect_tcp` via `_pinned_ips_var` (`ContextVar`) keyed by `(clean_host, port)`.
   - **Trade-off**: Cleanly isolates concurrent asyncio tasks, and `SSRFSafeNetworkBackend.connect_tcp` includes a defense-in-depth fallback to `resolve_and_validate_host` on cache miss, but relies on `try ... finally: _pinned_ips_var.reset(token)` discipline.

## Code Quality Issues

1. **Indirect DNS failure propagation in `resolve_and_validate_host`** (`wishenka/items/ssrf.py:142-153`, `250-263`):
   - When `loop.getaddrinfo` raises `socket.gaierror` or `OSError`, `resolve_and_validate_host` logs `INFO` (`dns_resolution_failed`) and returns `[]`.
   - `SSRFSafeNetworkBackend.connect_tcp` then sees an empty `ips` list, logs `WARNING` (`ssrf_no_validated_ips`), and raises `httpcore.ConnectError("No validated IP addresses available for '...'")`, losing the original `gaierror` cause.
   - No `NON-BLOCKER` refactoring is urgent, as `httpx` surfaces `ConnectError` to `UrlMetadataService` which gracefully falls back, but propagating or preserving the DNS failure reason would improve diagnostics.

## Missing Tests

All tests in `tests/test_ssrf_dns_rebinding.py` declare the mandatory module-level timeout marker (`pytestmark = pytest.mark.timeout(30)`). The core DNS rebinding, redirect-hop pinning, Host/TLS SNI preservation, IPv6 pinning, multi-IP failover, concurrent `ContextVar` isolation, UDS blocking, and defense-in-depth paths are covered.

Minor edge-case branches in `SSRFSafeNetworkBackend.connect_tcp` without dedicated unit tests in `tests/test_ssrf_dns_rebinding.py`:
1. **Empty validated IP list (`ssrf_no_validated_ips`)**: Verifying that a `socket.gaierror` during `resolve_and_validate_host` causes `connect_tcp` to raise `httpcore.ConnectError` without invoking `self._inner.connect_tcp` with the raw hostname.
2. **All pinned IPs failing (`ssrf_all_pinned_connects_failed`)**: Verifying that when every pinned IP raises `OSError` / `httpcore.ConnectError`, `connect_tcp` logs `ssrf_all_pinned_connects_failed` and raises `httpcore.ConnectError` (wrapping `OSError` if needed).
3. **Duplicate IP deduplication**: Verifying `list(dict.fromkeys(ips))` avoids retrying the same IP twice when `getaddrinfo` returns duplicate addresses.

## Performance Concerns

1. **Sequential multi-IP failover with per-attempt `timeout`** (`wishenka/items/ssrf.py:267-292`):
   - `SSRFSafeNetworkBackend.connect_tcp` tries each IP in `unique_ips` sequentially, passing the full `timeout` to each `self._inner.connect_tcp` call.
   - If a dual-stack domain returns unreachable IPv6 addresses before a reachable IPv4 address (or multiple dead A records), total connection time can multiply by `len(unique_ips)` up to `len(unique_ips) * timeout` instead of sharing a total deadline or using Happy Eyeballs (RFC 8305).
   - **Impact**: Low for typical single-IP or healthy dual-stack hosts, but can cause slow link-preview timeouts on hosts with blackholed IPv6.

## Follow-up Tasks

- `NON-BLOCKER`: **Shared connect deadline / Happy Eyeballs in `SSRFSafeNetworkBackend.connect_tcp`** — bound total connection time across `unique_ips` (or race IPv6/IPv4 with a short stagger) so unreachable first IPs do not multiply the connect timeout. Jira: [WISHENKA-231](https://pypost.atlassian.net/browse/WISHENKA-231)
- `NON-BLOCKER`: **Edge-case unit tests for `SSRFSafeNetworkBackend.connect_tcp`** — add tests in `tests/test_ssrf_dns_rebinding.py` for empty IP list (`socket.gaierror`), all-IPs-failed (`OSError` wrapping), and duplicate IP deduplication. Jira: [WISHENKA-230](https://pypost.atlassian.net/browse/WISHENKA-230)
- Note: Configurable SSRF policy (`WISHENKA-93`), in-memory DNS caching (`WISHENKA-94`), and extended IPv6/redirect-chain coverage (`WISHENKA-95`) are already tracked as separate backlog tasks per `ai-tasks/WISHENKA-92/10-requirements.md`.
