# Roadmap: WISHENKA-29

## Task Metadata

- **Implementation language**: Python 3.12+

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - Requirements: `ai-tasks/WISHENKA-29/10-requirements.md`
  - Reopened to include an explicit, user-controlled birthday source and tracking flow.
- [x] **STEP 2: High-Level Architecture Design**
  - Architecture: `ai-tasks/WISHENKA-29/20-architecture.md`
  - Reopened to document opt-in own-reservation confirmations and safe event semantics.
- [x] **STEP 3: Failing Repro Test**
  - Repro: `tests/test_notice_delivery_repro.py`
- [x] **STEP 4: Development**
  - [x] Added private birthday management and verified Telegram destinations.
  - [x] Added transactional shared-event intents and UTC occasion scheduling.
  - [x] Added live eligibility checks, shared rate limits and uncertainty resolution.
  - [x] Preserved receipt deduplication through migration and terminal-row cleanup.
  - [x] Added claim fencing, privacy, migration, throttling and integration tests.
- [x] **STEP 5: Code Cleanup**
  - Cleanup report: `ai-tasks/WISHENKA-29/40-code-cleanup.md`
  - Quality gate: 976 tests passed; Ruff, formatting, and Mypy passed.
- [x] **STEP 6: Observability**
  - Observability: `ai-tasks/WISHENKA-29/50-observability.md`
  - Tests: `tests/test_service_notice_observability.py`
- [x] **STEP 7: Technical Debt Analysis**
  - Analysis: `ai-tasks/WISHENKA-29/60-tech-debt.md`
- [x] **STEP 8: Dev Docs**
  - Created `doc/dev/notifications.md`
  - Updated `doc/dev/bot-scenarios.md`, `doc/dev/gift-receipt.md`, `doc/dev/migrations.md`, and `doc/dev/architecture.md`
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-29/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-29/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-29/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-29/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-29/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/notifications.md`
- `doc/dev/bot-scenarios.md`
- `doc/dev/gift-receipt.md`
- `doc/dev/migrations.md`
- `doc/dev/architecture.md`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
