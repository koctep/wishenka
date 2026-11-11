# WISHENKA-15: Observability Implementation

## Logging Implementation

### Added Logs

Logger `wishenka.web.items_ui` (`wishenka/web/routes/items_ui.py`):
- **WARNING**: `_reordered_response` — `ui_items_reorder_rejected` (invalid permutation, HTTP 400); context: `wishlist_id`, `actor_id`, `user_id`, `reason`.
- **INFO**: `reorder_items_ui` — `ui_items_reordered`; context: `wishlist_id`, `actor_id`, `item_count` (item id list intentionally not logged).
- **INFO**: `move_item_ui` — `ui_item_moved`; context: `wishlist_id`, `item_id`, `actor_id`, `direction`.
- **INFO**: `archive_confirm_ui` — `ui_item_archive_confirm_opened`; context: `has_active_reservations`, `gifter_warning_shown` (no gifter identities).
- **INFO**: `archive_item_ui` — `ui_item_archived`; context: `warn_on_delete_reserved`.
- **INFO**: `restore_item_ui` — `ui_item_restored`; context: `display_order`.

Logger `wishenka.wishlists` (`wishenka/wishlists/service.py`):
- **WARNING**: `archive_wish_item` — `item_access_denied` (permission denied).
- **INFO**: `archive_wish_item` — `item_archived` (with `active_reservations_count`).
- **DEBUG**: `get_wishlist_view` — `wishlist_view_projected`; extended with `items_count` and `archived_items_count`.

Domain errors (not found / permission / archived) are mapped to 404/409 by `_raise_http` without leaking details; the service layer logs denials.

### Log Structure

- Structured logs: yes (`extra` with `event` key)
- Includes context: yes (wishlist/item/actor ids)
- Log levels: WARNING, INFO, DEBUG

## Metrics Implementation (if applicable)

Not applicable: the project has no metrics infrastructure (no Prometheus/StatsD usage); no metrics were introduced.

## Monitoring Integration

- [ ] Prometheus metrics (n/a)
- [ ] Grafana dashboards (n/a)
- [ ] Alerting rules (n/a)
- [x] Log aggregation: structured `event` fields are queryable by existing log pipeline

## Validation Results

- [x] Logs are correctly formatted
- [ ] Metrics are collected correctly (n/a)
- [x] Logging works in error scenarios (reorder rejection WARNING)
- [x] Large data structures are not logged (removed `item_ids` list from `ui_items_reordered`)
- [ ] Metrics are available for monitoring (n/a)

## Notes

Changes in this step: removed the `item_ids` list from the `ui_items_reordered` log; added `items_count`/`archived_items_count` to the debug projection log.
