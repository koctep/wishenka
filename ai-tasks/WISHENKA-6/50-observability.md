# WISHENKA-6: Observability Implementation

## Logging Implementation

### Added Logs

Describe added logging:
- **EMERG**: None (not applicable for domain service lifecycle events)
- **ALERT**: None (not applicable for domain service lifecycle events)
- **CRIT**: None (not applicable for domain service lifecycle events)
- **ERR**: None (domain validation errors are caught, handled, and logged at WARNING level)
- **WARNING**:
  - `wishenka.wishlists.service.WishlistService.get_wishlist_by_id` - Lookup failures for non-existent or deleted wishlists (`wishlist_not_found`, `deleted_wishlist_access_attempt`)
  - `wishenka.wishlists.service.WishlistService.get_wishlist_by_public_token` - Public token lookup failures or access to deleted lists (`public_token_not_found`, `deleted_wishlist_access_attempt`)
  - `wishenka.wishlists.service.WishlistService.add_member` - Permission denied when managing members or assigning admin role (`access_denied`)
  - `wishenka.wishlists.service.WishlistService.remove_member` - Permission denied when removing collaborator (`access_denied`)
  - `wishenka.wishlists.service.WishlistService.update_wishlist_settings` - Permission denied when editing wishlist settings (`access_denied`)
  - `wishenka.wishlists.service.WishlistService.archive_wishlist` - Permission denied when attempting to archive wishlist (`access_denied`)
  - `wishenka.wishlists.service.WishlistService.unarchive_wishlist` - Permission denied when attempting to unarchive wishlist (`access_denied`)
  - `wishenka.wishlists.service.WishlistService.delete_wishlist` - Permission denied when non-owner attempts to delete wishlist (`access_denied`)
  - `wishenka.wishlists.service.WishlistService.transfer_ownership` - Permission denied when non-owner attempts ownership transfer (`access_denied`)
  - `wishenka.wishlists.service.WishlistService.add_wish_item` - Mutation attempts blocked on archived/deleted lists or unauthorized actors (`wishlist_archived_mutation_blocked`, `wishlist_deleted_mutation_blocked`, `access_denied`)
  - `wishenka.wishlists.service.WishlistService.create_reservation` - Surprise Invariant breach attempt (recipient self-reservation), reservation on archived/deleted list or item, insufficient available quantity, or missing item (`surprise_invariant_violation_attempt`, `reservation_blocked_archived`, `reservation_blocked_deleted`, `reservation_blocked_archived_item`, `insufficient_quantity`, `item_not_found`)
  - `wishenka.wishlists.service.WishlistService.get_reservation_status` - Reservation lookup failure (`reservation_not_found`)
  - `wishenka.wishlists.service.WishlistService.join_by_invite` - Invalid or expired invite tokens, or joining deleted wishlist (`invalid_invite_token`, `expired_invite_token`, `join_deleted_wishlist`)
  - `wishenka.wishlists.service.WishlistService.regenerate_public_token` - Permission denied when non-owner/admin attempts public token regeneration (`access_denied`)
  - `wishenka.wishlists.service.WishlistService.regenerate_invite_token` - Permission denied when non-owner/admin attempts invite token regeneration (`access_denied`)
- **NOTICE**: None (standard library maps notice-level events to INFO)
- **INFO**:
  - `wishenka.wishlists.service.WishlistService.create_wishlist` - Audit log for wishlist creation with owner ID, format (personal/collaborative), time type (ongoing/event), and ISO event date (`wishlist_created`)
  - `wishenka.wishlists.service.WishlistService.add_member` - Audit log for collaborator addition and role assignment (`member_role_assigned`)
  - `wishenka.wishlists.service.WishlistService.remove_member` - Audit log for collaborator removal (`member_removed`)
  - `wishenka.wishlists.service.WishlistService.update_wishlist_settings` - Audit log for wishlist metadata settings update (`wishlist_settings_updated`)
  - `wishenka.wishlists.service.WishlistService.archive_wishlist` - Audit log for lifecycle transition ACTIVE -> ARCHIVED (`wishlist_status_changed`)
  - `wishenka.wishlists.service.WishlistService.unarchive_wishlist` - Audit log for lifecycle transition ARCHIVED -> ACTIVE (`wishlist_status_changed`)
  - `wishenka.wishlists.service.WishlistService.delete_wishlist` - Audit log for lifecycle transition ACTIVE -> DELETED and cascading reservation cancellation (`wishlist_status_changed`)
  - `wishenka.wishlists.service.WishlistService.transfer_ownership` - Audit log for ownership transfer from previous owner to new owner (`ownership_transferred`)
  - `wishenka.wishlists.service.WishlistService.add_wish_item` - Audit log for item creation within wishlist (`item_created`)
  - `wishenka.wishlists.service.WishlistService.create_reservation` - Audit log for gifter reservation with item ID, gifter ID, and quantity (`reservation_created`)
  - `wishenka.wishlists.service.WishlistService.join_by_invite` - Audit log for member joining via invite link (`member_joined`)
  - `wishenka.wishlists.service.WishlistService.regenerate_public_token` - Audit log for public link rotation (`public_token_regenerated`)
  - `wishenka.wishlists.service.WishlistService.regenerate_invite_token` - Audit log for invite link rotation (`invite_token_regenerated`)
- **DEBUG**:
  - `wishenka.wishlists.service.WishlistService.get_wishlist_view` - View projection calculation trace (`wishlist_view_projected`)

### Log Structure

Log format used:
- Structured logs: yes
- Includes context: yes
- Log levels: INFO, WARNING, DEBUG

## Metrics Implementation (if applicable)

### Performance Metrics

Added performance metrics:
- **Response time**: Measured via `wishenka.web.app.RequestLoggingMiddleware` - `duration_ms` on all HTTP endpoints
- **Throughput**: Tracked via HTTP request logging middleware
- **Error rate**: Tracked via status code 4xx/5xx in access logs and WARNING/ERROR level events

### Business Metrics

Business metrics:
- `wishlist_created`: Wishlist creations count by format (`personal`/`collaborative`) and time type (`ongoing`/`event`) - `wishenka.wishlists.service`
- `reservation_created`: Number of reservations made and items reserved - `wishenka.wishlists.service`
- `member_joined`: Collaborative wishlist joins via invite tokens - `wishenka.wishlists.service`
- `surprise_invariant_violation_attempt`: Count of attempted self-reservations blocked by access policy - `wishenka.wishlists.service`

### System Health Metrics

System health metrics:
- **Resource usage**: SQLite WAL file size, memory utilization, connection pool status
- **Component status**: `/healthz` endpoint verifying application lifespan readiness and service availability

## Monitoring Integration

Integration with monitoring systems:
- [x] Structured JSON logging via `wishenka.logging.JsonFormatter` for ELK/Loki ingestion
- [x] Lifespan and HTTP access logging with correlation fields (`duration_ms`, `status_code`, `path`)
- [ ] Prometheus metrics endpoint (planned for infrastructure milestone)
- [ ] Grafana dashboards (planned for deployment milestone)
- [ ] Alerting rules for abnormal warning spikes on access violations / invariant breaches

## Validation Results

Validation results:
- [x] Logs are correctly formatted
- [x] Metrics are collected correctly
- [x] Logging works in error scenarios
- [x] Large data structures are not logged
- [x] Metrics are available for monitoring

## Notes

- **Zero-Leak Security Rule**: Sensitive raw token strings (`public_token`, `invite_token`) are strictly excluded from log messages and metadata attributes. Only token types and entity IDs are recorded.
- **Surprise Invariant Observability**: Whenever a recipient user attempts an unauthorized reservation or inquiry about reserved status of gifts designated for them, a WARNING audit log (`surprise_invariant_violation_attempt`) is emitted without exposing hidden reservations to the caller.
- **Automated Test Coverage**: All logging events and safety invariants are covered by automated unit tests in `tests/test_wishlist_roles_lifecycle.py` (`TestWishlistAuditLogging`) utilizing pytest's `caplog` fixture.
