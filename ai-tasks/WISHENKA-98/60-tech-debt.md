# WISHENKA-98: Technical Debt Analysis

## Shortcuts Taken

- Fractional prices now pass from preview through quick-add, SQLite persistence, and gifter
  display. The pre-existing integer SQLite column stores non-integer numeric values as REAL;
  legacy integer amounts remain unchanged. This resolves the previously identified blocker.
- A lone `¥` and a single separator with three trailing digits are ambiguous without locale
  metadata. The deterministic CNY and thousands-grouping defaults are documented architectural
  choices, not facts that can be inferred reliably from every merchant page.

## Code Quality Issues

Currency aliases, store names, and supported implicit URL suffixes are static lists in
`wishenka/items/parser.py` and `wishenka/items/classifier.py`. They must be maintained when support
expands; no additional refactor is required to satisfy the present scope.

## Missing Tests

The new international currency module and the changed item observability module have explicit
10-second pytest timeout markers. The offline fixtures cover the agreed currencies and structured
metadata, but cannot guarantee compatibility with changing live retailer markup.

## Performance Concerns

The parser retains bounded JSON-LD traversal and an offer recursion depth limit. The cost of
JSON-LD traversal is already tracked in
[WISHENKA-116](https://pypost.atlassian.net/browse/WISHENKA-116). No new benchmark or performance
claim was established in this step.

## Follow-up Tasks

The full suite had 1465 passed, 17 failed, and 2 skipped. All 17 failing cases reproduced on
base commit `7ef1b53` in an isolated worktree. They are **NON-BLOCKER — pre-existing** and are
tracked by the existing issues below; the baseline output is `/tmp/wishenka-baseline-98.log`.

- [WISHENKA-264](https://pypost.atlassian.net/browse/WISHENKA-264):
  `tests/test_items_ui_error_mapping.py` cases below:
  - `test_archived_wishlist_gives_409[archive-confirm]`
  - `test_archived_wishlist_gives_409[archive]`
  - `test_unknown_wishlist_gives_404[archive-confirm]`
  - `test_unknown_wishlist_gives_404[archive]`
  - `test_non_member_gives_404[archive-confirm]`
  - `test_non_member_gives_404[archive]`
  - `test_unknown_item_gives_404[archive-confirm]`
  - `test_unknown_item_gives_404[archive]`
- [WISHENKA-235](https://pypost.atlassian.net/browse/WISHENKA-235):
  `tests/test_wish_card_giver_controls.py::`
  `test_anonymous_share_shows_availability_without_a_book_control`, and the same missing
  availability text in `tests/test_surprise_role_context.py::`
  `test_share_link_visit_creates_no_account`.
- [WISHENKA-245](https://pypost.atlassian.net/browse/WISHENKA-245):
  `tests/test_receipt_notices_extra.py::test_cleanup_cycle_survives_a_failing_notice_purge`.
- [WISHENKA-226](https://pypost.atlassian.net/browse/WISHENKA-226):
  `tests/test_wishlists_htmx_observability.py::test_wishlist_shared_view_observability`.
- [WISHENKA-265](https://pypost.atlassian.net/browse/WISHENKA-265):
  `tests/test_receipt_modal_browser.py::test_stale_giver_card_is_neutral`.
- [WISHENKA-220](https://pypost.atlassian.net/browse/WISHENKA-220):
  `tests/test_receipt_modal_browser.py::test_unmarked_error_neither_shows_notice_nor_reloads`.
- [WISHENKA-232](https://pypost.atlassian.net/browse/WISHENKA-232):
  `tests/test_gift_receipt_migration.py::test_upgrade_is_repeatable`.
- [WISHENKA-266](https://pypost.atlassian.net/browse/WISHENKA-266):
  `tests/test_receipt_theme_browser.py::test_receipt_text_has_readable_contrast[dark]`.
- [WISHENKA-267](https://pypost.atlassian.net/browse/WISHENKA-267):
  `tests/test_wishlist_htmx_smoke_browser.py::test_real_htmx_move_button_with_cookie_and_csrf`.

- [WISHENKA-283](https://pypost.atlassian.net/browse/WISHENKA-283): three intermittent
  `tests/test_i18n_unit.py` failures in the final full run, which timed out before tracebacks.
  Two targeted reruns passed both at base `7ef1b53` and in the task tree. **NON-BLOCKER — flaky**.
