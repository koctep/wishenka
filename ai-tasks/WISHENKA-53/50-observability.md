# WISHENKA-53: Observability Implementation

## Logging Implementation

- `preview_cache_lookup` is a DEBUG event in `wishenka.items` with `cache_outcome` set to
  `miss` or `hit`. Hits are logged only after destination revalidation succeeds. Only enabled
  cache lookups emit the event; uncached calls with an injected client and plain text do not.
  The event includes no URL, cache key, response data, cookie, or user input.
- Existing `item_preview_success` INFO events provide overall preview duration, domain, input
  type, and fallback status. Existing WARNING events describe blocked destinations, HTTP and
  network failures; `item_metadata_parsing_error` is emitted at ERROR on extraction failure.
- Existing `url_fetch_success` INFO events include the complete URL and fetched byte count;
  error events may include URL or exception text. This task does not change their redaction.

The application uses Python logging with structured `extra` fields. The JSON formatter includes
these fields; the text formatter displays the event message. DEBUG is disabled at the default
INFO level and must be enabled to observe individual cache outcomes.

## Metrics Implementation

The application has no metrics exporter. No exporter or business, resource, pool occupancy,
or throughput metrics were introduced. When DEBUG events are collected, lookup hit and miss
counts can be derived from `preview_cache_lookup`; these counts are process-local and exclude
bypassed lookups. The existing preview duration is end-to-end, not a pool or DNS latency metric.
There is no guarantee of delivery or aggregation of logs, and no cache-size gauge was added.

## Monitoring Integration

No Prometheus exporter, dashboard, alert, or log aggregation integration is configured by this
change. Production collection and alert thresholds depend on deployment configuration.

## Validation Results

- The offline UI test checks miss then hit, structured event fields, one origin request, and
  absence of the URL path and `url` field from both new records.
- Existing tests cover fallback and security paths, including logging for extraction failures.
- The new event contains no response body or large data structure. Existing logs may contain
  full URLs or exception text, as stated above.
- No metrics collector was added; collector and dashboard validation are not applicable.
- `make test`: 348 passed with one dependency deprecation warning. Ruff and mypy passed for the
  modified Python files.

## Notes

Each application instance has an independent cache and pool. A DNS validation failure on a
candidate hit is reported by the existing fallback events rather than as a successful cache hit.
