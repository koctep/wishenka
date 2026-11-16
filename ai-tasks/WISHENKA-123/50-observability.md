# WISHENKA-123: Observability Implementation

## Logging Implementation

### Added Logs

No server or browser logs were added. Token preparation and request cancellation occur in the
browser; a failed preparation displays a retry message in the affected card. The client does not
write the CSRF token, cookie, authorization header, or response body to the console.

Existing server events provide diagnostics when requests reach the server:

- `csrf_cookie_missing` at WARNING and `csrf_token_issued` at INFO are emitted by the token
  endpoint and include the authenticated Telegram user ID, but not the cookie or token value.
- `csrf_origin_mismatch` and `csrf_token_invalid` at WARNING are emitted by the security
  middleware with the request path; origin mismatches also include the supplied origin.

### Log Structure

These Python logger records carry structured `event` and context fields. Browser-side failures
before a request reaches the server are not represented by a dedicated server event; the visible
retry message is the local diagnostic. Existing application access logs may also record requests.

## Metrics Implementation

No performance, business, or system-health metrics were added. This change does not introduce a
metrics backend; client-side timeouts and malformed responses cannot be counted from these server
events alone.

## Monitoring Integration

No Prometheus metrics, Grafana dashboards, alert rules, or log aggregation were added.

## Validation Results

- The reviewed browser tests cover delayed and failed token preparation, timeout and recovery,
  CSRF rejection, recipient refusal, and bearer requests, including a real HTMX request.
- Step 5 reports a successful `make check` with 858 tests and a subsequent 12-test browser run.
- The changed client code does not log credentials. Existing structured server events were
  inspected; this step did not add or change their log contract or test production log capture.
- Metrics availability and deployed log aggregation were not validated.

## Notes

The token endpoint's existing user ID logging predates this task. A request cancelled before
dispatch leaves no mutation record; operators cannot infer its frequency from middleware logs.
