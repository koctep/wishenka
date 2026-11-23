# WISHENKA-296: Code Cleanup Report

## Linter Fixes

- `make analyze`: ruff lint, ruff format check and mypy are clean (269 files); no fixes needed.
- `node --check wishenka/web/static/miniapp.js`: valid.

## Code Formatting

- [x] Automatic code formatting: nothing to change (ruff format clean).
- [x] Indentation and alignment: no changes.
- [x] Line length: no added Python, JS or CSS line exceeds 100 characters (ruff E501 clean;
  `miniapp.js:488` was already wrapped by the orchestrator).

## Code Cleanup

- Removed unused imports: 0 (`field_validator` in `wishlists.py` is used).
- Removed unused variables or helpers: 0.
- Reviewed `showCreate()` for the `submitting` flag versus `withPending` and the readonly
  inputs. The flag is not provably redundant: it guards the Cancel handler and the submit
  handler for the whole request including the error path, while `withPending` only covers the
  Create button. Left unchanged.
- No duplicate CSS: `.settings-field-error` and the `aria-invalid` rule are new and unique.
- No commented-out code, debug output or stale comments found. The `api()` comment about 422
  matches the code.
- Not changed on purpose: catalog text, class hooks, test files.

## Validation Results

- [x] All tests passed: `make test-serial` on the three new modules
  (`test_wishlist_create_validation_api.py`, `test_wishlist_create_form_ui.py`,
  `test_wishlist_create_form_browser.py`), the five updated modules,
  `tests/test_history_screen_browser.py` and `tests/test_reservations_cabinet_ui.py`
  : 237 passed, 1 warning.
- [x] All tests have explicit timeout markers (unchanged by this step).
- [x] No merge conflicts.
- [x] Syntax is valid (`node --check`).
- [x] Types are correct (mypy clean).

## Notes

No source changes were needed in this step. For Step 7 debt: `api()` sets `err.body` only for
422 because of the timing-weak wait in `tests/test_history_screen_browser.py[500]`; settings
editing does not follow the title rule; possible `-p no:logging` caplog setup errors.
