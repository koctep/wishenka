# Roadmap: WISHENKA-58

## Task Metadata

- **Implementation language**: Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
- [x] **STEP 2: High-Level Architecture Design**
- [x] **STEP 3: Failing Repro Test**
  - [ ] `tests/test_item_concurrency_lifetime.py` — inactive locks reclaimed after sequential use
- [x] **STEP 4: Development**
  - [x] Reclaim unreferenced locks with a weak registry while retaining active references.
  - [x] Verify handoff, cancellation, independent items, exception release, and reuse.
- [x] **STEP 5: Code Cleanup**
- [x] **STEP 6: Observability**
- [x] **STEP 7: Technical Debt Analysis**
- [x] **STEP 8: Dev Docs**
  - [ ] `doc/dev/reservations.md` — item lock lifecycle, usage, and troubleshooting
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-58/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-58/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-58/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-58/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-58/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
