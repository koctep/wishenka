# WISHENKA-3: Observability Implementation

## Logging Implementation

### Added Logs

- **EMERG**: N/A for baseline web service
- **ALERT**: N/A for baseline web service
- **CRIT**: N/A for baseline web service
- **ERR**: `wishenka/web/app.py:RequestLoggingMiddleware` - Unhandled request exceptions with full stack trace and duration context
- **WARNING**: Configured root/application handlers capture standard warnings
- **NOTICE**: `wishenka/main.py:main` - Server initialization notice (`Starting Wishenka server on http://0.0.0.0:8000`)
- **INFO**:
  - `wishenka/web/app.py:lifespan` - Application startup and shutdown events with runtime metadata (`app_name`, `environment`, `debug`, `log_level`)
  - `wishenka/web/app.py:RequestLoggingMiddleware` - HTTP request completion events (`method`, `path`, `status_code`, `duration_ms`)
- **DEBUG**:
  - `wishenka/web/app.py:RequestLoggingMiddleware` - HTTP request received start event
  - `wishenka/web/app.py:healthcheck` - `/healthz` probe execution

### Log Structure

Log format used:
- Structured logs: Yes (configurable text console formatter and `JsonFormatter` in `wishenka/logging.py`)
- Includes context: Yes (ISO timestamp, log level, logger name, message, contextual `extra` fields, and formatted exceptions)
- Log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL configurable via `WISHENKA_LOG_LEVEL` (`Settings.log_level`, default `INFO`) and `WISHENKA_LOG_JSON` (`Settings.log_json`, default `false`)

## Metrics Implementation (if applicable)

### Performance Metrics

Added performance metrics:
- **Response time**: Measured via `time.perf_counter()` in `RequestLoggingMiddleware` and recorded in request logs as `duration_ms`
- **Throughput**: Captured via access logs
- **Error rate**: Captured via HTTP 5xx responses and ERROR log records

### Business Metrics

- Baseline infrastructure task WISHENKA-3 does not contain business domains yet; business metrics will be introduced in subsequent feature stories (wishes, users).

### System Health Metrics

System health metrics:
- **Component status**: `/healthz` endpoint returning `{"status": "ok"}` for Docker / orchestrator liveness and readiness probes

## Monitoring Integration

Integration with monitoring systems:
- [x] Docker stdout/stderr structured stream ready for log aggregators (ELK, Vector, Loki)
- [x] Optional structured JSON logging via `WISHENKA_LOG_JSON=true`
- [ ] Prometheus metrics (deferred to future monitoring epic)
- [ ] Grafana dashboards (deferred to future monitoring epic)
- [ ] Alerting rules (deferred to deployment stage)

## Validation Results

Validation results:
- [x] Logs are correctly formatted (tested with both human-readable and `JsonFormatter`)
- [x] Healthcheck endpoint `/healthz` verified and tested
- [x] Logging works in error scenarios (middleware captures unhandled exceptions)
- [x] Large data structures are not logged (only metadata: method, path, status, duration)
- [x] Verified by automated tests in `tests/test_observability.py` and repository gate `make check`

## Notes

- Pytest log capturing (`caplog`) compatibility is preserved by ensuring `configure_logging()` avoids wiping non-console handlers.
- Both text console formatting for local development and JSON output for production log ingestion are supported out-of-the-box.
