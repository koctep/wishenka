# WISHENKA-296: Observability Implementation

## Scope and Decision

Logs only (D-7 of `20-architecture.md`; no metrics backend exists for this area). The flow after
the fix was reviewed path by path. **No production code was changed and no new event was added**;
the existing signals are sufficient and are now pinned by tests in
`tests/test_wishlist_create_observability.py` (11 tests, timeout 30).

## Logging Implementation

### Added Logs

None in production code. The following existing signals are pinned per path of `POST /api/wishlists`:

| Path | Status | Signals |
| ---- | ------ | ------- |
| Success | 201 | `wishlist_created` twice (INFO: service `wishenka.wishlists.service` and route `wishenka.web.wishlists`, the route record has `wishlist_id`, `user_id`); `wishlist_mutation_committed` once with `operation=create_wishlist` (the single-fire signal); request-completed INFO with `status_code=201` |
| Validation rejection (missing, null, blank, 256 chars, int, list) | 422 | request-completed INFO with `status_code=422` only; no creation event, no WARNING or higher |
| Unauthenticated | 401 | request-completed INFO with `status_code=401`; no creation event |
| CSRF (cookie session without Origin/token) | 403 | `csrf_origin_mismatch` WARNING (`path`, `origin`), existing middleware |
| Unexpected error | 500 | request middleware `HTTP request unhandled exception` ERROR (`method`, `path`, `duration_ms`); no creation event |

Abandoning or cancelling the form creates no request, so nothing is logged (by design).

### Log Structure

- Structured logs: yes (`extra` rendered by `JsonFormatter`).
- Context: `event`, `wishlist_id`, `user_id` (existing convention), `operation`, `status_code`, `path`.
- Never logged: the wishlist title, description, event title and tokens. The tests use an unusual
  title with quotes, accents and emoji and scan message, args, `vars()`, extras, the JSON line and
  the parsed JSON re-dumped with `ensure_ascii=False` (the formatter escapes non-ASCII, so a raw
  substring check alone would miss it) for every record.
- Logged by the service `wishlist_created` record (pre-existing, unchanged): `owner_id`,
  `format`, `time_type` and `event_date` (ISO value of the user-entered date). A date is of low
  sensitivity and is useful to diagnose date handling; the success test asserts exactly this and
  that the route record carries no date. Judged acceptable; see the Step 7 candidates below.

## Metrics Implementation

None. Counts are derivable: committed creations = `wishlist_mutation_committed` with
`operation=create_wishlist`; rejections = request-completed with `status_code=422` on
`POST /api/wishlists`.

## Monitoring Integration

- [ ] Prometheus / Grafana / alerting rules (not applicable)
- [x] Log aggregation: existing JSON logs; suggested query on 422 rate of `POST /api/wishlists`
  (a spike after a client release signals a form/validation regression).

## Validation Results

- [x] Logs are correctly formatted (every record formatted with `JsonFormatter` and parsed as JSON)
- [x] Logging works in error scenarios (422, 401, 403, 500 covered)
- [x] Large data structures are not logged
- [x] No titles, descriptions, event titles, tokens in any record (`event_date` is logged by the
  service record by design, see Log Structure)
- [x] `make analyze` clean; 36 tests green across `test_wishlist_create_observability.py` and
  `test_wishlist_create_validation_api.py`

## Notes

### Deviation from D-7

None. D-7 stated "no dedicated warning for 422" and "`wishlist_mutation_committed` is the
single-fire signal"; both are confirmed by tests (`wishlist_created` is asserted as two records
from two distinct loggers).

### Deliberately not added

- `wishlist_create_rejected` (user_id + reason enum): pydantic rejects before the route handler
  runs, so it would need a global `RequestValidationError` handler. The repo has none (only an
  HTTP exception handler in `wishenka/web/unavailable.py`; other 422s are visible only in the
  request-completed line), so a handler would be a new global behaviour touching every route and
  the 422 body shape. The 422 count is already available from the access line. A test asserts the
  event does not exist so adding it later is a conscious decision.
- Server-side logs of form abandonment/cancel (no request exists) and client telemetry.
- Changes to the duplicate `wishlist_created` (route vs service); alerting must count
  `wishlist_mutation_committed` or filter by logger.

### Step 7 debt candidates (low priority, optional)

- A global `RequestValidationError` log (reason enum, `user_id`, no input echo) if 422 rates ever
  need server-side diagnosis beyond the access line.
- `event_date` in the service `wishlist_created` extra is user-entered data in logs; drop it if a
  stricter no-user-input log policy is adopted.

### Step 8 follow-up (dev docs)

In the event table of `doc/dev/wishlists.md` note that `wishlist_created` is emitted twice per
creation (service and route logger) and that the single-fire signal is
`wishlist_mutation_committed` (`operation=create_wishlist`); document that 422 of creation has
no dedicated event (access line only).

### Validation notes

- "Logs are correctly formatted": ticked (JSON parse of all captured records).
- "Logging works in error scenarios": ticked (422, 401, 403, 500).
- "Large data structures are not logged": ticked (ids, enums, status only).
- "Metrics are collected / available": not applicable, no metrics backend.
