# WISHENKA-218: Technical Debt Analysis

## Shortcuts Taken

- **Legacy tests rewritten, not extended.** To align with FR-5 / Q12, assertions in
  `tests/test_wish_items_tma_ui.py`, `tests/test_wish_items_crud_api.py`,
  `tests/test_gift_receipt_service.py`, `tests/test_shared_inventory_multiprocess.py`,
  `tests/test_item_observability.py`, `tests/test_reservations_surprise_invariant.py` and
  `tests/test_currency_defaults.py` were changed from the old "occupied-units floor" behaviour to the
  new `max(1, received_quantity)` floor. The old floor semantics are no longer covered (intentional per
  Q12), and no explicit regression test pins "no `reserved_quantity` / `locked_quantity` in logs/HTML"
  beyond the new repro and `caplog` checks.
- **Service-layer log/error identifiers kept.** The structured event `item_quantity_reduction_rejected`
  and the i18n key `web.item.quantity_below_reserved` keep their old names even though they now refer to
  received quantity. Only the copy changed. Renaming would break dashboards and the catalog sync, so it
  was deferred.
- **Send-time authorization via raw SQL.** `_event_authorized` in `wishenka/notices/reminders.py` got
  another hand-written SQL branch for `item_quantity_overbooked`, consistent with the neighbouring
  branches but one more copy of the "open promise and not recipient and list visible" predicate.
- **`_record_shared_event` early return.** An empty recipient set now returns without queuing an
  event. This is a behaviour change for all event kinds, not only the new one. It is believed safe
  because an event with no recipients produced no notices.

## Code Quality Issues

- `WishlistService.update_wish_item` is now longer (floor check, overbooked detection, giver
  exclusion, logging). It should be split into helpers (e.g. `_collect_overbooked_givers`).
- The authorization predicate in `reminders.py` is duplicated across the `receipt_*` and
  `item_quantity_overbooked` branches and could be shared.
- The over-booked condition (`received + SUM(active/purchased) > quantity`) is expressed both in
  Python (service) and SQL (reminders), so the two can drift.

## Missing Tests

- **`service_notice_skipped` reason `unauthorized` is untested.** Only the `ineligible` reason is
  covered (see `50-observability.md`).
- **Send-time re-verification of `item_quantity_overbooked` is not directly tested.** The repro and
  `tests/test_item_observability.py` verify queuing and outbox rows, but there is no test where the
  over-booked state is cleared before delivery. Missing cases: the giver cancelled, the quantity was
  raised again, the giver became a recipient, or the list was deleted. In each, the notice should be
  dropped by `_event_authorized`.
- No test checks the rendered RU/EN `notices.item_quantity_overbooked` text through the reminder
  worker end to end. Only catalog sync (`test_i18n_sync.py`) covers the keys.
- No multi-giver test checks that one giver's over-booked notice contains no other giver's data. The
  template takes only `wish` and `wishlist`, so the risk is low.
- The repro checks `item_updated` exclusion for an editing co-author who is also a giver; the
  non-editing co-author case is not directly tested.
- All new and modified tests carry explicit `pytest.mark.timeout` markers, so there is no timeout debt.

## Performance Concerns

- The send-time SQL for over-booked notices runs a correlated `SUM` subquery over `wl_reservations`
  per outbox row. Row counts per item are small and the query is indexed by `wish_item_id`, so this is
  negligible. A mass edit that notifies many givers adds one outbox row per giver.
- `_record_shared_event` now iterates reservations for every item edit, as it did before. No new cost.

## Deviations from Architecture

- None known. Items still deferred from the architecture: the product copy for the over-booked notice
  was written by the developer and has not been reviewed by product, so the EN/RU wording is a
  **provisional i18n copy**. In RU, "Требуемое количество … уменьшилось" does not say who changed it
  (by design, for privacy).

## Follow-up Tasks

New follow-ups:

- [ ] **Add tests for send-time re-verification of `item_quantity_overbooked` and the
  `unauthorized` skip reason** — Priority: Medium.
  Jira: [WISHENKA-260](https://pypost.atlassian.net/browse/WISHENKA-260).
- [ ] **Add end-to-end reminder-worker test for the over-booked notice (EN/RU rendering,
  `item_updated` exclusion for co-author-givers, multi-giver privacy)** — Priority: Low.
  Jira: [WISHENKA-261](https://pypost.atlassian.net/browse/WISHENKA-261).
- [ ] **Refactor `update_wish_item` over-booking logic and de-duplicate the over-booked and
  authorization predicates between service and `reminders.py`** — Priority: Low.
  Jira: [WISHENKA-262](https://pypost.atlassian.net/browse/WISHENKA-262).
- [ ] **Product review of the `notices.item_quantity_overbooked` and updated
  `web.item.quantity_below_reserved` EN/RU copy; optionally rename the legacy
  `quantity_below_reserved` key / `item_quantity_reduction_rejected` event** — Priority: Low.
  Jira: [WISHENKA-263](https://pypost.atlassian.net/browse/WISHENKA-263).

Pre-existing failures (NON-BLOCKER): all 17 failures below were reproduced at base commit
`e433223` in an isolated worktree during WISHENKA-218. The issue links track each failure or its
matching root cause; none is caused by this task.

- Archive response mapping, [WISHENKA-264](https://pypost.atlassian.net/browse/WISHENKA-264):

  ```text
  tests/test_items_ui_error_mapping.py::test_archived_wishlist_gives_409[archive-confirm]
  tests/test_items_ui_error_mapping.py::test_archived_wishlist_gives_409[archive]
  tests/test_items_ui_error_mapping.py::test_unknown_wishlist_gives_404[archive-confirm]
  tests/test_items_ui_error_mapping.py::test_unknown_wishlist_gives_404[archive]
  tests/test_items_ui_error_mapping.py::test_non_member_gives_404[archive-confirm]
  tests/test_items_ui_error_mapping.py::test_non_member_gives_404[archive]
  tests/test_items_ui_error_mapping.py::test_unknown_item_gives_404[archive-confirm]
  tests/test_items_ui_error_mapping.py::test_unknown_item_gives_404[archive]
  ```

- Stale giver card, [WISHENKA-265](https://pypost.atlassian.net/browse/WISHENKA-265):
  `tests/test_receipt_modal_browser.py::test_stale_giver_card_is_neutral`.
- Dark theme contrast, [WISHENKA-266](https://pypost.atlassian.net/browse/WISHENKA-266):
  `tests/test_receipt_theme_browser.py::test_receipt_text_has_readable_contrast[dark]`.
- HTMX move and CSRF, [WISHENKA-267](https://pypost.atlassian.net/browse/WISHENKA-267):
  `tests/test_wishlist_htmx_smoke_browser.py::test_real_htmx_move_button_with_cookie_and_csrf`.
- Shared-view observability, [WISHENKA-226](https://pypost.atlassian.net/browse/WISHENKA-226):
  `tests/test_wishlists_htmx_observability.py::test_wishlist_shared_view_observability`.
- Anonymous public projection, [WISHENKA-235](https://pypost.atlassian.net/browse/WISHENKA-235):

  ```text
  tests/test_surprise_role_context.py::test_share_link_visit_creates_no_account
  tests/test_wish_card_giver_controls.py::test_anonymous_share_shows_availability_without_a_book_control
  ```

- Receipt migration, [WISHENKA-232](https://pypost.atlassian.net/browse/WISHENKA-232):
  `tests/test_gift_receipt_migration.py::test_upgrade_is_repeatable`.
- Unmarked browser error, [WISHENKA-220](https://pypost.atlassian.net/browse/WISHENKA-220):
  `tests/test_receipt_modal_browser.py::test_unmarked_error_neither_shows_notice_nor_reloads`.
- Notice cleanup, [WISHENKA-245](https://pypost.atlassian.net/browse/WISHENKA-245):
  `tests/test_receipt_notices_extra.py::test_cleanup_cycle_survives_a_failing_notice_purge`
  (`TypeError` vs `RuntimeError`, `wishenka/wishlists/cleanup.py`).
