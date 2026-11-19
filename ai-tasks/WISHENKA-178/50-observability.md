# WISHENKA-178: Observability Implementation

## Logging Implementation

### Added / Verified Logs

- **ERR**: `wishenka/bot/__main__.py` (`cleanup_loop`) — emits `bot_draft_cleanup_failed` (`extra={"event": "bot_draft_cleanup_failed", "order_retention_days": order_retention_days}`) on transient cleanup failures without exposing exception details or PII.
- **INFO**: `wishenka/bot/capture.py` (`cleanup_drafts`) — emits `"Bot draft cleanup completed"` (`extra={"event": "bot_draft_cleanup_completed", "total_removed": ..., "bot_drafts_removed": ..., "birthday_input_removed": ..., "support_input_removed": ..., "support_tickets_removed": ..., "bot_capture_order_removed": ..., "order_retention_days": ..., "duration_ms": ...}`) whenever `total_removed > 0`.
- **DEBUG**: `wishenka/bot/capture.py` (`cleanup_drafts`) — emits `"Bot draft cleanup completed"` with the same structured `extra` payload when `total_removed == 0` so periodic idle runs do not flood production INFO logs.

### Log Structure

- Structured logs: yes (`wishenka.logging.JsonFormatter` serializes `extra` fields when `LOG_JSON=true`, and human-readable format is used otherwise)
- Includes context: yes (aggregate per-table row counts, `bot_capture_order_removed`, `order_retention_days`, `duration_ms`; no user/chat IDs or draft contents)
- Log levels: `ERROR`, `INFO`, `DEBUG`

## Metrics Implementation (if applicable)

This repository does not use a dedicated metrics backend (e.g., Prometheus/StatsD). Instead, operational indicators are emitted as structured log fields on `bot_draft_cleanup_completed` and `bot_draft_cleanup_failed` for log-based metric extraction:

### Performance Metrics

- **Execution duration**: `duration_ms` field on `bot_draft_cleanup_completed` (`wishenka/bot/capture.py`)
- **Error signal**: `bot_draft_cleanup_failed` event (`wishenka/bot/__main__.py`)

### Business / Retention Metrics

- `bot_capture_order_removed`: number of stale `bot_capture_order` watermarks purged per batch (`wishenka/bot/capture.py`)
- `total_removed`, `bot_drafts_removed`, `birthday_input_removed`, `support_input_removed`, `support_tickets_removed`: per-table cleanup batch counts (`wishenka/bot/capture.py`)
- `order_retention_days`: active retention window in days (`wishenka/bot/capture.py`, `wishenka/bot/__main__.py`)

### System Health Metrics

- N/A — covered by existing `/healthz` endpoint and periodic `cleanup_loop` failure logging.

## Monitoring Integration

Integration with monitoring systems:
- [ ] Prometheus metrics (N/A — project uses structured JSON logging via `wishenka.logging.JsonFormatter`)
- [ ] Grafana dashboards (N/A)
- [ ] Alerting rules (N/A — can alert on `event == "bot_draft_cleanup_failed"` in log aggregation)
- [x] Log aggregation (`JsonFormatter` emits structured JSON lines to stdout when `log_json=True`)

## Validation Results

- [x] Logs are correctly formatted (verified `make analyze`: Ruff lint, Ruff format, Mypy across 223 files)
- [x] Structured cleanup metrics fields are emitted (`tests/test_bot_capture_order_retention.py::test_cleanup_drafts_logs_structured_completion`)
- [x] Logging works in error scenarios (`tests/test_bot_capture_repro.py::test_cleanup_loop_recovers_from_transient_failure`)
- [x] Large data structures and PII (`owner`, `chat`, draft payloads) are not logged (verified in `test_cleanup_drafts_logs_structured_completion`)
- [x] Full targeted test suite passed: `47 passed` across `tests/test_bot_capture_order_retention.py`, `tests/test_bot_capture_order_retention_repro.py`, and `tests/test_bot_capture_repro.py`

## Notes

- `cleanup_drafts` keeps its existing `int` return value (`total_removed`) and signature so all existing callers and test doubles remain compatible.
- `cleanup_loop` preserves its privacy/security contract of not logging raw exception details on `bot_draft_cleanup_failed`.
