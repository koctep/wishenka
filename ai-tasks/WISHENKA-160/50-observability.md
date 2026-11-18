# WISHENKA-160: Observability Implementation

## Logging Implementation

### Added Logs

Added structured `WARNING` logs in `wishenka/web/routes/items_ui.py` (logger `wishenka.web.items_ui`) for modal and quick-add 4xx error paths introduced/updated in WISHENKA-160, complementing existing `ui_item_edit_busy` (503) and `ui_reduction_lock_rejected` (409) warnings:

- **WARNING**: `wishenka/web/routes/items_ui.py` (`_modal_domain_error_response`) — `event: "ui_modal_domain_error"`. Emitted when modal/UI endpoints (`quick_add`, `new_item_modal`, `edit_item_modal`, `submit_edit_item`, `archive_confirm`, `archive_item`) encounter `WishlistArchivedError` (409) or missing/deleted/forbidden resource errors (404). Includes `operation`, `error_type`, `status_code`, `wishlist_id`, `item_id`, `actor_id`, and `user_id`.
- **WARNING**: `wishenka/web/routes/items_ui.py` (`submit_edit_item`) — `event: "ui_item_edit_validation_error"`. Emitted on 400 validation failures (`stage: "form"` for empty title / parse errors, `stage: "domain"` for domain `ValueError`). Includes `stage`, `status_code`, `wishlist_id`, `item_id`, `actor_id`, and `user_id`.
- **WARNING**: `wishenka/web/routes/items_ui.py` (`quick_add_item`) — `event: "ui_item_quick_add_validation_error"`. Emitted on 400 validation failures (`reason: "empty_title" | "parse_error" | "domain_validation"`). Includes `reason`, `status_code`, `wishlist_id`, `actor_id`, and `user_id`.

Existing preserved logs on modal paths:
- **WARNING**: `wishenka/web/routes/items_ui.py` (`submit_edit_item`) — `event: "ui_item_edit_busy"` (503 `InventoryBusyError`) and `event: "ui_reduction_lock_rejected"` (409 `CannotReduceQuantityBelowReservedError`).
- **INFO**: `ui_item_edit_opened`, `ui_reduction_lock_rendered`, `ui_item_edit_saved`, `ui_item_archive_confirm_opened`, `ui_item_archived`, `ui_item_quick_add_success`.

### Log Structure

Log format used:
- Structured logs: **yes** (Python `logging` `extra` dict with `event` key and typed IDs/codes)
- Includes context: **yes** (`wishlist_id`, `item_id`, `actor_id`, `user_id`, `status_code`, `operation` / `stage` / `reason`, `error_type`)
- Log levels: `INFO`, `WARNING` (syslog-compatible)
- Privacy & payload safety: User-entered form strings (`title`, `price`, `raw_input`, `description`, `link`, `recipient_name`) and gifter identities are never logged.

## Metrics Implementation (if applicable)

Not applicable — the repository does not use a Prometheus/OpenTelemetry metrics backend; observability is implemented via structured logging.

## Validation Results

- [x] `make analyze` (`ruff check`, `ruff format --check`, `mypy`) passed across 201 source files.
- [x] Observability & modal tests (`tests/test_wishenka_160_observability.py`, `tests/test_item_modals_repro.py`, `tests/test_item_busy_responses.py`) — `15 passed in 45.00s`.
- [x] Large data structures and user form payloads are not logged (verified by `test_edit_validation_error_logs_structured_warning_without_payload`).

## Notes

- Client-side `htmx:beforeSwap` in `wishenka/web/templates/base.html` only enables swapping for HTML 4xx/5xx responses targeting `#item-modal-container` / `#item-edit-sheet` / `#item-archive-modal` (excluding `X-Reorder-Refusal`, `X-Receipt-Refusal`, and `/reservations`), so server-side structured warnings remain the authoritative audit trail for modal failures.
