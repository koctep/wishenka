# WISHENKA-182: Technical Debt Analysis

## Shortcuts Taken

1. **`WishlistStore.execute_read` relies on SQLAlchemy `read_only=True` option without SQLite `PRAGMA query_only` or `_retry` (`wishenka/wishlists/store.py`, lines 81–89, 1649–1658):**
   - `WishlistStore.execute_read` sets `execution_options(read_only=True)` so `_sqlite_begin_immediate` issues a deferred `BEGIN` instead of `BEGIN IMMEDIATE`, and always rolls back in `finally`.
   - It does not enforce `PRAGMA query_only = ON` at the SQLite connection level (relying on caller discipline and `rollback()`), and does not wrap execution in `self._retry(...)` for `SQLITE_BUSY` like `_immediate` does.
2. **Two-step `UserStore` + `bot_destinations` persistence in `ensure_private_bot_user` (`wishenka/bot/principal.py`, lines 40–52):**
   - `ensure_private_bot_user` calls `users.get_by_telegram_id(user.id)` (and `users.upsert_from_bot(user)` when missing) followed by a separate `async with users.engine.begin() as conn:` transaction for `upsert_bot_destination`. This preserves existing `UserStore` abstractions without adding a combined store method, at the cost of 2–3 sequential DB roundtrips on the same SQLite engine.
3. **Unchanged rate-limit read/write split in `_submit_support_message` (`wishenka/bot/support.py`, lines 310–346):**
   - Rate-limit checking (`support_tickets`) runs in `store.execute_read(_prepare_read)` before network delivery to Telegram, while `support_tickets` insertion happens later in `store.transaction(_record_sent)`. This preserves the pre-existing non-atomic window for concurrent rapid submissions from the same user (necessary because Telegram API calls cannot run inside `BEGIN IMMEDIATE`).

## Code Quality Issues

1. **Duplicated clock-normalization helpers (`wishenka/bot/principal.py`, `wishenka/bot/birthdays.py`, `wishenka/bot/support.py`, `wishenka/bot/capture.py`):**
   - `_resolve_effective_now` in `wishenka/bot/principal.py` (lines 16–24) and `_now_epoch` in `wishenka/bot/birthdays.py` (lines 25–31) both normalize `dependencies.clock()` from `datetime | int` to Unix epoch seconds.
   - `support.py` and `capture.py` each retain their own `_now(deps)` helper.
2. **Loose typing on `dependencies` and `user` in `ensure_private_bot_user` (`wishenka/bot/principal.py`, lines 27–34):**
   - `dependencies: Any` and `user: Any` match the existing loose signatures in `birthdays.py`, `capture.py`, and `support.py`, rather than using a narrow `Protocol` (such as `EntryDependencies` in `wishenka/bot/entry.py`).

## Missing Tests

All tests in `tests/test_wishenka_182_repro.py` have explicit timeout markers (`pytestmark = pytest.mark.timeout(30)` at line 24). No `do-testing` timeout blockers exist.

Remaining test coverage gaps:
1. **Direct unit tests for `WishlistStore.execute_read` (`wishenka/wishlists/store.py`):**
   - Currently tested only indirectly via `_submit_support_message` in `tests/test_wishenka_182_repro.py`.
   - Missing dedicated unit tests verifying rollback on normal return/exception and verifying that `execute_read` does not contend with a concurrent `BEGIN IMMEDIATE` transaction in WAL mode.
2. **Direct edge-case unit tests for `ensure_private_bot_user` (`wishenka/bot/principal.py`):**
   - Missing direct unit tests for: `user=None`, `user_store=None`, group-chat guard (`chat_id != user.id`) returning `None` without DB writes, pre-injected `user_record` skipping `get_by_telegram_id`/`upsert_from_bot`, and explicit `now` / `dependencies.clock()` (`datetime` vs `int`) normalization.

## Performance Concerns

1. **Multiple sequential `SELECT` statements in `collect_diagnostic_context` (`wishenka/bot/support.py`, lines 117–196):**
   - `collect_diagnostic_context` executes 9 separate `SELECT` statements sequentially on `conn` (including separate queries for active vs. archived `wl_lists` counts and separate queries for owned vs. collaborative `wl_lists`/`wl_tokens`). All queries are indexed and user-scoped, so latency is negligible on local SQLite, though several could be combined if needed.

## Follow-up Tasks

No **Blocker** or **High** severity technical debt items were found.

1. **[Medium] Add dedicated unit tests for `WishlistStore.execute_read` and `ensure_private_bot_user` edge cases** — [WISHENKA-253](https://pypost.atlassian.net/browse/WISHENKA-253)
   - Cover `execute_read` rollback-on-exit/exception and non-blocking WAL concurrency against `BEGIN IMMEDIATE`, plus `ensure_private_bot_user` guard/clock/pre-resolved `user_record` branches.
2. **[Low] Harden `WishlistStore.execute_read` with `PRAGMA query_only` or explicit read-only guard & retry policy** — [WISHENKA-254](https://pypost.atlassian.net/browse/WISHENKA-254)
   - Evaluate enforcing `PRAGMA query_only = ON` (reset on connection return) and/or `SQLITE_BUSY` retry handling in `WishlistStore.execute_read` (`wishenka/wishlists/store.py`).
3. **[Low] Consolidate duplicate clock helpers (`_now_epoch`, `_resolve_effective_now`, `_now`) and narrow `PrincipalDependencies` protocol** — [WISHENKA-255](https://pypost.atlassian.net/browse/WISHENKA-255)
   - Unify `dependencies.clock()` epoch normalization across `wishenka/bot/principal.py` and `wishenka/bot/birthdays.py`, and replace `Any` with a `Protocol` for `ensure_private_bot_user` dependencies.
4. **[Low] Consolidate user-scoped queries in `collect_diagnostic_context`** — [WISHENKA-256](https://pypost.atlassian.net/browse/WISHENKA-256)
   - Optionally combine active/archived wishlist count queries (`GROUP BY status`) and owned/collaborative token lookups (`UNION`) in `wishenka/bot/support.py` to reduce per-ticket query roundtrips.
