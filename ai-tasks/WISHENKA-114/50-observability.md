# WISHENKA-114: Observability

## Logging implementation

- `wishenka.items.service.ItemPreviewService` emits the structured WARNING event
  `item_preview_route_rejected` for an opaque client (`unknown_route`) or a denied route
  (`route_denied`). Its fields are `reason`, `input_type`, `duration_ms`, and
  `fallback_reason=ssrf_blocked`. This distinguishes integration failures from destination
  failures without exposing request paths, query parameters, cookies, or authorization data.
- Existing structured `item_preview_ssrf_blocked` events continue to report other destination
  security failures. Existing `item_preview_success`, timeout, network, HTTP, payload-limit,
  and anti-bot events provide outcome and duration diagnostics; cache hit/miss and cassette
  hit/miss events remain available at their existing levels.
- No new lifecycle success logs are needed: application startup and shutdown already emit
  informational logs, and route ownership is verified by tests rather than logged per request.

## Metrics and monitoring

No metrics exporter or new counter is introduced. Route rejection counts and outcome latency
can be derived from structured log events where log aggregation is configured. The change does
not add Prometheus, Grafana, or alerting integration.

## Validation

- Two parameterized caplog cases verify both rejection reasons and assert that a private path
  and query value are absent from the new event's message and structured fields.
- `make test PYTEST_JOBS=1 PYTEST_ARGS="tests/test_preview_supported_routes.py
  tests/test_item_observability.py -q"`: 23 passed. Existing logging tests now mock the
  fetch boundary instead of injecting an unsupported opaque HTTP client.
- No response body, headers, caller client, or URL is included in the new rejection event.

## Notes

This change does not claim that all pre-existing preview events redact every URL. The new route
rejection event is deliberately bounded; broader logging privacy remains outside this step.
