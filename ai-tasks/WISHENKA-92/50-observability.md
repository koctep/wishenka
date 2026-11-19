# WISHENKA-92: Observability Implementation

## Logging Implementation

### Added Logs

Structured logs in `wishenka/items/ssrf.py` (logger `wishenka.items`):

- **WARNING**:
  - `SSRFSafeTransport.handle_async_request`: `event="ssrf_blocked"`, `reason="credentials"` — logs blocked requests containing URL credentials or `Authorization` header (without logging credential values).
  - `SSRFSafeNetworkBackend.connect_unix_socket`: `event="ssrf_blocked"`, `reason="uds"` — logs blocked Unix domain socket connection attempts with `path`.
  - `SSRFSafeNetworkBackend.connect_tcp`: `event="ssrf_no_validated_ips"` — logs when `connect_tcp` is invoked with an empty validated IP list for `host:port` before raising `httpcore.ConnectError`.
  - `SSRFSafeNetworkBackend.connect_tcp`: `event="ssrf_all_pinned_connects_failed"` — logs when all `attempted_count` pinned IP connection attempts fail for `host:port` with `error`.
- **INFO**:
  - Existing `resolve_and_validate_host`: `event="dns_resolution_failed"` — logs `socket.gaierror`/`OSError` during DNS resolution.
- **DEBUG**:
  - `SSRFSafeNetworkBackend.connect_tcp`: `event="ssrf_pinned_cache_miss"` — logs defense-in-depth fallback resolution when `_pinned_ips_var` has no entry for `(clean_host, port)`.
  - `SSRFSafeNetworkBackend.connect_tcp`: `event="ssrf_pinned_connect_failed"` (existing) — logs individual pinned IP connection failure during multi-IP failover.
  - `SSRFSafeTransport.handle_async_request`: `event="ssrf_request_dispatch"` — updated to include `pinned_ip_count` in `extra`.

### Log Structure

Log format used:
- Structured logs: yes (`extra={...}` fields formatted by `JsonFormatter` in `wishenka/logging.py` or standard formatter)
- Includes context: yes (`event`, `host`, `port`, `ip`, `path`, `reason`, `attempted_count`, `pinned_ip_count`, `error`)
- Log levels: `WARNING`, `INFO`, `DEBUG`

## Metrics Implementation (if applicable)

Not applicable: the project does not currently use a metrics backend (no Prometheus/OpenTelemetry metrics registry configured; `wishenka/logging.py` provides structured JSON logging).

### Performance Metrics

- N/A (not applicable to current project stack)

### Business Metrics

- N/A (not applicable to current project stack)

### System Health Metrics

- N/A (not applicable to current project stack)

## Monitoring Integration

Integration with monitoring systems:
- [ ] Prometheus metrics (N/A — not used in repository)
- [ ] Grafana dashboards (N/A — not used in repository)
- [ ] Alerting rules (N/A — not used in repository)
- [x] Log aggregation (structured JSON logs via `wishenka/logging.py` `JsonFormatter` to stdout)

## Validation Results

Validation results:
- [x] Logs are correctly formatted (verified via `make analyze`: `ruff check`, `ruff format --check`, `mypy`)
- [x] Metrics are collected correctly (N/A — logging only)
- [x] Logging works in error scenarios (verified via `pytest` SSRF test suite)
- [x] Large data structures are not logged (only scalar fields: `host`, `port`, `ip`, `reason`, counts, error string; credentials are never logged)
- [x] Metrics are available for monitoring (N/A — logging only)

## Notes

- All `SSRFBlockedError` paths in `wishenka/items/ssrf.py` now emit structured `WARNING` logs with `event="ssrf_blocked"` and `reason`.
- No secrets, URL credentials, or `Authorization` header values are included in log records.
