# WISHENKA-265: Code Cleanup Report

## Linter Fixes

`make analyze` covers Python (`ruff check`, `ruff format --check`, and `mypy`
on `wishenka` and `tests`). This repository has no ESLint or Prettier config
for `wishenka/web/static/app.js`.

- Fixed: none. Ruff reported all checks passed.
- Fixed: none. Ruff format reported 306 files already formatted.
- Fixed: none. Mypy reported no issues in 306 source files.

The giver-card wiring needed no linter edit. It publishes
`window.swapWishCard` once and calls that property when the card fetch
returns text.

## Code Formatting

Applied formatting changes:

- [x] Automatic code formatting (Python already formatted; no JS formatter)
- [x] Indentation and alignment fixes (none needed in the wiring)
- [x] Line length correction (no line in `app.js` exceeds 100 characters)

## Code Cleanup

Cleanup actions performed:

- Removed unused imports: 0
- Removed unused variables: 0
- Removed commented-out code: none in the wiring
- Removed debug prints: none in the wiring

`wishenka/web/static/app.js` stays as Step 4 left it. After the local
`swapWishCard` function, the script assigns `window.swapWishCard = swapWishCard`.
The `htmx:afterRequest` card fetch calls `window.swapWishCard(card, markup)`
when `response.text()` resolves, so a wrap installed by `wishlist.js` is the
function that runs. The listener does not call the local name. No other file
was edited.

## Validation Results

Validation results:

- [ ] All tests passed
- [x] All tests have explicit timeout markers
- [x] No merge conflicts
- [x] Syntax is valid
- [x] Types are correct (if applicable)

Product code did not change, so `test_stale_giver_card_is_neutral` was not
re-run. That module sets `pytestmark` to `pytest.mark.timeout(45)` and
`pytest.mark.browser`. `node --check wishenka/web/static/app.js` passed.
`git diff --check` on `app.js` reported no conflict markers. Mypy covers the
Python tree. The published swap already has JSDoc (`Element`, `string`,
`void`).

## Notes

The wiring already matches the Step 2 plan: one publish inside the IIFE, and
a property lookup at event time. STEP 5 stays `[/]` for the acceptance gate.
