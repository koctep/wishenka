# WISHENKA-27: Observability Implementation

## Logging Implementation

The polling process applies the existing `LOG_LEVEL` and `LOG_JSON` settings. JSON mode uses the
existing formatter and includes the following event fields:

| Level | Event | Context | Meaning |
| --- | --- | --- | --- |
| INFO | `bot_start_handled` | `outcome` | A response was sent for the requested entry. |
| ERROR | `bot_start_failed` | none | Language lookup or response delivery failed. |
| INFO | `public_entry_viewed` | `identified` | The public Mini App view was prepared. |
| WARNING | `public_entry_unavailable` | none | A public link could not be resolved or used. |

Outcomes are bounded values: `menu`, `public_link`, and `invalid_link`. The new events do not
include link capabilities, Telegram identifiers, message bodies, wishlist data, exception text,
or credentials. An aiogram error handler consumes entry errors after recording a safe event,
preventing the dispatcher from logging raw exceptions or tracebacks. The Uvicorn access filter
installed at application creation masks capability paths and strips other query strings. Reverse
proxies and external access logs must independently redact capability URLs and query strings.

## Metrics and Monitoring

The project has no dedicated metrics collector for this flow; no new in-process counter was
introduced. Structured events can support operational counts and failure rates in a log collector.
No Prometheus, Grafana, alerting, or aggregation integration was added in this step. Existing
infrastructure is responsible for component health and resource metrics.

## Validation Results

- Tests exercise normal and invalid bot starts, JSON event fields, and error logging without
  exposing the link or exception contents, including the dispatcher polling error path.
- A live Uvicorn subprocess test checks actual access output for a public view and query string.
- Tests exercise successful and unavailable public views and assert that their event records omit
  link capabilities and wishlist titles.
- Targeted bot entry tests passed: 17 tests, one Starlette deprecation warning. The Makefile
  target ran `tests/test_bot_start_repro.py` and `tests/test_bot_entry_repro.py` with no workers.
- `make check PYTEST_JOBS=4` passed: 876 tests, four Starlette deprecation warnings, Ruff,
  formatting, and Mypy.
- After the error-handler and access-log tests, `make test PYTEST_JOBS=4` passed: 877 tests,
  four Starlette deprecation warnings. Ruff and Mypy passed for the changed Python files.
