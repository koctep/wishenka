# WISHENKA-23: Observability Implementation

Binding rules: `ai-tasks/WISHENKA-22/50-observability.md` (event table, notice-path correlation rule,
presence and timing, never-logged list, window summary) as amended by `20-architecture.md` section 11
and the Divergences list. Most log calls were written in Step 4. Step 6 audited every call, fixed three
small defects and added `tests/test_receipt_observability.py` (8 tests).

## Logging Implementation

### Added Logs

Loggers: `wishenka.wishlists` (domain, existing), `wishenka.web.receipts` (route),
`wishenka.wishlists.notices` (producer after commit, worker, lifespan start and stop, purge is on
`wishenka.wishlists.cleanup`), `wishenka.wishlists.migrations`. Every record sets `extra={"event": ...}`.

- **EMERG / ALERT / CRIT**: N/A, nothing in this story needs them.
- **ERR**: `wishenka/notices/worker.py:NoticeWorker.run` - `receipt_notice_worker_error`, field
  `error_class`, once per failure streak (queue cannot be read or settled), loop backs off to 60 s.
- **WARNING**:
  - `wishenka/web/routes/receipts.py:_refusal` - `receipt_refused` (`operation`, `wishlist_id`, `item_id`,
    `actor_id`, `reason`, `http_status`, `remaining_quantity` only for `quantity_above_remaining` and
    `nothing_remaining`).
  - `receipts.py:_busy` - `receipt_inventory_busy` (`operation`, `wishlist_id`, `item_id`, `actor_id`).
  - `wishenka/wishlists/service.py:_log_archive_refused` - `wish_archive_refused` (`wishlist_id`, `item_id`,
    `actor_id`, `reason=nothing_remaining`), from `archive_wish_item` and `restore_wish_item`.
  - `wishenka/wishlists/cleanup.py:_purge_notices` - `receipt_notice_purge_failed` (`error_class`).
- **NOTICE**: no separate Python level; significant events are INFO.
- **INFO**:
  - `service.py:record_item_fulfillment` - `item_fulfilled` (kept, TD-1.5): `wishlist_id`, `item_id`,
    `user_id`, `actor_id`, `quantity`, `received_quantity`, `total_quantity`, `fully_received`.
  - `receipts.py:record_receipt` - `receipt_recorded_http` (`item_id`), after the transaction succeeded.
  - `service.py:_log_partial_move` - `wish_archived_partial`, `wish_restored_partial` (`wishlist_id`,
    `item_id`, `actor_id`, `received_quantity`, `total_quantity`); silent for a wish nothing was received of.
  - `alembic/versions/add_gift_receipts.py:upgrade` - `legacy_receipts_backfilled`,
    `legacy_archived_rows_normalised` (`rows`), logger `wishenka.wishlists.migrations`.
  - `notices/worker.py:NoticeWorker.flush_if_due` - `receipt_notice_window_summary` (`window_seconds`,
    `sent`, `retried`, `failed_terminal`), only for a closed window that processed rows.
  - `web/app.py:_start_notice_worker` / `_stop_notice_worker` - `receipt_notice_worker_started`,
    `receipt_notice_worker_stopped`, `receipt_notice_worker_disabled` (`reason`: `no_bot_token` or
    `disabled_by_setting`).
  - `cleanup.py:_purge_notices` - `receipt_notice_rows_purged` (`rows`), only when `rows > 0`.
- **DEBUG** (operator-only, per row, never a metric source):
  - `wishlists/store.py:_log_flushed_notices` (after commit) - `receipt_notice_created` (`outbox_id`),
    `receipt_notice_skipped` (`outbox_id`, `gate`).
  - `notices/worker.py:NoticeWorker._debug` - `receipt_notice_sent`, `receipt_notice_send_failed`,
    `receipt_notice_retry_scheduled`, `receipt_notice_failed_terminal` (`outbox_id`, `attempt`,
    plus `error_class` for the failure events).
  - `worker.py:run_once` - `receipt_notice_batch_processed` (`rows`), only when `rows > 0`.
  - `notices/store.py:NoticeStore.claim_next` - the stale `sending` row settled inside the claim logs the
    same `_retry_scheduled` / `_failed_terminal` (`outbox_id`, `attempt`).
  - `notices/store.py:NoticeStore._settle` - `receipt_notice_late_write_ignored` (`outbox_id`).

### Log Structure

- Structured logs: yes (`extra={"event": ...}`, rendered by `JsonFormatter` of `wishenka/logging.py` with
  extras under `extra`, or by the text formatter).
- Includes context: yes, business ids on the owner-side events; `outbox_id` only on the notice path.
- Log levels used: ERROR, WARNING, INFO, DEBUG.
- Message text of the new events is fixed (no interpolated ids). Exceptions from the older, kept events:
  `item_fulfilled` keeps its existing message with ids (22 allows keeping it unchanged); the two route
  records `receipt_refused` / `receipt_inventory_busy` / `receipt_recorded_http` interpolate the operation
  name or item id as the existing promise routes do (no giver, no booking data).
- Event names and messages of the notice path contain none of `notification`, `outbox`, `push`.
- `error_class` is the exception class name, never the message.
- An idle worker, an empty window and a stop write nothing.

## Audit of Step 4 logging against WISHENKA-22 and the architecture

| Item | Result |
| ---- | ------ |
| Event names, loggers, levels of the notice path | match section 11 (22 table minus the three dropped events) |
| No `receipt_id`, `item_id`, `wishlist_id`, `event_type`, giver key on any `receipt_notice_*` event | OK, tested |
| Per-row worker events at INFO or above | none; INFO or above holds only the summary, start, stop, disabled, purge, error |
| Idle worker silent, summary only when rows were processed, nothing on stop | OK, tested (`run_once` logs batch only when rows, `flush_if_due` only when counts) |
| Producer events after commit only | OK (`_log_flushed_notices` is called after the transaction) |
| Exception messages, tokens, titles, text | OK: only `type(err).__name__`; token scan test exists (`test_token_never_logged_with_real_bot`) |
| Forbidden words in event names or messages | none |
| `receipt_refused` fields | **Defect, fixed**: the record had `operation`, `reason`, `http_status` but no `wishlist_id`, `item_id`, `actor_id` and no `remaining_quantity`. Now complete per section 11 |
| `receipt_inventory_busy` fields | **Defect, fixed**: now also carries `wishlist_id`, `item_id`, `actor_id` |
| `wish_archived_partial`, `wish_restored_partial`, `wish_archive_refused` | **Missing, added** (listed in section 11 and in 22; not emitted by Step 4) |
| `receipt_notice_retry_scheduled` lacks `max_attempts` (22 table lists it) | Recorded, not changed: DEBUG only, not a metric source, `attempt` is logged and the limit is a setting |
| `receipt_recorded_http` is not in 22 or in section 11 | Recorded, kept: route-level INFO record that 22 asks for in the hand-off for WISHENKA-24; carries `item_id` only, no `outbox_id`, not a second domain event |
| `item_fulfilled` also carries `user_id` (owner, existing field) | Kept (22 allows the existing fields; it is the owner's own act) |
| `item_archived` (existing, not from this task) carries `active_reservations_count` | Out of scope of this task (pre-existing event, not on the receipt path). Noted for Step 7 as a presence signal on the owner stream |

## Fixes applied in Step 6 (production code)

1. `wishenka/web/routes/receipts.py`: `_run`, `_refusal`, `_busy` now receive a small context
   (`wishlist_id`, `item_id`, `actor_id`); `receipt_refused` adds `remaining_quantity` for the two
   allowed reasons. No response change.
2. `wishenka/wishlists/service.py`: new `_log_archive_refused` and `_log_partial_move`; three events
   `wish_archived_partial`, `wish_restored_partial`, `wish_archive_refused`. Only logging added, no
   behaviour change.
3. (Test support) none; `tests/test_receipt_observability.py` is new.

## Metrics Implementation

No exporter is implemented (WISHENKA-84 tracks it). Metrics are derived from structured log events at INFO or
above and from read-only SQL over the DB, as in 22 ("follow the existing convention"). No metric is sourced
from a DEBUG event. Labels never use user, wishlist, item or giver.

### Performance Metrics

- **Response time**: existing `HTTP request completed ... duration` of `RequestLoggingMiddleware`; nothing
  receipt-specific added.
- **Throughput**: see `wishlist_receipts_total` below.
- **Error rate**: `receipt_refused` by `reason` against accepted receipts.

### Business Metrics

| Candidate (22) | Derivable | Source and caveat |
| -------------- | --------- | ----------------- |
| `wishlist_receipts_total` (`outcome`, `full`) | yes | accepted: `item_fulfilled` (`fully_received` gives `full`); refused: `receipt_refused.reason`. DB cross-check: `SELECT count(*) FROM wl_receipts` |
| `wishlist_receipt_notices_total` by `status` | yes, by SQL | `SELECT status, count(*) FROM notification_outbox GROUP BY status` (system-wide, includes `sending`; retention 30 days). `sent` and `failed_terminal` also as window counts of `receipt_notice_window_summary`, delayed by up to the window |
| `wishlist_receipt_notice_retries_total` | yes | `retried` of `receipt_notice_window_summary` (counted only when the guarded write changed a row) |
| `wishlist_receipt_notice_send_failures_total` by `error_class` | **no** | not a log event at INFO and not a counter. `last_error_class` is stored but it is cleared on a later success and only describes the current state of a row, so a total over time cannot be built. Only a gauge of rows now `pending` or `failed` per class is available by SQL |
| `wishlist_receipt_notice_duplicates_total` | **no, dropped by design** | architecture Divergence 2: the receipt id is new in its transaction, so a key hit never happens. The real risk (resend after an ambiguous outcome) is bounded by the `ambiguous` flag; see the gauge below |
| `ambiguous` gauge | yes, with caveat | `SELECT count(*) FROM notification_outbox WHERE ambiguous = 1`. The flag is never cleared, so a row that was ambiguous and later `sent` still counts; the gauge is "rows with a possible duplicate or loss in the retention window", not "open ambiguous rows". Use `AND status IN ('sent','failed')` for possible duplicates and `failed` for unconfirmed deliveries |
| outbox depth | yes, SQL | `count(*)` where `status = 'pending'` (rows `sending` are in flight; add them for "not finished") |
| oldest pending age | yes, SQL | `now - min(created_at)` of `pending` rows; `next_attempt_at` shows the next due time |
| terminal failed rows | yes, SQL | `count(*)` where `status = 'failed'` |
| `wishlist_receipt_notice_delay_seconds` | yes, approximate | no `sent_at` column (decision, Divergence 15). `updated_at - created_at` of `sent` rows is the proxy: a settle writes `updated_at` once at the final transition, a later write is guarded and cannot touch a `sent` row. Second resolution, retained 30 days, SQL histogram only, no event |
| `wishlist_archive_partial_total` (`action`) | yes | `wish_archived_partial`, `wish_restored_partial` (INFO), now emitted |

### System Health Metrics

- **Resource usage**: not added.
- **Component status**: `receipt_notice_worker_started` / `_stopped` / `_disabled` (INFO) show the worker
  state; `receipt_notice_worker_error` (ERROR) is the loop failure signal; a growing oldest-pending age with
  no summary means the worker is stopped or the sender is down. Alert thresholds of 22 are adopted unchanged
  (oldest pending above a few poll intervals, any `failed` row, refusal rate far above accepted).

## Monitoring Integration

- [ ] Prometheus metrics - N/A, no exporter (WISHENKA-84)
- [ ] Grafana dashboards - N/A
- [ ] Alerting rules - thresholds recorded above; no rule engine in the repository
- [ ] Log aggregation - stdout JSON or text lines; collection is infrastructure

Requirement carried from 22: **DEBUG logs are operator-only** (no debug endpoint, no log viewer, no
forwarding to a user-visible channel). `LOG_LEVEL=DEBUG` re-exposes presence in the request window
(`receipt_notice_created` right after `item_fulfilled`).

## Validation Results

- [x] Logs are correctly formatted: every new record has `event`, a fixed message and only the fields above;
  checked by `_extras(record)` assertions in `tests/test_receipt_observability.py`.
- [x] Metrics are collected correctly: N/A for an exporter; the log-derived counts are asserted
  (`sent`/`retried`/`failed_terminal` in the summary, `rows` of the batch, `fully_received`); the SQL gauges
  are queries documented here (Step 8 moves them to `doc/dev`).
- [x] Logging works in error scenarios: `receipt_refused` (4 reasons incl. `forbidden`, `quantity_invalid`),
  `receipt_inventory_busy`, `wish_archive_refused`, sender failure (`RuntimeError`, `rejected`),
  `receipt_notice_worker_error` (existing `test_receipt_notices_extra.py`), `receipt_notice_purge_failed`
  (existing), late write ignored (existing).
- [x] Large data structures are not logged: only scalar fields; no DTO, no text, no title.
- [x] Metrics are available for monitoring: log-derived and SQL-derived as listed; the rest is stated as not
  derivable.

Commands run: `.venv/bin/pytest tests/test_receipt_observability.py` (8 passed),
`tests/test_reservation_observability.py`, `test_gift_receipt_api.py`, `test_gift_receipt_service.py`,
`test_surprise_receipt_walk.py`, `test_surprise_role_context.py` (all green), `ruff check`, `ruff format
--check`, `mypy wishenka tests` (clean). Full suite result: see the line under "Full suite" below.

### Never-logged guarantees and how each is tested

| Guarantee | Test |
| --------- | ---- |
| no giver name or id, no booking number on the receipt and notice path (all levels, DEBUG scope, three givers with booked 37, 41, 53) | `test_receipt_and_worker_run_never_log_giver_or_booking_data` |
| `outbox_id` is never joined with `receipt_id`, `item_id`, `wishlist_id`, `event_type` or a giver key; no notice-logger record carries those keys | same test |
| no per-row key (`outbox_id`, `attempt`, `max_attempts`, `error_class`) at INFO or above on the notice logger | same test |
| INFO or above holds one summary for 1 or 3 givers, same keys | `test_notice_logger_info_records_are_one_summary_for_any_giver_count` |
| exception message never logged, only `error_class`, at DEBUG | `test_exception_message_never_logged_only_error_class` |
| terminal failure is DEBUG per row and `failed_terminal` in the INFO summary | `test_rejected_terminal_counts_only_in_summary_at_info` |
| idle worker, empty window over several windows write nothing at any level | `test_idle_worker_and_empty_window_write_nothing` |
| forbidden words `notification`, `outbox`, `push` absent from event names and messages | `test_receipt_and_worker_run_never_log_giver_or_booking_data`; owner walk: `test_surprise_role_context.py`, `test_surprise_receipt_walk.py` (`_NOTICE_MARKS`) |
| token never logged, idle worker silent with a real bot object | `test_receipt_notices.py::test_token_never_logged_with_real_bot` |
| closed `receipt_refused` fields, `remaining_quantity` only for two reasons, `busy` record, `fully_received` | `test_refusal_and_busy_records_carry_closed_fields_only` |
| archive events and the refusal | `test_archive_events_for_partly_received_wish` |
| migration events: INFO, `rows` only, logger name | `test_migration_events_are_info_with_counts_only` (plus counts in `test_gift_receipt_migration.py`) |

Not tested (stated): the window rule "minimum 60 seconds" is a validation error of `Settings`; the
fixed grid is covered by `test_receipt_notices_extra.py` (window summary on a fixed grid). The
`receipt_notice_enqueue_failed` and `_duplicate_suppressed` events do not exist (Divergences 2, 3).

## Notes

- Residual (accepted, from 22/Divergence 14): `item_fulfilled` is logged inside the unit of work, before
  the commit. A failed commit leaves the record of an act that was rolled back; the store then writes
  `wishlist_inventory_rolled_back`. The producer DEBUG events do not have this property (after commit).
- Start, stop and disabled events are written by `web/app.py` (the lifespan helpers) on the notices
  logger, not by `NoticeWorker.run`; the worker task is cancelled on shutdown and the counters of an
  unfinished window are dropped by design (no counts on stop).
- A reason is not recorded by the route for `not_found` and `wishlist_not_active` refusals beyond the
  closed `reason`; they are WARNING like the others.
- Presence residual (accepted in 22): on an otherwise idle system a summary with non-zero counts appears
  after a window with open-promise receipts. Requires operator-only logs.
- Enqueue failure shows no log of its own; the receipt rolls back with the generic storage failure
  (`wishlist_inventory_rolled_back`), as decided in 1.6. Residual for Step 7.
- Open for Step 7: `item_archived` (existing event) logs `active_reservations_count` on the owner stream;
  `retry_scheduled` has no `max_attempts` (DEBUG, low value); `ambiguous` flag is never cleared, so the gauge
  needs the status filter above; `updated_at` is only an approximate sent time and the exporter and gauges
  are for WISHENKA-84; outbox retention and indexes are shared with WISHENKA-60 and WISHENKA-59.
- For Step 8 (`doc/dev`): document the event matrix above, the SQL gauges and the operator-only DEBUG rule.

## Full suite

`make test PYTEST='.venv/bin/pytest -q -p no:cacheprovider -rf --tb=short'`: 711 passed, 0 failed (703 + 8 new), 13 min.
`ruff check`, `ruff format --check`, `mypy wishenka tests`: clean.
