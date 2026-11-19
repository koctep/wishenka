# WISHENKA-179: Technical Debt Analysis

## Shortcuts Taken

- **All capture callbacks routed through `execute_with_connection` (`wishenka/bot/capture.py`)**: The callback `mutate(service, conn)` closure handles all callback commands (`save`, `cancel`, `p_`, `edit`, `view`, `c_`, `e_`, `l_`) inside `store.execute_with_connection(mutate)` rather than splitting draft-only commands (`cancel`, `view`, `edit`, `p_`, `c_`, `e_`) into `store.transaction(...)`. This keeps the callback handler in a single transaction path and provides `lists = _allowed(service, actor)` for rendering the review keyboard, at the cost of running `WishlistStore._read` / `_write` even when `WishlistService` is not mutated.
- **Existing failure-injection test still monkeypatches `_write`**: `tests/test_bot_capture_repro.py::test_failed_atomic_save_can_be_retried` continues to monkeypatch `store._write` to simulate a mid-commit database failure. This was intentionally left untouched so existing regression coverage remains intact.

## Code Quality Issues

- **Large nested `mutate` closure (`wishenka/bot/capture.py`, lines 551–674)**: `mutate` is ~124 lines long with 8+ inline command branches (`cancel`, `save`, `p_`, `edit`, `view`, `c_`, `e_`, `l_`) and repeated `UPDATE bot_drafts ... revision=revision+1` SQL statements. Extracting per-command helpers or a shared draft-update helper would improve readability and reduce nesting.
- **No AST/lint check on other modules**: `tests/test_bot_capture_atomic_store_repro.py::test_bot_capture_does_not_access_private_store_read_write` guards `wishenka/bot/capture.py` specifically against accessing `_read` / `_write`, rather than enforcing the boundary across the entire `wishenka/bot/` package.

## Missing Tests

- **Timeout markers**: `tests/test_bot_capture_atomic_store_repro.py` declares module-level `pytestmark = pytest.mark.timeout(15)` (no missing timeout marker blocker).
- **`TokenCollision` retry with caller SQL writes**: There is no direct test verifying that when `WishlistStore.execute_with_connection` hits a `TokenCollision` or token-table `IntegrityError` after the caller executes SQL on `conn`, both `WishlistService` state and caller SQL writes are rolled back and cleanly re-executed on retry.
- **Post-commit log suppression on caller SQL rollback**: There is no direct test in `tests/test_bot_capture_atomic_store_repro.py` asserting that `pending_commit_logs` / `flushed` notices are not emitted when an exception is raised in caller SQL after `service.add_wish_item` succeeds.

## Performance Concerns

- **Full `WishlistService` hydration on non-save callbacks (`wishenka/bot/capture.py`)**: Because `store.execute_with_connection(mutate)` runs `_read(conn)` and `_write(conn, service, snapshot)` for every callback command (including pagination `p_`, `view`, `edit`, `cancel`, `c_`, `e_`), each button tap hydrates and diffs the full domain graph even when only `bot_drafts` is read or updated. For users with large wishlists, a lightweight read-only query for eligible list titles/IDs combined with `store.transaction` for draft-only actions would reduce per-callback overhead.

## Follow-up Tasks

- **NON-BLOCKER**: Refactor `wishenka/bot/capture.py:mutate` into smaller per-command helpers and consider routing draft-only callbacks (`cancel`, `view`, `edit`, `p_`, `c_`, `e_`) through `store.transaction` with a lightweight eligible-lists query instead of full `WishlistService` hydration. — Jira: [WISHENKA-250](https://pypost.atlassian.net/browse/WISHENKA-250)
- **NON-BLOCKER**: Add tests in `tests/test_bot_capture_atomic_store_repro.py` covering `execute_with_connection` `TokenCollision` retry rollback/re-execution of caller SQL and post-commit log suppression on rollback. — Jira: [WISHENKA-249](https://pypost.atlassian.net/browse/WISHENKA-249)
