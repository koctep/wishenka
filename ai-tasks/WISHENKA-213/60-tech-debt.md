# WISHENKA-213: Technical Debt Analysis

## Shortcuts Taken

1. **Read-only single-wishlist methods still execute inside `BEGIN IMMEDIATE` write transactions** (`wishenka/wishlists/service.py`, `wishenka/wishlists/store.py`):
   - Read-only methods in `_SINGLE_WISHLIST_METHODS` (`get_wishlist_by_id`, `get_wishlist_view`, `get_members`, `get_wish_item`, `list_wish_items`, `list_gifted_items`, `is_favorite`) are routed through `WishlistStore.execute(..., wishlist_id=...)`.
   - Unlike `WishlistStore.execute_read(...)`, `execute()` opens a `BEGIN IMMEDIATE` write transaction and runs `_write()`, which re-issues `UPDATE` statements for the wishlist and all its loaded members, items, and reservations plus 5 `wl_counters` upserts even though no state was modified.
2. **Remaining unscoped `WishlistService` and `bot/capture.py` operations** (`wishenka/wishlists/service.py`, `wishenka/bot/capture.py`):
   - `record_view` (which enforces a 20-entry per-user cap across all wishlists), `list_favorites`, `get_history`, `clear_history`, `list_deleted_wishlists`, and `wishenka/bot/capture.py` (`lists_for`, `mutate`) continue to use unscoped `execute()` / `execute_with_connection()` (`wishlist_id=None`), hydrating all wishlists and related tables.
3. **Unconditional `UPDATE`s and `wl_counters` upserts in `WishlistStore._write()`** (`wishenka/wishlists/store.py`):
   - Unlike `_persist_wish` (which tracks `_item_state` and `_reservation_state` to skip unchanged rows), `_write()` unconditionally executes `UPDATE` statements for every loaded wishlist, member, item, and reservation and upserts all 5 `wl_counters` rows on every scoped `execute()` call.

## Code Quality Issues

1. **Manual method-name allowlist `_SINGLE_WISHLIST_METHODS`** (`wishenka/wishlists/service.py`):
   - `_wishlist_scope()` relies on a hardcoded `frozenset` of 23 method names (`_SINGLE_WISHLIST_METHODS`) and `inspect.signature(method).bind(...)` to extract `wishlist_id`. Any newly added `WishlistService` method accepting `wishlist_id` will silently fall back to full-database hydration (`wishlist_id=None`) unless explicitly added to `_SINGLE_WISHLIST_METHODS`.
2. **Repeated `WHERE`-clause string interpolation in `WishlistStore._read()`** (`wishenka/wishlists/store.py`):
   - `_read()` constructs SQL queries by interpolating `l_where`, `m_where`, `i_where`, `item_subquery`, and `fav_where` into `text(...)` strings. While safe (values are bound via `scope_params`), it repeats the `if wishlist_id is not None` branching across six queries.

## Missing Tests

1. **Scoped-hydration telemetry not explicitly asserted for all `_SINGLE_WISHLIST_METHODS`**:
   - `tests/test_wishenka_213_scoped_store_repro.py` explicitly asserts `scoped=True` / `wishlists_count=1` for 7 mutations (`reorder_wish_items`, `add_wish_item`, `archive_wish_item`, `update_wishlist_settings`, `add_member`, `regenerate_public_token`, `add_favorite`), `get_wishlist_by_id` (missing ID), `regenerate_invite_token`, and concurrent `add_wish_item`.
   - The remaining 14 `_SINGLE_WISHLIST_METHODS` (`remove_member`, `delete_wishlist`, `restore_deleted_wishlist`, `transfer_ownership`, `restore_wish_item`, `archive_wishlist`, `unarchive_wishlist`, `remove_favorite`, `get_wishlist_view`, `list_wish_items`, `list_gifted_items`, `get_members`, `get_wish_item`, `is_favorite`) share the same `_wishlist_scope` dispatch and are covered by existing functional tests, but lack explicit `wishlist_store_read` / `wishlist_store_write` scoping assertions in `tests/test_wishenka_213_scoped_store_repro.py`.
2. **Timeout markers check**:
   - `tests/test_wishenka_213_scoped_store_repro.py` sets `pytestmark = pytest.mark.timeout(30)` (no `do-testing` blocker).

## Performance Concerns

1. **Write-lock contention and unnecessary writes on read-only `_SINGLE_WISHLIST_METHODS`**:
   - Routing `get_wishlist_by_id`, `get_wishlist_view`, `get_members`, `get_wish_item`, `list_wish_items`, `list_gifted_items`, and `is_favorite` through `execute()` (`BEGIN IMMEDIATE` + `_write()`) acquires an exclusive SQLite write lock and performs redundant `UPDATE`s for pure reads.
2. **No dirty-tracking in `_write()` for large single wishlists**:
   - For a wishlist with many items, members, or reservations, `_write()` still updates every row in that wishlist even if only a single field or item changed.
3. **Full-database hydration on user-scoped operations**:
   - `record_view`, `list_favorites`, `get_history`, `clear_history`, and `list_deleted_wishlists` still run with `wishlist_id=None`, so their read/write cost continues to scale with total database size.

## Follow-up Tasks

| ID | Priority | Area | Description | Impact / Remediation | Jira |
| --- | --- | --- | --- | --- | --- |
| TD-1 | Medium | Wishlists / Performance | Route read-only `_SINGLE_WISHLIST_METHODS` (`get_wishlist_by_id`, `get_wishlist_view`, `get_members`, `get_wish_item`, `list_wish_items`, `list_gifted_items`, `is_favorite`) through a read-only `WishlistStore` transaction instead of `BEGIN IMMEDIATE` + `_write()` | Eliminates exclusive write-lock acquisition and redundant `UPDATE`s on read-only single-wishlist calls. | [WISHENKA-338](https://pypost.atlassian.net/browse/WISHENKA-338) |
| TD-2 | Low | Wishlists / Storage | Add dirty-state tracking to `WishlistStore._write()` (similar to `_persist_wish`) to skip unchanged rows and unchanged `wl_counters` upserts | Reduces write-transaction SQL statements for large single wishlists. | [WISHENKA-339](https://pypost.atlassian.net/browse/WISHENKA-339) |
| TD-3 | Low | Wishlists / Scalability | Add user-scoped hydration/persistence for `record_view`, `get_history`, `clear_history`, `list_favorites`, and `list_deleted_wishlists` (and evaluate `wishenka/bot/capture.py`) | Removes remaining full-database hydration paths in `WishlistService` and bot capture. | [WISHENKA-340](https://pypost.atlassian.net/browse/WISHENKA-340) |
| TD-4 | Low | Tests | Add explicit `scoped=True` / `wishlists_count=1` assertions in `tests/test_wishenka_213_scoped_store_repro.py` for remaining `_SINGLE_WISHLIST_METHODS` (`delete_wishlist`, `restore_deleted_wishlist`, `transfer_ownership`, `remove_member`, `restore_wish_item`, `remove_favorite`) | Ensures regression protection for all single-wishlist mutation paths. | [WISHENKA-341](https://pypost.atlassian.net/browse/WISHENKA-341) |
