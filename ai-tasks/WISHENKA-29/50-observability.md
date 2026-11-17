# WISHENKA-29: Observability Implementation

## Logging Implementation

### Added Logs

- **ERROR:** the worker emits `receipt_notice_worker_error` for queue failures and
  `reminder_scheduler_error` for scheduler failures, once per respective consecutive failure
  streak, with the exception class only. Both retry with bounded backoff; no exception message or
  traceback is included. Scheduler failure does not block delivery of already queued notices.
- **INFO:** the existing `receipt_notice_window_summary` reports aggregate receipt delivery
  outcomes. `service_delivery_window_summary` separately reports sent, retried, terminal failure,
  uncertain, and skipped service deliveries in a completed nonempty window.
- **DEBUG:** `reminder_scan_completed` reports aggregate counts of lists and birthdays scanned
  and new intents created after a successful transaction. Existing receipt events use opaque queue
  row IDs and attempts; the new service summary and scan do not expose per-user or per-row data.
- No new EMERG, ALERT, CRIT, or NOTICE events were necessary.

### Log Structure

Events use structured fields and the existing application logger. Summary counters, window duration,
and worker error classes also appear in the default plain-text output. Scan records contain
aggregate counts only. No birthday label or date, message
body, chat ID, user ID, credential, capability URL, reservation detail, or exception text is
included in the new records. Existing bot error handling suppresses aiogram traceback propagation;
the birthday user-store context filter keeps user profile fields out of birthday-input logs.

## Metrics Implementation

The process has no metrics exporter configured. The structured summary counters provide throughput
and error indicators for log aggregation; the scheduler scan provides diagnostic activity counts.
No new in-process Prometheus or Grafana dependency is introduced. Summaries are windowed in memory
and can be lost on abrupt shutdown; durable queue state remains the source of truth.

## Monitoring Integration

- Prometheus metrics: not configured.
- Grafana dashboards and alert rules: not configured.
- Log aggregation: compatible with the existing structured application logging pipeline.

## Validation Results

- Real scheduled delivery tests cover sent, retryable, terminal, and uncertain outcomes and assert
  aggregate counters without titles, capability strings, or user IDs in service records.
- Scheduler failure tests assert a safe error class, no exception text or URL, independent queued
  receipt delivery during repeated failures, recovery, and cancellation. The actual default
  formatter is checked for visible summary counters and a safe error class. Existing receipt
  observability tests cover receipt summaries and sender errors.
- The scheduler writes no record for an empty scan and the worker writes no idle window summary.
- Concurrent scans record one committed intent without logging the private occasion.
- `make check PYTEST_JOBS=4` passed after the review fixes: 985 tests, Ruff, formatting, and Mypy;
  four Starlette deprecation warnings remain.

## Notes

Uncertain sends require operator resolution and are counted separately from confirmed delivery.
External infrastructure must independently protect its own access and proxy logs.
