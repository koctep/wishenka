# WISHENKA-22: Observability Implementation

This story ships documents only (requirements, architecture, text updates in
`in-docs/spec.md`). It adds no runtime code, so it adds no logs and no
metrics. Nothing under `wishenka/`, `tests/` or `doc/dev` was changed in this
step. The real value of this file is the section «Observability requirements
for WISHENKA-23 / WISHENKA-24», which fixes what the follow-up stories must
log and measure, derived from `10-requirements.md` and `20-architecture.md`
(sections 3, 4, 6 and Q1, Q5).

## Logging Implementation

### Added Logs

- **EMERG**: N/A — no runtime code in this story (nothing added)
- **ALERT**: N/A — no runtime code in this story (nothing added)
- **CRIT**: N/A — no runtime code in this story (nothing added)
- **ERR**: N/A — no runtime code in this story (nothing added)
- **WARNING**: N/A — no runtime code in this story (nothing added)
- **NOTICE**: N/A — no runtime code in this story (nothing added)
- **INFO**: N/A — no runtime code in this story (nothing added)
- **DEBUG**: N/A — no runtime code in this story (nothing added)

### Log Structure

- Structured logs: N/A for this story. The project already uses structured
  logs: `logging.getLogger("wishenka.wishlists")` with
  `extra={"event": "<event_name>", ...}`, rendered by `JsonFormatter` in
  `wishenka/logging.py` (extras go under the `extra` key) or by a text
  formatter.
- Includes context: N/A (no code)
- Log levels: none used. Follow-ups use the existing convention: INFO for
  successful domain events, WARNING for business refusals, ERROR for failed
  operations (the Python names of the syslog levels the project maps to).

## Metrics Implementation (if applicable)

### Performance Metrics

- **Response time**: N/A — no runtime code in this story
- **Throughput**: N/A — no runtime code in this story
- **Error rate**: N/A — no runtime code in this story

### Business Metrics

- N/A — no runtime code in this story. Candidate metrics for the follow-ups
  are listed below.

### System Health Metrics

- **Resource usage**: N/A — no runtime code in this story
- **Component status**: N/A — no runtime code in this story

## Monitoring Integration

Verified in the repo: there is no metrics library or endpoint. `pyproject.toml`
and `wishenka/` contain no Prometheus, StatsD or OpenTelemetry code. The
existing "metrics" in `doc/dev/reservations.md` (section «Business &
Operational Metrics») are names of counters that a log aggregator would derive
from structured log events (for example `wishlist_items_fulfilled_total` from
`event="item_fulfilled"`). They are not exported by the app.

- [ ] Prometheus metrics — N/A: not present in the project; not introduced here
- [ ] Grafana dashboards — N/A: not present in the project
- [ ] Alerting rules — N/A: no runtime code in this story
- [ ] Log aggregation (ELK, Loki, etc.) — N/A: the app writes JSON or text
  lines to stdout; collection is infrastructure and is not part of this story

## Validation Results

- [ ] Logs are correctly formatted — N/A: no logs added
- [ ] Metrics are collected correctly — N/A: no metrics added
- [ ] Logging works in error scenarios — N/A: no logs added
- [ ] Large data structures are not logged — N/A: no logs added (the rule is
  restated for the follow-ups below)
- [ ] Metrics are available for monitoring — N/A: no metrics added; the project
  has no metrics export

## Observability requirements for WISHENKA-23 / WISHENKA-24

Scope: WISHENKA-23 owns all logging and metrics for the receipt, archive
split, outbox and worker (`20-architecture.md`, section 4, point 5, and
section 6, row «Logs»). WISHENKA-24 is a frontend story: it adds no domain
events. It only needs the route-level records of the receipt route (below) and
must not add client-side logging of wish or booking data.

### Conventions to follow

- Logger `wishenka.wishlists` for domain events, as in `reservations.md`
  («Structured Logging Matrix»). The receipt route logs on its own
  `wishenka.web.*` logger, as `wishenka.web.reservations` does for promise
  routes. The worker uses one dedicated logger name (for example
  `wishenka.wishlists.notices`).
- Every record sets `extra={"event": "<snake_case_name>", ...}`. One event
  name per fact. The message is fixed text with no interpolated ids, so the
  `message` stays safe for the surprise tests.
- Business-level fields only. No large structures: no wish description, no
  URLs, no DTOs, no outbox payload dump, no lists of ids, no SQL parameters.
- Use the project's real level mapping: INFO for accepted facts, WARNING for
  business refusals, ERROR for failures that need a person (unexpected
  exception, failure of the worker loop). A terminal send failure of one notice
  is DEBUG per row and counted in the INFO window summary. Syslog NOTICE has no separate Python
  level here, so significant events are INFO.
- Do not log in a loop for idle work. An idle worker poll writes nothing at
  INFO or above (see the walk-test rule below).
- Per-row worker facts (one outbox row, one giver) are DEBUG only. At INFO or
  above the worker writes only system-wide aggregates (see «Worker records and
  timing» below).

### Events to log

| Event | Level | Where | Fields allowed |
| ----- | ----- | ----- | -------------- |
| `receipt_recorded` | INFO | receipt service, after commit | `wishlist_id`, `item_id`, `receipt_id`, `actor_id`, `quantity`, `received_quantity`, `total_quantity`, `fully_received` |
| `receipt_refused` | WARNING | receipt service or route | `wishlist_id`, `item_id`, `actor_id`, `reason`, `http_status`, `remaining_quantity` (only for `quantity_above_remaining` and `nothing_remaining`) |
| `wish_archived_partial` | INFO | archive of a partly received wish | `wishlist_id`, `item_id`, `actor_id`, `received_quantity`, `total_quantity` |
| `wish_restored_partial` | INFO | restore | `wishlist_id`, `item_id`, `actor_id`, `received_quantity`, `total_quantity` |
| `wish_archive_refused` | WARNING | archive or restore refused (`nothing_remaining`) | `wishlist_id`, `item_id`, `actor_id`, `reason` |
| `legacy_receipts_backfilled` | INFO | migration | `rows` (count only) |
| `legacy_archived_rows_normalised` | INFO | migration | `rows` (count only) |
| `receipt_notice_created` | DEBUG | producer, after commit only | `outbox_id` |
| `receipt_notice_skipped` | DEBUG | producer, after commit only, settings gate said off | `outbox_id`, `gate` (`list` or `user`) |
| `receipt_notice_duplicate_suppressed` | DEBUG | producer, after commit only, de-dup key already exists | `outbox_id` |
| `receipt_notice_sent` | DEBUG | worker, after mark-sent, per row | `outbox_id`, `attempt` |
| `receipt_notice_send_failed` | DEBUG | worker, retryable error, per row | `outbox_id`, `attempt`, `error_class` |
| `receipt_notice_retry_scheduled` | DEBUG | worker, per row | `outbox_id`, `attempt`, `max_attempts` |
| `receipt_notice_failed_terminal` | DEBUG | worker, attempts exhausted for one row; the aggregate at INFO counts it in `failed_terminal` | `outbox_id`, `attempt`, `error_class` |
| `receipt_notice_batch_processed` | DEBUG | worker, end of one poll batch with at least one row | `rows` (count only) |
| `receipt_notice_window_summary` | INFO | worker, once per fixed time window, only if the window processed at least one row | `window_seconds`, `sent`, `retried`, `failed_terminal` (counts across all rows of all receipts in the window) |
| `receipt_notice_worker_started` / `_stopped` | INFO | app lifespan | none |
| `receipt_notice_worker_error` | ERROR | worker loop itself failed (for example the queue cannot be read), not a send error of one row | `error_class` only |
| `receipt_notice_enqueue_failed` | ERROR | producer, after the rollback of the receipt | `error_class` only |

Notes on the table:

- **Notice-path correlation rule.** Every `receipt_notice_*` event
  correlates by `outbox_id` only. It carries no `receipt_id`, `item_id`,
  `wishlist_id`, `event_type` or giver id of any kind. `receipt_recorded` and
  `receipt_refused` carry no `outbox_id`. No log field may join an
  `outbox_id` to a receipt, a wish or a list; the join exists only in the
  database and is made by an operator. Reason: the number or the mere presence
  of notice records for one `receipt_id` would show that the wish was booked
  and by how many givers (FR-6, `specs/00-high.md` invariants 1 and 4). The
  alternative of a separate logger was not chosen: it is feasible but it
  leaves the leak to the log routing, while the field rule holds on any
  stream. A field rule alone does not remove the join by time; that is
  handled in the next two notes.
- **Visibility model.** Application logs are an operator-only stream. The
  owner (recipient) never sees them, and the owner-facing channels (response,
  UI, Telegram) carry no log data. The walk test captures `caplog` as the
  proxy for any stream an owner could ever see, so the rules below are written
  so that this proxy stays clean. The real guarantee against a presence leak
  is the combination of three things: `outbox_id`-only fields, no join in any
  log field, and operator-only access to logs. The DEBUG level is defense in
  depth and not a guarantee (see «Presence and timing»).
- **Presence and timing.** Producer events (`_created`, `_skipped`,
  `_duplicate_suppressed`) run in the receipt request, and a record next to
  `receipt_recorded` would show by its presence that at least one giver
  exists, even with `outbox_id` only. They are therefore DEBUG and are
  written only after the commit. The production level comes from
  `Settings.log_level` (`wishenka/config.py`, default `INFO`, applied by
  `configure_logging` in `wishenka/logging.py`), and `LOG_LEVEL=DEBUG` is a
  normal operator setting. At DEBUG these records appear right after
  `receipt_recorded` in the request window and re-expose presence. This is
  accepted only because of the visibility model: **DEBUG logs are
  operator-only and must never be exposed to owners or any user** (no debug
  endpoint, no log viewer in the UI, no forwarding of DEBUG to a
  user-visible channel). That is a requirement for WISHENKA-23 and for
  operations, not an assumption that DEBUG is off.
- **Worker records and timing.** The worker emits records a short, roughly
  fixed time after `receipt_recorded`, once per outbox row (per giver). Per-row
  records at INFO or above (`sent`, `retry_scheduled`, `send_failed`,
  `failed_terminal`) would show by count and by time that the wish was booked,
  by how many givers, and when a giver acted, by temporal correlation even
  without shared ids. Decision: **per-row worker events are DEBUG only.** At
  INFO or above the worker emits only:
  - `receipt_notice_window_summary`: one record per fixed time window with
    counts `sent`, `retried`, `failed_terminal` over all rows processed in the
    window, no ids, not per giver and not per receipt. It is not emitted per
    batch and not per receipt. A window can contain rows of several unrelated
    receipts, and a window can contain several poll batches (the per-batch
    figure `receipt_notice_batch_processed` is DEBUG).
  - start and stop of the worker, and `receipt_notice_worker_error` for a
    failure of the loop itself. That record carries `error_class` only, does
    not depend on whether rows exist, and is not tied to a row.
  - An idle worker (empty batch, no rows in the window) emits nothing at
    INFO or above. No heartbeat record is written.
- **Window rules.** The window is configurable (a new setting, for example
  `receipt_notice_summary_window_seconds`) with an enforced minimum of 60
  seconds and a default of 300 seconds. The window ends on a fixed grid of
  wall-clock boundaries, never «N seconds after the first row», because a
  window that starts at the first row would reveal the time of the receipt.
  The poll interval must not exceed the window. The aim is that a single-giver
  case cannot be told apart from many givers by the batching or by the poll
  interval: the record never reports the size of one batch at INFO. The
  counters of an unfinished window are not flushed on stop (the stop record
  carries no counts); the database is the system of record. The terminal
  failure of one notice is reported at INFO or above only as `failed_terminal`
  in the summary; the per-row detail is at DEBUG. Operators get the per-row
  facts (status, attempts, last error class if stored) from the database
  outbox row.
- **Temporal correlation: accepted or closed.** Closed for any stream an
  owner can see: such a stream carries no worker records at all, and the
  request-window records carry no presence signal at INFO or above. Closed at
  INFO or above for per-giver and per-receipt joins by id, by count of
  records, and by one-to-one delay: no INFO record corresponds to one row or
  one receipt. **Accepted, with a stated residual:** on an otherwise idle
  system a window summary with non-zero counts appears after the window in
  which a receipt had open promises, and no summary appears when it had none.
  It is accepted because the stream is operator-only, an operator already
  reads the outbox rows in the database, the record carries only system-wide
  counts that merge unrelated receipts, and the fixed grid and the minimum
  window blur the time to the window size. Closing it fully would need a
  fixed-cadence heartbeat with noise, which contradicts the rule that an idle
  worker writes nothing, and is not required while logs stay operator-only.
- **After commit only.** `receipt_recorded` and the producer events are
  logged after the commit. On a rollback nothing but
  `receipt_notice_enqueue_failed` is emitted, with `error_class` only, because
  no receipt and no `outbox_id` exist then. A «created» record for a row that
  never existed is not possible.
- The worker events do not repeat the de-dup key or the giver.
- «Receipt refused» uses only the closed reasons of the contract
  (`quantity_invalid`, `quantity_above_remaining`, `wish_archived`,
  `wishlist_not_active`, `nothing_remaining`, `forbidden`, `busy`), never free
  text. `remaining_quantity` is requested minus received. It is the owner's own
  information, and the contract (`20-architecture.md`, section 5, FR-6.2,
  corner case 6) lets the refusal message name it, so logging it reveals
  nothing about bookings. It is logged only for `quantity_above_remaining` and
  `nothing_remaining` (value 0), and never as free remaining or occupied
  quantity. `busy` is WARNING and matches the existing `reservation_inventory_busy`
  pattern (503, nothing changed).
- Settings gate decisions are visible at DEBUG (operator-only, see «Presence
  and timing») through
  `receipt_notice_created` (pending) and `receipt_notice_skipped` (with which
  level decided), by `outbox_id` only. The log never records the giver's
  setting value as a person-level fact beyond the `gate` level.
- The worker never reads settings (`20-architecture.md`, section 4), so no
  settings decision is logged in the worker.
- `error_class` is the exception class name, not the message. Telegram error
  text may contain a chat id.
- `item_fulfilled` already exists (`reservations.md` matrix, INFO). If kept,
  it keeps its current message and fields: it carries the owner or author, not
  a giver, so it breaks no rule here. WISHENKA-23 may instead rename it to
  `receipt_recorded` together with the doc and
  `tests/test_reservation_observability.py`, and must not emit both for one
  act.

### Fields that MUST NEVER be logged

The rule behind this list is the surprise principle (`specs/00-high.md`
invariants 1 and 4; FR-4.3, FR-6 of the requirements; section 6 of the
architecture): nothing on a stream tied to the owner side may reveal a giver, a
booking or a booked quantity.

- Giver identity: giver user id, Telegram id, username, first name, or chat
  id, in any receipt, archive, outbox or worker record. Notice records
  correlate by `outbox_id` only; the giver is found in the database by an
  operator, not in the log. (This is stricter than the older `reservation_*`
  events, which carry `user_id`; the notice path must not copy that.)
- Anything about reservations: reservation id, status (`active`, `purchased`),
  occupied or free quantity, booked quantity, number of open promises.
- Counts that reveal bookings. `receipt_recorded` must NOT carry the number of
  notices created or the number of givers, because a non-zero count says that
  someone booked. Counts of notices exist only as metrics aggregated across
  all receipts, never per receipt on the receipt record.
- Any link between a notice and a receipt: `receipt_id`, `item_id`,
  `wishlist_id` on any `receipt_notice_*` event, and `outbox_id` on
  `receipt_recorded`, `receipt_refused` or any archive event. The number or
  presence of notice records for one receipt would show that the wish was
  booked. Producer events and per-row worker events stay DEBUG for the same
  reason (see the notes under the events table).
- Any worker record at INFO or above that is per row, per giver or per
  receipt: `outbox_id`, `attempt`, `max_attempts` or `error_class` of one
  row, and a size of one batch. Those exist only at DEBUG. A window that
  starts at the first row, and any per-batch summary at INFO or above, are
  also forbidden.
- Notice text, wish title, list title, outbox payload, any free-text
  exception message, Telegram error body.
- A refusal that states or implies booked units (FR-6.2). `receipt_refused`
  carries the closed `reason` only. For `quantity_above_remaining` and
  `nothing_remaining` the `remaining_quantity` may be logged (the message may
  name it, see the notes under the events table), nothing more.
- Tokens, cookies, share-token paths (the existing redaction rules apply).

### The `_NOTICE_MARKS` assertion — how WISHENKA-23 avoids tripping it

`tests/test_surprise_role_context.py` (`test_recipient_walk_hides_booking_in_response_log_and_notice`)
runs a recipient walk with `caplog` at INFO and asserts, for every record
captured during the walk:

- the gifter name, username and Telegram id are absent from the message plus
  all extras (`_record_text`, which dumps every extra field);
- the words in `_NOTICE_MARKS` (`notification`, `outbox`, `push`) are absent
  from `event` plus the formatted message (case-insensitive). Extras other
  than `event` are not checked for these words, but do not rely on that;
- no notification table exists after the walk (`_NOTICE_TABLES`; the
  architecture, Q1, already requires WISHENKA-23 to replace this one).

Requirements that follow:

1. Event names and fixed message text for the notice path must not contain
   `notification`, `outbox` or `push`. Use `receipt_notice_*` for events and
   words such as «notice queue row» if a message needs a noun. Do not use the
   table name `notification_outbox` in any message or event.
2. The worker runs from the app lifespan, so it exists during the recipient
   walk and `caplog` captures its records. An idle worker (empty queue) must
   log nothing at INFO or above, and no heartbeat. Startup and stop records
   (`receipt_notice_worker_started`) appear before `caplog.clear()` in the walk
   and use no forbidden word anyway. The window summary event name
   (`receipt_notice_window_summary`) uses none of the three words either.
3. The recipient walk performs no receipt, so no `receipt_notice_*` record
   should be produced during it (producer and per-row worker events are DEBUG,
   the summary needs processed rows, and the walk captures INFO). If
   WISHENKA-23 changes the assertion as the architecture (Q1) requires, the replacement must keep the log-text check
   for gifter marks and keep the three words out of owner-visible records. Do
   not narrow the log-text check just to fit new events.
4. Giver identity is never logged (previous section), so the gifter-mark check
   cannot fail from the notice path even when a receipt precedes a read. The
   notice path also carries no `receipt_id`, `item_id` or `wishlist_id`, so
   nothing joins a notice to a wish.
5. Add a WISHENKA-23 test in the style of the existing one, with
   `caplog.at_level(logging.INFO)`. It runs the same sequence for two wishes,
   one with an open promise and one with none: the receipt, the «Подаренные»
   read, and then **the worker run to completion** (all pending rows sent
   through a fake bot, and the summary window flushed deterministically, for
   example by a fake clock or a direct flush call). A background receipt with
   an open promise on an unrelated wish is part of both runs, so that the
   summary exists in both (a window can merge unrelated receipts). It
   asserts:
   - no giver mark, no reservation word and no booking quantity in any record
     (`_record_text`);
   - the set of event names and the set of extra keys of all INFO or above
     records from the receipt through the end of the worker run is identical
     for the wish with an open promise and for the wish with none;
   - no INFO or above record is per row: none has `outbox_id`, `attempt`,
     `max_attempts` or a per-row `error_class`; the worker records are only
     `receipt_notice_window_summary`, started or stopped, and
     `receipt_notice_worker_error`; and the number of worker records at INFO or
     above does not grow with the number of givers (run a variant with three
     givers on the promised wish and compare the count of records);
   - a second pass at DEBUG checks only the field rules: every record with
     `outbox_id` has none of `receipt_id`, `item_id`, `wishlist_id`,
     `event_type` or a giver key, and no record has both `outbox_id` and
     `receipt_id`. The presence difference at DEBUG is expected and is not
     asserted (see «Presence and timing»).

   The residual of an otherwise idle system (a summary only when rows exist)
   is accepted in this design and is not asserted; the background receipt
   keeps the two runs comparable.

   Numeric check. The existing `_has_whole_number` matches the whole numbers
   `_BOOKED` (3) and `_REMAINDER` (4) anywhere in the record text, so fields
   such as `attempt`, `max_attempts`, `outbox_id`, `received_quantity` and the
   summary counts can collide and make the new test flaky. The new test must
   either scope the numeric check to the quantity keys that may carry a
   booking figure and to the message text, or pick fixture values for the
   booking that cannot collide with any logged number (for example booked 37
   and remainder 41, above `max_attempts`, any seeded id and any summary
   count). Preferably it does both.

### Candidate metrics

The project has no metrics library or endpoint (verified: `pyproject.toml`,
`wishenka/`). Two options, the choice belongs to WISHENKA-23 and the product
owner:

- Follow the existing convention: define the metric names in `doc/dev` and
  derive them from structured log events in the aggregator, as
  `reservations.md` does today. No code dependency is added.
- Add an exporter (for example `prometheus_client`) in a separate infrastructure
  story. That is a new dependency and a new endpoint (access control, scrape
  config), so it is not assumed here.

Candidate metrics, aggregated across the whole system only:

| Metric | Source event or query | Label values (closed, low cardinality) |
| ------ | --------------------- | -------------------------------------- |
| `wishlist_receipts_total` | `receipt_recorded`, `receipt_refused` | `outcome` = `accepted` or a closed refusal reason; `full` = true/false |
| `wishlist_receipt_notices_total` | `sent` and `failed_terminal` of `receipt_notice_window_summary`, or a system-wide count of rows by status; `pending` and `skipped` from the same count (the producer and per-row events are DEBUG) | `status` = `pending`, `skipped`, `sent`, `failed` |
| `wishlist_receipt_notice_retries_total` | `retried` of `receipt_notice_window_summary` | none |
| `wishlist_receipt_notice_send_failures_total` | in-process worker counter or the stored last error class of outbox rows (system-wide); not a log event, because the per-row events are DEBUG | `error_class` (closed set of exception class names) |
| `wishlist_receipt_notice_duplicates_total` | database-side system-wide counter, incremented in the receipt transaction when the de-dup insert finds the key (zero rows inserted); one counter row, no receipt, giver or outbox key; not sourced from the DEBUG event | none |
| outbox depth (gauge) | count of `pending` rows | none |
| outbox oldest pending age in seconds (gauge) | `now - created_at` of the oldest `pending` row | none |
| terminal failed rows (gauge) | count of `failed` rows | none |
| `wishlist_receipt_notice_delay_seconds` (histogram) | `sent_at - created_at` | none |
| `wishlist_archive_partial_total` | `wish_archived_partial`, `wish_restored_partial` | `action` |

Rules for metrics: never use `user_id`, `wishlist_id`, `item_id` or a giver as a
label (cardinality and surprise). A per-receipt «notices created» figure is
never exposed; only the system-wide totals above. No metric may be sourced
from a DEBUG event, because DEBUG may be off or operator-only. A gap between created
and sent, a growing outbox age, or any failed gauge above zero is the operational
signal named in `20-architecture.md` (Q5); it is never shown to a user.

Suggested alert thresholds for WISHENKA-23 to confirm: oldest pending age above
a few worker intervals; any terminal failed row; refused-receipt rate far above
the accepted rate (a possible UI defect in WISHENKA-24).

### Per-story hand-off

- WISHENKA-23: implement the events and fields above, the `error_class`-only
  rule, the `outbox_id`-only correlation rule for the notice path (no
  `receipt_id`, `item_id`, `wishlist_id` or giver there, and no log field may
  join an `outbox_id` to a receipt), the DEBUG level of producer events and
  of all per-row worker events, the INFO aggregate
  `receipt_notice_window_summary` with the window setting (minimum 60 seconds,
  fixed grid, no heartbeat, poll interval not above the window), the
  operator-only access requirement for DEBUG logs (`LOG_LEVEL=DEBUG` is a
  normal setting and re-exposes presence in the request window), the
  database-side duplicates counter, the metric choice, and the walk-test rule
  with the worker run; document the final matrix in `doc/dev` in its own Step 8
  (this story does not edit `doc/dev`).
- WISHENKA-24: route-level records for the receipt route only (accepted or
  refused with the closed reason, `busy` as 503); no booking data in any
  template, script or client log; the existing browser tests already assert
  no booking marker for the recipient.

## Notes

- Verified for this step: only Markdown changed (`git status --porcelain`
  shows no change in `wishenka/`, `tests/` or `doc/dev`).
- Open point for WISHENKA-23 Step 2: whether to keep `item_fulfilled` or
  rename it (see the note under the events table). Either choice must update
  `tests/test_reservation_observability.py` and `reservations.md` in the same
  story.
- Open point for WISHENKA-23 Step 2 (the architecture is frozen, so it is
  recorded here): `receipt_notice_enqueue_failed` only arises when there are
  rows to insert (apart from a generic database error), and the receipt then
  rolls back with an error response. The presence signal therefore comes from
  the response behaviour fixed in `20-architecture.md`, not from the log.
  Step 2 must make that failure behaviour indistinguishable from the other
  failures of the receipt, or document the difference as an accepted
  residual.
- Open point for WISHENKA-23 Step 2: the storage of the database-side
  duplicates counter, and whether the outbox row stores the last error class
  (the per-row facts operators need for terminal failures).
- Open point for the product owner: whether a metrics exporter is wanted at
  all (the project has none).
