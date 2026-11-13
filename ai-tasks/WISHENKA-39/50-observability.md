# WISHENKA-39: Observability Implementation

## Logging Implementation

### Added Logs

No log was added. This task adds characterization checks in
`tests/test_booking_ceiling_r5.py`. It does not change product code,
and it does not add a lock.

- **EMERG**: none added.
- **ALERT**: none added.
- **CRIT**: none added.
- **ERR**: none added.
- **WARNING**: none added.
- **NOTICE**: none added.
- **INFO**: none added.
- **DEBUG**: none added.

The checks do not read log records. They do not use `caplog`. The
signals they already use are the attempt result and the balance read
after every gifter in that race has finished.

- `InsufficientQuantityError` is a complete refusal. `_reserve` catches
  only that exception and records `error_type` as
  `InsufficientQuantityError`. `_require_attempt` accepts that type
  and no other error. `_assert_ceiling` then requires that a refused
  gifter has no occupying row.
- `InventoryBusyError` fails the check. `_require_attempt` raises
  `AssertionError` when `error_type` is `InventoryBusyError`. The
  check does not retry a busy result and does not raise
  `busy_timeout`.
- The balance after the race is the proof. `_load` runs only after
  the attempts have joined. `_assert_ceiling` compares that balance
  with the balance from before the barrier: booked units equal the
  free remainder that start, the free remainder ends at zero,
  requested quantity and received quantity are unchanged, and a
  pre-seeded occupying row keeps its gifter, quantity, and status.

Those checks call the existing wish-scoped write. A shortage on that
path already logs at WARNING. This step did not change those lines.

`create_reservation` in `wishenka/wishlists/service.py` logs
`insufficient_quantity_blocked` at WARNING when `quantity` is greater
than `item.available_quantity`, then raises `InsufficientQuantityError`.
The logger is `logging.getLogger("wishenka.wishlists")`, so the record
name is `wishenka.wishlists`. The extras include `item_id`,
`gifter_id`, `requested_quantity`, and `available_quantity`.

`execute_wish` in `wishenka/wishlists/store.py` then rolls the wish
transaction back. `_log_wish_rollback` logs
`wishlist_inventory_rolled_back` at WARNING for a domain refusal,
including `InsufficientQuantityError`. The store logger is
`logging.getLogger(__name__)`, so the record name is
`wishenka.wishlists.store`. The extras are `error_type`, `item_id`,
and `operation` (`create_reservation` for these checks). That record
does not include the gifter id.

A `SQLITE_BUSY` wait on the same store logger is
`wishlist_inventory_busy` at WARNING, and the store raises
`InventoryBusyError`. The R5 checks treat that exception as a failed
check. They do not assert the warning text. Shortage logs stay
WARNING, so the ERROR `caplog` contract does not apply.

### Log Structure

Log format used:

- Structured logs: unchanged. Existing events still use
  `extra={"event": ...}` on the standard library loggers. This step
  did not change `wishenka.logging`.
- Includes context: unchanged. The service refusal record carries the
  wish and the gifter. The store rollback record carries the wish,
  the operation, and the exception class, and omits the gifter.
- Log levels: none added. The existing refusal and busy records on
  this path are WARNING. A committed wish remains INFO
  (`wishlist_inventory_committed` on `wishenka.wishlists.store`).

## Metrics Implementation (if applicable)

No metric was added. The service gained no counter, histogram, or
exporter from this task. The load profile has no response-time target
and no throughput target. The proof is the balance after the race.

### Performance Metrics

Added performance metrics:

- **Response time**: none added.
- **Throughput**: none added.
- **Error rate**: none added.

### Business Metrics

Business metrics:

- None added. Booked quantity and the free remainder are asserted in
  `tests/test_booking_ceiling_r5.py`. They are not exported as metrics.

### System Health Metrics

System health metrics:

- **Resource usage**: none added.
- **Component status**: none added. `InventoryBusyError` fails the
  check. It is not counted as a health metric.

## Monitoring Integration

Integration with monitoring systems:

- [ ] Prometheus metrics
- [ ] Grafana dashboards
- [ ] Alerting rules
- [ ] Log aggregation (ELK, Loki, etc.)

No monitoring client was added. Existing refusal records stay on
`wishenka.wishlists` and `wishenka.wishlists.store`.

## Validation Results

Validation results:

- [ ] Logs are correctly formatted
- [ ] Metrics are collected correctly
- [ ] Logging works in error scenarios
- [ ] Large data structures are not logged
- [ ] Metrics are available for monitoring

No new log line or metric was emitted, so these checks were not run
against new instrumentation. The ceiling checks already in
`tests/test_booking_ceiling_r5.py` judge the attempt result and the
balance after the race. Step 5 ran that module: 6 passed. This step
did not re-run it and did not edit the tests.

## Notes

Product code was not changed. No lock was added. A later locking
story (WISHENKA-49) owns further exclusion. This step leaves the
existing WARNING refusal logs in place and adds none of its own.
