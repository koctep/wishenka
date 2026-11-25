# WISHENKA-253: Technical Debt Analysis

## Shortcuts Taken

None. `WISHENKA-253` is a pure test-addition task covering existing contracts of `WishlistStore.execute_read` (`tests/test_wishlists_sqlite_repo.py`) and `ensure_private_bot_user` (`tests/test_bot_principal.py`) with no production code changes.

Related production improvements intentionally kept out of scope are already tracked separately:
- `WISHENKA-254`: `PRAGMA query_only` / `SQLITE_BUSY` retry hardening in `WishlistStore.execute_read`.
- `WISHENKA-255`: Refactoring duplicate clock helpers and narrowing dependency type protocols for `ensure_private_bot_user`.
- `WISHENKA-256`: Query consolidation in `collect_diagnostic_context`.

## Code Quality Issues

None.
- Both `tests/test_wishlists_sqlite_repo.py` and `tests/test_bot_principal.py` pass `ruff check`, `ruff format`, and `mypy` with zero issues (verified in `ai-tasks/WISHENKA-253/40-code-cleanup.md`).
- `tests/test_bot_principal.py` initializes both `WishlistStore` and `UserStore` on the same `tmp_path` SQLite URL in `_make_stores` because the `bot_destinations` table is provisioned by `WishlistStore.initialize()`, matching the existing pattern in `tests/test_wishenka_182_repro.py`.

## Missing Tests

None for the `WISHENKA-253` scope:
- All `WishlistStore.execute_read` contracts (rollback on normal return, rollback on exception, non-blocking WAL read alongside an active `BEGIN IMMEDIATE` transaction) are directly covered in `tests/test_wishlists_sqlite_repo.py`.
- All `ensure_private_bot_user` edge cases (`user=None`, `user_store=None`/absent, `chat_id != user.id`, pre-resolved `user_record`, and `now`/`dependencies.clock()` normalization) are directly covered in `tests/test_bot_principal.py`. (The `user_record=None` lookup/upsert path and `_private_bot_user` log suppression are already covered in `tests/test_wishenka_182_repro.py`.)
- **Timeout markers check**: Both `tests/test_wishlists_sqlite_repo.py` and `tests/test_bot_principal.py` declare `pytestmark = pytest.mark.timeout(10)`, and all `asyncio.wait_for(...)` calls in `test_execute_read_does_not_block_on_active_immediate_transaction` use explicit bounded timeouts (`2.0s` / `5.0s`) with `finally` task/engine cleanup (no `do-testing` blocker).

## Performance Concerns

None. All 15 tests across `tests/test_wishlists_sqlite_repo.py` and `tests/test_bot_principal.py` complete in `3.41s` using isolated `tmp_path` SQLite databases.

## Follow-up Tasks

| ID | Priority | Area | Description | Impact / Remediation | Jira |
| --- | --- | --- | --- | --- | --- |
