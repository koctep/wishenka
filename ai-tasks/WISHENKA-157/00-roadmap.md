# Roadmap: WISHENKA-157

## Task Metadata

- **Implementation language**: Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-157/10-requirements.md` — documented business goals, user stories, scope (9 hardening items from WISHENKA-23 T3), domain entities, non-functional requirements, Q&A, and Definition of Done.
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-157/20-architecture.md` — documented research, architectural decisions for all 9 T3 hardening items (deferred post-commit `item_fulfilled` logging, operator-only `receipt_notice_enqueue_failed`, `max_attempts` on `receipt_notice_retry_scheduled`, `item_archived` privacy fix, `last_error_class`/`ambiguous` SQL gauge semantics, deterministic worker loop testing, exact key-set assertions, and direct CC-13 coverage), and Step 3 failing-repro plan.
- [x] **STEP 3: Failing Repro Test**
  - `tests/test_receipt_observability.py` — red tests for `receipt_notice_retry_scheduled` (`max_attempts`), `item_archived` (no `active_reservations_count`), enqueue failure (`item_fulfilled` not emitted on rollback + `receipt_notice_enqueue_failed` operator error), plus exact key-set equality and worker-stop without summary counts.
  - `tests/test_receipt_concurrency.py` — direct CC-13 bounded-busy 503 no-leak test (`test_cc13_busy_503_bounded_and_identical_with_or_without_reservations`).
- [x] **STEP 4: Development**
  - [x] FR-2 (`wishenka/notices/worker.py`): Added `max_attempts: self._max_attempts` to `NoticeWorker._debug` when emitting `receipt_notice_retry_scheduled`.
  - [x] FR-3 (`wishenka/wishlists/store.py`): Emitted operator-only `ERROR` `receipt_notice_enqueue_failed` with `error_class` only on `wishenka.wishlists.notices` in `WishlistStore._flush_receipt_effects` before re-raising.
  - [x] FR-5 (`wishenka/wishlists/service.py`, `tests/test_wish_items_crud_api.py`): Removed `active_reservations_count` from `item_archived` and updated `test_item_lifecycle_observability_events`.
  - [x] FR-6 (`wishenka/wishlists/service.py`, `wishenka/wishlists/store.py`): Added `PendingCommitLog` / `_defer_commit_logs` / `_pending_commit_logs` and `flush_pending_commit_logs` so `item_fulfilled` is emitted only after `WishlistStore` commits, while preserving immediate logging for standalone `WishlistService.in_memory()`.
  - [x] NFR-1 (`tests/test_receipt_notices_extra.py`): Replaced `asyncio.sleep(0.6)` in `test_run_loop_logs_one_error_per_failure_streak` with deterministic `wishenka.notices.worker.asyncio.wait_for` interception.
  - [x] Verified `make analyze` (`ruff check`, `ruff format --check`, `mypy`: 0 issues) and targeted `pytest` suite (81 passed; 1 pre-existing baseline failure `test_cleanup_cycle_survives_a_failing_notice_purge`).
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-157/40-code-cleanup.md` — verified `make analyze` (Ruff lint, Ruff format, Mypy: 0 issues across 225 files), module-level `pytest.mark.timeout(...)` markers on all 4 modified test files, absence of debug prints/unused imports/merge conflicts, and targeted `pytest` run (41 passed, 1 pre-existing baseline failure `test_cleanup_cycle_survives_a_failing_notice_purge` / `WISHENKA-245`).
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-157/50-observability.md`
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-157/60-tech-debt.md`
- [x] **STEP 8: Dev Docs**
  - `doc/dev/notifications.md` — documented `receipt_notice_worker_started` / `receipt_notice_worker_stopped` (`INFO` without summary counts), `receipt_notice_worker_disabled`, `receipt_notice_enqueue_failed` (operator `ERROR`, `error_class` only), `max_attempts` on `receipt_notice_retry_scheduled`, `last_error_class` and `ambiguous` SQL gauge semantics on `notification_outbox`, post-commit `item_fulfilled`, and `item_archived` without `active_reservations_count`.
  - `doc/dev/gift-receipt.md` — updated logging table and rules for `receipt_notice_enqueue_failed`, `max_attempts` on `receipt_notice_retry_scheduled`, post-commit `item_fulfilled`, `item_archived` privacy contract, and `last_error_class` / `ambiguous` SQL gauge semantics.
  - `doc/dev/items.md` & `doc/dev/reservations.md` — aligned `item_archived` (omits `active_reservations_count`) and `item_fulfilled` (post-commit under `WishlistStore`) references.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-157/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-157/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-157/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-157/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-157/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
