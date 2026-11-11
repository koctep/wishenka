# WISHENKA-54: Technical Debt Analysis

## Shortcuts Taken

1. **DNS Rebinding / TOCTOU (Time-of-Check to Time-of-Use) in HTTP Transport**:
   - `SSRFSafeTransport` in `wishenka/items/ssrf.py` verifies the destination IP by performing DNS resolution (`await resolve_and_validate_host(host, port)`) prior to delegating the request to `super().handle_async_request(request)`.
   - While this check successfully intercepts direct IP requests and redirect targets before sending the HTTP request, HTTPX's underlying connection pool (`httpcore`) performs its own internal DNS resolution when opening the socket connection.
   - If an attacker controls an authoritative DNS server configured with low/zero TTL that returns a safe public IP on the initial lookup, but resolves to a restricted private or loopback IP (`127.0.0.1`, `169.254.169.254`) on subsequent queries during socket connection, a TOCTOU DNS rebinding window exists.
   - *Remediation*: Implement a pinned-IP transport or custom socket connection factory where the HTTP connection is dialed directly to the validated IP address while preserving the original `Host` header and TLS Server Name Indication (SNI) for hostname verification.

2. **Dual-Path Interceptor for Custom vs Default HTTP Clients**:
   - To maintain backward compatibility with existing unit test suites that inject custom `AsyncMock` or preconfigured `httpx.AsyncClient` instances into `UrlMetadataService._fetch_html`, two separate interception mechanisms are used:
     - Default clients use `SSRFSafeTransport` as their underlying transport.
     - Injected clients dynamically attach and detach a `_request_validation_hook` to `client.event_hooks["request"]`.
   - While effective for current tests, this creates divergent code paths between production execution and injected test environments.

## Code Quality Issues

1. **Hardcoded Network Blacklist & Size Limit Constants**:
   - In `wishenka/items/ssrf.py`, `FORBIDDEN_NETWORKS`, `ALLOWED_SCHEMES`, and `MAX_RESPONSE_BYTES` (2 MB) are defined as static module-level constants.
   - While standard for defaults, these values are not currently wired to `wishenka/config.py` (`Settings.ssrf_network_blacklist`, `Settings.ssrf_max_response_bytes`, `Settings.ssrf_allowed_schemes`).
   - Moving these to Pydantic settings would enable runtime environment overrides for staging, CI, or environments with custom internal CIDR blocks.

2. **Redundant Scheme and Host Validation Steps**:
   - Scheme checks and host resolution are executed both at the service layer (`UrlMetadataService._fetch_html`) and at the transport layer (`SSRFSafeTransport.handle_async_request` / `_request_validation_hook`).
   - While defense-in-depth is desirable for security boundaries, consolidating these checks into a unified validation helper would reduce code duplication and simplify maintenance.

3. **Domain Exception Hierarchy Lacks Public Error Serializers**:
   - The domain exceptions (`SSRFBlockedError`, `ResponseBodyTooLargeError`, `InvalidUrlSchemeError`) cleanly encapsulate metadata attributes (`ip_address`, `host`, `reason`, `received_bytes`, `max_bytes`).
   - Currently, these exceptions are caught and mapped internally to `ItemPreviewDTO(is_fallback=True)`. If link preview error details are ever surfaced to admin interfaces or debug endpoints, standard error DTO serializers should be created.

## Missing Tests

1. **Mock vs Real Network Socket Integration Tests**:
   - Current test coverage in `tests/test_ssrf_and_response_limits.py` relies on mocking `loop.getaddrinfo` and HTTPX responses via `unittest.mock`.
   - There are no end-to-end integration tests using an ephemeral local HTTP server to verify that real TCP socket connections are physically refused or aborted at the transport layer upon HTTP 302 redirect to private IPs.

2. **Advanced IPv6 Representation Edge Cases**:
   - The test suite covers standard IPv4, RFC 1918, cloud metadata (`169.254.169.254`), standard IPv6 loopback (`::1`), link-local (`fe80::1`), and IPv4-mapped IPv6 (`::ffff:127.0.0.1`).
   - Obscure IPv6 variants (e.g., scoped zone IDs `fe80::1%eth0`, 6to4 relay addresses `2002::/16`, Teredo tunneling `2001::/32`, and alternative compressed zero representations) should be added to an extended parameterized test suite.

3. **Multi-Hop Redirect Chains and Loop Bounds**:
   - Existing redirect tests verify a single-hop redirect from a public origin to a restricted private IP.
   - Deep multi-hop redirect chains (e.g., public hop 1 -> public hop 2 -> private hop 3) and circular redirect loops under SSRF inspection are not tested under explicit chain-length bounds.

## Performance Concerns

1. **DNS Resolution Latency without In-Memory TTL Cache**:
   - `resolve_and_validate_host` invokes `loop.getaddrinfo` on every outbound scrape. In Python's asyncio implementation, `getaddrinfo` runs in the default threadpool executor (`ThreadPoolExecutor`).
   - During concurrent preview requests for popular domains, repeated synchronous DNS round-trips add 20–100ms latency per request and contend for threadpool worker threads.
   - An in-memory TTL-bounded DNS cache or asynchronous resolver (`aiodns`) would eliminate redundant lookups.

2. **Relation to Existing Architecture Backlog Items**:
   - **DEBT-1 ([WISHENKA-52](https://pypost.atlassian.net/browse/WISHENKA-52))**: Offloading `HtmlMetadataExtractor.extract` to worker threads via `asyncio.to_thread` or adopting a C-accelerated parser remains pending to prevent event-loop blocking on large HTML documents.
   - **DEBT-2 ([WISHENKA-53](https://pypost.atlassian.net/browse/WISHENKA-53))**: `UrlMetadataService` instantiates a short-lived `httpx.AsyncClient` per request, incurring full TCP handshake and TLS negotiation overhead. A persistent connection pool with keep-alive and preview caching is required to scale outbound requests.

## Follow-up Tasks

### DEBT-W54-1: Pinned-IP Transport to Eliminate DNS Rebinding (TOCTOU) Window
- **Jira Issue**: [WISHENKA-92](https://pypost.atlassian.net/browse/WISHENKA-92) (3.0 Story Points)
- **Estimate**: 3 Story Points
- **Description**: Implement a pinned-IP transport or custom socket connection factory for HTTPX that establishes TCP/TLS connections directly to the pre-validated IP address, setting the `Host` header and TLS Server Name Indication (SNI) to the original hostname to completely eliminate DNS rebinding risks.
- **Impact / Severity**: Medium. Hardens SSRF defenses against sophisticated DNS rebinding attacks on zero-TTL domains.
- **Priority**: Medium
- **Blocker Status**: Non-blocker for WISHENKA-54
- **Suggested Remediation**: Configure HTTPX with a custom `AsyncHTTPTransport` using a pinned socket factory or custom connection pool connecting directly to the validated IP.

### DEBT-W54-2: Configurable SSRF Settings via Pydantic Application Settings
- **Jira Issue**: [WISHENKA-93](https://pypost.atlassian.net/browse/WISHENKA-93) (1.0 Story Points)
- **Estimate**: 1 Story Point
- **Description**: Move `MAX_RESPONSE_BYTES`, `ALLOWED_SCHEMES`, and `FORBIDDEN_NETWORKS` from static constants in `wishenka/items/ssrf.py` to `wishenka/config.py` `Settings` (`ssrf_max_response_bytes`, `ssrf_allowed_schemes`, `ssrf_forbidden_cidrs`) with environment variable overrides.
- **Impact / Severity**: Low. Improves configurability across staging and CI environments.
- **Priority**: Low
- **Blocker Status**: Non-blocker for WISHENKA-54
- **Suggested Remediation**: Define Pydantic settings fields with default values and inject them into `UrlMetadataService`.

### DEBT-W54-3: In-Memory Asynchronous DNS Cache with TTL
- **Jira Issue**: [WISHENKA-94](https://pypost.atlassian.net/browse/WISHENKA-94) (2.0 Story Points)
- **Estimate**: 2 Story Points
- **Description**: Introduce an in-memory TTL-bounded DNS cache in `wishenka/items/ssrf.py` (or adopt `aiodns`) to cache safe hostname resolutions for a short duration (e.g., 60 seconds), reducing `getaddrinfo` threadpool contention and scrape latency under burst load.
- **Impact / Severity**: Medium. Reduces external DNS query latency and threadpool load.
- **Priority**: Medium
- **Blocker Status**: Non-blocker for WISHENKA-54
- **Suggested Remediation**: Wrap `resolve_and_validate_host` with an LRU cache with TTL expiration.

### DEBT-W54-4: Expanded Parameterized Test Suite for Complex IPv6 and Redirect Chains
- **Jira Issue**: [WISHENKA-95](https://pypost.atlassian.net/browse/WISHENKA-95) (2.0 Story Points)
- **Estimate**: 2 Story Points
- **Description**: Expand `tests/test_ssrf_and_response_limits.py` with parameterized test cases covering 6to4, Teredo IPv6 prefixes, scoped addresses, zero-compressed notation, multi-hop redirect chains, and circular redirect loop limits.
- **Impact / Severity**: Low. Provides exhaustive edge-case test coverage for uncommon IP formats.
- **Priority**: Low
- **Blocker Status**: Non-blocker for WISHENKA-54
- **Suggested Remediation**: Add `@pytest.mark.parametrize` suites in `tests/test_ssrf_and_response_limits.py`.
