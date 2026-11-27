# WISHENKA-266: Observability Implementation

## Logging Implementation

### Added Logs

An operator still sees the existing receipt-dialog request logs. This step
adds none. The change is the existing CSS pair on the receipt close button
(`background: var(--receipt-bg)` and `color: var(--receipt-text)` on
`.receipt-sheet .btn-modal-close` in `wishenka/web/static/miniapp.css`),
not a new server event. Product code was not edited.

The dialog request is already logged in two places that stay as they are:

- `RequestLoggingMiddleware` in `wishenka/web/app.py` (logger `wishenka.web`)
  writes `HTTP request completed: %s %s status=%d duration=%.2fms` for
  `GET /web/wishlists/{wishlist_id}/items/{item_id}/receipt`. Extras are
  `method`, `path`, `status_code`, and `duration_ms`. The path is the URL
  path only. The dialog HTML stays out of the record. The same middleware
  writes `HTTP request started: GET` at DEBUG before the handler runs.
- `get_receipt_dialog` in `wishenka/web/routes/receipts_ui.py` (logger
  `wishenka.web.receipts_ui`) writes INFO `Receipt dialog opened` with
  event `ui_receipt_form_opened` when the form opens. Extras are
  `wishlist_id`, `item_id`, and `actor_id`. A refusal of that same request
  stays the existing WARNING `Receipt refused` (`ui_receipt_form_refused`)
  with `reason` and `http_status`.

- **EMERG**: none
- **ALERT**: none
- **CRIT**: none
- **ERR**: none
- **WARNING**: none added. A refused dialog open still uses the existing
  WARNING above.
- **NOTICE**: none
- **INFO**: none added. The completed-request line and `Receipt dialog
  opened` are the existing receipt-dialog request logs.
- **DEBUG**: none added. Request start stays on `RequestLoggingMiddleware`.

### Log Structure

Log format used:

- Structured logs: yes, unchanged (`RequestLoggingMiddleware` extras on
  logger `wishenka.web`; receipt UI extras on `wishenka.web.receipts_ui`)
- Includes context: yes, unchanged (method, dialog path, HTTP status,
  duration in milliseconds; on the UI record, wishlist, wish, and actor
  ids). The dialog HTML stays out of the record.
- Log levels: `INFO`, `DEBUG`, and `WARNING` (existing). This step adds
  none.

## Metrics Implementation (if applicable)

This step adds none. Receipt-dialog requests stay visible on the existing
request logs named above.

### Performance Metrics

This step adds none. Dialog-request duration stays on `duration_ms` in
`RequestLoggingMiddleware`.

### Business Metrics

This step adds none. An opened receipt dialog stays the existing INFO
`Receipt dialog opened`.

### System Health Metrics

This step adds none.

## Monitoring Integration

Integration with monitoring systems:

- [ ] Prometheus metrics
- [ ] Grafana dashboards
- [ ] Alerting rules
- [ ] Log aggregation (ELK, Loki, etc.)

No integration is added. Existing receipt-dialog request logs are unchanged.

## Validation Results

Validation results:

- [x] Logs are correctly formatted — no new statement. Completed-request
  extras stay `method`, `path`, `status_code`, and `duration_ms`. The UI
  record stays `event`, `wishlist_id`, `item_id`, and `actor_id`.
- [x] Metrics are collected correctly — this step adds none
- [x] Logging works in error scenarios — a refused dialog open still goes
  through `get_receipt_dialog`, which writes the existing WARNING
  `Receipt refused`. The middleware still writes the completed-request
  INFO line for that response.
- [x] Large data structures are not logged — the dialog HTML is not added
  to any record
- [x] Metrics are available for monitoring — this step adds none; the
  existing request extras are unchanged

No production code changed in this step, so the suite was not re-run.

## Notes

The close control paints an existing stylesheet pair. Dismissing the sheet
does not emit a server event. An operator still sees the existing
receipt-dialog request logs, and this step adds none.
