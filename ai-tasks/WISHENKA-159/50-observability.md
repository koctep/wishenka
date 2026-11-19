# WISHENKA-159: Observability Implementation

## Logging Implementation

### Added Logs

- **ERR (`logger.error`)**: `wishenka/wishlists/service.py` (`WishlistService._require_item_wishlist`) — logs an unreachable invariant violation whenever `item.wishlist is None` before raising `WishlistNotFoundError`:
  - Message: `"Invariant violation: item %s has no parent wishlist (wishlist_id=%s)"`
  - Structured `extra` payload:
    - `event`: `"item_missing_parent_wishlist"`
    - `item_id`: `item.id`
    - `wishlist_id`: `item.wishlist_id`

### Log Structure

- Structured logs: yes (`extra` dictionary with `event`, `item_id`, `wishlist_id` on `wishenka.wishlists` logger)
- Includes context: yes (`item_id`, `wishlist_id`; no full `WishItem` or `Wishlist` objects logged)
- Log levels: `ERROR`

## Metrics Implementation (if applicable)

N/A — the repository does not expose Prometheus/metrics collectors; structured `ERROR` logging provides immediate production alerting on `event="item_missing_parent_wishlist"`.

## Monitoring Integration

Integration with monitoring systems:
- [ ] Prometheus metrics (N/A)
- [ ] Grafana dashboards (N/A)
- [ ] Alerting rules (can alert on `event="item_missing_parent_wishlist"` at `ERROR` level)
- [x] Log aggregation (standard Python `logging` on `wishenka.wishlists` with `extra` fields)

## Validation Results

- [x] Logs are correctly formatted (`make analyze`: Ruff linter, Ruff format check, and Mypy passed across 219 source files)
- [x] Metrics are collected correctly (N/A)
- [x] Logging works in error scenarios (`tests/test_wishlist_fail_closed_repro.py`: 5 passed in 0.43s, exercising all five mutation entrypoints when `item.wishlist is None`)
- [x] Large data structures are not logged (only scalar `item.id` and `item.wishlist_id` are logged)
- [ ] Metrics are available for monitoring (N/A)

## Notes

- All four fail-closed guard sites (`update_wish_item`, `create_reservation`, `record_item_fulfillment`, and `_validate_receipt_mutation_access` used by `cancel_item_receipt` and `correct_item_receipt`) route through `WishlistService._require_item_wishlist`, so a single `logger.error` call covers every guarded mutation path.
