# WISHENKA-110: Code Cleanup Report

## Linter Fixes

- `make analyze`: Ruff linter "All checks passed", Ruff format check "103 files already formatted", Mypy "no issues found in 103 source files". No findings.
- `node --check tests/browser_assets/htmx_stub.js`: OK.
- Fixed: websockets `DeprecationWarning` at `tests/browser_cdp.py:160` (`ws.send`, 53+ repeats in the warning summary). Text: "connect() must be used as a context manager ... alternatively, use `websocket = connect(..., legacy=True)` to connect directly". `CdpBrowser.new_page` now passes `legacy=True` (installed websockets 17.4) with a one-line comment. Behaviour unchanged (the connection is held open and closed by `CdpPage.close`). The warning summary now shows only the third-party httpx/starlette warning.

## Code Formatting

- [x] Automatic code formatting: Ruff format clean for the whole scope.
- [x] Indentation and alignment fixes: none needed.
- [x] Line length correction: none needed (the `connect(...)` call was split to fit 100 characters).

## Code Cleanup

- Removed unused imports: 0 (Ruff F401 clean).
- Removed unused variables: 0.
- Dead code: none. A scripted AST scan of every top-level function, class, method and constant in `tests/browser_cdp.py`, `tests/browser_helpers.py` and `tests/conftest.py` found each name referenced beyond its definition (`pytest_runtest_makereport` is a pytest hook).
- Debug output: none (no `print`, `breakpoint`, `pdb`, TODO/FIXME in the scope).
- Commented-out code: none.
- Duplication: shared helpers live once in `tests/browser_helpers.py`; the three browser modules do not redefine them. No further extraction needed.
- Roadmap: the M7 count in the Step 4 sub-item corrected from 9 to 14 red.

## Validation Results

- [x] All tests passed: browser modules 53 passed (39 s, foreground, after the change); full suite `PYTHONDONTWRITEBYTECODE=1 make test`: 589 passed, 0 failed, 1 warning (third-party httpx/starlette deprecation), 496.97 s.
- [x] All tests have explicit timeout markers (grep `pytestmark`): `test_wishlist_cards_browser.py`, `test_wishlist_mouse_reorder_browser.py`, `test_wishlist_touch_reorder_browser.py` = `[pytest.mark.timeout(45), pytest.mark.browser]`; `test_wishlist_static_script.py`, `test_wishlist_touch_reorder.py`, `test_wish_items_list_reorder_ui.py`, `test_browser_prerequisites.py` = `timeout(30)`.
- [x] No merge conflicts.
- [x] Syntax is valid (`node --check`, mypy).
- [x] Types are correct (mypy).

## Notes

- Count reconciliation: 560 (HEAD e925c58) + 53 new browser tests - 25 removed string-check cases + 1 new guard test (`test_new_browser_modules_declare_marker_and_timeout`) = 589; `pytest --collect-only -q` reports 589 tests collected. The 25 is the net reduction in the three cleaned legacy modules (HEAD 5 + 11 + 37 = 53 collected cases, now 5 + 11 + 12 = 28), per the Step 5 review's measurement.
- Browser runtime: the three browser modules take about 39 s on their own; the whole suite took 497 s (about 8 min 17 s), in line with the 497 s of WISHENKA-109.
- Redundant production cancel paths (`pointercancel`, `htmx:beforeSwap` shadowed by `lostpointercapture`) remain a recorded test-isolation gap from Step 4, not changed here.
- No failures, so no triage or baseline worktree was needed. No stray chromium/uvicorn/pytest processes after the run (`ps` count 0). The untracked `core` file was left alone.
