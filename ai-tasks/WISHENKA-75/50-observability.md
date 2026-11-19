# WISHENKA-75: Observability Implementation

## Logging Implementation

### Added Logs

- **ERR**: `wishenka/wishlists/store.py` (`WishlistStore.execute`) — Existing structured error log `Wishlist storage integrity error` (`event="wishlist_store_integrity_error"`) verified for FK constraint violations (`IntegrityError` on `wl_favorites`, `wl_view_history`, `wl_members`), without logging PII or user IDs.
- **WARNING**: `wishenka/wishlists/alembic/versions/add_user_fk_cascades.py` (`_rebuild_table`, logger `wishenka.wishlists.migrations`) — Added `Cleaned orphaned user/wishlist link rows during FK migration` (`event="user_fk_migration_orphans_cleaned"`, `table`, `rows_removed`, `rows_kept`) whenever orphaned rows are filtered out during upgrade.
- **INFO**: `wishenka/wishlists/alembic/versions/add_user_fk_cascades.py` (`_rebuild_table`, `upgrade`, `downgrade`, logger `wishenka.wishlists.migrations`) — Added:
  - `Rebuilt table with user_id cascade FK` (`event="user_fk_migration_table_rebuilt"`, `table`, `rows_kept`) when no orphans were removed.
  - `Applied user_id cascade FK migration` (`event="user_fk_migration_completed"`, `tables`, `total_orphans_removed`).
  - `Rebuilt table without user_id FK` (`event="user_fk_downgrade_table_rebuilt"`, `table`, `rows_kept`).
  - `Reverted user_id cascade FK migration` (`event="user_fk_downgrade_completed"`, `tables`).
- **INFO / ERR**: `wishenka/wishlists/deletion.py` (`AccountDeletionService.delete_account`) — Existing structured logs (`account_deleted`, `account_deletion_already_deleted`, `account_deletion_failed`) verified with `subject_hash_prefix` (no raw `telegram_id` or PII), `deleted_lists`, `transferred_lists`, `cancelled_reservations`, `anonymized_items`, and `duration_ms`.

### Log Structure

- Structured logs: yes (`extra={"event": ..., ...}` formatted by `wishenka.logging.JsonFormatter` in JSON mode)
- Includes context: yes (table names, row counts, `tables`, `total_orphans_removed`, `deleted_lists`, `subject_hash_prefix`, `duration_ms`)
- Log levels: `INFO`, `WARNING`, `ERROR` (syslog-compatible `ERR`)
- PII / secrets protection: verified no `user_id`, `telegram_id`, `first_name`, or secret values are emitted in migration, FK integrity error, or account deletion logs.

## Metrics Implementation (if applicable)

N/A — the project uses structured JSON logging (`wishenka.logging.JsonFormatter`) without a Prometheus/OpenTelemetry metrics backend.

## Monitoring Integration

Integration with monitoring systems:
- [ ] Prometheus metrics (N/A)
- [ ] Grafana dashboards (N/A)
- [ ] Alerting rules (N/A)
- [x] Log aggregation (structured JSON logs via `wishenka.logging.JsonFormatter`)

## Validation Results

- [x] Logs are correctly formatted (`make analyze`: Ruff lint, Ruff format, and Mypy passed across 213 files)
- [x] Metrics are collected correctly (N/A — no metrics backend)
- [x] Logging works in error scenarios (`caplog` assertions in `tests/test_wishenka_75_user_fk_cascade.py` verified `wishlist_store_integrity_error` at `ERROR`, `user_fk_migration_orphans_cleaned` at `WARNING`, `user_fk_migration_completed` at `INFO`, and `account_deleted` at `INFO`; 5/5 tests passed)
- [x] Large data structures are not logged (only table names and integer counts/durations)
- [x] Metrics are available for monitoring (N/A)

## Notes

- Verified `tests/test_wishenka_75_user_fk_cascade.py` with `caplog` per `do-testing` rules: `.venv/bin/pytest -n 0 tests/test_wishenka_75_user_fk_cascade.py` -> `5 passed` in `21.02s`.
