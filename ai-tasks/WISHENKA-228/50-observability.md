# WISHENKA-228: Observability Implementation

## Logging Implementation

Counting `HEAD` with `GET` does not add a log event. `match_public_link_route`
returns the same token-free templates for `HEAD` as for `GET`. Denial still
runs in `PublicLinkRateLimitMiddleware.dispatch` before the router, and that
branch logs `request.method` unchanged. A refused `HEAD` is therefore visible
as `method=HEAD` on the existing warning, and as a completed request with
`status_code=429`.

### Added Logs

Describe added logging:

- **EMERG**: None
- **ALERT**: None
- **CRIT**: None
- **ERR**: None
- **WARNING**: Existing, not new. `wishenka/web/rate_limit.py`
  (`PublicLinkRateLimitMiddleware.dispatch`) logs `public_link_rate_limited`
  when the shared allowance is spent. Fields: `route`
  (`/share/{token}` or `/invite/{token}` for a `HEAD` probe;
  `/invite/{token}/join` remains `POST` only), `method` (`HEAD` or `GET`),
  `client_ip`, and `retry_after` (seconds). The message uses the route
  template, never the raw token.
- **NOTICE**: None
- **INFO**: Existing, not new. `wishenka/web/app.py`
  (`RequestLoggingMiddleware.dispatch`) logs completion for the `429`,
  including `method=HEAD`, the sanitized path, `status_code`, and
  `duration_ms`. An in-budget `HEAD` is logged the same way with the status
  the router returns (`405` on the current stack).
- **DEBUG**: Existing, not new. The same middleware logs request start with
  `method` and the sanitized path before the limiter runs.

### Log Structure

Log format used:

- Structured logs: yes (`extra` on `wishenka.web.rate_limit` and
  `wishenka.web`; `JsonFormatter` nests those fields under `extra`)
- Includes context: yes (`event`, `route`, `method`, `client_ip`,
  `retry_after` on refusal; `method`, `path`, `status_code`, `duration_ms`
  on completion)
- Log levels: `WARNING` (`public_link_rate_limited`), plus existing `INFO`
  and `DEBUG` in `RequestLoggingMiddleware`

`sanitize_log_path` rewrites `/share/{secret}` and `/invite/{secret}` before
the request logs are written. It does not depend on the method, so `HEAD`
uses the same redaction as `GET`.

## Metrics Implementation (if applicable)

No metrics backend was added. The project does not emit Prometheus,
OpenTelemetry, or StatsD series for this limiter. Refusals stay observable
through `public_link_rate_limited` and `status_code=429` completion logs.
`method=HEAD` distinguishes an existence-check refusal from a page open.

### Performance Metrics

Added performance metrics:

- **Response time**: Existing `duration_ms` on `RequestLoggingMiddleware` —
  `wishenka/web/app.py`. A refused `HEAD` is included.
- **Throughput**: N/A (derivable from request completion logs)
- **Error rate**: N/A (`429` rate derivable from `public_link_rate_limited`
  and `status_code=429`)

### Business Metrics

Business metrics:

- N/A. Probe volume is the count of `public_link_rate_limited` records whose
  `method` is `HEAD` and whose `route` is `/share/{token}` or
  `/invite/{token}`.

### System Health Metrics

System health metrics:

- **Resource usage**: N/A (`SlidingWindowRateLimiter` still bounds memory
  with `max_clients`; `HEAD` shares the existing per-visitor bucket)
- **Component status**: N/A

## Monitoring Integration

Integration with monitoring systems:

- [ ] Prometheus metrics
- [ ] Grafana dashboards
- [ ] Alerting rules
- [x] Log aggregation (structured `extra` fields compatible with JSON
  collectors)

## Validation Results

Validation results:

- [x] Logs are correctly formatted
- [ ] Metrics are collected correctly (N/A — no metrics backend)
- [x] Logging works in the rate-limited `HEAD` scenario
- [x] Large data structures and raw capability tokens are not logged
- [ ] Metrics are available for monitoring (N/A)

A one-off check against `create_app` with `max_requests=1` sent
`HEAD /share/{token}` then `HEAD /invite/{token}` from `203.0.113.8`. The
first response was `405` and produced no `public_link_rate_limited` record.
The second was `429`. `JsonFormatter` rendered one `WARNING` from
`wishenka.web.rate_limit` with `event=public_link_rate_limited`,
`route=/invite/{token}`, `method=HEAD`, `client_ip=203.0.113.8`, and
`retry_after=60`, and one `INFO` completion from `wishenka.web` with
`method=HEAD`, `path=/invite/{token}`, `status_code=429`. Neither rendered
line contained the share token or the invite token. The existing
`test_rate_limit_logs_structured_event_without_token_leakage` still covers
`GET` and `POST /join`.

## Notes

No production logging change. The refusal was already on the path that runs
for every matched route, and `HEAD` is now a match for the two public-link
templates. In-budget probes are not a separate security event; they appear
only in the ordinary request start and completion logs.
