# WISHENKA-38: Observability Implementation

## Logging Implementation

### Added Logs

No log was added. This task adds tests of behavior the product already
has. It does not add a notification sender, and it does not add a
production log that names the gifter, the reservation, the booked
quantity, the free remainder, or whether the gift was bought on a
recipient-facing path.

- **EMERG**: none added.
- **ALERT**: none added.
- **CRIT**: none added.
- **ERR**: none added.
- **WARNING**: none added.
- **NOTICE**: none added.
- **INFO**: none added.
- **DEBUG**: none added.

The new tests already judge existing records. No product logger was
rewritten. The records on the judged recipient request do not name the
gifter.

#### Recipient request window

`test_recipient_walk_hides_booking_in_response_log_and_notice` in
`tests/test_surprise_role_context.py` clears the capture, then wraps
only the owner `GET /api/wishlists/{wishlist_id}/items/{item_id}` at
INFO. That caller is the recipient. For each record in that window the
message and extras must omit the gifter name, username, and Telegram
id. The same window must not contain a notification, outbox, or push
event, and the database must not gain `notification_outbox` or
`user_notification_settings`.

On that successful read the INFO records are:

- `wishenka.web` `RequestLoggingMiddleware` in `wishenka/web/app.py`:
  `HTTP request completed` with `method`, `path`, `status_code`, and
  `duration_ms`. The path is the item URL. It does not carry the
  gifter.
- `wishenka.wishlists.store` `WishlistStore._read` in
  `wishenka/wishlists/store.py`: event `wishlist_store_read`. The
  store logger is `logging.getLogger(__name__)`, so the record name is
  `wishenka.wishlists.store`. The message and extras are row counts
  (`wishlists_count`, `items_count`, `reservations_count`,
  `members_count`, `favorites_count`, `history_count`).
  `reservations_count` is how many reservation rows were loaded. It
  is not the gifter, the booked quantity, or the free remainder.
- `wishenka.wishlists.store` `WishlistStore._write` in the same
  module: event `wishlist_store_write`. The extras are row counts and
  deleted-row counts. They do not name the gifter.

`get_wish_item` in `wishenka/wishlists/service.py` writes no log on
success. `execute` in `wishenka/web/routes/items.py` writes a WARNING
only when the item operation fails. A search of `wishenka/**/*.py`
finds no `notification`, `outbox`, or `push` symbol, so the walk has
no notice event to emit.

DEBUG records on that same request stay outside the INFO window the
test judges. They also do not name the gifter. `HTTP request started`
records method and path. `auth_session_resolved` in
`wishenka/auth/dependencies.py` records the session holder, who is the
owner, not the gifter.

#### Share visit

`test_share_link_visit_creates_no_account` captures
`GET /share/{public_token}` with no credential. The captured records
must not include event `user_created`. That event is emitted only by
`UserStore.upsert_user` in `wishenka/users/store.py`. The share route
uses `get_optional_current_user`, which returns no user when no
credential is sent and does not call `upsert_user`.

The visit does log `wishlist_shared_view` on `wishenka.web.sharing`
(`wishlist_id`, `is_recipient`, `is_collaborative`) and the completed
request on `wishenka.web`. `RequestLoggingMiddleware` rewrites the
path to `/share/{token}` before that INFO line.
`ShareTokenAccessFilter` does the same for the Uvicorn access record.
The store read and write counts described above can also appear,
because `get_wishlist_by_public_token` runs inside the store unit of
work. None of those records is `user_created`.

#### Gifter booking audit, left as it is

`create_reservation` logs event `item_reserved` with `gifter_id`.
`mark_reservation_purchased` logs event `reservation_purchased` with
`user_id`. Both use the service logger
`logging.getLogger("wishenka.wishlists")` in
`wishenka/wishlists/service.py`, so those records are named
`wishenka.wishlists`. Both are the gifter's own booking. The walk
seeds them before `caplog.clear()`, so they stay outside the
recipient window. This step does not change that stream.

### Log Structure

Log format used:

- Structured logs: unchanged. `wishenka/logging.py` already provides
  `JsonFormatter` and `configure_logging`. This step did not change
  them.
- Includes context: unchanged. The recipient-request window omits the
  gifter. The gifter's own booking audit may still include `gifter_id`
  or `user_id`.
- Log levels: none added. The judged window is INFO and above.

## Metrics Implementation (if applicable)

No metric was added. The service gained no counter, histogram, or
exporter from this task.

### Performance Metrics

Added performance metrics:

- **Response time**: none added.
- **Throughput**: none added.
- **Error rate**: none added.

The existing request log already records `duration_ms` for the
completed call. This step did not add a metric for it.

### Business Metrics

Business metrics:

- None added. This task does not count bookings, recipients, or share
  visits, and it does not record whether a gift was bought.

### System Health Metrics

System health metrics:

- **Resource usage**: none added.
- **Component status**: none added.

## Monitoring Integration

Integration with monitoring systems:

- [ ] Prometheus metrics
- [ ] Grafana dashboards
- [ ] Alerting rules
- [ ] Log aggregation (ELK, Loki, etc.)

No monitoring client was added. Existing records stay on
`wishenka.web`, `wishenka.web.sharing`, `wishenka.wishlists.store`,
`wishenka.wishlists`, and `wishenka.users`. Store read and write
counts (`wishlist_store_read`, `wishlist_store_write`) use
`wishenka.wishlists.store`. `wishenka.wishlists` is the service
logger for `item_reserved` and `reservation_purchased`.

## Validation Results

Validation results:

- [ ] Logs are correctly formatted
- [ ] Metrics are collected correctly
- [ ] Logging works in error scenarios
- [ ] Large data structures are not logged
- [ ] Metrics are available for monitoring

No new log line or metric was emitted, so these checks were not run
against new instrumentation. The existing records the new tests judge
are covered by `tests/test_surprise_role_context.py`: the recipient
request window must not name the gifter, that window must not emit a
notification, outbox, or push event, and the share visit must not log
`user_created`. Step 5 already ran that module; both tests passed.
The store read and write lines in the recipient window carry counts,
not reservation rows and not the gifter.

## Notes

Product code was not changed. The INFO records on the judged recipient
read do not name the gifter, so there was nothing to stop and report.
The operator audit of the gifter's own booking still may name that
gifter. A later sender, if one is added, stays out of this task.
