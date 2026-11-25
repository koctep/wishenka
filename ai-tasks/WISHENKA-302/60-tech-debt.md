# WISHENKA-302: Technical Debt Analysis

## Shortcuts Taken

1. **Dual-stack enforcement (`RepoWishlistOps` + `WishlistRepository` vs `WishlistService` + `WishlistStore`):**
   - Access-control enforcement, share-access grant persistence, revocation on token rotation/restore/member removal, and deferred commit logging had to be implemented in parallel across both `wishenka/wishlists/repo_ops.py`/`wishenka/wishlists/repository.py` and `wishenka/wishlists/service.py`/`wishenka/wishlists/store.py` (including scoped `_load_wish`/`_persist_wish` snapshots for `execute_wish` / `execute_wish_idempotent`).
   - Additionally, `transfer_ownership` only exists on `WishlistService` and is not implemented on `RepoWishlistOps`.

2. **Irreversible legacy data purge in Alembic migration:**
   - `wishenka/wishlists/alembic/versions/add_share_access_and_purge_favorites.py` (`upgrade()`) permanently deletes all pre-existing non-member `wl_favorites` rows because prior share-link visits were not tracked before `wl_share_access` existed. `downgrade()` drops `wl_share_access` and `idx_wl_share_access_wishlist` but cannot restore purged `wl_favorites` rows.

3. **Downstream `wishenka/notices/` queries rely on eager cleanup rather than read-time filtering:**
   - `wishenka/notices/preferences.py`, `wishenka/notices/reminders.py`, and `wishenka/notices/scheduler.py` query `wl_favorites` directly without joining `wl_members` or `wl_share_access`. This is currently safe because `WISHENKA-302` purges legacy rows and eagerly deletes non-member `wl_favorites` on `remove_member`, `regenerate_public_token`, `restore_deleted_wishlist`, and `transfer_ownership`, but any future direct DB mutation or new token-rotation path would bypass notice filtering unless kept in sync.

4. **Viewing History (`wl_view_history`) remains unguarded:**
   - `RepoWishlistOps.record_view` / `get_history` and `WishlistService.record_view` / `get_history` still allow non-members without share-link access to record and list arbitrary wishlists. Explicitly deferred to `WISHENKA-303`.

## Code Quality Issues

1. **Over-fetching in `RepoWishlistOps.add_favorite` (`wishenka/wishlists/repo_ops.py`):**
   - `RepoWishlistOps.add_favorite` calls `await self.repo.get_wishlist(wishlist_id)` (which loads all items, reservations, and members) solely to check `status`, `owner_id`, `public_token`, and membership. A lighter header + membership lookup (e.g., `get_wishlist_header` + member check) would avoid loading items and reservations on every favorite addition.

2. **Row-by-row `wl_share_access` deletion in `WishlistStore._flush_service` (`wishenka/wishlists/store.py`):**
   - When `WishlistService` revokes share-access grants for a wishlist, `_flush_service` diffs `snapshot.share_access` and executes one `DELETE FROM wl_share_access WHERE user_id = :uid AND wishlist_id = :wid` statement per revoked user instead of a single bulk delete.
   - Similarly, `_load_wish` / `_persist_wish` only upserts dirty grants via `_upsert_dirty_share_access` and does not diff deletions (safe today because `execute_wish` / `execute_wish_idempotent` only grants access, never revokes it).

3. **Pre-existing misnamed observability event in `record_view` (`repo_ops.py` and `service.py`):**
   - `RepoWishlistOps.record_view` and `WishlistService.record_view` emit `event="favorite_deleted_wishlist_denied"` when a wishlist is deleted (copied from `add_favorite` prior to `WISHENKA-302`; left untouched as out of scope).

## Missing Tests

All new and modified test files (`tests/test_favorites_access_control.py` and all 11 updated test files) declare explicit `@pytest.mark.timeout(...)` markers (no `do-testing` timeout blockers).

Minor coverage gaps identified:
1. **HTML share route (`GET /share/{public_token}` in `wishenka/web/routes/sharing.py`):**
   - `tests/test_favorites_access_control.py` verifies share-access granting via `GET /api/public/wishlists/{token}/view` and `POST /api/public/wishlists/{token}/items/{item_id}/reservations`, but does not explicitly test an authenticated giver visiting `GET /share/{public_token}` and then calling `POST /api/favorites/{wishlist_id}`.
2. **Account deletion cleanup of `wl_share_access` (`wishenka/wishlists/deletion.py`):**
   - Explicit `DELETE FROM wl_share_access WHERE user_id = :uid` in `AccountDeletionService` is not directly asserted in `tests/test_favorites_access_control.py` or `tests/test_wishenka_75_user_fk_cascade.py`.

## Performance Concerns

1. **Full wishlist hydration on `POST /api/favorites/{wishlist_id}`:**
   - As noted under Code Quality Issues, `RepoWishlistOps.add_favorite` loads the entire wishlist aggregate (`get_wishlist`, including items and reservations) instead of only the wishlist header and membership row.
2. **Per-grant `DELETE` loop in `WishlistStore._flush_service`:**
   - For wishlists with many historical share-link visitors, rotating `public_token` via `WishlistStore` issues `N` individual `DELETE` statements on `wl_share_access` instead of a single `DELETE FROM wl_share_access WHERE wishlist_id = :wid`.

## Follow-up Tasks

- **Optimize `RepoWishlistOps.add_favorite` and `WishlistStore` bulk `wl_share_access` revocation** — Jira: [WISHENKA-344](https://pypost.atlassian.net/browse/WISHENKA-344)
  - Replace `get_wishlist(wishlist_id)` in `RepoWishlistOps.add_favorite` with a lightweight header + membership check, and batch `wl_share_access` deletions in `WishlistStore._flush_service`.
- **Add integration tests for `GET /share/{public_token}` favorite grant and `AccountDeletionService` `wl_share_access` cleanup** — Jira: [WISHENKA-345](https://pypost.atlassian.net/browse/WISHENKA-345)
  - Cover authenticated HTML share-link visits granting Favorites access and verify `wl_share_access` row removal on account deletion.
- **Filter `wishenka/notices/` `wl_favorites` queries by membership or valid `wl_share_access` (defense in depth)** — Jira: [WISHENKA-346](https://pypost.atlassian.net/browse/WISHENKA-346)
  - Add `wl_members` / `wl_share_access` predicates (or shared repository helper) in `wishenka/notices/preferences.py`, `reminders.py`, and `scheduler.py` so notification queries cannot drift from Favorites access rules.
- **Viewing History access control (`WISHENKA-303`)** — Jira: [WISHENKA-303](https://pypost.atlassian.net/browse/WISHENKA-303)
  - Already tracked separately; apply the same membership-or-share-access model to `wl_view_history` (`record_view` / `get_history`).

### Pre-Existing Test Failures Observed During Validation

- `NON-BLOCKER — pre-existing`: 17 failures observed in `make test` (`40-code-cleanup.md`) reproduce identically on base commit `b2dbf2d`:
  - `tests/test_items_ui_error_mapping.py::test_archived_wishlist_gives_409[archive-confirm]`
  - `tests/test_items_ui_error_mapping.py::test_archived_wishlist_gives_409[archive]`
  - `tests/test_items_ui_error_mapping.py::test_unknown_wishlist_gives_404[archive-confirm]`
  - `tests/test_items_ui_error_mapping.py::test_unknown_wishlist_gives_404[archive]`
  - `tests/test_items_ui_error_mapping.py::test_non_member_gives_404[archive-confirm]`
  - `tests/test_items_ui_error_mapping.py::test_non_member_gives_404[archive]`
  - `tests/test_items_ui_error_mapping.py::test_unknown_item_gives_404[archive-confirm]`
  - `tests/test_items_ui_error_mapping.py::test_unknown_item_gives_404[archive]`
  - `tests/test_receipt_modal_browser.py::test_stale_giver_card_is_neutral`
  - `tests/test_receipt_modal_browser.py::test_unmarked_error_neither_shows_notice_nor_reloads`
  - `tests/test_preview_resource_reuse.py::test_concurrent_responses_do_not_share_cookies`
  - `tests/test_wish_card_giver_controls.py::test_anonymous_share_shows_availability_without_a_book_control`
  - `tests/test_receipt_notices_extra.py::test_cleanup_cycle_survives_a_failing_notice_purge`
  - `tests/test_bot_capture_atomic_store_repro.py::test_bot_capture_save_uses_execute_with_connection_and_preserves_replay`
  - `tests/test_gift_receipt_migration.py::test_upgrade_is_repeatable`
  - `tests/test_surprise_role_context.py::test_share_link_visit_creates_no_account`
  - `tests/test_wishlist_htmx_smoke_browser.py::test_real_htmx_move_button_with_cookie_and_csrf`
- `NON-BLOCKER — pre-existing`: `tests/test_history_screen_browser.py::test_control_opening_an_entry_moves_it_to_the_top_and_navigation_works` failed under parallel `make test` load and passed on serial re-run (`make test-serial` -> `1 passed in 3.24s`).
