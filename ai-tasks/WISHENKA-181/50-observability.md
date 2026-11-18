# WISHENKA-181: Observability Implementation

## Logging Implementation

### Added and Verified Logs

- **INFO**: `wishenka/bot/birthdays.py` (`create_birthday_router` / `callback_handler`) — emits `birthday_deleted_anonymized` with `owner_id` and `birthday_id` after birthday soft-deletion and immediate PII anonymization (`label=''`, `month=0`, `day=0`, `deleted_at` set). No birthday `label`, date (`month`/`day`), or `chat_id` is logged.
- **INFO**: `wishenka/notices/store.py` (`NoticeStore.purge_finished`) — emits `notice_outbox_purged` with `receipt_purged`, `reminder_purged`, and `total_purged` when terminal outbox rows are purged (while preserving active-cycle reminders).
- **INFO**: `wishenka/notices/store.py` (`NoticeStore.purge_retention_records`) — emits `notice_retention_records_purged` with `birthdays_purged`, `destinations_purged`, and `receipt_keys_purged` when expired deleted birthdays, inactive `bot_destinations`, or expired `notice_receipt_keys` are purged.
- **INFO**: `wishenka/wishlists/cleanup.py` (`run_cleanup_cycle`) — emits `background_cleanup_completed` with `expired_tokens_cleaned`, `wishlists_purged`, `idempotency_records_cleaned`, `session_revocations_cleaned`, `birthdays_purged`, `bot_destinations_purged`, `receipt_keys_purged`, and `duration_ms`.
- **INFO**: `wishenka/wishlists/cleanup.py` (`_purge_notices`) — emits `receipt_notice_rows_purged` with `rows` when finished notice/reminder outbox rows are purged.
- **WARNING**: `wishenka/wishlists/cleanup.py` (`_purge_notices`) — emits `receipt_notice_purge_failed` with `error_class` (exception class name only, no raw PII/payload) if notice/retention purge fails, without failing the cleanup cycle.

### Log Structure

- Structured logs: **Yes** (standard `logging` with `extra={"event": ..., ...}`, formatted as JSON lines by `wishenka.logging.JsonFormatter` when `log_json=True`).
- Includes context: **Yes** (event name, non-PII entity IDs or aggregate row counts, duration in milliseconds, and `error_class` on failure).
- Log levels: `INFO`, `WARNING` (and `ERROR` on outer `background_cleanup_failed`).

## Metrics Implementation (if applicable)

### Performance Metrics

- **Cleanup cycle duration**: `CleanupStats.duration_ms` and `duration_ms` in `background_cleanup_completed` (`wishenka/wishlists/cleanup.py`).

### Business / Retention Metrics

- `CleanupStats.birthdays_purged`: count of anonymized deleted birthday rows physically purged (`wishenka/wishlists/cleanup.py`).
- `CleanupStats.bot_destinations_purged`: count of inactive `bot_destinations` rows physically purged (`wishenka/wishlists/cleanup.py`).
- `CleanupStats.receipt_keys_purged`: count of expired `notice_receipt_keys` rows physically purged (`wishenka/wishlists/cleanup.py`).

### System Health Metrics

- N/A (the application does not use a Prometheus/OpenTelemetry metrics exporter; structured JSON logs and `CleanupStats` provide the operational telemetry).

## Monitoring Integration

- [ ] Prometheus metrics (N/A for this repository)
- [ ] Grafana dashboards (N/A for this repository)
- [ ] Alerting rules (N/A for this repository)
- [x] Structured JSON log aggregation (`wishenka.logging.JsonFormatter`)

## Validation Results

- [x] Logs are correctly formatted (`JsonFormatter` verified in `tests/test_wishenka_181_observability.py` and `tests/test_token_cleanup_observability.py`)
- [x] Metrics/counts are collected correctly (`CleanupStats` and structured log fields verified)
- [x] Logging works in error scenarios (`test_retention_purge_failure_logs_warning_without_raising`)
- [x] Large data structures and PII are not logged (verified no birthday `label`, date, or `chat_id` in `caplog` / JSON output)

## Notes

- All retention and anonymization log events strictly omit PII (`label`, `month`/`day`, `chat_id`, tokens, and raw exception messages in `_purge_notices`).
