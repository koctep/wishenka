# WISHENKA-328: Observability Implementation

The birthday list and the active-chat lookup open with `read_only` and
`begin()`. The existing `begin` listener emits `BEGIN`. Neither read adds
a log. `UserStore.write` only forwards to `_immediate`. A busy save is the
existing `UserStoreBusyError` path and its existing WARNING
`user_store_busy`. No second log was added. No metric was added. The
warning is already present, so production code was left unchanged.

## Logging Implementation

### Added Logs

None.

- **EMERG**: none. This service does not use that level.
- **ALERT**: none. This service does not use that level.
- **CRIT**: none. This service does not use that level.
- **ERR**: none added. A non-busy `SQLAlchemyError` stays the existing
  ERROR `user_store_error` inside `_immediate`.
- **WARNING**: none added. A busy save already logs `user_store_busy`.
- **NOTICE**: none. This service does not use that level.
- **INFO**: none added.
- **DEBUG**: none added.

### Records that already cover these paths

#### Read-only `BEGIN`

`configure_immediate_transactions` in `wishenka/sqlite.py` listens for
`begin`. When `execution_options` contains `read_only`, it runs `BEGIN`.
Otherwise it runs `BEGIN IMMEDIATE`. That listener does not log.

Two reads set `read_only` and call `begin()`, so they take that existing
`BEGIN`:

- `listing` in `wishenka/bot/birthdays.py` on `wishlist_store.engine`.
- `_find_active_chat_id` in `wishenka/web/routes/profile.py` on
  `wishlist_store.engine` when that store is on the app, and on
  `user_store.engine` otherwise.

Neither function logs the transaction, the SQL, or a failure. A read
failure stays the exception the driver already raises.

#### Busy save

`write` in `wishenka/users/store.py` returns
`await self._immediate(work, operation=operation)`. It does not log.

`_immediate` is the write helper. On `SQLAlchemyError` it rolls back when
the connection is in a transaction. When `is_sqlite_busy` accepts the
error, it logs one WARNING and raises `UserStoreBusyError`.

`user_store_busy` (`WARNING`), logger `wishenka.users`,
`UserStore._immediate` in `wishenka/users/store.py`.

Message: `User store operation rolled back because the database was busy`.

`extra`: `event` `user_store_busy` and `operation`. There is no
`error_type`, no `exc_info`, and no driver text.

The public message is `User service is temporarily busy; please retry`.

The two bot saves pass these `operation` values through `write`:

- `ensure_private_bot_user` in `wishenka/bot/principal.py`:
  `record_private_chat`.
- `reservation_confirmations` in `wishenka/bot/entry.py`:
  `reservation_confirmations`.

Those call sites do not log the busy outcome.

#### Any other `SQLAlchemyError` on the same helper

A non-busy `SQLAlchemyError` in `_immediate` stays ERROR
`User store operation failed due to database error` with `extra` `event`
`user_store_error` and the same `operation`, then
`RuntimeError("User storage operation failed")`. That is the ordinary
failure this helper already uses. `write` does not add a second copy.

### Log Structure

- Structured logs: yes (`extra` event fields; `JsonFormatter` places
  extras under `extra` when `log_json` is on)
- Includes context: `event` and `operation` on the busy warning and on
  the non-busy storage error
- Log levels: existing WARNING and ERROR. None added

## Metrics Implementation (if applicable)

No metric system exists in this repository (no Prometheus client, no
counters or histograms). None was added. A busy save stays the
`user_store_busy` log. It does not gain a counter.

### Performance Metrics

- **Response time**: none
- **Throughput**: none
- **Error rate**: none. A busy failure remains `user_store_busy`. Any
  other database failure on this helper remains `user_store_error`.

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
`user_store_busy` and `user_store_error`.

## Validation Results

Checked by reading `UserStore._immediate`, `UserStore.write`, the `begin`
listener in `wishenka/sqlite.py`, `listing`, and `_find_active_chat_id`.
The WARNING is already present, so production code was left unchanged.
`make analyze` was not run.

- [x] Logs are correctly formatted (existing `extra` dicts are `event`
  and `operation`)
- [ ] Metrics are collected correctly (no metrics system on this path)
- [x] Logging works in error scenarios (one WARNING `user_store_busy`
  then `UserStoreBusyError`; a non-busy error stays one ERROR
  `user_store_error` and `RuntimeError`; the reads add no log)
- [x] Large data structures are not logged (event name and operation
  string only)
- [ ] Metrics are available for monitoring (not applicable)

## Notes

The two reads emit `BEGIN` through the listener that already exists.
They do not add a log. `write` forwards to `_immediate` and does not log.
A busy error is the existing `UserStoreBusyError` path and the existing
`user_store_busy` warning. This step does not add a second log or a
metric.
