# WISHENKA-11: Observability Implementation

## Logging Implementation

### Added Logs

Describe added logging:
- **EMERG**: None (in-memory domain services with no immediate kernel/system crashes)
- **ALERT**: None (no paging alerts required for item preview degradations)
- **CRIT**: None
- **ERR**:
  - `wishenka.items` (`ItemPreviewService.fetch_preview`): Unexpected HTML parsing crashes (`item_metadata_parsing_error`) capturing exception details, `url_domain`, `duration_ms`, and initiating fallback DTO.
- **WARNING**:
  - `wishenka.items` (`ItemPreviewService.fetch_preview`): HTTP request timeout after 4.0s (`item_preview_timeout`) with `url_domain`, `duration_ms`, and `fallback_reason="timeout"`.
  - `wishenka.items` (`ItemPreviewService.fetch_preview`): HTTP connection/network error (`item_preview_network_error`) with `url_domain`, `duration_ms`, and `fallback_reason="http_error"`.
  - `wishenka.items` (`ItemPreviewService.fetch_preview`): Upstream HTTP >= 400 error (`item_preview_http_error`) with `status_code`, `url_domain`, and `duration_ms`.
  - `wishenka.wishlists` (`WishlistService.update_wish_item`): Desired quantity reduction below locked reserved/received units rejected (`item_quantity_reduction_rejected`) with `item_id`, `wishlist_id`, `requested_quantity`, `locked_quantity`.
  - `wishenka.wishlists` (`WishlistService.update_wish_item`): Item not found lookup failure (`item_not_found`) with `item_id`, `actor_id`.
  - `wishenka.wishlists` (`WishlistService.update_wish_item`): Mutation blocked on archived wishlist (`item_mutation_blocked_archived`) with `item_id`, `wishlist_id`.
  - `wishenka.wishlists` (`WishlistService.update_wish_item`): Mutation blocked on deleted wishlist (`item_mutation_blocked_deleted`) with `item_id`, `wishlist_id`.
  - `wishenka.wishlists` (`WishlistService.update_wish_item`): Edit permission denied (`access_denied`) with `item_id`, `wishlist_id`, `actor_id`.
- **NOTICE**: None
- **INFO**:
  - `wishenka.items` (`HtmlMetadataExtractor.extract`): Metadata extraction completed (`metadata_extraction_completed`) with `url_domain`, `duration_ms`, `parser_stage="complete"`, and metadata presence booleans (`has_title`, `has_price`, `has_image`).
  - `wishenka.items` (`ItemPreviewService.fetch_preview`): Link preview successfully resolved (`item_preview_success`) with `url_domain`, `duration_ms`, `input_type`, and `is_fallback=False`.
  - `wishenka.items` (`ItemPreviewService.fetch_preview`): Anti-bot challenge or restricted response detected (`anti_bot_challenge_detected`) with `status_code`, `url_domain`, `duration_ms`, triggering graceful fallback.
  - `wishenka.wishlists` (`WishlistService.add_wish_item`): Item added to wishlist (`item_created`) with `item_id`, `wishlist_id`, `actor_id`, and initial `quantity`.
  - `wishenka.wishlists` (`WishlistService.update_wish_item`): Item updated (`item_updated`) with `item_id`, `wishlist_id`, `actor_id`, new `quantity`, and `quantity_delta`.
- **DEBUG**:
  - `wishenka.items` (`UniversalInputClassifier.classify`): User input classified (`input_classified`) with `input_type`, `url_domain` (if present), and `has_residual` boolean.
  - `wishenka.items` (`HtmlMetadataExtractor.extract`): Metadata extraction started (`metadata_extraction_started`) with `url_domain`, `parser_stage="start"`, and HTML payload character length.
  - `wishenka.items` (`HtmlMetadataExtractor.extract`): Intermediate cascade stage resolved (`metadata_stage_resolved`) for `json_ld`, `opengraph`, and `microdata`.
  - `wishenka.items` (`ItemPreviewService.fetch_preview`): Plain text note preview processed (`item_preview_plain_text`) with elapsed `duration_ms`.

### Log Structure

Log format used:
- Structured logs: yes
- Includes context: yes (`event`, `url_domain`, `input_type`, `parser_stage`, `duration_ms`, `fallback_reason`, `item_id`, `wishlist_id`, `quantity`, `quantity_delta`, `actor_id`)
- Log levels: DEBUG, INFO, WARNING, ERROR

## Metrics Implementation (if applicable)

### Performance Metrics

Added performance metrics:
- **Response time**: `duration_ms` recorded per parsing execution and preview retrieval step in `ItemPreviewService` and `HtmlMetadataExtractor`.
- **Throughput**: Monitored via request/event counts (`item_preview_success`, `input_classified`, `item_created`, `item_updated`).
- **Error rate**: Tracked via `item_preview_timeout`, `item_preview_network_error`, `anti_bot_challenge_detected`, and `item_quantity_reduction_rejected`.

### Business Metrics

Business metrics:
- `item_created`: Tracks new items added to wishlists with initial target quantity.
- `item_updated`: Tracks item edits and desired quantity changes via `quantity_delta`.
- `item_quantity_reduction_rejected`: Tracks violations of multi-quantity lock invariants (attempting to reduce quantity below reserved/received).

### System Health Metrics

System health metrics:
- **Resource usage**: Fast in-memory parsing with regex and BeautifulSoup; HTML payload sizes tracked via length indicators without holding raw text in memory logs.
- **Component status**: Anti-bot challenge detection and scrape timeouts provide real-time health indicators of external marketplace availability (Ozon, Wildberries, Yandex Market, etc.).

## Monitoring Integration

Integration with monitoring systems:
- [x] Prometheus metrics (compatible via structured event extraction)
- [x] Grafana dashboards (Loki / JSON log ingestion compatible)
- [x] Alerting rules (alert on elevated `item_preview_timeout` or `anti_bot_challenge_detected` rates)
- [x] Log aggregation (ELK, Loki via standard `wishenka.logging.JsonFormatter`)

## Validation Results

Validation results:
- [x] Logs are correctly formatted
- [x] Metrics are collected correctly
- [x] Logging works in error scenarios
- [x] Large data structures are not logged (raw HTML payloads, long user residual texts, sensitive query parameters are strictly excluded)
- [x] Metrics are available for monitoring

## Notes

- All tests in `tests/test_item_observability.py` adhere to the `do-testing` skill contract (`pytestmark = pytest.mark.timeout(10)`, caplog level filtering and assertions).
- Multi-quantity updates emit `quantity_delta` to enable real-time tracking of item inventory adjustments.
- Fallback paths (timeouts, 403 Cloudflare challenges, 5xx server errors, parser crashes) log distinct event names and reasons, ensuring zero confusion between network drops and anti-bot mitigation.
