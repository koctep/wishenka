# WISHENKA-311: Code Cleanup Report

## Linter Fixes

Describe fixed linter errors and warnings:

- Fixed: `tests/test_history_screen_browser.py`, `_older_list_is_first`.
  Mypy `no-any-return`: the history row name is `Any`, so comparing it
  with a string and returning that value was not a `bool`. The name is
  stored first. The function then returns `bool(name == "Older list")`.
  `httpx.HTTPError` still returns `False`, so the poll retries that read.

## Code Formatting

Applied formatting changes:

- [x] Automatic code formatting. Ruff format already matched both files.
- [ ] Indentation and alignment fixes. None were required.
- [x] Line length correction. Both files stay within 100 characters.
  The longest line in the history file is 100.

## Code Cleanup

Cleanup actions performed:

- Removed unused imports: 0
- Removed unused variables: 0
- Removed commented-out code: none in this change
- Removed debug prints: none in this change

## Validation Results

Validation results:

- [ ] All tests passed. This step did not re-run pytest. Step 4 recorded
  the primed parallel run: 81 passed in 33.98 s. The only edit here wraps
  the same comparison in `bool`.
- [x] All tests have explicit timeout markers. Both modules set
  `pytestmark` to `pytest.mark.timeout(45)` and `pytest.mark.browser`.
- [x] No merge conflicts in the two test files.
- [x] Syntax is valid. Ruff parsed both files.
- [x] Types are correct. The second `make analyze` Mypy run reported
  no issues in 306 source files.

## Notes

`make analyze` from `/home/src` was run twice.

First run, before the fix, exit 2:

- Ruff linter: all checks passed.
- Ruff format check: 306 files already formatted.
- Mypy: 1 error in 1 file (306 source files checked).
  `tests/test_history_screen_browser.py:861: error: Returning Any from
  function declared to return "bool"  [no-any-return]`.

Second run, after the fix, exit 0:

- Ruff linter: all checks passed.
- Ruff format check: 306 files already formatted.
- Mypy: Success: no issues found in 306 source files.

Edits stayed in `tests/test_history_screen_browser.py`.
`tests/test_cross_screen_comfort_browser.py` needed no lint or format
change. `wishenka/` was not edited. WISHENKA-357 and WISHENKA-285 were
not fixed. No receipt was added to `app.js`.

STEP 5 stays `[/]` for the acceptance gate.
