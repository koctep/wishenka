# WISHENKA-303: Technical Debt Analysis

## Shortcuts Taken

1. **Dual-path maintenance across `RepoWishlistOps` and `WishlistService`** (`wishenka/wishlists/repo_ops.py`, `wishenka/wishlists/service.py`):
   - Viewing-history authorization, revocation (`remove_member`, `regenerate_public_token`, `restore_deleted_wishlist`), and deferred commit logging (`defer_commit_log` vs `_emit_or_defer_commit_log`) are implemented independently in both `RepoWishlistOps` and `WishlistService`, while `transfer_ownership` exists only on `WishlistService`.

## Code Quality Issues

1. **Redundant authorization re-check in `RepoWishlistOps.get_history`** (`wishenka/wishlists/repo_ops.py#L1236-L1256`):
   - `WishlistRepository.list_view_history` (`wishenka/wishlists/repository.py#L1307-L1347`) already filters `wl_view_history` in SQL by non-deleted status and `(owner OR member OR valid wl_share_access)`, yet `RepoWishlistOps.get_history` re-runs `WishlistAccessPolicy.resolve_context` and `self.repo.has_valid_share_access(...)` for every returned entry.
2. **No timeout-marker gaps**:
   - Verified `pytest.mark.timeout(...)` markers are present in `tests/test_history_access_control.py` and all 10 modified test files (no `do-testing` blocker).

## Missing Tests

1. **Direct `WishlistService` / `WishlistStore` unit coverage for `record_view` and `get_history`**:
   - `tests/test_history_access_control.py` primarily exercises the HTTP routes (`RepoWishlistOps` + `WishlistRepository`). The parallel `WishlistService` implementation (`record_view`, `get_history`, and `remove_member` history revocation) has limited direct unit coverage in `tests/test_history_access_control.py`.

## Performance Concerns

1. **N+1 (1 + 2N) queries in `RepoWishlistOps.get_history`** (`wishenka/wishlists/repo_ops.py#L1240-L1256`):
   - `RepoWishlistOps.get_history` executes `list_view_history` (1 query), then loops over up to `limit` (default 20) entries calling `await self.repo.get_wishlist(entry.wishlist_id)` (loading full wishlist + items + members) and, for non-member share-link viewers, `await self.repo.has_valid_share_access(...)` (another query per entry).
   - For a giver with 20 shared wishlists in Viewing History, `GET /api/history` issues up to 41 SQLite queries instead of a single joined/batched query, even though `GET /api/history` only needs wishlist metadata (`id`, `title`, `description`, `event_title`, `event_date`, `owner_id`, `members`) and `list_view_history` already filtered access in SQL.

## Follow-up Tasks

### Follow-up Items

1. **Eliminate N+1 queries in `RepoWishlistOps.get_history` (`wishenka/wishlists/repo_ops.py`, `wishenka/wishlists/repository.py`)**:
   - Return hydrated wishlist summary/metadata (and effective role) directly from `WishlistRepository.list_view_history` or batch-load wishlists, removing the per-entry `get_wishlist` + `has_valid_share_access` loop.
   - Jira: [WISHENKA-325](https://pypost.atlassian.net/browse/WISHENKA-325)
2. **Add direct `WishlistService` / `WishlistStore` unit tests in `tests/test_history_access_control.py`**:
   - Cover direct `WishlistService.record_view` / `get_history` / `remove_member` behavior alongside the existing HTTP route and `transfer_ownership` tests.
   - Jira: [WISHENKA-347](https://pypost.atlassian.net/browse/WISHENKA-347)

### Pre-Existing Test Failures (`NON-BLOCKER — pre-existing`)

Observed during verified `make test` run on the current tree (`2475 passed, 2 skipped, 17 failed in 197.97s`; 0 failures caused by `WISHENKA-303`). All 17 failures reproduced identically on base commit `b2dbf2d` (as documented in `ai-tasks/WISHENKA-302/40-code-cleanup.md` and `ai-tasks/WISHENKA-302/60-tech-debt.md`):

- `tests/test_items_ui_error_mapping.py::test_archived_wishlist_gives_409[archive-confirm]` — `NON-BLOCKER — pre-existing` (reproduces at `b2dbf2d`, Jira: `WISHENKA-264`)
- `tests/test_items_ui_error_mapping.py::test_archived_wishlist_gives_409[archive]` — `NON-BLOCKER — pre-existing` (reproduces at `b2dbf2d`, Jira: `WISHENKA-264`)
- `tests/test_items_ui_error_mapping.py::test_unknown_wishlist_gives_404[archive-confirm]` — `NON-BLOCKER — pre-existing` (reproduces at `b2dbf2d`, Jira: `WISHENKA-264`)
- `tests/test_items_ui_error_mapping.py::test_unknown_wishlist_gives_404[archive]` — `NON-BLOCKER — pre-existing` (reproduces at `b2dbf2d`, Jira: `WISHENKA-264`)
- `tests/test_items_ui_error_mapping.py::test_non_member_gives_404[archive-confirm]` — `NON-BLOCKER — pre-existing` (reproduces at `b2dbf2d`, Jira: `WISHENKA-264`)
- `tests/test_items_ui_error_mapping.py::test_non_member_gives_404[archive]` — `NON-BLOCKER — pre-existing` (reproduces at `b2dbf2d`, Jira: `WISHENKA-264`)
- `tests/test_items_ui_error_mapping.py::test_unknown_item_gives_404[archive-confirm]` — `NON-BLOCKER — pre-existing` (reproduces at `b2dbf2d`, Jira: `WISHENKA-264`)
- `tests/test_items_ui_error_mapping.py::test_unknown_item_gives_404[archive]` — `NON-BLOCKER — pre-existing` (reproduces at `b2dbf2d`, Jira: `WISHENKA-264`)
- `tests/test_receipt_modal_browser.py::test_stale_giver_card_is_neutral` — `NON-BLOCKER — pre-existing` (reproduces at `b2dbf2d`, Jira: `WISHENKA-265`)
- `tests/test_receipt_modal_browser.py::test_unmarked_error_neither_shows_notice_nor_reloads` — `NON-BLOCKER — pre-existing` (reproduces at `b2dbf2d`, Jira: `WISHENKA-220`)
- `tests/test_wish_card_giver_controls.py::test_anonymous_share_shows_availability_without_a_book_control` — `NON-BLOCKER — pre-existing` (reproduces at `b2dbf2d`, Jira: `WISHENKA-235`)
- `tests/test_receipt_notices_extra.py::test_cleanup_cycle_survives_a_failing_notice_purge` — `NON-BLOCKER — pre-existing` (reproduces at `b2dbf2d`, Jira: `WISHENKA-245`)
- `tests/test_gift_receipt_migration.py::test_upgrade_is_repeatable` — `NON-BLOCKER — pre-existing` (reproduces at `b2dbf2d`, Jira: `WISHENKA-232`)
- `tests/test_surprise_role_context.py::test_share_link_visit_creates_no_account` — `NON-BLOCKER — pre-existing` (reproduces at `b2dbf2d`, Jira: `WISHENKA-298`)
- `tests/test_wishlist_htmx_smoke_browser.py::test_real_htmx_move_button_with_cookie_and_csrf` — `NON-BLOCKER — pre-existing` (reproduces at `b2dbf2d`, Jira: `WISHENKA-267`)
- `tests/test_preview_resource_reuse.py::test_concurrent_responses_do_not_share_cookies` — `NON-BLOCKER — pre-existing` (reproduces at `b2dbf2d`, Jira: `WISHENKA-212`)
- `tests/test_bot_capture_atomic_store_repro.py::test_bot_capture_save_uses_execute_with_connection_and_preserves_replay` — `NON-BLOCKER — pre-existing` (reproduces at `b2dbf2d`, Jira: `WISHENKA-212`)
