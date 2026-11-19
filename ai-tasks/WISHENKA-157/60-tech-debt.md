# WISHENKA-157: Technical Debt Analysis

## Shortcuts Taken

1. **Scoped post-commit log deferral to `item_fulfilled` only (`wishenka/wishlists/service.py`)**:
   - Only `WishlistService.record_item_fulfillment` (`item_fulfilled`, `wishenka/wishlists/service.py:2599`) was migrated to `self._emit_or_defer_commit_log(...)`. Other `logger.info` domain-mutation calls in `WishlistService` (such as `archive_wish_item` at line 1808, `restore_wish_item`, `create_reservation`, etc.) still log immediately before `WishlistStore` commits, meaning a rollback after service execution can still leave those `INFO` records in logs. This was an intentional scope boundary per NFR-3 (`item_fulfilled` was the target of FR-6).
2. **Direct private-flag mutation from `WishlistStore` (`wishenka/wishlists/store.py`)**:
   - `WishlistStore._read` (`store.py:470`) and `WishlistStore._load_wish` (`store.py:1405`) mutate `service._defer_commit_logs = True` directly instead of passing a keyword argument to `WishlistService.in_memory(defer_commit_logs=True)`.
3. **Preserved `last_error_class` / `ambiguous` DB transition behavior (`wishenka/notices/store.py`)**:
   - Instead of changing `notification_outbox` schema or `NoticeStore.complete` / `operator.resolve` transitions (which existing tests in `tests/test_receipt_notices.py` rely on), FR-4 was resolved by codifying SQL gauge query semantics (`WHERE status IN ('pending', 'uncertain', 'failed')` for `last_error_class` and `WHERE status = 'uncertain'` vs. `WHERE ambiguous = 1 AND status IN ('sent', 'failed')` for `ambiguous`) to be documented in Step 8 (`doc/dev/notifications.md`, `doc/dev/gift-receipt.md`).
4. **Monkeypatched `execute_wish` in CC-13 test (`tests/test_receipt_concurrency.py`)**:
   - `test_cc13_busy_503_bounded_and_identical_with_or_without_reservations` injects `InventoryBusyError` by monkeypatching `app.state.wishlist_store.execute_wish` rather than inducing real SQLite `SQLITE_BUSY` lock contention through `WishlistStore._immediate`. This deterministically verifies the HTTP route and `receipt_inventory_busy` log symmetry, while leaving the store-level busy-to-`InventoryBusyError` mapping under `WishlistStore` covered only by existing store tests.

## Code Quality Issues

1. **Duplicated post-commit log flushing in `WishlistStore` (`wishenka/wishlists/store.py`)**:
   - `execute_wish` (lines 1083–1085), `execute_wish_idempotent` (lines 1262–1264), and `_execute_once` (lines 1685–1687) each duplicate the same three-line post-commit sequence:
     - `_log_flushed_notices(flushed)`
     - `_log_flushed_shared_events(flushed_shared)`
     - `flush_pending_commit_logs(pending_commit_logs)`
   - Extracting a small shared helper (e.g., `_flush_post_commit_logs(flushed, flushed_shared, pending_commit_logs)`) would remove the duplication across all three transaction wrappers.
2. **Test timeout markers verified (no blocker)**:
   - All four modified test files declare explicit module-level `pytestmark = pytest.mark.timeout(...)` markers (`tests/test_receipt_concurrency.py`: 120s, `tests/test_receipt_notices_extra.py`: 60s, `tests/test_receipt_observability.py`: 60s, `tests/test_wish_items_crud_api.py`: 30s).

## Missing Tests

1. **Post-commit `item_fulfilled` deferral on `execute_wish_idempotent` and `_execute_once`**:
   - `tests/test_receipt_observability.py::test_enqueue_failure_rolls_back_without_item_fulfilled_and_logs_operator_error` exercises rollback via `WishlistStore.execute_wish`. There is no dedicated test verifying `PendingCommitLog` deferral/flush through `execute_wish_idempotent` (HTTP idempotent receipt path) or `_execute_once` on rollback.
2. **SQL gauge query verification for `last_error_class` and `ambiguous`**:
   - No dedicated test runs the documented SQL gauge queries against `notification_outbox` after `NoticeStore.complete` and `operator.resolve(..., action="retry" | "fail")` to guard against future query or transition drift.
3. **End-to-end CC-13 SQLite lock contention test**:
   - No test holds an actual SQLite `BEGIN IMMEDIATE` write lock across `app.state.wishlist_store` to verify CC-13 end-to-end (SQLite busy -> `InventoryBusyError` -> 503) with 0 vs. active reservations without monkeypatching `execute_wish`.

## Performance Concerns

None identified in the WISHENKA-157 changes:
- `PendingCommitLog` buffers at most one small dataclass entry per `record_item_fulfillment` call inside a transaction and flushes synchronously in memory after commit.
- `NoticeWorker._debug` adds a single attribute lookup (`self._max_attempts`) to an existing `DEBUG` log dict.
- `WishlistStore._flush_receipt_effects` adds a `try/except` around an existing loop with zero overhead on the happy path.
- `test_run_loop_logs_one_error_per_failure_streak` eliminated the 0.6s wall-clock sleep, improving test suite speed and determinism.

## Follow-up Tasks

- **Pre-existing failing test (already triaged)**:
  - `tests/test_receipt_notices_extra.py::test_cleanup_cycle_survives_a_failing_notice_purge` — `NON-BLOCKER — pre-existing` — Jira: [WISHENKA-245](https://pypost.atlassian.net/browse/WISHENKA-245).
- **Consolidate post-commit log flushing and `defer_commit_logs` API (`wishenka/wishlists/service.py`, `wishenka/wishlists/store.py`)**:
  - Add `defer_commit_logs: bool = False` parameter to `WishlistService.in_memory(...)` instead of mutating `service._defer_commit_logs = True` from `WishlistStore`, and extract a shared `_flush_post_commit_logs(...)` helper in `WishlistStore`. — Jira: [WISHENKA-246](https://pypost.atlassian.net/browse/WISHENKA-246)
- **Extend deferred post-commit logging to remaining `WishlistService` domain `INFO` events**:
  - Audit and migrate remaining `logger.info` mutation logs in `WishlistService` (e.g., `item_archived`, `item_restored`, reservation events) to `_emit_or_defer_commit_log` so no domain `INFO` log is emitted on transaction rollback; add rollback tests for `execute_wish_idempotent` and `_execute_once`. — Jira: [WISHENKA-248](https://pypost.atlassian.net/browse/WISHENKA-248)
- **Add SQL gauge contract tests for `last_error_class` and `ambiguous`**:
  - Add a test in `tests/test_receipt_observability.py` or `tests/test_receipt_notices.py` verifying the documented SQL gauge queries on `notification_outbox` across `sent`, `uncertain`, `failed`, and `operator.resolve` transitions. — Jira: [WISHENKA-247](https://pypost.atlassian.net/browse/WISHENKA-247)
