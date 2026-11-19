# WISHENKA-183: Observability Implementation

## Logging Implementation

### Added Logs

Updated structured logging in `wishenka/notices/store.py` (`NoticeStore.purge_finished`):
- **INFO**: `wishenka/notices/store.py` (`NoticeStore.purge_finished`, event `notice_outbox_purged`) — extended the existing post-purge summary log (emitted only when `total > 0`) to include `batches` (number of `_purge_batch` transactions executed) and `batch_size` alongside `receipt_purged`, `reminder_purged`, and `total_purged`.

Evaluated other modified/inspected modules (no additional logging needed):
- `wishenka/notices/worker.py`, `wishenka/notices/reminders.py`, `wishenka/notices/scheduler.py`, `wishenka/notices/events.py`, `wishenka/notices/operator.py`: Changes in WISHENKA-183 only stamp/propagate `updated_at` on existing SQL writes. Per-row `updated_at` logging would be noisy; existing aggregate window summaries (`receipt_notice_window_summary`, `service_delivery_window_summary`), batch/skip debug logs, and error logs in `worker.py`/`reminders.py`/`scheduler.py` already cover delivery and retry diagnostics.
- `wishenka/wishlists/alembic/versions/add_reminder_outbox_updated_at.py`: Standard reversible Alembic migration; Alembic's runner already logs migration execution.

### Log Structure

Log format used:
- Structured logs: yes (`extra={"event": "notice_outbox_purged", ...}`)
- Includes context: yes (`receipt_purged`, `reminder_purged`, `total_purged`, `batches`, `batch_size` — aggregate integer counts only, no PII or row payloads)
- Log levels: `INFO` (for `notice_outbox_purged`; existing `DEBUG`/`INFO`/`WARNING`/`ERROR` levels in `worker.py`, `reminders.py`, `scheduler.py`, and `cleanup.py` remain unchanged)

## Metrics Implementation (if applicable)

### Performance Metrics

Not applicable (no Prometheus/OpenTelemetry metrics backend is configured in the repository; `cleanup.py` already records `duration_ms` and `background_cleanup_completed` via structured logs).

### Business Metrics

Not applicable (covered by aggregate structured log counts `receipt_purged`, `reminder_purged`, `total_purged`, `batches`, `batch_size`).

### System Health Metrics

Not applicable.

## Monitoring Integration

Integration with monitoring systems:
- [ ] Prometheus metrics (N/A — structured logging only)
- [ ] Grafana dashboards (N/A)
- [ ] Alerting rules (N/A)
- [x] Log aggregation (structured `extra` fields on `wishenka.wishlists.notices` logger)

## Validation Results

Validation results:
- [x] Logs are correctly formatted (`make analyze`: `ruff check`, `ruff format --check`, `mypy` all passed on 232 files)
- [x] Metrics are collected correctly (`batches` and `batch_size` verified in `tests/test_wishenka_183_updated_at.py::test_purge_finished_logs_batch_count_and_batch_size`)
- [x] Logging works in error scenarios (zero-row purge emits no `notice_outbox_purged` log; `cleanup.py` `_purge_notices` logs `receipt_notice_purge_failed` at `WARNING` on exception, verified in `tests/test_wishenka_181_observability.py`)
- [x] Large data structures are not logged (only scalar integer counts logged; no PII)
- [ ] Metrics are available for monitoring (N/A — no metrics exporter in project)

## Notes

- `NoticeStore.purge_finished` preserves the existing contract from WISHENKA-60 (`tests/test_wishenka_60_observability.py`) and WISHENKA-181 (`tests/test_wishenka_181_observability.py`) by emitting `notice_outbox_purged` only when `total > 0`.
