# Roadmap: WISHENKA-219

## Task Metadata

- **Implementation language**: `Python`

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - Clarify the boundary for receipt notices already accepted by the delivery provider.
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-219/20-architecture.md`
- [x] **STEP 3: Failing Repro Test**
  - `tests/test_wishenka_219_repro.py`
- [x] **STEP 4: Development**
  - [x] Added owner-only purchased-promise completion, API, cabinet action and localized outcomes.
  - [x] Added delivery locks and durable per-giver fence for both receipt queues, atomic queue suppression, and audited resolution.
  - [x] Added receipt, concurrency, idempotency and cross-process crash/recovery tests.
  - [x] Deferred unsent claims on busy locks and fences, preserving delivery attempts.
  - [x] Refreshed the home badge after completion and when restoring a cached page.
  - [x] Tested suspended and crashed senders before handoff and during delivery for both queues.
  - [x] Added nonblocking per-key `asyncio.Lock` to `delivery_lock` for in-process task exclusion and verified concurrent task fencing.
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-219/40-code-cleanup.md`
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-219/50-observability.md`
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-219/60-tech-debt.md`
- [x] **STEP 8: Dev Docs**
  - `doc/dev/architecture.md`
  - `doc/dev/reservations.md`
  - `doc/dev/notifications.md`
  - `doc/dev/gift-receipt.md`
  - `doc/dev/migrations.md`
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-219/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-219/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-219/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-219/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-219/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
