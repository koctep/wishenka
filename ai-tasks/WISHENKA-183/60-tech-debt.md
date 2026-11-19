# WISHENKA-183: Technical Debt Analysis

## Overview

All core requirements and architectural invariants for `WISHENKA-183` are implemented and verified:
- `NoticeStore.purge_finished` deletes expired terminal rows from `notification_outbox` and `reminder_outbox` in bounded per-transaction batches (`DEFAULT_PURGE_BATCH_SIZE = 500`, `batch_size >= 1`), draining backlogs while releasing the SQLite WAL write lock between batches.
- `wishenka/wishlists/alembic/versions/add_reminder_outbox_updated_at.py` adds `reminder_outbox.updated_at` and `idx_reminder_outbox_status_updated`, backfills `COALESCE(claimed_at, next_attempt_at)`, and is reversible.
- All `reminder_outbox` writers (`scheduler.py`, `events.py`, `reminders.py`, `store.py`, `worker.py`, `operator.py`) stamp `updated_at`.
- Both new test files (`tests/test_wishenka_183_repro.py` and `tests/test_wishenka_183_updated_at.py`) declare `pytestmark = pytest.mark.timeout(30)` (no `do-testing` timeout blocker).

No **Blocker** or **High** severity technical debt was introduced. Remaining trade-offs and follow-up opportunities are documented below.

## Shortcuts Taken

1. **Nullable `reminder_outbox.updated_at` with `COALESCE(updated_at, next_attempt_at)` fallback (`Low`):**
   - `add_reminder_outbox_updated_at.py` adds `updated_at INTEGER` as nullable (with backfill) and `NoticeStore._purge_batch` filters via `COALESCE(updated_at, next_attempt_at) <= :threshold_epoch`.
   - *Reason:* Preserves backward compatibility with existing test helpers and legacy SQL inserts that omit `updated_at` when inserting directly into `reminder_outbox`.
   - *Trade-off:* Prevents `COALESCE(...)` from using `idx_reminder_outbox_status_updated(status, updated_at)` as a range predicate (see Performance Concerns).
2. **Hardcoded `DEFAULT_PURGE_BATCH_SIZE = 500` (`Low`):**
   - `DEFAULT_PURGE_BATCH_SIZE` is a module constant in `wishenka/notices/store.py` rather than a `Settings` field in `wishenka/config.py`, and `wishenka/wishlists/cleanup.py` (`_purge_notices`) relies on the default without passing a configurable value.
3. **Optional `updated_at: int | None = None` in `settle_reminder` (`Low`):**
   - `wishenka/notices/reminders.py:settle_reminder` (and `NoticeStore.settle_reminder`) defaults `effective_updated = next_attempt if updated_at is None else updated_at` to keep existing callers/tests compatible.
   - *Risk:* Any future caller settling a row with `status='pending'` and a future `next_attempt` without passing `updated_at=now` would record a future `updated_at`. (`NoticeWorker.run_once` explicitly passes `updated_at=settled_at` for retryable errors, and `next_attempt = self._time(now)` for `skipped`/`sent`/`failed`/`uncertain`.)

## Code Quality Issues

1. **Inline SQLite `COALESCE` + subquery pattern in `NoticeStore._purge_batch` (`Low`):**
   - `wishenka/notices/store.py` repeats the `DELETE FROM <table> WHERE id IN (SELECT id FROM <table> WHERE ... ORDER BY id LIMIT :batch_size)` structure for `notification_outbox` and `reminder_outbox`. The two queries differ in timestamp type (ISO string vs. integer epoch) and active-cycle occasion guard, so keeping them explicit is readable, though a future schema unification (e.g., normalizing timestamp types across outboxes) could simplify them.

## Missing Tests

1. **Asymmetric queue draining (`Low`):**
   - `tests/test_wishenka_183_repro.py::test_purge_finished_drains_both_outboxes_and_preserves_protected_rows` seeds 5 expired rows in each outbox with `batch_size=2` (both drain in 3 batches). There is no dedicated test where one queue has `> batch_size` expired rows and the other has `0` or `1` rows to explicitly exercise independent `receipt_drained` / `reminder_drained` early-stop behavior.
2. **Additional `reminder_outbox` state-transition `updated_at` coverage (`Low`):**
   - `tests/test_wishenka_183_updated_at.py::test_reminder_outbox_writers_stamp_updated_at` covers `ReminderScheduler.run_once`, `EventProducer.record`, `NoticeWorker.run_once` retry path, `claim_reminder` stale recovery, and `operator.resolve(..., "fail", ...)`.
   - Not explicitly asserted in `test_wishenka_183_updated_at.py`: `claim_reminder` `skipped` transitions (unauthorized event / ineligible birthday or list), `claim_reminder` rate-limit backoff (`next_attempt_at = now + 1`), `claim_reminder` `sending` claim update, `NoticeWorker.run_once` terminal `sent`/`failed`/`uncertain` paths, `operator.resolve(..., "retry", ...)`, and `settle_reminder(..., updated_at=None)` fallback.

## Performance Concerns

1. **Index usability during `_purge_batch` scans (`Medium`):**
   - In `reminder_outbox`, `WHERE COALESCE(updated_at, next_attempt_at) <= :threshold_epoch AND status IN ('sent', 'skipped', 'failed') ... ORDER BY id LIMIT :batch_size` cannot use the `updated_at` column of `idx_reminder_outbox_status_updated(status, updated_at)` as a range bound because `COALESCE(...)` wraps the column in an expression.
   - In `notification_outbox`, the existing index is `idx_notice_outbox_due(status, next_attempt_at)` (`wishenka/wishlists/alembic/versions/add_notice_uncertain.py`), with no `(status, updated_at)` index.
   - Under a large backlog spanning many batches, each `_purge_batch` iteration may scan retained terminal rows within the retention window. Once all writers and test fixtures populate `reminder_outbox.updated_at` (or if an expression index / `NOT NULL` column + `(status, updated_at)` index on `notification_outbox` is added), each batch can seek directly by `(status, updated_at)`.
2. **Unbounded total batches per `purge_finished` invocation (`Low`):**
   - `purge_finished` bounds each SQLite write transaction to `batch_size` rows, but loops until both queues are completely drained. After a very long outage with hundreds of thousands of expired rows, a single `run_cleanup_cycle` invocation will execute all batches back-to-back before returning (though each transaction releases the WAL write lock in between).

## Follow-up Tasks

1. **[Medium] Index optimization for outbox retention purge:** — [WISHENKA-257](https://pypost.atlassian.net/browse/WISHENKA-257)
   - Add an index on `notification_outbox(status, updated_at)` and eliminate the `COALESCE(updated_at, next_attempt_at)` expression in `reminder_outbox` purge (after ensuring all test fixtures/writers set `updated_at` or using an expression/partial index) so `_purge_batch` seeks rather than scans retained terminal rows.
2. **[Low] Configurable `purge_batch_size` and optional per-cycle batch cap:** — [WISHENKA-258](https://pypost.atlassian.net/browse/WISHENKA-258)
   - Expose `notice_purge_batch_size` (and optionally `notice_purge_max_batches_per_cycle`) on `Settings` and pass it from `wishenka/wishlists/cleanup.py`.
3. **[Low] Expand `WISHENKA-183` unit test matrix:** — [WISHENKA-259](https://pypost.atlassian.net/browse/WISHENKA-259)
   - Add tests for asymmetric `receipt_drained` / `reminder_drained` multi-batch draining and remaining `claim_reminder` / `NoticeWorker` / `operator.resolve(..., "retry", ...)` `updated_at` transitions.
