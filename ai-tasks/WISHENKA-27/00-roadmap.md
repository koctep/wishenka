# Roadmap: WISHENKA-27

## Task Metadata

- **Implementation language**: Python 3.12+

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - Requirements: `ai-tasks/WISHENKA-27/10-requirements.md`
- [x] **STEP 2: High-Level Architecture Design**
  - Architecture: `ai-tasks/WISHENKA-27/20-architecture.md`
- [x] **STEP 3: Failing Repro Test**
  - Red tests: `tests/test_bot_entry_repro.py` and `tests/test_bot_start_repro.py`
- [x] **STEP 4: Development**
  - [x] Implemented private bot entry, localized menu, and independent polling lifecycle.
  - [x] Implemented role-aware public entry and transactional capability-bound reservation.
  - [x] Added unavailable-link recovery and preserved the invitation confirmation flow.
  - [x] Verified red repros and reservation behavior with fake Telegram transport and browser tests.
- [x] **STEP 5: Code Cleanup**
  - Cleanup report: `ai-tasks/WISHENKA-27/40-code-cleanup.md`
- [x] **STEP 6: Observability**
  - Report: `ai-tasks/WISHENKA-27/50-observability.md`
- [x] **STEP 7: Technical Debt Analysis**
  - Debt analysis: `ai-tasks/WISHENKA-27/60-tech-debt.md`
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

- `ai-tasks/WISHENKA-27/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-27/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-27/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-27/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-27/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
