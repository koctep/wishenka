# WISHENKA-220: Observability Implementation

## Logging Implementation

### Added Logs

No new log and no new metric. This task rewrote
`tests/test_receipt_modal_browser.py::test_unmarked_error_neither_shows_notice_nor_reloads`
so it observes the existing list notice. Production behavior is unchanged.
A second record of the same `ItemNotFoundError` / 404 would duplicate the
records below.

- **EMERG**: none
- **ALERT**: none
- **CRIT**: none
- **ERR**: none
- **WARNING**: none added. The missing-wish archive already records
  `ui_modal_domain_error` in `wishenka/web/routes/items_ui.py`
  (`_modal_domain_error_response`), called from `archive_item_ui` with
  `operation="archive_item"`. Logger `wishenka.web.items_ui`. Message
  `Modal archive_item failed with ItemNotFoundError (wishlist=..., item=..., status=404)`.
  Extras: `event`, `operation`, `error_type`, `status_code`,
  `wishlist_id`, `item_id`, `actor_id`, `user_id`. The notice sentence
  and the OOB HTML stay out of the record.
- **NOTICE**: none
- **INFO**: none added. `RequestLoggingMiddleware` in `wishenka/web/app.py`
  still logs method, path, status, and duration for
  `POST /web/wishlists/{wishlist_id}/items/{item_id}/archive`. A successful
  archive still uses `ui_item_archived`. This failure does not.
- **DEBUG**: none added. The same middleware still logs request start at
  DEBUG. `app.js` and the htmx stub emit no console record for this 404;
  `isError` is cleared so `htmx:responseError` does not fire.

### Log Structure

Log format used:

- Structured logs: yes, unchanged (`extra={"event": "ui_modal_domain_error"}`
  on `wishenka.web.items_ui`)
- Includes context: yes, unchanged (operation, error type, HTTP status,
  wishlist id, item id, actor id). The notice text and response body stay
  out of the record.
- Log levels: `WARNING` and `INFO` (existing). This step adds none.

## Metrics Implementation (if applicable)

No new metric. The project has no Prometheus, StatsD, or OpenTelemetry
export. The missing-wish count stays derivable from `ui_modal_domain_error`
with `operation=archive_item`, `error_type=ItemNotFoundError`, and
`status_code=404`.

### Performance Metrics

None added. Request duration stays on `RequestLoggingMiddleware`.

### Business Metrics

None added. `ui_modal_domain_error` remains the count for this 404.
`ui_item_archived` remains the successful-archive count.

### System Health Metrics

None.

## Monitoring Integration

Integration with monitoring systems:

- [ ] Prometheus metrics
- [ ] Grafana dashboards
- [ ] Alerting rules
- [ ] Log aggregation (ELK, Loki, etc.)

No integration is added. Existing structured logs are unchanged.

## Validation Results

Validation results:

- [x] Logs are correctly formatted — no new statement. Existing extras on
  `ui_modal_domain_error` are the closed set in
  `_modal_domain_error_response` (operation, error type, status, ids).
- [x] Metrics are collected correctly — no new metric
- [x] Logging works in error scenarios — `archive_item_ui` still catches
  `ItemNotFoundError` in `_DOMAIN_ERRORS` and passes it to
  `_modal_domain_error_response` before the 404 OOB notice. Step 3 already
  observed `Modal archive_item failed with ItemNotFoundError` and status
  404 on this path.
- [x] Large data structures are not logged — no notice sentence, dialog
  HTML, or response body was added
- [x] Metrics are available for monitoring — no new metric; the existing
  `ui_modal_domain_error` extras are unchanged

No production code changed in this step, so the browser node was not
re-run.

## Notes

The rewritten check watches the list notice, the closed dialog, card order,
and `window.__beforeReload`. It does not listen for `htmx:responseError`
and it does not assert a log line. Client-side logging of the 404 body
would duplicate `ui_modal_domain_error` and is out of scope.
