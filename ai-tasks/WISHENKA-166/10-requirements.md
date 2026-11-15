# WISHENKA-166: Parallel test run, full suite in no more than 2 minutes

Programming language for implementation: **Python 3.12+** (test infrastructure: pytest
configuration, fixtures and helpers under `tests/`, `pyproject.toml`, `Makefile`). Recorded in
`00-roadmap.md`.

Jira title: «[Техдолг] Параллельный запуск тестов: полный прогон не более 2 минут».

This file says WHAT the developer gets. The choice of tools and the way tests are distributed
over workers belong to Step 2. The ticket mentions parallel execution as background; this file
does not prescribe a tool.

## Goals

Why the task exists. The full suite (798 tests, `make test`) runs one test after another and
takes about 17 minutes (measured 17 min 20 s on the reference machine). The author of a change
cannot get a verdict on it in a reasonable time:

- A developer runs the suite before a commit and the quality gate `make check`. A 17-minute wait
  turns every iteration into a context switch, so the suite is run rarely, late, or only in
  part.
- Partial runs let a regression reach the commit unnoticed, and a failure found 17 minutes
  later costs a full re-run to confirm the fix.
- The user names this a serious blocker of daily work. The sprint pipeline (several steps, each
  with a test run and a review) multiplies the cost.

Business value: a feedback loop of at most 2 minutes, so that the full suite is run before every
commit, without loss of coverage and without new random failures. A fast but unreliable suite is
worse than a slow one, so reliability is part of the goal, not a side effect.

## Scope

### In scope

- The default path of `make test` (and so `make check`) runs the whole suite in at most 2 minutes
  on the reference machine.
- A serial way of running remains for debugging.
- Elimination of everything that makes the suite fail, hang or flip when tests run
  concurrently (shared state, fixed resources, time-sensitive waits), including the slowest
  tests found by measurement.
- Documentation of how to run the suite fast and serially (Step 8).

### Out of scope

| Topic | Reason |
| ----- | ------ |
| Any change of product behavior | This is a test-infrastructure task |
| Removing, weakening or rewriting test assertions to gain speed | Test semantics are fixed (C-1) |
| Faster hardware, changing the number of cores or RAM of the machine | Not controlled by the project |
| Setting up an external CI service or its pipeline | Only a requirement that nothing in the setup prevents it (see the CI user story) |
| Fixing product defects that parallel runs may reveal | Recorded as separate tickets (Q-4) |

## Main Business Entities

- **Suite**: all automated tests collected by `make test`, today 798 tests in about 60 modules
  under `tests/`.
- **Test group**: a set of tests with the same needs. Known groups:
  - unit and route-level tests (fast, isolated);
  - browser tests (drive a real headless Chromium, marked `browser`);
  - concurrency and multiprocess tests (they start their own processes and depend on timing:
    booking ceiling, receipt concurrency, shared inventory, migration concurrency);
  - tests that start the project build tool themselves (`test_browser_prerequisites.py`).
- **Runner**: whatever executes the suite on the developer machine (`make test`).
- **Reference machine**: the machine on which the time budget is measured. Measured here:
  **N = 6 cores** (`nproc`), **5909 MiB RAM** (`free -m`), no swap, Linux 6.8.
- **Run**: one full execution of the suite from start to the final verdict.

## User Stories

- As a developer, I run `make test` before a commit and get the verdict of the full suite in no
  more than 2 minutes (F-1, N-1).
- As a developer, I re-run one failing test serially and see its plain output, so that I can
  debug it without the effects of concurrency (F-3).
- As a developer, I trust a green run: nothing was skipped to make it fast, and a failure is
  never caused by the parallel mode itself (F-4, N-2).
- As a developer working on a 5909 MiB machine, I do not lose the session to a memory shortage
  during the run (N-3).
- As another contributor or a CI system, I run the same command on a similar machine and get
  the same behavior without extra manual steps.
- As a maintainer, I add a new test and it is run in the fast path by default, with the rule
  for the tests that cannot run concurrently written down (F-8, F-9).

## Functional Requirements

Priority is MUST unless marked SHOULD.

- F-1. **Fast path by default.** `make test` runs the whole suite concurrently, with no extra
  flag or manual step, and `make check` uses it.
- F-2. **Time budget measured by evidence.** The work starts from the measured time per test
  and per module (`pytest --durations`), recorded in the task artifacts, so that the slowest
  tests and the share of serial time are known before anything is changed.
- F-3. **Serial mode stays available.** A documented, single command (for example a Makefile
  target) runs the suite, a module or a single test strictly one at a time, with the output
  readable test by test. It produces the same verdicts as the fast path.
- F-4. **No loss of coverage.** Every one of the 798 collected tests (and any added meanwhile)
  runs in the fast path. No test is deleted, skipped, marked expected-to-fail or silently
  deselected to reach the goal. The collected count and the count of passed tests of the fast
  path equal those of the serial path (798 collected, 0 skipped beyond today's).
- F-5. **Slow tests are not excluded by default.** The recommended position: no test is excluded
  from `make test`. If measurement shows that the budget cannot be met otherwise, a test may
  be moved out of the default run only with a written justification (what it costs, what it
  protects), and only if it still runs in an explicit second target that is part of `make check`
  (so the quality gate does not lose coverage). The decision and the list are recorded in the
  artifacts of the task.
- F-6. **Isolation between tests.** A test result does not depend on the order, on the
  neighbors running at the same time, or on which worker runs it. Tests that need a resource
  that cannot be shared (a fixed port, a fixed path, a global lock, a build directory, the
  browser) get an isolated one per test or per worker, or are explicitly grouped.
- F-7. **Tests that start the build tool or their own processes.** Tests that call `make` or
  start their own worker processes (the group above) are safe in the fast path: they do not
  interfere with each other or with the parent run and do not make the run slower than the
  budget by themselves. The measured cost of each such module is stated.
- F-8. **New tests join the fast path by default.** A new test module needs no registration to be
  run in the fast path. The rule for a test that cannot run concurrently is a documented,
  explicit marker or group, not an implicit convention.
- F-9. **Clear failure report.** A failed test in the fast path reports its name, its output and
  its traceback as in the serial mode; the run exit code is non-zero if any test failed or
  any worker died.

## Non-functional Requirements

- N-1. **Time budget.** On the reference machine (N = 6 cores, 5909 MiB RAM) the full run of
  `make test` takes **at most 120 s of wall-clock time**, measured from the start of the
  command to its end, including environment checks that the command performs. The measurement
  is stated together with N and the amount of RAM. A target for other machines is not set;
  the time is expected to scale with the number of cores.
- N-2. **Reproducibility.** **K = 3** consecutive full runs on the reference machine all end with
  0 failures, 0 errors and the same set of passed tests, each within the budget of N-1. No
  test fails in one run and passes in another (no flipping). A test that flipped during the
  series is fixed, not retried; automatic re-runs of failed tests are not used to hide it.
  (K = 3 is a recommendation; see Q-3.)
- N-3. **Resource limits.** The run stays within the 5909 MiB of RAM without swap: no out-of-memory
  kill of any process, no worker lost, and the machine stays usable. The peak memory of the
  run is measured and recorded. The number of concurrent heavy consumers (browsers) is bounded.
- N-4. **Bounded waits are kept.** Every test keeps its time limit (timeout markers stay) and
  every wait stays bounded and deterministic. A time-sensitive test (strict limit of about
  10 s, `time.sleep` call sites, multiprocess timing) is made stable under the load of the
  parallel run by waiting for a condition, not by removing the limit, by lengthening it
  without a reason, or by retries. Any limit raised is justified in the artifacts.
- N-5. **Determinism of verdicts.** The same code gives the same set of verdicts in serial and
  in fast mode; the order of the output may differ.
- N-6. **No leftovers.** After a run (successful or not) no stray processes (browser, workers,
  child servers), no temporary directories and no occupied ports are left; a next run starts
  clean without manual cleanup.
- N-7. **Maintainability.** The run configuration lives in the project files (`pyproject.toml`,
  `Makefile`, `tests/`), is documented in `doc/dev/testing.md`, and keeps the existing static
  analysis (`make analyze`) green.

## Constraints and Assumptions

- C-1. **Test semantics are fixed.** The behavior checked by each test and its assertions do not
  change. Changes to a test are allowed only to remove a dependency on timing, order or a
  shared resource, and each is justified.
- C-2. **Production code is untouched** unless a test needs a small seam that cannot be
  provided otherwise (for example a configurable path or port). Any such change is listed and
  justified at Step 2 (Q-2); it must not alter product behavior.
- C-3. **Reference machine.** The budget is measured on the machine of the task: 6 cores, 5909
  MiB RAM, no swap, headless Chromium available. The earlier figures (798 tests, 17 min 20 s
  serial) come from an estimation pass and are re-measured at the start of Step 2 or 3.
- C-4. **Known risk areas (hypotheses to verify, not conclusions):** the test that starts `make`
  itself (`tests/test_browser_prerequisites.py`); the multiprocess and time-sensitive modules
  (`test_booking_ceiling_r5.py`, `test_receipt_concurrency.py`,
  `test_shared_inventory_multiprocess.py`, `test_wishlist_migrations_concurrency.py`); strict
  10 s limits under CPU load; about 9 `time.sleep` call sites; one browser process per worker.
  Ports and the browser profile appear safe per run, and each test works with its own copy of
  the SQLite database; all of this is checked, not assumed.
- C-5. **Dependencies.** A new development dependency is allowed if it is declared in the project
  dependency list and installed by the existing `make deps`; no manual installation step.
- C-6. The suite stays runnable offline, as today.

## Definition of Done

Each item is measurable and is shown by a recorded command output in the task artifacts.

1. `make test` with no extra flags runs concurrently (F-1) and finishes in at most 120 s on
   the reference machine; the output records the command, the wall-clock time, `nproc` = 6
   and RAM from `free -m`. (F-1, N-1)
2. K = 3 consecutive full runs of `make test`: 0 failed, 0 errors, 798 (or the then-current
   count) passed, each within 120 s, with the same set of passed test names in all three runs.
   (N-2, N-5)
3. The serial run (documented command) gives the same collected and passed counts as the fast
   path and was executed at least once in full. (F-3, F-4)
4. The collected count equals the count before the change plus tests added by the task itself;
   no new skip, xfail, deselect or deleted test is introduced; the diff of `tests/` is
   reviewed for weakened assertions. (F-4, C-1)
5. The measured durations (`pytest --durations`) before and after are recorded, with the list of
   the slowest tests and what was done about each one above the agreed threshold. (F-2)
6. Each module of the risk areas of C-4 is reported with its measured time and the reason it is
   safe concurrently (or how it was made safe). (F-6, F-7)
7. Every timeout marker present before is still present; any raised limit or changed wait has a
   justification; no retry plugin or rerun-on-failure is used. (N-4)
8. Peak memory of a full run is recorded and stays below the machine limit with no OOM event
   in the system log. (N-3)
9. After a full run no stray process, temporary directory or occupied port remains. (N-6)
10. `make analyze` is green and `doc/dev/testing.md` describes the fast run, the serial run, the
    rule for tests that cannot run concurrently, and the measured figures. (F-8, N-7)

## Task Description

Today the project has a thorough suite whose cost grows with every story (WISHENKA-24 alone
added seven modules). It runs strictly one test at a time on a machine with six cores, of which
one is used. The browser tests, the multiprocess tests and the many small tests all wait in one
line. The task changes the way the suite runs, not what it checks, and removes whatever stops
the suite from running safely on several cores at once. Speed gained at the price of random
failures or skipped tests is not acceptable.

## Q&A

- Q1. The ticket is technical («запустить параллельно»). Why do we need it?
  A. Because a 17-minute feedback loop makes the developer avoid the full run, which lets
  regressions pass; the user calls it a serious blocker. The business goal is a verdict
  within 2 minutes that the developer can trust. See Goals.
- Q2. May a slow test be dropped from the default run to reach 2 minutes?
  A. Recommended: no (F-5). Only with justification and only if it still runs in an explicit
  second target included in `make check`. Coverage must not decrease.
- Q3. Why exactly 2 minutes and 6 cores?
  A. 2 minutes is the ticket's limit. N = 6 and 5909 MiB are measured on this machine (`nproc`,
  `free -m`) and are the reference for the budget. 17.3 min / 6 cores is about 2.9 min even
  with perfect scaling, so the budget is reachable only if the slowest tests are also made
  faster (F-2, F-7); this is why measurement comes first.

## Open Questions

- Q-1. Is a budget of 120 s on the reference machine accepted as hard, given that perfect
  6-core scaling of the serial time gives about 175 s? Recommended: yes, keep 120 s and
  reduce the slowest tests (waits, per-test setup) as part of the task; do not relax the
  limit without the product owner.
- Q-2. May a small seam be added to production code if a test cannot be isolated otherwise
  (a configurable path or port)? Recommended: yes, only if it changes no product behavior, and
  it is listed in the Step 2 artifact.
- Q-3. Is K = 3 enough as the reproducibility series? Recommended: 3 full runs for acceptance
  (about 6 minutes), and a longer series (for example 10 runs of the risk-area modules only)
  during development.
- Q-4. If the parallel run reveals a real product defect (for example a race in the booking
  code), is it fixed here? Recommended: no; record it as a separate Bug and keep the test
  stable by a documented, minimal means that does not hide the defect.
- Q-5. Is the 2-minute budget also required on other machines or CI? Recommended: no, only on
  the reference machine (N-1); other machines are a best effort with the same design.

## Traceability

| Goal or ticket statement | Requirement |
| ------------------------ | ----------- |
| Full run no more than 2 minutes on N cores | F-1, N-1, DoD 1 |
| 0 failures | N-2, DoD 2 |
| No flaky tests across a series of repeated runs | N-2, N-4, DoD 2, DoD 7 |
| Start from `pytest --durations` | F-2, DoD 5 |
| Serial run stays for debugging | F-3, DoD 3 |
| Nothing dropped to reach the goal | F-4, F-5, C-1, DoD 4 |
| Risk areas (make, multiprocess, timeouts, sleeps, Chromium) | F-6, F-7, N-3, N-4, C-4, DoD 6, 8 |
