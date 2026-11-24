# WISHENKA-80: Technical Debt Analysis

## Shortcuts Taken

1. **Standalone `RepoWishlistOps` adapter instead of refactoring `WishlistService`**:
   - Created `wishenka/wishlists/repo_ops.py` (1,139 lines) mirroring `WishlistService` domain operations against `WishlistRepository` instead of migrating `WishlistService` itself to `WishlistRepository` or calling `WishlistRepository` directly from route handlers.
2. **Legacy `app.state.wishlist_service` test-compatibility fallback in routes**:
   - All 6 migrated route modules (`wishenka/web/routes/wishlists.py`, `items.py`, `items_ui.py`, `receipts.py`, `receipts_ui.py`, `sharing.py`) retain `getattr(request.app.state, "wishlist_service", None)` dispatch branches so existing in-memory unit tests continue to work without SQLite or `dependency_overrides`.
3. **`ContextVar` + `asynccontextmanager` fallback in `receipts_ui.py`**:
   - `wishenka/web/routes/receipts_ui.py` (`_repo_ctx` and `_execute`) uses a `ContextVar` when set by a handler and falls back to `asynccontextmanager(get_wishlist_repository)(store)` when `_repo_ctx` is unset, instead of passing `repo: WishlistRepo` explicitly through all UI call chains.
4. **Generic `SQLAlchemyError` mapping without `SQLITE_BUSY` retry in `get_wishlist_repository`**:
   - `wishenka/web/dependencies.py:get_wishlist_repository` uses `conn.begin()` and converts any `SQLAlchemyError` (including transient `OperationalError` / `SQLITE_BUSY` under concurrent writes) into `RuntimeError("Wishlist storage operation failed")`, rather than retrying or mapping `SQLITE_BUSY` to `InventoryBusyError` as `WishlistStore.execute_wish` does.

## Code Quality Issues

1. **Domain logic duplication between `WishlistService` and `RepoWishlistOps`**:
   - Access-policy checks (`WishlistAccessPolicy`), `SharedEvent` recipient calculation (`record_shared_event`), token-collision retry loops (`_TOKEN_ATTEMPTS`), and `WishlistDetailViewDTO` projection (`project_wishlist_view`) are duplicated between `wishenka/wishlists/service.py` and `wishenka/wishlists/repo_ops.py`. Future rule changes must be applied in both places until `WishlistService` is unified or retired from web routes.
2. **Repeated route-level `execute` / `_execute` dispatch boilerplate**:
   - Each migrated route module defines its own local helper to switch between `app.state.wishlist_service` and `RepoWishlistOps(repo)`.
3. **Large module sizes**:
   - `wishenka/wishlists/repo_ops.py` (1,139 lines) and `wishenka/wishlists/repository.py` (1,169 lines) combine wishlists, items, members, tokens, favorites, receipts, and view history in single files; splitting by sub-domain would improve readability.
4. **Dynamic table name interpolation in `WishlistRepository._allocate_id`**:
   - `wishenka/wishlists/repository.py` (`_allocate_id`) interpolates `table_name` into `SELECT COALESCE(MAX(id), 0) FROM {table_name}`. All current callers pass hardcoded literals, but an explicit allowlist or `Literal[...]` constraint would make the invariant self-enforcing.

## Missing Tests

1. **Targeted unit tests for new `WishlistRepository` and `RepoWishlistOps` edge cases**:
   - `tests/test_web_repository_di_repro.py` and the existing API/observability suites cover route integration, but dedicated unit tests for `WishlistRepository.rotate_public_token` / `rotate_invite_token` (`TokenCollision` retry paths) and `reorder_items` edge cases are limited.
2. **Concurrent write contention (`SQLITE_BUSY`) test for `get_wishlist_repository`**:
   - No test verifies behavior when `get_wishlist_repository` encounters `SQLITE_BUSY` during concurrent write requests.
3. **Timeout markers**:
   - All 6 WISHENKA-80 test files (`tests/test_web_repository_di_repro.py`, `tests/test_gifted_section_ui.py`, `tests/test_items_ui_error_mapping.py`, `tests/test_wishlist_api.py`, `tests/test_wishlist_create_observability.py`, `tests/test_wishlist_delete_observability.py`) have explicit `pytestmark = pytest.mark.timeout(30)` markers (no blocker).

## Performance Concerns

1. **N+1 query in `RepoWishlistOps.get_history`**:
   - `wishenka/wishlists/repo_ops.py:get_history` calls `self.repo.list_view_history(user.telegram_id, limit=limit)` and then loops over each entry calling `await self.repo.get_wishlist(entry.wishlist_id)`, executing up to `limit` full-aggregate queries instead of a single batch header query.
2. **Single-wishlist full-aggregate loads on metadata-only mutations**:
   - Operations in `RepoWishlistOps` such as `archive_wishlist`, `unarchive_wishlist`, `delete_wishlist`, `regenerate_public_token`, `regenerate_invite_token`, and `add_member` call `get_wishlist_by_id` (`repo.get_wishlist`), which loads all items and reservations for that wishlist even when only `wl_lists` / `wl_members` (or `record_shared_event` recipients) are needed. This is a major improvement over full-database `WishlistStore._read()`, but can be narrowed further for large wishlists.

## Follow-up Tasks

### WISHENKA-80 Technical Debt Follow-ups

1. **Unify `WishlistService` and `RepoWishlistOps` / remove legacy route fallbacks**:
   - Consolidate duplicated domain/outbox logic between `wishenka/wishlists/service.py` and `wishenka/wishlists/repo_ops.py`, and remove `app.state.wishlist_service` fallback branches from `wishenka/web/routes/` once legacy in-memory tests use `dependency_overrides` or SQLite.
   - Jira: [WISHENKA-323](https://pypost.atlassian.net/browse/WISHENKA-323)
2. **Eliminate N+1 query in `RepoWishlistOps.get_history`**:
   - Add a batch `WishlistRepository.list_wishlists_by_ids` (or header-only) query and replace the per-entry `get_wishlist` loop in `wishenka/wishlists/repo_ops.py:get_history`.
   - Jira: [WISHENKA-325](https://pypost.atlassian.net/browse/WISHENKA-325)
3. **Remove `_repo_ctx` `ContextVar` fallback in `wishenka/web/routes/receipts_ui.py`**:
   - Pass `repo: WishlistRepo` explicitly to all `receipts_ui` handlers and helpers so `_repo_ctx` and `asynccontextmanager(get_wishlist_repository)` are no longer needed.
   - Jira: [WISHENKA-324](https://pypost.atlassian.net/browse/WISHENKA-324)
4. **Add `SQLITE_BUSY` retry / `InventoryBusyError` handling in `get_wishlist_repository`**:
   - Align `wishenka/web/dependencies.py:get_wishlist_repository` error/retry behavior with `WishlistStore` for transient SQLite write contention.
   - Jira: [WISHENKA-326](https://pypost.atlassian.net/browse/WISHENKA-326)
5. **Add unit tests for `WishlistRepository` token-rotation collisions and `get_wishlist_repository` contention**:
   - Cover `TokenCollision` retry paths in `rotate_public_token` / `rotate_invite_token` and concurrent write error handling.
   - Jira: [WISHENKA-327](https://pypost.atlassian.net/browse/WISHENKA-327)

### Pre-existing Failures (Already Ticketed — Do Not Duplicate)

- `WISHENKA-245` (`https://pypost.atlassian.net/browse/WISHENKA-245`) — `test_cleanup_cycle_survives_a_failing_notice_purge` (`NON-BLOCKER — pre-existing at ca2d7fa`)
- `WISHENKA-232` (`https://pypost.atlassian.net/browse/WISHENKA-232`) — `test_upgrade_is_repeatable` (`NON-BLOCKER — pre-existing at ca2d7fa`)
- `WISHENKA-264` (`https://pypost.atlassian.net/browse/WISHENKA-264`) — `test_items_ui_error_mapping.py` archive cases (`NON-BLOCKER — pre-existing at ca2d7fa`)
- `WISHENKA-235` (`https://pypost.atlassian.net/browse/WISHENKA-235`) — `test_anonymous_share_shows_availability_without_a_book_control` (`NON-BLOCKER — pre-existing at ca2d7fa`)
- `WISHENKA-298` (`https://pypost.atlassian.net/browse/WISHENKA-298`) — `test_share_link_visit_creates_no_account`, `test_wishlist_shared_view_observability` (`NON-BLOCKER — pre-existing at ca2d7fa`; note: `test_wishlist_shared_view_observability` now passes after the Step 6 `is_recipient` fix in `wishenka/web/routes/sharing.py`)
- `WISHENKA-220` (`https://pypost.atlassian.net/browse/WISHENKA-220`) — `test_unmarked_error_neither_shows_notice_nor_reloads` (`NON-BLOCKER — pre-existing at ca2d7fa`)
- `WISHENKA-265` (`https://pypost.atlassian.net/browse/WISHENKA-265`) — `test_stale_giver_card_is_neutral` (`NON-BLOCKER — pre-existing at ca2d7fa`)
- `WISHENKA-267` (`https://pypost.atlassian.net/browse/WISHENKA-267`) — `test_real_htmx_move_button_with_cookie_and_csrf` (`NON-BLOCKER — pre-existing at ca2d7fa`)
