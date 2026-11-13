# Roadmap: WISHENKA-39

## Task Metadata

- **Implementation language**: Python 3.12+

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-39/10-requirements.md`
  - Deliverable is automated proof of the booking ceiling under repeated
    contention, many gifters, and a bounded load profile (matrix row R5).
    Product behavior stays as it is.
  - Sibling boundaries: WISHENKA-57 already keeps one shared inventory
    balance. WISHENKA-49 owns further locking and isolation. WISHENKA-38
    closed S5, S6, S8, and A3. R1–R4 stay on their existing checks.
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-39/20-architecture.md`
  - R5 checks call the existing `WishlistStore.execute_wish` path.
    They reuse the R2 spawn, barrier, queue, and join harness. No new
    lock. No R1–R4 rewrite. No surprise-rule tests.
  - Step 3 plan: `N/A — no behavioral change`. A local probe of five
    gifters already kept the ceiling on one store and on several
    processes. Step 4 adds characterization checks expected to pass.
- [x] **STEP 3: Failing Repro Test**
  - N/A — no behavioral change. The wish-scoped booking ceiling already
    holds, so there is no red defect test; characterization checks belong
    to Step 4 and are expected to pass.
- [x] **STEP 4: Development**
  - [x] Added `tests/test_booking_ceiling_r5.py`: five-gifter ceiling
    checks for one-unit and whole-remainder shapes, one store and one
    process per gifter, three repetitions, and a two-round load profile.
    Product code unchanged. The focused suite passed: 6 tests.
- [x] **STEP 5: Code Cleanup**
  - Scope: `tests/test_booking_ceiling_r5.py` only. Product behavior
    stays unchanged.
  - `make analyze`: Ruff check passed, Ruff format check reported 84
    files already formatted, and Mypy reported no issues in 84 files.
    No task-introduced warnings to fix.
  - No unused imports, unused variables, commented-out code, debug
    prints, or conflict markers. The longest line is 99 characters,
    under the 100-character project limit. The test file was not
    rewritten.
  - `make test PYTEST=".venv/bin/pytest tests/test_booking_ceiling_r5.py"`:
    6 passed in 13.49s. Module timeout is 120 seconds, with closer
    per-test marks of 30, 60, 90, or 120. The full suite was not run.
  - Artifact: `ai-tasks/WISHENKA-39/40-code-cleanup.md`.
- [x] **STEP 6: Observability**
  - No product change. No new log, metric, or lock.
  - The R5 checks already prove the ceiling: `InsufficientQuantityError`
    is a complete refusal, `InventoryBusyError` fails the check, and the
    balance after the race is the proof. Existing WARNING refusal logs
    stay on `wishenka.wishlists` and `wishenka.wishlists.store`.
  - Artifact: `ai-tasks/WISHENKA-39/50-observability.md`.
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-39/60-tech-debt.md`
  - No new follow-up. The six checks already have explicit timeout
    marks. Further locking stays on WISHENKA-49. Pointing the
    verification matrix at these tests stays on Step 8.
  - User documentation under `doc/` was not changed.
- [x] **STEP 8: Dev Docs**
  - Updated `doc/dev/verification-matrix.md`. Row R5 names
    `tests/test_booking_ceiling_r5.py` and the six checks: one-unit
    and whole-remainder, one copy and many copies, repeated
    contention, and the load profile. It also documents the focused
    test command, fixed bounds, and expected versus failing outcomes.
  - Updated the matrix pointer in `doc/dev/architecture.md` so R5
    names that file.
  - S5, S6, S8, and A3 stay closed on
    `tests/test_surprise_role_context.py`. Further locking stays on
    WISHENKA-49. No product code, no test edits, no commit.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-39/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-39/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-39/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-39/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-39/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/verification-matrix.md`
- `doc/dev/architecture.md`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
