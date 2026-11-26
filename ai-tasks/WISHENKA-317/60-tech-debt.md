# WISHENKA-317: Technical Debt Analysis

No blockers were found. The 410 path and the delete Cancel name match
`20-architecture.md`. Reviewed: `wishenka/web/static/miniapp.js`
(`confirmDelete`, `deleteWishlistControls`), `wishenka/i18n/catalog.py`
(`miniapp.wishlist_delete.cancel_name`), `tests/test_wishlist_delete_ui.py`,
`tests/test_wishlist_delete_browser.py`, `40-code-cleanup.md`, and
`50-observability.md`.

Source items from `ai-tasks/WISHENKA-295/60-tech-debt.md`:

- **C-1 addressed.** On HTTP 410, `confirmDelete`
  (`wishenka/web/static/miniapp.js`) awaits `showHome()`, writes
  `miniapp.wishlist_delete.failed` with `status(..., 'error')`, sets
  `aria-label` on `#status` to that sentence, sets `aria-describedby="status"`
  on the home `h1`, focuses that heading, and returns. It does not write the
  detached `role="alert"` or call `yesBtn.focus()`.
- **C-2 addressed.** The delete Cancel keeps the visible
  `miniapp.wishlist_delete.cancel` ("Cancel" / "Отмена") and sets
  `aria-label` from `miniapp.wishlist_delete.cancel_name` with the list title
  (`catalog.py`, both locales). The settings Cancel is still created with
  only `miniapp.wishlist_settings.cancel` and has no `aria-label`.
- **T-2 addressed.** `test_expired_delete_focuses_the_home_heading_and_announces_the_failure`
  in `tests/test_wishlist_delete_ui.py` and
  `test_expired_delete_focuses_the_home_heading_and_describes_the_failure` in
  `tests/test_wishlist_delete_browser.py` cover Russian and English: connected
  home-heading focus, `tabindex="-1"`, `aria-describedby="status"`, assertive
  `#status` text, and (browser) the accessibility-tree description.

Timeouts are present. `tests/test_wishlist_delete_ui.py` has
`pytestmark = pytest.mark.timeout(20)`. `tests/test_wishlist_delete_browser.py`
has `pytestmark = [pytest.mark.timeout(45), pytest.mark.browser]`. The new
cases sit in those modules and inherit the marks. The Node harness subprocess
also passes `timeout=10`.

Every item below is NON-BLOCKER. Nothing here needs a new Jira issue.

## Shortcuts Taken

- **S-1 Accessible name follows the required strings** (accepted wording).
  English `Cancel deleting "{title}"` contains the visible word "Cancel", so
  a short "Cancel" speech command can still reach both Cancels; the full name
  is the distinct one. Russian `Отменить удаление «{title}»` does not contain
  the visible label "Отмена" (WCAG 2.5.3 Label in Name). `10-requirements.md`
  fixes both strings, and `20-architecture.md` says the Russian string stays
  as specified. The settings Cancel remains the control named "Отмена".
  No follow-up.

`withPending`'s `finally` still clears `disabled` on the confirm button after
the 410 `return`. That button is already off the document. The `finally` does
not write `#status`. `20-architecture.md` keeps that write. No follow-up.

## Code Quality Issues

- **D-1 Developer docs still describe the pre-fix 410 path and the shared
  Cancel name** (Low; Step 8 of this task). Product code is ahead of
  `doc/dev/`:
  - `doc/dev/miniapp.md` (410 bullet) still says the expired path writes the
    detached panel and that focus must not be documented. The same section's
    "Known accessibility smell" still treats the two Cancels as one name.
  - `doc/dev/i18n.md` still says twelve `miniapp.wishlist_delete.*` keys and
    omits `cancel_name`. The catalog now has thirteen keys in each locale.
    The note that `cancel` repeats `miniapp.wishlist_settings.cancel` is
    still true for the visible label; the accessible names now differ.
  - `doc/dev/testing.md` still counts 103 delete tests (49 UI, 15 browser)
    and says there is no focus or announcement check after 410
    (WISHENKA-317). Step 5 re-ran the two modules at 78 passed. The UI module
    docstring matches the green checks. The browser module docstring
    (`tests/test_wishlist_delete_browser.py`) still says the WISHENKA-317
    checks are red.
  Fix: Step 8, including that browser docstring. No new ticket if Step 8
  does it.

## Missing Tests

None for this task's definition of done. Interface and browser checks cover
the expired return and the distinct Cancel name in Russian and English,
including an empty title and a title with markup characters on the interface
check, and a markup title in the accessibility tree.

What this change added on top of older test debt stays on the existing keys:

- The UI module grew more `_NODE_HARNESS` string anchors (`h1` walk, focus
  fields, `replaceWith` / `remove`). The browser module's new helpers
  (`_ax_tree`, `_dom_backend_id`, `_accessible_button_name`) still call
  `page._send`. That is the WISHENKA-319 harness debt, widened here.
  Jira: [WISHENKA-319](https://pypost.atlassian.net/browse/WISHENKA-319).
- The new browser assertions read Chromium's accessibility tree only. No
  speech engine, WebKit, or Gecko run. Same limit as WISHENKA-313.
  Jira: [WISHENKA-313](https://pypost.atlassian.net/browse/WISHENKA-313).

## Performance Concerns

None. The 410 branch is the existing home reload plus one attribute and one
`focus()`. No new request, poll, or query. The two delete modules were 78
passed in 18.16s at Step 5.

## Follow-up Tasks

No new follow-up. This change does not need a ticket that does not already
exist.

- **D-1** is Step 8 of WISHENKA-317 (developer docs and the stale browser
  module docstring). No separate key.
- Harness and `page._send` growth stays on
  [WISHENKA-319](https://pypost.atlassian.net/browse/WISHENKA-319).
- Chromium-only accessibility checks stay on
  [WISHENKA-313](https://pypost.atlassian.net/browse/WISHENKA-313).
- **S-1** is the wording this task was required to ship. No ticket.

Considered and dropped: a second announcement node, a timer before focus,
changing the visible Cancel labels, and clearing `#status` from `withPending`.

### Pre-existing test failures

Step 4 `make test PYTEST_ARGS='-q --tb=no'`: 2495 passed, 2 skipped, 26 failed
in 247.78s. No delete-panel test failed. The 26 are the filed set below.
They are `NON-BLOCKER — pre-existing`. This task did not cause them. No new
ticket. The node ids are the ones already recorded for these keys (the
WISHENKA-316 set, plus the history flake that was absent from that run).

History-screen flake. Jira:
[WISHENKA-311](https://pypost.atlassian.net/browse/WISHENKA-311).

- `tests/test_history_screen_browser.py::test_control_opening_an_entry_moves_it_to_the_top_and_navigation_works`
  — NON-BLOCKER — pre-existing

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
- `tests/test_wish_card_giver_controls.py::test_anonymous_share_shows_availability_without_a_book_control`
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
- `tests/test_bot_capture_atomic_store_repro.py::test_bot_capture_save_uses_execute_with_connection_and_preserves_replay`
  — NON-BLOCKER — pre-existing. Jira:
  [WISHENKA-212](https://pypost.atlassian.net/browse/WISHENKA-212).

User documentation under `doc/` was left unchanged. The sentences above are
developer docs and belong to Step 8.
