# Roadmap: WISHENKA-26

## Task Metadata

- **Implementation language**: Python 3.12+ (documentation task)

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - Requirements: `ai-tasks/WISHENKA-26/10-requirements.md`
- [x] **STEP 2: High-Level Architecture Design**
  - Architecture: `ai-tasks/WISHENKA-26/20-architecture.md`
- [x] **STEP 3: Failing Repro Test**
  - N/A — no behavioral change. This task delivers a scenario specification only; it changes no
    runtime behavior or interface. Subsequent implementation tasks require their own red tests.
- [x] **STEP 4: Development**
  - [x] Documented bot journeys, target selection, notification matrix, and acceptance examples.
  - Specification: `in-docs/bot-scenarios.md`
- [x] **STEP 5: Code Cleanup**
  - Cleanup report: `ai-tasks/WISHENKA-26/40-code-cleanup.md`
- [x] **STEP 6: Observability**
  - Assessment: `ai-tasks/WISHENKA-26/50-observability.md`
- [x] **STEP 7: Technical Debt Analysis**
  - Analysis: `ai-tasks/WISHENKA-26/60-tech-debt.md`
- [x] **STEP 8: Dev Docs**
  - Developer guide: `doc/dev/bot-scenarios.md`
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-26/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-26/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-26/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-26/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-26/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
