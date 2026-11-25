# WISHENKA-254: Technical Debt Analysis

## Shortcuts Taken

- **Simulated `SQLITE_BUSY` in unit test**: `test_execute_read_maps_sqlite_busy_to_inventory_busy_error` ([test_wishenka_254_execute_read_hardening_repro.py](file:///home/src/tests/test_wishenka_254_execute_read_hardening_repro.py#L128-L161)) raises a synthetic `OperationalError("SELECT 1", {}, sqlite3.OperationalError("database is locked"))` inside `work` instead of holding a real cross-connection `BEGIN EXCLUSIVE` lock for `busy_timeout=5000`. This is an intentional test-speed/determinism trade-off.
- **Monkeypatched `engine.connect` for reset-failure test**: `test_execute_read_logs_warning_and_invalidates_on_query_only_reset_failure` ([test_wishenka_254_execute_read_hardening_repro.py](file:///home/src/tests/test_wishenka_254_execute_read_hardening_repro.py#L165-L227)) wraps `engine.connect` with `_WrappedRawConn` to deterministically fail `execution_options(isolation_level="AUTOCOMMIT")`.
- No production shortcuts or temporary workarounds were introduced in `WishlistStore.execute_read` ([store.py](file:///home/src/wishenka/wishlists/store.py#L1739-L1772)).

## Code Quality Issues

- **Asymmetry with `UserStore._read` (out of scope)**: `UserStore._read` ([users/store.py](file:///home/src/wishenka/users/store.py#L125-L134)) still relies on `execution_options(read_only=True)` + `conn.rollback()` without `PRAGMA query_only = ON/OFF` enforcement or `is_sqlite_busy` -> `UserStoreBusyError` mapping.
- **Timeout markers**: All tests in both `tests/test_wishenka_254_execute_read_hardening_repro.py` (`pytest.mark.timeout(30)`) and `tests/test_wishlists_sqlite_repo.py` (`pytest.mark.timeout(10)`) have explicit module-level timeout markers (`pytestmark`).

## Missing Tests

- **Dual-exception `finally` path**: `WishlistStore.execute_read` ([store.py](file:///home/src/wishenka/wishlists/store.py#L1756-L1772)) guards `if not has_active_exc: raise` so a `PRAGMA query_only = OFF` reset failure does not mask an active exception from `work(conn)`. While the single-failure reset path is tested, the simultaneous `work` exception + `query_only` reset failure case is not explicitly exercised by a unit test.

## Performance Concerns

- **Per-call `PRAGMA` overhead**: `execute_read` issues two extra `PRAGMA` statements per call (`PRAGMA query_only = ON` and `PRAGMA query_only = OFF` in `AUTOCOMMIT`). On local SQLite WAL connections this is negligible and avoids maintaining a separate read-only `AsyncEngine`/pool.
- **No cascading retry delay**: Relying on `PRAGMA busy_timeout = 5000` without a Python retry loop avoids multiplying read latency on `SQLITE_BUSY`.

## Follow-up Tasks

| Priority | Type | Summary | Details | Jira |
|---|---|---|---|---|
| Low | NON-BLOCKER | Harden `UserStore._read` with `PRAGMA query_only` and `UserStoreBusyError` mapping | Mirror `WishlistStore.execute_read` in `wishenka/users/store.py:125-134` so user-store reads also reject writes at the SQLite engine level and map `SQLITE_BUSY` consistently. | [WISHENKA-342](https://pypost.atlassian.net/browse/WISHENKA-342) |
| Low | NON-BLOCKER | Test dual-exception preservation in `WishlistStore.execute_read` | Add a unit test in `tests/test_wishenka_254_execute_read_hardening_repro.py` verifying that when `work(conn)` raises and `PRAGMA query_only = OFF` also fails, `raw_conn.invalidate()` + warning log occur and the original `work(conn)` exception propagates. | [WISHENKA-343](https://pypost.atlassian.net/browse/WISHENKA-343) |
