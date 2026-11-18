# WISHENKA-153: Observability Implementation

## Logging Implementation

### Added and Verified Logs

- **INFO** (`wishenka/wishlists/service.py`, `cancel_item_receipt`): logs `event="receipt_cancelled"` with `wishlist_id`, `item_id`, `receipt_id`, `user_id`, `actor_id`, `received_quantity`, and `total_quantity`.
- **INFO** (`wishenka/wishlists/service.py`, `correct_item_receipt`): logs `event="receipt_corrected"` with `wishlist_id`, `item_id`, `receipt_id`, `user_id`, `actor_id`, `old_quantity`, `new_quantity`, `received_quantity`, and `total_quantity`.
- **INFO** (`wishenka/web/routes/receipts.py`, `cancel_receipt` & `correct_receipt`): logs `event="receipt_cancelled_http"` and `event="receipt_corrected_http"` with `item_id` and `receipt_id`.
- **INFO** (`wishenka/web/routes/receipts_ui.py`, `_open_receipt_entry_modal` & `_execute_receipt_mutation_ui` — added in Step 6):
  - `_open_receipt_entry_modal`: logs `event="ui_receipt_entry_form_opened"` with `wishlist_id`, `item_id`, `actor_id`, `receipt_id` when the edit/cancel modal opens cleanly.
  - `_execute_receipt_mutation_ui`: logs `event="receipt_corrected_http"` or `event="receipt_cancelled_http"` with `wishlist_id`, `item_id`, `actor_id`, `receipt_id` on both idempotent replay/execution and normal execution.
- **WARNING** (`wishenka/wishlists/service.py`, `_validate_receipt_mutation_access`; `wishenka/web/routes/receipts.py`, `_run`/`_refusal`/`_busy`; `wishenka/web/routes/receipts_ui.py`, `_open_receipt_entry_modal`/`_execute_receipt_mutation_ui`):
  - `access_denied` on non-member receipt mutation attempts.
  - `receipt_refused` / `ui_receipt_entry_form_refused` with `reason`, `http_status`, `wishlist_id`, `item_id`, `actor_id` (and `remaining_quantity` only when `QuantityAboveRemainingError` or `NothingRemainingError`).
  - `receipt_inventory_busy` on `InventoryBusyError` (503) and `receipt_idempotency_conflict` / `receipt_refused` (`idempotency_conflict`) on `IdempotencyConflictError` (409).
- **DEBUG** (`wishenka/wishlists/store.py`, `_log_flushed_shared_events`; `wishenka/notices/reminders.py`, `claim_reminder`):
  - `shared_notice_events_queued` (`kind` = `receipt_reverted` / `receipt_increased`, `queued_count`) after commit without exposing giver IDs.
  - `service_notice_skipped` (`outbox_id`, `kind`, `reason`) when a reminder is skipped during claim.

### Privacy & Surprise Invariants

- Verified that none of the service, store, JSON API, or UI logs include promise existence, giver identities, recipient identities, booked quantities, or `free_quantity`.

### Log Structure

- Structured logs: **yes** (`extra={...}` dict with `event` and scalar IDs/counts)
- Includes context: **yes** (`wishlist_id`, `item_id`, `receipt_id`, `actor_id`/`user_id`, `reason`, `http_status`)
- Log levels: `INFO`, `WARNING`, `DEBUG` (standard Python `logging` levels matching existing repository conventions)

## Metrics Implementation (if applicable)

- N/A — per `10-requirements.md` ("Out of scope: New metrics exporters (WISHENKA-84)"), no Prometheus/Grafana metrics exporter is used in this repository.

## Monitoring Integration

- [ ] Prometheus metrics (N/A — out of scope, deferred to WISHENKA-84)
- [ ] Grafana dashboards (N/A)
- [ ] Alerting rules (N/A)
- [x] Log aggregation (structured `extra` fields on `wishenka.wishlists`, `wishenka.wishlists.notices`, `wishenka.web.receipts`, `wishenka.web.receipts_ui`)

## Validation Results

- [x] Logs are correctly formatted
- [ ] Metrics are collected correctly (N/A — no metrics exporter in scope)
- [x] Logging works in error scenarios (`receipt_refused`, `ui_receipt_entry_form_refused`, `receipt_inventory_busy`, `access_denied`)
- [x] Large data structures are not logged (only scalar IDs, counts, and event/reason strings)
- [ ] Metrics are available for monitoring (N/A)

## Notes

- In Step 6, `wishenka/web/routes/receipts_ui.py` was updated to emit `INFO` logs (`ui_receipt_entry_form_opened`, `receipt_corrected_http`, `receipt_cancelled_http`) on success paths in `_open_receipt_entry_modal` and `_execute_receipt_mutation_ui`, bringing edit/cancel UI routes to parity with `get_receipt_dialog` and `record_receipt_ui`.
