# WISHENKA-57: Observability Implementation

## Logging Implementation

### Added Logs

Wish-scoped inventory changes log on `wishenka.wishlists.store` from
`WishlistStore.execute_wish`, after `COMMIT` or after rollback.
`wishenka.logging.configure_logging` accepts `DEBUG`, `INFO`, `WARNING`,
`ERROR`, and `CRITICAL`. It has no `EMERG`, `ALERT`, or `NOTICE` level, so
those syslog names are not emitted. `CRITICAL` is unused: a busy or
rolled-back wish does not stop the process.

- **EMERG**: not used. This logger has no EMERG level, and this path does
  not stop the process.
- **ALERT**: not used. This logger has no ALERT level.
- **CRIT**: not used. Python `CRITICAL` exists and is not emitted here.
- **ERR**: `wishenka.wishlists.store` — `wishlist_inventory_rolled_back` at
  Python `ERROR` when a wish transaction rolls back for a non-busy
  storage failure (`SQLAlchemyError` that is not the busy case). Context
  is `item_id` and/or `reservation_id`, `operation`, and `error_type`
  (the exception class). The driver text and SQL are omitted. The
  exception is rolled back and re-raised as `RuntimeError`.
- **WARNING**: `wishenka.wishlists.store` — `wishlist_inventory_busy` when
  `SQLITE_BUSY` becomes `InventoryBusyError`. Context is `item_id` or
  `reservation_id`, plus `operation`. No gifter id, name, or other user's
  data.
- **WARNING**: `wishenka.wishlists.store` — `wishlist_inventory_rolled_back`
  when a domain refusal aborts the wish transaction. That includes
  `WishlistError` and `ValueError` from `record_item_fulfillment`,
  `update_reservation_quantity`, and `update_wish_item` (quantity and
  membership refusals). Context is `error_type`, `item_id` or
  `reservation_id`, and `operation`. The exception text, gifter identity,
  and row dumps are omitted. The exception is rolled back and re-raised.
- **WARNING**: `wishenka.web.items` — `item_inventory_busy` on HTTP 503.
  Adds `item_id` when the route is wish-scoped. The response body stays
  the busy sentence and does not include the log record.
- **WARNING**: `wishenka.web.items_ui` — `ui_item_edit_busy` was already
  present for the edit modal. It keeps `wishlist_id` and `item_id` and
  names no gifter. The modal sentence is unchanged.
- **NOTICE**: not used. This logger has no NOTICE level. A committed wish
  is INFO.
- **INFO**: `wishenka.wishlists.store` — `wishlist_inventory_committed`
  after `COMMIT`. Context is `item_id`, `operation`, and
  `reservations_written` (a count). No row dump, token, title, or gifter
  identity.
- **DEBUG**: not added. The aiosqlite logger stays at WARNING so SQL
  parameters are not emitted.

`operation` is the domain method name (`create_reservation`,
`update_wish_item`, and the other wish-scoped methods), the item route
function name, or `submit_edit_item` for the edit modal.

A full-snapshot `execute` that is not wish-scoped still logs
`wishlist_inventory_busy` without an item id, and `wishlist_store_error`
for a non-busy database error. That entry has no wish key to record.

### Log Structure

Log format used:

- Structured logs: yes (`extra={"event": ...}` on the standard library
  logger; JSON when `json_logs` is enabled)
- Includes context: yes (`item_id` or `reservation_id`, `operation`,
  rollback `error_type`, commit `reservations_written`)
- Log levels: INFO, WARNING, ERROR

These events omit gifter and actor ids, names, capability tokens, wishlist
titles, item text, prices, SQL, driver messages, and full row or graph
dumps. The records stay on the server. The busy API detail and the edit
modal sentence do not name a gifter.

## Metrics Implementation (if applicable)

This service has no metrics exporter. No counters, histograms, or
monitoring client were added. The events above are the production signal
for this path.

### Performance Metrics

Added performance metrics:

- **Response time**: none. Commit timing is not measured.
- **Throughput**: none.
- **Error rate**: none as a metric. Busy and rollback events can be
  counted from logs.

### Business Metrics

Business metrics:

- `wishlist_inventory_committed`: one committed wish change, with
  `operation` and `reservations_written` — `WishlistStore.execute_wish`
- `wishlist_inventory_busy`: one retryable lock wait —
  `WishlistStore.execute_wish`
- `wishlist_inventory_rolled_back`: one aborted wish change —
  `WishlistStore.execute_wish`

### System Health Metrics

System health metrics:

- **Resource usage**: not collected on this path
- **Component status**: SQLite lock contention is the
  `wishlist_inventory_busy` warning

## Monitoring Integration

Integration with monitoring systems:

- [ ] Prometheus metrics
- [ ] Grafana dashboards
- [ ] Alerting rules
- [ ] Log aggregation (ELK, Loki, etc.)

The process can emit these records as text or JSON through
`wishenka.logging.configure_logging`. No scraper or dashboard was added.

## Validation Results

Validation results:

- [x] Logs are correctly formatted
- [ ] Metrics are collected correctly (no metrics were added)
- [x] Logging works in error scenarios
- [x] Large data structures are not logged
- [ ] Metrics are available for monitoring (no metrics were added)

`tests/test_shared_inventory_multiprocess.py`: 13 passed in 15.45s. The
cases check a commit, a domain `WishlistError` rollback, a `ValueError`
quantity refusal at WARNING, and a non-busy storage rollback at ERROR.
The busy case checks `wishlist_inventory_busy`. Those records contain the
item or reservation id and operation, and omit gifter ids, names, titles,
capability tokens, and driver text. `make analyze` passed: Ruff, format
check, and Mypy reported no issues.

## Notes

`wishlist_inventory_committed` is written only after `COMMIT`. A failure
does not emit it. The earlier `wishlist_inventory_write` record, which ran
inside the open transaction, was removed so a failed commit is not logged
as a success.

A domain refusal is WARNING. That includes `InsufficientQuantityError` and
a `ValueError` from a quantity or membership check in
`record_item_fulfillment`, `update_reservation_quantity`, or
`update_wish_item`. The rule rejected the change and the wish stayed at
the last commit. A non-busy database error (`SQLAlchemyError` other than
the busy case) is ERROR and becomes `RuntimeError` (`Wishlist storage
operation failed`). The refusal and the storage error are both re-raised
after rollback. `SQLITE_BUSY` stays `InventoryBusyError` and HTTP 503.
