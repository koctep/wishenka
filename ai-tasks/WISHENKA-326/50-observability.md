# WISHENKA-326: Observability Implementation

A busy `SQLAlchemyError` on the shared wishlist repository is already one
WARNING and one `InventoryBusyError`. The app handler turns that exception
into HTTP 503 and does not log. `wishlists.execute` re-raises the busy
error so the dependency writes that warning once. Any other
`SQLAlchemyError` stays the existing ERROR `wishlist_store_error` and
`RuntimeError`. No log was added. No metric was added.

## Logging Implementation

### Added Logs

None. The WARNING for a busy shared-repository failure is already present.

- **EMERG**: none. This service does not use that level.
- **ALERT**: none. This service does not use that level.
- **CRIT**: none. This service does not use that level.
- **ERR**: none added. A non-busy `SQLAlchemyError` stays the existing
  ERROR below.
- **WARNING**: none added. A busy `SQLAlchemyError` in
  `get_wishlist_repository` already logs `wishlist_inventory_busy`.
- **NOTICE**: none. This service does not use that level.
- **INFO**: none added.
- **DEBUG**: none added.

### Records that already cover this failure

#### Busy shared repository

`wishlist_inventory_busy` (`WARNING`), logger
`wishenka.web.dependencies`, `get_wishlist_repository` in
`wishenka/web/dependencies.py`.

Message: `Wishlist inventory change rolled back because the database was busy`.

`extra`: `event` only. There is no `error_type`, no `exc_info`, and no
driver text. The message does not include the SQL exception string.

The line is written once, after rollback and after commit logs are
cleared, when `is_sqlite_busy` accepts the `SQLAlchemyError`. The
dependency then raises `InventoryBusyError` from that exception. The
public message is the exception default: `The wish was busy and the
attempt changed nothing`.

`install_inventory_busy_handler` in `wishenka/web/app.py` catches an
`InventoryBusyError` that leaves the route. It returns HTTP 503 with
`{"detail": str(exc)}`. That handler does not log.

#### Busy error through `wishlists.execute`

`execute` in `wishenka/web/routes/wishlists.py` (logger
`wishenka.web.wishlists`) catches `SQLAlchemyError` while the dependency
is still yielded. When `is_sqlite_busy` accepts it, `execute` re-raises
that `SQLAlchemyError`. It does not log `wishlist_inventory_busy` and it
does not log `wishlist_store_error` for that case.

The re-raised error returns to `get_wishlist_repository`. That function
writes the single WARNING above and raises `InventoryBusyError`. The app
handler then returns HTTP 503 without a second log.

#### Any other `SQLAlchemyError`

A non-busy `SQLAlchemyError` stays ERROR `wishlist_store_error` and
`RuntimeError("Wishlist storage operation failed")`. Which logger writes
the ERROR depends on who catches the database error.

`wishlists.execute` catches it first on the wishlist API path. It logs
ERROR `Wishlist storage operation failed due to database error` with
`extra` `event` `wishlist_store_error` and no `error_type`, then raises
`RuntimeError`. That `RuntimeError` is not a `SQLAlchemyError`, so
`get_wishlist_repository` handles it in `except BaseException`: rollback,
clear commit logs, re-raise. The dependency does not write
`wishlist_store_error` again.

A non-busy `SQLAlchemyError` that reaches `get_wishlist_repository`
without that route conversion is logged there instead. The dependency
logs the same ERROR sentence with `extra` `event` `wishlist_store_error`
and `error_type` set to the exception class name, then raises the same
`RuntimeError`. It does not log `wishlist_inventory_busy`.

### Log Structure

- Structured logs: yes (`extra` event fields; `JsonFormatter` places
  extras under `extra` when `log_json` is on)
- Includes context: `event` on the busy warning; `event` on the route
  storage error; `event` and `error_type` on the dependency storage error
- Log levels: existing WARNING and ERROR. None added

## Metrics Implementation (if applicable)

No metric system exists in this repository (no Prometheus client, no
counters or histograms). None was added.

### Performance Metrics

- **Response time**: none
- **Throughput**: none
- **Error rate**: none. A busy failure remains `wishlist_inventory_busy`.
  Any other database failure remains `wishlist_store_error`.

### Business Metrics

None.

### System Health Metrics

None added.

- **Resource usage**: none
- **Component status**: none

## Monitoring Integration

- [ ] Prometheus metrics
- [ ] Grafana dashboards
- [ ] Alerting rules
- [ ] Log aggregation (ELK, Loki, etc.)

No exporter or dashboard was added. Existing JSON logs already include
`wishlist_inventory_busy` and `wishlist_store_error`.

## Validation Results

Checked by reading `get_wishlist_repository`, `wishlists.execute`, and
`install_inventory_busy_handler`. The WARNING is already present, so
production code was left unchanged. `make analyze` was not run.

- [x] Logs are correctly formatted (existing `extra` dicts are `event`,
  and `error_type` only on the dependency's non-busy ERROR)
- [ ] Metrics are collected correctly (no metrics system on this path)
- [x] Logging works in error scenarios (one WARNING
  `wishlist_inventory_busy` then `InventoryBusyError` and HTTP 503 with
  no second log; a non-busy error stays one ERROR
  `wishlist_store_error` and `RuntimeError`)
- [x] Large data structures are not logged (event name, and the exception
  class name on the dependency's non-busy ERROR)
- [ ] Metrics are available for monitoring (not applicable)

## Notes

The busy outcome is one warning in `get_wishlist_repository`. The route
does not add a busy log, and the HTTP 503 handler does not add one. On
the `execute` path a non-busy `SQLAlchemyError` is logged by the route
before the dependency sees the replacement `RuntimeError`. The dependency
does not log that case again.
