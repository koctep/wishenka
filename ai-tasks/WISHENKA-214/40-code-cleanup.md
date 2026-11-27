# WISHENKA-214: Code Cleanup Report

## Linter Fixes

Describe fixed linter errors and warnings:

- None required. `make analyze` (Ruff check, Ruff format check, Mypy) reported
  all checks passed, 306 files already formatted, and no issues in 306 source
  files. JavaScript and HTML are outside that target; those files were checked
  by hand for the 100-character line limit, unused names, and debug output.

## Code Formatting

Applied formatting changes:

- [x] Automatic code formatting (`make analyze` format check; Python already
  matched Ruff)
- [x] Indentation and alignment fixes (capture-phase note in `receipt.js` now
  uses the file's block-comment style)
- [x] Line length correction (`data-own-feedback` moved to its own line on the
  three receipt dialog roots; the added attribute had pushed the opening tag
  to 105 characters)

## Code Cleanup

Cleanup actions performed:

- Removed unused imports: 0
- Removed unused variables: 0
- Removed commented-out code: none found
- Removed debug prints: none found (`console.` and `print` are absent from the
  touched scripts)
- Reworded the docstring of
  `test_shared_app_script_has_no_gift_receipt_reference` so it no longer says
  the header reads are still red. The assertion is unchanged: raw and
  comment-stripped `app.js` are still compared case-insensitively against
  `X-Receipt-Refusal`, `.receipt-sheet`, and the substring `receipt`.

## Validation Results

Validation results:

- [x] Scoped static tests passed: 11 passed, including
  `test_shared_app_script_has_no_gift_receipt_reference`.
  Command: `td-log run test --task WISHENKA-214 -- make test`
  with `PYTEST_ARGS="tests/test_receipt_static_script.py"`.
- [x] All tests in that file have an explicit timeout marker
  (`pytestmark = pytest.mark.timeout(30)`)
- [x] No merge conflicts (`git diff --check` on the scoped files exited 0)
- [x] Syntax is valid (pytest collected and ran the module; Mypy succeeded)
- [x] Types are correct (Mypy: no issues found in 306 source files)

## Notes

- `app.js` was already within the line limit and contains no `receipt`
  substring. It was not edited in this step.
- Pre-existing lines longer than 100 characters in the receipt partials (the
  `hx-swap-oob` attribute line and later markup) were left as they were.
- The full suite was not re-run. Pre-existing failures
  `tests/test_receipt_modal_browser.py::test_unmarked_error_neither_shows_notice_nor_reloads`
  (WISHENKA-220) and
  `tests/test_receipt_modal_browser.py::test_busy_keeps_dialog_and_chosen_quantity`
  (WISHENKA-354) were not touched.
