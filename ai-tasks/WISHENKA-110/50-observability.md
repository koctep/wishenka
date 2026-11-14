# WISHENKA-110: Observability Implementation

## Scope Decision

The task added test infrastructure only: `tests/browser_cdp.py`, `tests/browser_helpers.py`,
`tests/browser_assets/htmx_stub.js`, fixtures in `tests/conftest.py` and three browser test
modules. No production code (`wishenka/`) changed. Production logging, metrics, dashboards and
alerting are N/A. The relevant observability is what a developer or a CI log reader sees when a
browser test fails. That was reviewed against the code. No genuine diagnostics gap was found, so no
source change was made (and `make analyze` and the test run were not repeated, since no file in
`tests/` or `wishenka/` was touched in this step).

## Logging Implementation

### Added Logs

No Python `logging` calls and no `console.*` calls were added. Test helpers report through pytest
assertion messages and report sections.

- **EMERG / ALERT / CRIT / ERR / WARNING / NOTICE / INFO / DEBUG**: N/A. No runtime code changed;
  the production reorder/toggle logs from WISHENKA-108/109 are unchanged.

### Developer / CI Diagnostics (existing, reviewed)

- **Page snapshot** (`CdpPage.snapshot()`, `tests/browser_cdp.py`): URL and `scrollY`, body class,
  one line per card (`data-item-id`, `aria-expanded`, `hidden`, class), `window.__ajaxCalls`,
  the first 2000 characters of `#items-list` outerHTML, the last 20 console entries (type and
  text), the last 20 requests (method, path, status, post body), `external_requests` (non-local
  URLs that were blocked) and the last 5 driver errors. If the page cannot be evaluated, the
  snapshot says `(page state unavailable: ...)` and still prints the console, request and
  external lists. The 2000-character cut applies only to the raw HTML; the structured per-card
  lines are not cut, so order and state stay complete. Console text and post bodies are not cut
  (they are short in these tests).
- **Failure report**: `pytest_runtest_makereport` (`tests/conftest.py`) appends a section
  `Page N diagnostics` with the snapshot to the call-phase report of a failed test. It is in the
  normal pytest output, so it appears in the CI job log.
- **Assertion messages**: the helpers (`assert_order`, `assert_cards`, `assert_gesture_clean`,
  no-reorder asserts, focus assert, `assert_clean_console`) and `CdpPage.query`/`drop_outside`
  failures include the expected value, the actual value and the snapshot.
- **`PageWaitTimeout`** (subclass of `AssertionError`): the message is
  `timed out after <N>s waiting for: <description>`, then `last value: <last predicate result>`,
  then the snapshot. It names what was awaited and the last observed value. Other driver
  failures name the CDP method or URL (`CDP <method>: no response within Ns`, `CDP <method>
  failed`, `navigation to <url> failed`, `<url> did not finish loading within Ns`, `page exception
  in <expression>: <text>`), and `CdpBrowser.start` names an early Chromium exit with its code.
- **`assert_clean_console`**: fails on any console warning, error or uncaught exception and
  prints the offending entries plus the snapshot. It is an explicit call in tests (not an autouse
  fixture, to avoid a new marker under `--strict-markers`). Tests that expect the
  `wishlist.js: reorder skipped` warning assert it explicitly.
- **External requests**: scripts the page tries to load from outside are blocked, recorded in
  `external_requests` and shown in the snapshot, so a hidden network dependency is visible
  instead of causing a slow or flaky test.
- **Missing browser**: unchanged from WISHENKA-124. Setup ERROR with a message naming the missing
  binary and the fix, or a SKIP with the explicit local opt-out (ignored when `CI` is set).
- **htmx stub**: `window.__ajaxCalls` records `verb`, `url`, `target`, `swap`, `values` for every
  `htmx.ajax` call, and `window.__ajaxPending` counts calls in flight. Both are included in the
  snapshot (`ajax calls:`) and readable in tests through `ajax_calls()`. This is the debugging
  aid for "which request did the gesture produce".
- **Artifacts on failure**: the `_browser_pages` teardown writes `diagnostics-N.txt` (same text as
  the snapshot) and `failure-N.png` into pytest's `tmp_path`, each in its own `suppress` so a dead
  tab does not hide the test failure.

### Limitations (stated, not fixed)

- **CI and the PNG**: `.github/workflows/ci.yml` runs `make deps`, `make deps-browser`,
  `make check` and has no `upload-artifact` step. On a CI failure the snapshot text is in the log
  (report section), but `failure-N.png` and `diagnostics-N.txt` stay in the runner's temp
  directory and are lost when the job ends. Locally they are under pytest's `tmp_path` (by
  default `/tmp/pytest-of-<user>/pytest-<run>/<test>/`), and pytest keeps only the last 3 base
  directories, so older ones are removed. The failure report does not print this path (the files
  are written at teardown, after the report section is built); `--basetemp` or `pytest -v` plus
  `--tb` do not change that. A developer finds them by the test name under the basetemp.
- **Duplicated text**: a `PageWaitTimeout` message already contains a snapshot and the hook adds
  a second one in the report section. This is noise, not a gap, and cheap to ignore.
- Not added, because the text snapshot already shows the DOM state and request tail and a
  screenshot rarely adds to it for logic tests: upload of failure artifacts in CI. Recorded as a
  follow-up candidate for Step 7: `actions/upload-artifact` with `if: failure()` over the pytest
  basetemp (needs `--basetemp` in `make check` or a fixed path), if a visual-only failure ever
  needs it.

### Log Structure

- Structured logs: no (human-readable multi-line text for developers).
- Includes context: yes (expected, actual, last wait value, DOM state, console, requests).
- Log levels: none; the pytest report is the channel.

## Metrics Implementation (if applicable)

N/A. There is no runtime service behind this change.

### Performance Metrics

- N/A. Every wait is bounded (`wait_for` default 5 s, CDP command timeout, page load timeout,
  module `timeout(45)`), and a timeout is reported with its description. Suite wall time for the
  three modules is about 35-40 s (measured in Step 4); pytest `--durations` can be used ad hoc.

### Business Metrics

- N/A. No product behavior changed.

### System Health Metrics

- N/A. Chromium start and liveness are reported by the fixture (`ensure_alive`, early-exit error).

## Monitoring Integration

- [ ] Prometheus metrics: N/A (no runtime code)
- [ ] Grafana dashboards: N/A
- [ ] Alerting rules: N/A (a failing browser test fails the CI job `make check`)
- [ ] Log aggregation: N/A (the GitHub Actions job log is the sink)

## Validation Results

- [x] Messages are correctly formatted and carry description, last value and snapshot (code
  review of `wait_for`, `snapshot`, helper asserts).
- [ ] Metrics are collected correctly: N/A
- [x] Failure scenarios: the hook, `PageWaitTimeout` and the artifact writer are reached by the
  Step 4 mutation runs (each failing test reports an assertion error with a snapshot, M1-M14);
  the contents of `diagnostics-N.txt` and `failure-N.png` were not inspected, so this is a
  code-reading claim, not a verified one.
- [x] Large data structures are not logged (HTML cut to 2000 characters, console and request
  tails limited to 20 entries, driver errors to 5).
- [ ] Metrics available for monitoring: N/A

## Notes

No code change, so the 53 browser tests and `make analyze` result from Step 5 remain valid.
