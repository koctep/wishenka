# WISHENKA-218: Observability Implementation

## Logging Implementation

### Added & Verified Logs

- **EMERG**: N/A — no emergency-level system failure paths introduced in this task.
- **ALERT**: N/A — no immediate operator-alert paths introduced in this task.
- **CRIT**: N/A — no critical-level failure paths introduced in this task.
- **ERR**: N/A — domain validation and outbox skip paths are handled at `WARNING`/`DEBUG`; unexpected storage/worker errors continue to use existing error handlers.
- **WARNING**:
  - `wishenka/wishlists/service.py` (`WishlistService.update_wish_item`, logger `wishenka.wishlists`):
    - `event="item_quantity_reduction_rejected"`: logged when `quantity < max(1, item.received_quantity)`. Includes `item_id`, `wishlist_id`, `actor_id`, `requested_quantity`, `received_quantity`, and `reason` (citing only `received_quantity`; never logs `reserved_quantity`, `locked_quantity`, or giver identities).
    - `event="item_quantity_overbooked"` (added): logged when `quantity_delta < 0` and `item.received_quantity + item.reserved_quantity > item.quantity`. Includes `item_id`, `wishlist_id`, `actor_id`, `quantity`, `quantity_delta`, and `notified_givers_count` (never logs `reserved_quantity`, giver IDs, names, or wish titles).
  - `wishenka/web/routes/items_ui.py` (`submit_edit_item`, logger `wishenka.web.items_ui`):
    - `event="ui_reduction_lock_rejected"`: logged when `CannotReduceQuantityBelowReservedError` is caught. Includes `wishlist_id`, `item_id`, `actor_id`, `user_id`, `requested_quantity`, and `received_quantity` (no `reserved_quantity` or `locked_quantity`).
- **NOTICE**: N/A — Python `logging` uses standard levels (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`).
- **INFO**:
  - `wishenka/wishlists/service.py` (`WishlistService.update_wish_item`, logger `wishenka.wishlists`):
    - `event="item_updated"`: logged after item update with `item_id`, `wishlist_id`, `actor_id`, `updated_fields`, `quantity`, `quantity_delta`.
  - `wishenka/web/routes/items_ui.py` (logger `wishenka.web.items_ui`):
    - `get_new_item_modal`: `event="ui_item_edit_opened"` with `wishlist_id`, `item_id=None`, `actor_id`, `user_id`, `mode="create"`, `is_collaborative` (no `received_quantity`, `reserved_quantity`, or `locked_quantity`).
    - `get_edit_item_modal`: `event="ui_item_edit_opened"` with `wishlist_id`, `item_id`, `actor_id`, `user_id`, `mode="edit"`, `received_quantity`, `is_collaborative` (no `reserved_quantity` or `locked_quantity`).
    - `submit_edit_item`: emits only `event="ui_item_edit_saved"` with `wishlist_id`, `item_id`, `actor_id`, `user_id`, `quantity`, `has_recipient` (it does not emit `ui_item_edit_opened`).
- **DEBUG**:
  - `wishenka/notices/reminders.py` (`claim_reminder`, `_normalize_row_locale`, loggers `wishenka.wishlists.notices`, `wishenka.notices.reminders`):
    - `event="service_notice_skipped"`: logged when an outbox row (including `item_quantity_overbooked`) is skipped. `reason="unauthorized"` when send-time authorization (`_event_authorized`) fails; `reason="ineligible"` when the destination, user preference, or title check fails. Includes only `outbox_id`, `kind`, and `reason` (no `user_id`, `chat_id`, wish title, or item title).
    - `event="notice_locale_resolved"`: logged with `channel`, `locale`, `fallback_used` (no PII).

### Log Structure

Log format used:
- Structured logs: yes (`extra={"event": ..., ...}` on all reviewed/added log records)
- Includes context: yes (`item_id`, `wishlist_id`, `actor_id`, `quantity`, `quantity_delta`, `received_quantity`, `notified_givers_count`, `outbox_id`, `kind`, `reason`)
- Log levels: `WARNING`, `INFO`, `DEBUG`

## Metrics Implementation (if applicable)

N/A — the repository uses structured `logging` events without a separate Prometheus/StatsD metrics backend. Operational counts (e.g. `item_quantity_overbooked`, `item_quantity_reduction_rejected`, `ui_reduction_lock_rejected`, `service_notice_skipped`) are derivable from structured log `event` fields.

## Monitoring Integration

Integration with monitoring systems:
- [ ] Prometheus metrics (N/A — not used in repository)
- [ ] Grafana dashboards (N/A)
- [ ] Alerting rules (N/A)
- [x] Log aggregation (structured `event` keys in `wishenka.wishlists`, `wishenka.web.items_ui`, `wishenka.wishlists.notices`, `wishenka.notices.reminders`)

## Validation Results

Validation results:
- [x] Logs are correctly formatted (`make analyze`: `ruff check`, `ruff format --check`, `mypy` clean)
- [x] Metrics are collected correctly (N/A — structured log events verified via `caplog`)
- [x] Logging works in error/refusal and overbooking scenarios (`tests/test_item_observability.py` for `item_quantity_reduction_rejected`/`item_quantity_overbooked`/`item_updated`; `tests/test_wish_items_tma_ui.py` for `ui_reduction_lock_rejected`/`ui_item_edit_opened`/`ui_item_edit_saved`; `tests/test_wishenka_60_observability.py` for `service_notice_skipped`; `tests/test_i18n_unit.py` asserts `notice_locale_resolved` (DEBUG level, `channel`, `locale`, `fallback_used`); for `service_notice_skipped` only the `ineligible` reason is test-covered, `unauthorized` is not)
- [x] Large data structures and PII/booking data are not logged (verified via `caplog` assertions: no `reserved_quantity`, `locked_quantity`, `givers`, giver IDs, or names)
- [x] Metrics are available for monitoring (structured `event` fields verified)

## Notes

- In `wishenka/wishlists/service.py`, `WishlistService.update_wish_item` previously queued `SharedEvent("item_quantity_overbooked", ...)` without emitting a dedicated structured log; added `logger.warning(..., extra={"event": "item_quantity_overbooked", ...})` and corresponding `caplog` assertions in `tests/test_item_observability.py`.
- Verified `wishenka/web/routes/items_ui.py` and `wishenka/notices/reminders.py` emit no `reserved_quantity`, `locked_quantity`, or PII in log messages or `extra` fields.
- `ai-tasks/WISHENKA-218/00-roadmap.md` has STEP 6 marked `[/]` (left for the orchestrator to mark `[x]` after review passes).
