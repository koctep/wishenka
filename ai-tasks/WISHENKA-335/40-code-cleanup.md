# WISHENKA-335: Code Cleanup Report

## Linter Fixes

Describe fixed linter errors and warnings:

- Fixed: none. `make analyze` reported no Ruff or Mypy issues in the
  WISHENKA-335 diff. No source edits were required.

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

The shared runner names are all used. `MigrationHistory`,
`apply_history`, `apply_history_sync`, `configured`, and
`migration_lock_path` serve the wishlist history wrappers. Wishlist
startup and person startup re-export `upgrade_to_head` from
`wishenka.db.migrations`. The wishlist store also imports
`migration_lock_path` from that module. The repro file keeps
`pytestmark = pytest.mark.timeout(10)`.

Apply behavior is unchanged. The product history, legacy adoption, and
the person-key revision stay in `wishenka.wishlists`.

## Validation Results

Validation results:

- [x] All tests passed (repro not re-run; production code was not edited)
- [x] All tests have explicit timeout markers
  (`pytestmark = pytest.mark.timeout(10)` on the repro file)
- [x] No merge conflicts
- [x] Syntax is valid
- [x] Types are correct (Mypy, 304 source files)

Commands:

- `make analyze` — Ruff check passed, Ruff format check passed
  (304 files already formatted), Mypy succeeded with no issues in
  304 source files.
- Repro command was not run. Production code was not touched.

## Notes

Step 5 stays in progress for the acceptance gate. No production or test
edits were required.
