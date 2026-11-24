# WISHENKA-121: Technical Debt Analysis

## Shortcuts Taken

1. **Direct `UserStore.engine` callers bypass `UserStore._read` and `UserStore._immediate`**:
   - `wishenka/web/dependencies.py` (`async with store.engine.connect() as conn:`), `wishenka/bot/birthdays.py` (`async with store.engine.connect() as conn:`), and `wishenka/web/routes/profile.py` (`_find_active_chat_id` fallback to `user_store.engine`) call `engine.connect()` without `execution_options(read_only=True)`. Because `configure_immediate_transactions` is attached to `UserStore.engine.sync_engine`, SQLAlchemy 2.0 autobegin on `connect()` emits `BEGIN IMMEDIATE` for these read-only queries, unnecessarily taking a `RESERVED` write lock.
   - `wishenka/bot/entry.py` and `wishenka/bot/principal.py` call `users.engine.begin()` directly instead of going through `UserStore._immediate()`, so `SQLITE_BUSY` in those paths still surfaces as raw `OperationalError` rather than `UserStoreBusyError`.
2. **Hardcoded 5000ms SQLite busy timeout**:
   - `UserStore.__init__` hardcodes `connect_args={"timeout": 5}` and `configure_immediate_transactions(self.engine.sync_engine)` (default `busy_timeout_ms=5000`), and `UserStore.initialize` hardcodes `PRAGMA busy_timeout=5000`. There is no constructor or `Settings` override (which also forces `tests/test_user_store_concurrency_repro.py` to wait ~5s per busy-lock test case).
3. **`UserStore(..., engine=...)` assumes caller-configured transactions**:
   - When `engine` is passed explicitly to `UserStore.__init__`, `configure_immediate_transactions` is not called on it, assuming the caller already attached the listeners.
4. **`UserStore._read` does not map `SQLITE_BUSY`**:
   - Unlike `_immediate`, `UserStore._read` does not wrap `SQLAlchemyError` / `is_sqlite_busy`, so a read-side busy error (if one occurs under extreme contention) surfaces as raw `SQLAlchemyError` rather than `UserStoreBusyError`.

## Code Quality Issues

1. **Duplicated busy/error mapping in `UserStore`**:
   - `UserStore.initialize()` (lines 184–197) and `UserStore._immediate()` (lines 144–159) duplicate the `is_sqlite_busy(exc)` -> `user_store_busy` warning -> `UserStoreBusyError` and `user_store_error` error -> `RuntimeError` handling block. Extracting a small helper `_handle_storage_error(exc, operation=...)` would remove the duplication.
2. **Duplicated HTTP 503 `UserStoreBusyError` handling in `wishenka/web/routes/profile.py`**:
   - `update_profile_locale` and `update_profile_birthdate` duplicate the `except UserStoreBusyError` -> structured warning log -> `HTTPException(503)` block (and `auth_telegram` in `wishenka/web/routes/auth.py` has the same pattern). A shared FastAPI exception handler or route helper could centralize `UserStoreBusyError` -> HTTP 503 mapping.
3. **Unserialized `_ensure_initialized` check**:
   - `UserStore._ensure_initialized` checks `if not self._initialized:` without an `asyncio.Lock`. Concurrent cold-start requests can both enter `initialize()` before `_initialized` flips to `True` (safe and idempotent via `BEGIN IMMEDIATE` and `IF NOT EXISTS`, but redundant).

## Missing Tests

All tests in `tests/test_user_store_concurrency_repro.py` have explicit timeout markers (`pytestmark = pytest.mark.timeout(60)`), so there are no `do-testing` blockers. Remaining coverage gaps:

1. **`UserStore.initialize()` busy-lock path**: `tests/test_user_store_concurrency_repro.py` covers `user_store_error` during `initialize()`, but not `is_sqlite_busy` -> `UserStoreBusyError` during `initialize()` WAL/pragma setup.
2. **`UserStore(..., engine=...)` injection path**: Constructing `UserStore` with a shared `AsyncEngine` is not exercised by tests.
3. **Profile `clear_birthdate` and fallback `upsert_user` 503 paths**: `test_user_store_busy_maps_to_http_503` tests `UserStore.set_birthdate` raising `UserStoreBusyError`, but not `clear=True` (`UserStore.clear_birthdate`) or the fallback `UserStore.upsert_user` branch in `PATCH /api/profile/birthdate`.
4. **Bot callers of `UserStore`**: `wishenka/bot/i18n.py` and `wishenka/bot/principal.py` calling `upsert_from_bot` / `users.engine.begin()` under `UserStoreBusyError` are not covered by concurrency tests.

## Performance Concerns

1. **Read-only queries on `UserStore.engine` taking `BEGIN IMMEDIATE`**:
   - Callers using `user_store.engine.connect()` without `execution_options(read_only=True)` (`wishenka/web/dependencies.py`, `wishenka/bot/birthdays.py`, `wishenka/web/routes/profile.py` `_find_active_chat_id` fallback) acquire `RESERVED` write locks for `SELECT` queries, increasing write-lock contention.
2. **Slow busy-timeout tests**:
   - Hardcoded 5000ms `busy_timeout` causes the 5 busy-lock assertions in `tests/test_user_store_concurrency_repro.py` to take ~25s of wall-clock sleep time. Exposing `busy_timeout_ms` on `UserStore` would speed up the test suite significantly.

## Follow-up Tasks

1. **Migrate direct `UserStore.engine` callers to `read_only=True` / `UserStore` methods**:
   - Update `wishenka/web/dependencies.py`, `wishenka/bot/birthdays.py`, and `wishenka/web/routes/profile.py` (`_find_active_chat_id`) to use `execution_options(read_only=True)` (or a public `UserStore.execute_read` helper) so read queries do not emit `BEGIN IMMEDIATE`.
   - Route `wishenka/bot/entry.py` and `wishenka/bot/principal.py` `users.engine.begin()` blocks through `UserStore` write helpers so `SQLITE_BUSY` maps to `UserStoreBusyError` consistently.
   - Jira: [WISHENKA-328](https://pypost.atlassian.net/browse/WISHENKA-328)
2. **Make `busy_timeout_ms` configurable on `UserStore` and extract shared error-mapping helpers**:
   - Add `busy_timeout_ms: int = 5000` to `UserStore.__init__`, extract `_handle_storage_error` in `wishenka/users/store.py`, and consider a centralized FastAPI exception handler for `UserStoreBusyError` -> HTTP 503.
   - Jira: [WISHENKA-329](https://pypost.atlassian.net/browse/WISHENKA-329)
3. **Expand concurrency test coverage**:
   - Add tests for `UserStore.initialize()` `UserStoreBusyError`, `UserStore(..., engine=...)`, and `PATCH /api/profile/birthdate` (`clear=True`) HTTP 503 mapping.
   - Jira: [WISHENKA-330](https://pypost.atlassian.net/browse/WISHENKA-330)
