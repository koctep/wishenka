# WISHENKA-13: Observability Implementation

## Logging Implementation

### Added Logs

Structured production logging for wish items lifecycle, atomic reordering, safe archiving, RBAC enforcement, and reduction invariants:

- **WARNING**:
  - [`wishenka.wishlists.WishlistService.add_wish_item`](file:///home/src/wishenka/wishlists/service.py#L780) — Unauthorized actor denied permission to add an item to the wishlist (`event="item_access_denied"`).
  - [`wishenka.wishlists.WishlistService.update_wish_item`](file:///home/src/wishenka/wishlists/service.py#L913) — Unauthorized actor denied permission to update an item (`event="item_access_denied"`).
  - [`wishenka.wishlists.WishlistService.reorder_wish_items`](file:///home/src/wishenka/wishlists/service.py#L1061) — Unauthorized actor denied permission to reorder items (`event="item_access_denied"`).
  - [`wishenka.wishlists.WishlistService.archive_wish_item`](file:///home/src/wishenka/wishlists/service.py#L1144) — Unauthorized actor denied permission to archive an item (`event="item_access_denied"`).
  - [`wishenka.wishlists.WishlistService.restore_wish_item`](file:///home/src/wishenka/wishlists/service.py#L1186) — Unauthorized actor denied permission to restore an item (`event="item_access_denied"`).
  - [`wishenka.wishlists.WishlistService.update_wish_item`](file:///home/src/wishenka/wishlists/service.py#L946) — Attempt to reduce item quantity below actively locked (reserved + received) count rejected (`event="item_quantity_reduction_rejected"`).
  - [`wishenka.wishlists.WishlistService.reorder_wish_items`](file:///home/src/wishenka/wishlists/service.py#L1074) — Invalid reorder request with duplicate IDs or set mismatch (`event="item_reorder_invalid"`).
  - [`wishenka.web.routes.items.execute`](file:///home/src/wishenka/web/routes/items.py#L43) — REST API route exception handling logs (`event="item_not_found"`, `event="item_permission_denied"`, `event="item_conflict"`, `event="item_validation_error"`).
- **INFO**:
  - [`wishenka.wishlists.WishlistService.add_wish_item`](file:///home/src/wishenka/wishlists/service.py#L827) — Wish item successfully created with auto-incremented display order (`event="item_created"`).
  - [`wishenka.wishlists.WishlistService.update_wish_item`](file:///home/src/wishenka/wishlists/service.py#L990) — Wish item properties updated (`event="item_updated"`).
  - [`wishenka.wishlists.WishlistService.reorder_wish_items`](file:///home/src/wishenka/wishlists/service.py#L1110) — Wishlist items atomically reordered (`event="items_reordered"`).
  - [`wishenka.wishlists.WishlistService.archive_wish_item`](file:///home/src/wishenka/wishlists/service.py#L1160) — Wish item safely archived while preserving reservations (`event="item_archived"`).
  - [`wishenka.wishlists.WishlistService.restore_wish_item`](file:///home/src/wishenka/wishlists/service.py#L1212) — Archived wish item restored and appended to the end of active order (`event="item_restored"`).

### Log Structure

Log format used:
- Structured logs: Yes (`extra={...}` dictionary attached to all domain and route log entries).
- Includes context: Yes (`event`, `wishlist_id`, `item_id`, `actor_id`, `quantity`, `display_order`, `has_recipient`, `updated_fields`, `active_reservations_count`, `item_count`, `requested_quantity`, `locked_quantity`, `reason`, `action`, `role`).
- Log levels: `INFO`, `WARNING`.
- Privacy & security invariant:
  - **Zero capability tokens logged**: `public_token` and `invite_token` are never logged in any message or structured attribute.
  - **Zero sensitive authentication data logged**: Session bearer secrets, Telegram `init_data`, and auth signatures are omitted from all telemetry records.
  - **Zero large payload dumps**: Only scalar IDs, change deltas, updated field names, and error reasons are recorded.

## Event Catalog

| Event Name | Log Level | Context Attributes | Description |
|:---|:---|:---|:---|
| `item_created` | `INFO` | `wishlist_id`, `item_id`, `actor_id`, `quantity`, `display_order`, `has_recipient` | Wish item successfully added to wishlist |
| `item_updated` | `INFO` | `wishlist_id`, `item_id`, `actor_id`, `updated_fields`, `quantity`, `quantity_delta` | Wish item properties updated |
| `item_archived` | `INFO` | `wishlist_id`, `item_id`, `actor_id`, `active_reservations_count` | Wish item archived, hiding from active list while preserving reservations |
| `item_restored` | `INFO` | `wishlist_id`, `item_id`, `actor_id`, `display_order` | Archived item restored to end of active list |
| `items_reordered` | `INFO` | `wishlist_id`, `actor_id`, `item_count`, `item_ids` | Active items display order atomically permuted |
| `item_quantity_reduction_rejected` | `WARNING` | `wishlist_id`, `item_id`, `actor_id`, `requested_quantity`, `locked_quantity`, `reason` | Invariant violation: quantity reduction below locked reservations |
| `item_reorder_invalid` | `WARNING` | `wishlist_id`, `actor_id`, `reason` | Permutation integrity failure (duplicates or incomplete set) |
| `item_access_denied` | `WARNING` | `wishlist_id`, `actor_id`, `action`, `role` | Unauthorized action attempt by non-member or unauthorized role |

## Metrics Implementation (if applicable)

### Performance Metrics

- **Mutation Throughput**: Tracked via volume of `event="item_created"`, `event="item_updated"`, `event="items_reordered"`.
- **Archiving & Restoration Rate**: Monitored via counts of `event="item_archived"` and `event="item_restored"`.
- **Conflict & Invariant Violation Rate**: Tracked through occurrences of `event="item_quantity_reduction_rejected"` and `event="item_reorder_invalid"`.

### Business Metrics

- **Item Multi-Quantity Distribution**: Monitored through `quantity` attribute in `item_created` and `item_updated`.
- **Collaborative Addressing Adoption**: Monitored via `has_recipient` boolean in `item_created` and `updated_fields` containing `recipient_user_id` / `recipient_name`.
- **Access Violation Frequency**: Monitored by `item_access_denied` grouped by `action` and `role`.

### System Health Metrics

- **Reorder Permutation Integrity**: Ratio of `item_reorder_invalid` to `items_reordered`.
- **Lock Invariant Health**: Frequency of `item_quantity_reduction_rejected` indicating UI desynchronization or race attempts.

## Monitoring Integration

- [x] Structured JSON / extra log aggregation ready (Vector, Loki, ELK)
- [x] Contextual attributes indexed (`event`, `wishlist_id`, `item_id`, `actor_id`, `action`, `role`)
- [ ] Prometheus metrics export (future telemetry stage)
- [ ] Grafana dashboard for item CRUD and conflict monitoring

## Validation Results

- [x] Structured logs correctly formatted across all 8 required events.
- [x] Required event attributes present and verified (`item_created`, `item_updated`, `item_archived`, `item_restored`, `items_reordered`, `item_quantity_reduction_rejected`, `item_reorder_invalid`, `item_access_denied`).
- [x] Privacy invariants validated: 0 capability tokens (`public_token`, `invite_token`) and 0 session secrets logged.
- [x] Automated tests added in [`tests/test_wish_items_crud_api.py`](file:///home/src/tests/test_wish_items_crud_api.py):
  - `test_item_lifecycle_observability_events`
  - `test_item_rejection_and_access_denied_observability_events`
  - `test_item_observability_privacy_invariants_no_tokens_or_auth_data`
- [x] Full test suite passes: 289 passed in ~55s.
- [x] Static analysis clean: 0 Ruff errors, 0 Ruff formatting issues, 0 Mypy type errors.
