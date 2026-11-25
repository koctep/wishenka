# WISHENKA-188: Observability Implementation

## Logging Implementation

### Added Logs

Added structured observability in `wishenka/wishlists/alembic/versions/unify_user_keys_and_cascades.py` (logger `wishenka.wishlists.migrations`) to match existing FK migration conventions (`add_user_fk_cascades.py`):

- **WARNING**: `wishenka/wishlists/alembic/versions/unify_user_keys_and_cascades.py` (`_rebuild`) — `unify_user_keys_orphans_cleaned`: emitted when orphaned rows are filtered out during table rebuild (`table`, `rows_removed`, `rows_kept`).
- **INFO**: `wishenka/wishlists/alembic/versions/unify_user_keys_and_cascades.py` (`_ensure_users_columns`) — `unify_user_keys_users_columns_added`: emitted when missing birthdate columns are added to `users` (`columns`).
- **INFO**: `wishenka/wishlists/alembic/versions/unify_user_keys_and_cascades.py` (`_rebuild`) — `unify_user_keys_table_rebuilt`: emitted on clean table rebuilds (`table`, `rows_kept`).
- **INFO**: `wishenka/wishlists/alembic/versions/unify_user_keys_and_cascades.py` (`upgrade` / `downgrade`) — `unify_user_keys_migration_completed` (`tables=8`, `total_orphans_removed`) and `unify_user_keys_downgrade_completed` (`tables=8`).

Existing observability verified as sufficient in the other modified modules:
- `wishenka/users/store.py` (`wishenka.users`): `user_store_busy` (WARNING), `user_store_error` (ERROR), `user_created` / `user_updated` (INFO), `locale_auto_resolved` (DEBUG), `locale_explicit_updated` / `birthdate_explicit_updated` / `birthdate_explicit_cleared` (INFO); migration lifecycle logged by `wishenka/wishlists/migrations.py` (`upgrade_to_head`).
- `wishenka/wishlists/deletion.py` (`wishenka.wishlists.deletion`): `account_deletion_preview_computed` (DEBUG), `account_deletion_failed` (ERROR with `exc_info=True`, `subject_hash_prefix`, `error_class`, `duration_ms`), `account_deletion_already_deleted` / `account_deleted` (INFO with `subject_hash_prefix`, counts, `duration_ms` — no PII).
- `wishenka/web/routes/profile.py` (`wishenka.web.profile`), `wishenka/bot/*`, `wishenka/notices/*`: existing structured logging preserved.

### Log Structure

Log format used:
- Structured logs: yes (`extra={"event": ..., ...}`)
- Includes context: yes (table name, row counts, column names, `tables`, `total_orphans_removed`, `duration_ms`, `subject_hash_prefix`)
- Log levels: `WARNING`, `INFO`, `ERROR`, `DEBUG`

## Metrics Implementation (if applicable)

No new Prometheus/OpenTelemetry metrics added; existing `duration_ms` and row/item counters in structured logs cover migration and account deletion diagnostics.

## Monitoring Integration

Integration with monitoring systems:
- [ ] Prometheus metrics
- [ ] Grafana dashboards
- [ ] Alerting rules
- [x] Log aggregation (structured `extra` fields compatible with JSON log aggregation)

## Validation Results

Validation results:
- [x] Logs are correctly formatted
- [ ] Metrics are collected correctly (N/A — no metrics backend in this task)
- [x] Logging works in error / orphan-cleanup scenarios (`test_migration_logs_orphans_cleaned_and_completion_summary`)
- [x] Large data structures are not logged
- [ ] Metrics are available for monitoring (N/A)

## Notes

- All migration logs avoid logging user PII or token values, recording only table names and aggregate row counts.
