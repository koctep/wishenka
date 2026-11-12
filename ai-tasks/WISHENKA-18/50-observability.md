# WISHENKA-18: Observability Implementation

## Logging Implementation

### Added Logs

HTTP promise actions log on `wishenka.web.reservations` from `execute` in
`wishenka/web/routes/reservations.py`. Commit, busy, and rollback records
for the wish transaction stay on `wishenka.wishlists.store`
(`wishlist_inventory_committed`, `wishlist_inventory_busy`,
`wishlist_inventory_rolled_back`) from WISHENKA-57.
`wishenka.logging.configure_logging` accepts `DEBUG`, `INFO`, `WARNING`,
`ERROR`, and `CRITICAL`. It has no `EMERG`, `ALERT`, or `NOTICE` level, so
those syslog names are not emitted. `CRITICAL` is unused: a refused or busy
promise action does not stop the process.

- **EMERG**: not used. This logger has no EMERG level, and this path does
  not stop the process.
- **ALERT**: not used. This logger has no ALERT level.
- **CRIT**: not used. Python `CRITICAL` exists and is not emitted here.
- **ERR**: not used on these routes. A domain refusal stays WARNING. A
  non-busy storage failure is still the store's `ERROR` record from
  WISHENKA-57 and is re-raised as `RuntimeError`. These routes do not add
  another error record.
- **WARNING**: `wishenka.web.reservations` —
  `reservation_action_refused` for the fixed recipient answers. Create
  (`SelfReservationError`) is HTTP 403. A mutation the recipient must not
  see, a missing id, a missing wish, and a deleted list are HTTP 404 with
  body `Resource not found`. Both outcomes use this one event. Context is
  `http_status`, `operation`, and the path `item_id` or `reservation_id`
  when that id is in the URL. The message is
  `Reservation action refused: <operation>`. It does not include the
  exception class or text, a gifter id, a name, or a flag that a promise
  row was found. A 403 create omits `reservation_id`. A 404 for a real
  promise and a 404 for a missing id carry the same fields; `reservation_id`
  is the id from the path in both cases.
- **WARNING**: `wishenka.web.reservations` —
  `reservation_inventory_busy` when `InventoryBusyError` becomes HTTP 503.
  Context is `operation` and the path `item_id` or `reservation_id`. No
  gifter id, name, or token. The response detail stays the busy sentence.
- **WARNING**: `wishenka.web.reservations` —
  `reservation_permission_denied` (HTTP 403 `Forbidden`),
  `reservation_conflict` (HTTP 409), and `reservation_validation_error`
  (HTTP 400). Context is `operation` and the path ids. The log does not
  copy `str(exc)`, the request body, or the wish graph, and it names no
  gifter.
- **NOTICE**: not used. This logger has no NOTICE level. A completed
  promise action is INFO.
- **INFO**: `wishenka.web.reservations` —
  `reservation_action_completed` after a promise action returns
  `PromiseActionDTO`. Context is `operation`, `item_id`, `reservation_id`,
  and `status`. `status` is that promise's status (`active`, `purchased`,
  or `cancelled`), not the HTTP code. The record does not include a gifter
  id, name, token, quantity, request body, or the embedded wish view.
- **DEBUG**: not added.

`operation` is the route function name (`create_reservation`,
`update_reservation_quantity`, `cancel_reservation`,
`purchase_reservation`, or `undo_reservation_purchase`).

### Log Structure

Log format used:

- Structured logs: yes (`extra={"event": ...}` on the standard library
  logger; JSON when `json_logs` is enabled)
- Includes context: yes (`operation`, path `item_id` or `reservation_id`,
  promise `status` on success, `http_status` on a 403 or 404 refusal)
- Log levels: INFO, WARNING

These events omit gifter and actor ids, names, session tokens, request
bodies, wishlist titles, item text, and the wish graph on
`PromiseActionDTO.item`. The records stay on the server. The HTTP body is
unchanged: success is the promise just changed, recipient create is
`Cannot promise this wish`, and a recipient mutation is
`Resource not found`.

## Metrics Implementation (if applicable)

This service has no metrics exporter. No counters, histograms, or
monitoring client were added. The events above are the production signal
for these routes.

### Performance Metrics

Added performance metrics:

- **Response time**: none. Handler timing is not measured here.
- **Throughput**: none.
- **Error rate**: none as a metric. Refusal and busy events can be counted
  from logs.

### Business Metrics

Business metrics:

- `reservation_action_completed`: one successful promise action, with
  `operation` and promise `status` — `execute` in
  `wishenka/web/routes/reservations.py`
- `reservation_action_refused`: one fixed 403 create or 404 answer —
  `execute` in `wishenka/web/routes/reservations.py`
- `reservation_inventory_busy`: one HTTP 503 because the wish was busy —
  `execute` in `wishenka/web/routes/reservations.py`

### System Health Metrics

System health metrics:

- **Resource usage**: not collected on this path
- **Component status**: SQLite lock contention on these routes is the
  `reservation_inventory_busy` warning. The store still records
  `wishlist_inventory_busy` for the same failure.

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

`tests/test_reservation_actions_api.py`: 19 passed in 6.85s. The new cases
check a completed create and purchase, a recipient create before and after
a promise exists, a recipient cancel beside a missing id, and
`InventoryBusyError`. Those route records contain the fields above and
omit gifter ids, names, session tokens, and the wish title. The module
keeps `pytestmark = pytest.mark.timeout(30)`. `make analyze` passed: Ruff,
format check, and Mypy reported no issues on 79 source files. The run also
emits `StarletteDeprecationWarning` from the installed FastAPI package.

## Notes

`reservation_action_completed` is written only after the action returns the
promise DTO. A refusal or a busy wish does not emit it.

A recipient create is HTTP 403 whether or not the wish already has a
promise. Those two WARNING records match, and neither carries
`reservation_id`. A recipient mutation is HTTP 404, the same body and the
same log fields as a missing promise. The path id is not evidence that a
row was found.

Older domain logs on `wishenka.wishlists` still name the gifter for
reservation changes. That text is from earlier tasks and is not copied into
these HTTP records or into `detail`.
