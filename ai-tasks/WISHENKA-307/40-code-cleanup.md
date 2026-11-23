# WISHENKA-307: Code Cleanup Report

## Linter Fixes

- `make analyze`: ruff lint, ruff format check, mypy all clean before and after; no fixes needed.
- `node --check wishenka/web/static/settings.js`: valid.

## Code Formatting

- [x] Automatic code formatting: nothing to change (ruff format clean).
- [x] Line length: all added lines in the four scope files are at most 100 characters.
- [x] `ai-tasks/WISHENKA-307/30-failing-repro.md`: the inventory table (rows up to 219
  characters) became a nested list wrapped to 100 characters; the content is unchanged.

## Code Cleanup

- Removed unused imports: 0 (ruff clean; every name in the test module is used).
- Removed unused variables, helpers or constants: 0 (checked by name-occurrence scan).
- `wishenka/web/static/miniapp.css`: the unknown-state track used `border: 2px solid`, which
  repeated the base width and style; now `border-color: var(--danger)` (identical computed
  style). The pending-state `border` shorthand stays because it changes the style to dashed.
- Kept deliberately: the `background` re-declarations on unknown and pending tracks and thumbs
  (they override the `:checked` rules, which have equal specificity), and the shared transition
  selector (already one rule for `::before` and `::after`).
- `settings.js`: the change is three lines in `refreshDisabled` (`aria-busy` set or removed on
  global switches); `toggleAttribute` was rejected because it writes `aria-busy=""`, not
  `"true"`. No change.
- No commented-out code, debug output or stale comments found.

## Validation Results

- [x] All tests passed: `make test-serial` on `tests/test_settings_switch_browser.py`,
  `tests/test_personal_settings_browser.py`, `tests/test_cross_screen_comfort_browser.py`,
  `tests/test_browser_prerequisites.py`, `tests/test_i18n_sync.py`: 171 passed (the switch
  module's 33 included).
- [x] Test module keeps `pytest.mark.timeout(45)` through `pytestmark`.
- [x] No merge conflicts.
- [x] Syntax is valid (`node --check`).
- [x] Types are correct (mypy clean).

## Notes

Not fixed here, left for Step 7 debt: forced-colors track colour for pending or unknown plus
checked, and label wrapping at ru-320.
