# WISHENKA-161: Observability Implementation

## Logging Implementation

### Added Logs

No new log statements were added in WISHENKA-161, by design:

- **Backend (`wishenka/web/routes/receipts_ui.py`)**: WISHENKA-161 only adds `RECEIPT_SELECT_MAX = 20` and passes `"select_max": RECEIPT_SELECT_MAX` into `_dialog_html(...)`. All server-side receipt dialog open, refusal, busy, and mutation paths already emit structured logs via `wishenka.web.receipts_ui` (`_log`, `_log_refusal`: `ui_receipt_form_opened`, `ui_receipt_form_refused`, `receipt_recorded_http`, `receipt_refused`, `receipt_inventory_busy`) and `wishenka.web` HTTP request/response middleware (`wishenka/web/app.py`), with strict surprise-secrecy enforcement (no booking or giver data logged). The exact log schema is pinned by `tests/test_receipt_ui_observability.py::test_full_ui_flow_log_contract`.
- **Frontend (`wishenka/web/static/receipt.js`)**: All WISHENKA-161 changes are client-side DOM/accessibility behavior (background `inert`/`aria-hidden` isolation, `Tab`/`Shift+Tab` focus trap, focus return on dismissal/partial/full/refusal, `details.gifted-items-details` open-state preservation, and `[data-receipt-step]`/`[data-receipt-quantity]` stepper bounds). `tests/test_receipt_static_script.py::test_receipt_script_hygiene_and_wishlist_additions` explicitly forbids `console.*` in `receipt.js`.
- **Templates & CSS (`item_receipt_modal.html`, `receipt_edit_modal.html`, `receipt_cancel_modal.html`, `wishlist_detail.html`, `miniapp.css`)**: Declarative HTML attributes (`aria-modal="true"`, `tabindex="-1"`, stepper markup) and CSS rules; no runtime logging applicable.

Existing syslog-compatible levels in `wishenka/web/routes/receipts_ui.py`:
- **EMERG**: N/A (not used)
- **ALERT**: N/A (not used)
- **CRIT**: N/A (handled by application/middleware exception logging in `wishenka/web/app.py`)
- **ERR**: N/A (unhandled errors logged via `logger.exception` in `wishenka/web/app.py` request middleware)
- **WARNING**: `wishenka/web/routes/receipts_ui.py` (`_log_refusal`, `receipt_inventory_busy`) - receipt/dialog refusals and 503 busy states with `wishlist_id`, `item_id`, `actor_id`, `reason`, `http_status`
- **NOTICE**: N/A (Python `logging` uses `INFO`/`WARNING`)
- **INFO**: `wishenka/web/routes/receipts_ui.py` (`ui_receipt_form_opened`, `receipt_recorded_http`) - dialog open and receipt mutation events
- **DEBUG**: `wishenka/web/app.py` - request/response debug trace when `log_level=DEBUG`

### Log Structure

Log format used (existing `wishenka/logging.py` `JsonFormatter` / stream formatter):
- Structured logs: yes (`JsonFormatter` when `json_logs=True`, key-value `extra` dict)
- Includes context: yes (`event`, `wishlist_id`, `item_id`, `actor_id`, and refusal `reason`/`http_status`)
- Log levels: `INFO`, `WARNING` (in `receipts_ui.py`), `ERROR`/`DEBUG` (in `wishenka/web/app.py` middleware)

## Metrics Implementation (if applicable)

N/A — The repository does not use a metrics library (e.g., Prometheus/OpenTelemetry). HTTP request duration and status codes for `/web/wishlists/{wishlist_id}/items/{item_id}/receipt` are recorded by the request logging middleware in `wishenka/web/app.py`. Client-side accessibility/focus/stepper interactions do not introduce server metrics.

### Performance Metrics

- **Response time**: Logged per HTTP request by `wishenka/web/app.py` middleware (existing)
- **Throughput**: N/A (no Prometheus counter)
- **Error rate**: HTTP status codes logged per request and refusal reason logged at `WARNING` in `wishenka/web/routes/receipts_ui.py` (existing)

### Business Metrics

- Receipt dialog opens (`ui_receipt_form_opened`) and recorded receipts (`receipt_recorded_http`) are emitted as structured log events in `wishenka/web/routes/receipts_ui.py` (existing).

### System Health Metrics

- **Resource usage**: N/A (outside WISHENKA-161 scope)
- **Component status**: `/healthz` endpoint in `wishenka/web/app.py` (existing)

## Monitoring Integration

Integration with monitoring systems:
- [ ] Prometheus metrics (N/A — not used in repository)
- [ ] Grafana dashboards (N/A — not used in repository)
- [ ] Alerting rules (N/A — not used in repository)
- [x] Log aggregation (structured JSON logs via `wishenka/logging.py` `JsonFormatter` ready for stdout log aggregation)

## Validation Results

Validation results:
- [x] Logs are correctly formatted (verified via `.venv/bin/pytest tests/test_receipt_ui_observability.py` — 1 passed)
- [x] Metrics are collected correctly (N/A — no metrics library in repo; HTTP timing middleware unchanged)
- [x] Logging works in error scenarios (verified via `tests/test_receipt_ui_observability.py` and `tests/test_receipt_ui_routes.py`)
- [x] Large data structures are not logged (verified: only scalar IDs and refusal reason/status are logged; surprise secrecy preserved)
- [x] Metrics are available for monitoring (N/A — stdout structured logs available for aggregation)
- [x] `receipt.js` hygiene constraint preserved (no `console.*` calls, verified against `tests/test_receipt_static_script.py`)

## Notes

- Because WISHENKA-161 is a UI accessibility, focus management, and quantity-stepper enhancement (`RECEIPT_SELECT_MAX = 20` + `receipt.js` + templates/CSS) and `tests/test_receipt_static_script.py` forbids `console.*` in `receipt.js`, keeping existing backend structured logging untouched preserves both `test_receipt_ui_observability.py` and `test_receipt_static_script.py` invariants without adding noisy or forbidden client-side logs.
