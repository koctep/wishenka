# WISHENKA-132: Observability Implementation

## Logging Implementation

### Added Logs

- **WARNING**: [`WishlistStore.initialize()`](file:///home/src/wishenka/wishlists/store.py#L404-L413) — logs `wishlist_store_init_failed` before calling `await self.dispose()` when `initialize()` fails with any `BaseException` (including `asyncio.CancelledError` or unmapped exceptions). Includes `error_type` and `has_temporary_db` in `extra`.
- **DEBUG**: [`WishlistStore.dispose()`](file:///home/src/wishenka/wishlists/store.py#L426-L429) — logs `wishlist_store_temp_db_removed` when an owned temporary SQLite database and its sidecar/lock files are unlinked.

Existing caller and migration logs remain intact:
- [`upgrade_to_head_sync()`](file:///home/src/wishenka/wishlists/migrations.py#L258-L290) logs `wishlist_migration_started` (`INFO`), `wishlist_migration_failed` (`ERROR` with traceback via `logger.exception`), and `wishlist_migration_completed` (`INFO` with `duration_ms`).
- [`wishenka/web/app.py`](file:///home/src/wishenka/web/app.py#L210-L242) logs application startup and shutdown (`INFO`).

### Log Structure

Log format used:
- Structured logs: yes (`extra={"event": ...}` compatible with `wishenka.logging.JsonFormatter`)
- Includes context: yes (`event`, `error_type`, `has_temporary_db`; no filesystem paths or large payloads)
- Log levels: `WARNING`, `DEBUG`

## Metrics Implementation (if applicable)

Not applicable — the project does not currently integrate a metrics backend (no Prometheus/OpenTelemetry instrumentation). Migration duration is already recorded in `wishlist_migration_completed` (`duration_ms`).

## Monitoring Integration

Integration with monitoring systems:
- [ ] Prometheus metrics (not applicable to project)
- [ ] Grafana dashboards (not applicable to project)
- [ ] Alerting rules (not applicable)
- [x] Log aggregation (structured JSON logs via `wishenka.logging.JsonFormatter`)

## Validation Results

Validation results:
- [x] Logs are correctly formatted
- [x] Metrics are collected correctly (N/A)
- [x] Logging works in error scenarios (verified via `test_initialize_failure_logs_structured_cleanup_events`)
- [x] Large data structures are not logged
- [x] Metrics are available for monitoring (N/A)

## Notes

- Using `WARNING` for `wishlist_store_init_failed` avoids duplicate stack-trace noise alongside `upgrade_to_head_sync`'s `logger.exception("Wishlist database migration failed")` while still capturing store-level resource disposal for `CancelledError` or non-migration failures.
- Using `DEBUG` for `wishlist_store_temp_db_removed` avoids `INFO` log noise during frequent ephemeral `:memory:` store lifecycles in tests.
