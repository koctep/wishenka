# WISHENKA-63: Observability Implementation

## Logging Implementation

### Added Logs

Describe added logging:
- **EMERG**: N/A - no system-wide emergency events introduced in this change.
- **ALERT**: N/A - no immediate external alert events introduced in this change.
- **CRIT**: N/A - no critical infrastructure failure events introduced in this change.
- **ERR**: `WishlistService.__init__` in `wishenka/wishlists/service.py` - emits `wishlist_service_store_required` on `wishenka.wishlists` when `WishlistService` is constructed with `store=None` without going through `WishlistService.in_memory()`, immediately before raising `ValueError`.
- **WARNING**:
  - `WishlistService.get_wishlist_by_public_token` in `wishenka/wishlists/service.py` - emits `public_token_not_found` and `deleted_wishlist_access_attempt` (with `wishlist_id`) on `wishenka.wishlists` without logging the capability token.
  - `public_wishlist` (`GET /api/public/wishlists/{token}`) and `public_wishlist_view` (`GET /api/public/wishlists/{token}/view`) in `wishenka/web/routes/wishlists.py` - emit `public_wishlist_not_found` and `public_entry_unavailable` on `wishenka.web.wishlists` without logging the public token.
  - `view_public_share` (`GET /share/{public_token}`) in `wishenka/web/routes/sharing.py` - emits `wishlist_shared_view_failed` on `wishenka.web.sharing` when public token lookup fails.
- **NOTICE**: N/A - Python standard `logging` maps significant operational notifications to `INFO`.
- **INFO**:
  - `WishlistService.get_wishlist_by_public_token` in `wishenka/wishlists/service.py` - emits `public_wishlist_resolved` on `wishenka.wishlists` with `wishlist_id`, `identified` (`bool`), `user_id` (`int | None`), `projection_mode` (`"anonymous_safe"`, `"recipient_safe"`, or `"gifter"`), and `items_count` (`int`).
  - `public_wishlist` and `public_wishlist_view` in `wishenka/web/routes/wishlists.py` - emit `public_wishlist_viewed` (`wishlist_id`) and `public_entry_viewed` (`wishlist_id`, `identified`) on `wishenka.web.wishlists`.
  - `view_public_share` in `wishenka/web/routes/sharing.py` - emits `wishlist_shared_view` (`wishlist_id`, `is_recipient`, `is_collaborative`) on `wishenka.web.sharing`.
- **DEBUG**:
  - `WishlistService.in_memory` in `wishenka/wishlists/service.py` - emits `wishlist_service_in_memory_created` on `wishenka.wishlists` when an explicit in-memory service instance is created for isolated tests or `WishlistStore` transactional hydration.
  - `WishlistService.get_wishlist_view` in `wishenka/wishlists/service.py` - emits `wishlist_view_projected` on `wishenka.wishlists` with `wishlist_id`, `user_id`, `role`, `items_count`, and `archived_items_count`.

### Log Structure

Log format used:
- Structured logs: yes (`extra={"event": ..., ...}` compatible with JSON and key-value formatters in `wishenka/logging.py`)
- Includes context: yes (`wishlist_id`, `identified`, `user_id`, `projection_mode`, `items_count`, `archived_items_count`, `is_recipient`, `is_collaborative`)
- Log levels: `ERR` (`ERROR`), `WARNING`, `INFO`, `DEBUG`

## Metrics Implementation (if applicable)

### Performance Metrics

Added performance metrics:
- **Response time**: `duration_ms` emitted by HTTP request logging middleware in `wishenka/web/app.py` (with redacted `/share/[REDACTED]` and `/api/public/wishlists/[REDACTED]` paths).
- **Throughput**: Request and projection counts derived from `public_wishlist_resolved`, `public_wishlist_viewed`, `public_entry_viewed`, and `wishlist_shared_view` structured events.
- **Error rate**: Failure and boundary-violation counts derived from `wishlist_service_store_required`, `public_token_not_found`, `public_wishlist_not_found`, `public_entry_unavailable`, and `wishlist_shared_view_failed`.

### Business Metrics

Business metrics:
- `public_wishlist_resolved` (`projection_mode` dimension): tracks the distribution of public-link resolutions across `anonymous_safe`, `recipient_safe`, and `gifter` projection modes in `wishenka/wishlists/service.py`.

### System Health Metrics

System health metrics:
- **Resource usage**: N/A - no new process resource collectors added in this task.
- **Component status**: `wishlist_service_store_required` (`ERROR`) detects any misconfigured component attempting to instantiate `WishlistService` without persistent `WishlistStore` backing in `wishenka/wishlists/service.py`.

## Monitoring Integration

Integration with monitoring systems:
- [ ] Prometheus metrics
- [ ] Grafana dashboards
- [ ] Alerting rules
- [x] Log aggregation (ELK, Loki, etc.) via structured JSON/extra fields in `wishenka/logging.py`

## Validation Results

Validation results:
- [x] Logs are correctly formatted
- [x] Metrics are collected correctly
- [x] Logging works in error scenarios (`wishlist_service_store_required` on `WishlistService()` / `WishlistService(store=None)`, `public_token_not_found` on invalid public token)
- [x] Large data structures are not logged (only scalar identifiers, counts, booleans, and `projection_mode` enum strings are logged)
- [x] Metrics are available for monitoring (structured event names and dimensions verified via `caplog` in `tests/test_wishenka_63_repro.py`)

## Notes

- **Secret and Capability-Token Redaction**: Public share tokens (`public_token`), collaboration invite tokens (`invite_token`), and unknown lookup tokens are never interpolated into log messages or `extra` dictionaries in `WishlistService.get_wishlist_by_public_token`, `public_wishlist`, `public_wishlist_view`, or `view_public_share`. `test_public_projection_observability_logs_without_leaking_tokens` in `tests/test_wishenka_63_repro.py` asserts zero occurrences of `public_token`, `invite_token`, and invalid lookup tokens across all captured log messages and record attributes.
- **Surprise Invariant in Logs**: `public_wishlist_resolved` logs only `projection_mode` (`anonymous_safe`, `recipient_safe`, `gifter`) and `items_count`, never reservation quantities, giver IDs, or purchase statuses.
