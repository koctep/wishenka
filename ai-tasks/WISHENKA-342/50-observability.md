# WISHENKA-342: Observability Implementation

Person lookups stay on `UserStore._read` in `wishenka/users/store.py`.
A finished lookup is the common case. This step does not log or count it.
The failure signals the architecture already named are already in that
method. No production logger or metric was added.

## Logging Implementation

### Added Logs

None. The accepted architecture names two warnings and forbids a success
log, a `user_store_error` line, and a `RuntimeError` wrap on this path.
Those warnings are already written by `_read`.

- **EMERG**: none. This service does not use that level.
- **ALERT**: none. This service does not use that level.
- **CRIT**: none. This service does not use that level.
- **ERR**: none added. A non-busy `SQLAlchemyError` is re-raised from
  `_read`. It does not log `user_store_error` and it is not wrapped in
  `RuntimeError`.
- **WARNING**: none added. Busy and reset-failure warnings are already
  on `_read` (see below).
- **NOTICE**: none. This service does not use that level.
- **INFO**: none added. A successful lookup adds no log.
- **DEBUG**: none added.

### Records that already cover a person lookup

Logger for every line below: `wishenka.users`.

#### Successful lookup

No log. `get_by_telegram_id` and `get_by_id` return `UserRecord` or
`None` through `_read` without an info, notice, or debug event.

#### Busy lookup

`user_store_busy` (`WARNING`), `UserStore._read`.

Message: `User store operation rolled back because the database was busy`.

`extra`: `event="user_store_busy"` and `operation` set to the public
method name (`get_by_telegram_id` or `get_by_id`). The line is written
when `is_sqlite_busy` accepts a `SQLAlchemyError` from begin, from
`PRAGMA query_only = ON`, or from the lookup work. The method then
raises `UserStoreBusyError("User service is temporarily busy; please retry")`
from that exception. There is no second wait and no second attempt.

This is the same warning `_immediate` and `initialize` already emit.
Callers that already catch `UserStoreBusyError` (`auth`, locale, and
birthdate routes) still write their own busy warnings. Those warnings
were already there. `_read` does not add a second user-store event.

#### `query_only` reset failure

`user_store_query_only_reset_failed` (`WARNING`), same logger and method,
in the `finally` after rollback.

Message: `Failed to reset query_only after user read; invalidating connection`.

`extra`: `event="user_store_query_only_reset_failed"` and `error_type`
set to `type(exc).__name__`. No person id and no SQL text. The raw
connection is invalidated. If the lookup already failed, the reset error
is not raised again. If the lookup succeeded and the reset fails, that
reset error is raised.

#### Other database errors

Any other `SQLAlchemyError` from begin, the pragma, or the lookup work
is re-raised from `_read` after rollback. A refused write is the driver's
`OperationalError` (`readonly`). It is not busy, so it stays that error.
No `user_store_error` and no `RuntimeError("User storage operation failed")`
on this path. Those two remain on `_immediate` and `initialize`.

### Log Structure

Log format used:

- Structured logs: yes (`extra={"event": ...}` on `wishenka.users`)
- Includes context: yes (`operation` on a busy lookup; `error_type` on a
  reset failure). No person id, row, or SQL text.
- Log levels: `WARNING` on the two existing failure events. No new level.

## Metrics Implementation (if applicable)

No metric system exists in this repository (no Prometheus client, no
OpenTelemetry series). A successful lookup is not counted. This step
does not add one.

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

Checked against `UserStore._read` and
`tests/test_wishenka_342_user_read_hardening_repro.py`.
`make test-serial` on that file: 8 passed. No production code was edited.

- [x] Logs are correctly formatted — busy uses `event` and `operation`;
  reset failure uses `event` and `error_type`; both are `WARNING` on
  `wishenka.users`
- [x] Metrics are collected correctly — no new metric
- [x] Logging works in error scenarios — a busy lookup logs
  `user_store_busy` and raises `UserStoreBusyError`; a failed
  `query_only` reset logs `user_store_query_only_reset_failed` and
  invalidates; a non-busy `SQLAlchemyError` is re-raised with no
  `user_store_error`
- [x] Large data structures are not logged — no person id, row, or SQL
- [x] Metrics are available for monitoring — no new metric

## Notes

The success path of both person lookups stays quiet, as the requirements
and the architecture require. The busy warning is the one saves already
write. The reset-failure warning is the only event this task added, and
it was added with `_read` in development. This step leaves both in place
and does not add a success log.
