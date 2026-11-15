# WISHENKA-166: Technical Debt Analysis

Scope: the uncommitted change set of WISHENKA-166 (Steps 3 to 6) over HEAD `4148ec2`: `Makefile`, `pyproject.toml`,
`tests/conftest.py`, `tests/browser_cdp.py`, `tests/xdist_support.py` (new), `tests/bench_suite.py` (new),
`tests/test_parallel_run_contract.py` (new, 16 collected cases from 13 functions), and the three modified modules
`tests/test_browser_prerequisites.py`, `tests/test_wishlist_management_browser.py`, `tests/test_wishlist_sections_ui.py`.
`wishenka/` is untouched. Nothing was changed in code, tests or the Makefile in this step (docs only). The untracked `core`
file (WISHENKA-126) and `ai-tasks/sprint-2110/` are not part of this change set.

Evidence gathered in this step: every file:line below was read in the current tree; one more full `make test` was run
(`814 passed in 44.14 s`, `/dev/shm` empty afterwards, no Chromium left) with `--durations` and a JUnit file to measure the
critical path; one `pytest --collect-only -m "not timeout"` run (see the timeout rule).

## Verdict

**No BLOCKER for closing WISHENKA-166.** Every measurable DoD item of `10-requirements.md` that Steps 1 to 6 own is met on the
reference machine (6 cores, 5909 MiB): DoD 1 and 2 (6 parallel runs 48.9 to 55.3 s wall, 814 passed each, sets equal; today
44.1 s pytest time), 3 (serial 114 s, same 814), 4 (798 + 16 contract tests, no skip, xfail or deselect), 5, 6, 7 (no marker
removed, no limit raised, no retry plugin), 8 (min `MemAvailable` 1908 MiB, no OOM), 9 (no leftovers), `make analyze` part of 10.

Honest reservations, none of which breaks the DoD:

1. **DoD 10 is only half met today**: `doc/dev/testing.md` does not describe the fast run, `-n 0`, the `WISHENKA_TEST_*`
   switches and the measured figures. That is the explicit job of Step 8, so it stays open until Step 8 passes (carried to
   Step 8, see D-14). If the task were closed without Step 8, DoD 10 would be a real gap.
2. The 120 s budget is proven **only on the reference machine** (requirements N-1 and Q-5 say so on purpose). Nothing proves it
   on CI (`ubuntu-latest`, 2 or 4 vCPU) or on a slow-storage laptop (about 16 min by design). A reader of the roadmap line
   "120 s" must not read it as a general guarantee (D-9, D-10).
3. Test coverage of the new infrastructure is thin: the 16 contract cases were written as a red repro and cover the pure
   helpers and two Makefile and pyproject facts, not the process-reaping, stale-cleanup and fallback paths (D-1 to D-5). A
   mutation of `read_debug_port` (`isdigit` condition) passes all 16 (known; confirmed by reading that no test imports it
   directly, only the Chromium tests use it).
4. Wording nit in `40-development.md` line 51 ("12 full parallel runs", whose parenthesis adds up to 14, while the roadmap says
   6 final-configuration runs): documentation inconsistency only (D-15).

## Python test-timeout rule

Outcome: **satisfied, no BLOCKER.** Checked with `ast` over the four test modules added or modified by this task:

| File | Test functions | Timeout marker |
| ---- | :------------: | -------------- |
| `tests/test_parallel_run_contract.py` | 13 (16 cases with parametrisation) | module `pytestmark = pytest.mark.timeout(30)` (line 27) |
| `tests/test_browser_prerequisites.py` | 36 | module `pytestmark = pytest.mark.timeout(30)` (line 33) |
| `tests/test_wishlist_management_browser.py` | 1 | module `pytestmark = pytest.mark.timeout(45)` (line 19) |
| `tests/test_wishlist_sections_ui.py` | 7 | module `pytestmark = pytest.mark.timeout(60)` (line 36) |
| `tests/xdist_support.py`, `tests/bench_suite.py`, `tests/conftest.py`, `tests/browser_cdp.py` | 0 (helpers, fixtures) | not applicable |

- `.venv/bin/pytest --collect-only -q -m "not timeout" -p no:cacheprovider -n 0` reports `no tests collected (814 deselected)`:
  no collected test of the whole suite lacks a marker; total collected is 814.
- The fixture `tmp_path` override in `test_browser_prerequisites.py:38-48` and the autouse and session fixtures are covered by
  the module marks of the tests that use them.
- Bounded waits added by this task: the CDP port wait is bounded by 10 s (`browser_cdp.py` `_launch`), the two own-Popen tests
  by 8 s deadlines (`test_wishlist_management_browser.py:114`, `test_wishlist_sections_ui.py:420`), `stop_chromium` by
  `TERMINATE_TIMEOUT` 5 s twice, `bench_suite` subprocess calls by 10 s (`_run`). No unbounded loop or wait was found.
- Side note (not a marker issue): the `-m "not timeout"` command printed `test files kept for diagnosis` because pytest exited
  with status 5 (nothing collected); see D-6.

## Shortcuts Taken

| # | Shortcut / assumption | Where | Class | Priority |
| - | --------------------- | ----- | :---: | :------: |
| S-1 | Speed comes from moving test files to tmpfs (`/dev/shm`) and running 6 workers, not from making the per-test setup cheap. The root cause (a SQLite migration with `fsync` for every test, setup 56 % of serial time, roadmap line 30) is untouched; on storage with slow `fsync` the suite still takes about 16 min (`SLOW_STORAGE_WARNING`, `xdist_support.py:36`) | `xdist_support.py:10-14, 36-39`, `conftest.py:74-93` | NON-BLOCKER | Medium |
| S-2 | `--dist loadfile` chosen on thin evidence: 3 runs each, median 46.2 s vs 49.4 s, while run-to-run spread of the final configuration is 48.9 to 55.3 s (40-development.md DoD table), so the 3 s difference is inside the noise. It was chosen for safety (module-scoped state and the per-module browser setups stay in one worker) rather than proven faster | `Makefile:62` | NON-BLOCKER | Low |
| S-3 | One Chromium per xdist worker (session fixture `chromium_browser`, `conftest.py:176-188`), up to 6 browsers plus the two own-Popen tests; peak use 2.7 to 2.9 GiB of 5.9 GiB. Accepted because the worker cap (`PER_WORKER_MB = 600`) is derived from it, not measured per browser | `conftest.py:176-188`, `xdist_support.py:23-25` | NON-BLOCKER | Low |
| S-4 | The two old tests keep their own Chromium start code (copy of the launch arguments) and only got the new helpers; they were not moved to the shared `chromium_browser` fixture because that would change what they test (DoD 4) | `test_wishlist_management_browser.py:99-110`, `test_wishlist_sections_ui.py:406-418` | NON-BLOCKER | Low |
| S-5 | Hang guard is a plain `timeout -k 30 600` around pytest. It kills only the pytest controller process, with no stack dump; `faulthandler` is armed only at session finish (`conftest.py:99`) | `Makefile:10-11, 62`, `conftest.py:96-99` | NON-BLOCKER | Low |
| S-6 | The pytest `tmp_path` fixture is overridden inside `test_browser_prerequisites.py:38-48` to get an exec-capable disk directory, while `test_parallel_run_contract.py:191-199` defines a second, independent `disk_tmp_path` fixture with the same body (`mkdtemp` under `WISHENKA_TEST_DISK_TMPDIR`). The shared `xdist_support.disk_mkdtemp` already exists, but the contract file does not use it and uses another prefix (`wk-contract-`, so `remove_stale_disk_dirs` never cleans it: it needs `wk-<kind>-<pid>-`) | `test_parallel_run_contract.py:194-195`, `xdist_support.py:111-126, 183-189` | NON-BLOCKER | Low |

## Code Quality Issues

| # | Observation | Evidence | Class | Priority |
| - | ----------- | -------- | :---: | :------: |
| Q-1 | Hardcoded values, none configurable: fsync probe threshold `FSYNC_FAST_SECONDS = 0.002` with 5 samples (`xdist_support.py:26-27`), `MIN_FREE_MB = 48`, `RESERVE_MB = 1200`, `PER_WORKER_MB = 600` (`:23-25`), wall guard 600 s is configurable (`Makefile:10`), session-end dump `SESSION_END_DUMP_SECONDS = 120` (`conftest.py:35`), Chromium start wait 10 s (`browser_cdp.py` `_launch`), `TERMINATE_TIMEOUT = 5.0`. The fsync rule is asymmetric: a noisy neighbour can classify good disk storage as slow, and then the run uses 1 worker and takes minutes, with only a stderr warning. `WISHENKA_TEST_WORKERS` silently ignores a non-digit or `0` value (`:177`) | listed lines | NON-BLOCKER | Low |
| Q-2 | Platform assumptions in helpers that are plain Linux: `os.sched_getaffinity` (`xdist_support.py:147`, absent on macOS and Windows), `os.getuid` (`:66, 95, 122`, absent on Windows), `os.killpg` and `start_new_session` (`browser_cdp.py:614, 622`), `/proc/meminfo`, `/sys/fs/cgroup/memory.max` (`xdist_support.py:129-130`, fall back to "10**6 MiB = unknown", so no memory cap), `setpriv` (optional by `shutil.which`), `timeout` command in `Makefile:11` (empty when absent, so no guard, silently). `bench_suite.py` also calls `nproc` and `free -m` (`:116-117`) and `/dev/shm`. Behaviour per platform is in the CI/portability table below | listed lines | NON-BLOCKER | Medium |
| Q-3 | The contract tests depend on internal names and on Linux: `test_worker_cap_hook_is_registered_as_optional` parses `conftest.py` with `ast` for the name `pytest_xdist_auto_num_workers` and the text `optionalhook=True` (`test_parallel_run_contract.py:246-263`); `test_fsync_probe_is_fast_on_tmpfs` asserts that `/dev/shm` exists (`:166-173`), so on macOS or Windows it **fails** instead of skipping; the failure message of `test_make_test_runs_in_parallel` still says `--dist load` (`:63-65`) while the Makefile uses `loadfile` (the assertion is only `"--dist" in stdout`); `test_choose_workers` accepts a set `{5, 6}` (`:128`) so an off-by-one in the formula would pass | listed lines | NON-BLOCKER | Low |
| Q-4 | `remove_stale_disk_dirs` calls `entry.stat()` without a guard (`xdist_support.py:122`); if two controllers of the same user start at the same moment and both see a dead run's directory, the second `stat` can raise `FileNotFoundError` inside `pytest_configure` (`conftest.py:84`) and abort the whole run. Found by reading, not reproduced (needs two simultaneous starts) | `xdist_support.py:111-126` | NON-BLOCKER | Low (Bug) |
| Q-5 | A pytest exit status that is not 0 is treated as "failed run": exit 5 (nothing collected, e.g. `-k` that matches nothing, `-m "not timeout"`) keeps the `/dev/shm/wishenka-pytest-<uid>-<pid>` directory and prints `test files kept for diagnosis`. Reproduced in this step with the timeout-rule command: message printed and directory left behind (removed by hand afterwards). Harmless (empty directory, next run removes it) but the message is false | `conftest.py:108, 113-120` | NON-BLOCKER | Low (Bug) |
| Q-6 | `tests/bench_suite.py` has no `deps` prerequisite of its own (`Makefile:72-74` `test-bench` has none, the module only calls `make test`, which has it); on a fresh checkout `make test-bench` fails at `$(PYTHON)` (`.venv/bin/python` missing) before `make deps` can run. Also Linux-only commands (Q-2) | `Makefile:72-74`, `bench_suite.py:116-123` | NON-BLOCKER | Low |
| Q-7 | `.venv` is Python 3.13.5 while the project declares `>=3.12` and CI uses 3.12 (`ci.yml`, `setup-python` 3.12); the new code uses only 3.12-safe syntax by reading, but the parallel suite was never run on 3.12 (same finding as WISHENKA-3 and 124, not new) | `ci.yml`, `pyproject.toml` | NON-BLOCKER | Low (existing note) |
| Q-8 | The untracked 197 MB `core` file in the repository root is **not ignored** (`.gitignore` has no `core` line; `git check-ignore -v core` prints nothing; `git ls-files core` is empty). Existing Jira WISHENKA-126 (ticketed in WISHENKA-111, 108, 109, 110, 112, 23, 24). It must not be committed: `td-99-commit` stages by explicit path. A `.gitignore` entry `core` (and `core.*`) would remove the risk for every future task; it can be added in WISHENKA-126, not here (scope guard: no unrelated change) | `.gitignore`, repo root | NON-BLOCKER | Medium (existing) |

## Missing Tests

| # | Gap | Evidence | Class | Priority |
| - | --- | -------- | :---: | :------: |
| M-1 | `read_debug_port` has no direct unit test: empty file, file with only a newline, `"abc"`, `"45678\n/devtools/..."`, whitespace. A mutation of the `isdigit` condition passed all 16 contract tests. The only indirect coverage is the Chromium tests (`test_cdp_launch_waits_for_complete_port_file` covers only the "empty, then valid" order through `CdpBrowser`, `test_parallel_run_contract.py:202-219`) | `browser_cdp.py` `read_debug_port`, `test_parallel_run_contract.py` | NON-BLOCKER | Medium |
| M-2 | Process reaping is untested: `start_new_session`, `setpriv --pdeathsig KILL`, `os.killpg` in `stop_chromium`, the `atexit` hook `_kill_live_browsers`, and "browser died, `_launch` reaps its group" (`self.stop()` at the start of `_launch`). Only manual evidence exists (no orphan after a killed run, 40-development.md). A fake browser that forks a child would test the group kill without Chromium | `browser_cdp.py:595-660` | NON-BLOCKER | Medium |
| M-3 | Stale cleanup is untested: `remove_stale` and `remove_stale_disk_dirs` (dead pid removed, live pid kept, another user's directory kept, name without a pid kept), and the pid-reuse case (a dead run's pid taken by another process leaves the directory in place until that process ends; a reused pid of an unrelated live process hides it forever). Also a pid from another pid namespace (containers sharing `/dev/shm`) looks dead and its directory would be deleted under a live run | `xdist_support.py:92-126` | NON-BLOCKER | Medium |
| M-4 | The slow-storage fallback is untested end to end: `plan_storage` (explicit `WISHENKA_TEST_TMPDIR`, value `disk`, unusable `/dev/shm`, probe on the default temp directory), `plan_workers` (override digits, warning text), `available_memory_mb` (cgroup `max`, missing files) and the hook output on stderr. Only `choose_workers` and `pick_fast_basetemp` with `fast=False` are checked | `xdist_support.py:129-185` | NON-BLOCKER | Medium |
| M-5 | `Makefile` behaviour is untested: the exit 124 and 137 hint (`:63-65`), the wall guard (`TEST_WALL_LIMIT`), `test-bench` target existence, `--dist loadfile` value. The contract only checks `-n` and the word `--dist` | `Makefile:60-66, 72-74` | NON-BLOCKER | Low |
| M-6 | `pytest_terminal_summary` (kept-directory line, `conftest.py:113-120`), `pytest_unconfigure` keep-on-failure rule (`:102-110`) and `pytest_sessionfinish` faulthandler arming (`:96-99`) have no test; `bench_suite.parse_junit` and the `--compare` logic have none either (it is a tool, but its equality check is part of DoD 2 evidence) | listed lines, `bench_suite.py:45-58, 143-147` | NON-BLOCKER | Low |

## Performance Concerns

Measured in this step (`make test --durations=25` plus JUnit): 44.14 s pytest time, 814 passed.

- **Sum of all test times is 161.9 s**; divided by 6 workers that is 27 s, so about 17 s (40 %) of the 44 s is not useful test
  time: worker start and collection (about 2 s per worker), the per-worker Chromium start, and load imbalance.
- **Critical path under `loadfile`**: the largest modules run in one worker each: `test_shared_inventory_multiprocess` 25.2 s,
  `test_booking_ceiling_r5` 19.6 s (its `test_repeated_contention_many_copies` alone 11.96 s), `test_wishlist_touch_reorder_browser`
  15.1 s, `test_wishlist_migrations_concurrency` 10.8 s, `test_wishlist_cards_browser` 11.9 s. The 25 s module alone is 57 % of
  the wall time, so adding CPUs beyond about 6 cannot make the run faster than about 30 s without splitting those modules or
  using `--dist worksteal`/`loadgroup`.
- **Browser modules** sum to 46.5 s of test time (29 %), plus a Chromium per worker.
- **Headroom against 120 s**: about 65 s on the reference machine. Extrapolation, not measured: a 2-vCPU runner needs at least
  162 s / 2 = 81 s of test time plus overhead (about 95 to 110 s), within budget only barely; a 4-vCPU runner about 55 to 65 s.
  The two multiprocess modules spawn their own processes, so on fewer cores they also compete with the workers.
- **Slow-storage machines** (virtiofs `/tmp`, networked disks, `/dev/shm` unavailable or too small): one worker, about 16 min,
  by design (`xdist_support.py:36-39`); trying to use six workers there gave 981 s with 28 failed and 9 errors (roadmap line 30).
  The structural fix (migrate once and copy a template database per test, as the browser fixture `migrated_db_template` already
  does at `conftest.py:191-210`, or relax `synchronous` for test databases) is a separate task because it touches test setup.
- **Memory**: peak in use 2.7 to 2.9 GiB for 6 workers (about 450 to 480 MiB per worker including Chromium), minimum
  `MemAvailable` 1908 MiB, so the cap `(mem - 1200) // 600` is conservative; on a 4 GiB machine it allows only 4 workers.
- `/dev/shm` use is small (peak 3.8 to 5.3 MiB; the 64 MiB Docker default is enough, `MIN_FREE_MB = 48` is far above need but
  protects the default).
- Remaining slow single tests (`test_booking_ceiling_r5`, `test_wishlist_migrations_concurrency`, the multiprocess modules) are
  the real contention tests; their durations were not reduced (DoD 5 and 6 say "safe concurrently", not "faster").

## CI and portability

`ci.yml` runs `make deps`, `make deps-browser`, `make check` on `ubuntu-latest` with Python 3.12. `make check` now runs
`analyze test`, where `test` uses xdist. What happens, per environment (items marked "unverified" were not run here):

| Environment | What the code does | Risk |
| ----------- | ------------------ | ---- |
| Reference machine (Linux, `/dev/shm` 64 MiB `noexec`, 6 CPUs, 5.9 GiB) | measured: 6 workers, 44 to 55 s | none |
| GitHub-hosted `ubuntu-latest` | `/dev/shm` is expected to exist as tmpfs (size unverified); `setpriv` and `timeout` are in coreutils/util-linux; 2 to 4 vCPU and 7 to 16 GiB (unverified): workers = `min(cpu, (mem - 1200) // 600)`, so 2 to 4. If `/dev/shm` is unusable the code probes `fsync` on the default temp directory; runner disks usually pass the 2 ms rule (unverified), otherwise one worker and a long run | Medium: unverified; the first CI run decides. The workflow does not print the plan (workers, storage), so a slow run cannot be explained from the log. Browser tests need Chromium from `make deps-browser` (existing, WISHENKA-124) |
| Docker with default `/dev/shm` 64 MiB, `noexec` | the measured case; disk profile and fake-browser directories go to `WISHENKA_TEST_DISK_TMPDIR` or the default temp directory | none |
| Linux with `/dev/shm` mounted too small or missing | fallback to the default temp directory with the fsync probe; fast: parallel; slow: one worker plus warning | covered by design, untested (M-4) |
| macOS | no `/dev/shm`; `os.sched_getaffinity` raises `AttributeError` in `cpu_count` (`xdist_support.py:147`) as soon as `-n auto` asks the hook, so `make test` fails before the first test. `timeout` command usually absent (no wall guard), `setpriv` absent (handled), `/proc/meminfo` absent (handled, no memory cap) | High for macOS developers; the repo targets Linux (Docker, CI), not declared anywhere in docs |
| Windows (native) | `os.getuid`, `os.killpg`, `os.sched_getaffinity`, `setpriv`, `timeout` all missing; not supported | Accepted (WSL works as Linux) |
| Contract tests off Linux | `test_fsync_probe_is_fast_on_tmpfs` fails instead of skipping (Q-3) | Low |

Recommendation: (a) in `cpu_count` use `os.process_cpu_count()` (3.13) or `len(os.sched_getaffinity(0))` when available else
`os.cpu_count()`; (b) make the `/dev/shm` contract test skip when the directory is absent; (c) in the Step 8 document say that
Linux is the supported platform for the parallel run and that `make test-serial` is the portable path; (d) add one CI step (or
log line) that prints `nproc`, `free -m`, the worker count and the storage plan, and keep the first CI run as the measured
evidence of the CI budget before promising a figure for it; (e) add `core` to `.gitignore` through WISHENKA-126.

## Faulthandler gap

- `faulthandler_timeout` is not set in `pyproject.toml` and `faulthandler.dump_traceback_later` is armed only inside
  `pytest_sessionfinish` (`conftest.py:99`, 120 s), i.e. it covers a hang in teardown or worker shutdown (the H8 case) but not a
  hang **inside** a test. A hang inside a test is stopped by `pytest-timeout` (every test has a marker, see the timeout rule;
  default method `signal` prints stacks on Linux), so in practice only a hang outside test items remains uncovered: collection,
  xdist controller deadlock, a worker that never reports. For those the only guard is the 600 s `timeout -k 30` (no stacks).
- Proposal: set `faulthandler_timeout` to a value above the largest test limit (60 s) such as 90 s in `pyproject.toml`; it dumps
  threads of a stuck worker and never fails a test. NON-BLOCKER, Low.

## Follow-up Tasks

Existing tickets checked by grep over `ai-tasks/*/60-tech-debt.md`: no entry mentions xdist, parallel runs, test speed or the
CDP helpers of this task. WISHENKA-126 (stray `core`) exists. WISHENKA-145 (real-htmx fidelity), 118 (SQLite writer contention),
140 (CSP inline JS), 84 (metrics exporter) and 157/158 (receipt hardening) were considered and have **no overlap**. WISHENKA-118
is related to the contention tests that dominate the critical path but covers the product, not test speed. Jira was not called
(per instructions); "NEW" means "not found in any artifact".

| ID | Title | Rationale | Priority | Type | Evidence | Jira | For closing WISHENKA-166 |
| -- | ----- | --------- | :------: | :--: | -------- | ---- | :----------------------: |
| D-1 | Unit tests for `read_debug_port` and the CDP port wait (all line shapes) | A mutation of the `isdigit` condition passes 16 contract tests (M-1) | Medium | Debt | `browser_cdp.py` `read_debug_port`; `test_parallel_run_contract.py` | NEW | NON-BLOCKER |
| D-2 | Tests for Chromium reaping: process group kill, `atexit` hook, relaunch after a crash, `setpriv` present and absent | Core safety property H9 is proven only by hand (M-2) | Medium | Debt | `browser_cdp.py:595-660` | NEW | NON-BLOCKER |
| D-3 | Tests for stale-directory cleanup incl. pid reuse and foreign user; harden `remove_stale_disk_dirs` against `FileNotFoundError` | M-3 and Q-4; race of two simultaneous runs can abort `pytest_configure` | Medium | Debt (hardening part: Bug) | `xdist_support.py:92-126`, `conftest.py:84-88` | NEW | NON-BLOCKER |
| D-4 | Tests for `plan_storage`, `plan_workers`, `available_memory_mb` and the slow-storage fallback; reject an invalid `WISHENKA_TEST_WORKERS` with a message | M-4, Q-1 | Medium | Debt | `xdist_support.py:129-185` | NEW | NON-BLOCKER |
| D-5 | Test the Makefile hint and wall guard, `loadfile`, `test-bench`; test `pytest_terminal_summary` and `parse_junit` | M-5, M-6 | Low | Debt | `Makefile:60-74`, `conftest.py:96-120`, `bench_suite.py:45-58` | NEW (fold into D-1 to D-4 as one story) | NON-BLOCKER |
| D-6 | Do not print "test files kept" and keep the directory for exit status 5 (and 0) | Q-5, reproduced | Low | Bug | `conftest.py:108, 113-120` | NEW | NON-BLOCKER |
| D-7 | Make the per-test setup cheap so that the suite is fast without tmpfs: a migrated template database copied per test (as `migrated_db_template`), or relaxed `synchronous` in test settings | Root cause S-1: slow-storage machines still need about 16 min | Medium | Debt | `conftest.py:191-210`, roadmap line 30 | NEW (related to nothing existing; WISHENKA-118 is product-side) | NON-BLOCKER |
| D-8 | Rebalance the critical path: split `test_shared_inventory_multiprocess` (25 s) and `test_booking_ceiling_r5` (20 s), or use `--dist worksteal`/`loadgroup`; re-decide `loadfile` vs `load` with at least 10 runs each | S-2, performance section; ideal 27 s vs 44 s | Low | Debt | `Makefile:62`; JUnit of this step | NEW | NON-BLOCKER |
| D-9 | CI: print the plan (nproc, memory, workers, storage) and record the first `ubuntu-latest` timing; decide whether 120 s applies to CI | Unverified CI behaviour, 2-vCPU estimate 95 to 110 s | Medium | Debt | `.github/workflows/ci.yml`, `xdist_support.py:174-185` | NEW | NON-BLOCKER (scope guard: CI setup is OUT) |
| D-10 | Portability: `cpu_count` fallback for macOS, skip the `/dev/shm` contract test when absent, state Linux support | Q-2, Q-3, CI table | Medium | Debt | `xdist_support.py:147`, `test_parallel_run_contract.py:166-173` | NEW | NON-BLOCKER |
| D-11 | Make thresholds configurable and justified: fsync 2 ms, 48 MiB, 1200/600 MiB, 5 samples, 120 s dump; report the classification reason in the terminal header | Q-1 | Low | Debt | `xdist_support.py:23-27`, `conftest.py:35` | NEW | NON-BLOCKER |
| D-12 | Set `faulthandler_timeout` (about 90 s) so a hang outside `pytest-timeout` prints stacks | Faulthandler gap | Low | Debt | `pyproject.toml`, `conftest.py:96-99` | NEW | NON-BLOCKER |
| D-13 | Unify the two disk-directory fixtures (`disk_tmp_path` in the contract test, `tmp_path` override in the prerequisites module) on `xdist_support.disk_mkdtemp`; decouple the contract test from internal function names (`ast` parse of `conftest.py`) and correct the stale `--dist load` message; tighten `{5, 6}` | S-6, Q-3 | Low | Debt | `test_parallel_run_contract.py:63-65, 128, 191-199, 246-263` | NEW (fold into D-1 to D-5 story) | NON-BLOCKER |
| D-14 | Document the fast run, `make test-serial`, `WISHENKA_TEST_TMPDIR` / `_DISK_TMPDIR` / `_WORKERS`, kept directories, the rule for tests that cannot run concurrently, measured figures in `doc/dev/testing.md` | DoD 10; the switches exist only in code comments and architecture A4 | High for the task, but its own Step | task step | `40-development.md` Open risks | **Carried to Step 8** (not a Jira item) | Closing requires Step 8 done; not a blocker of Step 7 |
| D-15 | Wording fix in `40-development.md` line 51: "12 full parallel runs" does not match its own list (14) or the roadmap (6 final runs plus the measurements) | Documentation inconsistency | Low | Debt | `ai-tasks/WISHENKA-166/40-development.md:51`, `00-roadmap.md` Step 4 P8 | none (fix in the artifact, in Step 8 or the commit step) | NON-BLOCKER |
| D-16 | Add `core` and `core.*` to `.gitignore`; remove the 197 MB file | Q-8, stray file must not be committed | Medium | Debt | `.gitignore`, repo root | **WISHENKA-126** (existing, do not duplicate) | NON-BLOCKER (stage by explicit path at commit) |
| D-17 | Run the parallel suite once on Python 3.12 (CI version); `.venv` is 3.13.5 | Q-7 | Low | Debt | `ci.yml`, `.venv` | NEW or note on WISHENKA-3 | NON-BLOCKER |
| D-18 | `make test-bench` prerequisite `deps` and Linux-only commands in `bench_suite.py` | Q-6 | Low | Debt | `Makefile:72-74`, `bench_suite.py:116-117` | NEW (fold into D-10) | NON-BLOCKER |

Pre-existing test failures: none found. The full run of this step and all earlier runs ended with 814 passed, 0 failed, 0
errors, 0 skipped.

## Blockers for closing WISHENKA-166

**None found in Step 7.** Checked against the DoD: 120 s (met on the reference machine), 0 failures (met, 814 of 814 in every
recorded run), equal passed sets (met for the 6 final-configuration runs and the serial run), no weakened tests (diff of the
three modified modules read: only the launcher, port wait and teardown changed; assertions are unchanged), no leftovers (met:
`/dev/shm` empty and no Chromium after the run of this step), timeout markers (met for all 814 collected tests). The only open
DoD item is DoD 10 documentation, which is Step 8 and must be passed before the commit step.

## Review addenda (Step 7 review, accepted)

- D-6 (exit status 5) is wider than described: any run that selects nothing (`-k` without match, `-m` without
  match, a mistyped node id) prints the false "kept for diagnosis" line and leaves the `-tmp` directory (not the
  basetemp named in the message). Fix: treat exit status 5 like 0 in `pytest_unconfigure` and
  `pytest_terminal_summary` (`tests/conftest.py:108`, `:116`). NON-BLOCKER, Low, cheap.
- D-13 / D-10: `test_fsync_probe_is_fast_on_tmpfs` also fails (does not skip) on a Linux machine where `/dev/shm`
  is slow or unavailable; the skip rule must cover that case too.
- D-3: acceptance point: "pid not visible" is treated as dead by `remove_stale` / `remove_stale_disk_dirs`; in
  containers with a shared `/dev/shm` and separate pid namespaces one run can delete another's live directory.
- D-14 (documentation of the fast and serial runs and the `WISHENKA_TEST_*` switches) is carried to Step 8 and
  must be done before the commit.
- D-15 ("12 vs 14 runs" in `40-development.md:51`) is fixed in the artifact by the orchestrator.
- Run-time figures: 48.9-55.3 s are the three recorded K=3 runs of Step 4; 44.1 s is a separate later run.

## Created Jira tickets (Phase D)

- WISHENKA-167 (Debt, Medium, 5): tests for Chromium launch/reaping and Makefile hint (D-1, D-2, D-5, D-13)
- WISHENKA-168 (Debt, Medium, 5): stale-dir cleanup and worker/storage planning tests and hardening (D-3, D-4)
- WISHENKA-169 (Bug, Low, 1): exit status 5 false "kept for diagnosis" (D-6)
- WISHENKA-170 (Debt, Medium, 8): template database per test, fast without tmpfs (D-7)
- WISHENKA-171 (Debt, Low, 3): critical path / worksteal / loadfile vs load (D-8)
- WISHENKA-172 (Debt, Medium, 2): CI plan output and first ubuntu-latest timing (D-9)
- WISHENKA-173 (Debt, Medium, 3): portability, macOS, no /dev/shm, bench_suite (D-10, D-18)
- WISHENKA-174 (Debt, Low, 2): thresholds in settings and faulthandler_timeout (D-11, D-12)
- WISHENKA-175 (Debt, Low, 2): run on Python 3.12 (D-17)
- D-16 (`core` file): existing WISHENKA-126. D-14: done in Step 8. D-15: fixed in the artifact.
