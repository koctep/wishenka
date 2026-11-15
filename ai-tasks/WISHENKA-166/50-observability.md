# WISHENKA-166: Observability Implementation

The task changes test infrastructure only (no production code). "Observability" here means the
diagnostics a developer or CI sees when the parallel test run is slow or goes wrong. Step 6 audited every
diagnostic of `tests/conftest.py`, `tests/xdist_support.py`, `tests/bench_suite.py` and the `Makefile`,
and fixed four small defects (section "Fixes"). No test semantics, thresholds or timeouts changed.

## Logging Implementation

### Added Logs

There is no application logging. The channels are pytest terminal output and `stderr`. Levels map as:
WARNING = a line starting with `WARNING:`; NOTICE = an informational line; ERR = a failing exit code.

| Source | Trigger | Text | Channel / level | Verdict |
| ------ | ------- | ---- | --------------- | ------- |
| `tests/xdist_support.py:35`, emitted at `tests/conftest.py:69` | `-n auto` and no fast storage (tmpfs missing, too small, or the default dir fails the 2 ms fsync probe) | `WARNING: slow test storage: running with one worker; expected about 16 minutes; set WISHENKA_TEST_TMPDIR to a fast directory (for example /dev/shm)` | stderr, WARNING, once, before the pytest header | OK after fix 4 (names the variable and an example). Seen only with `-n auto` (what `make test` uses); not with `-n 0` or an explicit `-n N` |
| xdist (not ours) | any parallel run | `created: 5/5 workers`, `5 workers [814 items]` | stdout header, NOTICE | OK: the only worker-count line; it shows the cap result (5 of 6 CPUs on the reference machine, memory bound) |
| `tests/conftest.py:113` (new hook) | controller, run ended with a non-zero status and basetemp was set by us | `test files kept for diagnosis: /dev/shm/wishenka-pytest-<uid>-<pid> (the next run removes it once this process is gone)` | terminal summary, NOTICE | OK after fix 1 (see Fixes). Path contains uid and pid only, no user name or home |
| `tests/conftest.py:96-99`, `:35` | end of every session | none unless teardown or worker shutdown hangs for 120 s; then `faulthandler` writes all thread stacks to stderr, process keeps running | stderr, ERR (diagnostic dump) | OK: silent on green. Covers only the end of the session, not hangs during tests |
| `Makefile:9-11`, `:62-66` | `timeout -k 30 $(TEST_WALL_LIMIT)` ends the run (exit 124) or the run is SIGKILLed (137) | `==> make test: stopped after the 600 s wall-clock limit or killed (exit 124); find the stuck test in the last lines above; reproduce: make test-serial PYTEST_ARGS=--timeout=120 plus the test ids (prints stacks)`, then `make: *** [Makefile:62: test] Error 124` | stderr, ERR | OK after fix 2 (before: only make's bare `Error 124`). The text is generic for 124 and 137 (137 can also be the OOM killer) |
| `Makefile:61` | start of `make test` / `make test-serial` | `==> Running Pytest test suite in parallel...` / `... serially...` | stdout, INFO | OK: tells which mode ran |
| `tests/bench_suite.py:116-156` | `make test-bench` | `nproc`, `free -m`, `command:`, `exit code`, `wall time: X s (budget 120 s)`, `memory low-water mark`, `/dev/shm peak used`, `tests: N total, P passed, F failed/errors, S skipped`, `passed set equals <file>: True/False`, `FAIL: wall time above the 120 s budget`, `RESULT: OK/FAIL` | stdout, INFO; exit code 0/1 | OK. After fix 3 it also names the first 10 failed ids and states why skipped tests fail the run |
| `tests/bench_suite.py:149` | no JUnit file | `no JUnit file written` | stdout, WARNING; RESULT FAIL | OK, accurate |
| `tests/browser_support.py` / `chromium_executable` (WISHENKA-110 code, unchanged) | no Chromium | actionable message from `check_chromium` (`make deps-browser`) | pytest failure/skip text | OK, out of this task's scope |
| per-test failure | browser test fails | sections `Page N diagnostics`; `diagnostics-N.txt`, `failure-N.png` in the kept `tmp_path` | report sections, ERR | OK: kept dir path makes the files reachable |

Secrets and personal paths: none printed. Paths are `/dev/shm/wishenka-pytest-<uid>-<pid>`; the
Chromium binary path is printed only by existing browser-support messages. `BROWSER_TEST_SECRET` is a
fixed test value and is never printed.

### Log Structure

- Structured logs: no (human text for a developer terminal and CI log; there is no log pipeline to parse).
- Includes context: yes (path, limit, exit code, counts).
- Levels used: WARNING (`WARNING:` prefix), NOTICE/INFO (plain lines), ERR (non-zero exit with a message).
- Happy path: the run prints only the `make` banner, the pytest header with the xdist `created:` line, the
  per-test lines and the final `814 passed` line. No project-specific noise (checked with `make test`).

### Fixes made in Step 6

1. `tests/conftest.py:96-124`: the "kept for diagnosis" line was written to stderr in `pytest_unconfigure`,
   so in a pipe (CI) it landed mid-output, glued to the progress line (`[100%]test files kept ...`) and
   before the failure report. Now written by `pytest_terminal_summary` (controller only, status non-zero),
   in report order, with the note that the next run removes it. Cleanup after green is unchanged.
2. `Makefile:62-66`: a wall-clock kill showed only `Error 124`. Now prints a one-line explanation and the
   reproduction command; the exit code is preserved (`exit $$rc`). Initial wording mentioned a faulthandler
   dump; verified false for a kill (SIGTERM does not trigger it), so the text points at the last lines and at
   `--timeout=120` (pytest-timeout, already a dev dependency) instead.
3. `tests/bench_suite.py:139-142`: failed ids and the skipped-count reason were not printed (only counts and
   `RESULT: FAIL`). Now `FAILED: <id>` (first 10) and `FAIL: skipped tests are not allowed ...`.
4. `tests/xdist_support.py:35-38`: the slow-storage warning now suggests a concrete directory (`/dev/shm`).

## Scenarios: what the developer sees and how to diagnose

| Scenario | Observed | Diagnose / act |
| -------- | -------- | -------------- |
| Green `make test` | banner, `created: 5/5 workers`, 814 `PASSED` lines, `814 passed, 5 warnings in 45.9 s`; `/dev/shm` and `/tmp/wk-*` empty, no chromium | nothing |
| Slow storage (`WISHENKA_TEST_TMPDIR=/nonexistent make test PYTEST_ARGS="tests/test_browser_prerequisites.py -q"`) | `WARNING: slow test storage: ...`, then `created: 1/1 worker` | set `WISHENKA_TEST_TMPDIR=/dev/shm` (or another tmpfs); `WISHENKA_TEST_TMPDIR=disk` forces disk on purpose; `WISHENKA_TEST_WORKERS=N` overrides the count (no warning then) |
| Failing test | normal pytest failure report; with fast storage the tail shows `test files kept for diagnosis: /dev/shm/wishenka-pytest-501-<pid> (...)`; `tmp_path` in the traceback is under that path (`popen-gwN/<test>`) | open the directory (database copies, browser diagnostics/screenshots); rerun the single test with `make test-serial PYTEST_ARGS="tests/x.py::t"`; `rm -rf` the path when done or let the next run do it |
| Slow run, no failure | green but above 120 s | `make test-bench` (wall time, memory low-water mark, shm peak, counts); `make test PYTEST_ARGS=--durations=20` for the slowest tests; check the `created:` line for a reduced worker count and the warning above |
| Hung run | no output for long; at 600 s `timeout` stops it (grace 30 s) and prints the Makefile line, exit 124 | the last `tests/...::name` line without a result is the stuck test; reproduce with `make test-serial PYTEST_ARGS="--timeout=120 <id>"`, which prints stacks; a hang only at session end prints `faulthandler` stacks after 120 s. Raise `TEST_WALL_LIMIT` only if the suite really got slower |
| OOM-killed worker | xdist reports `node down: Not properly terminated` / `worker 'gwN' crashed`; or exit 137 with the Makefile line | `free -m`; run with `WISHENKA_TEST_WORKERS=2`; the cap `(MemAvailable - 1200) // 600` already limits workers; compare the memory low-water mark in `make test-bench` |
| Orphans / leftovers | killed run leaves `/dev/shm/wishenka-pytest-<uid>-<pid>[-tmp]` and `/tmp/wk-*` (verified after a forced timeout) | the next run removes entries whose pid is dead (`remove_stale`, `remove_stale_disk_dirs`); manual: `ls /dev/shm /tmp \| grep -E 'wishenka-pytest\|wk-'`, `pgrep -a chrom` (Chromium is started via `setpriv`/killpg and reaped at session end) |

## Metrics Implementation (if applicable)

No metrics exporter applies (no service, no Prometheus/Grafana/alerting). Only the benchmark report
produces numbers, printed by `make test-bench` (`tests/bench_suite.py`).

### Performance Metrics

- **Wall time** of `make test` vs the 120 s budget (`bench_suite.py:122-129`), exit 1 above budget.
- **Counts**: total, passed, failed/errors, skipped from the JUnit file; passed-set comparison with earlier
  runs (`--compare`).

### Business Metrics

None.

### System Health Metrics

- **Memory**: minimum `MemAvailable` over the run, sampled once per second (`Sampler`, system-wide, not per
  process); `/dev/shm` peak usage.
- **Reference data**: `nproc` and `free -m` printed before the run.

Not measured: per-test or per-worker durations (use `--durations`), per-worker memory, CPU load, fsync
latency over time (only the 5-sample probe at start), disk usage outside `/dev/shm`, run-to-run history or
trends, orphan-process count (a manual check). Samples are 1 s apart, so short memory peaks can be missed.

## Monitoring Integration

- [ ] Prometheus metrics: not applicable
- [ ] Grafana dashboards: not applicable
- [ ] Alerting rules: not applicable (the guards are the Makefile wall-clock limit and the bench budget)
- [ ] Log aggregation: not applicable (CI log is the only sink)

## Validation Results

- [x] Messages are accurate and actionable after the fixes (slow-storage, kept-dir, wall-clock kill, bench failure lines each observed)
- [x] Metrics are collected correctly (bench report unchanged apart from two extra failure lines; logic covered by `tests/test_parallel_run_contract.py`)
- [x] Logging works in error scenarios (failing scratch test outside the repo, forced `TEST_WALL_LIMIT=3` kill, `WISHENKA_TEST_TMPDIR=/nonexistent`)
- [x] Large data structures are not logged; no secrets or personal paths printed
- [x] `tests/test_parallel_run_contract.py` 16 passed; `make analyze` green (136 files); `make test` 814 passed in 45.9 s (50.1 s wall); `/dev/shm`, `/tmp/wk-*` empty, no chromium

## Notes

- The slow-storage warning and the worker count exist only on the `-n auto` path (hook
  `pytest_xdist_auto_num_workers`); an explicit `-n N` skips both by design.
- `faulthandler` only covers the session end (120 s timer). A hang inside a test is covered by the Makefile
  limit plus `--timeout` on a serial rerun; no `faulthandler_timeout` is configured (changing it would alter
  run behaviour, left for Step 7 to judge).
- A run killed by SIGTERM/SIGKILL cannot clean its `/dev/shm` directories; the next run does.
