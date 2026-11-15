# WISHENKA-59: Observability Implementation

## Logging

Both indexed cabinet reads are reached through existing HTTP routes. `RequestLoggingMiddleware` in `wishenka/web/app.py` records method, route, response
status and duration at INFO; unhandled failures are logged at ERROR with route and duration.
The request log does not include the giver ID, reservation contents, or query parameters.

SQLite errors in the new store methods emit `reservation_cabinet_busy` at WARNING or
`reservation_cabinet_error` at ERROR. Both events carry an `operation` field identifying the
list or summary read, and omit SQL parameters, user IDs, reservation data, and driver text.
Busy errors still raise `InventoryBusyError`, and other database errors retain the existing
storage failure mapping. The read-specific messages do not describe an inventory mutation.

The in-memory index is derived state updated within the service; its normal lookups and updates
are frequent and need no per-entry logging. The existing reservation lifecycle logs remain in
place. This change does not add user IDs, reservation IDs, or result payloads to logs.

## Metrics and Monitoring

No dedicated metrics or exporter were introduced. Existing HTTP request duration and status logs
can be aggregated by the two cabinet routes to observe latency and failures. They do not measure
index size, distinguish database time from application time, or directly prove index use. The
SQLite query-plan test and targeted tests provide verification of the indexed paths, rather than
production metrics. Monitoring-system configuration and alert rules are unchanged.

## Validation

- Reviewed the middleware and database error handler for context and data exposure.
- The Step 5 `make check` passed static analysis and 835 tests, including the indexed-read,
  lifecycle, transaction, and query-plan tests.
- Four parameterized error-path tests cover busy and generic failures for each cabinet read,
  event context and absence of user IDs and driver details. All 8 tests in the lifecycle module
  passed; Ruff and mypy passed on the affected Python files.
- Existing request logs and storage errors retain their established formatting and levels.
