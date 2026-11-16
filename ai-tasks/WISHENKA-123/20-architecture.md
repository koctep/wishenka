# WISHENKA-123: Coordinate giver requests with CSRF initialization

## Research

- `base.html` starts a cookie-bound token fetch on `DOMContentLoaded` and adds the token in
  `htmx:configRequest`; that synchronous hook currently cannot wait for the fetch.
- Giver-card mutations are HTMX POST or PATCH requests to reservation paths. Existing
  `htmx:afterRequest` maps every 403 to `notice=refused`; the security middleware instead
  returns JSON `{"detail":"Invalid CSRF token"}` for either invalid token or origin.
- `GET /api/auth/me` and the CSRF endpoint do not inherit headers added only to an HTMX
  request. The CSRF endpoint requires a cookie session and returns 401 for bearer auth. A
  separate authentication probe cannot safely establish which credentials a mutation carries.
- The pinned [HTMX 1.9.12 source](https://raw.githubusercontent.com/bigskysoftware/htmx/v1.9.12/src/htmx.js)
  builds request headers before the cancellable `htmx:configRequest` event and sends after it.
- [HTMX events](https://htmx.org/events/) document that `htmx:confirm` can cancel a request
  and later resume it via `issueRequest`; `htmx:configRequest` can set request headers.

## Implementation Plan

1. Maintain one bounded, shared CSRF fetch promise using same-origin credentials. Store the
   token only in JavaScript memory, never in HTML, URLs, logs, or DOM attributes. Concurrent
   clicks share the pending initialization. Do not infer mutation credentials from `/me`, page
   authentication, or whether the CSRF endpoint failed.
2. Intercept unsafe giver-card reservation requests at `htmx:confirm`. Defer while the shared
   token fetch settles, then resume through `issueRequest` without bypassing confirmation. The
   final synchronous `htmx:configRequest` guard checks the actual HTMX request headers: proceed
   only if a nonempty CSRF token is attached, or a nonempty explicit `Authorization: Bearer ...`
   is already present in the request configuration (case-insensitive header name). Cancel before
   XHR dispatch otherwise; show a retryable preparation message. Never copy bearer credentials
   from HTML or another request. An expired or invalid bearer is rejected by the server. A later
   click retries a failed token fetch; repeated pending clicks on one control are coalesced and a
   detached card must not issue a delayed request. Preserve other HTMX traffic and header hooks.
   Do not use a bearer exception if HTMX is configured to suppress request headers.
3. For a 403, parse the response safely. Only the exact structured middleware detail above is
   a CSRF rejection: do not refresh with `notice=refused`; show the separate retryable message,
   invalidate the cached cookie token, and fetch a fresh token on a later click. Preserve the
   existing card refresh and refused notice for actual recipient 403s. Do not automatically
   replay a rejected mutation. Network/parse failures must not create false recipient notices.
4. Add focused automated browser tests with bounded waits and no external network dependencies.
   Preserve existing recipient and bearer routes and run the appropriate full quality gate.

**Failing repro, Step 3:** Add a test in the existing browser test layout, using the project's
local HTMX stub or real locally served HTMX with actual event semantics. Hold the CSRF GET
response pending, click a giver-card mutation, and assert no mutation leaves the browser; release
it and assert exactly one request with the issued token. Current code dispatches before release,
so the test must fail for that assertion before production changes. Add a second red assertion
that a structured CSRF 403 never fetches `notice=refused`. Use bounded event barriers, explicit
pytest timeouts, and no sleeps as synchronization. Review the red tests before implementing.

## Architecture

```text
Giver control -> HTMX confirm gate -> bounded token initialization
                                         |
                               configRequest guard
                           token or explicit bearer header
                                         |
                            server security -> handler
                                         |
                          response classifier -> card refresh / error
```

- **Page security coordinator:** owns one initialization promise and cached token;
  shares it with the synchronous header hook and deferred giver-card gate. On failure or CSRF
  rejection it clears the appropriate state, enabling an explicit retry without leaking tokens.
- **HTMX gate:** scopes itself by the reservation path and `.item-card` ancestry, checks the
  method, and only cancels relevant mutations. Preserve other card and cabinet flows and HTMX
  hooks. A cancellable configRequest guard verifies the outgoing HTMX headers after they are
  built; pending operations have bounded lifetimes and do not act on removed elements.
- **Response classifier:** distinguishes only the documented JSON CSRF rejection from other
  403 responses, preserving existing recipient authorization handling and card expansion state.
- **Server:** existing authentication, middleware, endpoints, and security enforcement remain
  authoritative. Bearer API callers remain supported without a CSRF header; HTMX bearer
  callers are supported when their Authorization header is explicitly in the HTMX request
  configuration. Browser or proxy injected headers invisible to HTMX cannot be safely inferred
  by JavaScript: without an available cookie CSRF token, the UI fails closed for these callers.
- **Tests:** simulate delayed success, failed/empty/malformed or timed-out initialization,
  explicit retry, repeated clicks, stale card removal, token rejection, genuine recipient 403,
  and explicit HTMX bearer requests with no CSRF header. Assert token absent from initial HTML
  and no unprotected cookie mutation. Include bearer-only, cookie-only, and combined
  cookie-plus-bearer requests; simulate differing probe and mutation headers and ensure a failed
  CSRF fetch never authorizes a headerless cookie mutation. Test implicit browser-injected
  headers fail closed in the UI and retain a real server bearer API integration check.

## Q&A

- **Why inspect the actual outgoing headers?** Probe credentials can differ from the mutation.
  Only explicit HTMX request headers are visible to the guard; unknown credentials fail closed.
  An explicit bearer header wins on the server even when a cookie is also sent.
- **What happens after preparation failure?** No mutation is sent. A visible retry message
  invites another action, which triggers a fresh bounded initialization attempt.
- **How is a recipient refusal distinguished?** Match the middleware's exact JSON detail,
  without assuming all HTTP 403 responses mean the same thing.
