# Roadmap: WISHENKA-102

## Task Metadata

- **Implementation language**: Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-102/00-roadmap.md` — task roadmap created, implementation language set to Python
  - `ai-tasks/WISHENKA-102/10-requirements.md` — business requirements, user stories, entities, scope, and acceptance criteria
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-102/20-architecture.md` — research, implementation plan (Step 3 N/A note), module architecture, interaction flow, and interfaces
- [x] **STEP 3: Failing Repro Test**
  - N/A — no behavioral change (test-only tech-debt task adding stress/concurrency tests in `tests/test_wish_lifecycle_stress.py` without modifying production code or runtime behavior, per `20-architecture.md` and `10-requirements.md`)
- [x] **STEP 4: Development**
  - [x] Iteration 1: Created `tests/test_wish_lifecycle_stress.py` with SQLite WAL store lifecycle helper (`_open_wal_store`), barrier concurrency runner (`_run_barrier_tasks`), SQL+service invariant verifier (`_assert_wishlist_invariants`), and single-store/multi-store concurrent `reorder_wish_items` stress tests (2 passed).
  - [x] Iteration 2: Added concurrent `add_wish_item` + `reorder_wish_items`, concurrent `archive_wish_item` + `add_wish_item` + `reorder_wish_items`, multi-wave mixed owner/co-author lifecycle stress test, and multi-wishlist isolation stress test in `tests/test_wish_lifecycle_stress.py`; verified `ruff check`, `ruff format --check`, `mypy`, and all 6 stress tests pass (`26.94s` on `/dev/shm`, `28.49s` on default tmp). Note: full suite (`1124` items) timed out under container storage I/O limits (`exit 124` at 51% in 900s with 9 pre-existing/unrelated `F` failures observed before timeout).
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-102/40-code-cleanup.md` — static analysis (`ruff check`, `ruff format --check`, `mypy`), line-length/cleanup verification, and stress test run (`6 passed in 33.21s`)
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-102/50-observability.md` — N/A evaluation for test-only task (no production code modified; production logging/metrics out of scope)
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-102/60-tech-debt.md` — technical debt, test coverage gaps, performance observations, and follow-up tasks analysis
- [x] **STEP 8: Dev Docs**
  - `doc/dev/testing.md` — документация стресс-набора конкурентного жизненного цикла желаний (`tests/test_wish_lifecycle_stress.py`) и верификации SQLite WAL + `BEGIN IMMEDIATE`
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-102/00-roadmap.md`
- `ai-tasks/WISHENKA-102/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-102/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-102/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-102/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-102/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
