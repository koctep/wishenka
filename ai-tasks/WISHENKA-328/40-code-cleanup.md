# WISHENKA-328: Code Cleanup Report

## Linter Fixes

Describe fixed linter errors and warnings:

- Fixed: none. `make analyze` reported no Ruff or Mypy issues. No source
  edits were required.

## Code Formatting

Applied formatting changes:

- [x] Automatic code formatting
- [x] Indentation and alignment fixes
- [x] Line length correction

Ruff format already kept the scoped Python at the 100-character limit.
No indentation or wrapping changes were required.

## Code Cleanup

Cleanup actions performed:

- Removed unused imports: 0
- Removed unused variables: 0
- Removed commented-out code: none in the scoped files
- Removed debug prints: none in the scoped files

The new names are all used. `UserStore.write` calls `_immediate`.
`listing` and `_find_active_chat_id` use the read-only connection they
open. `ensure_private_bot_user` and `reservation_confirmations` pass
`AsyncConnection` into `users.write`. Every helper in
`tests/test_wishenka_328_read_lock_and_bot_busy_repro.py` is called by
the four tests.

Read-lock and busy-save behavior is unchanged. Birthday list and the
active-chat lookup still open with a read-only `BEGIN`. A locked
private-chat save and a locked confirmation save still raise
`UserStoreBusyError`.

## Validation Results

Validation results:

- [x] Required tests passed (full suite was not re-run)
- [x] All tests have explicit timeout markers
  (`pytestmark = pytest.mark.timeout(30)` on the repro file)
- [x] No merge conflicts
- [x] Syntax is valid
- [x] Types are correct (Mypy, 299 source files)

Commands:

- `make analyze` — Ruff check passed, Ruff format check passed
  (299 files already formatted), Mypy succeeded with no issues in
  299 source files.
- `make test PYTEST_ARGS="tests/test_wishenka_328_read_lock_and_bot_busy_repro.py -q"`
  — 4 passed in 14.23s.

## Notes

Step 5 stays in progress for the acceptance gate. No production or test
edits were required.
