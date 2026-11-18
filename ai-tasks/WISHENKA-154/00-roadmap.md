# Roadmap: WISHENKA-154

## Task Metadata

- **Implementation language**: `Markdown (documentation-only; no code changes)`

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-154/00-roadmap.md`
  - `ai-tasks/WISHENKA-154/10-requirements.md`
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-154/20-architecture.md`
- [x] **STEP 3: Failing Repro Test**
  - N/A — documentation-only change, no code or behavioral change
- [x] **STEP 4: Development**
  - [x] Updated `in-docs/spec.md` (sections 3, 4.4, 5.5, 6.3, 6.4, 7.2, 7.3, and 16; verified section 11.2) to reflect all six settled product decisions (assumptions A–D, Q6, Q8, Q11, Q12, and purchased-promise «Завершено» state) without Jira keys or implementation details.
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-154/40-code-cleanup.md`
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-154/50-observability.md` (N/A — documentation-only task; no code or runtime changes)
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-154/60-tech-debt.md`
- [x] **STEP 8: Dev Docs**
  - `doc/dev/gift-receipt.md` — documented settled product decisions (`FR-1`–`FR-4`: assumptions A–D, no public «уже подарено» label, deletion of «Подаренные» with deleted list vs read-only archive, co-author/recipient role rules) and marked `FR-5` (Q12, `WISHENKA-218`) and `FR-6` (Shortcut E, `WISHENKA-219`) as planned/target spec rules.
  - `doc/dev/items.md` — noted planned/target `FR-5` (`WISHENKA-218`) on the Reduction Lock Invariant and `FR-4` (co-author/recipient role rules) on Dual-Role Projections.
  - `doc/dev/reservations.md` — marked `FR-6` (`WISHENKA-219`, «Завершено» state for purchased promises) and `FR-5` (`WISHENKA-218`, Reduction Lock tightening) as planned/target spec rules.
  - `doc/dev/wishlists.md` — noted `FR-4` (co-author/recipient role rules) in the Privilege Matrix and `FR-3` (deletion of «Подаренные» on list deletion vs read-only archive) in `delete_wishlist`.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-154/00-roadmap.md`
- `ai-tasks/WISHENKA-154/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-154/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-154/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-154/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-154/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
