# WISHENKA-312: Technical Debt Analysis

No blockers. One deliberate confirmation already creates one wishlist and
sends one `POST /api/wishlists`. Steps 1–6 changed no production code, and
this step does not either. The in-flight guard (`submitting` plus
`withPending` on the Create button) and one insert per request were already
in place. The locks named in `20-architecture.md` already assert that rule,
and each of those modules carries an explicit `pytest.mark.timeout`
(`tests/test_wishlist_create_form_ui.py` 20,
`tests/test_wishlist_create_form_browser.py` 45,
`tests/test_cross_screen_comfort_browser.py` 45). No test was added or
edited, so there is no missing-timeout blocker.

Nothing below blocks closing WISHENKA-312. No new Jira issue is required.

## Shortcuts Taken

None. The product was left as it is because one confirmation already sends
one creation request. Opening, repeating, cancelling, or leaving "Create
wishlist" still creates nothing. A visible failure still allows one later
confirmation.

A retry after a lost response, where the server committed and the client
only saw a failure, is the limit already recorded for
[WISHENKA-322](https://pypost.atlassian.net/browse/WISHENKA-322). The
architecture keeps that limit there. It is not new debt from this task.

## Code Quality Issues

None from this task. `showCreate`, `withPending`, `create_wishlist`, and
`WishlistRepository.create_wishlist` were not edited. No hardcoded limit,
copy, or timeout was introduced.

## Missing Tests

None. No new behavior was added, so no new test was required. The existing
locks already cover one creation POST for a submit burst, Enter plus taps,
a real tap burst, both locales, no POST from the home action, and one later
request after a visible failure.

## Performance Concerns

None. One confirmation stays one request and one insert. No query, poll, or
client loop was added.

## Follow-up Tasks

No new follow-up. The items below already have tickets. Do not file them
again.

- Lost-response retry on `POST /api/wishlists` (no `Idempotency-Key`).
  Already owned by WISHENKA-322. Not debt introduced here.
  Jira: [WISHENKA-322](https://pypost.atlassian.net/browse/WISHENKA-322)

### Pre-existing test failures (`NON-BLOCKER — pre-existing`)

This task did not re-run the full suite. Step 4 re-ran only
`tests/test_wishlist_create_form_ui.py::test_submit_burst_sends_exactly_one_post`
(`make test-serial`), and it passed. The red suite already recorded in
`ai-tasks/WISHENKA-228/40-code-cleanup.md` stays on the tickets below.
No new ticket.

History-screen flake. Jira: [WISHENKA-311](https://pypost.atlassian.net/browse/WISHENKA-311).

- `tests/test_history_screen_browser.py::test_control_opening_an_entry_moves_it_to_the_top_and_navigation_works`
  — `NON-BLOCKER — pre-existing`

Share-page and public-view cluster. Jira: [WISHENKA-348](https://pypost.atlassian.net/browse/WISHENKA-348).

- `tests/test_wishlist_cards_browser.py::test_page_loads_offline_with_real_assets[share]`
  — `NON-BLOCKER — pre-existing`
- `tests/test_wishlist_cards_browser.py::test_share_page_toggles_cards[click]`
  — `NON-BLOCKER — pre-existing`
- `tests/test_wishlist_cards_browser.py::test_share_page_toggles_cards[Enter]`
  — `NON-BLOCKER — pre-existing`
- `tests/test_wishlist_cards_browser.py::test_share_page_toggles_cards[Space]`
  — `NON-BLOCKER — pre-existing`
- `tests/test_wishlist_mouse_reorder_browser.py::test_share_page_has_no_handle_and_cannot_reorder`
  — `NON-BLOCKER — pre-existing`
- `tests/test_bot_entry_repro.py::test_shared_link_hides_reservation_from_recipient`
  — `NON-BLOCKER — pre-existing`
- `tests/test_bot_entry_repro.py::test_anonymous_public_api_does_not_disclose_reservations`
  — `NON-BLOCKER — pre-existing`
- `tests/test_wishenka_63_repro.py::test_public_api_endpoints_anonymous_recipient_and_gifter_views`
  — `NON-BLOCKER — pre-existing`

The other 17 failures are the WISHENKA-303 set, already filed:

- `tests/test_items_ui_error_mapping.py::test_archived_wishlist_gives_409[archive-confirm]`
  — `NON-BLOCKER — pre-existing` (Jira: [WISHENKA-264](https://pypost.atlassian.net/browse/WISHENKA-264))
- `tests/test_items_ui_error_mapping.py::test_archived_wishlist_gives_409[archive]`
  — `NON-BLOCKER — pre-existing` (Jira: [WISHENKA-264](https://pypost.atlassian.net/browse/WISHENKA-264))
- `tests/test_items_ui_error_mapping.py::test_unknown_wishlist_gives_404[archive-confirm]`
  — `NON-BLOCKER — pre-existing` (Jira: [WISHENKA-264](https://pypost.atlassian.net/browse/WISHENKA-264))
- `tests/test_items_ui_error_mapping.py::test_unknown_wishlist_gives_404[archive]`
  — `NON-BLOCKER — pre-existing` (Jira: [WISHENKA-264](https://pypost.atlassian.net/browse/WISHENKA-264))
- `tests/test_items_ui_error_mapping.py::test_non_member_gives_404[archive-confirm]`
  — `NON-BLOCKER — pre-existing` (Jira: [WISHENKA-264](https://pypost.atlassian.net/browse/WISHENKA-264))
- `tests/test_items_ui_error_mapping.py::test_non_member_gives_404[archive]`
  — `NON-BLOCKER — pre-existing` (Jira: [WISHENKA-264](https://pypost.atlassian.net/browse/WISHENKA-264))
- `tests/test_items_ui_error_mapping.py::test_unknown_item_gives_404[archive-confirm]`
  — `NON-BLOCKER — pre-existing` (Jira: [WISHENKA-264](https://pypost.atlassian.net/browse/WISHENKA-264))
- `tests/test_items_ui_error_mapping.py::test_unknown_item_gives_404[archive]`
  — `NON-BLOCKER — pre-existing` (Jira: [WISHENKA-264](https://pypost.atlassian.net/browse/WISHENKA-264))
- `tests/test_receipt_modal_browser.py::test_stale_giver_card_is_neutral`
  — `NON-BLOCKER — pre-existing` (Jira: [WISHENKA-265](https://pypost.atlassian.net/browse/WISHENKA-265))
- `tests/test_receipt_modal_browser.py::test_unmarked_error_neither_shows_notice_nor_reloads`
  — `NON-BLOCKER — pre-existing` (Jira: [WISHENKA-220](https://pypost.atlassian.net/browse/WISHENKA-220))
- `tests/test_wish_card_giver_controls.py::test_anonymous_share_shows_availability_without_a_book_control`
  — `NON-BLOCKER — pre-existing` (Jira: [WISHENKA-235](https://pypost.atlassian.net/browse/WISHENKA-235))
- `tests/test_receipt_notices_extra.py::test_cleanup_cycle_survives_a_failing_notice_purge`
  — `NON-BLOCKER — pre-existing` (Jira: [WISHENKA-245](https://pypost.atlassian.net/browse/WISHENKA-245))
- `tests/test_gift_receipt_migration.py::test_upgrade_is_repeatable`
  — `NON-BLOCKER — pre-existing` (Jira: [WISHENKA-232](https://pypost.atlassian.net/browse/WISHENKA-232))
- `tests/test_surprise_role_context.py::test_share_link_visit_creates_no_account`
  — `NON-BLOCKER — pre-existing` (Jira: [WISHENKA-298](https://pypost.atlassian.net/browse/WISHENKA-298))
- `tests/test_wishlist_htmx_smoke_browser.py::test_real_htmx_move_button_with_cookie_and_csrf`
  — `NON-BLOCKER — pre-existing` (Jira: [WISHENKA-267](https://pypost.atlassian.net/browse/WISHENKA-267))
- `tests/test_preview_resource_reuse.py::test_concurrent_responses_do_not_share_cookies`
  — `NON-BLOCKER — pre-existing` (Jira: [WISHENKA-212](https://pypost.atlassian.net/browse/WISHENKA-212))
- `tests/test_bot_capture_atomic_store_repro.py::test_bot_capture_save_uses_execute_with_connection_and_preserves_replay`
  — `NON-BLOCKER — pre-existing` (Jira: [WISHENKA-212](https://pypost.atlassian.net/browse/WISHENKA-212))

User documentation was not edited. The owner's experience did not change.
The `doc/dev/miniapp.md` sentence belongs to Step 8.
