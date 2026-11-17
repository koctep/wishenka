# WISHENKA-35: Observability Implementation

## Logging Implementation

### Added and Reviewed Logs

- **EMERG / ALERT / CRIT / NOTICE**: N/A — Wishenka uses Python `logging` levels (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`) formatted via `wishenka.logging.JsonFormatter` in JSON mode.
- **ERR**:
  - `wishenka/wishlists/deletion.py` (`AccountDeletionService.delete_account`): added `logger.error("Account deletion failed", exc_info=True, extra=...)` when the atomic deletion transaction raises an exception, recording `event="account_deletion_failed"`, `subject_hash_prefix`, `error_class`, and `duration_ms` before re-raising.
- **WARNING**:
  - `wishenka/web/routes/profile.py` (`delete_profile_account`): added `logger.warning("Rejected account deletion without explicit confirmation", extra=...)` on HTTP 422 when `confirm` is not `True`, recording `event="account_deletion_rejected"`, `reason="missing_confirmation"`, and `status_code=422`.
  - `wishenka/auth/dependencies.py` (`get_optional_current_user`, existing from Step 4): `logger.warning("Session token rejected: account deleted or session revoked", extra=...)` recording `event="session_rejected_revoked_or_deleted"`, `subject_hash_prefix`, and `auth_method`.
- **INFO**:
  - `wishenka/wishlists/deletion.py` (`AccountDeletionService.delete_account`):
    - Updated `account_deleted` log to include `subject_hash_prefix` and `duration_ms` alongside `deleted_lists`, `transferred_lists`, `cancelled_reservations`, and `anonymized_items`.
    - Added `account_deletion_already_deleted` log for idempotent repeat calls, recording `subject_hash_prefix` and `duration_ms`.
  - `wishenka/wishlists/cleanup.py` (`run_cleanup_cycle`, existing from Step 4): `background_cleanup_completed` includes `session_revocations_cleaned` and `duration_ms`.
- **DEBUG**:
  - `wishenka/wishlists/deletion.py` (`AccountDeletionService.preview_account_deletion`): added `logger.debug("Account deletion preview computed", extra=...)` recording `event="account_deletion_preview_computed"` and aggregate impact counts (`personal_lists_count`, `collaborative_transferred_count`, `collaborative_deleted_count`, `reservations_count`).

### PII & Secret Hygiene

- All logs in the account deletion, session revocation, and preview paths strictly omit `telegram_id`, `user_id`, `username`, `first_name`, `invite_token`, and raw session tokens.
- Correlation across deletion and subsequent rejected session attempts uses `subject_hash_prefix` (the first 12 hex characters of the keyed HMAC-SHA256 `compute_revocation_subject_hash(telegram_id, secret_key)`).
- Verified by automated test `tests/test_account_deletion.py::test_account_deletion_structured_logging_has_no_pii`.

### Log Structure

- Structured logs: yes (`wishenka.logging.JsonFormatter` places `extra` fields under `"extra"` in JSON log lines).
- Includes context: yes (`event`, `subject_hash_prefix`, operation counts, `duration_ms`, `error_class`, `reason`, `status_code`, `auth_method`).
- Log levels: `DEBUG`, `INFO`, `WARNING`, `ERROR`.

## Metrics Implementation (if applicable)

N/A — The repository does not use a separate metrics stack (Prometheus/OpenTelemetry metrics). Timing (`duration_ms`) and outcome counts are emitted via structured JSON logs.

### Performance Metrics

- **Response time**: `duration_ms` emitted in `account_deleted`, `account_deletion_already_deleted`, `account_deletion_failed`, and `background_cleanup_completed`.
- **Throughput / Error rate**: derivable from structured `event` counts (`account_deleted`, `account_deletion_already_deleted`, `account_deletion_rejected`, `account_deletion_failed`, `session_rejected_revoked_or_deleted`).

### Business Metrics

- `deleted_lists`, `transferred_lists`, `cancelled_reservations`, `anonymized_items` emitted in `account_deleted`.

### System Health Metrics

- `session_revocations_cleaned` emitted in `background_cleanup_completed` (`wishenka/wishlists/cleanup.py`).

## Monitoring Integration

- [ ] Prometheus metrics: N/A (no metrics stack in project)
- [ ] Grafana dashboards: N/A
- [ ] Alerting rules: N/A
- [x] Log aggregation: JSON lines via `wishenka/logging.py` (`JsonFormatter`) ready for stdout log collectors.

## Validation Results

- [x] Logs are correctly formatted (`JsonFormatter` verified in `test_account_deletion_structured_logging_has_no_pii`)
- [x] Metrics are collected correctly (`duration_ms` and deletion counts emitted in structured logs)
- [x] Logging works in error scenarios (`account_deletion_rejected` 422 and `session_rejected_revoked_or_deleted` 401 verified; `account_deletion_failed` added on transaction error)
- [x] Large data structures are not logged (only scalar counts, `duration_ms`, and 12-char `subject_hash_prefix`; zero PII)
- [ ] Metrics are available for monitoring: N/A (no metrics stack)

## Notes

- Static analysis (`make analyze`) and full test suite (`make test`) executed after all observability edits.
