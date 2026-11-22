# WISHENKA-288: Code Cleanup Report

## Linter Fixes

- Fixed >100-character line length in `wishenka/web/static/miniapp.css` by wrapping the
  `.receipt-sheet form` declaration block across two lines (`<= 100` characters).
- Fixed >100-character line length in `tests/test_visual_identity_browser.py` (`E501`) by
  wrapping `matchesExpected` inside `_assert_focus_visible` (`<= 100` characters).
- Fixed >100-character touched lines in `wishenka/web/templates/partials/member_list.html`
  (wrapped `class="..."` on `.btn-delete.btn-danger` across two lines) and
  `wishenka/web/templates/settings.html` (wrapped `#birthdate-form` submit `<button>` inner
  text across lines), keeping every touched/added line `<= 100` characters while preserving
  HTML structure, Jinja rendering, classes, attributes, and whitespace semantics.
- Confirmed `ruff check wishenka tests`, `ruff format --check wishenka tests`,
  `mypy wishenka tests`, `node --check wishenka/web/static/miniapp.js`, and `git diff --check`
  pass with zero warnings or errors.
- Confirmed `wishenka/web/static/miniapp.js` required no Step 5 edits and adheres to
  `lsr-javascript` (`const`/`let` with zero `var`, strict equality `===`/`!==`, arrow
  functions, optional chaining `?.`, nullish coalescing `??`, zero debug `console.log`
  statements, and zero unused helper functions).

## Code Formatting

Applied formatting and style checks across all WISHENKA-288 modified and added files:

- [x] Automatic code formatting verified via `ruff format --check wishenka tests`
  (`250 files already formatted`)
- [x] Indentation and alignment verified (`git diff --check` clean;
  `wishenka/web/static/miniapp.css` permissions are `0644`, matching adjacent static assets)
- [x] Line length correction applied in `wishenka/web/static/miniapp.css`
  (`.receipt-sheet form`), `tests/test_visual_identity_browser.py` (`matchesExpected`),
  `wishenka/web/templates/partials/member_list.html` (`.btn-delete.btn-danger`), and
  `wishenka/web/templates/settings.html` (`#birthdate-form` submit button); zero lines over
  100 characters in `ai-tasks/WISHENKA-288/40-code-cleanup.md`,
  `ai-tasks/WISHENKA-288/00-roadmap.md`, `wishenka/web/static/miniapp.css`,
  `wishenka/web/static/miniapp.js`, `tests/test_visual_identity_browser.py`, and all
  added/modified (`+`) lines of `git diff`

## Code Cleanup

Cleanup actions performed:

- Removed unused CSS token `--border: #eac8d3;` in `:root` of
  `wishenka/web/static/miniapp.css` (never referenced across `wishenka/` or `tests/`).
- Removed duplicated CSS selectors in `wishenka/web/static/miniapp.css`:
  - Removed redundant `a.btn-primary:hover` and `a.btn-danger:hover` selectors (specificity
    `(0, 2, 1)`; `a.btn-primary:hover:not(:disabled)` would have specificity `(0, 3, 1)`),
    because `.btn-primary:hover:not(:disabled)` and `.btn-danger:hover:not(:disabled)` have
    specificity `(0, 3, 0)`, which already matches both `<button>` and `<a>` and overrides
    `:where(...):hover:not(:disabled)` (`(0, 2, 0)`) and `.btn-primary`/`.btn-danger`
    (`(0, 1, 0)`).
  - Removed redundant `.receipt-sheet :focus-visible, .modal-sheet :focus-visible` rule
    because both `.receipt-sheet` and `.modal-sheet` already set
    `--focus: var(--receipt-text);`, which feeds
    `:focus-visible { outline: 3px solid var(--focus); outline-offset: 3px; }`.
- Retained `.modal-header h2 { color: inherit; }` in `wishenka/web/static/miniapp.css`
  because `wishenka/web/templates/partials/share_modal.html` renders `.modal-header` outside
  `.modal-sheet`.
- Cleaned up `tests/test_visual_identity_browser.py` per `lsr-python` and `do-testing`:
  - Added docstring to `_open`.
  - Replaced mixed `'{selector}'` / `repr(selector)` JS interpolation in
    `test_both_shells_use_coherent_light_canvas_and_surfaces` with `js_str(selector)`.
  - Eliminated local variable `focus` shadowing `tests.browser_helpers.focus` and
    consolidated the three duplicated `:focus-visible` outline assertions into
    `_assert_focus_visible`.
- Unused imports removed: `0` (all imports in `tests/test_visual_identity_browser.py` are
  used).
- Unused variables removed: `0` (fixed variable shadowing of `focus`).
- Commented-out code removed: `0` (none found).
- Debug prints removed: `0` (none found; `console?.warn?.(...)` calls in
  `wishenka/web/static/miniapp.js` are intentional i18n fallback diagnostics).

## Validation Results

All checks below ran **after** the final edit:

- [x] Targeted browser and i18n tests passed (`68 passed` across the 6 targeted test modules)
- [x] All tests in `tests/test_visual_identity_browser.py` have explicit timeout and browser
  markers (`pytestmark = [pytest.mark.timeout(45), pytest.mark.browser]`), and all browser
  waits use bounded CDP deadlines (`CdpPage.wait_for` default `5.0`s, `settle`,
  `open_receipt_dialog`, `navigate` `10.0`s)
- [x] No merge conflicts or whitespace/diff errors (`git diff --check` exited `0`)
- [x] Syntax is valid (`node --check wishenka/web/static/miniapp.js` exited `0`)
- [x] Static analysis and types are clean (`make analyze`: Ruff lint, Ruff format, and Mypy
  passed across `250` source files)

### Verification Commands

```bash
node --check wishenka/web/static/miniapp.js
# exit 0 (no output)

git diff --check
# exit 0 (no output)

make analyze
# ==> Running Ruff linter...
# All checks passed!
# ==> Running Ruff format check...
# 250 files already formatted
# ==> Running Mypy type checker...
# Success: no issues found in 250 source files

CHROMIUM_LIB=/tmp/wishenka-chromium/usr/lib/aarch64-linux-gnu
WISHENKA_CHROMIUM_BIN=/tmp/wishenka-chromium/usr/lib/chromium/chromium-headless-shell \
  LD_LIBRARY_PATH="${CHROMIUM_LIB}:${CHROMIUM_LIB}/pulseaudio" \
  PYTHONPATH=. .venv/bin/pytest \
  tests/test_visual_identity_browser.py \
  tests/test_receipt_theme_browser.py \
  tests/test_receipt_accessibility_browser.py \
  tests/test_bot_menu_miniapp_e2e_browser.py \
  tests/test_i18n_unit.py \
  tests/test_i18n_sync.py \
  -v --tb=short
# 68 passed
```

## Notes

- Existing `miniapp.js` tests (such as `tests/test_reservations_cabinet_ui.py`) inspect source
  slices using `source_between(source, "async function showHome(", "function settingsForm(")`.
  Step 5 made no edits to `wishenka/web/static/miniapp.js`, whereas Step 4's scoped diff is
  `+11/-8` lines preserving both the `async function showHome(` and `function settingsForm(`
  function boundaries and all behavioral and static contracts.
- All accessibility guarantees (light/dark modal heading and `:focus-visible` contrast
  `>= 4.5`, `44px` touch targets, link button geometry, keyboard focus rings, and
  selected/disabled visual distinctions) remain intact and verified in headless Chromium.
