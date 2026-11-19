# WISHENKA-88: Observability Implementation

## Logging Implementation

### Added Logs

Describe added logging:
- **EMERG**: None
- **ALERT**: None
- **CRIT**: None
- **ERR**: None
- **WARNING**: `wishenka/web/rate_limit.py` (`PublicLinkRateLimitMiddleware.dispatch`) — logs `public_link_rate_limited` when a client exceeds the public-link sliding-window limit, recording `route` (token-redacted template: `/share/{token}`, `/invite/{token}`, or `/invite/{token}/join`), `method`, `client_ip`, and `retry_after` (in seconds), without ever logging raw capability tokens.
- **NOTICE**: None
- **INFO**: `wishenka/web/app.py` (`RequestLoggingMiddleware.dispatch`) — continues logging completed requests (including `429` responses) with masked public-link paths, `status_code`, and `duration_ms`.
- **DEBUG**: `wishenka/web/app.py` (`RequestLoggingMiddleware.dispatch`) — logs request start with masked public-link paths.

### Log Structure

Log format used:
- Structured logs: yes (`extra={...}` fields on `wishenka.web.rate_limit` logger)
- Includes context: yes (`event`, `route`, `method`, `client_ip`, `retry_after`)
- Log levels: `WARNING` (`public_link_rate_limited`), plus existing `INFO`/`DEBUG` in `RequestLoggingMiddleware`

## Metrics Implementation (if applicable)

No new Prometheus/OpenTelemetry metrics backend was added in this task; rate-limit rejections are observable via structured `public_link_rate_limited` warning logs and `RequestLoggingMiddleware` `status_code=429` completion logs.

### Performance Metrics

Added performance metrics:
- **Response time**: Existing `duration_ms` on `RequestLoggingMiddleware` - `wishenka/web/app.py`
- **Throughput**: N/A (derivable from request completion logs)
- **Error rate**: N/A (`429` rate-limit events derivable from `public_link_rate_limited` / `status_code=429` logs)

### Business Metrics

Business metrics:
- N/A

### System Health Metrics

System health metrics:
- **Resource usage**: N/A (`SlidingWindowRateLimiter` bounds memory via `max_clients` LRU/expired eviction)
- **Component status**: N/A

## Monitoring Integration

Integration with monitoring systems:
- [ ] Prometheus metrics
- [ ] Grafana dashboards
- [ ] Alerting rules
- [x] Log aggregation (structured `extra` fields compatible with JSON/structured log collectors)

## Validation Results

Validation results:
- [x] Logs are correctly formatted
- [ ] Metrics are collected correctly (N/A — no metrics backend)
- [x] Logging works in error/rate-limited scenarios (`test_rate_limit_logs_structured_event_without_token_leakage` in `tests/test_public_link_rate_limit.py`)
- [x] Large data structures and raw capability tokens are not logged
- [ ] Metrics are available for monitoring (N/A)

## Notes

- `test_rate_limit_logs_structured_event_without_token_leakage` in `tests/test_public_link_rate_limit.py` uses `caplog` to verify `event="public_link_rate_limited"`, `route`, `method`, `client_ip`, `retry_after >= 1`, and zero leakage of `public_token` or `invite_token` in logs.
