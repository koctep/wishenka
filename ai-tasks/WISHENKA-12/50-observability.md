# WISHENKA-12: Observability Implementation

## Logging Implementation

### Added Logs

Structured production logging for marketplace URL cleaning, rule matching, JSON-LD extraction, and anti-bot degradation:

- **ERR**: [`wishenka.items.service.ItemPreviewService.fetch_preview`](file:///home/src/wishenka/items/service.py#L347) — HTML/metadata parsing failure during extraction (`event="item_metadata_parsing_error"`).
- **WARNING**:
  - [`wishenka.items.service.ItemPreviewService.fetch_preview`](file:///home/src/wishenka/items/service.py#L94) — SSRF protection triggered for forbidden host/IP (`event="item_preview_ssrf_blocked"`).
  - [`wishenka.items.service.ItemPreviewService.fetch_preview`](file:///home/src/wishenka/items/service.py#L123) — Forbidden or invalid URL scheme (`event="item_preview_invalid_scheme"`).
  - [`wishenka.items.service.ItemPreviewService.fetch_preview`](file:///home/src/wishenka/items/service.py#L149) — Upstream response body exceeds safety limit (`event="item_preview_response_too_large"`).
  - [`wishenka.items.service.ItemPreviewService.fetch_preview`](file:///home/src/wishenka/items/service.py#L177) — Upstream HTTP fetch timed out (`event="item_preview_timeout"`).
  - [`wishenka.items.service.ItemPreviewService.fetch_preview`](file:///home/src/wishenka/items/service.py#L211) — Anti-bot challenge or restricted status code (HTTP 403, 429, 503) intercepted (`event="item_preview_anti_bot"`).
  - [`wishenka.items.service.ItemPreviewService.fetch_preview`](file:///home/src/wishenka/items/service.py#L295) — Anti-bot challenge signature (Cloudflare Turnstile, Qrator, DDoS-Guard) detected in HTML body (`event="item_preview_anti_bot"`).
  - [`wishenka.items.service.ItemPreviewService.fetch_preview`](file:///home/src/wishenka/items/service.py#L247) — Upstream HTTP >= 400 error requiring graceful fallback (`event="item_preview_http_error"`).
  - [`wishenka.items.service.ItemPreviewService.fetch_preview`](file:///home/src/wishenka/items/service.py#L270) — Upstream network connection error (`event="item_preview_network_error"`).
- **INFO**:
  - [`wishenka.items.marketplaces.clean_url`](file:///home/src/wishenka/items/marketplaces.py#L58) — Tracking query parameters (e.g. `utm_*`, `from=share*`, `clid`) stripped from URL (`event="marketplace_url_cleaned"`).
  - [`wishenka.items.parser.HtmlMetadataExtractor.extract`](file:///home/src/wishenka/items/parser.py#L383) — HTML metadata extraction completed successfully (`event="metadata_extraction_completed"`).
  - [`wishenka.items.service.ItemPreviewService.fetch_preview`](file:///home/src/wishenka/items/service.py#L320) — Link preview successfully constructed (`event="item_preview_success"`).
  - [`wishenka.items.service.ItemPreviewService.fetch_preview`](file:///home/src/wishenka/items/service.py#L224) — Anti-bot or restricted response handled with graceful degradation (`event="anti_bot_challenge_detected"`).
- **DEBUG**:
  - [`wishenka.items.marketplaces.MarketplaceRegistry.get_rule`](file:///home/src/wishenka/items/marketplaces.py#L187) — Specific marketplace rule matched for domain (`event="marketplace_rule_matched"`).
  - [`wishenka.items.parser.HtmlMetadataExtractor._find_jsonld_products`](file:///home/src/wishenka/items/parser.py#L427) — JSON-LD `@graph` container traversal (`event="jsonld_graph_traversal"`).
  - [`wishenka.items.parser.HtmlMetadataExtractor.extract`](file:///home/src/wishenka/items/parser.py#L281) — Schema.org `AggregateOffer` (`lowPrice`, `highPrice`) extraction diagnostics (`event="jsonld_aggregate_offer_extracted"`).
  - [`wishenka.items.parser.HtmlMetadataExtractor.extract`](file:///home/src/wishenka/items/parser.py#L215) — Metadata extraction started for domain (`event="metadata_extraction_started"`).
  - [`wishenka.items.parser.HtmlMetadataExtractor.extract`](file:///home/src/wishenka/items/parser.py#L295) — Intermediate extraction stage resolved (`event="metadata_stage_resolved"`).
  - [`wishenka.items.service.ItemPreviewService.fetch_preview`](file:///home/src/wishenka/items/service.py#L70) — Plain text item preview processed (`event="item_preview_plain_text"`).

### Log Structure

Log format used:
- Structured logs: Yes (`extra={...}` dictionary attached to every logging call).
- Includes context: Yes (includes `event`, `url_domain`, `status_code`, `duration_ms`, `fallback_reason`, `graph_items_count`, `removed_params_count`, `removed_keys`).
- Log levels: `DEBUG`, `INFO`, `WARNING`, `ERROR`.
- Safety invariant: **Strictly zero raw HTML payloads and zero secret/token leaks**. Only parameter names (not sensitive query values) are recorded in `removed_keys`. Response bodies and heavy DOM trees are never included in log records.

## Metrics Implementation (if applicable)

### Performance Metrics

Added performance metrics:
- **Response time**: Measured via `duration_ms` (using `time.perf_counter()`) on:
  - [`HtmlMetadataExtractor.extract`](file:///home/src/wishenka/items/parser.py#L382) (`event="metadata_extraction_completed"`)
  - [`ItemPreviewService.fetch_preview`](file:///home/src/wishenka/items/service.py#L328) (`event="item_preview_success"`)
  - All degradation and fallback branches in `ItemPreviewService`
- **Throughput**: Tracked via `event="item_preview_success"`, `event="item_preview_plain_text"`, and `event="marketplace_url_cleaned"`.
- **Error rate**: Tracked via `event="item_preview_anti_bot"`, `event="item_preview_timeout"`, `event="item_preview_ssrf_blocked"`, `event="item_preview_response_too_large"`.

### Business Metrics

Business metrics:
- **Marketplace adoption**: Count of `event="marketplace_rule_matched"` by `store_name` (Ozon, Wildberries, Yandex Market, Avito, Megamarket).
- **Anti-bot impact**: Ratio of `event="item_preview_anti_bot"` vs `event="item_preview_success"` partitioned by `url_domain`.
- **Tracking cleaning frequency**: Volume of `event="marketplace_url_cleaned"` indicating share-sheet vs direct desktop link usage.

### System Health Metrics

System health metrics:
- **Upstream dependency health**: Tracked via timeout and network error rates per target marketplace domain.
- **Parser stability**: Tracked via `item_metadata_parsing_error` occurrences.

## Monitoring Integration

Integration with monitoring systems:
- [x] Structured JSON / extra log aggregation ready (Loki, ELK, Vector)
- [x] Contextual fields indexed (`event`, `url_domain`, `fallback_reason`, `status_code`)
- [ ] Prometheus metrics exporter (planned for future gateway instrumentation)
- [ ] Grafana dashboard for marketplace success rates

## Validation Results

Validation results:
- [x] Logs are correctly formatted: structured `extra` with `event` string.
- [x] Metrics are collected correctly (`duration_ms`, item counts, status codes).
- [x] Logging works in error scenarios (SSRF, timeout, anti-bot 403/503/challenge HTML, 500 server error).
- [x] Large data structures are not logged: raw HTML and tracking parameter values are completely omitted.
- [x] Verified by automated tests in [`tests/test_metadata_extractor_service.py`](file:///home/src/tests/test_metadata_extractor_service.py) (`TestObservabilityAndLogging`) and [`tests/test_item_observability.py`](file:///home/src/tests/test_item_observability.py).
- [x] Verified full repository quality gate: all 272 automated tests passing, `make analyze` with 0 Ruff/Mypy errors.

## Notes

- The dual emission of `event="item_preview_anti_bot"` (at `WARNING`) and `event="anti_bot_challenge_detected"` (at `INFO`) guarantees strict backward compatibility with existing test suites and downstream telemetry consumers while satisfying the WISHENKA-12 alert threshold specifications.
