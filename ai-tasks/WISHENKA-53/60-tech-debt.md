# WISHENKA-53: Technical Debt Analysis

## Shortcuts Taken

The injected-client compatibility wrapper selects transports using HTTPX's private
`_transport_for_url`, `_transport` and `_pool` members and checks httpcore proxy pool types.
These implementation details can change across dependency releases. A changed internal proxy
representation could also invalidate the safety decision; tests and dependency review are
needed before upgrades. Application-owned requests instead use the dedicated safe transport.

The cache deliberately admits only explicitly public, non-varying, credential-free responses
without query strings. This lowers hit rate but avoids guessing whether a response is private.
Cache entries and pooled resources are per application instance and are lost on restart.
Concurrent misses may independently fetch and parse the same URL. The defaults of 256 entries,
300 seconds, 20 connections, 10 keep-alive connections and five seconds idle expiry are fixed
in code rather than operator settings.

## Code Quality Issues

The injected-client adapter couples security-sensitive proxy classification to HTTPX and
httpcore internals. It also adds a second request client and transport selection path to maintain.
Existing compatibility branches for mocked clients remain in the fetcher. Cache freshness and
eligibility use conservative custom HTTP header parsing rather than a reusable HTTP cache.

## Missing Tests

- A local HTTP/1.1 server test confirms that two non-cacheable previews reuse the same TCP
  connection; only its loopback destination is permitted by the test's DNS validator override.
- The offline tests exercise TTL, LRU, public eligibility, DNS revalidation, cookie isolation,
  proxy selection, startup cleanup and fallback behavior. They do not cover all custom third-party
  transport or proxy implementations, dependency versions, or production concurrency loads.
- `tests/test_preview_resource_reuse.py` declares a module timeout; its capacity test has an
  explicit longer timeout. The latest full test run recorded 348 passes and one dependency
  deprecation warning, already tracked in
  [WISHENKA-41](https://pypost.atlassian.net/browse/WISHENKA-41).

## Performance Concerns

Fresh destination resolution is performed for each cache hit and every redirect destination;
it may add latency but avoids reusing stale DNS decisions. Cache misses can duplicate work under
concurrency. Pool and cache limits are bounded per process, so deployment-wide resource use grows
with worker count. The extraction worker pool's saturation and cancellation behavior is already
tracked in [WISHENKA-113](https://pypost.atlassian.net/browse/WISHENKA-113).

The pre-existing DNS validation-to-connect race remains: a different address can be resolved
when the underlying socket connects. Revalidating cache hits and pooling do not pin that address.
The existing [WISHENKA-92](https://pypost.atlassian.net/browse/WISHENKA-92) tracks a pinned-IP
transport with preserved hostname and TLS identity; do not treat this implementation as closing it.

## Follow-up Tasks

- **NON-BLOCKER — Medium: Remove private HTTPX transport dependency.** Design a supported
  injected-client integration that isolates request state and preserves safe direct mounts,
  rejects proxy bypasses, retains ownership and lifecycle semantics, and tests dependency upgrades
  and concurrent requests. Until then, review HTTPX and httpcore changes before upgrading.
  Jira: [WISHENKA-114](https://pypost.atlassian.net/browse/WISHENKA-114)
- **Already tracked:** DNS rebinding is covered by WISHENKA-92; extraction load and cancellation
  by WISHENKA-113; the test-client deprecation warning by WISHENKA-41. No duplicate tickets are
  proposed for those findings.
