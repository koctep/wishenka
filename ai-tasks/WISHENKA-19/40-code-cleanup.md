# WISHENKA-19: Code Cleanup Report

## Linter Fixes

Describe fixed linter errors and warnings:

- Fixed: none. `make analyze` (Ruff lint, Ruff format check, Mypy) reported no issues
  on the first run and again after the template wraps.

## Code Formatting

Applied formatting changes:

- [x] Automatic code formatting — Ruff format check: 80 files already formatted
- [x] Indentation and alignment fixes — wrapped template lines keep the existing indent
- [x] Line length correction — 14 lines in `wishenka/web/templates/partials/item_card.html`
  and 3 lines in `wishenka/web/templates/base.html` were over 100 characters. URL
  attributes stay single-line. Jinja locals `bought_mark`, `undo_path`, and `item_web`
  hold the long expressions. Python files in this change were already within 100.

## Code Cleanup

Cleanup actions performed:

- Removed unused imports: none
- Removed unused variables: none
- Removed commented-out code: none
- Removed debug prints: none

## Validation Results

Validation results:

- [x] Scoped tests passed: `tests/test_wish_card_giver_controls.py` and
  `tests/test_wishlist_roles_lifecycle.py` — 39 passed. The full suite was not re-run.
- [x] All tests in those modules have explicit timeout markers (`pytestmark`)
- [x] No merge conflicts
- [x] Syntax is valid
- [x] Types are correct (Mypy: no issues in 80 source files)

## Notes

Template wraps do not change rendered URLs, giver copy, or the refresh script's
`aria-expanded` / `hidden` behavior. Whitespace around «Куплено» is stripped with
`{%-` / `-%}` so the own line stays `Забронировано вами (N)` plus ` · Куплено` only
when the single occupying promise is bought.

Commands run from `/home/src`:

- `make analyze` (before the wraps, and again after)
- pytest on the two giver-card modules (`-q`): 39 passed

```bash
.venv/bin/pytest tests/test_wish_card_giver_controls.py \
    tests/test_wishlist_roles_lifecycle.py -q
```
