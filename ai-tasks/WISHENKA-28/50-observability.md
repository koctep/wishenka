# WISHENKA-28: Observability Implementation

## Logging Implementation

The bot uses the existing `LOG_LEVEL` and `LOG_JSON` settings. Structured events include:

| Level | Event | Context | Meaning |
| --- | --- | --- | --- |
| INFO | `bot_capture_preview` | `outcome`, `duration_ms` | Preview completed or was skipped. |
| INFO | `bot_capture_draft_ready` | none | A reviewable draft was prepared. |
| INFO | `bot_capture_save` | `outcome` | A save action finished, including refusals. |
| ERROR | `bot_capture_action_error` | none | A draft action transaction failed. |
| ERROR | `bot_draft_cleanup_failed` | none | Draft cleanup failed and will be retried. |

Preview outcomes are `complete`, `partial`, `error`, or `unsupported`. Save outcomes are bounded
status codes; a successful response's list title is never logged. Preview duration is measured by a
monotonic clock. No exception text, payload, link, user, chat, draft, or list identifiers are added
to these events. Existing bot error handling prevents dispatcher exception tracebacks from leaking.

A context-local filter suppresses logs from the explicitly configured classifier, preview HTTP
client, user store, wishlist store, and wishlist notice loggers during sensitive operations.
Other asynchronous operations retain their normal logging. The filter does not apply implicitly
to future child loggers or replace redaction at external proxies. Captured Telegram responses
remain available to their intended recipient, not the log. Cleanup runs immediately and hourly;
after an error it emits a safe event without exception details and retries in one minute.

## Metrics and Monitoring

The project has no metrics collector for this flow. The event counts and preview duration field
can support throughput, error-rate and latency calculations in an external log collector. No
Prometheus, Grafana, alerting, or resource metrics integration was added.

## Validation Results

- The capture tests exercise successful saves and transaction failures, check the error event and
  preview outcome, and ensure private URL, domain, content, and exception text do not occur in log
  messages or structured fields, including HTTP client and classifier debug logging.
- The existing capture suite checks that preview-service logs do not expose private links.
- Tests exercise a transient cleanup failure and retry, cancellation, and concurrent logging from
  a sensitive operation and an unrelated operation.
- `make check PYTEST_JOBS=4` passed: 910 tests, Ruff, formatting and Mypy. Four
  Starlette deprecation warnings were reported.
