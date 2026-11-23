# WISHENKA-294: Observability Implementation

## Scope and Decision

Step 4 added one server-side behavior: an HTML unavailable page for GET 404/401 on
`/share/<token>`, `/web/wishlists/<id>`, `/web/reservations` (`wishenka/web/unavailable.py`).
All else is client presentation with no new endpoint.

Gap review: `RequestLoggingMiddleware` already logs method, masked path (`/share/{token}`),
status and duration for every render. It cannot tell an HTML unavailable page from the plain JSON
error on the same path and status, and it does not carry the locale or a route family
(`/web/wishlists/<id>` is also logged with its id). One INFO event was added for that gap.

## Logging Implementation

### Added Logs

- **INFO** `wishenka.web` (`unavailable.py`): `unavailable_page_rendered`, emitted once per HTML
  render. Fields: `event`, `status_code` (401/404), `route_kind` (`share`, `wishlist`,
  `reservations`), `locale`.
- **WARNING** `wishenka.web` (existing): locale lookup failure fallback with `exc_info`.
- Existing request completion logs are relied on for duration and status.

### Log Structure

- Structured logs: yes (`extra` rendered by `JsonFormatter`).
- Includes context: event, status, route kind, locale.
- Levels: INFO, WARNING. No token, wishlist id, title, user or reservation data is logged
  (surprise invariant holds). JSON, wildcard, htmx and non-page requests emit nothing new.

## Metrics Implementation

None. The project has no metrics exporter; the event and request logs are countable by
`event`/`status_code` in log aggregation.

## Monitoring Integration

- [ ] Prometheus metrics (not applicable)
- [ ] Grafana dashboards (not applicable)
- [ ] Alerting rules (not applicable)
- [ ] Log aggregation: filter `extra.event = "unavailable_page_rendered"`; watch share-404
  volume per day for broken or probed links (no alert threshold set).

## Validation Results

- [x] Logs are correctly formatted (rendered through `JsonFormatter` in the test)
- [x] Logging works in error scenarios (404/401 renders)
- [x] Large data and PII not logged (test asserts no token or id in the JSON line)
- [x] `tests/test_unavailable_page_observability.py` (2 tests, 30 s timeout): one event per
  HTML render with expected kind/status; JSON, wildcard, htmx and `/api` requests emit none.
- `make analyze`: clean. `make test-serial` on the new file plus
  `tests/test_cross_screen_comfort_browser.py`: 50 passed.
