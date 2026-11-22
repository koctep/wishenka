# WISHENKA-292: Observability Implementation

## Scope and Decision

The history screen is client-side and uses existing endpoints `GET /api/history`,
`POST /api/history/{id}` and `DELETE /api/history`. They already log each flow with structured
`extra` fields. One real gap was found and closed: the clear event did not say how many entries
it removed, which matters now that Clear is a deliberate, confirmed action. No route, endpoint or
metric was added.

## Logging Implementation

### Existing logs relied on

- **INFO** `wishenka/wishlists/service.py` and `wishenka/web/routes/wishlists.py`:
  `view_history_recorded` (`wishlist_id`, `user_id`), `view_history_listed` (`user_id`, `count`).
- **WARNING** `favorite_deleted_wishlist_denied`: recording a view of a deleted list (the 404 path
  of the open-entry flow).
- `wishenka/web/app.py` request logging (method, masked path, status, elapsed ms) covers every
  call, including 404 and failures.

### Added

- **INFO** `view_history_cleared` in `WishlistService.clear_history` now carries
  `removed_count` (and `removed=N` in the message). Value is a count only.
- The duplicate route-level `view_history_cleared` in `DELETE /api/history` was removed, so
  exactly one event (logger `wishenka.wishlists`, with `removed_count`) exists per request.

### Out of scope (pre-existing)

- Route and service both log `view_history_recorded`, `view_history_listed` and
  `favorite_deleted_wishlist_denied`. This double logging pre-exists and was not changed
  (candidate tech debt).

### Log Structure

- Structured: yes (`extra` rendered by `JsonFormatter`).
- Context: event name, internal `user_id`, `wishlist_id`, counts.
- No wishlist titles, descriptions, tokens or other users' data are logged.
- Client side: the screen shows loading, error with Retry, and clear feedback. The project has no
  client telemetry convention, so none was added.

## Metrics Implementation

None. The project has no metrics exporter for these paths; request logs carry status and
duration.

## Monitoring Integration

- [ ] Prometheus, Grafana, alerting (not applicable)
- [ ] Log aggregation (existing infrastructure unchanged)

## Validation Results

- [x] Extended contract `test_view_history_lifecycle_observability` in
  `tests/test_wishlist_sections_observability.py` (caplog, any logger): exactly one
  `view_history_cleared` record with `removed_count == 1`, message has no list title.
- [x] Recorded and listed events were already pinned by the same test.
- [x] `make test` on `tests/test_wishlist_sections_observability.py`, `tests/test_observability.py`,
  `tests/test_wishlist_management_observability.py`, `tests/test_history_screen_browser.py`:
  51 passed. `make analyze` clean.
