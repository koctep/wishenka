# WISHENKA-110: Technical Debt Analysis

Scope: `tests/browser_cdp.py` (671 lines), `tests/browser_helpers.py` (242), `tests/browser_assets/htmx_stub.js`
(69), the browser fixtures appended to `tests/conftest.py`, `tests/test_wishlist_cards_browser.py` (21 tests),
`tests/test_wishlist_mouse_reorder_browser.py` (13), `tests/test_wishlist_touch_reorder_browser.py` (19), the
guard `test_new_browser_modules_declare_marker_and_timeout` in `tests/test_browser_prerequisites.py:504-531`,
and the cleaned legacy modules (`test_wishlist_static_script.py`, `test_wishlist_touch_reorder.py`,
`test_wish_items_list_reorder_ui.py`). Compared against `10-requirements.md`, `20-architecture.md`, the
Step 4 record in `00-roadmap.md` and the sibling debt files of this sprint
(`ai-tasks/WISHENKA-124`, `-108`, `-109`). No production code changed (`git status`: only `tests/` and
`ai-tasks/` are touched; `wishenka/` is clean).

Timeout markers (grep `pytestmark` / `timeout` over every test module touched):

- `test_wishlist_cards_browser.py:27`, `test_wishlist_mouse_reorder_browser.py:29`,
  `test_wishlist_touch_reorder_browser.py:42`: `pytestmark = [pytest.mark.timeout(45), pytest.mark.browser]`.
- `test_wishlist_static_script.py:28`, `test_wishlist_touch_reorder.py:37`, `test_wish_items_list_reorder_ui.py:30`,
  `test_browser_prerequisites.py:29`: `pytest.mark.timeout(30)`.
- `browser_cdp.py`, `browser_helpers.py` and `conftest.py` contain no test items (helpers and fixtures), so no
  marker is required there.

No test module of the task lacks an explicit timeout marker. No timeout-marker BLOCKER.

Pre-existing failures: none (full suite 589 passed, per the task brief; not re-run in this step because no
code changed). The untracked `core` file in the repository root (`ls -l core`: 197,693,440 bytes, Nov 12 07:09)
is already ticketed as WISHENKA-126 and is not duplicated. For `td-99-commit`: stage by explicit path so `core`
is never added (also `ai-tasks/sprint-2109/` is untracked and not part of this task).

Blockers: none. Every follow-up below is NON-BLOCKER.

## Shortcuts Taken

- **Real htmx is replaced by an own stub; the committed tests never run real htmx.** `tests/browser_assets/htmx_stub.js`
  implements only `htmx.ajax(verb, url, {target, swap, values})` and always does an `innerHTML` swap
  (`target.innerHTML = html`, line near the end of `ajax`) whatever `swap` says (the value is only recorded in
  `__ajaxCalls`). It does not process `hx-*` attributes, does not run `htmx:configRequest` (so the CSRF header
  logic of `base.html` is not exercised), no `outerHTML` / `beforeend` swaps, no extensions (`json-enc` is served as
  an empty body, `browser_cdp.py:112`). The header comment says so. Consequence: `test_toggle_works_after_htmx_swap`
  and the `htmx:beforeSwap` cancel case call `window.htmx.ajax(...)` explicitly instead of clicking a move button
  (reviewer note, recorded in the roadmap). Wiring bugs such as a wrong `hx-post`/`hx-target` on the move buttons,
  or a change of htmx event semantics in a future htmx upgrade (which the requirements name as a motivating change),
  would not be caught here. This is the designed trade-off for criterion 22 (no network). Follow-up 3.
- **Authentication is Bearer, not the cookie/CSRF flow.** `Network.setExtraHTTPHeaders` sets the Bearer token for
  every request of the tab (`browser_cdp.py`, `setup`), and the `seed_wishlist` factory talks to the REST API with
  httpx and the same tokens (`tests/conftest.py:152-185`). The cookie session, CSRF token injection and the
  `hx-headers` path used by real users are not exercised. Part of follow-up 3.
- **Surviving mutations M4b and M11 (redundant production cancel paths).** Recorded in Step 4: removing the
  `pointercancel` listener (`wishlist.js:488`) or the `htmx:beforeSwap` listener (`:520`) alone leaves all 19 touch
  tests green, because the browser also delivers `lostpointercapture` (`:494`), and that listener runs the same
  `cancelTouchDrag`. Combined mutants M4c (`pointercancel` + `lostpointercapture`) and M11b (`beforeSwap` +
  `lostpointercapture`) are caught (5 and 2 red), so the tests do detect the loss of cancel handling as a whole, but no
  test can isolate either listener. This is a property of the production code (two independent paths to one
  outcome), not something a better test can fix without a test hook in `wishlist.js`. Accepted, no new issue; a
  note goes to WISHENKA-144 (when the file is tidied, decide whether the redundancy is intentional and comment
  it). The mouse path was not mutated for M5 (only `pointerup` was) and M7-M14 were optional extras.
- **Criterion 19 is out of scope by requirement:** autoscroll at the edges (`AUTOSCROLL_*`), the Telegram SDK stub call
  order (disable, impact, selection, enable) and degradation when the SDK is absent or old, the `warnSdk` branch, and
  the real Telegram WebView. None of it is tested in a browser. Real-device verification is WISHENKA-143 (already
  holds the autoscroll and SDK questions from the 109 analysis); the automated autoscroll/SDK-order tests that the
  CDP driver could now host are recorded as a note there, not duplicated.
- **`label` is not in `TOGGLE_EXCLUSION`** (`wishlist.js:13`: `a, button, input, select, textarea, [data-no-toggle]`),
  while the requirement text (criterion 4, "метки") mentions labels. `test_nested_controls_do_not_toggle` asserts the
  real set and carries a comment that `label` is not asserted. Not a test defect and not a production bug as such
  (no `<label>` exists inside the card templates as far as the tests seed them; not re-verified across all
  partials in this step). This is a note for product/requirements: either remove "метки" from the criterion text or
  add `label` to the set together with a test case. No ticket.
- **The mirror constant `CLICK_SUPPRESS_MS = 400` is duplicated in the tests** (`browser_helpers.py:16-19`, with a
  50 ms margin `CLICK_SUPPRESS_MARGIN_MS`; the production constant is private to `wishlist.js:20`). Drift is
  detected in one direction only: if production grows the window, `test_next_tap_after_suppression_window_toggles`
  fails (the next tap is swallowed); if production shrinks it, the tests just wait longer and stay green. Low risk;
  the wait itself is bounded and clock-based (`wait_suppression_window_over` polls `performance.now()`, 3 s limit,
  `browser_helpers.py:238-242`), not a blind sleep.
- **The three external URLs are duplicated in the driver** (`browser_cdp.py:33-35`: htmx 1.9.12, json-enc, Telegram)
  and must equal `base.html:8-10`. If the template changes a URL, interception no longer matches, the real URL is
  blocked into `external_requests`, and the tests fail loudly with a snapshot (not silent). Acceptable; a future
  htmx upgrade needs a one-line change in two places. Included in follow-up 3.
- **`wait_for` sends sub-pixel `touchMove` events for every finger that is down on each unsuccessful poll**
  (`browser_cdp.py:318-330`, `_hold_fingers`, 0.01 px alternating shift). Reason documented: Chromium delivers
  `lostpointercapture` only together with the next pointer event. Side effect: a "finger stays still" wait is not
  perfectly still, and a future test that wants to assert "no pointer events during a wait" would be misled. Not
  an issue for the current 19 tests (stable 10/10), recorded because it hides in a generic helper.
- **The guard is named and scoped for the new modules.** `test_new_browser_modules_declare_marker_and_timeout`
  (`test_browser_prerequisites.py:504-531`) globs `test_*_browser.py`, so `tests/test_wishlist_sections_ui.py` (a
  browser test with timeout 60, per WISHENKA-124) is not covered, and the name says "new" although it checks all
  matching modules. It also requires these three module names to exist (`NEW_BROWSER_MODULES`; `missing = NEW_BROWSER_MODULES - found`),
  which makes the guard fail if one of them is renamed or merged. Overlaps WISHENKA-137 ("tighten the marker declaration check");
  note there.

## Code Quality Issues

- **Three independent hand-rolled CDP clients now exist.** `tests/browser_cdp.py` (the new `CdpBrowser`/`CdpPage`,
  671 lines) next to the older inline clients in `tests/test_wishlist_management_browser.py:61-121` and
  `tests/test_wishlist_sections_ui.py` (`ws.recv(timeout=15)` helpers, `connect(...)` setup, its own uvicorn thread
  and Chromium launch). WISHENKA-124 recorded this duplication as an explicit decision ("общий CDP-код остаётся
  дублированным") without a ticket. Now that a reusable, bounded driver and a per-test server fixture exist, the
  older modules can be migrated (and their private process/thread handling dropped). Not done here because it widens
  the task and the older tests are green. NEW Debt, follow-up 1.
- **`tests/browser_cdp.py` is large (671 lines) and mixes concerns**: browser process lifecycle, CDP transport/event
  pump, Fetch interception, touch/mouse/drag input and the snapshot formatter in one module. Readable and documented,
  with bounded waits everywhere, but a split (transport, input, snapshot) would be natural if the driver grows.
  Only worth doing together with follow-up 1. No separate issue.
- **Duplicate failure diagnostics.** On a failed call phase the snapshot is appended to the pytest report
  (`tests/conftest.py:53-63`, `pytest_runtest_makereport`) and the same snapshot is written again to
  `diagnostics-N.txt` at teardown (`conftest.py:196-199`), plus `failure-N.png` (`:200-202`). The two paths are
  intentional (report for the log, files for artifacts) but the same text is produced twice, and the file paths
  are not printed anywhere (the files land in `tmp_path`, which pytest prints only for `--basetemp`-less default
  runs under `/tmp/pytest-of-<user>/`). Follow-up 2.
- **`legacy=True` for `websockets.sync.client.connect`** (`browser_cdp.py:644-650`). The installed `websockets` 17.4
  warns when `connect()` is not used as a context manager ("deprecated in 17.1", `sync/client.py:95-103`) and
  names `legacy=True` as the way to connect directly. The code uses the escape hatch, so it works today and emits
  no warning, but `legacy` is by its name a compatibility flag and may be removed in a future major version.
  Also, `pyproject.toml:35` declares `websockets>=13.0` (no upper bound), while the flag exists only in releases
  with the 17.1 deprecation (inferred from the 17.x source; I could not install an older version in this step to
  confirm, so confirm before changing the pin). With `>=13.0` an environment that resolves to an older
  `websockets` would fail with a `TypeError` (the extra keyword goes to the socket layer) instead of a clear
  message. The older modules use the context-manager form (`test_wishlist_management_browser.py:121`). Follow-up 4:
  set a consistent range (for example `>=17.1,<18`) or make the driver version-independent.
- **`CdpBrowser.new_page(viewport=...)` has an extra optional argument** and fixtures pass the default `(412, 800)`
  through three factories; the signature is repeated rather than centralised (`conftest.py:224-256`,
  `browser_cdp.py:641`). Cosmetic.
- **Helper module `browser_helpers.py` is not in the architecture file list** (added at Step 3 to avoid triplicating
  helpers). Recorded in the roadmap; no problem.
- **No session fixture asserts that Chromium stays alive between tests.** If Chromium crashes mid-session, all
  following tests fail at `new_page` with a connection error, which is clear enough but not specific. Low value.

## Missing Tests

- **Real htmx path, CSRF and `hx-*`:** see Shortcuts; not covered by any committed test. The only real-htmx run is the
  throwaway Step 4 check of WISHENKA-109. Follow-up 3.
- **Autoscroll, Telegram SDK order and degradation, `warnSdk`:** criterion 19, out of scope; note on WISHENKA-143.
- **M4b and M11 isolation:** see Shortcuts; accepted.
- **No dedicated test for the `touch` mouse/pen boundary** (`pointerType !== 'touch'` returns at
  `wishlist.js:416-418`, documented in 109). Out of the 110 criteria; no action.
- **Layout-jump UX when an expanded card is dragged** is only worked around in the tests (`retarget_touch_drag`
  re-aims the finger after the dragged card collapses, `browser_helpers.py:220-235`), not asserted. The UX
  decision belongs to WISHENKA-142; the retarget helper will need review if 142 changes the layout.
- **No test of the first-failure `sdkWarned` behaviour, of the `visibilitychange` event on a really hidden tab**:
  the tests dispatch synthetic window events (`WindowEventKind = Literal["blur", "visibilitychange"]`,
  `browser_cdp.py:46`) rather than hiding the tab. Fidelity limit: the production listener is exercised, the
  browser's own event generation is not.
- **Touch is synthesized, not real.** `Input.dispatchTouchEvent` through headless Chromium with
  `Emulation.setTouchEmulationEnabled`; Step 4 verified that a synthetic swipe scrolls (`scrollY > 0` stays strong),
  `touchCancel` gives `pointercancel` and a second finger works. Real-device behaviour is WISHENKA-143.
- **No coverage for the deleted string checks beyond the browser tests.** What remains of the string checks is
  deliberate: `test_wishlist_script_contains_sdk_token` (4 SDK tokens: `disableVerticalSwipes`,
  `enableVerticalSwipes`, `isVersionAtLeast`, `HapticFeedback`, which the browser tests cannot see because the SDK stub
  is empty), `-webkit-touch-callout: none`, `test_css_summary_does_not_block_touch_scroll`,
  `test_wishlist_script_has_single_reorder_submit_point`, the markup tests, the 200 and `javascript` content-type
  check for `/static/wishlist.js`, and `test_cards_have_no_inline_event_handlers`. These still pass on a comment
  and are the kept CSS/SDK guards; they stay until WISHENKA-143 or an SDK-stub test replaces them. The weakened
  or removed checks all map to a named browser test (mapping in the roadmap Step 4 "CLEANUP mapping").

## Performance Concerns

- **Runtime.** The three new modules take about 35-40 s for 53 tests (10 consecutive runs 34.9-39.6 s, mean about
  37.3 s, recorded at Step 4), inside the soft target of about 60 s (criterion 25). The full suite takes 8m17s
  (589 passed). The browser share is about 8 percent of the suite; the larger cost is the older legacy
  modules that each build their own app, as the Step 4 note says (129-test subset 97.8 s).
- **A server and a database copy are started for every test.** `wishlist_server` (`conftest.py:113-149`) starts a
  uvicorn thread and copies `template.db` (migrations run once per session in `migrated_db_template`). This was the
  requirement (criterion 20: own DB and data per test) and costs roughly 0.1-0.3 s per test (not measured
  separately). The shared session Chromium and a tab per test avoid the dominant start-up cost. No action unless the
  count of browser tests grows several times over; then consider a server per module with a per-test wishlist.
- **Driver pacing is deliberate and adds fixed time to every gesture:** `TOUCH_MOVE_INTERVAL = 0.016` after each
  `touchMove` and `TOUCH_REST_BEFORE_END = 0.06` before `touchEnd` (`browser_cdp.py:41-42`, `:456`, `:465`);
  `_pump(0.02)` after clicks/keys/mouse steps (`:255-280`, `:419`), `POLL_STEP = 0.025`. The values come from a
  finding: without the pauses Chromium sees a huge release velocity, starts a fling and swallows the next tap for over
  1.2 s. They are not tuned by measurement and not environment-adaptive. On a slow CI runner the fling heuristic may
  differ; see flakiness.
- **`wait_for` default limit is 5 s per wait, driver command timeout 10 s (`COMMAND_TIMEOUT`), page load 10 s
  (`LOAD_TIMEOUT`), drag intercept 3 s, per-test marker 45 s.** Several chained waits that each approach their own
  limit can exceed 45 s, in which case pytest-timeout fires before the specific message appears; a test that fails
  slowly loses its `PageWaitTimeout` diagnostics. Same family as WISHENKA-138 (probe budget vs the 45 s marker);
  note there.

## Hardcoded Values

- Viewport `412x800` is repeated as a default in three places (`conftest.py:235,255`, `browser_cdp.py:641`). It is a
  phone-sized default and tests that need other sizes pass it explicitly. One constant would do (cosmetic).
- Driver constants named at the top of `browser_cdp.py:37-42`: `COMMAND_TIMEOUT 10`, `LOAD_TIMEOUT 10`,
  `DRAG_INTERCEPT_TIMEOUT 3`, `POLL_STEP 0.025`, `TOUCH_MOVE_INTERVAL 0.016`, `TOUCH_REST_BEFORE_END 0.06`; in
  `conftest.py`: `SERVER_START_TIMEOUT`, `SERVER_STOP_TIMEOUT`, `chromium.wait(5)`, `httpx timeout=10`; module marker 45 s
  (requirement 25). `CLICK_SUPPRESS_MS = 400` plus 50 ms margin mirror production (see Shortcuts). `wait_for`
  limits `5.0` / `3.0` per call site. No retries exist: `grep` for retry loops in the driver, fixtures, helpers and the
  three modules found none (the only loops are the bounded polls). That is intended (a retry would hide flakiness).
- The `2000`-character cut of `#items-list` HTML and the "last 20" cut of console and requests in
  `snapshot()` (`browser_cdp.py:561-567`): enough for 3-5 seeded cards, not for large lists. Fine for the current
  tests.
- The seeded identifiers, titles and tokens (`OWNER_TELEGRAM_ID`, `VIEWER_TELEGRAM_ID`, `BROWSER_TEST_SECRET`) are
  test constants; no production secret is used.
- External URLs duplicated from `base.html` (see Shortcuts).

## Flakiness Risks

- **Shared browser context.** All tabs live in Chromium's single default browser context (no
  `Target.createBrowserContext`), so cookies, localStorage and the HTTP cache are shared between tests.
  Origins stay separate only because each test's server uses a random port, and tabs are closed per test, so the
  risk is low; no ticket needed.
- **Headless Chromium, synthesized touch.** 10/10 stable on the dev box (Chromium 156, Debian 13, Python 3.13);
  not run on CI yet. CI uses `ubuntu-latest` and Python 3.12 (`.github/workflows`, `python-version: "3.12"`): the browser
  name that `make deps-browser` resolves there is unverified (WISHENKA-135), and the first CI run may show a
  different fling/scroll behaviour in headless mode, especially `test_vertical_swipe_outside_handle_scrolls_not_reorders`
  (asserts `scrollY > 0` after a synthesized swipe), the fling-sensitive `next_tap` tests, and the
  `lostpointercapture` waits that depend on the `_hold_fingers` workaround. Record the first CI result as a note on
  WISHENKA-135.
- **Timing windows:** the 400 ms suppression wait uses the page clock plus 50 ms; on a loaded runner the page clock
  keeps advancing so the wait does not lengthen the test but a very slow runner could still fall inside the
  window between the clock check and the tap. The 45 s per-test limit is generous (tests take about 0.7 s each).
- **Chromium version drift:** the system browser is not pinned (`/usr/bin/chromium` on the dev box). A new
  Chromium could change touch/DnD synthesis (`Input.setInterceptDrags` is marked experimental in CDP). Mitigation
  is the failing-diagnostics output; no pin exists.
- **Process cleanup is bounded** (terminate, `wait(5)`, kill; server `join` with an assertion) and Step 4 saw zero stray
  processes after 10 runs. A killed pytest worker (SIGKILL) would leave Chromium with the temp profile; same as the
  older browser modules.

## Test Diagnostics Gaps

- **No CI artifact upload.** Failure screenshots `failure-N.png` and `diagnostics-N.txt` are written into pytest's
  `tmp_path` (`conftest.py:196-202`) but CI does not upload them, and the default `tmp_path` base is not fixed, so the
  files are lost with the runner. The snapshot text is in the CI log through the report section, which is enough to
  diagnose most failures, but the screenshot is not. Fix: run pytest with a fixed `--basetemp` (for example
  `.pytest-tmp`, git-ignored) and add an `actions/upload-artifact` step with `if: failure()` over
  `.pytest-tmp/**/failure-*.png` and `diagnostics-*.txt`; also print the written paths in the report section.
  Reduce duplicate snapshot noise at the same time (emit the full text only once, point to the file from the report).
  NEW Debt, follow-up 2. The CI file currently has one job with `make check`, so the change touches `.github/workflows`
  and the Makefile pytest invocation.
- **Paths of the diagnostic files are not printed** (see above).
- **Skipped/slow-failure diagnostics:** see the `wait_for` versus marker note in Performance.

## Deviations from Architecture

Checked against `20-architecture.md` and the code:

- Implemented as designed: own CDP driver on `websockets.sync` with a single reader and no threads, Fetch interception
  of the three `base.html` URLs, per-test server and database, shared session Chromium, `seed_wishlist` /
  `wishlist_page` / `share_page` factories, mutation proof, cleanup mapping, 10-run stability check, three browser
  modules with `timeout(45)` and `browser`.
- Deviation 1 (accepted, documented): Playwright is not used although the Jira title says "Playwright". The decision and
  its reasons are in `20-architecture.md` (section (a), "Решение: свой драйвер `CdpPage`", Q&A). Revisit trigger
  from the architecture: the number of scenarios grows enough that auto-wait and locators pay for the dependency
  (~53 MB wheel, greenlet, a browser-version pairing outside Playwright's guarantee with a system Chromium). Proposed
  concrete revisit triggers for the record: more than about 100 browser tests or a second page type that needs
  real htmx navigation; a third driver feature that Playwright gives for free (tracing, video, network
  mocking); or `websockets` removing `legacy`. Maintenance risk of a hand-rolled driver is real (671 lines, an
  experimental CDP method for drag interception, workarounds for Chromium's fling and `lostpointercapture`
  timing); it is documented in the code comments. No ticket; follow-up 4 and the revisit triggers are recorded
  here.
- Deviation 2 (accepted, recorded at Step 3): `tests/browser_helpers.py` is not in the architecture file list.
- Deviation 3 (accepted): the "no console problems" guard is an explicit `assert_clean_console(page)` call per test,
  not an autouse fixture (a new marker would be needed under `--strict-markers`).
- Deviation 4 (accepted): in the `htmx:beforeSwap` cancel case the expected order after the swap is the server order
  after the real `move` (`[b, a, c]`), not the original, because the stub really swaps the list.
- Deviation 5 (accepted): the `htmx:beforeSwap` cancel test calls `htmx.ajax(... ?direction=down ...)` explicitly
  because the stub does not process `hx-*` (the test form is authoritative, the architecture text said otherwise).
- Deviation 6 (accepted): the `Input.setInterceptDrags` path was enough, the synthetic `DragEvent` fallback of
  the architecture was not needed (10/10 stable).
- No assertion was weakened: `scrollY > 0` stays strong; the legacy string checks were reduced only after the browser
  tests replacing them were green.

## Follow-up Tasks

There are no BLOCKER items. Every item below is NON-BLOCKER; none prevents Step 8, the commit, or closing
WISHENKA-110. Jira handling is proposed here; Phase D adds the links.

1. **NON-BLOCKER, NEW Jira Debt issue (about 3 SP):** migrate the older browser modules to the shared driver and
   Jira: [WISHENKA-146](https://pypost.atlassian.net/browse/WISHENKA-146)
   fixtures: `tests/test_wishlist_management_browser.py` (CDP helpers at `:61`, `:121`, own uvicorn thread and Chromium
   launch) and `tests/test_wishlist_sections_ui.py` (`:337`, `:431`) onto `CdpBrowser`/`CdpPage`, `wishlist_server`
   and the session `chromium_browser`; delete the duplicated `send_command`/`wait_for_load`/server code. Replaces the
   unticketed "CDP duplication remains" note in WISHENKA-124 (not a duplicate of any existing issue: 135-138 cover
   CI, apt, probe and markers, not driver reuse). While there, widen the marker guard to those modules (see
   WISHENKA-137 note).
2. **NON-BLOCKER, NEW Jira Debt issue (1 to 2 SP):** failure diagnostics in CI: fixed pytest `--basetemp`, an
   Jira: [WISHENKA-147](https://pypost.atlassian.net/browse/WISHENKA-147)
   `actions/upload-artifact` step with `if: failure()` for `failure-N.png` and `diagnostics-N.txt`, print the file
   paths in the failure report, and stop emitting the same snapshot twice (report section vs `diagnostics-N.txt`,
   `conftest.py:53-63` and `:196-202`).
3. **NON-BLOCKER, NEW Jira Debt issue (about 3 SP, after WISHENKA-140 if the inline script moves):** fidelity gap of
   Jira: [WISHENKA-145](https://pypost.atlassian.net/browse/WISHENKA-145)
   the htmx stub. One small smoke test that runs real htmx (a vendored `htmx.org@1.9.12` copy under
   `tests/browser_assets/` or a pinned local file, no download at run time, to respect criterion 22) with a real
   `hx-post` move button, the CSRF `hx-headers`/`htmx:configRequest` logic and the cookie session instead of Bearer, so
   an htmx upgrade or a template wiring change is caught. Also add a guard that the three URLs in
   `browser_cdp.py:33-35` equal the ones in `base.html:8-10`. Not a duplicate of WISHENKA-140 (CSP/inline JS) or
   WISHENKA-141 (`data-reorder-url`).
4. **NON-BLOCKER, NEW Jira Debt issue (1 SP, low priority; may be merged into follow-up 1):** the `websockets`
   Jira: [WISHENKA-146](https://pypost.atlassian.net/browse/WISHENKA-146) (merged with item 1)
   dependency. Replace `websockets>=13.0` (`pyproject.toml:35`) by a range that matches the `legacy=True` API
   (probably `>=17.1,<18`; verify the release where `legacy` appeared), or switch the driver to a form that does not
   need the flag (a context-managed connection owned by `CdpPage`); document the revisit trigger (`websockets` drops
   `legacy`, or Playwright becomes attractive) in `doc/dev/testing.md` at Step 8.
5. **NON-BLOCKER, note on existing WISHENKA-143:** besides the real-device checklist, record that the committed
   Jira: noted as a comment on [WISHENKA-143](https://pypost.atlassian.net/browse/WISHENKA-143) (no new issue).
   driver can host automated tests for criterion 19 (autoscroll at both edges, Telegram SDK stub call order and
   degradation, `warnSdk` branch) once the SDK stub exists; these were explicitly left out of WISHENKA-110.
6. **NON-BLOCKER, note on existing WISHENKA-135:** the 53 browser tests add about 40 s to the CI quality gate; on the
   Jira: noted as a comment on [WISHENKA-135](https://pypost.atlassian.net/browse/WISHENKA-135) (no new issue).
   first CI run record the resolved browser, version, test runtime and any flakiness of the touch tests
   (synthesized touch scroll in headless Chromium on `ubuntu-latest`, Python 3.12).
7. **NON-BLOCKER, note on existing WISHENKA-137:** (a) the new guard `test_new_browser_modules_declare_marker_and_timeout`
   Jira: noted as a comment on [WISHENKA-137](https://pypost.atlassian.net/browse/WISHENKA-137) (no new issue).
   (`test_browser_prerequisites.py:504-531`) already covers part of "tighten the marker declaration check" for
   `test_*_browser.py`, but it misses `test_wishlist_sections_ui.py`, is named "new" and hard-codes the three module
   names; (b) the unreachable 60 s nested-pytest timeout (`test_browser_prerequisites.py:314`) vs the 30 s marker is
   unchanged and is covered by WISHENKA-137, referenced and not duplicated here.
8. **NON-BLOCKER, note on existing WISHENKA-138:** same family as the probe budget: driver waits (`COMMAND_TIMEOUT 10`,
   Jira: noted as a comment on [WISHENKA-138](https://pypost.atlassian.net/browse/WISHENKA-138) (no new issue).
   `LOAD_TIMEOUT 10`, `wait_for` 5 s) can add up beyond the 45 s per-test marker, in which case pytest-timeout fires and
   the specific `PageWaitTimeout` message with the snapshot is lost. Consider one per-test deadline for the driver.
9. **NON-BLOCKER, note on existing WISHENKA-144:** the redundant production cancel paths (`pointercancel` `:488` and
   Jira: noted as a comment on [WISHENKA-144](https://pypost.atlassian.net/browse/WISHENKA-144) (no new issue).
   `htmx:beforeSwap` `:520` both end in the same `cancelTouchDrag` as `lostpointercapture` `:494`) are the reason
   mutants M4b and M11 survive; decide during the tidy-up whether to comment the redundancy as intentional or to expose
   a test seam. No code change is proposed here.
10. **NON-BLOCKER, note on existing WISHENKA-141:** the browser tests assert the request path through
   Jira: noted as a comment on [WISHENKA-141](https://pypost.atlassian.net/browse/WISHENKA-141) (no new issue).
    `reorder_requests` (`browser_helpers.py:108-110`, `path.endswith("/items/reorder")`) and the numeric `data-wishlist-id`
    case (`test_reorder_uses_data_wishlist_id_not_location`, `test_wishlist_mouse_reorder_browser.py:117`). When
    `data-reorder-url` replaces the hardcoded URL and the regex (`wishlist.js:112`, `WISHLIST_ID_PATTERN`), those
    tests and the three-case warning test (`:179`) need to change in the same commit; the route suffix
    `/items/reorder` stays valid.
11. **NON-BLOCKER, references only (no ticket, no note):** WISHENKA-142 (layout jump; `retarget_touch_drag` compensates in
    the tests), WISHENKA-136 (apt branch of `deps-browser`, not touched), WISHENKA-139 (caching of `/static/*`: the
    tests fetch `wishlist.js` per test, negligible), WISHENKA-140 (inline JS), WISHENKA-126 (`core` file), WISHENKA-112 (no
    overlap). Accepted and recorded without a ticket: Playwright vs CDP decision (architecture section (a)),
    `label` outside `TOGGLE_EXCLUSION` (a note for product/requirements: fix the wording of criterion 4 or add
    `label` and a case), mirror constant `CLICK_SUPPRESS_MS`, the sub-pixel `_hold_fingers` side effect, fixed driver pacing
    (16 ms, 60 ms) and viewport/timeouts.

Pre-existing test failures: none found, so no `NON-BLOCKER — pre-existing` entries.
