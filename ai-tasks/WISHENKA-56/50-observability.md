# WISHENKA-56: Observability Implementation

## Logging Implementation

The `wishenka.items` logger emits structured DEBUG events when JSON-LD cannot be parsed
(`jsonld_parse_skipped`), type inspection reaches a bound (`jsonld_type_limit`), or product
discovery reaches a bound (`jsonld_discovery_limit`). Limit events include the number of visited
nodes. They do not include page contents, charset declarations, or URLs. Invalid scripts and
bounded searches remain recoverable and continue to later metadata or fallback sources.

Existing extraction events describe start, graph traversal, successful metadata extraction and
completion; existing service events cover fallback and extraction errors. The shared decoder is a
pure helper and does not log raw bytes or headers. Ambiguous legacy encodings are not reliably
detectable, so a successful guess does not constitute proof of the original encoding.

## Metrics and Monitoring

The existing completion event includes extraction duration, and service events can support log
aggregation of outcomes. There is no metrics exporter or project monitoring integration for this
component; no new counters or external dependencies were introduced. DEBUG events require an
appropriate log level to be visible, and should not be treated as always-on production metrics.

## Validation Results

- A `caplog` test covers malformed JSON-LD and both bounded search events, verifies fallback, and
  asserts that a page-content marker is absent from log messages.
- The existing tests cover normal graph and extraction events. The targeted encoding and graph
  suite passed, as did Ruff and mypy for the changed Python files.
- `make test` passed with 387 tests and two dependency warnings. The preserved `core` file from
  an intermittent post-test crash was not modified.
