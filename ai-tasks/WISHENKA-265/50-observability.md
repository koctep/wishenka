# WISHENKA-265: Observability Implementation

## Logging Implementation

### Added Logs

No new logs or metrics. The change is client-side in
`wishenka/web/static/app.js`: the card fetch still calls
`response.text()` for every status, then `window.swapWishCard(card, markup)`.
`wishlist.js` replaces a body that is not the same `.item-card` with one
`p.item-card-unavailable` paragraph. `app.js` has no `console` call. A
missing wish is already visible as HTTP 404 on the card route.

- **EMERG**: none
- **ALERT**: none
- **CRIT**: none
- **ERR**: none
- **WARNING**: none. `get_item_card_partial` in
  `wishenka/web/routes/sharing.py` raises `HTTPException` 404 with detail
  `Item not found` when the wish is absent from the giver view. That
  handler writes no logger call of its own.
- **NOTICE**: none
- **INFO**: none added. `RequestLoggingMiddleware` in `wishenka/web/app.py`
  (`wishenka.web`) already logs a completed card refresh, including a
  missing wish. Message:
  `HTTP request completed: %s %s status=%d duration=%.2fms`
  for `GET /wishlists/{wishlist_id}/items/{item_id}/card` with status 404.
  Extras: `method`, `path`, `status_code`, `duration_ms`. The path is the
  URL path only (numeric wishlist and item ids). The JSON body and the
  neutral sentence stay out of the record. The same middleware logs a
  still-available refresh as `status=200`.
- **DEBUG**: none added. The same middleware still logs
  `HTTP request started: GET` plus method and path before the handler
  runs.

### Log Structure

Log format used:

- Structured logs: yes, unchanged (`RequestLoggingMiddleware` extras on
  logger `wishenka.web`)
- Includes context: yes, unchanged (method, card path, HTTP status,
  duration in milliseconds). The response body, the neutral sentence,
  and the query string stay out of the record.
- Log levels: `INFO` and `DEBUG` (existing). This step adds none.

## Metrics Implementation (if applicable)

No new metric. The project has no Prometheus, StatsD, or OpenTelemetry
export. A missing-card refresh is the existing INFO line with
`status_code` 404 on
`GET /wishlists/{wishlist_id}/items/{item_id}/card`. A still-available
refresh is the same line with `status_code` 200.

### Performance Metrics

None added. Card-refresh duration stays on `duration_ms` in
`RequestLoggingMiddleware`.

### Business Metrics

None added. Count missing-card refreshes from that INFO line where
`status_code` is 404. Count successful card refreshes from the same
line where `status_code` is 200.

### System Health Metrics

None.

## Monitoring Integration

Integration with monitoring systems:

- [ ] Prometheus metrics
- [ ] Grafana dashboards
- [ ] Alerting rules
- [ ] Log aggregation (ELK, Loki, etc.)

No integration is added. Existing request logs are unchanged.

## Validation Results

Validation results:

- [x] Logs are correctly formatted — no new statement. The completed-request
  extras stay `method`, `path`, `status_code`, and `duration_ms`.
- [x] Metrics are collected correctly — no new metric
- [x] Logging works in error scenarios — `get_item_card_partial` returns
  the 404 response through the route, so `call_next` completes and the
  middleware writes the INFO line with `status_code` 404. The unhandled
  exception path is a different record and does not run for this
  `HTTPException`.
- [x] Large data structures are not logged — the card JSON, the card
  HTML, and the neutral sentence are not added to any record
- [x] Metrics are available for monitoring — no new metric; the existing
  request extras are unchanged

No production code changed in this step, so the suite was not re-run.
`tests/test_observability.py::test_request_logging_and_lifespan` already
asserts that `RequestLoggingMiddleware` emits `HTTP request completed`.

## Notes

The giver card fetch has no client log. An operator sees a missing wish
on the server INFO line for that GET with status 404, so this step adds
no second record. `app.js` was not edited and still has no `receipt`
substring.
