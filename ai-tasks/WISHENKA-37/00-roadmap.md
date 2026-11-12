# Roadmap: WISHENKA-37

## Task Metadata

- **Implementation language**: Python 3.12+

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-37/10-requirements.md`
  - Deliverable is a verification matrix document. It records coverage and
    gaps. The end-to-end surprise suite stays on WISHENKA-38. The race and
    load suite stays on WISHENKA-39.
  - Families: surprise at every exit, concurrent booking and the free
    remainder, anonymous giver access by share link.
  - Shipped promise actions, wish card, cabinet, and shared quantity outcome
    are pointed at (WISHENKA-18, WISHENKA-19, WISHENKA-20, WISHENKA-57).
  - Step 1 note: the share-page remainder, the public-list omission, and
    the recipient omission are decided product behavior. The share-link
    visit that must create no account is a WISHENKA-38 gap. A2 cites
    `test_anonymous_share_shows_availability_without_a_book_control`.
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-37/20-architecture.md`
  - Durable checklist: `doc/dev/verification-matrix.md`, linked from
    `doc/dev/architecture.md`.
  - The checklist indexes API exits, logs, the share page, and the existing
    tests named in the architecture research.
  - Implementation plan: N/A — no behavioral change. Step 3 is N/A.
    WISHENKA-38 owns the end-to-end surprise gaps. WISHENKA-39 owns race
    and load.
- [x] **STEP 3: Failing Repro Test**
  - N/A — no behavioral change. There is no production behavior to fail
    before a fix, and a test that only waits for a markdown file is not
    required.
- [x] **STEP 4: Development**
  - [x] N/A runtime change. Aligned `doc/dev/verification-matrix.md`
    with the tests that assert each covered row: S4 cites the gifter
    remainder line, A4 names the share-page, public-list, and recipient
    tests, S5 drops citations that do not assert gifter omission, and
    R1 drops the rollback test that does not assert two bookings.
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-37/40-code-cleanup.md`
  - No Python change. `make analyze` was not run.
  - Removed the repeated A3 health-check note from the matrix index.
    S7 still cites the stale-session test once, under Covered by.
  - No trailing whitespace. The architecture.md matrix link resolves.
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-37/50-observability.md`
  - No log or metric was added. Existing logs stay indexed by
    `doc/dev/verification-matrix.md`: S5 (recipient logs omit a gifter;
    the operator stream may contain `gifter_id`) and A7 (access logs
    omit the share token).
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-37/60-tech-debt.md`
  - No new follow-up. Open rows stay with WISHENKA-38 and WISHENKA-39.
  - This task added no test, so a missing pytest timeout is out of scope.
  - Matrix citations match the tests they name.
    `doc/dev/verification-matrix.md` was left unchanged.
  - User documentation: N/A. Step 8 owns `doc/dev/`.
- [x] **STEP 8: Dev Docs**
  - `doc/dev/verification-matrix.md` is the developer checklist, already
    linked from `doc/dev/architecture.md`.
  - Added Overview and Where the gaps live. How to read a row and
    Modules this matrix indexes were already present.
  - Open gaps stay with WISHENKA-38 (S5 combined walk, S6, S8, and the
    A3 share-link visit that creates no account) and WISHENKA-39 (R5).
  - Covered-row test citations were left unchanged. No test and no
    production Python were added.
  - Configuration: N/A. The checklist has no settings. The service does
    not read the file.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-37/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-37/20-architecture.md`
- `doc/dev/verification-matrix.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-37/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-37/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-37/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/verification-matrix.md`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
