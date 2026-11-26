# WISHENKA-320: Technical Debt Analysis

No blockers. Create and edit share one name rule: required, 1 to 255 code
points after the Python edge-space trim, invisible-only is missing, and a
longer name is `wishlist_name_too_long`. The Mini App submits the normalized
string and maps that `422` type to the too-long catalog string.
`bindFieldErrors` is the field-error helper both forms use. Description and
event title stay uncapped on purpose. Every new or changed pytest module
that collects tests has an explicit `pytest.mark.timeout`. The touched
modules passed 216 tests. The full suite was not started.

Reviewed: `wishenka/wishlists/name_contract.py`,
`wishenka/web/routes/wishlists.py` (`WishlistCreateInput`, `WishlistInput`,
`update_wishlist`), `wishenka/web/static/miniapp.js` (`wishlistNameDecision`,
`optionalDetail`, `bindFieldErrors`, `showCreate`, `settingsForm`), the
name-contract tests, and the create-validation, create-form, and home
overview edits. `tests/conftest.py` only gained `database_path` and collects
no tests, so it has no timeout marker.

## Source debt from WISHENKA-296

Follow-up item 1 of `ai-tasks/WISHENKA-296/60-tech-debt.md` is this task.
Jira: [WISHENKA-320](https://pypost.atlassian.net/browse/WISHENKA-320).

- **S-2.** Addressed for the name. PATCH uses the same 1-255 rule as
  create. Invisible-only names are `wishlist_name_required` on both.
  Part (b), a ceiling for description and event title, is a future product
  choice below, not an open defect.
- **S-4.** Addressed by the product rule. Empty stored names stay readable
  under the untitled label. Nothing migrates or deletes them. The next save
  must send a real name.
- **C-1.** Addressed. `nameErrorFromDetail` reads `detail[].type`.
  `wishlist_name_too_long` uses the too-long string.
- **T-1.** Addressed. Create UI and browser tests map a too-long `422` to
  the too-long catalog string and keep the typed name.
- **T-2.** Addressed. `tests/test_wishlist_name_contract_api.py` and the
  replaced PATCH case in `tests/test_wishlist_create_validation_api.py`
  lock the shared rule.
- **C-3.** Addressed. `bindFieldErrors` is shared by `showCreate` and
  `settingsForm`. The two forms still build their own fields.
- **Follow-up 1.** Addressed for the name contract, the too-long message,
  invisible-only names, and existing blank titles. The "agreed maxima"
  clause was not chosen. See the product choice below.

## Shortcuts Taken

- **Domain writes still accept any title** (accepted). `WishlistService.create_wishlist`
  still defaults `title=""`, and `update_wishlist_settings` still assigns
  the title it is given. The HTTP models and the omitted-name check in
  `update_wishlist` are the gate, so fixtures and legacy rows stay
  constructible. The Mini App and a direct `POST` or `PATCH` cannot bypass
  that gate. No migration and no `CHECK`. This is the architecture, not a
  leftover hole in the app.
- **The Mini App repeats the rule in JavaScript** (accepted). The static
  script cannot import `name_contract.py`. `stripEdgeSpaces` and
  `PYTHON_SPACES` copy `str.isspace()`, and `U+FEFF` stays a mark. Create
  and settings submit `decision.name` with no second `trim()`.
- **The home overview seeds an empty title in SQLite** (test only).
  `tests/test_home_overview_browser.py` updates `wl_lists.title` after a
  normal create. `PATCH` can no longer clear a name. `BrowserServer.database_path`
  exists so that seed can see the file.

## Code Quality Issues

- **The edge-space table is handwritten** (Low). `PYTHON_SPACES` in
  `miniapp.js` is a fixed set of code points. Python `str.isspace()` is the
  server rule. Nothing asserts the set still matches that predicate. The
  characters this task called out (`U+FEFF` kept, `U+200B` not a space) are
  tested. A later Unicode change could split create from edit without a
  failing test. See follow-up 1.
- **Settings UI harness is a string splice** (Low).
  `tests/test_wishlist_settings_name_contract_ui.py` inserts `settings_flow`
  into the create harness by replacing one anchor. A create-harness edit
  fails that assert. The splice avoids a second copy of the Node DOM.
- **`bindFieldErrors` still clears text before `removeChild`** (Low,
  already filed). `clear` sets `err.textContent = ''` and then
  `wraps[name].removeChild?.(err)`. That is the old `clearFieldError`
  leftover from WISHENKA-296 C-2. The call site moved into `bindFieldErrors`.
  It stays on [WISHENKA-321](https://pypost.atlassian.net/browse/WISHENKA-321).
  No new ticket.
- **Create still calls a private CDP method** (Low, already filed).
  `tests/test_wishlist_create_form_browser.py` still uses
  `page._send("Accessibility.getFullAXTree")`. The settings name-contract
  browser module does not. Scope stays on
  [WISHENKA-319](https://pypost.atlassian.net/browse/WISHENKA-319).

## Missing Tests

- **No parity check of `PYTHON_SPACES` against `str.isspace()`** (Low, goes
  with the handwritten table). Behavioral tests lock `U+FEFF`, the five
  invisible marks, ordinary spaces, and code-point length. They do not walk
  the space set.
- **No browser test that a stored invisible-only name stays off the untitled
  label** (Low, not a follow-up). Requirement 8 says those rows are not
  rewritten and do not gain the untitled fallback. Display is the existing
  `list.name || t('miniapp.common.untitled_wishlist')`. Only `""` is empty,
  and the empty-name tests lock that label. An invisible-only string cannot
  take that branch.

An administrator is not given a separate name test. `WishlistInput` does not
branch on role. `require_member(..., manager=True)` is unchanged.

## Performance Concerns

None. Each check walks one short string. No new query, poll, or request.
The name-contract modules passed 216 tests. The full suite was not started.
Its wall-clock cost on this host is already known and is not caused by this
change.

## Future product choice

Description and event title have no character ceiling. Create and edit both
accept a value longer than the name, and blank or spaces-only means unset.
`normalize_optional_detail` has no maximum. Neither input has `maxlength`.
That is the acceptance this task was required to keep. It is not a broken
acceptance criterion and not code debt. A later product decision can add one
ceiling in the optional-text helper and on both forms together.

## Follow-up Tasks

1. **Lock the Mini App edge-space set to Python `str.isspace()`.**
   NON-BLOCKER (both sides already agree on the marks and on `U+FEFF`),
   priority Low. One test can build a string from the JavaScript set and
   from `str.isspace()` over the same code-point range. Jira:
   [WISHENKA-349](https://pypost.atlassian.net/browse/WISHENKA-349).

No other new ticket.

- Idempotent create stays on
  [WISHENKA-322](https://pypost.atlassian.net/browse/WISHENKA-322) (WISHENKA-296
  S-3). This task did not add an idempotency key.
- Catalog-helper cleanup and the history wait stay on
  [WISHENKA-321](https://pypost.atlassian.net/browse/WISHENKA-321). The field
  clear now lives in `bindFieldErrors`.
- Chromium-only coverage of the new settings browser module stays with the
  creation form on
  [WISHENKA-313](https://pypost.atlassian.net/browse/WISHENKA-313).
- The private accessibility call stays on
  [WISHENKA-319](https://pypost.atlassian.net/browse/WISHENKA-319).

Considered and dropped: a database length check (it would reject a legacy
empty row); moving the rule into `WishlistService` (fixtures and older rows
must still load); a dedicated `422` log or metric (the completed-request
INFO line is the record, and the name is absent); re-filing WISHENKA-296
S-3, C-2, T-3, or T-4.

### Pre-existing test failures

The full suite was not started. The touched modules passed 216 tests. The
failures below are the already-filed set. They are
`NON-BLOCKER — pre-existing`. This step did not re-run them and did not
file them again. Node ids are the ones already recorded for these keys.

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

User documentation under `doc/` was left unchanged. Developer docs for this
contract belong to Step 8.
