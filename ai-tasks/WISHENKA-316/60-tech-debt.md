# WISHENKA-316: Technical Debt Analysis

No blockers. This change closes the retention copies WISHENKA-295 recorded as
S-1, S-2, and S-3. No new follow-up. The 25 full-suite failures stay the filed
pre-existing set. WISHENKA-311 did not fail that run.

Reviewed: `wishenka/wishlists/retention.py`, `wishenka/config.py`,
`wishenka/wishlists/__init__.py`, `get_wishlist_or_none` and
`classify_owner_delete` on `WishlistService` and `RepoWishlistOps`, list and
restore on both, `wishenka/wishlists/cleanup.py`, `get_retention_days` and
`delete_wishlist` in `wishenka/web/routes/wishlists.py`,
`wishenka/web/routes/miniapp.py`,
`tests/test_wishlist_retention_single_rule.py`, and the out-of-scope section
of `20-architecture.md`.

## Source items from WISHENKA-295

- **S-1 addressed.** The delete route calls `classify_owner_delete`. It does
  not read `service._wishlists` or `repo.get_wishlist`. The wishlist routes
  take the period from `get_retention_days`, which returns
  `wishlist_retention_days(settings)`. The Mini App shell does the same. No
  `getattr(..., "wishlist_retention_days", 30)` remains.
  `Settings.wishlist_retention_days` defaults to
  `DEFAULT_WISHLIST_RETENTION_DAYS`. List and restore defaults use that
  constant, so a caller that omits the argument still gets the usual 30.
  `list_wishlists` and the invite-token lookup still read `service._wishlists`.
  The architecture left those reads out of scope. They are not the delete
  classification. No new ticket.
- **S-2 addressed.** `is_retention_expired` is the comparison in
  `classify_owner_delete`, `list_deleted_wishlists`, and
  `restore_deleted_wishlist` on both backends. Each call looks the function up
  on `wishenka.wishlists.retention` at call time. Cleanup builds the purge
  cutoff with `purge_threshold` and `wishlist_retention_days`. The delete route
  no longer compares `updated_at` itself. Both backends still implement
  `classify_owner_delete`. That pair is the architecture for the two adapters.
  Each list method still builds the payload expiry as
  `deletion_moment + timedelta(days=retention_days)`. `days_remaining` uses the
  same addition. That instant is the list field, not a second restorability
  rule. No follow-up.
- **S-3 addressed.** `data-retention-days` is filled only by
  `wishlist_retention_days`. The shell has no private 30. A cached shell picks
  up a new period on the next document load, which is what the requirements
  call the next open. No bootstrap field was added. No ticket.

## Shortcuts Taken

None left as a temporary fix. The wishlists package loads public names on first
use so `config` can import `DEFAULT_WISHLIST_RETENTION_DAYS` while `Settings`
is still initializing. `retention.py` names `Settings` only for type checkers.
That is the cycle break this change required.

## Code Quality Issues

None introduced by this change.

Out of scope, unchanged, already named:

- Expired-path focus and the second Cancel name stay on
  [WISHENKA-317](https://pypost.atlassian.net/browse/WISHENKA-317)
  (WISHENKA-295 C-1, C-2, T-2).
- The shared expiry log in `execute` still says "Wishlist restore rejected
  because retention window expired". That wording, the denied-delete alert,
  and the dev-doc mismatches stay on
  [WISHENKA-318](https://pypost.atlassian.net/browse/WISHENKA-318)
  (WISHENKA-295 C-3, C-4, C-5). Step 8 may correct the dev docs. The log
  wording stays on WISHENKA-318.
- The plain web list screen still has no owner delete (S-4). That remains an
  open product decision. No ticket.
- Delete still cancels purchased reservations with no giver notice (S-5).
  Unchanged. No new ticket.
- Favorite and history rows that can reappear after restore stay on
  [WISHENKA-302](https://pypost.atlassian.net/browse/WISHENKA-302) and
  [WISHENKA-303](https://pypost.atlassian.net/browse/WISHENKA-303). This change
  did not touch them.

## Missing Tests

None for this change. `tests/test_wishlist_retention_single_rule.py` sets
`pytestmark = pytest.mark.timeout(30)`. It forces `is_retention_expired` and
checks delete, recently deleted, and restore. The existing delete modules and
the cleanup tests remain the lock for the unpatched outcomes. No test added
here is missing an explicit timeout.

## Performance Concerns

None. Classification is one row lookup plus the comparison the route used to
do inline. Cleanup still issues one purge. The package pays the lazy import
once per process, on the first use of a public name.

## Follow-up Tasks

No new follow-up. This change does not need a ticket that does not already
exist.

Out of scope stays on the keys the architecture already names:
[WISHENKA-317](https://pypost.atlassian.net/browse/WISHENKA-317) and
[WISHENKA-318](https://pypost.atlassian.net/browse/WISHENKA-318).

### Pre-existing test failures

Step 4 `make test`: 2482 passed, 2 skipped, 25 failed. Those 25 are the filed
set below. They are `NON-BLOCKER — pre-existing`. This task did not cause
them. WISHENKA-311 did not fail that run. No new ticket.

Share-page and public-view cluster. Jira:
[WISHENKA-348](https://pypost.atlassian.net/browse/WISHENKA-348).

- `tests/test_wishlist_cards_browser.py::test_page_loads_offline_with_real_assets[share]`
  — NON-BLOCKER — pre-existing
- `tests/test_wishlist_cards_browser.py::test_share_page_toggles_cards[click]`
  — NON-BLOCKER — pre-existing
- `tests/test_wishlist_cards_browser.py::test_share_page_toggles_cards[Enter]`
  — NON-BLOCKER — pre-existing
- `tests/test_wishlist_cards_browser.py::test_share_page_toggles_cards[Space]`
  — NON-BLOCKER — pre-existing
- `tests/test_wishlist_mouse_reorder_browser.py::test_share_page_has_no_handle_and_cannot_reorder`
  — NON-BLOCKER — pre-existing
- `tests/test_bot_entry_repro.py::test_shared_link_hides_reservation_from_recipient`
  — NON-BLOCKER — pre-existing
- `tests/test_bot_entry_repro.py::test_anonymous_public_api_does_not_disclose_reservations`
  — NON-BLOCKER — pre-existing
- `tests/test_wishenka_63_repro.py::test_public_api_endpoints_anonymous_recipient_and_gifter_views`
  — NON-BLOCKER — pre-existing

Archived-item error mapping. Jira:
[WISHENKA-264](https://pypost.atlassian.net/browse/WISHENKA-264).

- `tests/test_items_ui_error_mapping.py::test_archived_wishlist_gives_409[archive-confirm]`
  — NON-BLOCKER — pre-existing
- `tests/test_items_ui_error_mapping.py::test_archived_wishlist_gives_409[archive]`
  — NON-BLOCKER — pre-existing
- `tests/test_items_ui_error_mapping.py::test_unknown_wishlist_gives_404[archive-confirm]`
  — NON-BLOCKER — pre-existing
- `tests/test_items_ui_error_mapping.py::test_unknown_wishlist_gives_404[archive]`
  — NON-BLOCKER — pre-existing
- `tests/test_items_ui_error_mapping.py::test_non_member_gives_404[archive-confirm]`
  — NON-BLOCKER — pre-existing
- `tests/test_items_ui_error_mapping.py::test_non_member_gives_404[archive]`
  — NON-BLOCKER — pre-existing
- `tests/test_items_ui_error_mapping.py::test_unknown_item_gives_404[archive-confirm]`
  — NON-BLOCKER — pre-existing
- `tests/test_items_ui_error_mapping.py::test_unknown_item_gives_404[archive]`
  — NON-BLOCKER — pre-existing

- `tests/test_receipt_modal_browser.py::test_stale_giver_card_is_neutral`
  — NON-BLOCKER — pre-existing. Jira:
  [WISHENKA-265](https://pypost.atlassian.net/browse/WISHENKA-265).
- `tests/test_receipt_modal_browser.py::test_unmarked_error_neither_shows_notice_nor_reloads`
  — NON-BLOCKER — pre-existing. Jira:
  [WISHENKA-220](https://pypost.atlassian.net/browse/WISHENKA-220).
- `tests/test_wish_card_giver_controls.py::test_anonymous_share_shows_`
  `availability_without_a_book_control`
  — NON-BLOCKER — pre-existing. Jira:
  [WISHENKA-235](https://pypost.atlassian.net/browse/WISHENKA-235).
- `tests/test_receipt_notices_extra.py::test_cleanup_cycle_survives_a_failing_notice_purge`
  — NON-BLOCKER — pre-existing. Jira:
  [WISHENKA-245](https://pypost.atlassian.net/browse/WISHENKA-245).
- `tests/test_gift_receipt_migration.py::test_upgrade_is_repeatable`
  — NON-BLOCKER — pre-existing. Jira:
  [WISHENKA-232](https://pypost.atlassian.net/browse/WISHENKA-232).
- `tests/test_surprise_role_context.py::test_share_link_visit_creates_no_account`
  — NON-BLOCKER — pre-existing. Jira:
  [WISHENKA-298](https://pypost.atlassian.net/browse/WISHENKA-298).
- `tests/test_wishlist_htmx_smoke_browser.py::test_real_htmx_move_button_with_cookie_and_csrf`
  — NON-BLOCKER — pre-existing. Jira:
  [WISHENKA-267](https://pypost.atlassian.net/browse/WISHENKA-267).
- `tests/test_preview_resource_reuse.py::test_concurrent_responses_do_not_share_cookies`
  — NON-BLOCKER — pre-existing. Jira:
  [WISHENKA-212](https://pypost.atlassian.net/browse/WISHENKA-212).
- `tests/test_bot_capture_atomic_store_repro.py::`
  `test_bot_capture_save_uses_execute_with_connection_and_preserves_replay`
  — NON-BLOCKER — pre-existing. Jira:
  [WISHENKA-212](https://pypost.atlassian.net/browse/WISHENKA-212).

User documentation under `doc/` was not edited. Owner-visible behavior did not
change. Developer docs stay with Step 8.
