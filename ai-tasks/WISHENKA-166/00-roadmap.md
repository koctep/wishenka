# Roadmap: WISHENKA-166

## Task Metadata

- **Implementation language**: Python 3.12+ (test infrastructure: pytest configuration and fixtures under `tests/`, `pyproject.toml`, `Makefile`)

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - [/] `ai-tasks/WISHENKA-166/00-roadmap.md` created from the template
  - [/] Implementation language recorded in Task Metadata: Python 3.12+ / test infrastructure / Makefile
  - [/] `ai-tasks/WISHENKA-166/10-requirements.md` written (business view only; requirement IDs F-1 to F-9, N-1 to N-7, DoD 1 to 10; reference machine 6 cores / 5909 MiB RAM measured by `nproc` and `free -m`)
  - [/] Scope guard: IN is the speed and reliability of the full run of the existing 798 tests; OUT is any change of product behavior, test semantics and CI provider setup
  - [/] Open questions recorded in the requirements (Q-1 to Q-5), none of them blocks Step 2
  - [/] Awaiting review and the acceptance gate (the orchestrator marks `[x]`)
- [x] **STEP 2: High-Level Architecture Design**
  - [/] Serial baseline measured: 798 passed in 971.7 s (setup 56 %, call 40 %); `ai-tasks/WISHENKA-166/21-baseline-data.md`
  - [/] Root cause measured: `fsync` on virtiofs `/tmp` (11 ms alone, 75 ms with 6 writers); `-n 6` on disk gave 981 s with 28 failed and 9 errors (file order)
  - [/] Experiments on tmpfs: serial 112.6 to 114.1 s, `-n 6` 48 to 63 s, 798 passed; peak memory drop 2737 to 3115 MiB at 6 workers
  - [/] `ai-tasks/WISHENKA-166/20-architecture.md` written (decisions D1..D13, hazards H1..H14, plan P1..P9, failing-repro design)
  - [/] No production code seam needed (Q-2); no test excluded (F-5 unused)
  - [/] Review FAIL fixed (revision 2): re-measured with `-p no:randomly` (serial tmpfs 114.1 s; `-n 6` load 63.3 and 56.6 s, loadfile 47.8 s; disk `-n 6` 981 s with 28 failed and 9 errors); slow-storage fallback to one worker; optional xdist hook; `bench_suite` moved to P6; `setpriv`/killpg browser reaping; fast `TMPDIR`; traceability matrix
  - [/] Awaiting review and the acceptance gate (the orchestrator marks `[x]`)
- [x] **STEP 3: Failing Repro Test**
  - [/] Red test: `tests/test_parallel_run_contract.py` (16 tests: 15 red, 1 green by construction; about 0.5 s)
  - [/] Red reasons recorded in `ai-tasks/WISHENKA-166/30-failing-repro.md` (Makefile, pyproject, xdist_support, CDP port-file race, default DB, optional hook)
  - [/] No production code, Makefile, pyproject or existing test changed; bench_suite is P6, not a red test
  - [/] Awaiting independent review (the orchestrator marks `[x]`)
- [x] **STEP 4: Development**
  - [x] P1 pyproject: pytest-xdist in dev extras, retention policy "failed"; installed with `make deps`
  - [x] P2 `tests/xdist_support.py` and conftest hooks (optional worker cap, tmpfs basetemp, fast TMPDIR, stale cleanup, faulthandler timer)
  - [x] P3 CDP port-file wait, `launch_chromium`/`stop_chromium` (setpriv, killpg), disk profiles, two own-Popen tests migrated
  - [x] P4 disk `tmp_path` override in `test_browser_prerequisites.py`; P5 autouse default-database isolation (no production seam)
  - [x] P6 Makefile `test` / `test-serial` / `test-bench` / help, `tests/bench_suite.py`
  - [x] P7 `--dist loadfile` chosen (median 46.2 s vs 49.4 s); worst duration/limit 0.174, no limit raised
  - [x] P8 DoD series: 6 parallel runs 48.9 to 55.3 s wall, 814 passed each; serial 114 s pytest, 814 passed; `make check` green; no leftovers
  - [x] P9 skipped (docs are Step 8); log in `ai-tasks/WISHENKA-166/40-development.md`
- [x] **STEP 5: Code Cleanup**
  - [/] `make analyze` green (ruff, format, mypy: 136 files); wider scan (F, ERA, T20, N, UP, B) shows only intended findings
  - [/] No code edits needed: no unused code, commented-out code, scratch paths or stale comments
  - [/] `ai-tasks/WISHENKA-166/40-code-cleanup.md` written; `make test` 814 passed (51.67 s), no leftovers
  - [/] Awaiting review and the acceptance gate (the orchestrator marks `[x]`)
- [x] **STEP 6: Observability**
  - [/] Audit of test-run diagnostics and 4 small fixes (kept-dir line moved to terminal summary, Makefile kill message, bench failure lines, slow-storage hint); `ai-tasks/WISHENKA-166/50-observability.md`; `make test` 814 passed (45.9 s), no leftovers
- [x] **STEP 7: Technical Debt Analysis**
  - [/] `ai-tasks/WISHENKA-166/60-tech-debt.md` written (18 follow-ups D-1..D-18, no BLOCKER; DoD 10 docs carried to Step 8); timeout rule satisfied (0 of 814 without marker); `make test` 814 passed in 44.1 s; awaiting review and the acceptance gate
- [x] **STEP 8: Dev Docs**
  - [/] `doc/dev/testing.md` new section «Параллельный запуск тестов (WISHENKA-166)» (overview, architecture, usage, configuration, slow storage, troubleshooting, limits D-1..D-18; DoD 10, D-14); `doc/dev/infrastructure.md` (Makefile targets, CI step); `doc/dev/verification-matrix.md` (Family 4, row P1); awaiting review and the acceptance gate
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-166/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-166/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-166/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-166/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-166/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
