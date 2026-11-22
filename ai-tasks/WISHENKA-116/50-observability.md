# WISHENKA-116: Observability Implementation

## Logging Implementation

### Added Logs

Audited and verified structured logging in [`wishenka/items/parser.py`](file:///home/src/wishenka/items/parser.py) on logger `wishenka.items` (no production log changes were required; existing structured logs and memo-hit replay were already complete and verified):

- **EMERG**: N/A - JSON-LD parsing and HTML metadata extraction run per preview request; no system-wide emergency conditions arise in this module.
- **ALERT**: N/A - No immediate operator-paging conditions originate inside HTML/JSON-LD metadata parsing.
- **CRIT**: N/A - No critical system failures originate in this module; invalid or excessive JSON-LD degrades to OpenGraph/Microdata/HTML fallback.
- **ERR**: N/A - Malformed JSON-LD scripts (`json.JSONDecodeError`, `TypeError`, `RecursionError`) and limit exhaustion are handled cleanly by skipping/bounding and falling back without emitting `ERROR` noise.
- **WARNING**: N/A - Adversarial or oversized JSON-LD is an expected untrusted-input condition on external web pages and is logged at `DEBUG` rather than `WARNING`.
- **NOTICE**: N/A - Python standard `logging` in this module uses `INFO` and `DEBUG`.
- **INFO**:
  - `HtmlMetadataExtractor.extract` (`event="metadata_extraction_completed"`): summarizes completed HTML metadata extraction with `url_domain`, `parser_stage="complete"`, `duration_ms`, `has_title`, `has_price`, `price`, `currency`, and `has_image` (no raw HTML, title text, or JSON-LD nodes).
- **DEBUG**:
  - `HtmlMetadataExtractor._walk_product_type` (`event="jsonld_type_limit"`): logs when `@type` inspection hits depth `> 128` or reaches the `20_000`-node visit budget with remaining work (`extra={"event": "jsonld_type_limit", "visited_nodes": visited}`), and records `visited` in `_type_limit_collector` when active.
  - `HtmlMetadataExtractor._walk_jsonld_products` (`event="jsonld_type_limit"` memo-hit replay): replays `extra={"event": "jsonld_type_limit", "visited_nodes": limit_visited}` on memo hits whose first evaluation triggered a type limit, keeping discovery-local diagnostic output identical without re-traversing the `@type` structure.
  - `HtmlMetadataExtractor._walk_jsonld_products` (`event="jsonld_graph_traversal"`): logs entry into a `list` or `dict` `@graph` container with `extra={"event": "jsonld_graph_traversal", "graph_items_count": len(graph)}`.
  - `HtmlMetadataExtractor._walk_jsonld_products` (`event="jsonld_discovery_limit"`): logs when JSON-LD product discovery hits depth `> 128` or reaches the `20_000`-node visit budget with pending stack frames (`extra={"event": "jsonld_discovery_limit", "visited_nodes": visited}`).
  - Surrounding `HtmlMetadataExtractor.extract` and pricing/currency helpers: `metadata_extraction_started` (`url_domain`, `parser_stage="start"`, `len(html)` in message), `jsonld_parse_skipped`, `metadata_stage_resolved` (`parser_stage="json_ld"` / `"opengraph"`), `jsonld_price_specification_extracted`, `jsonld_aggregate_offer_extracted`, `inline_currency_extracted`, and `currency_fallback_default`.

### Log Structure

Log format used:

- Structured logs: yes (standard `logging.Logger` calls with `extra={"event": ..., ...}`, serialized in production JSON mode by [`JsonFormatter`](file:///home/src/wishenka/logging.py#L9-L55) into `timestamp`, `level`, `logger`, `message`, and `extra`).
- Includes context: yes (`event`, `visited_nodes`, `graph_items_count`, `url_domain`, `parser_stage`, `duration_ms`, `has_title`, `has_price`, `price`, `currency`, `has_image`, `offer_price`).
- Log levels: `INFO`, `DEBUG`.

## Metrics Implementation (if applicable)

### Performance Metrics

Added performance metrics:

- **Response time**: N/A - No Prometheus, StatsD, or OpenTelemetry metrics backend is used in `wishenka/items/parser.py` or this module layer. Extraction latency is emitted as `duration_ms` on the `metadata_extraction_completed` structured log event.
- **Throughput**: N/A - No metrics exporter is configured in this module; per-discovery traversal counts (`visited_nodes`, `graph_items_count`) are emitted via structured `DEBUG` logs when limits or `@graph` containers are encountered, and offline traversal bounds are covered by `ai-tasks/WISHENKA-116/benchmark_traversal.py` and `HtmlMetadataExtractor._jsonld_traversal_diagnostics`.
- **Error rate**: N/A - No metrics counter exists; malformed JSON-LD and traversal limit events are emitted as structured `jsonld_parse_skipped`, `jsonld_type_limit`, and `jsonld_discovery_limit` logs.

### Business Metrics

Business metrics:

- N/A - Internal JSON-LD traversal and HTML metadata extraction helper; no new business counters added.

### System Health Metrics

System health metrics:

- **Resource usage**: N/A - No Prometheus runtime gauges exist in `wishenka/items/parser.py`. Bounded traversal stack depth (`<= 262` pending discovery records, `<= 131` pending type records) and per-discovery memo size (`<= 20_000` entries) are enforced structurally and asserted deterministically in [`tests/test_jsonld_traversal_bounds.py`](file:///home/src/tests/test_jsonld_traversal_bounds.py).
- **Component status**: N/A - Stateless parser helper.

## Monitoring Integration

Integration with monitoring systems:

- [ ] Prometheus metrics (not applicable — no Prometheus client or metrics backend exists in `wishenka/items/parser.py` or the repository)
- [ ] Grafana dashboards (not applicable — no Prometheus/Grafana pipeline in repository)
- [ ] Alerting rules (not applicable — bounded traversal degradation is handled via fallback without new alert rules)
- [x] Log aggregation (ELK, Loki, etc.) — compatible via `JsonFormatter` structured JSON output (`event` and bounded scalar `extra` fields on `wishenka.items`)

## Validation Results

Validation results:

- [x] Logs are correctly formatted — verified `extra` fields, `DEBUG` levels, and `JsonFormatter` JSON serialization via `caplog` in [`tests/test_jsonld_traversal_bounds.py`](file:///home/src/tests/test_jsonld_traversal_bounds.py) (`test_memo_preserves_limit_logging_and_is_local_to_each_discovery`, `test_discovery_and_graph_logging_emit_debug_metadata_without_raw_payloads`, `test_type_visit_limit_logging_replays_on_memo_hit_without_payloads`).
- [x] Metrics are collected correctly — N/A (no Prometheus/metrics backend exists in `wishenka/items/parser.py`; structured log diagnostics verified instead).
- [x] Logging works in error scenarios — verified malformed JSON-LD (`jsonld_parse_skipped`), discovery visit/depth limits (`jsonld_discovery_limit`), and type visit/depth limits with memo replay (`jsonld_type_limit`) across `tests/test_jsonld_traversal_bounds.py` and `tests/test_encoding_nested_graph.py`.
- [x] Large data structures are not logged — verified that untrusted `@type` tokens, JSON-LD node values, malformed script bodies, and raw HTML payloads never appear in `record.getMessage()`, `record.__dict__`, or formatted `JsonFormatter` JSON output.
- [x] Metrics are available for monitoring — N/A (no Prometheus metrics exporter in this module; structured `wishenka.items` log events are ready for log aggregation).

## Notes

- Added two observability regression tests in [`tests/test_jsonld_traversal_bounds.py`](file:///home/src/tests/test_jsonld_traversal_bounds.py) (`test_discovery_and_graph_logging_emit_debug_metadata_without_raw_payloads` and `test_type_visit_limit_logging_replays_on_memo_hit_without_payloads`) alongside existing `test_memo_preserves_limit_logging_and_is_local_to_each_discovery`, `tests/test_encoding_nested_graph.py::test_bounded_and_malformed_jsonld_diagnostics_hide_page_content`, `tests/test_metadata_extractor_service.py::TestObservabilityAndLogging::test_jsonld_graph_and_aggregate_offer_debug_diagnostics`, and `tests/test_item_observability.py`.
- Verification commands run after the final edit:
  - `make analyze`: Ruff linter (`All checks passed!`), Ruff format check (`248 files already formatted`), and Mypy (`Success: no issues found in 248 source files`).
  - `PYTHONPATH=. .venv/bin/pytest tests/test_jsonld_traversal_bounds.py tests/test_encoding_nested_graph.py tests/test_metadata_extractor_service.py tests/test_marketplace_cassettes.py`: `149 passed` (`23` in `test_jsonld_traversal_bounds.py`, `38` in `test_encoding_nested_graph.py`, `59` in `test_metadata_extractor_service.py`, `29` in `test_marketplace_cassettes.py`).
  - `PYTHONPATH=. .venv/bin/pytest tests/test_item_observability.py`: `7 passed`.
