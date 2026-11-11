# WISHENKA-14: Observability Implementation

## Logging Implementation

### Added Logs

Structured production logging for Telegram Mini App (TMA) and HTMX wish item UI endpoints (`wishenka.web.items_ui`), covering live universal input preview, quick item creation, detailed modal opening, Reduction Lock rendering and rejection, collaborative recipient targeting, and safe item archive/restore lifecycle:

- **WARNING**:
  - [`wishenka.web.routes.items_ui.submit_edit_item`](file:///home/src/wishenka/web/routes/items_ui.py#L629-L644) — Attempt to reduce item quantity below actively locked (reserved + received) quantity rejected with HTTP 409 and preserved form state (`event="ui_reduction_lock_rejected"`).
- **INFO**:
  - [`wishenka.web.routes.items_ui.preview_item_input`](file:///home/src/wishenka/web/routes/items_ui.py#L173-L213) — Universal input classified (plain text vs. URL) and live preview card or fallback rendered with latency tracking (`event="ui_item_quick_add_preview"`).
  - [`wishenka.web.routes.items_ui.quick_add_item`](file:///home/src/wishenka/web/routes/items_ui.py#L302-L317) — Wish item created via Quick Add Bar or creation modal with HTMX out-of-band DOM resets (`event="ui_item_quick_add_success"`).
  - [`wishenka.web.routes.items_ui.get_new_item_modal`](file:///home/src/wishenka/web/routes/items_ui.py#L406-L420) — Detailed item creation BottomSheet modal opened with prepopulated preview fields (`event="ui_item_edit_opened"`, `mode="create"`).
  - [`wishenka.web.routes.items_ui.get_edit_item_modal`](file:///home/src/wishenka/web/routes/items_ui.py#L493-L508) — Detailed item edit BottomSheet modal opened with computed `locked_quantity` (`event="ui_item_edit_opened"`, `mode="edit"`).
  - [`wishenka.web.routes.items_ui.get_edit_item_modal`](file:///home/src/wishenka/web/routes/items_ui.py#L510-L523) — Active Reduction Lock constraint (`min=locked_quantity` and warning banner) rendered in edit modal (`event="ui_reduction_lock_rendered"`).
  - [`wishenka.web.routes.items_ui.submit_edit_item`](file:///home/src/wishenka/web/routes/items_ui.py#L686-L700) — Wish item attributes and recipient targeting saved via detailed edit form (`event="ui_item_edit_saved"`).
  - [`wishenka.web.routes.items_ui.archive_item_ui`](file:///home/src/wishenka/web/routes/items_ui.py#L755-L767) — Wish item archived via HTMX UI while preserving gifter reservations (`event="ui_item_archived"`).
  - [`wishenka.web.routes.items_ui.restore_item_ui`](file:///home/src/wishenka/web/routes/items_ui.py#L814-L826) — Archived wish item restored to active list via HTMX UI (`event="ui_item_restored"`).

### Log Structure

Log format used:

- Structured logs: Yes (`extra={...}` dictionary attached to all log records in `wishenka.web.items_ui`).
- Includes context: Yes (`event`, `wishlist_id`, `item_id`, `actor_id`, `user_id`, `input_type`, `domain`, `store_name`, `is_fallback`, `duration_ms`, `has_link`, `price`, `quantity`, `mode`, `locked_quantity`, `requested_quantity`, `is_collaborative`, `has_recipient`).
- Log levels: `INFO`, `WARNING`.
- Privacy & security invariants:
  - **Zero raw URLs or sensitive query parameters logged**: Only the normalized hostname (`domain`, e.g. `ozon.ru`, `market.yandex.ru`) and `store_name` are logged; full URLs, paths, affiliate IDs, and query tokens are never written to logs.
  - **Zero capability tokens or session secrets logged**: `public_token`, `invite_token`, bearer session tokens, and secret keys are never logged.
  - **Surprise Invariant preserved in telemetry**: Recipient UI logs record only aggregate `locked_quantity` and never include gifter `user_id`, `username`, or `first_name`.
  - **Zero large data structures**: HTML bodies, template contexts, and raw user text/descriptions are excluded from log records.

## Event Catalog

| Event Name | Log Level | Context Attributes | Description |
| :--- | :--- | :--- | :--- |
| `ui_item_quick_add_preview` | `INFO` | `wishlist_id`, `actor_id`, `user_id`, `input_type`, `domain`, `store_name`, `is_fallback`, `duration_ms` | Universal input classified and preview/fallback rendered |
| `ui_item_quick_add_success` | `INFO` | `wishlist_id`, `item_id`, `actor_id`, `user_id`, `has_link`, `price`, `quantity` | Wish item created via Quick Add Bar or creation modal |
| `ui_item_edit_opened` | `INFO` | `wishlist_id`, `item_id`, `actor_id`, `user_id`, `mode`, `locked_quantity`, `is_collaborative` | Detailed item create (`mode="create"`) or edit (`mode="edit"`) modal opened |
| `ui_reduction_lock_rendered` | `INFO` | `wishlist_id`, `item_id`, `actor_id`, `user_id`, `locked_quantity` | Edit modal rendered with active Reduction Lock constraint (`locked_quantity > 0`) |
| `ui_reduction_lock_rejected` | `WARNING` | `wishlist_id`, `item_id`, `actor_id`, `user_id`, `requested_quantity`, `locked_quantity` | Edit submission rejected (HTTP 409) due to quantity below locked reservations |
| `ui_item_edit_saved` | `INFO` | `wishlist_id`, `item_id`, `actor_id`, `user_id`, `quantity`, `has_recipient` | Wish item edits successfully persisted via UI modal |
| `ui_item_archived` | `INFO` | `wishlist_id`, `item_id`, `actor_id`, `user_id` | Wish item archived via HTMX UI |
| `ui_item_restored` | `INFO` | `wishlist_id`, `item_id`, `actor_id`, `user_id` | Archived wish item restored via HTMX UI |

## Metrics Implementation (if applicable)

### Performance Metrics

- **Response time**: `duration_ms` recorded on every `ui_item_quick_add_preview` event in [`wishenka/web/routes/items_ui.py`](file:///home/src/wishenka/web/routes/items_ui.py#L172-L213) to track end-to-end link classification and metadata preview latency.
- **Throughput**: Event volume of `ui_item_quick_add_preview`, `ui_item_quick_add_success`, `ui_item_edit_saved`, `ui_item_archived`, and `ui_item_restored`.
- **Error / Fallback rate**: Ratio of `is_fallback=True` in `ui_item_quick_add_preview` by `domain` and rate of `ui_reduction_lock_rejected` warnings.

### Business Metrics

- **Quick Add Link vs. Plain Text Share**: Tracked via `input_type` and `has_link` on `ui_item_quick_add_preview` and `ui_item_quick_add_success`.
- **Collaborative Recipient Addressing Usage**: Tracked via `has_recipient` boolean on `ui_item_edit_saved`.
- **Reduction Lock Protection Triggers**: Tracked via `ui_reduction_lock_rendered` and `ui_reduction_lock_rejected`.

### System Health Metrics

- **Marketplace Scraper Degradation**: Monitored via `ui_item_quick_add_preview` where `is_fallback=True` grouped by `domain`.
- **UI Concurrency Conflicts**: Monitored via `ui_reduction_lock_rejected` when a gifter reserves an item while the owner has the edit modal open.

## Monitoring Integration

Integration with monitoring systems:

- [x] Log aggregation (ELK, Loki, Vector) via structured `extra` attributes
- [ ] Prometheus metrics
- [ ] Grafana dashboards
- [ ] Alerting rules

## Validation Results

Validation results:

- [x] Logs are correctly formatted
- [x] Metrics are collected correctly (`duration_ms`, `is_fallback`, `locked_quantity`, `has_recipient`, `has_link`)
- [x] Logging works in error scenarios (`ui_reduction_lock_rejected` on HTTP 409 Conflict)
- [x] Large data structures and sensitive tokens/URLs are not logged
- [x] Automated observability tests added in [`tests/test_wish_items_tma_ui.py`](file:///home/src/tests/test_wish_items_tma_ui.py#L663-L991):
  - `test_tma_ui_observability_events_and_attributes`
  - `test_tma_ui_observability_privacy_invariants`
- [x] Full quality gate (`make check`) passed: 0 Ruff lint/format issues, 0 Mypy errors, 301 passed tests.

## Notes

All UI log events include both `actor_id` and `user_id` in structured `extra` attributes for consistent correlation across domain (`wishenka.wishlists`) and web UI (`wishenka.web.items_ui`) loggers.
