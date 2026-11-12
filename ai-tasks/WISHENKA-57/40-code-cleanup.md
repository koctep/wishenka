# WISHENKA-57: Code Cleanup Report

## Linter Fixes

`make analyze` (Ruff lint, Ruff format check, Mypy strict) reported no issues
before or after the small edits below. Nothing in the touched files needed a
linter fix.

- Fixed: none. Ruff check passed with no warnings.
- Fixed: none. Mypy reported no issues in 77 source files.

## Code Formatting

Applied formatting changes:

- [x] Automatic code formatting — `ruff format --check` reported 77 files
  already formatted. No rewrite was required.
- [x] Indentation and alignment fixes — none required.
- [x] Line length correction — none required. The project limit is 100
  characters, and the touched files already stayed inside it.

## Code Cleanup

Cleanup actions performed:

- Removed unused imports: 0
- Removed unused variables: 1. The SQLite `connect` listener in
  `wishenka/wishlists/store.py` must accept the connection-record argument.
  The unused name `connection_record` is now `_connection_record`.
- Removed commented-out code: none present in the files this task touched.
- Removed debug prints: none present.
- Corrected the module docstring in
  `tests/test_shared_inventory_multiprocess.py`. It still said the current
  code maps a busy lock to `RuntimeError`. The test now describes
  `InventoryBusyError` and an unchanged wish.

## Validation Results

Validation results:

- [x] All tests passed
- [x] All tests have explicit timeout markers
- [x] No merge conflicts
- [x] Syntax is valid
- [x] Types are correct (if applicable)

Commands:

- `.venv/bin/pytest tests/test_shared_inventory_multiprocess.py -v` —
  9 passed in 16.36s.
- `make analyze` — Ruff check passed, 77 files already formatted, Mypy
  success on 77 source files.
- `make test` — 396 passed, 1 warning in 55.76s. The warning is
  `StarletteDeprecationWarning` from `fastapi/testclient.py` inside the
  installed FastAPI package.

`tests/test_shared_inventory_multiprocess.py` uses
`pytestmark = pytest.mark.timeout(60)`. Every other collected test module
already declares `pytest.mark.timeout` at module or function scope. No
merge-conflict markers were found in `wishenka/` or `tests/`.

## Notes

The edit-modal busy sentence stays in English:

`The wish was busy, the edit was not saved, and it can be submitted again.`

That wording is the sentence accepted in
`ai-tasks/WISHENKA-57/20-architecture.md`. This step's cleanup rules do not
require a translation, and `wishenka/web/routes/items_ui.py` has no i18n
catalog. The same modal uses a Russian sentence for the quantity-lock error.
That neighboring copy does not replace the accepted busy sentence.
