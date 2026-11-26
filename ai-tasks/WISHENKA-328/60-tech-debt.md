# WISHENKA-328: Technical Debt Analysis

No blockers. Birthday listing and the active-chat lookup open with
`execution_options(read_only=True)` and `begin()`, so the existing listener
emits plain `BEGIN`. `UserStore.write` only forwards to `_immediate`. The
private-chat save and the reservation-confirmation save use that forwarder.
A leftover lock is `UserStoreBusyError` and one WARNING `user_store_busy`.
There is no second begin and no second retry. `wishenka/web/dependencies.py`
is unchanged. `UserStore._read` is unchanged.

`tests/test_wishenka_328_read_lock_and_bot_busy_repro.py` has
`pytestmark = pytest.mark.timeout(30)`. This step did not add a marker.

Reviewed: `listing` (`wishenka/bot/birthdays.py`), `_find_active_chat_id`
(`wishenka/web/routes/profile.py`), `UserStore.write` and `_immediate`
(`wishenka/users/store.py`), `ensure_private_bot_user`
(`wishenka/bot/principal.py`), `reservation_confirmations`
(`wishenka/bot/entry.py`), `wishenka/web/dependencies.py`,
`tests/test_wishenka_328_read_lock_and_bot_busy_repro.py`,
`20-architecture.md`, `40-code-cleanup.md`, and `50-observability.md`.

## Shortcuts Taken

- **The read-only shape is copied at the two call sites** (accepted).
  `listing` and `_find_active_chat_id` each open their existing engine with
  `read_only`, `begin()`, and `rollback` in `finally`. The birthday list
  always uses the wishlist engine. The chat lookup uses that engine when a
  wishlist store is on the app, and the user engine otherwise. A public
  `UserStore` read method would use the other pool. No shared helper was
  added.
- **`write` is a forwarder** (accepted). It returns
  `await self._immediate(work, operation=operation)`. Rollback, the busy
  warning, and `UserStoreBusyError` stay inside `_immediate`. The bot does
  not copy that `except`.

## Code Quality Issues

None that this change introduced. Production code has no remaining
`users.engine.begin()`. The two bot saves that opened it now call
`users.write`:

- `ensure_private_bot_user` with `operation="record_private_chat"`.
- `reservation_confirmations` with `operation="reservation_confirmations"`.

Other bot SQL stays on `WishlistStore.transaction` (birthday changes,
capture, support). Those writes are wishlist-store work. They are not a
`UserStore` bypass. `dependencies.py` still opens the shared wishlist
repository with `conn.begin()` and no `read_only` option. That request
reads and changes wishlist data. WISHENKA-326 already maps a remaining
lock there.

## Missing Tests

The new module covers the four paths this task changed: the birthday list
read, the chat lookup on both engines, a locked private-chat save, and a
locked confirmation save. Each read asserts one plain `BEGIN` and no
`BEGIN IMMEDIATE`. Each busy save asserts `UserStoreBusyError` with the
existing message and an unchanged row. No scenario from this change is
left without a test. No follow-up.

## Performance Concerns

None. The reads no longer take the writer lock. Each save still waits once
inside the listener's `busy_timeout` (5000 ms). This task does not add a
wait, a query, or a retry.

## Follow-up Tasks

No new follow-up. No other `users.engine.begin()` still takes a write lock
on a read, and no bot write of a person save still bypasses `UserStore`.

These already have keys and are not re-filed:

- The receipts `ContextVar` `_repo_ctx` stays on
  [WISHENKA-324](https://pypost.atlassian.net/browse/WISHENKA-324).
- The shared Alembic runner stays on
  [WISHENKA-335](https://pypost.atlassian.net/browse/WISHENKA-335).
- Read-only single-wishlist methods stay on
  [WISHENKA-338](https://pypost.atlassian.net/browse/WISHENKA-338).
- User-scoped hydration stays on
  [WISHENKA-340](https://pypost.atlassian.net/browse/WISHENKA-340).
- `UserStore._read` stays on
  [WISHENKA-342](https://pypost.atlassian.net/browse/WISHENKA-342).
  This task did not add `PRAGMA query_only` or a busy outcome on that
  helper, and it did not file that gap again.
- The shared-method set stays on
  [WISHENKA-350](https://pypost.atlassian.net/browse/WISHENKA-350).
- The missing-user history skip stays on
  [WISHENKA-351](https://pypost.atlassian.net/browse/WISHENKA-351).
- History share-grant batching stays on
  [WISHENKA-353](https://pypost.atlassian.net/browse/WISHENKA-353).

Developer docs for these paths are Step 8 of WISHENKA-328. No separate key.
User documentation under `doc/` was left unchanged. The person-facing busy
sentence already exists.

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
