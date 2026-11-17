# Roadmap: WISHENKA-61

## Task Metadata

- **Implementation language**: Python 3.12+

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - [ ] `ai-tasks/WISHENKA-61/10-requirements.md` — Business requirements, user stories, scope, and acceptance criteria
- [x] **STEP 2: High-Level Architecture Design**
  - [ ] `ai-tasks/WISHENKA-61/20-architecture.md` — High-level architecture, SQLite idempotency schema, request fingerprinting, replay/concurrency, TMA retry, and Step 3 failing-repro plan
- [x] **STEP 3: Failing Repro Test**
  - [ ] `tests/test_booking_idempotency.py` — Red automated repro tests for booking/receipt idempotency replay, payload mismatch 409, invalid header 400, cross-actor isolation, and Surprise Invariant on replay
- [x] **STEP 4: Development**
  - [x] Iteration 1: Added Alembic migration `add_idempotency_records`, `Settings.idempotency_retention_hours`, `InvalidIdempotencyKeyError`, and `IdempotencyConflictError`
  - [x] Iteration 2: Added web idempotency helper (`wishenka/web/idempotency.py`) for header validation, canonical SHA-256 request hashing, and response serialization/replay
  - [x] Iteration 3: Implemented `WishlistStore.execute_wish_idempotent()`, Surprise/membership replay verification, `cleanup_expired_idempotency_records()`, and wired cleanup into `run_cleanup_cycle()`
  - [x] Iteration 4: Wired `Idempotency-Key` handling into all 8 protected booking & gift-receipt endpoints (`reservations.py`, `wishlists.py`, `receipts.py`, `receipts_ui.py`)
  - [x] Iteration 5: Updated TMA frontend (`base.html`, `receipt.js`, `miniapp.js`) to generate `Idempotency-Key` per user action and reuse across network/503 retries
  - [x] Iteration 6: Added extended unit/integration/cleanup/concurrency/migration tests in `tests/test_booking_idempotency_extended.py` and verified `make test` and `make analyze`
- [x] **STEP 5: Code Cleanup**
  - [ ] `ai-tasks/WISHENKA-61/40-code-cleanup.md` — Code cleanup, formatting, linting, timeout audit, and `make check` verification
- [x] **STEP 6: Observability**
  - [ ] `ai-tasks/WISHENKA-61/50-observability.md` — Structured logging, counters, privacy audit, and observability test verification
  - [ ] `tests/test_wishenka_61_observability.py` — Observability and privacy-invariant tests for idempotency replay, conflict, invalid header, and cleanup
- [x] **STEP 7: Technical Debt Analysis**
  - [ ] `ai-tasks/WISHENKA-61/60-tech-debt.md` — Technical debt analysis, timeout marker audit, and follow-up tasks
- [x] **STEP 8: Dev Docs**
  - [x] `doc/dev/idempotency.md` — Client idempotency keys overview, architecture, schema, TMA lifecycle, config, observability, and troubleshooting
  - [x] `doc/dev/migrations.md` — Added revision 12 (`add_idempotency_records`) as Alembic head
  - [x] `doc/dev/architecture.md` — Added `wl_idempotency_records` and `doc/dev/idempotency.md` references
  - [x] `doc/dev/gift-receipt.md` — Updated migration chain to `add_idempotency_records` and cross-referenced `Idempotency-Key` support
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-61/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-61/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-61/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-61/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-61/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
