# WISHENKA-19: Observability Implementation

## Logging Implementation

### Added Logs

No new log records were added. `20-architecture.md` states that new card
logs are not required and that the existing `wishenka.web.reservations`
records stay the mutation log. The card does not open a transaction and
does not decide the promise outcome.

The browser script in `wishenka/web/templates/base.html` discards the JSON
body. After a promise write it either reads the existing card partial or
shows a fixed busy sentence on the current card. Those three refresh
outcomes are already covered by the write:

| Refresh the browser shows | Promise-write record that already exists |
| ------------------------- | ---------------------------------------- |
| Success swap (HTTP 200 or 201) | `reservation_action_completed` INFO |
| Refused notice (`notice=refused` or `notice=shortage`) | The matching refusal WARNING below |
| Busy sentence, card left in place (HTTP 503) | `reservation_inventory_busy` WARNING |

`GET /wishlists/{wishlist_id}/items/{item_id}/card` in
`wishenka/web/routes/sharing.py` (`get_item_card_partial`) only renders
`partials/item_card.html`. On HTTP 200 or 201 the script requests that
partial with `is_first` and `is_last` and no `notice`. On HTTP 409, 401,
403, or 404 it adds `notice=shortage` or `notice=refused`. The query value
is chosen in the browser from the status already logged on the write.
`notice` is rendered only when the projection is `WishItemGifterViewDTO`.
A recipient projection drops it, so a log of the query would not match the
HTML. HTTP 503 does not request the partial. The script sets the sentence
«Желание занято, бронь не изменилась. Повторите попытку.» on the card that
is already on screen.

A log on that GET, or a second record for the busy sentence, would repeat
the write and would not be a new server event. None was added.

The records this card relies on, all from WISHENKA-18
`execute` in `wishenka/web/routes/reservations.py`, are unchanged:

- **EMERG**: not used. `wishenka.logging.configure_logging` has no EMERG
  level, and this path does not stop the process.
- **ALERT**: not used. This logger has no ALERT level.
- **CRIT**: not used. Python `CRITICAL` exists and is not emitted here.
- **ERR**: not added. A domain refusal stays WARNING. A non-busy storage
  failure stays the store `ERROR` from WISHENKA-57 and is re-raised as
  `RuntimeError`. The card partial does not add an error record.
- **WARNING**: not added. Existing events on `wishenka.web.reservations`:
  `reservation_action_refused` (fixed HTTP 403 create and HTTP 404),
  `reservation_inventory_busy` (HTTP 503), `reservation_permission_denied`
  (HTTP 403 `Forbidden`), `reservation_conflict` (HTTP 409, including the
  shortage the browser labels `notice=shortage`), and
  `reservation_validation_error` (HTTP 400). Context is `operation` and
  the path `item_id` or `reservation_id`. A 403 or 404 refusal also
  carries `http_status`. These records do not include a gifter id, a
  recipient id, a name, who holds a promise, a row dump, driver text, or
  SQL. A missing session on the write is `auth_failure` on
  `wishenka.auth` (`missing_credentials` or `invalid_session_token`). The
  card does not add a copy of that warning.
- **NOTICE**: not used. This logger has no NOTICE level. A completed
  promise action stays INFO. The card does not emit a notice-level record
  for a rendered `notice` query.
- **INFO**: not added. `reservation_action_completed` remains the success
  record: `operation`, `item_id`, `reservation_id`, and promise `status`.
  It does not include a gifter id, a name, a token, a quantity, the
  request body, or the embedded wish view.
- **DEBUG**: not added.

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
  `json_logs` is enabled). No card record was added.
- Includes context: yes, on those records (`operation`, path `item_id` or
  `reservation_id`, promise `status` on success, `http_status` on a 403
  or 404 refusal). The card partial adds no context fields.
- Log levels: INFO and WARNING on the existing reservation path. This
  step emits none.

## Metrics Implementation (if applicable)

This service has no metrics exporter. No counters, histograms, or
monitoring client were added for the card. The reservation events above
remain the production signal for a promise write. The card refresh is a
read or a browser sentence and has no metric of its own.

### Performance Metrics

Added performance metrics:

- **Response time**: none. Card-partial timing is not measured.
- **Throughput**: none.
- **Error rate**: none as a metric. Refusal and busy events can be counted
  from the existing reservation logs.

### Business Metrics

Business metrics:

- None added. A successful promise is still
  `reservation_action_completed`. A refused card notice is still the
  matching refusal warning. A busy sentence is still
  `reservation_inventory_busy`. All three are emitted by `execute` in
  `wishenka/web/routes/reservations.py`, not by the card partial.

### System Health Metrics

System health metrics:

- **Resource usage**: not collected on this path
- **Component status**: SQLite lock contention on a promise write is still
  `reservation_inventory_busy`, with `wishlist_inventory_busy` on the
  store. The card does not record a second health event.

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

Checked by reading the card refresh in `base.html`,
`get_item_card_partial`, and `execute`. The three refresh outcomes map to
records that already exist. No production module was changed, so this step
adds no caplog test and does not re-run pytest or `make analyze`.

The existing records still omit gifter ids, recipient ids, names, who
holds a promise, row dumps, driver text, SQL, session tokens, and the
wish graph. The card template does not render those fields, and this step
does not log them.

## Notes

The surprise rule is why the card partial is not a log site. A recipient
refresh must contain no booking sentence. Logging `notice`, the rendered
HTML, or the viewer would either name a person or describe a promise the
recipient must not see. The write log already has `item_id` and
`operation` without a gifter id. That is the server event.

HTTP 503 never reaches `get_item_card_partial`. The busy sentence is
client text. `reservation_inventory_busy` is the server record for that
outcome.
