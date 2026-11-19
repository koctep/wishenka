# WISHENKA-180: Observability Implementation

## Logging Implementation

### Added Logs

**N/A — no new logs added.** `WISHENKA-180` is a pure interface refactoring (`TransactionalStore` protocol, `NoticeStore.transaction`, `NoticeStore` reminder delegation methods, and decoupling `NoticeWorker` / `ReminderScheduler` from private `NoticeStore._store`). All existing structured logging is preserved unchanged:

- **EMERG**: N/A
- **ALERT**: N/A
- **CRIT**: N/A
- **ERR**:
  - `wishenka/notices/worker.py` (`NoticeWorker.run`): logs `reminder_scheduler_error` and `receipt_notice_worker_error` with `error_class` (first failure in streak, avoiding log spam).
- **WARNING**: N/A
- **NOTICE**: N/A
- **INFO**:
  - `wishenka/notices/worker.py` (`NoticeWorker.flush_if_due`): logs `receipt_notice_window_summary` and `service_delivery_window_summary` with per-window counters (`sent`, `retried`, `failed_terminal`, `uncertain`, `skipped`).
  - `wishenka/notices/store.py` (`NoticeStore`): logs `receipt_notice_window_summary` / retention purge events (`notice_retention_records_purged`).
- **DEBUG**:
  - `wishenka/notices/scheduler.py` (`ReminderScheduler.run_once`): logs `reminder_scan_completed` (`lists_scanned`, `birthdays_scanned`, `intents_created`) when scan work occurs.
  - `wishenka/notices/reminders.py` (`claim_reminder`, `_normalize_row_locale`): logs `service_notice_skipped` (`outbox_id`, `kind`, `reason`) and `notice_locale_resolved` (`channel`, `locale`, `fallback_used`).
  - `wishenka/notices/worker.py` (`NoticeWorker.run_once`, `_debug`): logs `receipt_notice_batch_processed` (`rows`) and per-row receipt notice lifecycle events.
  - `wishenka/notices/store.py` (`NoticeStore._eligible`): logs `notice_locale_resolved` (`channel`, `locale`, `fallback_used`).

`NoticeStore.transaction`, `NoticeStore.claim_reminder`, `NoticeStore.refresh_reminder`, and `NoticeStore.settle_reminder` are thin boundary/delegation methods; adding extra logs at the transaction wrapper level would duplicate existing downstream and worker logs.

### Log Structure

Log format used (existing, preserved):
- Structured logs: yes (standard `logging.Logger` with `extra={...}` event dictionaries)
- Includes context: yes (`event`, `outbox_id`, `kind`, `reason`, `error_class`, `window_seconds`, `lists_scanned`, `birthdays_scanned`, `intents_created`, `locale`, `fallback_used`)
- Log levels: `ERROR`, `INFO`, `DEBUG`

## Metrics Implementation (if applicable)

### Performance Metrics

**N/A — no new metrics added.** `NoticeWorker` preserves its existing in-memory windowed counters (`_counts` and `_reminder_counts`) flushed via `NoticeWorker.flush_if_due` as `INFO` structured summary logs (`receipt_notice_window_summary`, `service_delivery_window_summary`).

### Business Metrics

- Existing reminder delivery counters (`sent`, `retried`, `failed_terminal`, `uncertain`, `skipped`) in `wishenka/notices/worker.py` (`NoticeWorker._reminder_counts`) remain intact after switching `NoticeWorker` from `self._store._store` to `self._store.claim_reminder` / `refresh_reminder` / `settle_reminder`.

### System Health Metrics

- **Resource usage**: N/A (not modified in this refactoring).
- **Component status**: Existing error-streak logging and exponential backoff in `NoticeWorker.run` (`reminder_scheduler_error`, `receipt_notice_worker_error`) remain unchanged.

## Monitoring Integration

Integration with monitoring systems (N/A for this refactoring; existing log-based structured events remain available):
- [ ] Prometheus metrics (N/A — project uses structured log aggregation / windowed summary logs)
- [ ] Grafana dashboards (N/A)
- [ ] Alerting rules (N/A)
- [x] Log aggregation (existing structured `extra` fields preserved without schema changes)

## Validation Results

Validation results:
- [x] Logs are correctly formatted (existing structured `extra` payloads in `worker.py`, `scheduler.py`, `reminders.py`, `store.py` verified untouched)
- [x] Metrics are collected correctly (`NoticeWorker._reminder_counts` and `flush_if_due` preserved and covered by existing notice/reminder tests)
- [x] Logging works in error scenarios (`reminder_scheduler_error` and `receipt_notice_worker_error` in `NoticeWorker.run` preserved)
- [x] Large data structures are not logged (only scalar IDs, counts, locale codes, event names, and `error_class` are logged; no message bodies or DB rows)
- [ ] Metrics are available for monitoring (N/A — no Prometheus endpoint in scope; existing structured summary logs preserved)

## Notes

- Because `WISHENKA-180` only replaces private `NoticeStore._store` coupling with the public `TransactionalStore` protocol and `NoticeStore` methods (`transaction`, `claim_reminder`, `refresh_reminder`, `settle_reminder`), no production code changes were needed for observability.
