# WISHENKA-123: Technical Debt Analysis

## Shortcuts Taken

- The giver-card gate is implemented in the existing inline page script, alongside the existing
  HTMX security and card handlers. It uses the pinned HTMX 1.9.12 event contract rather than
  introducing a shared client framework.
- The CSRF initialization deadline is a fixed 10 seconds. If it expires, the request fails closed
  and the user can retry; this is not an automatic retry or a guarantee of network recovery.
- Bearer credentials injected outside the visible HTMX request configuration cannot be inferred
  safely by the client. If no CSRF token is available, these UI requests fail closed; server-side
  bearer API requests remain supported without a CSRF header.

## Code Quality Issues

- The page coordinator and the separate Mini App client each manage CSRF initialization. Their
  flows have different request mechanisms; this task does not change the Mini App flow.
- Tests retain locally served copies of pinned HTMX and its JSON extension with a license so that
  the real event path can be exercised without external network access. Dependency upgrades must
  keep these fixtures aligned with the application and verify their provenance and license.

## Missing Tests

- Browser checks cover delayed initialization, failed, empty, malformed and timed-out responses,
  retry, duplicate and detached controls, CSRF and recipient 403s, and bearer/cookie combinations.
  The real HTMX test verifies delayed dispatch and the persisted booking. The tests use explicit
  pytest timeouts; they cannot cover every external browser extension or proxy that adds headers.
- Step 5 reports a successful `make check` with 858 tests; after a formatting-only test change,
  the focused 12 browser tests and Ruff passed.

## Performance Concerns

- Concurrent giver interactions share one pending CSRF request; a single control's pending action
  is coalesced. A slow initialization delays an action for at most the configured deadline before
  showing a retryable error. Explicitly configured bearer actions can also wait for this deadline.
- The additional event checks are restricted to card reservation mutations. No new server-side
  scans or storage operations were introduced.

## Follow-up Tasks

- No new follow-up tasks are required for the accepted scope. The fixed deadline, separate Mini App
  flow, hidden-credential limitation and pinned test fixtures are documented maintenance trade-offs.
