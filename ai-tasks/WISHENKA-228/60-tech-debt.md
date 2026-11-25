# WISHENKA-228: Technical Debt Analysis

## Shortcuts Taken

No shortcut was added. `match_public_link_route` in
`wishenka/web/rate_limit.py` now admits `HEAD` with `GET` for
`/share/{token}` and `/invite/{token}`. The method is not rewritten to
`GET`, so an in-budget probe still reaches the router as `HEAD`. On
FastAPI 0.165.0 that response is `405` with `Allow: GET` for both a real
secret and an unknown one. The requirements allow an in-budget check to
show the same validity outcome as a page open, and they do not require
this service to start showing it. A later FastAPI release that serves
`HEAD` by running the `GET` handler would make an in-budget probe
informative. An over-limit probe would still be the existing token-free
`429`, because the middleware refuses before `call_next`.

The WISHENKA-88 note that `HEAD` bypassed the limiter is closed by this
predicate. Process-local buckets, the inline HTML `429`, leftmost
`X-Forwarded-For`, and the unthrottled `/api/public/wishlists/{token}*`
routes stay as they were. They remain on
[WISHENKA-229](https://pypost.atlassian.net/browse/WISHENKA-229).

No user-facing document names these methods, so none was edited. The
protected-route list in `doc/dev/wishlists.md` still shows `GET` only.
That developer-doc update belongs to Step 8.

## Code Quality Issues

None in the change. The admission rule is one condition,
`upper_method in {"GET", "HEAD"}`, on the existing two-segment branch.
`POST /invite/{token}/join` is unchanged. `resolve_client_ip`,
`SlidingWindowRateLimiter`, and `_build_rate_limit_response` were not
edited. The method set is the policy, not a new limit or timeout.

Every test in `tests/test_public_link_rate_limit.py` carries an explicit
timeout through the module marker `pytestmark = pytest.mark.timeout(30)`
(22 tests, including the parametrized unknown-visitor case). There is no
`do-testing` timeout-marker blocker.

## Missing Tests

The Step 3 cases are in `tests/test_public_link_rate_limit.py`: shared
`HEAD`/`GET` allowance for share and invite, unknown share secrets, the
over-limit `429` contract, in-budget opens and join, trusted `X-Real-IP`,
and the shared `"unknown"` allowance through the middleware.

Two edges stay unasserted and do not need a new issue:

- `test_rate_limit_logs_structured_event_without_token_leakage` locks
  `public_link_rate_limited` for `GET` and `POST`. It does not send
  `HEAD`. The denial logger writes `request.method` for every matched
  route, and Step 6 checked a refused `HEAD` by hand (`method=HEAD`,
  route template, no token). The event is `WARNING`, so the error-path
  `caplog` contract does not add a required block.
- `HEAD /invite/{token}/join` is unmatched because that path has three
  segments and the method is not `POST`. No test names that negative.
  The length check is the same one that already rejects extra segments.

## Performance Concerns

None from this change. A matched `HEAD` uses the existing per-visitor
bucket and does not add a setting, a second window, or a lookup before
the limit decision. The full-bucket scan in `_evict_expired` and the
single-process counter are unchanged and already tracked with the
WISHENKA-88 store limits.

## Follow-up Tasks

No new follow-up. Nothing below was introduced by counting `HEAD`, and
none of it blocks closing WISHENKA-228.

### Pre-existing test failures (`NON-BLOCKER — pre-existing`)

`make test` on this tree, recorded in
`ai-tasks/WISHENKA-228/40-code-cleanup.md`: 2480 passed, 2 skipped,
26 failed. None of the failures are in
`tests/test_public_link_rate_limit.py`.

History-screen flake. Failed in the parallel run and passed on an
immediate serial re-run. Jira: [WISHENKA-311](https://pypost.atlassian.net/browse/WISHENKA-311).

- `tests/test_history_screen_browser.py::test_control_opening_an_entry_moves_it_to_the_top_and_navigation_works`
  — `NON-BLOCKER — pre-existing`

Share-page and public-view cluster. Fails at base `7e7b7f1` with
`sqlite3.IntegrityError: FOREIGN KEY constraint failed` and HTTP 500.
Jira: [WISHENKA-348](https://pypost.atlassian.net/browse/WISHENKA-348).

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

The other 17 failures are the set already recorded on WISHENKA-303.
Same node ids, already filed:

- `tests/test_items_ui_error_mapping.py::test_archived_wishlist_gives_409[archive-confirm]`
  — `NON-BLOCKER — pre-existing` (Jira: `WISHENKA-264`)
- `tests/test_items_ui_error_mapping.py::test_archived_wishlist_gives_409[archive]`
  — `NON-BLOCKER — pre-existing` (Jira: `WISHENKA-264`)
- `tests/test_items_ui_error_mapping.py::test_unknown_wishlist_gives_404[archive-confirm]`
  — `NON-BLOCKER — pre-existing` (Jira: `WISHENKA-264`)
- `tests/test_items_ui_error_mapping.py::test_unknown_wishlist_gives_404[archive]`
  — `NON-BLOCKER — pre-existing` (Jira: `WISHENKA-264`)
- `tests/test_items_ui_error_mapping.py::test_non_member_gives_404[archive-confirm]`
  — `NON-BLOCKER — pre-existing` (Jira: `WISHENKA-264`)
- `tests/test_items_ui_error_mapping.py::test_non_member_gives_404[archive]`
  — `NON-BLOCKER — pre-existing` (Jira: `WISHENKA-264`)
- `tests/test_items_ui_error_mapping.py::test_unknown_item_gives_404[archive-confirm]`
  — `NON-BLOCKER — pre-existing` (Jira: `WISHENKA-264`)
- `tests/test_items_ui_error_mapping.py::test_unknown_item_gives_404[archive]`
  — `NON-BLOCKER — pre-existing` (Jira: `WISHENKA-264`)
- `tests/test_receipt_modal_browser.py::test_stale_giver_card_is_neutral`
  — `NON-BLOCKER — pre-existing` (Jira: `WISHENKA-265`)
- `tests/test_receipt_modal_browser.py::test_unmarked_error_neither_shows_notice_nor_reloads`
  — `NON-BLOCKER — pre-existing` (Jira: `WISHENKA-220`)
- `tests/test_wish_card_giver_controls.py::test_anonymous_share_shows_availability_without_a_book_control`
  — `NON-BLOCKER — pre-existing` (Jira: `WISHENKA-235`)
- `tests/test_receipt_notices_extra.py::test_cleanup_cycle_survives_a_failing_notice_purge`
  — `NON-BLOCKER — pre-existing` (Jira: `WISHENKA-245`)
- `tests/test_gift_receipt_migration.py::test_upgrade_is_repeatable`
  — `NON-BLOCKER — pre-existing` (Jira: `WISHENKA-232`)
- `tests/test_surprise_role_context.py::test_share_link_visit_creates_no_account`
  — `NON-BLOCKER — pre-existing` (Jira: `WISHENKA-298`)
- `tests/test_wishlist_htmx_smoke_browser.py::test_real_htmx_move_button_with_cookie_and_csrf`
  — `NON-BLOCKER — pre-existing` (Jira: `WISHENKA-267`)
- `tests/test_preview_resource_reuse.py::test_concurrent_responses_do_not_share_cookies`
  — `NON-BLOCKER — pre-existing` (Jira: `WISHENKA-212`)
- `tests/test_bot_capture_atomic_store_repro.py::test_bot_capture_save_uses_execute_with_connection_and_preserves_replay`
  — `NON-BLOCKER — pre-existing` (Jira: `WISHENKA-212`)
