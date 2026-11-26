# WISHENKA-323: Technical Debt Analysis

No blockers. `RepoWishlistOps` is the shared wishlist rule set. Screens build
it on the request repository and do not read `app.state.wishlist_service`.
A store-backed `WishlistService` shared method forwards through
`WishlistStore.run_repository` and does not snapshot. An in-memory shared
method logs `wishlist_repository_path_required` and raises
`WishlistNotFoundError`. `record_view` skips a visitor who has no `users`
row before the history insert. Settings, ownership transfer, reservations,
and receipts stay on the snapshot path, as `20-architecture.md` requires.

`tests/test_wishenka_323_one_wishlist_rule_set.py` has
`pytestmark = pytest.mark.timeout(30)`. Every other test module this task
edited already has a `pytest.mark.timeout` marker. No marker was added in
this step.

Reviewed: `wishenka/wishlists/service.py` (`_repository_forward`,
`_SHARED_REPOSITORY_METHODS`, `_lookup_wishlist`,
`_resolve_loaded_public_token`), `wishenka/wishlists/store.py`
(`run_repository`, `compose_response`), `wishenka/wishlists/repo_ops.py`
(`record_view`), `wishenka/bot/capture.py`, the screen routes that dropped
`app.state.wishlist_service`, `40-code-cleanup.md`, and
`50-observability.md`.

Baseline for the non-browser failures below is commit `b004048` (the tree
before this task's uncommitted edits), worktree `/tmp/baseline-WISHENKA-323`,
removed after the run. The same node ids fail there with the same errors
Step 5 recorded on the task tree.

## Shortcuts Taken

- **Shared public methods keep a raise that the wrapper never calls**
  (accepted shape). `_repository_forward` replaces each name in
  `_SHARED_REPOSITORY_METHODS`. With a store it calls
  `RepoWishlistOps` through `getattr` on the method name. Without a store
  it logs and raises. The original coroutine still raises
  `WishlistNotFoundError` so the signature stays on the class for invite
  TTL binding. That body does not run. See follow-up 1.
- **Inventory callbacks use private hydrated lookups** (accepted).
  `execute_wish` runs the original function on a service whose `_store` is
  `None`, so a public shared name fail-closes and never reads `_wishlists`.
  `submit_edit_item` in `wishenka/web/routes/items_ui.py` calls
  `_lookup_wishlist` and reads `_items`. `reserve_from_public_link` in
  `wishenka/web/routes/wishlists.py` calls `_resolve_loaded_public_token`,
  which also records the share grant on that hydrated graph so the grant
  commits with the reservation. The public token lookup for a screen stays
  on `RepoWishlistOps`.
- **A missing `users` row is reported as a missing wishlist** (accepted).
  `RepoWishlistOps.record_view` logs `view_history_user_missing` and raises
  `WishlistNotFoundError` with the wishlist-not-found text.
  `record_share_view_if_authenticated` already swallows that error, so a
  share or public view is not aborted. `POST /api/history/{wishlist_id}`
  surfaces the same not-found error. A separate exception would need every
  caller updated. See follow-up 2.
- **Settings, ownership transfer, and `is_favorite` still snapshot**
  (accepted). They stay on `_transactional`. Screens do not call them.
  Favorite checks on a screen use `WishlistRepository.is_favorite`.
- **Older history rows stay stored** (accepted). `record_view` updates one
  row and does not delete past 20. Listing still returns at most 20. That
  is the Mini App outcome this task was required to keep.
- **An idempotent receipt screen composes HTML on the wish connection**
  (accepted). `execute_wish_idempotent` takes `compose_response` and runs
  it after the wish rows are written and before the idempotency record is
  stored. Replay returns the stored body. A receipt post without an
  idempotency key still mutates and then reads on the receipt helper's
  second repository open. That second open is WISHENKA-324.

## Code Quality Issues

- **The shared-name set is a handwritten frozenset** (Medium).
  `_SHARED_REPOSITORY_METHODS` in `wishenka/wishlists/service.py` must match
  coroutine names on `RepoWishlistOps`. The forward uses `getattr`. A
  renamed repository method fails only when that action is called through
  `WishlistService`. A new public coroutine left out of the set goes back
  through `execute` and `_write`. See follow-up 1.
- **Developer docs still describe the injected service and the in-memory
  history prune** (Low; Step 8 of this task). Product code is ahead of
  `doc/dev/`:
  - `doc/dev/wishlists.md` still says `app.state.wishlist_service` can
    override the router, that both copies enforce `record_view`, and that
    the in-memory `record_view` drops rows past 20.
  - `doc/dev/miniapp.md` still says only the in-memory service prunes
    history storage to 20.
  - `doc/dev/items.md`, `doc/dev/reservations.md`, and
    `doc/dev/idempotency.md` still describe a test-injected
    `app.state.wishlist_service`.
  - The log tables do not list `wishlist_repository_path_required` or
    `view_history_user_missing`.
  Step 8 owns `doc/dev/`. No separate ticket if Step 8 updates these.
- **One foreign-key test docstring is stale** (Low, no follow-up).
  `tests/test_wishenka_75_user_fk_cascade.py::test_rejects_wishlist_user_links_for_nonexistent_user`
  still says a missing user must raise `IntegrityError` for view history.
  The assertion expects `WishlistNotFoundError`, which is the skip.

## Missing Tests

- **No check that the shared-name set is the repository forward** (Medium,
  follow-up 1). The task file locks three outcomes: a screen ignores an
  injected service, a store-backed `record_view` keeps 21 rows, and capture
  save calls `RepoWishlistOps.add_wish_item`. It does not walk
  `_SHARED_REPOSITORY_METHODS`.
- **The missing-user skip is only the exception type** (Low, follow-up 2).
  `test_rejects_wishlist_user_links_for_nonexistent_user` expects
  `WishlistNotFoundError` from `record_view`. Nothing asserts
  `view_history_user_missing`, an empty history table for that visitor, or
  HTTP 200 on the share page.

Reservation and receipt idempotency tests were not rewritten. They stay the
existing `execute_wish` coverage.

## Performance Concerns

`get_history` still loads one wishlist per history row, then may load share
access per non-member row. That cost is
[WISHENKA-325](https://pypost.atlassian.net/browse/WISHENKA-325). This task
did not change the list query.

Capture eligibility now calls `list_accessible_wishlists` instead of
hydrating every wishlist. That method still loads each accessible list with
`get_wishlist`. The keyboard is a smaller read than the old unscoped
snapshot. No new ticket.

`run_repository` adds no busy retry. The current busy error on a screen
request stays
[WISHENKA-326](https://pypost.atlassian.net/browse/WISHENKA-326).

## Follow-up Tasks

1. **Lock the shared-method set to `RepoWishlistOps`.** NON-BLOCKER, priority
   Medium. One test can call each name in `_SHARED_REPOSITORY_METHODS` on a
   store-backed `WishlistService` and assert the matching `RepoWishlistOps`
   coroutine ran, and assert an in-memory call does not run that coroutine.
   That also locks the wrapper as the public attribute, so a future edit to
   an unreachable stub cannot become a second rule body. Jira:
   [WISHENKA-350](https://pypost.atlassian.net/browse/WISHENKA-350).

2. **Lock the missing-user history skip.** NON-BLOCKER, priority Low. Assert
   `view_history_user_missing`, no `wl_view_history` row, and a share or
   public view that still returns HTTP 200 for an authenticated visitor with
   no `users` row. Jira:
   [WISHENKA-351](https://pypost.atlassian.net/browse/WISHENKA-351).

No other new ticket.

- Receipt-screen `_repo_ctx` and its managed-repository fallback stay on
  [WISHENKA-324](https://pypost.atlassian.net/browse/WISHENKA-324).
- History per-entry loads stay on
  [WISHENKA-325](https://pypost.atlassian.net/browse/WISHENKA-325).
- Busy-storage handling stays on
  [WISHENKA-326](https://pypost.atlassian.net/browse/WISHENKA-326).
- Extra link-clash checks on the snapshot path stay on
  [WISHENKA-327](https://pypost.atlassian.net/browse/WISHENKA-327). This task
  did not add a clash-only test.
- Developer docs and the two new log events in the tables are Step 8 of
  WISHENKA-323. No separate key.

Considered and dropped: deleting the unreachable stub bodies (the signatures
are what invite TTL binding reads); moving public-link reservation onto
`get_wishlist_by_public_token` inside `execute_wish` (that public name
fail-closes on the hydrated service); pruning history rows past 20 (the
Mini App outcome is to keep them); a new busy retry inside `run_repository`.

### Pre-existing test failures

These are `NON-BLOCKER — pre-existing`. This step did not file them again.
The non-browser node ids below fail at `b004048` with the same error Step 5
saw on the task tree. The three browser node ids were not re-run here; Step 5
recorded them as timeouts outside the repository-path change.

- `tests/test_gift_receipt_migration.py::test_upgrade_is_repeatable`
  — NON-BLOCKER — pre-existing. `notice_receipt_keys` column count. Jira:
  [WISHENKA-232](https://pypost.atlassian.net/browse/WISHENKA-232).
- `tests/test_wish_card_giver_controls.py::test_anonymous_share_shows_availability_without_a_book_control`
  — NON-BLOCKER — pre-existing. Share page is HTTP 200 and the availability
  copy is absent. Jira:
  [WISHENKA-235](https://pypost.atlassian.net/browse/WISHENKA-235).
- `tests/test_surprise_role_context.py::test_share_link_visit_creates_no_account`
  — NON-BLOCKER — pre-existing. Same missing availability copy. Jira:
  [WISHENKA-298](https://pypost.atlassian.net/browse/WISHENKA-298).
- `tests/test_receipt_modal_browser.py::test_stale_giver_card_is_neutral`
  — NON-BLOCKER — pre-existing. Jira:
  [WISHENKA-265](https://pypost.atlassian.net/browse/WISHENKA-265).
- `tests/test_receipt_modal_browser.py::test_unmarked_error_neither_shows_notice_nor_reloads`
  — NON-BLOCKER — pre-existing. Jira:
  [WISHENKA-220](https://pypost.atlassian.net/browse/WISHENKA-220).
- `tests/test_wishlist_htmx_smoke_browser.py::test_real_htmx_move_button_with_cookie_and_csrf`
  — NON-BLOCKER — pre-existing. Jira:
  [WISHENKA-267](https://pypost.atlassian.net/browse/WISHENKA-267).

Confirmed at `b004048` and already filed:

- `tests/test_receipt_notices_extra.py::test_cleanup_cycle_survives_a_failing_notice_purge`
  — NON-BLOCKER — pre-existing. `error_class` is `TypeError` where the test
  expects `RuntimeError`. Jira:
  [WISHENKA-245](https://pypost.atlassian.net/browse/WISHENKA-245).
- Eight archive cases in `tests/test_items_ui_error_mapping.py`
  — NON-BLOCKER — pre-existing. Each fails with
  `json.decoder.JSONDecodeError` while reading an HTML body. Jira:
  [WISHENKA-264](https://pypost.atlassian.net/browse/WISHENKA-264).
  - `tests/test_items_ui_error_mapping.py::test_archived_wishlist_gives_409[archive-confirm]`
  - `tests/test_items_ui_error_mapping.py::test_archived_wishlist_gives_409[archive]`
  - `tests/test_items_ui_error_mapping.py::test_unknown_wishlist_gives_404[archive-confirm]`
  - `tests/test_items_ui_error_mapping.py::test_unknown_wishlist_gives_404[archive]`
  - `tests/test_items_ui_error_mapping.py::test_non_member_gives_404[archive-confirm]`
  - `tests/test_items_ui_error_mapping.py::test_non_member_gives_404[archive]`
  - `tests/test_items_ui_error_mapping.py::test_unknown_item_gives_404[archive-confirm]`
  - `tests/test_items_ui_error_mapping.py::test_unknown_item_gives_404[archive]`

Confirmed at `b004048` and not named by an open issue (a text search for the
node id returned none; WISHENKA-212 does not name this test):

- `tests/test_preview_resource_reuse.py::test_concurrent_responses_do_not_share_cookies`
  — NON-BLOCKER — pre-existing. The test records one origin request and
  expects two (`assert 1 == 2`). Jira:
  [WISHENKA-352](https://pypost.atlassian.net/browse/WISHENKA-352).

User documentation under `doc/` was left unchanged. Developer docs for this
rule set belong to Step 8.
