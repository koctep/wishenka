# WISHENKA-54: Observability Implementation

## Logging Implementation

### Added Logs

Production structured logging added to `wishenka/items/ssrf.py`, `wishenka/items/fetcher.py`, and `wishenka/items/service.py`:
- **WARNING**: `wishenka/items/ssrf.py:resolve_and_validate_host` — Security event when direct IP or resolved hostname maps to a private/forbidden IP address (`event="ssrf_blocked"` with `host`, `ip`, `reason="forbidden_ip"`).
- **WARNING**: `wishenka/items/ssrf.py:SSRFSafeTransport.handle_async_request` — Security event when HTTP request attempts to use an unauthorized URL scheme (`event="ssrf_blocked"` with `url`, `host`, `scheme`, `reason="invalid_scheme"`).
- **WARNING**: `wishenka/items/fetcher.py:UrlMetadataService._fetch_html` — Security event when target URL or redirect hop uses an unauthorized URL scheme (`event="ssrf_blocked"` with `url`, `scheme`, `reason="invalid_scheme"`).
- **WARNING**: `wishenka/items/fetcher.py:UrlMetadataService._fetch_via_get` & `_stream_and_read` — Payload size violation when `Content-Length` header exceeds `max_bytes` (2MB) limit (`event="payload_size_violation"` with `url`, `content_length`, `max_allowed`, `reason="content_length_exceeded"`).
- **WARNING**: `wishenka/items/fetcher.py:UrlMetadataService._stream_and_read` — Payload size violation when streaming chunk accumulation exceeds `max_bytes` (2MB) limit (`event="payload_size_violation"` with `url`, `streamed_bytes`, `max_allowed`, `reason="stream_chunk_overflow"`).
- **WARNING**: `wishenka/items/service.py:ItemPreviewService.fetch_preview` — Graceful degradation fallback on SSRF block (`event="item_preview_ssrf_blocked"`) enriched with `url`, `url_domain`, `host`, `ip`, `reason`, `duration_ms`.
- **WARNING**: `wishenka/items/service.py:ItemPreviewService.fetch_preview` — Graceful degradation fallback on invalid scheme (`event="item_preview_invalid_scheme"`) enriched with `url`, `url_domain`, `scheme`, `duration_ms`.
- **WARNING**: `wishenka/items/service.py:ItemPreviewService.fetch_preview` — Graceful degradation fallback on oversized response (`event="item_preview_response_too_large"`) enriched with `url`, `url_domain`, `content_length`, `max_allowed`, `duration_ms`.
- **INFO**: `wishenka/items/ssrf.py:resolve_and_validate_host` — DNS resolution failure diagnostics (`event="dns_resolution_failed"` with `host`, `error`).
- **INFO**: `wishenka/items/fetcher.py:UrlMetadataService._stream_and_read` — Fetch completion summary without payload body (`event="url_fetch_success"` with `url`, `effective_url`, `bytes`).
- **DEBUG**: `wishenka/items/ssrf.py:resolve_and_validate_host` — DNS resolution lifecycle diagnostics (`event="dns_resolution_start"` and `event="dns_resolution_success"` with `clean_host`, `port`, `resolved_ips`).
- **DEBUG**: `wishenka/items/ssrf.py:SSRFSafeTransport.handle_async_request` — Request dispatch diagnostics (`event="ssrf_request_dispatch"` with `url`, `host`, `scheme`).
- **DEBUG**: `wishenka/items/service.py:ItemPreviewService.fetch_preview` — Plain text preview completion latency (`event="item_preview_plain_text"`).

### Log Structure

Log format used:
- Structured logs: Yes (`JsonFormatter` and standard logging extra dictionary support)
- Includes context: Yes (`event`, `url`, `host`, `ip`, `reason`, `content_length`, `max_allowed`, `duration_ms`)
- Log levels: `DEBUG`, `INFO`, `WARNING`, `ERROR`

## Metrics Implementation (if applicable)

### Performance Metrics

Added performance metrics:
- **Response time**: `duration_ms` recorded in structured logs for all preview outcomes (plain text, SSRF blocked, oversized payload, timeout, HTTP error, anti-bot challenge, success) in `wishenka/items/service.py`.
- **Throughput**: Tracked via `url_fetch_success` log events in `wishenka/items/fetcher.py`.
- **Error rate**: SSRF blocks (`item_preview_ssrf_blocked`) and payload overflows (`item_preview_response_too_large`) isolated by discrete event tags.

### Business Metrics

Business metrics:
- `item_preview_ssrf_blocked`: Number of malicious or internal resource scrape attempts mitigated.
- `item_preview_response_too_large`: Number of payload limit rejections preventing memory exhaustion.
- `fallback_reason`: Aggregable metric dimension indicating rate of fallback to plain text preview vs rich metadata.

### System Health Metrics

System health metrics:
- **Resource usage**: Memory protection verified by bounding HTML body consumption to <= 2 MB before memory allocation.
- **Component status**: Transport health and DNS resolution status logged via `dns_resolution_start`, `dns_resolution_success`, and `dns_resolution_failed`.

## Monitoring Integration

Integration with monitoring systems:
- [x] Structured JSON logger compatibility (`wishenka.logging.JsonFormatter`)
- [x] Standard syslog level mapping (`DEBUG`, `INFO`, `WARNING`, `ERROR`)
- [x] Log aggregation ready (ELK, Loki, Datadog parsing via standard JSON `extra` dictionary)
- [ ] Prometheus metrics export (deferred to central telemetry collector)
- [ ] Grafana dashboards (deferred to central ops)

## Validation Results

Validation results:
- [x] Logs are correctly formatted: Structured extra fields (`event`, `url`, `host`, `ip`, `reason`, `duration_ms`) validated.
- [x] Metrics are collected correctly: `duration_ms` and size metrics recorded on every path.
- [x] Logging works in error scenarios: Verified with unit tests covering SSRF blocks, invalid schemes, and oversized payloads.
- [x] Large data structures are not logged: Zero raw HTML bodies and zero authentication tokens/cookies in logs (`test_invariant_never_log_raw_html_or_secrets` passes).
- [x] Automated tests green: 26/26 tests passing in `tests/test_ssrf_and_response_limits.py`.
- [x] Static analysis clean: `make analyze` passed with 0 errors (Ruff lint, Ruff format, Mypy).

## Notes

- **Payload Security Invariant**: Raw response HTML payloads, query parameters with sensitive credentials, and authorization headers are never logged. Only domain/URL host, IP address, byte length, and timing are recorded in log extras.
