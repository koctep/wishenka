# WISHENKA-124: Observability Implementation

## Scope Decision

The task changed only test tooling and developer infrastructure (`tests/browser_support.py`,
`tests/conftest.py`, Makefile `deps-browser`, the `ci.yml` step, `doc/dev/testing.md`). No
production runtime code (`wishenka/`) changed. Production logging, metrics, dashboards and alerting
are therefore not applicable. The relevant observability is the diagnostics that a developer or CI
log reader sees. They were reviewed and no code change was needed.

## Logging Implementation

### Added Logs

No Python `logging` calls were added. Adding them to test helpers or to production code would be
noise.

- **EMERG / ALERT / CRIT / ERR / WARNING / NOTICE / INFO / DEBUG**: N/A. No production code was
  changed, and the helper is a CLI and fixture that report through stdout/stderr and the pytest
  report.

### Developer / CI Diagnostics (existing, verified)

- **Success, `make deps-browser`** (stdout): prints `<resolved path> <version>`, for example
  `/usr/bin/chromium Chromium 156.0.8078.79 built on Debian GNU/Linux 13 (trixie)`, exit 0. In CI
  this is the log line that shows the chosen browser (step "Install browser for UI tests").
  The snap-confinement warning is added only on the fixture path (`check_chromium`), not by
  the CLI, which prints just the path and version.
- **Not found or not runnable** (stderr, exit 2 or 3): `missing_message` names what is missing,
  that is, the unusable `WISHENKA_CHROMIUM_BIN` value or the searched candidate names
  (`chromium, chromium-browser, google-chrome-stable, google-chrome`). It lists each probed
  candidate with its failure cause (timeout, exec error, exit code plus stderr truncated to 300
  characters), a snap hint, the fix (`make deps-browser`, `WISHENKA_CHROMIUM_BIN`,
  `doc/dev/testing.md`) and the local opt-out. Exit codes 2 and 3 distinguish "absent" from
  "present but broken".
- **Fixture `chromium_executable`**: a missing browser is a setup ERROR with the same message
  (`pytrace=False`, so no traceback noise). It is a SKIP only with the explicit local opt-out
  `WISHENKA_SKIP_BROWSER_TESTS=1`, and the opt-out is ignored when `CI` is set. The skip reason
  starts with the opt-out and then repeats the full cause. It is visible with `-rs`.
- **Verified manually**: `make deps-browser` gives rc 0 with path and version. An unusable
  `WISHENKA_CHROMIUM_BIN=/nonexistent` gives rc 2 with the message above. With the opt-out set,
  `pytest -rs` shows `SKIPPED ... WISHENKA_SKIP_BROWSER_TESTS=1: browser tests skipped. <cause>`.

### Log Structure

- Structured logs: no (not applicable; human-readable multi-line text for developers).
- Includes context: yes (path, version, candidates, probe failure cause, remedy).
- Log levels: none; stdout is used for success and stderr for failure.

## Metrics Implementation (if applicable)

N/A. There is no runtime service behind this change, so there is nothing to measure in production.

### Performance Metrics

- N/A. The only bounded cost is the probe, which is limited by `DEFAULT_PROBE_TIMEOUT` = 10 s per
  candidate. A timeout is reported as a failure cause.

### Business Metrics

- N/A. No product behavior changed.

### System Health Metrics

- N/A. Browser availability is reported per run by the diagnostics above (CI step result).

## Monitoring Integration

- [ ] Prometheus metrics: N/A (no runtime code)
- [ ] Grafana dashboards: N/A
- [ ] Alerting rules: N/A (a missing browser fails the CI job `make deps-browser` / `make check`
  directly)
- [ ] Log aggregation: N/A (the GitHub Actions job log is the sink)

## Validation Results

- [x] Messages are correctly formatted and name the missing item and the candidates (covered by
  `tests/test_browser_prerequisites.py`, 46 tests, assertions untouched).
- [ ] Metrics are collected correctly: N/A
- [x] Failure scenarios work (not found, unusable explicit binary, opt-out skip with `-rs`; checked
  manually).
- [x] Large data structures are not logged (probe stderr truncated to 300 characters).
- [ ] Metrics available for monitoring: N/A

## Notes

Considered a `pytest_report_header` that prints the chosen browser on every run. It was rejected:
CI already logs the browser in the `make deps-browser` step, and a header would run an extra probe
on every pytest invocation, including non-browser runs. No source change was made, so
`make analyze` was not re-run in this step.
