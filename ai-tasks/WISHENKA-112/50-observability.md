# WISHENKA-112: Observability Implementation

## Scope Decision

The task is a behaviour-preserving refactor: `_NOT_FOUND_ERRORS` renamed to `_DOMAIN_ERRORS` and the
reorder callable simplified to `Callable[[list[int]], list[int]]` in `wishenka/web/routes/items_ui.py`;
five redundant `hasattr`/`getattr` column probes removed in `wishenka/wishlists/store.py` (3) and
`wishenka/wishlists/repository.py` (2). No new logging or metrics is warranted and none was added.
The review below checked the diff against the code: no log call, event name, level or `extra` field
changed. No source file was touched in this step, so the Step 4/5 test and `make analyze` results stay
valid.

## Logging Implementation

### Added Logs

None. The existing events, all from logger `wishenka.web.items_ui` (`items_ui.py:39`), are unchanged
(verified in the diff and the code):

- **WARNING**: `_reordered_response` (`items_ui.py`, `except ValueError`) - event
  `ui_items_reorder_rejected`, extra `wishlist_id`, `actor_id`, `user_id`, `reason=invalid_permutation`;
  the response is HTTP 400 `Invalid item order`.
- **INFO**: `reorder_items_ui` - event `ui_items_reordered`, extra `wishlist_id`, `actor_id`,
  `user_id`, `item_count`. Emitted only after `_reordered_response` returned, so never on 400/404/409.
- **INFO**: `move_item_ui` - event `ui_item_moved`, extra `wishlist_id`, `item_id`, `actor_id`,
  `user_id`, `direction`. Same rule: not emitted on errors.
- **Domain error mapping (404/409)**: `_raise_http` does not log. Archived -> 409
  `Wishlist is archived`; every other member of `_DOMAIN_ERRORS` -> 404 `Resource not found`. The
  domain exception is chained (`from exc`) but there is no log line at the mapping site. The only
  trace is the access log line of the HTTP middleware in `wishenka/web/app.py` (method, path,
  `status_code`, `duration_ms`). This is as before the refactor and the detail text intentionally does
  not leak details. Not changed: adding a log here would be a new behaviour outside this task. It could
  be a follow-up if 404 triage needs the exception class.
- The rename `_NOT_FOUND_ERRORS` -> `_DOMAIN_ERRORS` and the callable change touch no log statement.
  `current_ids` is now computed once; the success events do not use it (`item_count` is
  `len(item_ids)` from the form, as before).

### Tests that now pin the events

`tests/test_items_ui_error_mapping.py` asserts through `caplog` (logger `wishenka.web.items_ui`, level
INFO):
- `ui_items_reorder_rejected`: two rejected requests (short list, unknown id) give exactly two
  records, level WARNING, `reason == "invalid_permutation"`, and no `ui_items_reordered`.
- `ui_item_moved`: one record on a real move, level INFO, `direction == "up"`, `item_id` correct.
- `ui_items_reordered`: one record on a real reorder, level INFO, `item_count == 3`.
- 404/409 on reorder and move: neither `ui_items_reordered` nor `ui_item_moved` is logged.
- 409/404 status mapping for reorder, move, archive-confirm, archive and restore.

The tests do not assert `actor_id`/`user_id`/`wishlist_id` values, and there is no test for the absence
of a log at the 404/409 mapping. These are accepted gaps, not changed in this step.

### Deliberate behavioural nuance: missing column

`store.py` and `repository.py` used to default silently (`hasattr`/`getattr`) when
`warn_on_delete_reserved` or `display_order` was missing from a result row. Now a missing column
raises `AttributeError`. Both columns are guaranteed by the schema and the Alembic migrations
(WISHENKA-111), so the case is only reachable if a query's select list or the schema is broken. Where
it is visible:
- The request fails with HTTP 500. The HTTP middleware (`wishenka/web/app.py`, `except Exception`)
  calls `logger.exception("HTTP request unhandled exception: <method> <path> duration=...")` with the
  full traceback (ERROR level), with `method`, `path`, `duration_ms` in `extra`; the traceback names the
  row attribute. Uvicorn also prints its own "Exception in ASGI application" traceback to the process
  stderr.
- Why this is intended: a silent default would hide a schema/query drift and show wrong data
  (`display_order` 0 for every item would break the manual order, `warn_on_delete_reserved` True would
  override a user's choice). A loud failure with a traceback is the better diagnostic. The `None`
  guards (nullable value in an existing column) and `or 0` are kept, so a NULL value is still handled
  as before.
- Not covered by a test (no test removes a column on purpose); noted, not added.

### Log Structure

- Structured logs: yes (`extra` with `event` and context fields).
- Includes context: yes.
- Log levels: INFO, WARNING (existing); ERROR via the middleware for the 500 case.

## Metrics Implementation (if applicable)

N/A. No runtime behaviour changed, so no new quantity to measure.

### Performance Metrics

- **Response time**: N/A. The middleware already logs `duration_ms` per request; the refactor does not
  change the number of queries (the probes were in-memory attribute checks) or the number of
  `reorder_wish_items` calls (pinned by a spy test: 0 when order is unchanged, 1 per real move/reorder).
- **Throughput / Error rate**: N/A, no metrics system in the project.

### Business Metrics

- N/A. No product behaviour changed.

### System Health Metrics

- N/A. No component or resource usage change.

## Monitoring Integration

- [ ] Prometheus metrics: N/A (project has no metrics endpoint; nothing new to export)
- [ ] Grafana dashboards: N/A (no metrics source)
- [ ] Alerting rules: N/A (no new failure signal; the AttributeError case is an existing 500 log)
- [ ] Log aggregation: N/A (existing log stream unchanged)

## Validation Results

- [x] Logs are correctly formatted: existing calls reviewed in the code, unchanged.
- [ ] Metrics are collected correctly: N/A
- [x] Logging works in error scenarios: 400 warning and the absence of success events on 404/409 are
  covered by `tests/test_items_ui_error_mapping.py`; the 500 path is existing middleware code
  (code-read, not exercised by a test for the missing-column case).
- [x] Large data structures are not logged: only ids and counts in `extra`.
- [ ] Metrics are available for monitoring: N/A

## Notes

No code change in this step. Possible follow-ups (Step 7 candidates, not done): a log line (DEBUG/INFO)
with the exception class at the `_raise_http` mapping; assertions of `actor_id`/`wishlist_id` in the
caplog tests.
