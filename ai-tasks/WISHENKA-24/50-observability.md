# WISHENKA-24: Observability Implementation

Binding rules: `ai-tasks/WISHENKA-22/50-observability.md` (allowed fields, never-logged list, operator-only
logs, presence and timing) and `ai-tasks/WISHENKA-23/50-observability.md` (loggers, JSON route events,
levels: INFO success, WARNING refusal or busy). All UI log calls were written in Step 4 (P8 to P13).
Step 6 audited every log call added or changed by this task, found no defect in production code (no
production file changed in this step), recorded four open points, and added one test file
(`tests/test_receipt_ui_observability.py`, 1 test) for the full-flow scan.

## Logging Implementation

### Added Logs

All records set `extra={"event": ...}`. Logger of the UI path: `wishenka.web.receipts_ui`. Messages are
fixed text, no interpolation. Extra keys are the 22 set without `operation`.

| Logger | Level | Event | Extra keys (besides `event`) | Emitted at |
| ------ | ----- | ----- | ---------------------------- | ---------- |
| `wishenka.web.receipts_ui` | INFO | `ui_receipt_form_opened` | `wishlist_id`, `item_id`, `actor_id` | `receipts_ui.py:get_receipt_dialog` |
| `wishenka.web.receipts_ui` | WARNING | `ui_receipt_form_refused` | `wishlist_id`, `item_id`, `actor_id`, `reason`, `http_status`, `remaining_quantity` only for `quantity_above_remaining` and `nothing_remaining` | `get_receipt_dialog` via `_log_refusal` (reasons incl. `busy`, 503) |
| `wishenka.web.receipts_ui` | INFO | `receipt_recorded_http` | `wishlist_id`, `item_id`, `actor_id` | `receipts_ui.py:record_receipt_ui`, after the commit and the state read |
| `wishenka.web.receipts_ui` | WARNING | `receipt_refused` | as `ui_receipt_form_refused` | `record_receipt_ui` via `_log_refusal` |
| `wishenka.web.receipts_ui` | WARNING | `receipt_inventory_busy` | `wishlist_id`, `item_id`, `actor_id` | `record_receipt_ui` (`InventoryBusyError`) |

Messages: `Receipt dialog opened`, `Receipt recorded`, `Receipt refused` (both refusal events), `Receipt busy`.

Not logged by the UI layer, by design:

- Stale archive and restore of a fully received wish (`items_ui._nothing_remaining_response`, 409 with
  `X-Receipt-Refusal: nothing_remaining`). The domain service already writes the one
  `wish_archive_refused` WARNING (logger `wishenka.wishlists`, keys `wishlist_id`, `item_id`, `actor_id`,
  `reason`) before raising, exactly as before this task. The replaced `_raise_nothing_remaining` wrote
  nothing either. One record per outcome holds (tested).
- Stale reorder 400 with `X-Reorder-Refusal: stale_order` (`items_ui._reordered_response`). The existing
  WARNING `ui_items_reorder_rejected` (logger `wishenka.web.items_ui`, keys `wishlist_id`, `actor_id`,
  `user_id`, `reason=invalid_permutation`) is written before the response; this task only added the
  header. No new event.
- The effect read after a refusal (`_effect_fragments`) and the gifted read (`gifted_view.read_gifted_rows`)
  write nothing, including when they degrade.
- `gifted_view.py`, `sharing.py` (`is_member` flag only), templates and `app.py` (router include): no log call
  added or changed.
- Existing events on the same request, unchanged: `item_fulfilled` (service, logger `wishenka.wishlists`,
  kept by 22), `wish_archived_partial`, `wish_restored_partial`, `wish_archive_refused` (23).

### Log Structure

- Structured logs: yes (`extra={"event": ...}`, `JsonFormatter` puts extras under `extra`).
- Includes context: yes, `wishlist_id`, `item_id`, `actor_id`; `reason` and `http_status` for refusals.
- Log levels used: INFO, WARNING. No ERROR on this path: an unclassified exception is re-raised and the
  application error handling logs it.
- One record per outcome (accepted, refused by reason, busy, dialog opened, dialog refused). The refusal
  record is written before the effect read, so a degraded read does not add or remove a record.
- Event and message text contain none of `notification`, `outbox`, `push`.

## Audit of the log calls against the binding rules

| Item | Verdict |
| ---- | ------- |
| Field set of every UI record = 22 allowed set without `operation` | OK |
| No `user_id`, `operation`, `quantity`, title, giver, booking number, exception text, token | OK |
| `remaining_quantity` only for `quantity_above_remaining`, `nothing_remaining` (`_log_refusal`, `_WITH_REMAINING`) | OK; `busy`, `forbidden`, `not_found` etc. carry none |
| Levels: INFO success and dialog open, WARNING refusal, busy, dialog refusal | OK (23 convention) |
| One record per outcome | OK, tested |
| No `outbox_id` on UI records, none shares a record with receipt keys | OK, tested over all records of the flow |
| Pre-existing event names reused (`receipt_*`) by design (22 `wishlist_receipts_total`) | OK, see Metrics |
| Stale archive and restore | OK, service `wish_archive_refused` only, same as before |
| Stale reorder | OK, existing `ui_items_reorder_rejected` |

Fixes in production code: none needed.

## Metrics Implementation (if applicable)

No exporter exists; WISHENKA-84 tracks it. None implemented. Nothing is sourced from DEBUG.

### Performance Metrics

- **Response time**: only the existing request-completed record of `RequestLoggingMiddleware`; nothing
  receipt-specific added.
- **Throughput / error rate**: see below.

### Business Metrics derivable from the UI events

| Metric | Source | Derivable |
| ------ | ------ | --------- |
| Receipts by outcome (`wishlist_receipts_total`) | `receipt_recorded_http` (accepted) and `receipt_refused` by `reason` on logger `wishenka.web.receipts_ui` | yes; `full` is not on the UI record, use the service `item_fulfilled.fully_received` |
| Dialog opened vs submitted | `ui_receipt_form_opened` vs the three attempt events | yes (a rate, not a count of users) |
| Dialog refusals by reason | `ui_receipt_form_refused` by `reason` | yes; own event name keeps them out of the refusal rate |
| Busy rate | `receipt_inventory_busy` (POST), `ui_receipt_form_refused` with `reason=busy` (GET) | yes |
| Stale archive or restore rate | `wish_archive_refused` (service) | yes, system-wide; the channel (UI or JSON) is not recorded |
| Stale reorder rate | `ui_items_reorder_rejected` (`reason=invalid_permutation`) | yes, system-wide |
| Receipt quantity, per-wish or per-giver figures | none | no (never logged) |
| Client-side failure rate (generic sentence) | none | no (see Client) |

### Shared event names and double counting

`receipt_recorded_http`, `receipt_refused` and `receipt_inventory_busy` are written by both
`wishenka.web.receipts` (JSON route) and `wishenka.web.receipts_ui` (UI). A consumer tells the channel
apart by the logger name only (the UI records have no `operation` key; the JSON ones do). A count by event
name alone adds both channels, which is the intended sum for `wishlist_receipts_total`, but double counts
if a per-channel total is later added to the sum of both. A UI receipt writes one UI record and calls the
service once, so the same act never produces records on both loggers. `item_fulfilled` (service) is written
once per accepted act on either channel and is the channel-neutral source.

### System Health Metrics

- N/A (no new component or resource).

## Client (JS) observability

- `receipt.js` and the `wishlist.js` additions (`swapWishCard` wrapper, `htmx:responseError` listener)
  contain no `console.*`, no `sendBeacon`, `fetch`, `XMLHttpRequest`, `Image` beacon, `localStorage`,
  `sessionStorage`; checked by grep and by `tests/test_receipt_static_script.py` hygiene tests. Server text is
  rendered into the DOM only, never stored or sent.
- The only client signals are user-visible: the generic sentence «Не удалось сохранить отметку. Повторите
  попытку.» when an attempt ends without a server sentence; the notice and a reload after 800 ms when
  `X-Reorder-Refusal: stale_order` arrives; the neutral stale-card text. They are not sent anywhere. The
  server records of the same requests (status, reason) are the operator signal; a pure network failure leaves
  no server record.
- Real htmx writes `console.error` for an unswapped 4xx by itself (expected, not from our code).

## Monitoring Integration

- [ ] Prometheus metrics (WISHENKA-84)
- [ ] Grafana dashboards
- [ ] Alerting rules
- [x] Log aggregation: structured `event` extras of the existing `JsonFormatter`

## Validation Results

- [x] Logs are correctly formatted: exact key sets per event asserted
- [ ] Metrics are collected correctly: N/A, no exporter
- [x] Logging works in error scenarios: every `_REFUSALS` class path of the flow (above, invalid, forbidden,
  not_found, wish_archived, nothing_remaining, busy POST and GET, stale GET) asserted
- [x] Large data structures are not logged: scalar ids only
- [ ] Metrics are available for monitoring: N/A

Tests of the contract (caplog C1-C5, no network, explicit `timeout`):

- `tests/test_receipt_ui_observability.py::test_full_ui_flow_log_contract` (new): three promised givers
  (37, 41, 53), partial receipt, refusals, busy (POST and GET), stale open, stale archive, stale restore, stale
  reorder. Asserts for each UI outcome exactly one record on `wishenka.web.receipts_ui`, event, level, the
  exact extra key set, `reason`, `http_status`, `remaining_quantity` (93 and 0) only for the two reasons, and
  zero UI records for archive, restore and reorder. Scans every `wishenka*` record of the flow for giver
  names, titles, booking numbers, the English route messages, the Russian sentences, tracebacks, `exc_info`,
  notice words in event and message, and an `outbox_id` key together with a receipt key; UI records also for
  `operation`, `user_id`, `outbox_id`, `quantity`, `title`, numbers 37, 41, 53, 7, 999, 200, 300; fixed
  message set. Mutation checks: adding `user_id` to `_log`, and interpolating a title into the busy message,
  each fail the test.
- `tests/test_receipt_ui_routes.py::test_ui_logging_once_per_outcome` (Step 3): six outcomes, field subset.
- `tests/test_receipt_observability.py` (23, JSON route and notice path): unchanged; it filters by exact
  logger name `wishenka.web.receipts`, so the UI logger is not swept into it.
- `tests/test_surprise_role_context.py` / `test_surprise_receipt_walk.py` (`_NOTICE_MARKS`): green.

## Notes

1. `ui_items_reorder_rejected` (existing) carries `user_id` next to `actor_id`. Pre-existing, not on the
   receipt path, owner's own act; not changed. Candidate for a debt item (Step 7).
2. The JSON route interpolates the operation name in its message and writes `operation`; the UI records do
   not. This difference is the documented way to tell channels apart besides the logger name.
3. `ui_receipt_form_refused` and `receipt_refused` share the message text `Receipt refused`; consumers must
   use `event`. Left unchanged (cosmetic).
4. Stale archive and restore are not distinguishable by channel in logs (the service writes the record for
   both). Metrics are system-wide only, as 22 requires.
5. No record exists for a client network failure or an unclassified 500 beyond the framework's own.
