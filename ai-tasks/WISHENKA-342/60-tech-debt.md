# WISHENKA-342: Technical Debt Analysis

No blockers. `UserStore._read` sets `PRAGMA query_only = ON` before the
lookup, rolls back, then sets `PRAGMA query_only = OFF` through
`AUTOCOMMIT`. A failed reset logs `user_store_query_only_reset_failed`
and invalidates the connection, keeping an error the lookup already
raised. A busy `SQLAlchemyError` logs `user_store_busy` and raises
`UserStoreBusyError`. Any other storage error stays that error.

This closes TD-1 in `ai-tasks/WISHENKA-254/60-tech-debt.md`. That item is
not re-filed.

The repro timeout is present. In
`tests/test_wishenka_342_user_read_hardening_repro.py`,
`pytestmark = pytest.mark.timeout(30)` is at module scope and covers every
test in the file. There is no `do-testing` blocker.

Reviewed: `UserStore._read`, `get_by_telegram_id`, and `get_by_id`
(`wishenka/users/store.py`), `WishlistStore.read_transaction`
(`wishenka/wishlists/store.py`), `is_sqlite_busy`
(`wishenka/sqlite.py`), `listing` (`wishenka/bot/birthdays.py`),
`_find_active_chat_id` (`wishenka/web/routes/profile.py`),
`tests/test_wishenka_342_user_read_hardening_repro.py`,
`20-architecture.md`, `40-code-cleanup.md`, and `50-observability.md`.

## Shortcuts Taken

- **The wishlist read finally is copied** (accepted). `_read` follows
  `read_transaction`: plain `BEGIN`, `query_only` on, busy mapping, rollback,
  then `query_only` off in `AUTOCOMMIT`, and invalidate when that reset
  raises. The architecture kept the two helpers apart. Wishlist busy still
  raises `InventoryBusyError`. A person lookup raises `UserStoreBusyError`.
- **Busy is a synthetic driver error** (accepted). The locked-lookup test
  raises `OperationalError` with `sqlite3.OperationalError("database is locked")`
  from the person `SELECT`. A second connection holding `BEGIN IMMEDIATE`
  does not make a WAL lookup busy. The existing non-blocking lookup test
  stays the proof that these lookups still finish under that lock.
- **Reset failure is forced on `engine.connect`** (accepted). The two reset
  tests wrap the raw connection so `isolation_level="AUTOCOMMIT"` raises.
  One case is a successful read. The other raises from the work callback.
  Both assert `invalidate()` and `user_store_query_only_reset_failed`.

## Code Quality Issues

None that need a follow-up.

The busy warning in `_read` is the same warning `_immediate` and
`initialize` already emit, with `operation` set to the lookup name.
WISHENKA-329 already tracks extracting that shared mapping. This copy
stays inside `_read` so the write path is untouched.

`UserStoreBusyError`'s class sentence still says a write transaction.
Reads now raise that same class and the same message. Callers and the
message are unchanged. Developer wording for the lookup belongs in Step 8.

The repro module sentence still describes the old `_read`. The tests
assert the shipped sequence, the readonly refusal, the busy outcome, the
reset failure, the kept work error, the quiet success, and the non-busy
storage error.

## Missing Tests

No blocker. The module mark above covers these cases:

- `get_by_telegram_id` and `get_by_id` emit `query_only` on, the person
  `SELECT`, `AUTOCOMMIT`, then `query_only` off.
- An `UPDATE` inside `_read` raises `OperationalError` matching `readonly`,
  and the seeded name is still the seeded name.
- A locked lookup raises `UserStoreBusyError` with the existing message and
  one `user_store_busy` warning whose `operation` is the lookup name. No
  `user_store_error` line.
- A failed reset after a successful read is the raised error, with one
  warning and `invalidate()`.
- A failed reset after a failed read still invalidates, and the work error
  remains the one raised.
- A successful lookup adds no `wishenka.users` log.
- A disk I/O `OperationalError` stays that error, with no `user_store_error`.

## Performance Concerns

None. Each lookup adds two `PRAGMA query_only` statements on the connection
it already opens. The listener's `busy_timeout` (5000 ms) stays the only
wait. This task does not add a second wait or a second attempt.

## Follow-up Tasks

No new follow-up. The person lookup refuses a change, hands the connection
back with `query_only` off or discards it when that reset fails, and reports
a busy database as `UserStoreBusyError`.

Closed here, and not re-filed:

- WISHENKA-254 TD-1, harden `UserStore._read` with `PRAGMA query_only` and
  `UserStoreBusyError`, is this task:
  [WISHENKA-342](https://pypost.atlassian.net/browse/WISHENKA-342).

Already filed, and left in place:

- Birthday listing and the private-chat lookup stay on
  [WISHENKA-328](https://pypost.atlassian.net/browse/WISHENKA-328).
  They still open with `read_only` and `begin()` and do not set
  `query_only` or map busy. This task did not change them.
- Wishlist reads stay on
  [WISHENKA-338](https://pypost.atlassian.net/browse/WISHENKA-338).
  `read_transaction` was not edited.
- The dual-exception test for the wishlist read stays on
  [WISHENKA-343](https://pypost.atlassian.net/browse/WISHENKA-343).
  The person-lookup pair of reset tests already covers that case for
  `_read`.
- Extracting the shared busy mapping, and a central HTTP 503 handler for
  `UserStoreBusyError`, stay on
  [WISHENKA-329](https://pypost.atlassian.net/browse/WISHENKA-329).

Developer docs for this lookup are Step 8. `doc/dev/users.md` still
describes `_read` as `read_only` plus rollback only. No separate key.
User documentation under `doc/` was left unchanged. This task did not add
a person-facing sentence. The temporary-unavailable message is the one
person saves already use.

### Pre-existing test failures

This step did not re-run the suite and observed no new failure. Nothing
here is filed as `NON-BLOCKER — pre-existing`.
