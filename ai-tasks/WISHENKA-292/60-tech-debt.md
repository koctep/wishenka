# WISHENKA-292: Technical Debt Analysis

No blockers were found. Every acceptance criterion in `10-requirements.md` is covered by the
implementation and by passing tests. The items below are non-blocking follow-ups. Each one is
either pre-existing behavior that the requirements explicitly keep unchanged, or a test and
maintenance weakness that does not affect the acceptance criteria.

## Shortcuts Taken

No temporary production workaround was identified. The history screen uses the existing
endpoints (`GET /api/history`, `POST /api/history/{id}`, `DELETE /api/history`) without contract
changes. Clear confirmation is client-side and inline, as designed in `20-architecture.md`.
Per-entry removal, search and filtering were not added: `10-requirements.md` (scope section)
excludes them, so their absence is not debt.

## Code Quality Issues

### Recording a view has no access check (NON-BLOCKER, high)

`POST /api/history/{id}` (`record_view` in `wishenka/web/routes/wishlists.py`) rejects only
missing or deleted wishlists. `WishlistService.record_view` and `get_history` apply no
membership or favorite check. Any authenticated user can therefore record a view of any
non-deleted list id they cannot open. `GET /api/history` then returns that list's `name`,
`description`, `event_title` and `event_date` to them. Wishlist ids are sequential integers,
so titles can be enumerated.

Blocker decision for this task: NON-BLOCKER. Reasons:

- It is pre-existing behavior of the API, recorded at Step 2 (`20-architecture.md`).
- Requirement 10 says access checks are unchanged by this task, so closing the gap would
  break the stated scope. The acceptance criteria on privacy (no reservation or surprise data
  in entries) are met: entries carry no reservation data, and the browser test checks this.
- The redesigned screen shows titles more prominently, but the same data was already shown by
  the previous history screen and returned by the same API, so exposure did not grow.

"Pre-existing" does not mean low risk. This is a genuine disclosure bypass: any user can POST a
guessable sequential wishlist id and read `name`, `description`, `event_title` and `event_date`
back via `GET /api/history`. It is not caused by this redesign, which changed no API contract
and no rendered fields (the JS does not render `description`). It therefore keeps high priority.

`WishlistAccessPolicy.can_view_wishlist` (`wishenka/wishlists/policy.py`) is not a usable fix:
it only returns `wishlist.status != DELETED`, which the route and service already check, so
calling it would close nothing. `GET /api/wishlists/{id}` enforces access with
`require_member`, i.e. `WishlistAccessPolicy.resolve_context(user, wl).is_member`, and answers
404 otherwise. The client records a view (`showList` in `miniapp.js`) right before that call.
The `/share/{public_token}` route (`view_public_share`) does not call `record_view`, so a
share-link visitor who is not a member gets no history entry from the visit today.

Verified in code and tests: non-member favoriting and recording are currently DESIGNED
behavior, not only a gap. `POST /api/favorites/{id}` (`add_favorite` in
`wishenka/web/routes/wishlists.py` and `WishlistService.add_favorite`) checks only that the
list exists, is not deleted and is not the caller's own list. `tests/test_wishlist_sections_ui.py`
has a non-member (Bob) favoriting Alice's list (200, `role == "favorite"`) and a non-member
viewer recording history for 25 lists. The `projection` and `list_favorites` code has a
"favorite" role for non-members, and `tests/test_home_overview_ui.py` renders favorite-role
cards. Only the detail-screen favorite button is member-only (it loads through
`GET /api/wishlists/{id}`, 404 for non-members); the API and the home UI model non-member
favorites. `WishlistAccessPolicy.resolve_context(...).is_member` is true for the owner, for
admins and for members, so an `is_member` gate does not lock out owners. A `has_favorite`
gate would be unsound: any user could favorite a guessable id first and pass it.

Suggested follow-up for history: decide the access model first (see below), then enforce it
in `record_view` and `get_history`.

The risk is real and needs a product/security decision on the intended access model before
any code change. Two options:

- (a) Gate recording and favoriting on `is_member` (404 as for `GET /api/wishlists/{id}`).
  The "favorite" role then becomes unreachable except through a share-token flow. Existing
  tests that seed non-members must be rewritten to use members or the share-token path.
  Tests that break under an API-level gate (verified by reading them):
  - `tests/test_wishlist_sections_ui.py`: Bob favoriting, the 25-list viewer,
    `test_surprise_invariant_in_favorites_and_history_projections` and
    `test_home_sections_api_and_role_badge_precedence`.
  - `tests/test_wishlist_sections_observability.py`: viewer 202 and the gifter are never
    members of owner 101's list, so `test_favorites_lifecycle_observability`,
    `test_view_history_lifecycle_observability` and
    `test_redaction_zero_leak_in_observability` break.
    `test_warning_on_self_favoriting_and_deleted_wishlists` breaks only if the gate runs
    before the deleted-list check, since its deleted-list steps are denied first.
  - `tests/test_i18n_sync.py` (~line 434): the giver POSTs `/api/favorites/{id}` on the
    owner's list and expects 200.
  - `tests/test_home_overview_browser.py` (lines ~159-165, ~713-714): the owner favorites
    the viewer's pure-favorite list and other lists; the seeding at 159-165 is the real
    favorite-role case.
  - `tests/test_history_screen_browser.py`:
    `test_control_clear_scope_api_contract_and_payload_shape` makes the owner favorite and
    record the viewer's list, so the owner acts as a non-member. The other history screen
    tests seed each user's own lists (owners are members) and would still pass.
  Tests that break only if the gate lives in the service (direct service calls by
  non-members): the `test_domain_service_*` tests (user 2002),
  `tests/test_wishenka_34_preferences.py::test_preferences_store_validation_roles_and_isolation`,
  `tests/test_notice_wishlist_events.py::test_favorite_tracking_reminder_respects_current_favorite`
  and `tests/test_wishenka_75_user_fk_cascade.py::test_rejects_wishlist_user_links_for_nonexistent_user`
  (a ghost user expects a storage RuntimeError, a service gate would raise not-found first).
  `tests/test_home_overview_ui.py` only uses JS fetch stubs, never the real API, so it does
  not break; its favorite-role fixtures are mock-only and would only need updating to match.
- (b) Require a share-token or visit proof recorded server-side in `view_public_share`
  (`/share/{public_token}`, the only way a non-member legitimately reaches a list; it records
  nothing today) and accept `POST` favorites and history only with that proof. This keeps the
  "favorite" role reachable but needs new server-side state and a client change.

The decision must precede implementation. Whichever option is chosen, add API tests for a
stranger recording or favoriting a private list (404, nothing stored), for a member still
working, and for revoked access.

Cleanup of already-leaked data is part of the follow-up: filtering in `get_history` and
`list_favorites` only hides rows, it does not purge existing rows from `_view_history` and
`_favorites`. The follow-up must either purge or migrate them (drop entries whose user has no
access under the chosen model) or record an explicit decision to leave them. A member whose
access is later revoked is covered only by the read-time filter in `get_history` and
`list_favorites`; this is acceptable and is stated here on purpose.

### Favorites accept any non-deleted wishlist id (NON-BLOCKER, high)

`add_favorite` accepts any existing, non-deleted wishlist id that is not the caller's own,
without a membership or share-token check. `GET /api/favorites` (`list_favorites`) then
returns `name`, `description`, `event_title` and `event_date` of every favorited list, even
when the caller is not a member. Ids are sequential, so this is the same enumeration bypass as
the history finding, through a second, older endpoint. As shown above, non-member favoriting
is currently designed behavior (tests and the "favorite" role), so closing it is an access
model change, not a bug fix. This task does not touch favorites, so it is pre-existing and
NON-BLOCKER, but it keeps high priority and is a prerequisite for the history fix to mean
anything, because closing only history leaves the same data readable through favorites.

Suggested follow-up: after the product/security decision between options (a) and (b) above,
apply the same rule in `add_favorite` and skip inaccessible lists in `list_favorites`. The
same test impact and the same purge-or-migrate step for already stored `_favorites` rows
apply.

### Unstable order for equal `viewed_at` (NON-BLOCKER, low)

`WishlistService.get_history` sorts by `viewed_at` only (`reverse=True`), and the trimming in
`record_view` sorts by `viewed_at` alone as well. Entries with equal timestamps rely on list
order, which is an accident of the in-memory list rather than a contract. Step 3 also saw one
unexplained misorder in about 1 of 13 runs. It could not be reproduced in 280 further rounds,
so the cause is unknown. It may be equal or close timestamps in the test seeding, and it may
be a test-side race; no production defect is proven.

Suggested follow-up: add the entry `id` as a secondary key (newest first) in both sorts, add a
unit test with equal timestamps, and keep a note to re-check the flake if it shows up again.

### Double logging in route and service (NON-BLOCKER, low)

The route and the service both log `view_history_recorded`, `view_history_listed` (and
both also contain a `favorite_deleted_wishlist_denied` branch for a deleted list, with a name
that no longer fits the history flow). The route checks first and raises, so the service-level
denial log is unreachable through the route and only one denial record is emitted. The
"two records per request" claim holds for `view_history_recorded` and `view_history_listed`
only: those come from different loggers with the same event name, which inflates counts in log
queries. This task already removed the duplicate
`view_history_cleared` and left the rest (see `50-observability.md`).

Suggested follow-up: keep one event per request (service-level), rename the denial event to a
history-specific name, and update `tests/test_wishlist_sections_observability.py`, which
currently expects the existing events.

## Missing Tests

### Fragility of `tests/test_history_screen_browser.py` (NON-BLOCKER, low)

The module has an explicit `pytest.mark.timeout(45)`, so there is no timeout-marker blocker.
Known weaknesses:

- It imports the private helpers `_open_home` and `_set_user_locale` from
  `tests/test_home_overview_browser.py`. Renaming them there breaks this module silently.
- The deleted-list control writes `wl_lists.status` directly with `sqlite3`, which couples the
  test to the table layout instead of using a public API.
- The absolute-time check only matches a four-digit year (`\b20\d\d\b`). It does not check the
  day or month format or the locale wording of the date.
- Relative time is tested only for ages of 5 minutes and 3 days. Boundaries (under a minute,
  hours, one day, 6 and 7 days, future timestamps from clock skew) are not pinned.

Suggested follow-up: move the shared helpers to `tests/browser_helpers.py`, delete the list
through the API, assert the full RU and EN absolute date, and parametrize relative time over
its boundaries.

## Performance Concerns

None. The list is capped at 20 entries. `get_history` filters and sorts all entries in memory
on each call, which is acceptable at current scale and unchanged by this task.

## Follow-up Tasks

Follow-ups were filed in Jira after the blocker review (SAFE TO CLOSE).

1. **Decide and enforce the access model for recording and listing viewing history
   (`is_member` or share-token proof; purge or migrate leaked rows).** NON-BLOCKER,
   pre-existing, priority High. Jira: [WISHENKA-303](https://pypost.atlassian.net/browse/WISHENKA-303)
2. **Add a deterministic tie-breaker to history ordering and re-check the Step 3 misorder.**
   NON-BLOCKER, priority Low. Jira: [WISHENKA-304](https://pypost.atlassian.net/browse/WISHENKA-304)
3. **Remove duplicate route/service logging of history events.** NON-BLOCKER, priority Low.
   Jira: [WISHENKA-305](https://pypost.atlassian.net/browse/WISHENKA-305)
4. **Harden `tests/test_history_screen_browser.py` (shared helpers, API deletion, date and
   relative-time boundaries).** NON-BLOCKER, priority Low. Jira: [WISHENKA-306](https://pypost.atlassian.net/browse/WISHENKA-306)
5. **Decide and enforce the access model for favorites and `GET /api/favorites`
   (`is_member` or share-token proof; purge or migrate leaked rows).**
   NON-BLOCKER, pre-existing, priority High. Jira: [WISHENKA-302](https://pypost.atlassian.net/browse/WISHENKA-302)

### Pre-existing test failures

The full `make test` run showed 16 failures that reproduce on the base commit cc77dc0
(repro: `make test`, clean tree). Each is **NON-BLOCKER — pre-existing**, not caused by this
task, and already tracked in Jira, so no duplicate issues are needed here.

- NON-BLOCKER — pre-existing, WISHENKA-264, in `tests/test_items_ui_error_mapping.py`, each
  with params `[archive]` and `[archive-confirm]`:
  - `::test_archived_wishlist_gives_409`
  - `::test_unknown_wishlist_gives_404`
  - `::test_non_member_gives_404`
  - `::test_unknown_item_gives_404`
- Note: unwrappable pytest node ids are the only lines allowed to exceed 100 characters.
- NON-BLOCKER — pre-existing, WISHENKA-235:
  `tests/test_wish_card_giver_controls.py::test_anonymous_share_shows_availability_without_a_book_control`
- NON-BLOCKER — pre-existing, WISHENKA-245:
  `tests/test_receipt_notices_extra.py::test_cleanup_cycle_survives_a_failing_notice_purge`
- NON-BLOCKER — pre-existing, WISHENKA-265:
  `tests/test_receipt_modal_browser.py::test_stale_giver_card_is_neutral`
- NON-BLOCKER — pre-existing, WISHENKA-220:
  `tests/test_receipt_modal_browser.py::test_unmarked_error_neither_shows_notice_nor_reloads`
- NON-BLOCKER — pre-existing, WISHENKA-232:
  `tests/test_gift_receipt_migration.py::test_upgrade_is_repeatable`
- NON-BLOCKER — pre-existing, WISHENKA-267:
  `tests/test_wishlist_htmx_smoke_browser.py::test_real_htmx_move_button_with_cookie_and_csrf`
- NON-BLOCKER — pre-existing, WISHENKA-298:
  - `tests/test_surprise_role_context.py::test_share_link_visit_creates_no_account`
  - `tests/test_wishlists_htmx_observability.py::test_wishlist_shared_view_observability`
