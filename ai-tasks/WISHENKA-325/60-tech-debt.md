# WISHENKA-325: Technical Debt Analysis

No blockers. `RepoWishlistOps.get_history` loads the capped visit list, then
the headers with `get_wishlist_headers_by_ids` and this person's memberships
with `list_user_memberships_by_wishlist_ids`. An empty visit list skips both
batches. The cap, the stored rows, the person-facing fields, and the access
checks stay. `items` on a history row stay empty.

`tests/test_wishenka_325_history_batch_repro.py` has
`pytestmark = pytest.mark.timeout(30)`. This step did not add a marker and
did not change production code.

Reviewed: `RepoWishlistOps.get_history` (`wishenka/wishlists/repo_ops.py`),
`WishlistRepository.get_wishlist_headers_by_ids` and
`list_user_memberships_by_wishlist_ids` (`wishenka/wishlists/repository.py`),
`GET /api/history` (`wishenka/web/routes/wishlists.py`),
`tests/test_wishenka_325_history_batch_repro.py`, `20-architecture.md`,
`40-code-cleanup.md`, and `50-observability.md`.

## Shortcuts Taken

- **A non-owner who is not a member still pays one share read per row**
  (deferred). After the two batches, `get_history` calls
  `has_valid_share_access` once for each such visit. `list_view_history`
  already kept only a grant whose token matches the list. The history cap
  the route passes is 20, so the loop is at most that many indexed reads.
  The architecture kept this check and left it out of the header query.
  See follow-up 1.
- **History listing stays on the current repository transaction**
  (accepted). `GET /api/history` still runs inside the request repository
  transaction. This task does not move the read to `execute_read`.
- **Chunk size stays 500** (accepted). The new membership query uses
  `_chunked_unique_ids` and `_ID_BATCH_SIZE`. A normal open is one chunk
  because the cap is 20. A larger `limit` still chunks under SQLite's
  bind limit. The constant is the one the header batch already uses.

## Code Quality Issues

- **Developer docs still describe the list load without the two batches**
  (Low; Step 8 of this task). Product code gathers headers and this
  person's memberships together. `doc/dev/wishlists.md` still says
  `RepoWishlistOps` loads the SQL page and checks policy again, and the
  repository catalog does not name `list_user_memberships_by_wishlist_ids`.
  The `wishlist_repo_batch_read` row names `get_items_by_ids` and
  `get_wishlist_headers_by_ids` and omits the membership batch
  (`entity` `wishlist_member`). Step 8 owns `doc/dev/`. No separate ticket
  if Step 8 updates these.

The membership query copies the header batch's debug fields, including
`requested_count` as the length of the id list passed in. History ids are
already one row per wishlist. That log shape is the header contract.

## Missing Tests

- **The new module does not lock a share-only row's grant query** (Low,
  follow-up 1). `test_history_open_batches_headers_without_per_row_wishlist_load`
  locks zero `wl_items` reads, zero `FROM wl_lists WHERE id = ?`, one
  header `IN (` covering the page, the member role on the collaborative
  row, the cap, and the stored visits. Share-only inclusion and revocation
  stay on `tests/test_history_access_control.py`, which already has
  `pytestmark = pytest.mark.timeout(30)`. That file does not count
  `wl_share_access` statements.
- **The membership `IN (` shape is not asserted** (Low, no follow-up).
  The collaborative row's `resolve_context` role is `MEMBER`, which
  requires this person's `wl_members` row on the header. The architecture
  allows that membership read and does not require the test to count
  every `SELECT`. An empty visit list returns before either batch; an
  empty id list inside each batch returns `{}` and does not log. A limit
  above 500 is outside the route cap. Not a separate ticket.

## Performance Concerns

Opening history no longer loads wishes, reservations, or every member once
per row. The remaining per-row cost is `has_valid_share_access` for a
viewer who is neither owner nor member. See follow-up 1.

## Follow-up Tasks

1. **Batch the remaining share-grant reads on a history open.**
   NON-BLOCKER, priority Low. Replace the per-row `has_valid_share_access`
   loop in `RepoWishlistOps.get_history` with one chunked read of this
   person's current grants for the visit ids (token still matched to the
   list). Keep the cap, the SQL filter in `list_view_history`, and the
   `can_view_history` decision. A regression check can count one
   `wl_share_access` read for a page of share-only rows and still show
   those rows, then drop them after the token rotates.
   Jira: [WISHENKA-353](https://pypost.atlassian.net/browse/WISHENKA-353)

No other new ticket. These already have keys and are not re-filed:

- Rule-set unification stays on
  [WISHENKA-323](https://pypost.atlassian.net/browse/WISHENKA-323).
- Receipt repository wiring stays on
  [WISHENKA-324](https://pypost.atlassian.net/browse/WISHENKA-324).
- Busy-storage handling stays on
  [WISHENKA-326](https://pypost.atlassian.net/browse/WISHENKA-326).
- The shared-method set stays on
  [WISHENKA-350](https://pypost.atlassian.net/browse/WISHENKA-350).
- The missing-user history skip stays on
  [WISHENKA-351](https://pypost.atlassian.net/browse/WISHENKA-351).

Developer docs for the two batches are Step 8 of WISHENKA-325. No
separate key.

### Pre-existing test failures

This step did not re-run the suite. Nothing new was observed. The keys
below stay the filed set. They are `NON-BLOCKER — pre-existing`. This step
did not file them again.

- `tests/test_gift_receipt_migration.py::test_upgrade_is_repeatable`
  — NON-BLOCKER — pre-existing. Jira:
  [WISHENKA-232](https://pypost.atlassian.net/browse/WISHENKA-232).
- `tests/test_wish_card_giver_controls.py::test_anonymous_share_shows_availability_without_a_book_control`
  — NON-BLOCKER — pre-existing. Jira:
  [WISHENKA-235](https://pypost.atlassian.net/browse/WISHENKA-235).
- `tests/test_surprise_role_context.py::test_share_link_visit_creates_no_account`
  — NON-BLOCKER — pre-existing. Jira:
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
- `tests/test_receipt_notices_extra.py::test_cleanup_cycle_survives_a_failing_notice_purge`
  — NON-BLOCKER — pre-existing. Jira:
  [WISHENKA-245](https://pypost.atlassian.net/browse/WISHENKA-245).
- Eight archive cases in `tests/test_items_ui_error_mapping.py`
  — NON-BLOCKER — pre-existing. Jira:
  [WISHENKA-264](https://pypost.atlassian.net/browse/WISHENKA-264).
- `tests/test_preview_resource_reuse.py::test_concurrent_responses_do_not_share_cookies`
  — NON-BLOCKER — pre-existing. Jira:
  [WISHENKA-352](https://pypost.atlassian.net/browse/WISHENKA-352).

User documentation under `doc/` was left unchanged. Developer docs for the
history batches belong to Step 8.
