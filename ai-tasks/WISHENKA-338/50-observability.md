# WISHENKA-338: Observability Implementation

One-wishlist openings now use `read_transaction` (`BEGIN` plus
`query_only`) instead of `BEGIN IMMEDIATE`. A finished read is the common
case. This step does not log or count it. A failed read keeps the error
it already raises. The failure signals that already exist on this path
stay in place. No production logger or metric was added.

## Logging Implementation

### Added Logs

None.

- **EMERG**: none. This service does not use that level.
- **ALERT**: none. This service does not use that level.
- **CRIT**: none. This service does not use that level.
- **ERR**: none added. A failed read still raises the error it already
  raised.
- **WARNING**: none added. A busy read and a failed `query_only` reset
  already log inside `read_transaction`.
- **NOTICE**: none. This service does not use that level.
- **INFO**: none added. A successful opening does not write a read event.
- **DEBUG**: none added.

### Records that already cover a failed read

#### Busy read

`wishlist_read_busy` (`WARNING`), logger `wishenka.wishlists.store`,
`WishlistStore.read_transaction` in `wishenka/wishlists/store.py`.

Message: `Wishlist read failed because the database was busy`.

`extra`: `event` only. The line is written when `is_sqlite_busy` accepts
the `SQLAlchemyError`. The method then raises `InventoryBusyError` from
that exception.

`get_wishlist_read_repository` does not log this again. It lets
`InventoryBusyError` leave the dependency. `install_inventory_busy_handler`
turns that exception into HTTP 503 with the existing detail and does not
log. A receipt route that catches `InventoryBusyError` still writes its
own `receipt_inventory_busy` warning. That warning was already there.

The seven service openings go through `run_repository_read`, which uses
the same context manager, so a busy opening writes this warning once.

#### `query_only` reset failure

`wishlist_read_query_only_reset_failed` (`WARNING`), same logger and
method.

Message: `Failed to reset query_only after wishlist read; invalidating connection`.

`extra`: `event` and `error_type` (the exception class name). The
connection is invalidated. If the read already failed, the reset error is
not raised again. If the read succeeded and the reset fails, that reset
error is raised.

#### Other database errors on an HTTP route that uses `execute`

A non-busy `SQLAlchemyError` that `wishlists.execute` catches still logs
ERROR `wishlist_store_error` (`Wishlist storage operation failed due to
database error`) and raises `RuntimeError("Wishlist storage operation
failed")`. That `RuntimeError` is not a `SQLAlchemyError`, so
`read_transaction` does not replace it and does not write
`wishlist_read_busy`.

#### Domain refusals

A missing wishlist, a deleted wishlist, a missing wish, a refused member
list, and a refused gifted list stay the exceptions those openings
already raise. Routes that already log a refusal (`wishlist_permission_denied`
and the modal and receipt refusal warnings) still do. This step does not
add a log for a refusal that was already returned without one.

#### Unhandled HTTP failure

A database error that no route converts still reaches
`RequestLoggingMiddleware`, which logs the unhandled exception with the
method and path. That middleware log is not a new event.

### Log Structure

Log format used:

- Structured logs: unchanged (`extra={"event": ...}` on the existing
  loggers)
- Includes context: unchanged (`event` on a busy read; `event` and
  `error_type` on a `query_only` reset failure)
- Log levels: none added

No wishlist body, wish list, member list, or SQL text is written for
these openings.

## Metrics Implementation (if applicable)

No new metric. A successful read is not counted. This repository has no
Prometheus or OpenTelemetry series for wishlist reads, and this step does
not add one.

### Performance Metrics

None.

### Business Metrics

None.

### System Health Metrics

None.

## Monitoring Integration

Integration with monitoring systems:

- [ ] Prometheus metrics
- [ ] Grafana dashboards
- [ ] Alerting rules
- [x] Log aggregation (existing structured `event` fields; none added)

## Validation Results

Checked by reading the read path. No production code was edited, and no
new log line was exercised.

- [x] Logs are correctly formatted — no new log line
- [x] Metrics are collected correctly — no new metric
- [x] Logging works in error scenarios — a busy read still logs
  `wishlist_read_busy` and raises `InventoryBusyError`; a failed
  `query_only` reset still logs `wishlist_read_query_only_reset_failed`;
  other failures keep the error the caller already received
- [x] Large data structures are not logged — no new log
- [x] Metrics are available for monitoring — no new metric

## Notes

The success path of these reads is every opening of one wishlist, its
detail, its members, one wish, its wishes, its gifted wishes, and its
favorite mark, plus the session lookup that uses the same
`read_transaction`. Logging each of those would record ordinary traffic.
The lock change is not a new failure mode. `SQLITE_BUSY` on the read
connection was already the cabinet-read outcome, with `wishlist_read_busy`
and `InventoryBusyError`. Requests that still take `BEGIN IMMEDIATE` keep
`wishlist_inventory_busy` on `get_wishlist_repository`.
