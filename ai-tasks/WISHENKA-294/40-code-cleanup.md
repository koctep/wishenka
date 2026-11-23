# WISHENKA-294: Code Cleanup Report

## Linter Fixes

- `make analyze` (ruff, ruff format, mypy): clean before and after; nothing to fix.
- `node --check` on `miniapp.js` and `app.js`: OK.

## Code Formatting

- [x] Automatic formatting: already applied (260 files formatted).
- [x] Line length: the one added line over 100 characters,
  `partials/reservations_list.html:41` ("Go to wish" anchor), wrapped onto three lines; the
  rendered text differs only by whitespace inside the inline anchor. No other added line in the
  Python, JS, CSS or test files exceeds 100 characters.

## Code Cleanup

- Removed unused imports, variables, commented-out code, debug prints: none found in the Step 4
  changes.
- Reviewer finding applied: `unavailable.py` now passes `headers=exc.headers` to the
  `TemplateResponse`, so the HTML 401 page keeps `WWW-Authenticate` (and any other exception
  headers).

## Validation Results

- [x] `make analyze` passes; `node --check` passes.
- [x] `make test-serial` on `test_cross_screen_comfort_browser.py` (48),
  `test_home_overview_browser.py`,
  `test_home_overview_ui.py`, `test_i18n_unit.py`, `test_wishenka_219_badge.py`,
  `test_miniapp_i18n_repro.py`, `test_i18n_sync.py`, `test_browser_prerequisites.py`:
  159 passed.
- [x] Browser tests keep their existing timeout markers (checked by
  `test_browser_prerequisites.py`).

## Notes

No behavior changes. Template whitespace inside the wrapped anchor is the only rendered delta.
