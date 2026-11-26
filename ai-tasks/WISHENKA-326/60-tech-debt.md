# WISHENKA-326: Technical Debt Analysis

No blockers. `get_wishlist_repository` maps a busy `SQLAlchemyError` from
`await conn.begin()` and from work after `yield` to `InventoryBusyError`
and one WARNING `wishlist_inventory_busy`. Any other `SQLAlchemyError` on
either side stays `RuntimeError` (`Wishlist storage operation failed`) and
`wishlist_store_error`. Rollback runs only when a transaction is open.
Commit logs are cleared only after the repository exists. `wishlists.execute`
re-raises only the busy case, so that mapping runs once.
`install_inventory_busy_handler` returns HTTP 503 with `detail` equal to
`str(exc)` and does not log. The shared `busy_timeout` wait was already in
place and was not changed.

`tests/test_wishenka_326_repository_busy_repro.py` has
`pytestmark = pytest.mark.timeout(30)`. This step did not add a marker.

Reviewed: `get_wishlist_repository` (`wishenka/web/dependencies.py`),
`execute` (`wishenka/web/routes/wishlists.py`),
`install_inventory_busy_handler` (`wishenka/web/app.py`), the other
`WishlistRepo` routes (`items.py`, `items_ui.py`, `receipts.py`,
`receipts_ui.py`, `sharing.py`), `tests/test_wishenka_326_repository_busy_repro.py`,
`20-architecture.md`, `40-code-cleanup.md`, and `50-observability.md`.

## Shortcuts Taken

- **The busy error is classified after the connection closes** (accepted).
  `get_wishlist_repository` remembers a busy `SQLAlchemyError` from
  `conn.begin()` or from later work, rolls back when a transaction is open,
  then logs and raises `InventoryBusyError` after the connection context
  exits. Commit logs stay untouched when `begin()` fails before the
  repository exists. That is the same flag style as today's non-busy
  `RuntimeError`. It keeps connection cleanup from becoming a second
  exception.
- **The app handler is JSON for an error that leaves the route**
  (accepted). Route `except InventoryBusyError` blocks still build their
  own HTTP 503 body when the store or domain raises that exception inside
  the route. A busy `SQLAlchemyError` on the shared repository is mapped
  only after that `try` has ended, so the app handler answers it. The
  status is 503 and the detail is the existing busy message. This task
  does not add a second sentence.
- **The unscope warning sentence is written again in the dependency**
  (accepted). The store already logs that sentence when a busy error has
  no wish id. The dependency logs the same sentence with `event` only.
  The store keeps its scoped wording. No shared helper was added.

## Code Quality Issues

None that this change introduced. `is_sqlite_busy` stays the one busy
check. `wishlists.execute` is the only web route that catches
`SQLAlchemyError`. Its busy branch re-raises that error and does not log
`wishlist_store_error`. Items, receipts, sharing, and the item and receipt
screens do not catch `SQLAlchemyError`, so a busy shared-repository error
reaches `get_wishlist_repository`.

The receipts screen still opens the shared repository through `_repo_ctx`
or, when that is unset, through `get_wishlist_repository`. Both paths now
receive this mapping. Removing the `ContextVar` stays on WISHENKA-324.

Developer docs still describe `wishlist_inventory_busy` as the store path
(`doc/dev/items.md`, `doc/dev/reservations.md`). They do not yet name the
dependency warning or the app handler. Step 8 owns `doc/dev/`. No separate
ticket if Step 8 updates these.

## Missing Tests

- **The HTTP handler is not called by the new module** (no follow-up).
  The tests drive `get_wishlist_repository` directly. They cover a busy and
  a non-busy `SQLAlchemyError` after `yield`, the same two outcomes when
  `conn.begin()` raises, and one busy error through `wishlists.execute`.
  They lock `InventoryBusyError`, the default message, the single WARNING,
  rollback when a transaction is open, cleared commit logs after the
  repository exists, and the non-busy `RuntimeError`. They do not send a
  request through `install_inventory_busy_handler`. That handler returns
  status 503 and `{"detail": str(exc)}` and does not branch. Not a separate
  ticket.
- **A non-busy error through `wishlists.execute` is not in this module**
  (no follow-up). That arm still logs `wishlist_store_error` and raises
  `RuntimeError`. The new non-busy test covers the dependency arm. The
  route arm is the behavior this task left in place.

## Performance Concerns

None. Classification is the existing `is_sqlite_busy` check on the error
that already escaped `busy_timeout`. This task does not add a wait, a
query, or a retry.

## Follow-up Tasks

No new follow-up. No other route still turns a busy shared-repository
`SQLAlchemyError` into the generic storage failure. `wishlists.execute`
was the only catch that did that, and its busy branch now re-raises.

These already have keys and are not re-filed:

- The receipts `ContextVar` `_repo_ctx` stays on
  [WISHENKA-324](https://pypost.atlassian.net/browse/WISHENKA-324).
- `UserStore.engine` callers stay on
  [WISHENKA-328](https://pypost.atlassian.net/browse/WISHENKA-328).
- `UserStore._read` `PRAGMA query_only` stays on
  [WISHENKA-342](https://pypost.atlassian.net/browse/WISHENKA-342).
- The shared Alembic runner stays on
  [WISHENKA-335](https://pypost.atlassian.net/browse/WISHENKA-335).
- Read-only single-wishlist methods stay on
  [WISHENKA-338](https://pypost.atlassian.net/browse/WISHENKA-338).
- User-scoped hydration stays on
  [WISHENKA-340](https://pypost.atlassian.net/browse/WISHENKA-340).
- The shared-method set stays on
  [WISHENKA-350](https://pypost.atlassian.net/browse/WISHENKA-350).
- The missing-user history skip stays on
  [WISHENKA-351](https://pypost.atlassian.net/browse/WISHENKA-351).
- History share-grant batching stays on
  [WISHENKA-353](https://pypost.atlassian.net/browse/WISHENKA-353).

Developer docs for the dependency warning and the app handler are Step 8
of WISHENKA-326. No separate key. User documentation under `doc/` was left
unchanged. The person-facing busy sentence already exists.

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
