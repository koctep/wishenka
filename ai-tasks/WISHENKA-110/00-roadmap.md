# Roadmap: WISHENKA-110

## Task Metadata

- **Implementation language**: Python (pytest) for the tests; code under test: JavaScript (`wishenka/web/static/wishlist.js`, no production-language change)

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-110/10-requirements.md` written (business requirements, scope, acceptance criteria)
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-110/20-architecture.md` written (own CDP driver `tests/browser_cdp.py` instead of Playwright; Fetch-interception offline stubs; per-test server+DB, shared Chromium; test catalogue, mutation plan, cleanup mapping)
- [x] **STEP 3: Failing Repro Test**
  - Structurally red tests written (53 tests, full real assertions): `tests/test_wishlist_cards_browser.py` (21), `tests/test_wishlist_mouse_reorder_browser.py` (13), `tests/test_wishlist_touch_reorder_browser.py` (19); each `pytestmark = [pytest.mark.timeout(45), pytest.mark.browser]`.
  - Stubs: `tests/browser_cdp.py` (`CdpPage`, `CdpBrowser`, `PageWaitTimeout`; behaviour methods and the `console`/`requests`/`external_requests` properties raise `NotImplementedError("<Class.method> not implemented")`; only the data containers `ConsoleEntry`, `ConsoleLog`, `RecordedRequest` are real); fixtures `seed_wishlist`, `wishlist_page`, `share_page` appended to `tests/conftest.py` (factories that raise `NotImplementedError` when called). htmx stub asset (`tests/browser_assets/htmx_stub.js`), server lifecycle, session Chromium and the failure-diagnostics hook are Step 4.
  - Real helper module (not in the architecture file list): `tests/browser_helpers.py` (`Seeded`, selectors, `assert_order`/`assert_cards`/`assert_gesture_clean`/..., `begin_touch_drag`, `wait_suppression_window_over`) to avoid triplicating helpers in the three modules.
  - Guard added: `tests/test_browser_prerequisites.py::test_new_browser_modules_declare_marker_and_timeout` (GREEN by design; AST check of every `tests/test_*_browser.py`: `browser` marker at module level or on every test, module `timeout(45)`; asserts the three new modules exist; existing assertions untouched; the older `test_wishlist_management_browser.py` passes it because its tests carry `@pytest.mark.browser`).
  - Red evidence (`.venv/bin/python -m pytest -p no:cacheprovider -q <3 new modules>`): `--collect-only` 53 tests, no collection errors; run: 53 failed, 0 passed, 0 errors, 0.20 s. All 53 failure lines are `E       NotImplementedError: seed_wishlist not implemented` (the first driver-side call in every test is the `seed_wishlist` factory stub, so the `CdpPage` stubs are not reached yet; Step 4 must expect first-call failures to move to the driver as fixtures land). Tests FAIL (not ERROR): factories only request `chromium_executable` at setup, so a missing Chromium would still error with the WISHENKA-124 message before any test body (here `/usr/bin/chromium` exists, so the red is not masked).
  - `make analyze`: ruff check, ruff format --check and mypy clean (it reinstalled the package).
  - Driver/fixture contract choices where the architecture was ambiguous (Step 4 must implement exactly these):
    - `TouchPoint = tuple[int, float, float]` (finger id, x, y); `touch_start(points)` called again with a longer list adds a finger; `touch_move(points)` lists every finger down; `touch_end()` ends all fingers and is a no-op when none is down (tests call it after cancel paths); `touch_cancel()` = `touchCancel`.
    - `press_key` keys: `Enter`, `Space` (`key=" "`, `text=" "`), `Escape`, `ArrowDown`, single letters. `wait_for(description, predicate_js, timeout=5.0)` returns the last truthy value. `mouse_drag(..., y_fraction=)`: 0.0 target top edge, 1.0 bottom edge. `drop_outside(source_selector, point)` with `point=(x, y)` viewport CSS px (tests use `(1.0, 1.0)`; it also serves as the "dragend without drop" path).
    - `console` is a `list[ConsoleEntry]` subclass (`.type`: `"warning"` for `console.warn`, `"error"`, `"exception"` for uncaught; `.text`) with `.warnings()`; `requests` items are `RecordedRequest(method, url, post_data, status)` with `.path` (status filled from the response); `external_requests` is `list[str]`; `ajax_calls()` dicts have keys `verb`, `url`, `target`, `swap`, `values`; `card_state()` returns `{"expanded": "true"|"false"|None, "hidden": bool}`; `order()`/`Seeded.item_ids` are strings.
    - Fixtures are factories: `seed_wishlist(titles, *, quantities=None) -> Seeded(wishlist_id, public_token, item_ids, owner_token, viewer_token)`; `wishlist_page(seeded, *, as_user="owner"|"viewer", viewport=(412, 800))`; `share_page(seeded, *, as_user=None|"viewer", viewport=(412, 800))`; touch is enabled in tests via `page.enable_touch()`. The "no console problems" guard from the architecture is implemented as explicit `assert_clean_console(page)` calls in tests, not as an autouse fixture (no new pytest marker needed under `--strict-markers`).
    - htmx stub contract used by tests: `window.__ajaxCalls`, `window.__ajaxPending` (0 when idle), real forwarding of `htmx.ajax` to the server, `htmx:beforeSwap` (with `detail.target`) fired before the `innerHTML` swap.
  - Reviewer notes honoured: (1) `test_toggle_works_after_htmx_swap` and the `htmx:beforeSwap` cancel case call `window.htmx.ajax('POST', '.../items/<id>/move?direction=down', {target: '#items-list', swap: 'innerHTML'})` explicitly because the offline stub does not process `hx-*` (stated in the docstring/comment); (2) criterion 4 asserts the real `TOGGLE_EXCLUSION` set (`a, button, input, select, textarea, [data-no-toggle]`: handle, giver text, select, reserve button, synthetic link/input/textarea) with a comment that `label` is not in the set and is not asserted; (3) interface as stated, choices recorded above.
  - Deviations to note: in the `htmx:beforeSwap` cancel case the expected DOM order after the swap is the server order after the real `move` (`[b, a, c]`), not the original, because the stub really swaps the list; the assertion remains "no `/items/reorder` request, gesture state clean". `test_vertical_swipe_outside_handle_scrolls_not_reorders` asserts `scrollY > 0` strongly; Step 4 may weaken it only with a recorded reason (architecture, p. 17).
- [x] **STEP 4: Development**
  - [x] Driver `tests/browser_cdp.py` implemented (`CdpBrowser`, `CdpPage`; single-reader event pump on `websockets.sync`, no threads; `Fetch.enable` offline interception of the three `base.html` URLs, other external URLs blocked into `external_requests`, local requests recorded with status via `Network.responseReceived`; Bearer via `Network.setExtraHTTPHeaders`; console via `Runtime.consoleAPICalled`/`exceptionThrown`; native HTML5 DnD via `Input.setInterceptDrags`/`dragIntercepted`/`dispatchDragEvent` (the synthetic `DragEvent` fallback was NOT needed); touch incl. multi-finger via `touchPoints`; bounded `wait_for`). `CdpBrowser.new_page(viewport=...)` has an extra optional argument.
  - [x] `tests/browser_assets/htmx_stub.js` (own code, `window.htmx = ...` configurable/deletable, `__ajaxCalls`, `__ajaxPending`, `htmx:beforeSwap` with `detail.target` before the `innerHTML` swap, `htmx:afterSwap` after); `node --check` OK.
  - [x] Fixtures in `tests/conftest.py`: session `chromium_browser` (temp profile, terminate/wait(5)/kill), session `migrated_db_template` (migrations run once in `TestClient`, engines disposed on lifespan end, no `-wal` left; only the `.db` is copied), per-test `wishlist_server` (uvicorn.Server in a daemon thread on 127.0.0.1:random, bounded stop in `finally`), `seed_wishlist` (REST via httpx; the wishlist-create response key is `share_token`), `wishlist_page`/`share_page` factories, `_browser_pages` teardown (closes tabs; writes `diagnostics-N.txt` and `failure-N.png` into `tmp_path` on failure), `pytest_runtest_makereport` hook appends the page snapshot to the failure report.
  - [x] Result: 53/53 browser tests green; with the legacy touched modules and the guard 129 passed (`test_wishlist_cards/mouse_reorder/touch_reorder_browser.py`, `test_browser_prerequisites.py`, `test_wishlist_management_browser.py`, `test_wishlist_static_script.py`, `test_wishlist_touch_reorder.py`, `test_wish_items_list_reorder_ui.py`). `make analyze` clean (ruff, format, mypy 103 files). `git diff --exit-code -- wishenka/` empty (production untouched).
  - [x] Step-4 verification items from the architecture (all confirmed empirically): synthesized touch swipe DOES scroll in headless Chromium, so the `scrollY > 0` assertion stays strong (NOT weakened); `touchCancel` produces `pointercancel`; a second finger via a second `touchStart` with both `touchPoints` works; touch tap produces `click`; no assertion weakened anywhere.
  - [x] Driver findings worth knowing (documented in code comments): (1) touch events sent with no pause give a huge release velocity; Chromium then starts a fling and swallows the NEXT tap (`test_next_tap_after_suppression_window_toggles[drop]` failed for >1.2 s after the gesture). Fix: `touch_move` pumps 16 ms after each move and `touch_end` rests 60 ms before `touchEnd`. (2) Chromium dispatches `lostpointercapture` after `releasePointerCapture` only together with the next pointer event; `wait_for` therefore sends a sub-pixel (0.01 px) `touchMove` for fingers that are down on every unsuccessful poll (a resting real finger also reports). (3) `Input.dragIntercepted` was received every time; native DnD gave 10/10 stable runs.
  - [x] STABILITY (one-time, not a CI gate): the three modules run 10 consecutive times, foreground: 10/10 `53 passed`, 0 failures, 0 flaky; wall time per run (pytest-reported) 37.9, 37.4, 38.0, 38.9, 39.2, 39.6, 37.2, 35.2, 35.2, 34.9 s (mean about 37.3 s). No stray Chromium/uvicorn processes after the runs (`ps` count 0).
  - [x] RUNTIME vs requirement 25 (about 60 s): three browser modules about 35-40 s, inside the target. Whole set above (129 tests incl. legacy and the older browser test) 97.8 s (the legacy `test_wishlist_*` modules each build their own app).
  - [x] MUTATION PROOF (criterion 27), `wishlist.js` temporarily edited by a one-mutation script with `git checkout --` in `finally`; failures were assertion errors (a `PageWaitTimeout`, which is an `AssertionError`, only for the lostpointercapture waits):
    - M1 midpoint `>` -> `<`: 12 red (all 4 `test_mouse_drop_before_or_after...`, `..._one_request_with_full_order`, `drop_on_self_or_outside[self,outside]`, `test_repeated_reorder...`, 3x `test_touch_drag_handle_reorders`, `test_handle_and_feedback_computed_styles`).
    - M2 ids collected before `insertBefore`: 11 red (4 midpoint, one_request_with_full_order, drop_on_self_or_outside x2, repeated, 3x touch_drag_handle_reorders).
    - M3 `TOGGLE_EXCLUSION` early return removed: 8 red (all 7 `test_nested_controls_do_not_toggle` cases, `test_tap_on_summary_toggles_tap_on_handle_does_nothing`).
    - M4a Escape listener disabled: 2 red (`cancel_paths[escape]`, `escape_cancels...[active]`).
    - M4b `pointercancel` listener removed: SURVIVED (19 passed). Reason: after `touchCancel` the browser also fires `lostpointercapture`, whose listener runs the same `cancelTouchDrag`; the code has two independent cancel paths, so removing one is behaviourally equivalent. Combined M4c (`pointercancel` + `lostpointercapture` removed): 5 red (`cancel_paths[pointercancel]`, `[lostpointercapture]`, `expanded_card_stays_expanded_after_cancelled_touch_drag`, `next_tap...[cancel]`, `handle_and_feedback`), so the `pointercancel` test does detect loss of cancel handling. Gap noted: no test can isolate `pointercancel` alone.
    - M5 second `submitReorder` in `pointerup`: 4 red (3x `touch_drag_handle_reorders`, `test_one_request_per_gesture`). The mouse path was not mutated (M5 targets `pointerup` only).
    - M6 `console.warn` removed: 3 red (all `test_reorder_skipped_with_exactly_one_warning`).
    - Extra: M7 `details.hidden = !expanded`: 14 red; M8 keydown `preventDefault` removed: 1 red (`space_default_prevented`); M9 `lostpointercapture` removed: 1 red (`cancel_paths[lostpointercapture]`); M10a `visibilitychange` removed: 1 red (`[visibilitychange]`); M10b `blur` removed: 1 red (`[blur]`); M12 `target === dragged` removed: 2 red (`drop_on_self[self]`, `repeated`); M13 suppression flag not cleared by the timer: 2 red (`next_tap...[drop]`, `[cancel]`); M14 second finger no longer cancels: 1 red (`second_finger...`).
    - M11 `htmx:beforeSwap` listener removed: SURVIVED (19 passed). Same reason: the swap removes the dragged card/handle, the browser loses the capture, and `lostpointercapture` cancels the gesture. Combined M11b (`beforeSwap` + `lostpointercapture` removed): 2 red (`[htmx-beforeSwap]`, `[lostpointercapture]`). Reported as a test-isolation gap (redundant production cancel paths), not blocking per architecture (M7-M14 optional).
    - After the last mutation: `git diff --exit-code -- wishenka/` empty.
  - [x] CLEANUP mapping (criteria 28/29), done only after the replacing browser tests were green (old -> new):
    - `test_wishlist_static_script.py::test_static_wishlist_script_content`: markers `toggleWishCard`, exclusion selector, `'Enter'`, `' '`, `.item-card-summary`, `dragstart/dragover/drop/dragend`, `/items/reorder`, `wishlistId`/`data-wishlist-id`, `location.pathname`/`window.location` removed -> `test_click_toggles_card_both_ways`, `test_enter_and_space_toggle`, `test_nested_controls_do_not_toggle`, mouse reorder tests, `test_reorder_uses_data_wishlist_id_not_location`; kept: 200 + `javascript` content-type; unused constant `EXCLUSION_SELECTOR` removed.
    - `test_wishlist_touch_reorder.py`: `test_wishlist_script_contains_token` (23 params) reduced to `test_wishlist_script_contains_sdk_token` (4 SDK params: `disableVerticalSwipes`, `enableVerticalSwipes`, `isVersionAtLeast`, `HapticFeedback`; 19 gesture tokens removed -> touch browser tests); `test_css_drag_handle_declares_touch_rules` reduced to `-webkit-touch-callout: none` (`touch-action`, `user-select`, `min-width: 44px` -> `test_handle_and_feedback_computed_styles`); `test_css_has_drag_feedback_rule` (3 params) removed with helper `css_has_rule_for` -> computed `opacity`/`boxShadow` + classes in `test_touch_drag_handle_reorders`; kept: `test_css_summary_does_not_block_touch_scroll`, `test_wishlist_script_has_single_reorder_submit_point`, other markup tests.
    - `test_wish_items_list_reorder_ui.py`: `assert "onclick" not in html` removed (stronger `test_cards_have_no_inline_event_handlers` stays) and `"toggleWishCard" in static_js.text` removed (-> `test_click_toggles_card_both_ways`); the 200 status check on `/static/wishlist.js` stays.
    - Counts: removed 19 + 3 + 3 + 1 parametrized/plain weak checks (about 26 test cases, 1 assertion pair in the UI test, plus the content-test markers); 53 browser tests added.
  - [x] Reported to Step 5/8: `label` is not in `TOGGLE_EXCLUSION` (requirement wording lists labels; not asserted, see `test_nested_controls_do_not_toggle` comment); `pyproject.toml` marker text ("drive a real Chromium over CDP") stays valid, no change made; the CSRF path is not exercised (Bearer auth), the htmx stub does not process `hx-*`; docs (`doc/dev/testing.md`, `miniapp.md`) are Step 8.
  - Not done / for the gate owner: the final `[x]` for STEP 4 (agent leaves `[/]`).
  - Step 3 review fixes for Step 4 to honour: (a) the htmx stub must define `window.htmx` as a configurable/deletable property (`window.htmx = ...`, not `var`) so the "htmx missing" skip case can delete it; (b) the `htmx:beforeSwap` cancel test calls `htmx.ajax` with `?direction=down` (the architecture text says otherwise; the test form is authoritative); (c) touch tests re-aim the finger (`retarget_touch_drag`) after activation because an expanded dragged card collapses and shifts the layout; (d) the vertical-swipe test starts on `title(ids[0])`, checked with `elementFromPoint`.
- [x] **STEP 5: Code Cleanup**
- [x] **STEP 6: Observability**
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-110/60-tech-debt.md` written: no BLOCKER; 4 proposed NEW Debt issues (CDP client consolidation, CI failure artifacts, real-htmx smoke, websockets pin) and notes on WISHENKA-143, 135, 137, 138, 141, 144; all test modules have explicit timeout markers
- [x] **STEP 8: Dev Docs**
  - `doc/dev/testing.md`: new section "Browser UI-тесты списка желаний (WISHENKA-110)" (coverage of the three modules, helper/driver/fixture layout, run commands, offline design, fidelity limits, failure diagnostics, timeout/marker convention and guard, stability result, mutation proof with survivors M4b/M11, CDP-vs-Playwright decision with revisit triggers, troubleshooting); Overview and "Известные ограничения" updated (WISHENKA-145/146/147).
  - `doc/dev/miniapp.md` §9.8.1: Tests bullet rewritten to the delivered state; Related debts extended with WISHENKA-145/146/147.
  - `doc/dev/infrastructure.md` §7.2: one sentence about the added ~40 s of browser tests.
  - Grep of `doc/`, `in-docs/`, `specs/`, `README.md` for stale statements: only the miniapp.md Tests bullet was stale.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-110/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-110/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-110/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-110/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-110/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
