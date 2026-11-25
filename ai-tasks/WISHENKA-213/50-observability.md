# WISHENKA-213: Observability Implementation

## Logging Implementation

### Added Logs

Added scoped hydration and commit telemetry fields (`scoped: bool`, `wishlist_id: int | None`) to existing structured `INFO` log events in `wishenka/wishlists/store.py`:

- **INFO**: `wishenka/wishlists/store.py` (`WishlistStore._read`, `event="wishlist_store_read"`) - Logs `"Wishlist store snapshot loaded: %d wishlists, %d items"` with `extra` fields:
  - `scoped`: `wishlist_id is not None` (`True` for single-wishlist scoped reads, `False` for full-snapshot reads)
  - `wishlist_id`: target `wishlist_id` when scoped, `None` when unscoped
  - Existing counts: `wishlists_count`, `items_count`, `reservations_count`, `members_count`, `favorites_count`, `history_count`
- **INFO**: `wishenka/wishlists/store.py` (`WishlistStore._write`, `event="wishlist_store_write"`) - Logs `"Wishlist store committed changes: %d wishlists, %d items"` with `extra` fields:
  - `scoped`: `wishlist_id is not None` (`True` for single-wishlist scoped writes, `False` for full-snapshot writes)
  - `wishlist_id`: target `wishlist_id` when scoped, `None` when unscoped
  - Existing counts: `wishlists_count`, `members_count`, `items_count`, `reservations_count`, `deleted_wishlists_count`, `deleted_members_count`, `deleted_items_count`, `deleted_reservations_count`

Existing error/retry structured logs in `wishenka/wishlists/store.py` (`wishlist_token_collision_retry`, `wishlist_store_integrity_error`, `wishlist_store_error`) and `wishenka/wishlists/service.py` were inspected and left unchanged.

### Log Structure

Log format used:
- Structured logs: yes (`extra={...}` dict on Python `logging` records)
- Includes context: yes (`event`, `scoped`, `wishlist_id`, entity counts)
- Log levels: `INFO` (store read/write snapshots), `WARNING` (token collision retries, domain refusals, SQLite busy), `ERROR` (storage/integrity failures)

## Metrics Implementation (if applicable)

No separate Prometheus/StatsD metric collector is used in this repository; operational metrics are derived from structured log attributes (`scoped`, `wishlist_id`, `wishlists_count`, `items_count`, `history_count`) emitted by `WishlistStore._read` and `WishlistStore._write`.

### Performance Metrics

- **Hydration scope / row-load volume**: `wishlists_count`, `items_count`, `reservations_count`, `members_count`, `favorites_count`, `history_count`, and `scoped` (`True`/`False`) on `wishlist_store_read` in `wishenka/wishlists/store.py`
- **Write diff volume**: `wishlists_count`, `items_count`, `deleted_*_count`, and `scoped` on `wishlist_store_write` in `wishenka/wishlists/store.py`

### Business Metrics

- Not applicable (internal storage scoping optimization).

### System Health Metrics

- Not applicable (covered by existing storage error/busy structured logs).

## Monitoring Integration

Integration with monitoring systems:
- [ ] Prometheus metrics
- [ ] Grafana dashboards
- [ ] Alerting rules
- [x] Log aggregation (structured `extra` fields on `wishenka.wishlists.store` logger)

## Validation Results

Validation results:
- [x] Logs are correctly formatted (`ruff check`, `ruff format --check wishenka/ tests/`, `mypy wishenka/` passed)
- [x] Metrics/telemetry fields are collected correctly (`tests/test_wishenka_213_scoped_store_repro.py` and `tests/test_wishlists_sqlite_repo_observability.py` passed — 8 passed)
- [x] Logging works in error/missing-wishlist and token-collision scenarios (`test_scoped_store_handles_nonexistent_wishlist_id`, `test_scoped_token_regeneration_retries_on_cross_wishlist_collision`, `test_token_collision_retry_logging`)
- [x] Large data structures are not logged (only scalar IDs, booleans, and counts)
- [x] No capability tokens or secrets are leaked (`test_token_redaction_in_all_logs` passed)

## Notes

- Kept the existing event name `wishlist_store_write` in `WishlistStore._write` (rather than renaming it) to preserve compatibility with existing observability tests and log consumers.
- Did not modify `00-roadmap.md` per task instructions.
