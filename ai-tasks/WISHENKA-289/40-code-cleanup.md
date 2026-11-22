# WISHENKA-289: Code Cleanup Report

## Linter Fixes

- Confirmed `.venv/bin/ruff check --no-cache wishenka tests`,
  `.venv/bin/ruff check --no-cache --select E,F,I,B,UP,RUF100` on
  `wishenka/i18n/catalog.py`, `tests/test_home_overview_ui.py`, and
  `tests/test_home_overview_browser.py`,
  `.venv/bin/ruff format --check --no-cache wishenka tests`,
  `.venv/bin/mypy --no-incremental --cache-dir=/dev/null wishenka tests`,
  `node --check wishenka/web/static/miniapp.js`, and `git diff --check` pass with zero warnings
  or errors.
- Confirmed `wishenka/web/static/miniapp.js` required no Step 5 edits and adheres to
  `lsr-javascript` (`const`/`let` with zero `var`, strict equality `===`/`!==`, arrow functions,
  optional chaining `?.`, nullish coalescing `??`, zero debug `console.log` statements, and zero
  unused helper functions).
- Confirmed all added `miniapp.home.*` entries in `wishenka/i18n/catalog.py` stay `<= 100`
  characters per line with identical EN/RU placeholder sets and WCAG 2.5.3 Label-in-Name
  `aria-label` prefixes.

## Code Formatting

Applied formatting and style checks across all WISHENKA-289 modified and added files:

- [x] Automatic code formatting verified via
  `.venv/bin/ruff format --check --no-cache wishenka tests` (`252 files already formatted`)
- [x] Indentation and alignment verified (`git diff --check` clean; zero tab characters across
  all touched code, test, and Markdown artifact files)
- [x] Line length verified at `<= 100` characters across `wishenka/web/static/miniapp.js`,
  `wishenka/web/static/miniapp.css`, `tests/test_home_overview_ui.py`,
  `tests/test_home_overview_browser.py`, `ai-tasks/WISHENKA-289/*.md`, and all added/modified
  (`+`) lines of `git diff` (including `wishenka/i18n/catalog.py`)

## Code Cleanup

Cleanup actions performed:

- Simplified duplicate CSS declaration in `wishenka/web/static/miniapp.css`:
  - Moved `.history-time` (`margin-left: .5rem;`) immediately above `.deleted-meta`
    (`margin-left: 0; flex-shrink: 0;`) and removed the redundant
    `.wishlist-card-header .history-time { margin-left: 0; }` selector, so `.deleted-meta`
    cleanly resets `margin-left: 0` on `.history-time.deleted-meta` at equal `(0, 1, 0)`
    specificity without duplicate rules.
- Verified all four additive CSS custom properties in `:root` of
  `wishenka/web/static/miniapp.css` (`--surface-subtle`, `--border-subtle`, `--accent-soft`,
  and `--muted-border`) are actively referenced across `.reservations-card`,
  `.wishlist-section*`, `.section-count`, `.wishlist-card*`, and `.empty-state`.
- Cleaned up `tests/test_home_overview_ui.py` and `tests/test_home_overview_browser.py` per
  `lsr-python` and `do-testing`:
  - Added docstrings to helper functions `_placeholders`, `_load_miniapp_assets`, `_run_node`,
    `_classes`, `_find_all`, `_find_one`, `_collect_text`, and `_reservations_card_html` in
    `tests/test_home_overview_ui.py`.
  - Removed unused `"fav_id"` key from the dictionary returned by `_seed_rich_overview` in
    `tests/test_home_overview_browser.py`.
- Unused imports removed: `0` (all imports in `tests/test_home_overview_ui.py` and
  `tests/test_home_overview_browser.py` are used).
- Unused variables removed: `1` (unused `"fav_id"` entry in `_seed_rich_overview`).
- Commented-out code removed: `0` (none found).
- Debug prints removed: `0` (none found; `console?.warn?.(...)` calls in
  `wishenka/web/static/miniapp.js` are intentional i18n fallback diagnostics).

## Validation Results

All checks below ran **after** the final edit:

- [x] All 10 targeted unit, i18n, and browser test suites passed (`102 passed`)
- [x] All tests declare explicit timeout markers (`pytestmark = pytest.mark.timeout(20)` in
  `tests/test_home_overview_ui.py` and
  `pytestmark = [pytest.mark.timeout(45), pytest.mark.browser]` in
  `tests/test_home_overview_browser.py`), and all internal waits are bounded
  (`subprocess.run(..., timeout=10)`, `httpx.Client(..., timeout=10)`, and `CdpPage.wait_for`
  default `5.0`s / `navigate` `10.0`s)
- [x] No merge conflicts or whitespace/diff errors (`git diff --check` exited `0`)
- [x] Syntax is valid (`node --check wishenka/web/static/miniapp.js` exited `0`)
- [x] Static analysis and types are clean (`ruff check`, `ruff format --check`, and `mypy`
  passed across `252` source files)

### Verification Commands

```bash
node --check wishenka/web/static/miniapp.js
# exit 0 (no output)

git diff --check
# exit 0 (no output)

.venv/bin/ruff check --no-cache wishenka tests \
  && .venv/bin/ruff check --no-cache --select E,F,I,B,UP,RUF100 \
    wishenka/i18n/catalog.py \
    tests/test_home_overview_ui.py \
    tests/test_home_overview_browser.py \
  && .venv/bin/ruff format --check --no-cache wishenka tests \
  && .venv/bin/mypy --no-incremental --cache-dir=/dev/null wishenka tests
# All checks passed!
# All checks passed!
# 252 files already formatted
# Success: no issues found in 252 source files

CHROMIUM_LIB=/tmp/wishenka-chromium/usr/lib/aarch64-linux-gnu
WISHENKA_CHROMIUM_BIN=/tmp/wishenka-chromium/usr/lib/chromium/chromium-headless-shell \
  LD_LIBRARY_PATH="${CHROMIUM_LIB}:${CHROMIUM_LIB}/pulseaudio" \
  PYTHONPATH=. .venv/bin/pytest \
  tests/test_home_overview_ui.py \
  tests/test_home_overview_browser.py \
  tests/test_visual_identity_browser.py \
  tests/test_reservations_cabinet_ui.py \
  tests/test_wishlist_sections_ui.py \
  tests/test_wishlist_deleted_restore.py \
  tests/test_miniapp_i18n_repro.py \
  tests/test_bot_menu_miniapp_e2e_browser.py \
  tests/test_i18n_unit.py \
  tests/test_i18n_sync.py \
  -v --tb=short
# 102 passed
```

## Notes

- Preserved all existing static and runtime contracts in `wishenka/web/static/miniapp.js`:
  - `tests/test_reservations_cabinet_ui.py` inspects the slice between
    `async function showHome(` and `function settingsForm(` (`source_between`), confirming
    `/web/reservations/card` and `node(` are present and `innerHTML`, `insertAdjacentHTML`, and
    `createContextualFragment` remain absent.
  - `tests/test_miniapp_i18n_repro.py` runs `miniapp.js` in a minimal Node VM DOM mock where
    `root.querySelector('.wishlist-section')` scans direct children of `#app`.
  - `tests/test_visual_identity_browser.py` asserts `document.querySelectorAll('.top-nav
    button').length === 2` with distinct primary and secondary button styles and opaque
    `#ffffff` section surfaces.
  - `tests/test_bot_menu_miniapp_e2e_browser.py` verifies `startapp=create` focuses the Create
    wishlist button via `root.querySelector('button')?.focus()` without auto-creating a list,
    and clicking Create submits `POST /api/wishlists` with `{}` (`WISHENKA-296` compatibility).
