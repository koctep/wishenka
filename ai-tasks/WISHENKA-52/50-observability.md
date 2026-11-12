# WISHENKA-52: Observability Implementation

## Logging Implementation

Existing `wishenka.items` events cover the affected paths, so this change does not introduce
duplicate production logs:

- `item_preview_success` (INFO) records the domain, input type, overall preview duration in
  milliseconds, and fallback status. Duration includes fetching, executor queueing, and parsing.
- `item_metadata_parsing_error` (ERROR) records the domain, input type, overall duration, and
  fallback reason when the offloaded preview extractor raises.
- `fetch_and_extract_fallback` (WARNING) records errors and the URL for the metadata service.
- `url_fetch_success` (INFO) records fetched byte count and URLs. Existing parser diagnostic
  events continue to use the same logging infrastructure from the worker thread.

These are Python logging records with structured fields in `extra`; rendering depends on the
configured handler. Existing fetcher events include full URLs, and error messages may include
exception text. No HTML body or extracted metadata is intentionally added by this change.

## Metrics Implementation

There is no metrics exporter in the affected code. The existing preview duration log is an
end-to-end performance indicator rather than an extraction-only measurement. Executor queue depth,
parse duration, CPU usage, throughput, and error-rate counters are not added by this change;
operations can derive success and error counts from the existing events if logs are aggregated.
No business or system health metric is introduced.

## Monitoring Integration

No Prometheus exporter, Grafana dashboard, alerting rule, or log aggregation integration was
added. Deployment-specific logging and monitoring remain outside this task.

## Validation Results

- The existing preview success logging test checks event name, level, domain, input type, and
  duration. The metadata extractor fallback test now checks the correct structured error event
  for each offloaded path and the corresponding fallback behavior.
- The log calls do not add the HTML body or a large extracted data structure. Exception messages
  and existing full URL fields are not redacted by this task.
- `make test`: 312 passed, with one dependency deprecation warning.
- No new metrics were added, so no exporter collection test applies.

## Notes

The default executor and the Python GIL can still affect latency under load. Cancellation of the
await does not stop a worker already parsing; a cancelled request may therefore lack a terminal
preview log. The existing duration event is not a measurement of event-loop responsiveness.
