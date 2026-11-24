# WISHENKA-176: Technical Debt Analysis

## Shortcuts Taken

- **In-memory `WishlistService` hydration for cabinet reads (`wishenka/wishlists/store.py`, `WishlistStore._cabinet_service`):**
  Rather than introducing a dedicated SQL-backed read projection or DTO mapper, `_cabinet_service` still constructs `WishlistService.in_memory()`, registers `Reservation` and `WishItem` domain objects, and delegates DTO projection to `WishlistService.get_user_reservations` / `get_user_reservations_summary`. This guarantees exact parity with in-memory business rules and Surprise Invariant checks, at the cost of instantiating full domain objects on every cabinet read.
- **Hardcoded batch chunk size (`wishenka/wishlists/repository.py`, `_ID_BATCH_SIZE = 500`):**
  The `IN (...)` chunk size is a module-level constant (`500`) chosen to stay below SQLite's `SQLITE_MAX_VARIABLE_NUMBER` limit rather than a configurable setting.
- **Wall-clock latency threshold in test (`tests/test_cabinet_batch_and_read_tx_repro.py:273`):**
  `test_cabinet_representative_volume_latency_and_chunking` asserts `elapsed < 1.0` for 60 items. While generous for local SQLite, wall-clock assertions can be sensitive under heavy CI CPU contention.

## Code Quality Issues

- **Duplicated column lists and hydration logic in `wishenka/wishlists/repository.py`:**
  - `get_wishlist_header` (lines 304–313) and `get_wishlist_headers_by_ids` (lines 315–347) duplicate the 15-column `wl_lists` `SELECT` list. `get_wishlist_header` could delegate to `get_wishlist_headers_by_ids([wishlist_id])` or share a column-list constant.
  - `get_item` (lines 664–685) and `get_items_by_ids` (lines 687–735) duplicate the 20-column `wl_items` `SELECT` list, the 7-column `wl_reservations` `SELECT` list, and the reservation-attachment loop. `get_item` could delegate to `get_items_by_ids([item_id])` or share hydration helpers.
- **Minor log metric asymmetry (`wishenka/wishlists/repository.py`):**
  `get_wishlist_headers_by_ids` and `get_items_by_ids` record `requested_count` using raw `len(wishlist_ids)` / `len(item_ids)` (before `dict.fromkeys` deduplication) while `found_count` reflects deduplicated rows.

## Missing Tests

- **Explicit timeout markers:** Verified compliant — `tests/test_cabinet_batch_and_read_tx_repro.py` declares `pytestmark = pytest.mark.timeout(60)` and `tests/test_reservation_index_lifecycle.py` declares `pytestmark = pytest.mark.timeout(30)`, with bounded internal `asyncio.wait_for` timeouts.
- **Concurrent writer test for `get_user_reservations_summary`:**
  `test_cabinet_read_does_not_block_concurrent_writer_and_keeps_snapshot` covers `get_user_reservations` under `execute_read`, but `get_user_reservations_summary` (also switched from `_immediate` to `execute_read`) lacks a dedicated concurrent-writer snapshot test.
- **End-to-end >500 persisted items chunking test:**
  `test_cabinet_representative_volume_latency_and_chunking` exercises >500 IDs directly on `WishlistRepository` with mostly nonexistent IDs (`range(10_000, 10_520)`), rather than >500 persisted items end-to-end through `WishlistStore.get_user_reservations`.
- **Direct empty-input tests for batch repository methods:**
  `WishlistRepository.get_items_by_ids([])` and `get_wishlist_headers_by_ids([])` early-return `{}` branches are not directly tested (skipped by `_cabinet_service` when `reservations` is empty).

## Performance Concerns

- **Full `wl_reservations` hydration per reserved `WishItem` (`WishlistRepository.get_items_by_ids`):**
  To compute `change_ceiling` and remaining availability, `get_items_by_ids` loads all `wl_reservations` rows (including cancelled and other users' reservations) for every `wish_item_id` in the giver's cabinet. If a single popular item accumulates a very large reservation history, row hydration scales linearly with total reservations on that item; a future optimization could aggregate active/purchased occupancy in SQL.
- **No retry on transient `SQLITE_BUSY` in `WishlistStore.execute_read`:**
  `execute_read` maps `SQLITE_BUSY` to `InventoryBusyError` without a bounded retry loop. While `BEGIN DEFERRED` WAL readers normally do not contend with writers, rare busy errors during WAL checkpointing or connection setup would fail immediately.

## Follow-up Tasks

- Deduplicate `WishlistRepository.get_wishlist_header` / `get_wishlist_headers_by_ids` and `get_item` / `get_items_by_ids` by delegating single-ID methods to the batch methods (or extracting shared column-list constants).
  - Jira: [WISHENKA-332](https://pypost.atlassian.net/browse/WISHENKA-332)
- Add concurrent-writer snapshot test coverage for `WishlistStore.get_user_reservations_summary`, direct empty-input tests for `get_items_by_ids([])` / `get_wishlist_headers_by_ids([])`, and an end-to-end multi-chunk (>500 persisted items) cabinet read test.
  - Jira: [WISHENKA-331](https://pypost.atlassian.net/browse/WISHENKA-331)
- Monitor reservation counts per `WishItem`; if popular items accumulate large reservation histories, consider SQL-side occupancy aggregation instead of loading all `wl_reservations` rows per item in `get_items_by_ids`.
  - Jira: [WISHENKA-333](https://pypost.atlassian.net/browse/WISHENKA-333)
