# WISHENKA-108: Code Cleanup Report

## Linter Fixes

- `make analyze`: Ruff linter "All checks passed", Mypy "no issues found in 97 source files". No findings, no fixes needed.

## Code Formatting

- [x] Automatic code formatting — Ruff format check: 97 files already formatted.
- [x] Indentation and alignment fixes — none needed. `wishlist.js` uses 2-space indent, single quotes and semicolons, same as the neighbouring `miniapp.js`.
- [x] Line length correction — none needed (Ruff 100 columns; `wishlist.js` lines are all under 100).

## Code Cleanup

- Removed unused imports: 0.
- Removed unused variables: 0.
- Removed commented-out code: none found.
- Removed debug prints: none. The single `console.warn` in `wishlist.js` is an intentional diagnostic for the "missing wishlist id or htmx" skip path, not a debug leftover; kept.
- Dead code: none in `wishlist.js`. All constants and helpers (`SUMMARY_SELECTOR`, `TOGGLE_EXCLUSION`, `WISHLIST_ID_PATTERN`, `toggleWishCard`, `findSummary`) are used. JSDoc is complete on every function and on the `dragged` state variable.
- `base.html`: no leftovers after the move. The inline toggle/DnD block is gone, the remaining inline script (CSRF, reservation helpers) is untouched, there are no extra empty lines, and no CSS/ids/variables became unused. Nothing references `toggleWishCard` outside `wishlist.js` and the tests that assert its absence.
- No files were edited in this step; behaviour is unchanged.

## Validation Results

- [x] All tests passed — see Notes for the full-suite result.
- [x] All tests have explicit timeout markers — the three task test modules use module-level `pytestmark = pytest.mark.timeout(30)`.
- [x] No merge conflicts.
- [x] Syntax is valid — `node --check wishenka/web/static/wishlist.js` OK; Ruff and Mypy clean. ESLint/Prettier were not run (not installed locally; nothing was installed).
- [x] Types are correct — Mypy passed.

## Notes

- Full suite (`PYTHONDONTWRITEBYTECODE=1 make test`): 523 passed, 2 warnings (third-party deprecations), 0 failed, 455 s. No failures, so no triage or baseline worktree run was needed.
- The untracked `core` file in the repo root is not part of this task and was left alone.
