# WISHENKA-132: Technical Debt Analysis

Scope: [`wishenka/wishlists/store.py`](file:///home/src/wishenka/wishlists/store.py#L397-L432) (`WishlistStore.initialize`, `WishlistStore.dispose`) and [`tests/test_wishenka_132_initialize_dispose_repro.py`](file:///home/src/tests/test_wishenka_132_initialize_dispose_repro.py). Compared against `10-requirements.md`, `20-architecture.md`, `40-code-cleanup.md`, and `50-observability.md`.

Timeout markers check: [`tests/test_wishenka_132_initialize_dispose_repro.py`](file:///home/src/tests/test_wishenka_132_initialize_dispose_repro.py#L21) declares `pytestmark = pytest.mark.timeout(10)` at module level. All tests use `monkeypatch` without sleeps or unbounded waits. No `do-testing` timeout-marker BLOCKER.

Pre-existing failures: none observed in the scoped test run reported in `40-code-cleanup.md` (`13 passed in 1.92s`).

Blockers: none.

## Shortcuts Taken

None. `WISHENKA-132` implements the planned `try ... except BaseException` cleanup in `WishlistStore.initialize()` and SQLite sidecar (`-wal`, `-shm`, `-journal`) plus migration-lock cleanup in `WishlistStore.dispose()` without workarounds, hardcoded values, or deviations from `20-architecture.md`.

## Code Quality Issues

None requiring remediation. Minor accepted observation:
- In [`WishlistStore.initialize()`](file:///home/src/wishenka/wishlists/store.py#L404-L414), `await self.dispose()` runs inside `except BaseException:` without a nested `try/except` guard. If `self.engine.dispose()` or `Path.unlink()` raised an unexpected `OSError` during failure cleanup, that secondary error would mask the original initialization exception. Accepted as negligible risk because `unlink(missing_ok=True)` and `AsyncEngine.dispose()` do not normally raise on local temp files.

## Missing Tests

None blocking; all acceptance criteria in `10-requirements.md` (`:memory:` temp-file and lock cleanup, persistent DB preservation, `dispose()` idempotency, unmapped exception propagation, and structured cleanup logging) are covered in [`tests/test_wishenka_132_initialize_dispose_repro.py`](file:///home/src/tests/test_wishenka_132_initialize_dispose_repro.py).

Minor unexercised edge cases (accepted, no follow-up needed):
- Explicit assertions for SQLite sidecar files (`-wal`, `-shm`, `-journal`) in `dispose()` and `asyncio.CancelledError` during `initialize()` (handled by the `suffix` loop at `store.py:424-425` and `except BaseException:` at `store.py:404`).

## Performance Concerns

None. Cleanup executes only on `initialize()` failure and uses `unlink(missing_ok=True)` on at most five paths.

## Follow-up Tasks

| ID | Priority | Area | Description | Impact / Remediation | Jira |
| --- | --- | --- | --- | --- | --- |
