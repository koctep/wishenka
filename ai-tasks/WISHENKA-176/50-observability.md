# WISHENKA-176: Observability Implementation

## Logging Implementation

### Added and Audited Logs

- **ERR**: `wishenka/wishlists/store.py` (`_raise_for_storage_error`) — `reservation_cabinet_error`
  - Emitted when `get_user_reservations` or `get_user_reservations_summary` fails with a non-busy `SQLAlchemyError`.
  - Context fields: `event="reservation_cabinet_error"`, `operation` (`"reservations_list"` | `"reservations_summary"`), `error_type` (exception class name).
  - Omits `user_id`, raw SQL, bound parameters, and driver error text.
- **WARNING**: `wishenka/wishlists/store.py` (`_raise_for_storage_error`) — `reservation_cabinet_busy`
  - Emitted when `get_user_reservations` or `get_user_reservations_summary` fails with SQLite busy/locked (`is_sqlite_busy(exc)`).
  - Context fields: `event="reservation_cabinet_busy"`, `operation`.
- **DEBUG**: `wishenka/wishlists/store.py` (`WishlistStore._cabinet_service`) — `reservation_cabinet_read`
  - Emitted after hydrating the cabinet service inside `execute_read`.
  - Context fields: `event="reservation_cabinet_read"`, `include_items`, `reservations_count`, `items_count`, `wishlists_count`.
  - Omits `user_id`, item/wishlist titles, and capability tokens.
- **DEBUG**: `wishenka/wishlists/repository.py` (`WishlistRepository.get_items_by_ids`, `WishlistRepository.get_wishlist_headers_by_ids`) — `wishlist_repo_batch_read`
  - Emitted after each batched `IN (...)` lookup completes.
  - Context fields: `event="wishlist_repo_batch_read"`, `entity` (`"item"` | `"wishlist_header"`), `requested_count`, `chunks_count`, `found_count`.
  - Omits `user_id`, titles, and capability tokens (`public_token`, `invite_token`).

### Audited Unchanged Modules

- `wishenka/web/routes/reservations.py`: already emits `reservation_action_refused` (`WARNING`) and `reservation_action_completed` (`INFO`) without gifter IDs or wish graph dumps; write transactions delegate to `WishlistStore.execute_wish` / `execute_wish_idempotent` (`wishlist_inventory_committed`, `wishlist_inventory_busy`, `wishlist_inventory_rolled_back`, `idempotency_replay_hit`).
- `wishenka/web/routes/reservations_ui.py`: thin read-only presentation layer delegating to `WishlistStore.get_user_reservations` and `get_user_reservations_summary`; no additional logging needed.

### Log Structure

- Structured logs: yes (`JsonFormatter` in `wishenka/logging.py` serializes `extra` fields under `"extra"`).
- Includes context: yes (`event`, `operation`, `entity`, `chunks_count`, row counts, `error_type`).
- Log levels: `ERROR`, `WARNING`, `DEBUG`.

## Metrics Implementation (if applicable)

Not applicable — the project uses structured application logging without a Prometheus/StatsD metrics exporter. Batch chunk counts and hydrated entity counts are recorded in `DEBUG` logs.

## Monitoring Integration

- [ ] Prometheus metrics (N/A)
- [ ] Grafana dashboards (N/A)
- [ ] Alerting rules (N/A)
- [x] Log aggregation (`JsonFormatter` structured JSON output supported via `settings.log_json`)

## Validation Results

- [x] Logs are correctly formatted (verified via `ruff`, `mypy`, and `caplog` tests)
- [x] Logging works in error scenarios (`tests/test_reservation_index_lifecycle.py::test_cabinet_storage_error_logs_read_context_without_user_data`)
- [x] Large data structures, PII, and capability tokens are not logged (`tests/test_cabinet_batch_and_read_tx_repro.py::test_cabinet_and_batch_read_logging_omits_pii_and_tokens`)

## Notes

- `aiosqlite` logger level remains pinned to `WARNING` in `wishenka/wishlists/store.py` so bound SQL parameters (including capability tokens) are never emitted at `DEBUG`.
