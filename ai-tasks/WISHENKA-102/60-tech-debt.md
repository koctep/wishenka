# WISHENKA-102: Technical Debt Analysis

## Shortcuts Taken

1. **Single-process `asyncio` concurrency only (`tests/test_wish_lifecycle_stress.py`):**
   - Multi-store contention tests (`test_concurrent_reorders_multiple_stores_preserve_permutation`, `test_mixed_lifecycle_waves_owner_and_coauthors`) instantiate multiple `WishlistStore` objects against the same SQLite WAL file within a single Python process and event loop. True multi-process OS-level contention (separate worker processes with independent `aiosqlite` connection threads) is not exercised.
2. **Contiguous `display_order` verified only after follow-up reorder in mixed archive/add scenarios (`tests/test_wish_lifecycle_stress.py`):**
   - In `test_concurrent_add_and_reorder_preserve_all_items` and `test_mixed_lifecycle_waves_owner_and_coauthors`, `require_contiguous_order=True` (`0..K-1`) is asserted only after a post-race `reorder_wish_items` call, and is omitted in `test_concurrent_archive_and_reorder_exclude_archived_items` and `test_concurrent_lifecycle_isolation_across_wishlists`. This reflects the current behavior of `WishlistService.archive_wish_item` (`wishenka/wishlists/service.py`), which marks `item.is_archived = True` without re-compacting `display_order` of remaining active items (leaving unique, ordered, non-contiguous `display_order` values until the next reorder).
3. **No production shortcuts:**
   - `WISHENKA-102` is a test-only task (`10-requirements.md`, `20-architecture.md`); no production files in `wishenka/` were modified.

## Code Quality Issues

1. **Explicit timeout markers (verified compliant — no blocker):**
   - `tests/test_wish_lifecycle_stress.py` defines `pytestmark = pytest.mark.timeout(120)` at module level (line 22) and enforces bounded waits (`_BARRIER_TIMEOUT_SECONDS = 15.0`, `_BATCH_TIMEOUT_SECONDS = 45.0`) inside `_run_barrier_tasks`.
2. **Inline operation factory duplication (`tests/test_wish_lifecycle_stress.py`):**
   - Helper closures (`make_add`, `make_reorder`, `make_archive`) with similar `try ... except ValueError: return ("stale_rejected", ...)` handling are repeated inline across `test_concurrent_add_and_reorder_preserve_all_items`, `test_concurrent_archive_and_reorder_exclude_archived_items`, `test_mixed_lifecycle_waves_owner_and_coauthors`, and `test_concurrent_lifecycle_isolation_across_wishlists`. Acceptable for self-contained test readability, but worth extracting if more stress tests are added.
3. **Asymmetric store setup in multi-store tests (`tests/test_wish_lifecycle_stress.py`):**
   - `test_concurrent_reorders_multiple_stores_preserve_permutation` (lines 228–266) and `test_mixed_lifecycle_waves_owner_and_coauthors` (lines 449–552) construct worker `WishlistStore` instances directly and dispose them manually in `finally`, rather than reusing `_open_wal_store` (which also asserts `PRAGMA journal_mode == "wal"`, `foreign_keys == 1`, and `busy_timeout == 5000`).

## Missing Tests

While all target scenarios in `10-requirements.md` (`add_wish_item`, `reorder_wish_items`, `archive_wish_item`, `Owner`/`Admin`/`Member` roles, single/multi-store, and multi-wishlist isolation) are covered, adjacent lifecycle and failure scenarios remain uncovered by stress tests:

1. **Concurrent `restore_wish_item` races:** restoring an archived item concurrently with `reorder_wish_items` and `archive_wish_item` (verifying stale reorder rejection and active-set consistency).
2. **Concurrent duplicate `archive_wish_item` on the same `item_id`:** verifying idempotent archiving and `shared_event` deduplication under simultaneous calls.
3. **Concurrent `update_wish_item` / `delete_wish_item` with `reorder_wish_items`:** verifying no lost updates or stale-snapshot corruption.
4. **Lock-timeout (`InventoryBusyError`) stress path:** holding a write lock beyond `busy_timeout=5000` ms to verify clean transaction rollback and zero partial state.
5. **Multi-process SQLite WAL contention:** separate OS processes racing on the same WAL database file.

## Performance Concerns

1. **Stress test runtime (~27–33s for 6 tests):**
   - Each test initializes a fresh SQLite database and runs Alembic `upgrade_to_head` plus multiple `WishlistStore.execute()` transactions, taking `26.94s` on `/dev/shm` and `28.49s`–`33.21s` on default temp storage (`00-roadmap.md`, `40-code-cleanup.md`).
2. **Full-database hydration in `WishlistStore.execute()` (`wishenka/wishlists/store.py`, pre-existing):**
   - `WishlistStore.execute()` runs `_read(conn)` to hydrate all wishlists and items into `WishlistService`, executes the operation in memory, and diffs/persists changes in `_write(conn, service, snapshot)` inside a single global `BEGIN IMMEDIATE` transaction. As database size grows, every `add_wish_item`, `reorder_wish_items`, or `archive_wish_item` call serializes globally across all wishlists and scales with total DB size rather than single-wishlist size.
3. **Full test suite I/O timeout (pre-existing):**
   - As recorded in `00-roadmap.md` (Step 4, Iteration 2), the full test suite (`1124` items) timed out at 900s (`exit 124` at 51%) under container storage I/O limits.

## Follow-up Tasks

- **NON-BLOCKER**: Add stress tests for concurrent `restore_wish_item`, `update_wish_item`, `delete_wish_item`, same-item `archive_wish_item` races, and `InventoryBusyError` rollback under `busy_timeout` exhaustion in `tests/test_wish_lifecycle_stress.py`. Jira: [WISHENKA-211](https://pypost.atlassian.net/browse/WISHENKA-211)
- **NON-BLOCKER**: Extract shared concurrent operation factory helpers in `tests/test_wish_lifecycle_stress.py` and unify multi-store initialization/pragma verification via `_open_wal_store` if the stress suite expands. Jira: [WISHENKA-210](https://pypost.atlassian.net/browse/WISHENKA-210)
- **NON-BLOCKER**: Evaluate scoping `WishlistStore.execute()` / `_read()` / `_write()` in `wishenka/wishlists/store.py` to the target `wishlist_id` (or targeted SQL updates) to avoid full-DB hydration on every wish lifecycle mutation. Jira: [WISHENKA-213](https://pypost.atlassian.net/browse/WISHENKA-213)
- **NON-BLOCKER — pre-existing**: Investigate the full-suite (`1124` items) 900s timeout (`exit 124` at 51%) under container storage I/O limits and the 9 pre-existing/unrelated failures observed in `00-roadmap.md` Step 4 Iteration 2 (exact test node IDs were not recorded in `00-roadmap.md`). Jira: [WISHENKA-212](https://pypost.atlassian.net/browse/WISHENKA-212)
