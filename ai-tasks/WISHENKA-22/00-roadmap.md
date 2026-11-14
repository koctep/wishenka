# Roadmap: WISHENKA-22

## Task Metadata

- **Implementation language**: Markdown (documentation only) for this
  specification story. The follow-up stories WISHENKA-23 (backend business
  logic and archive) and WISHENKA-24 (frontend screen and «Подаренные»
  section) are implemented in Python 3.12+.

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-22/10-requirements.md`
  - Scope: business scenarios and corner cases of full and partial gift
    receipt, the effect of receipt on active bookings, the notification of
    givers, and the split between «Подаренные» and the archive of deleted
    wishes. No schemas, API, or screen design.
  - Closes the open question in `in-docs/spec.md` section 16 and the open
    sentence in section 7.3 («точное согласование частично полученного и
    забронированного количества определяется при реализации»).
  - Fix round 1 after review FAIL: requirements corrected (FR-2.5, FR-2.6,
    FR-3.4, FR-3.6, FR-3.8, FR-4.2, FR-4.3, FR-4.7, Q5, Q12, goals, NFR section).
  - Fix round 2 after re-review FAIL: FR-2.6 cross-reference, code identifier
    removed from goals, observability wording removed from FR-4.7 / NFR /
    constraints, FR-3.6, FR-3.8 clarified.
  - Review round 3: PASS.
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-22/20-architecture.md`
  - Fix round 1 after review FAIL: legacy archived rows, settings gate
    owner and storage, corner case 16 and FR-1.4 tests, delivery wording,
    cross-reference and note clean-ups.
- [x] **STEP 3: Failing Repro Test**
  - [x] N/A — no behavioral change
    - WISHENKA-22 delivers only documents (requirements, architecture, `doc/dev` and
      `in-docs/spec.md` text updates); no runtime change, no production code, no tests.
    - `20-architecture.md` (Failing Repro) lists the red tests required for the behavior;
      they are owned by WISHENKA-23 and WISHENKA-24, each under its own Step 3.
- [x] **STEP 4: Development**
  - [x] Iteration 1: consolidated and verified the deliverables. The plan in
    `20-architecture.md` (Implementation Plan / WISHENKA-22) assigns no
    production code to this story, and assigns the `doc/dev` updates to
    Step 8, so none were made here. `10-requirements.md` and
    `20-architecture.md` were re-read and are consistent with each other.
  - [x] Iteration 2: `in-docs/spec.md` section 7.3 — replaced the open
    sentence with the agreed rules (FR-3.1 to FR-3.7, FR-4, FR-2.4).
  - [x] Iteration 3: `in-docs/spec.md` section 7.2 — added the rules of
    receipt (FR-1, FR-2.1 to FR-2.3, FR-5, FR-3.8). Section 16 — removed the
    closed bullet on the quantity of received items vs. bookings.
  - [x] Verified with `git status --porcelain`: only Markdown under
    `ai-tasks/` and `in-docs/` changed. No tests run (no code changes).
  - Review PASS. Note for Step 8: the in-docs/spec.md closure of sections
    7.3 and 16 was done in Step 4; Step 8 verifies it and covers doc/dev
    only (no duplicate rewrite).
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-22/40-code-cleanup.md`
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-22/50-observability.md`
  - Fix round 1: notice-path logs correlate by `outbox_id` only, event table field list closed
  - Fix round 2: per-row worker events moved to DEBUG, INFO aggregate window summary, DEBUG
    operator-only requirement, worker run in the walk test, DB-side duplicates counter
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-22/60-tech-debt.md`
  - [x] Fix round 1: review FAIL gaps 1 to 7 and items N4, N5 applied to `60-tech-debt.md`
- [x] **STEP 8: Dev Docs**
  - `doc/dev/gift-receipt.md` (new): target design, status block PLANNED,
    deferred to WISHENKA-23 and WISHENKA-24
  - Planned-change pointers (no current-behaviour text changed):
    `doc/dev/items.md`, `doc/dev/reservations.md`, `doc/dev/architecture.md`,
    `doc/dev/verification-matrix.md`
  - `in-docs/spec.md` 7.2: unified the wording «владелец, администраторы и
    участники» (section 3 gives every participant edit rights)
  - Decision on the trailing source line of 7.3: DELETED. `spec.md` carries no
    other Jira key or source line, so there is no convention to keep it;
    traceability is in git history and `doc/dev/gift-receipt.md`
  - Verified with `git status --porcelain`: only Markdown under `doc/dev/`,
    `in-docs/` and `ai-tasks/` changed
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-22/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-22/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-22/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-22/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-22/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
