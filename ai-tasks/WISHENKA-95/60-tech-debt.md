# WISHENKA-95: Technical Debt Analysis

## Shortcuts Taken

No temporary production changes were introduced. The redirect scenarios use the existing offline
replay route and controlled DNS; this verifies validation before dispatch, but does not replace
live-network integration coverage. The test cases use fixed addresses and response chains to keep
security expectations and dispatch order explicit. No deviation from the approved architecture was
identified.

## Code Quality Issues

No new production code or public interface was changed. The two dispatch spies repeat a small
amount of test instrumentation; with two cases, extracting a shared abstraction would add more
indirection than value. The circular redirect test intentionally reads HTTPX's client limit instead
of hardcoding a limit that could become stale.

## Missing Tests

The new matrix covers representative 6to4, Teredo, scoped and compressed IPv6 addresses; it is
not an exhaustive enumeration of IPv6 address space. Further address variants and live network
behavior are outside this task's agreed coverage; no specific additional follow-up was identified.
Python `ipaddress` classification and HTTPX behavior can change with supported dependency versions,
so policy expectation changes require review rather than silently relaxing assertions.

All tests in `tests/test_ssrf_and_response_limits.py`, including the new parameter cases, inherit
its explicit module-level `pytest.mark.timeout(30)` at line 83. No missing timeout blocker was
identified. Focused coverage passed 38 tests; `make analyze` passed. The full-suite baseline
comparison and all failing node IDs are recorded in `41-baseline-test-evidence.md`.

## Performance Concerns

No runtime performance change: this task changes tests only. Offline chains and the bounded HTTPX
redirect limit avoid external network dependencies and unbounded loops. The new cases add 12 passing
test items in the full run; no performance issue requiring a follow-up was identified.

## Follow-up Tasks

- **NON-BLOCKER — pre-existing:** the identical 13 non-browser failures on base `42fcae1` and
  the task tree are already tracked. The exact node IDs and comparison are in
  `ai-tasks/WISHENKA-95/41-baseline-test-evidence.md`:
  - [WISHENKA-264](https://pypost.atlassian.net/browse/WISHENKA-264): eight archive error-mapping
    cases in `tests/test_items_ui_error_mapping.py`.
  - [WISHENKA-235](https://pypost.atlassian.net/browse/WISHENKA-235): anonymous share cases in
    `tests/test_wish_card_giver_controls.py` and `tests/test_surprise_role_context.py`.
  - [WISHENKA-245](https://pypost.atlassian.net/browse/WISHENKA-245): notice cleanup failure.
  - [WISHENKA-226](https://pypost.atlassian.net/browse/WISHENKA-226): shared-view observability.
  - [WISHENKA-232](https://pypost.atlassian.net/browse/WISHENKA-232): repeatable migration.
- **NON-BLOCKER — pre-existing environment:** 115 identical browser setup errors are listed by
  node ID in `41-baseline-test-evidence.md`. Chromium is unavailable and `make deps-browser`
  requires an unavailable sudo password. Tracked as
  [WISHENKA-297](https://pypost.atlassian.net/browse/WISHENKA-297).

No new unticketed follow-up or acceptance-criteria blocker was identified.
