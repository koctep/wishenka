# WISHENKA-80: Observability Implementation

## Logging Implementation

### Added Logs

Audited and updated structured logging across `wishenka/web/dependencies.py`, `wishenka/wishlists/repository.py`, `wishenka/wishlists/repo_ops.py`, and `wishenka/web/routes/{wishlists,items,items_ui,receipts,receipts_ui,sharing}.py`:

- **ERR**:
  - `wishenka/web/dependencies.py:get_wishlist_store` — logs `wishlist_store_uninitialized` when `app.state.wishlist_store` is missing or invalid before raising `RuntimeError`.
  - `wishenka/web/dependencies.py:get_wishlist_repository` — logs `wishlist_store_error` with `error_type` (exception class name only, without `exc_info` or SQL bound parameters) on `SQLAlchemyError` so capability tokens are never leaked into tracebacks.
- **WARNING**:
  - `wishenka/wishlists/repo_ops.py:join_by_invite` — logs `wishlist_invite_join_failed` with `user_id`, `reason` (`not_found` or `expired`), and `wishlist_id` (when known) without logging `invite_token`.
  - `wishenka/wishlists/repo_ops.py:regenerate_public_token` — logs `public_token_rotate_denied` with `wishlist_id` and `actor_id`.
  - `wishenka/wishlists/repo_ops.py:regenerate_invite_token` — logs `invite_token_rotate_denied` with `wishlist_id` and `actor_id`.
- **INFO**:
  - `wishenka/wishlists/repository.py:rotate_public_token` — logs `wishlist_repo_mutation` (`entity="wishlist_public_token"`, `operation="rotate"`, `entity_id=wishlist_id`) without logging `new_token`.
  - `wishenka/wishlists/repository.py:rotate_invite_token` — logs `wishlist_repo_mutation` (`entity="wishlist_invite_token"`, `operation="rotate"`, `entity_id=wishlist_id`, `has_expiry`) without logging `new_token`.
  - `wishenka/wishlists/repository.py:cancel_wishlist_reservations` — logs `wishlist_repo_mutation` (`entity="reservation"`, `operation="cancel_for_wishlist"`, `wishlist_id`, `cancelled_count`).
  - `wishenka/wishlists/repo_ops.py:join_by_invite` — logs `wishlist_member_joined` (`wishlist_id`, `user_id`) on new collaborator join.
  - `wishenka/wishlists/repo_ops.py:regenerate_public_token` — logs `public_token_rotated` (`wishlist_id`, `actor_id`) without logging `new_token`.
  - `wishenka/wishlists/repo_ops.py:regenerate_invite_token` — logs `invite_token_rotated` (`wishlist_id`, `actor_id`) without logging `new_token`.
  - `wishenka/web/routes/sharing.py:view_public_share` — fixed `is_recipient` calculation for `wishlist_shared_view` so anonymous guests (`current_user is None`) log `is_recipient=False` rather than inheriting the DTO's `anonymous_safe` `WishItemRecipientViewDTO.is_recipient=True` marker.

### Existing Verified Logs (Audited, No Changes Needed)

- `wishenka/web/routes/wishlists.py` — `wishlist_mutation_committed`, `wishlist_store_error`, `wishlist_retention_expired`, `wishlist_permission_denied`, `wishlist_archived_mutation_blocked`, `wishlist_access_denied`, `favorite_own_wishlist_denied`, `favorite_deleted_wishlist_denied`.
- `wishenka/web/routes/items.py` — `item_inventory_busy`, `item_not_found`, `item_permission_denied`, `item_conflict`, `item_validation_error`.
- `wishenka/web/routes/items_ui.py` — `ui_modal_domain_error` and item UI mutation/refusal logs.
- `wishenka/web/routes/receipts.py` — `receipt_refused`, `receipt_inventory_busy`, `receipt_idempotency_conflict`, and receipt completion logs.
- `wishenka/web/routes/receipts_ui.py` — `_log` / `_log_refusal` structured UI events with `(wishlist_id, item_id, actor_id)` and closed refusal reasons.

### Log Structure

Log format used:
- Structured logs: yes (`wishenka.logging.JsonFormatter` in production / `extra={...}` dict with `"event"` key)
- Includes context: yes (`wishlist_id`, `item_id`, `actor_id` / `user_id`, `operation`, `entity`, `reason`, `error_type`, counts)
- Log levels: `ERROR`, `WARNING`, `INFO` (and `DEBUG` in `RequestLoggingMiddleware`)

## Metrics Implementation (if applicable)

### Performance Metrics

- **Response time**: `duration_ms` logged on every HTTP request by `wishenka/web/app.py:RequestLoggingMiddleware`.
- **Throughput / Error rate**: derivable from `RequestLoggingMiddleware` structured `status_code` and `path` (with `/share/{token}` and `/invite/{token}` sanitized). No separate Prometheus/OpenTelemetry metrics backend is configured in this repository.

## Monitoring Integration

Integration with monitoring systems:
- [ ] Prometheus metrics (N/A — repository uses structured JSON logs via `wishenka.logging.JsonFormatter`)
- [ ] Grafana dashboards (N/A)
- [ ] Alerting rules (N/A)
- [x] Log aggregation (structured JSON lines via `JsonFormatter` with `event` and entity IDs)

## Validation Results

Validation results:
- [x] Logs are correctly formatted (`ruff check`, `ruff format --check`, `mypy` passed on all modified files)
- [x] Metrics are collected correctly (`RequestLoggingMiddleware` `duration_ms` / `status_code` intact)
- [x] Logging works in error scenarios (`tests/test_web_repository_di_repro.py` + `tests/*observability*.py`: 134/134 passed)
- [x] Large data structures and secrets/tokens are not logged (verified no `public_token`, `invite_token`, or SQL bound params in log payloads)

## Notes

- Fixing `is_recipient` in `wishenka/web/routes/sharing.py:view_public_share` resolved the pre-existing `test_wishlist_shared_view_observability` failure in `tests/test_wishlists_htmx_observability.py`.
