# Roadmap: WISHENKA-180

## Task Metadata

- **Implementation language**: Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - [x] `ai-tasks/WISHENKA-180/10-requirements.md` — Business and functional requirements documented
- [x] **STEP 2: High-Level Architecture Design**
  - [x] `ai-tasks/WISHENKA-180/20-architecture.md` — High-level architectural design and failing repro plan
- [x] **STEP 3: Failing Repro Test**
  - [x] `tests/test_notice_store_transaction_repro.py` — Red repro for missing public `NoticeStore.transaction()` and private `_store._store` access in `wishenka/notices/`
- [x] **STEP 4: Development**
  - [x] Iteration 1: Added `TransactionalStore` protocol in `wishenka/notices/models.py`, exposed `NoticeStore.transaction`, `claim_reminder`, `refresh_reminder`, and `settle_reminder` in `wishenka/notices/store.py`, generalized `ReminderScheduler` and `wishenka/notices/reminders.py` to `TransactionalStore`, and decoupled `NoticeWorker` from `NoticeStore._store` in `wishenka/notices/worker.py`.
  - [x] Verified static analysis (`ruff check`, `ruff format --check`, `mypy`: 0 issues across 227 files) and 70 notice/reminder tests (`test_notice_store_transaction_repro.py`, `test_notice_delivery_repro.py`, `test_receipt_notices.py`, `test_notice_operator.py`, `test_reminder_scan_paging.py`, `test_notice_worker_concurrency.py`: 70 passed).
- [x] **STEP 5: Code Cleanup**
  - [x] `ai-tasks/WISHENKA-180/40-code-cleanup.md` — Verified `make analyze` (`ruff check`, `ruff format --check`, `mypy`: 0 issues across 227 files) and 70 targeted notice/reminder tests (`70 passed`); no debug prints, unused code, or conflict markers found.
- [x] **STEP 6: Observability**
  - [x] `ai-tasks/WISHENKA-180/50-observability.md` — Evaluated observability for `NoticeStore.transaction`, `NoticeStore` reminder methods, `NoticeWorker`, and `ReminderScheduler` (pure interface refactoring; existing structured logging and windowed counters preserved)
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-180/60-tech-debt.md` — Technical debt analysis for `NoticeStore.transaction()` and `TransactionalStore` refactoring
- [x] **STEP 8: Dev Docs**
  - [x] `doc/dev/notifications.md` — Documented `TransactionalStore`, `NoticeStore.transaction`, `NoticeStore` reminder methods (`claim_reminder`, `refresh_reminder`, `settle_reminder`), `ReminderScheduler(store, settings)` accepting `TransactionalStore`, and removed resolved `WISHENKA-180` from Known Limitations.
  - [x] `doc/dev/testing.md` — Documented `tests/test_notice_store_transaction_repro.py` coverage for `NoticeStore.transaction` and AST check against private `_store` access.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-180/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-180/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-180/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-180/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-180/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
