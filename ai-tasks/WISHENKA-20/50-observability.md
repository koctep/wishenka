# WISHENKA-20: Observability Implementation

## Logging Implementation

### Added Logs

No new log records were added. `20-architecture.md` does not name a server
event for the cabinet. The three routes in
`wishenka/web/routes/reservations_ui.py` are reads of the caller's
occupying promises. They do not open `BEGIN IMMEDIATE`, and there is no
`POST` on those paths. Promise writes stay on the five routes in
`wishenka/web/routes/reservations.py`. Those routes already log on
`wishenka.web.reservations`. A second record for the same write would
duplicate that log.

This step removed two INFO lines the card and the page were emitting.
Each message included the caller's telegram id, and each `extra` set
`user_id` to that same id:

- `reservations_card_rendered` on `GET /web/reservations/card`, with
  `distinct_items`
- `reservations_cabinet_rendered` on `GET /web/reservations`, with
  `groups`

Those reads are not mutations. The id is a gifter id. The architecture
does not ask for either event. `GET /web/reservations/list` had no log
and still has none.

The browser script in `wishenka/web/templates/base.html` discards the
write JSON. After a cabinet action it either replaces
`#reservations-cabinet` from the list GET or leaves the cabinet in place
and shows a fixed busy sentence. Those outcomes are already covered by
the write:

| Refresh the browser shows | Promise-write record that already exists |
| ------------------------- | ---------------------------------------- |
| List swap (HTTP 200) | `reservation_action_completed` INFO |
| `notice=refused` or `notice=shortage` | The matching refusal WARNING below |
| Busy sentence, cabinet left in place (HTTP 503) | `reservation_inventory_busy` WARNING |

`notice` is chosen in the browser from the status the write already
logged. HTTP 409 uses `notice=shortage` when `responseText` contains
`available`, and `notice=refused` otherwise. HTTP 401, 403, and 404 use
`notice=refused`. The list HTML is the caller's promises only. It does
not print a gifter name or the raw exception text. HTTP 503 does not
request the list. The script sets «Желание занято, бронь не изменилась.
Повторите попытку.» on the row that is already on screen.

A log on any of the three GETs would repeat the write, or would record a
read that changed nothing. None was added. The removed card and page
lines are not replaced.

The records this cabinet relies on, all from WISHENKA-18 `execute` in
`wishenka/web/routes/reservations.py`, are unchanged:

- **EMERG**: not used. `wishenka.logging.configure_logging` has no EMERG
  level, and this path does not stop the process.
- **ALERT**: not used. This logger has no ALERT level.
- **CRIT**: not used. Python `CRITICAL` exists and is not emitted here.
- **ERR**: not added. A domain refusal stays WARNING. A non-busy storage
  failure stays the store `ERROR` from WISHENKA-57 and is re-raised as
  `RuntimeError`. The cabinet routes do not add an error record.
- **WARNING**: not added. Existing events on `wishenka.web.reservations`:
  `reservation_action_refused` (fixed HTTP 403 create and HTTP 404),
  `reservation_inventory_busy` (HTTP 503), `reservation_permission_denied`
  (HTTP 403 `Forbidden`), `reservation_conflict` (HTTP 409, including the
  shortage the browser labels `notice=shortage`), and
  `reservation_validation_error` (HTTP 400). Context is `operation` and
  the path `item_id` or `reservation_id`. A 403 or 404 refusal also
  carries `http_status`. These records do not include a gifter id, a
  recipient id, a name, who holds a promise, a row dump, driver text, or
  SQL. A missing session on a write, and a missing session on a cabinet
  GET, is `auth_failure` on `wishenka.auth` (`missing_credentials` or
  `invalid_session_token`). The cabinet routes do not add a copy of that
  warning.
- **NOTICE**: not used. This logger has no NOTICE level. A completed
  promise action stays INFO. The cabinet does not emit a notice-level
  record for a rendered `notice` query.
- **INFO**: not added. `reservation_action_completed` remains the success
  record: `operation`, `item_id`, `reservation_id`, and promise `status`.
  It does not include a gifter id, a name, a token, a quantity, the
  request body, or the embedded wish view. The card and page no longer
  emit an INFO line of their own.
- **DEBUG**: not added. Session resolution still emits
  `auth_session_resolved` on `wishenka.auth` before `get_current_user`
  returns. That record is not a cabinet event, and this step does not
  copy it.

Inventory commit, busy, and rollback stay on `wishenka.wishlists.store`
(`wishlist_inventory_committed`, `wishlist_inventory_busy`,
`wishlist_inventory_rolled_back`). This step does not duplicate them.

`operation` on the reservation records remains the route function name
(`create_reservation`, `update_reservation_quantity`,
`cancel_reservation`, `purchase_reservation`, or
`undo_reservation_purchase`).

### Log Structure

Log format used:

- Structured logs: yes, on the existing reservation records
  (`extra={"event": ...}` on the standard library logger; JSON when
  `json_logs` is enabled). No cabinet record was added. The two cabinet
  INFO lines that carried `user_id` were removed.
- Includes context: yes, on the write records (`operation`, path
  `item_id` or `reservation_id`, promise `status` on success,
  `http_status` on a 403 or 404 refusal). The cabinet routes add no
  context fields.
- Log levels: INFO and WARNING on the existing reservation path. This
  step emits none.

## Metrics Implementation (if applicable)

This service has no metrics exporter. No counters, histograms, or
monitoring client were added for the cabinet. The reservation events
above remain the production signal for a promise write. The cabinet GET
is a read and has no metric of its own.

### Performance Metrics

Added performance metrics:

- **Response time**: none. Cabinet timing is not measured.
- **Throughput**: none.
- **Error rate**: none as a metric. Refusal and busy events can be counted
  from the existing reservation logs.

### Business Metrics

Business metrics:

- None added. A successful promise action is still
  `reservation_action_completed`. A refused cabinet notice is still the
  matching refusal warning. A busy sentence is still
  `reservation_inventory_busy`. All three are emitted by `execute` in
  `wishenka/web/routes/reservations.py`, not by the cabinet routes.

### System Health Metrics

System health metrics:

- **Resource usage**: not collected on this path
- **Component status**: SQLite lock contention on a promise write is still
  `reservation_inventory_busy`, with `wishlist_inventory_busy` on the
  store. The cabinet does not record a second health event.

## Monitoring Integration

Integration with monitoring systems:

- [ ] Prometheus metrics
- [ ] Grafana dashboards
- [ ] Alerting rules
- [ ] Log aggregation (ELK, Loki, etc.)

The process can emit the existing reservation records as text or JSON
through `wishenka.logging.configure_logging`. No scraper, dashboard, or
Prometheus client was added.

## Validation Results

Validation results:

- [x] Logs are correctly formatted
- [ ] Metrics are collected correctly (no metrics were added)
- [x] Logging works in error scenarios
- [x] Large data structures are not logged
- [ ] Metrics are available for monitoring (no metrics were added)

Checked by reading the cabinet routes, the cabinet branch in `base.html`,
and `execute`. The refresh outcomes map to records that already exist.
The card and page no longer log the caller's telegram id, a group count,
or a distinct-wish count. No new log was added, so this step adds no
caplog test.

The route module changed, so the cabinet UI tests and `make analyze`
were re-run. `tests/test_reservations_cabinet_ui.py`: 11 passed.
`make analyze`: no issues.

The existing write records still omit gifter ids, recipient ids, names,
who holds a promise, row dumps, driver text, SQL, session tokens, and
the wish graph. The cabinet templates have no slot for another
reservation, and this step does not log one.

## Notes

The cabinet is a read of the caller's promises. Logging the caller, or
naming another holder, is not required to see that a promise changed.
The write log already has `item_id`, `reservation_id`, `operation`, and
promise `status` without a gifter id. That is the server event.

HTTP 503 never reaches `GET /web/reservations/list`. The busy sentence is
client text. `reservation_inventory_busy` is the server record for that
outcome.
