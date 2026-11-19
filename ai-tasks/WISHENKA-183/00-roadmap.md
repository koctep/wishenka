# Roadmap: WISHENKA-183

## Task Metadata

- **Implementation language**: Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - Created `ai-tasks/WISHENKA-183/00-roadmap.md` and `ai-tasks/WISHENKA-183/10-requirements.md`
- [x] **STEP 2: High-Level Architecture Design**
  - Created `ai-tasks/WISHENKA-183/20-architecture.md`
- [x] **STEP 3: Failing Repro Test**
  - `tests/test_wishenka_183_repro.py`
- [x] **STEP 4: Development**
  - [x] Added reversible Alembic migration `wishenka/wishlists/alembic/versions/add_reminder_outbox_updated_at.py` (`down_revision = "add_bot_capture_order_retention"`) adding `reminder_outbox.updated_at`, `idx_reminder_outbox_status_updated`, and `COALESCE(claimed_at, next_attempt_at)` backfill.
  - [x] Stamped `updated_at` on all `reminder_outbox` writers (`scheduler.py`, `events.py`, `reminders.py`, `store.py`, `worker.py`, `operator.py`).
  - [x] Implemented bounded per-transaction batched deletion (`DEFAULT_PURGE_BATCH_SIZE = 500`, `batch_size >= 1`) with `COALESCE(updated_at, next_attempt_at)` retention filtering in `NoticeStore.purge_finished`.
  - [x] Added writer and migration tests in `tests/test_wishenka_183_updated_at.py` and verified `tests/test_wishenka_183_repro.py` + targeted notice/migration suites + `make analyze`.
- [x] **STEP 5: Code Cleanup**
  - Created `ai-tasks/WISHENKA-183/40-code-cleanup.md`; verified `make analyze` (`ruff check`, `ruff format --check`, `mypy`), `git diff --check`, and `.venv/bin/pytest tests/test_wishenka_183_repro.py tests/test_wishenka_183_updated_at.py -v` (`5 passed`).
- [x] **STEP 6: Observability**
  - Extended `notice_outbox_purged` in `wishenka/notices/store.py` (`NoticeStore.purge_finished`) with `batches` and `batch_size` aggregate fields (no PII).
  - Added `test_purge_finished_logs_batch_count_and_batch_size` in `tests/test_wishenka_183_updated_at.py` and created `ai-tasks/WISHENKA-183/50-observability.md`.
- [x] **STEP 7: Technical Debt Analysis**
  - Created `ai-tasks/WISHENKA-183/60-tech-debt.md` analyzing shortcuts, code quality, missing tests, performance concerns, and follow-up items.
- [x] **STEP 8: Dev Docs**
  - [x] Updated `doc/dev/notifications.md` (`NoticeStore.purge_finished` bounded batching with `DEFAULT_PURGE_BATCH_SIZE = 500`, `reminder_outbox.updated_at` + `idx_reminder_outbox_status_updated`, `COALESCE(updated_at, next_attempt_at)` retention predicate, `notice_outbox_purged` `batches`/`batch_size` fields, and `tests/test_wishenka_183_*.py` in test command).
  - [x] Updated `doc/dev/migrations.md` (added `add_reminder_outbox_updated_at` to revision chain as head and reversible rollback table).
  - [x] Updated `doc/dev/gift-receipt.md` (aligned `Retention` section with batched `purge_finished`, `COALESCE(updated_at, next_attempt_at)`, and `batches`/`batch_size` log fields).
  - [x] Updated `doc/dev/testing.md` (documented `tests/test_wishenka_183_repro.py` and `tests/test_wishenka_183_updated_at.py`).
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-183/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-183/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-183/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-183/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-183/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
