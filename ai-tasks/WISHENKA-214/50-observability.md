# WISHENKA-214: Observability Implementation

## Logging Implementation

### Added Logs

No new log and no new event. The change only moves the client claim of an
already-logged gift-receipt refusal. `receipt.js` sets `detail.skipSharedDialog`
in the capture phase and stops `htmx:responseError` for `X-Receipt-Refusal`.
`app.js` returns on that flag and on `[data-own-feedback]`. The server still
decides the refusal, still sends the same header and sentence, and still
writes the records below. A browser log would name the refusal or the
response body, and `tests/test_receipt_static_script.py` forbids `console.`
in `receipt.js`.

- **EMERG**: none
- **ALERT**: none
- **CRIT**: none
- **ERR**: none
- **WARNING**: none added. Existing refusal records stay:
  - `receipt_refused` and `ui_receipt_form_refused` —
    `wishenka/web/routes/receipts_ui.py` (`_log_refusal`). Message
    `Receipt refused`. Extras: `event`, `wishlist_id`, `item_id`,
    `actor_id`, `reason` (closed code), `http_status`, and
    `remaining_quantity` only for `quantity_above_remaining` and
    `nothing_remaining`.
  - `wish_archive_refused` — `wishenka/wishlists/service.py`
    (`_log_archive_refused`), called from
    `wishenka/wishlists/repo_ops.py` before `NothingRemainingError` on
    archive and restore. Message
    `Archive or restore refused: nothing remains`. Extras: `event`,
    `wishlist_id`, `item_id`, `actor_id`, `reason` =
    `nothing_remaining`. The UI route
    `wishenka/web/routes/items_ui.py` (`_nothing_remaining_response`)
    still adds no receipt-UI record; that silence is asserted by
    `tests/test_receipt_ui_observability.py`.
- **NOTICE**: none
- **INFO**: none added. Successful receipt and archive records
  (`receipt_recorded_http`, `ui_receipt_form_opened`, `ui_item_archived`)
  are unchanged. `RequestLoggingMiddleware` in `wishenka/web/app.py` still
  logs method, path, status, and duration for the same requests.
- **DEBUG**: none

### Log Structure

Log format used:

- Structured logs: yes, unchanged (`extra={"event": ...}` on
  `wishenka.web.receipts_ui` and `wishenka.wishlists`)
- Includes context: yes, unchanged (list, wish, and actor ids, closed
  reason, HTTP status). The refusal sentence, dialog HTML, wish title,
  and response body stay out of the record.
- Log levels: `WARNING` and `INFO` (existing). This step adds none.

## Metrics Implementation (if applicable)

No new metric. The project has no Prometheus, StatsD, or OpenTelemetry
export. Refusal counts stay derivable from the existing `event` and
`reason` fields.

### Performance Metrics

None added. Request duration stays on `RequestLoggingMiddleware`.

### Business Metrics

None added. `receipt_refused`, `ui_receipt_form_refused`, and
`wish_archive_refused` remain the refusal counts.

### System Health Metrics

None.

## Monitoring Integration

Integration with monitoring systems:

- [ ] Prometheus metrics
- [ ] Grafana dashboards
- [ ] Alerting rules
- [ ] Log aggregation (ELK, Loki, etc.)

No integration is added. Existing structured refusal logs are unchanged.

## Validation Results

Validation results:

- [x] Logs are correctly formatted — no new statement. Existing extras are
  the closed set in `tests/test_receipt_ui_observability.py` and
  `tests/test_receipt_observability.py` (`reason`, ids, status;
  `remaining_quantity` only for the two reasons that carry it).
- [x] Metrics are collected correctly — no new metric
- [x] Logging works in error scenarios — receipt refusals, including
  `nothing_remaining` and `idempotency_conflict`, still go through
  `_log_refusal`. Archive and restore of a fully received wish still go
  through `wish_archive_refused` before the client claim.
- [x] Large data structures are not logged — no response body, sentence,
  title, or header dump was added. `app.js` and `receipt.js` contain no
  `console.`
- [x] Metrics are available for monitoring — no new metric; the existing
  refusal extras are unchanged

No production code changed in this step, so
`tests/test_receipt_static_script.py` was not re-run.

## Notes

`detail.skipSharedDialog` and `data-own-feedback` are routing flags. They
do not create a new outcome, so they have no event of their own. Logging
the header value or `xhr.responseText` from the browser would put the
refusal body on the client and is out of scope. WISHENKA-220 and
WISHENKA-354 were left alone.
