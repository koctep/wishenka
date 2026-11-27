# WISHENKA-264: Observability Implementation

## Logging Implementation

### Added Logs

No new logs or metrics. This task only aligns the eight archive nodes in
`tests/test_items_ui_error_mapping.py` with the HTML list notice. Both
archive actions already return that notice from
`_modal_domain_error_response`, and that helper already records the refusal.

- **EMERG**: none
- **ALERT**: none
- **CRIT**: none
- **ERR**: none
- **WARNING**: none added. `wishenka/web/routes/items_ui.py`
  (`_modal_domain_error_response`) logs `ui_modal_domain_error` on logger
  `wishenka.web.items_ui`. Message:
  `Modal %s failed with %s (wishlist=%s, item=%s, status=%s)`.
  Extras: `event`, `operation`, `error_type`, `status_code`, `wishlist_id`,
  `item_id`, `actor_id`, `user_id`. The notice sentence and the OOB HTML
  stay out of the record.
  - `archive_confirm_ui` calls it with `operation="archive_confirm"`.
  - `archive_item_ui` calls it with `operation="archive_item"`.
  - `WishlistArchivedError` is status 409 (archived wishlist).
  - `WishlistNotFoundError`, `PermissionDeniedError`, and
    `ItemNotFoundError` are status 404 (unknown wishlist, non-member,
    unknown wish). `WishlistDeletedError` uses the same 404 record.
- **NOTICE**: none
- **INFO**: none added. A refusal returns before
  `ui_item_archive_confirm_opened` and `ui_item_archived`.
  `RequestLoggingMiddleware` in `wishenka/web/app.py` still logs method,
  path, status, and duration for
  `GET /web/wishlists/{wishlist_id}/items/{item_id}/archive-confirm` and
  `POST /web/wishlists/{wishlist_id}/items/{item_id}/archive`, including
  status 404 and 409.
- **DEBUG**: none added. The same middleware still logs request start at
  DEBUG.

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
export. Archive refusal counts stay derivable from `ui_modal_domain_error`
with `operation` `archive_confirm` or `archive_item`, `status_code` 409 or
404, and the matching `error_type`.

### Performance Metrics

None added. Request duration stays on `RequestLoggingMiddleware`.

### Business Metrics

None added. `ui_modal_domain_error` remains the count for these 404 and 409
refusals. `ui_item_archive_confirm_opened` and `ui_item_archived` remain
the successful-path counts.

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
- [x] Logging works in error scenarios — both archive handlers catch
  `_DOMAIN_ERRORS` and pass the exception to
  `_modal_domain_error_response` before the OOB notice.
  `tests/test_wishenka_160_observability.py::test_modal_domain_errors_log_structured_warning`
  already asserts this WARNING for `archive_item` / `ItemNotFoundError` /
  status 404 and for a 409 `WishlistArchivedError` on the same helper.
- [x] Large data structures are not logged — no notice sentence, dialog
  HTML, or response body was added
- [x] Metrics are available for monitoring — no new metric; the existing
  `ui_modal_domain_error` extras are unchanged

No production code changed in this step, so the suite was not re-run.

## Notes

The eight nodes in `tests/test_items_ui_error_mapping.py` assert status,
`text/html`, the Russian catalog sentence in `#list-notice`, and an empty
`#item-modal-container`. They do not assert a log line. A second record of
the same refusal would duplicate `ui_modal_domain_error`.
