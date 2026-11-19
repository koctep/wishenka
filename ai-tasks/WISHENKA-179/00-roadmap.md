# Roadmap: WISHENKA-179

## Task Metadata

- **Implementation language**: Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - [x] Created `ai-tasks/WISHENKA-179/00-roadmap.md` and `ai-tasks/WISHENKA-179/10-requirements.md` (business goals, scope, user stories, acceptance criteria, Python language recorded; awaiting review gate)
- [x] **STEP 2: High-Level Architecture Design**
  - [/] Created `ai-tasks/WISHENKA-179/20-architecture.md` (module diagram, interfaces, `WishlistStore.execute_with_connection` design, and Step 3 failing-repro plan; awaiting review gate)
- [x] **STEP 3: Failing Repro Test**
  - [ ] `tests/test_bot_capture_atomic_store_repro.py`
- [x] **STEP 4: Development**
  - [x] Added `WishlistStore.execute_with_connection` in `wishenka/wishlists/store.py` and delegated `WishlistStore.execute` to it (sharing retry, token-collision, `_read`/`_write`, error-mapping, and post-commit log flushing).
  - [x] Migrated `mutate` in `wishenka/bot/capture.py` from `store.transaction` + `store._read`/`store._write` to `store.execute_with_connection`, and added an AST private-access assertion in `tests/test_bot_capture_atomic_store_repro.py`.
  - [x] Verified `make analyze` (`ruff check`, `ruff format --check`, `mypy`) and pytest (`55 passed` across `tests/test_bot_capture_atomic_store_repro.py`, `tests/test_bot_capture_repro.py`, `tests/test_bot_capture_order_retention.py`, `tests/test_bot_capture_order_retention_repro.py`, `tests/test_receipt_concurrency.py`).
- [x] **STEP 5: Code Cleanup**
- [x] **STEP 6: Observability**
  - [x] Evaluated production observability of `WishlistStore.execute_with_connection` (`wishenka/wishlists/store.py`) and `wishenka/bot/capture.py:mutate`; confirmed existing structured logging and post-commit log flushing (`flushed`, `flushed_shared`, `pending_commit_logs`, `receipt_notice_enqueue_failed`, `bot_capture_save`, `bot_capture_action_error`) cover all paths without new ad-hoc logs. Created `ai-tasks/WISHENKA-179/50-observability.md`.
- [x] **STEP 7: Technical Debt Analysis**
  - [x] Analyzed `wishenka/wishlists/store.py`, `wishenka/bot/capture.py`, and `tests/test_bot_capture_atomic_store_repro.py`; created `ai-tasks/WISHENKA-179/60-tech-debt.md`
- [x] **STEP 8: Dev Docs**
  - [x] Updated `doc/dev/bot-scenarios.md`, `doc/dev/wishlists.md`, and `doc/dev/testing.md` to document `WishlistStore.execute_with_connection`, the `wishenka/bot/capture.py:mutate` migration, and `tests/test_bot_capture_atomic_store_repro.py`.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-179/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-179/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-179/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-179/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-179/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
