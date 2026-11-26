# WISHENKA-338: Technical Debt Analysis

No blockers. One-wishlist openings use `read_transaction`: plain `BEGIN`
plus `PRAGMA query_only`. That covers the seven service names, the
pure-read HTTP handlers, and the session lookup when the app holds a
`WishlistStore`. Saves, and any request that still goes through
`get_wishlist_repository`, still use `BEGIN IMMEDIATE`. `UserStore._read`
was not changed. It still sets `read_only` and does not set `query_only`.

`tests/test_wishenka_338_read_openings_repro.py` has
`pytestmark = pytest.mark.timeout(30)` at module scope. That mark covers
every test in the file. This step did not add a marker.

Reviewed: `read_transaction`, `run_repository_read`, and `execute_read`
(`wishenka/wishlists/store.py`), `_READ_REPOSITORY_METHODS` and
`_read_repository_forward` (`wishenka/wishlists/service.py`),
`RepoWishlistOps.is_favorite` (`wishenka/wishlists/repo_ops.py`),
`get_wishlist_read_repository` (`wishenka/web/dependencies.py`),
`_is_session_active` (`wishenka/auth/dependencies.py`), `UserStore._read`
(`wishenka/users/store.py`), the pure-read handlers in `wishlists.py`,
`items.py`, `items_ui.py`, `sharing.py`, `receipts.py`, and
`receipts_ui.py`, `tests/test_wishenka_338_read_openings_repro.py`,
`20-architecture.md`, `40-code-cleanup.md`, and `50-observability.md`.

## Shortcuts Taken

- **A second dependency, not a flag on the shared one** (accepted).
  `get_wishlist_read_repository` yields a repository inside
  `read_transaction`. It does not commit, flush logs, or map a non-busy
  database error. `get_wishlist_repository` is unchanged: `conn.begin()`
  with no `read_only` option, then commit and `wishlist_inventory_busy`
  when the lock outlasts the wait. A save that also loads the wishlist
  stays on that path.
- **Two service forwarders** (accepted). `_read_repository_forward` matches
  `_repository_forward` and calls `run_repository_read`. With no store,
  `is_favorite` still runs the in-memory body. The other six still fail
  closed. A configured store does not enter `execute` or `_write()`.
- **Session lookup uses the same read transaction** (accepted). When
  `app.state.wishlist_store` is a `WishlistStore`, `_is_session_active`
  opens `read_transaction` before the handler runs. A pure-read GET would
  still take the save lock if the session check began immediate. A bare
  engine that is not a `WishlistStore` keeps the previous `read_only`
  `begin()` and rollback. Production uses `WishlistStore`.

## Code Quality Issues

None that need a follow-up. The read and write forwarders stay separate
because they open different transactions. `is_favorite` is the only name
that still has an in-memory body. Settings and ownership transfer stay on
`execute`. `UserStore._read` is a different helper and was not copied.

Public-link and invite handlers still take `WishlistRepo`. The
requirements left those openings on the save lock. This change did not
move them. The favorites list, history, recording a view, the deleted
list, and `list_wishlists` also stay on `get_wishlist_repository`. The
receipts `_execute` fallback still calls `get_wishlist_repository` when
no repository was injected.

## Missing Tests

The repro covers the behavior this change owns.

- The seven `WishlistService` openings return the committed snapshot
  within 2 seconds while another connection holds `BEGIN IMMEDIATE`. A
  missing wishlist, a deleted wishlist, a missing wish, a refused member
  list, a refused gifted list, and a signed-out favorite stay the same
  refusals. After rollback, the title is the original title.
- The pure-read API GETs (one wishlist, including `is_favorite`, the wish
  list, members, one wish, and gifted wishes) match the unlocked status
  and body within 2 seconds per request. Those requests authenticate, so
  the session lookup is on that path.
- `update_wishlist_settings` still does not finish within 2 seconds while
  that lock is held.

HTML detail, modals, member and wish partials, and the three receipt
dialogs use `WishlistReadRepo` and are not separate cases in this module.
They open the same dependency the API GETs already hold under the lock.
No follow-up.

`query_only` rejecting a write is the existing `execute_read` lifecycle.
`execute_read` now delegates to `read_transaction`. This module does not
repeat that write rejection. No follow-up.

## Performance Concerns

None. These openings no longer take the reserved lock, so a save does not
wait behind a lookup. Each save that still uses `BEGIN IMMEDIATE` waits
once inside the listener's `busy_timeout` (5000 ms). This task does not
add a wait, a retry, or a second query on the opening itself. The session
check sets `query_only` on the connection that check already opens.

## Follow-up Tasks

No new follow-up. The seven openings, the pure-read GETs, and the session
lookup on `WishlistStore` leave the save lock free. Writes and mixed
requests still take it, which is the boundary this task shipped.

These already have keys and are not re-filed:

- The receipts `ContextVar` `_repo_ctx` and its fallback to
  `get_wishlist_repository` stay on
  [WISHENKA-324](https://pypost.atlassian.net/browse/WISHENKA-324).
- The shared Alembic runner stays on
  [WISHENKA-335](https://pypost.atlassian.net/browse/WISHENKA-335).
- User-scoped hydration for history, favorites, deleted wishlists, and
  recording a view stays on
  [WISHENKA-340](https://pypost.atlassian.net/browse/WISHENKA-340).
- `UserStore._read` stays on
  [WISHENKA-342](https://pypost.atlassian.net/browse/WISHENKA-342).
  This task did not add `PRAGMA query_only` or a busy outcome on that
  helper, and it did not file that gap again.
- The shared-method set stays on
  [WISHENKA-350](https://pypost.atlassian.net/browse/WISHENKA-350).
- The missing-user history skip stays on
  [WISHENKA-351](https://pypost.atlassian.net/browse/WISHENKA-351).
- Concurrent preview cookies stay on
  [WISHENKA-352](https://pypost.atlassian.net/browse/WISHENKA-352).
- History share-grant batching stays on
  [WISHENKA-353](https://pypost.atlassian.net/browse/WISHENKA-353).

Unchanged-row writes on settings and ownership transfer stay on
[WISHENKA-339](https://pypost.atlassian.net/browse/WISHENKA-339). The busy
mapping on `get_wishlist_repository` stays on
[WISHENKA-326](https://pypost.atlassian.net/browse/WISHENKA-326). This step
did not file either again.

Developer docs for the read dependency are Step 8 of WISHENKA-338. No
separate key. User documentation under `doc/` was left unchanged. These
openings did not add a person-facing sentence.

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
