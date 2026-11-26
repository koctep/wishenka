# WISHENKA-304: Technical Debt Analysis

No blockers. Equal view times follow `recorded_seq`, newest recording first.
A repeat keeps the row id and still takes the newest place. That rule is the
in-memory sort and prune, and it is the SQLite `ORDER BY` before `LIMIT`.
The one-time copy of the old id into old rows is a migration fill, not the
live tie-break. No new follow-up. The repro module already has an explicit
timeout. The full suite was not finished on this host.

Reviewed: `WishlistService.record_view` and `get_history` (`_history_rank`),
`WishlistRepository.record_view` and `list_view_history`, `WishlistStore`
load and flush, Alembic `add_view_history_recorded_seq`, and
`tests/test_wishenka_304_history_order_repro.py`.

## Source debt from WISHENKA-292

Follow-up item 2 of `ai-tasks/WISHENKA-292/60-tech-debt.md` is this task.
Jira: [WISHENKA-304](https://pypost.atlassian.net/browse/WISHENKA-304).
Done in this task. Not an open follow-up.

- **Item 2.** Addressed. Equal `viewed_at` values follow `recorded_seq`,
  newest recording first. A repeat keeps the row id and receives a new
  sequence value, so the lasting id is not freshness. The in-memory path
  sorts and prunes with `(viewed_at, recorded_seq)`. SQLite lists with
  `ORDER BY vh.viewed_at DESC, vh.recorded_seq DESC` before `LIMIT`.
- **Migration fill.** Accepted by design. `upgrade` sets
  `recorded_seq = id` where the new column is still 0, and starts
  `wl_counters.view_history_seq` at `MAX(recorded_seq)`. That fills old
  rows once. The next `record_view`, including a repeat at the same
  `viewed_at`, replaces `recorded_seq` from the counter. The live
  comparator does not read `id`.

## Shortcuts Taken

- **Old rows are numbered from `id` once** (accepted by design). Rows that
  are never recorded again keep that filled number. Their equal-time order
  is stable, and it is still not the live rule. A later recording overwrites
  it. No second backfill.
- **Two counters, one rule** (accepted by design). `WishlistService` advances
  `_next_view_history_seq`. `WishlistRepository._next_sequence` advances
  `view_history_seq` and does not call `_allocate_id`. `WishlistStore`
  loads and flushes the service counter. Listings stay per user, so another
  viewer's number does not reorder this viewer's rows.
- **`recorded_seq` stays off the HTTP history object** (accepted by design).
  Callers keep using `id` as identity. Freshness is the counter.

## Code Quality Issues

None new. History still loads with `ORDER BY id ASC`. List and prune do not
use that order. They use `(viewed_at, recorded_seq)`.

Duplicate `view_history_recorded` and `view_history_listed` lines, one in the
route and one in the service, are unchanged. They are the open log-dedup
task, tracked under
[WISHENKA-305](https://pypost.atlassian.net/browse/WISHENKA-305). This task
did not add a log line and did not create that debt.

## Missing Tests

No acceptance gap. `tests/test_wishenka_304_history_order_repro.py` already
has `pytestmark = pytest.mark.timeout(30)`. This step did not add a marker
and did not change the test. The module freezes the view time and checks
newest recording first for a repeat that keeps its row, on the session list
and on the stored list, including which equal-time rows stay inside the
existing limit of 20. A later view time still ranks first.

There is no separate upgrade test that the one-time fill copies `id`. That
fill is not the live tie-break. The repro locks the live rule. Not a
follow-up.

## Performance Concerns

None. The shown list stays at 20. The history index is
`(user_id, viewed_at DESC, recorded_seq DESC)`, the same key as the query
that applies `LIMIT`.

Targeted history tests passed. The repro module was 5 passed. A related set
of 35 passed before cleanup. The full suite was not finished on this host.
Its wall-clock cost is not caused by this change.

## Follow-up Tasks

No new follow-up. Follow-up count: 0.

[WISHENKA-305](https://pypost.atlassian.net/browse/WISHENKA-305) stays open.
It is the separate log-dedup task. It is not debt created by this task.
No new ticket.

### Pre-existing test failures

The full suite was not finished. The failures below are the already-filed
set. They are `NON-BLOCKER — pre-existing`. This step did not re-run them
and did not file them again. Node ids are the ones already recorded for
these keys.

History-screen flake. Jira:
[WISHENKA-311](https://pypost.atlassian.net/browse/WISHENKA-311).

- `tests/test_history_screen_browser.py::`
  `test_control_opening_an_entry_moves_it_to_the_top_and_navigation_works`
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
- `tests/test_wish_card_giver_controls.py::`
  `test_anonymous_share_shows_availability_without_a_book_control`
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

User documentation under `doc/` was left unchanged. Developer docs that still
describe a `viewed_at`-only order belong to Step 8.
