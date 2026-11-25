# WISHENKA-254: Observability Implementation

## Logging Implementation

### Added Logs

- **WARNING**: [store.py](file:///home/src/wishenka/wishlists/store.py#L1749-L1752) (`WishlistStore.execute_read`) — logs `"Wishlist read failed because the database was busy"` with `extra={"event": "wishlist_read_busy"}` when `SQLAlchemyError` matches `is_sqlite_busy(exc)` before raising `InventoryBusyError`.
- **WARNING**: [store.py](file:///home/src/wishenka/wishlists/store.py#L1762-L1769) (`WishlistStore.execute_read`) — logs `"Failed to reset query_only after wishlist read; invalidating connection"` with `extra={"event": "wishlist_read_query_only_reset_failed", "error_type": type(exc).__name__}` when resetting `PRAGMA query_only = OFF` in `finally` fails and triggers `await raw_conn.invalidate()`.

### Log Structure

Log format used:
- Structured logs: yes (`extra={"event": ..., ...}` on `wishenka.wishlists.store` logger)
- Includes context: yes (`event`, and `error_type` on `query_only` reset failure; no SQL statements, bound parameters, or PII)
- Log levels: `WARNING`

## Metrics Implementation (if applicable)

Not applicable — this repository uses structured logging without a Prometheus/OTel metrics backend for `WishlistStore`.

### Performance Metrics

Added performance metrics:
- None (N/A)

### Business Metrics

Business metrics:
- None (N/A)

### System Health Metrics

System health metrics:
- None (N/A)

## Monitoring Integration

Integration with monitoring systems:
- [ ] Prometheus metrics
- [ ] Grafana dashboards
- [ ] Alerting rules
- [x] Log aggregation (structured `event` fields emitted via standard Python `logging`)

## Validation Results

Validation results:
- [x] Logs are correctly formatted
- [ ] Metrics are collected correctly (N/A)
- [x] Logging works in error scenarios (verified via `caplog` in [test_wishenka_254_execute_read_hardening_repro.py](file:///home/src/tests/test_wishenka_254_execute_read_hardening_repro.py))
- [x] Large data structures are not logged
- [ ] Metrics are available for monitoring (N/A)

Verified commands after final edit:
- `.venv/bin/ruff check wishenka/wishlists/store.py tests/test_wishenka_254_execute_read_hardening_repro.py` — passed
- `.venv/bin/ruff format --check wishenka/wishlists/store.py tests/test_wishenka_254_execute_read_hardening_repro.py` — passed
- `.venv/bin/mypy wishenka/wishlists/store.py tests/test_wishenka_254_execute_read_hardening_repro.py` — passed
- `.venv/bin/pytest -q tests/test_wishenka_254_execute_read_hardening_repro.py` — 5 passed

## Notes

- `WishlistStore.execute_read` already logged `wishlist_read_busy` at `WARNING` level; `caplog` assertions were added to `test_execute_read_maps_sqlite_busy_to_inventory_busy_error`.
- Added structured `WARNING` logging (`wishlist_read_query_only_reset_failed`) before `raw_conn.invalidate()` in the `finally` block so connection invalidations on `PRAGMA query_only = OFF` failure are observable even when an active user exception suppresses re-raising the cleanup error.
