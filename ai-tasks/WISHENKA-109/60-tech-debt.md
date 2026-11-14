# WISHENKA-109: Technical Debt Analysis

Scope: `wishenka/web/static/wishlist.js`, `wishenka/web/static/miniapp.css`,
`wishenka/web/templates/partials/item_card.html`, `tests/test_wishlist_touch_reorder.py`.
Compared against `20-architecture.md` and `10-requirements.md`.

Timeout markers (grep `pytestmark` over `tests/test_wishlist_touch_reorder.py`): line 36 declares
a module-level `pytestmark = pytest.mark.timeout(30)`. The task adds one test module and it has
the marker. No timeout-marker BLOCKER.

Pre-existing failures: none (full suite 560 passed, per the task brief; not re-run in this step,
no code changed). The untracked `core` file in the repository root (197,693,440 bytes,
`ls -l core`) is already ticketed as WISHENKA-126 and is not duplicated here. For `td-99-commit`:
stage files by explicit path so `core` is never added.

## Shortcuts Taken

- **The touch gesture has no automated behavioural test.** `tests/test_wishlist_touch_reorder.py`
  inspects only rendered HTML (handle placement, `draggable`, `aria-label` on move buttons, no new
  third-party scripts) and string/regex tokens in `wishlist.js` and `miniapp.css`. The module
  docstring says so explicitly. Such checks pass on a comment and do not run the state machine
  (`armed`/`active`, threshold, cancel paths, hit-test, one request per gesture). The only
  dynamic evidence is the throwaway Chromium CDP run recorded in `00-roadmap.md` (Step 4: offline
  htmx stub, Telegram stub, touch emulation, not committed, autoscroll not exercised). A
  committed CDP/Playwright touch test (touch-drag, tap-vs-drag, cancel paths, autoscroll) belongs
  to WISHENKA-110 per `20-architecture.md` section (d); referenced, not duplicated. Follow-up 2.
- **Details are hidden at drag start (`display: none`), so the list shifts under the finger for
  an expanded card.** `miniapp.css`: `.item-card.is-touch-dragging .item-card-details { display:
  none; }`. This is the design in `20-architecture.md` (section (b), "Развёрнутая карточка"), not
  a deviation, and `hidden`/`aria-expanded` stay untouched, so cancel keeps the expanded state.
  The Step 4 observation stands: cards below the dragged one jump up by the height of the
  details panel at the moment the gesture becomes active (after the 4 px threshold). The drop
  works because the hit-test uses live layout (`elementFromPoint`, `getBoundingClientRect` in
  `updateDropTarget`, `wishlist.js:278-296`), but the jump is visible and may make the first
  drop target feel unpredictable. Not verified on a device how disorienting it is. Candidate UX
  improvement: collapse visually with a height transition, or keep the details and only dim them.
  Follow-up 3.
- **Click suppressor can swallow a genuine tap.** `armClickSuppression` (`wishlist.js:219-226`)
  sets `suppressNextClick` for up to `CLICK_SUPPRESS_MS` (400 ms) at the end of an `active`
  gesture (pointerup, and `cancelTouchDrag` for an active gesture). The capture-phase click
  listener (`wishlist.js:527-537`) clears the flag on the first click it sees. If the browser
  fires no click after the drag (the usual case when the pointer moved a lot: browsers do not
  emit `click` after a drag in many cases, not verified on Telegram WebView), the flag stays set
  until the timer fires and the next tap anywhere on the page within that window is swallowed
  (`preventDefault` and `stopPropagation`). The source comment documents this
  (`wishlist.js:212-217`). It also differs from the architecture text, which said the flag resets
  by `setTimeout(..., 0)` "not later than ~400 ms"; the code always waits the full window.
  Low impact (400 ms after a drag), unverified on real devices. Follow-up 1 (verify) and the
  possible fix (clear the flag on the next `pointerdown`) is noted there.
- **Pen input falls through to native DnD.** `pointerdown` returns for `pointerType !== 'touch'`
  (`wishlist.js:416-418`), so a stylus on a tablet gets whatever the browser does with HTML5 DnD
  on a `draggable="true"` card. Documented in `20-architecture.md` (section (b), last paragraph,
  and Q&A). Accepted; recorded only so it is not mistaken for new debt.
- **Native `draggable="true"` kept on the card; only a `dragstart` guard protects the touch
  path.** `wishlist.js:373-377` calls `preventDefault` on `dragstart` while `touchDrag` is set.
  The architecture allowed additionally toggling `card.draggable = false` during the gesture,
  "choose by manual result"; not done, and the manual result does not exist (needs Chrome Android
  long-press). Part of follow-up 1.

## Code Quality Issues

- **Long lines in JS.** `wishlist.js:141` (the `warnSdk` `console.warn(...)` template string, 110
  characters) and `wishlist.js:198` (the `warnSdk(kind === 'impact' ? ... : ...)` call in
  `haptic`, 110 characters). No JS formatter or line limit is configured (the `line-length = 100`
  in `pyproject.toml:42` is for Python/ruff), so this is style only. Cheap fix: wrap both, for
  example by computing the call name into a local constant. Fold into follow-up 4.
- **`wishlist.js` has grown to 538 lines and one IIFE** with a touch state machine, Telegram SDK
  wrappers (`telegramWebApp`, `warnSdk`, `disableSwipes`, `restoreSwipes`, `haptic`,
  `wishlist.js:120-200`), toggle, mouse DnD and global listeners together. Readable and
  documented with JSDoc, but a split into modules (toggle, reorder, telegram bridge) would be the
  natural step once WISHENKA-140 moves the remaining inline JS to static files and a convention
  for multiple scripts exists. Follow-up 4.
- **The reorder URL is still hardcoded** (`wishlist.js:112`, `/web/wishlists/${wishlistId}/items/
  reorder`) and the id still validated by regex (`WISHLIST_ID_PATTERN`, `:14`). The touch path
  now shares `submitReorder`, so this is the single place to change. Existing ticket:
  WISHENKA-141 (`data-reorder-url`). Interplay: WISHENKA-141 should change only `submitReorder`
  (`wishlist.js:95-118`) and the two templates; the touch gesture needs no change because it calls
  `submitReorder(list, card, target, after)` and reads nothing from `data-*` itself. A note on
  WISHENKA-141, no new issue.
- **Mouse and touch paths share `submitReorder` but not target resolution.** Mouse uses
  `event.target.closest('.item-card')` in `drop` (`:399`), touch uses `elementFromPoint` plus
  `closest` (`:279-283`). Both then go through `isAfterMidpoint`. Different inputs, so a shared
  helper would add little. No action.
- **Telegram SDK failures are reported once.** `sdkWarned` (`:55`) silences later failures by
  design (documented in `50-observability.md`). If the first failure is for
  `disableVerticalSwipes` and a later one for haptics, the second is invisible. Accepted
  trade-off against console spam.
- **Redundant duplicate `keydown` listeners** (toggle at `:363`, Escape at `:500`) and double
  `click` listeners (bubble at `:356`, capture at `:527`). Each has a distinct job and the
  suppressor must run in capture phase; no action, noted for readers.
- **Accessibility change: the handle is now `aria-hidden="true"` with `title` only.**
  `item_card.html:15-19`: the old handle in `.item-actions` had `aria-label="Перетащить"`
  (visible in the diff). The architecture explains why: the handle now lives inside the summary
  (`role="button"`, whose descendants are presentational), so a labelled child would be ignored
  or announced as noise (section (b)). Accepted deviation from the old markup, not from the
  architecture. Consequences, recorded as a note: (a) screen reader users and keyboard users
  have no drag; the only non-pointer reorder path is the move up/down buttons in the expanded
  card (`btn-move-up`, `btn-move-down`, the test checks they keep `aria-label`:
  `test_wishlist_touch_reorder.py:221`); that is sufficient for WCAG 2.5.7 (dragging
  alternative) and is unchanged; (b) the `title="Перетащить"` tooltip is mouse-only and gives
  nothing on touch (no hint text for first-time users beyond the `⠿` glyph, discoverability
  relies on the glyph). No action; revisit if user research shows the handle is not discovered.

## Missing Tests

- **No behavioural test of the touch gesture**, see Shortcuts. Scenarios left for WISHENKA-110
  (and listed in `20-architecture.md` section (d)): touch-drag collapsed and expanded card, drop
  on upper and lower half, tap on handle (no toggle, no request), tap on summary (toggle),
  vertical swipe outside the handle scrolls, cancel paths (`pointercancel`, second pointer,
  Escape, `visibilitychange`, `blur`, `htmx:beforeSwap` on `#items-list`), drop on self or
  outside list (no request), one request per gesture, repeated drag after the swap, click
  suppression after drag, autoscroll at both edges, Telegram stub call order (disable, impact,
  selection, enable) and degradation when the SDK is absent or older than 7.7/6.1, the
  `console.warn` branches of `submitReorder` and `warnSdk`.
- **The string tests are brittle** (`test_wishlist_touch_reorder.py:242-282`, parametrized token
  and CSS-declaration checks): a reformat of the CSS declaration or a token in a comment changes
  the result without a behaviour change. Same judgement as WISHENKA-108 follow-up 4: delete or
  reduce after browser tests land. Note on WISHENKA-110.
- **No test for the `drop`/mouse path after the refactor onto `submitReorder`.** The refactor was
  verified once by a synthetic dragstart/drop in the throwaway CDP run (same request as before)
  and by the existing string tests in `test_wishlist_static_script.py`. Covered by the
  WISHENKA-110 scope.
- **No test that `miniapp.css` is the file actually served with these rules at runtime** (only
  content checks). Low value.

## Performance Concerns

- **Autoscroll runs a `requestAnimationFrame` loop for the whole active gesture**
  (`autoScrollTick`, `wishlist.js:312-332`) and calls `elementFromPoint` and
  `getBoundingClientRect` on every `pointermove` and on every frame while scrolling. For a list
  of tens of cards this is cheap; for hundreds of cards the forced layout per frame could cost
  but it is not measured. The loop reschedules itself every frame even when the pointer is
  outside the edge zones (`speed === 0`), which is idle work, only for the gesture duration.
  NON-BLOCKER, no action unless profiling shows jank.
- **`will-change: transform` and `box-shadow` on the dragged card** (`miniapp.css`
  `.item-card.is-touch-dragging`): single element, only during the gesture. No concern.
- **`Cache-Control: no-store` for `/static/*`** (inherited, `wishlist.js` and `miniapp.css` grew)
  is WISHENKA-139. This task grows `wishlist.js` to 538 lines (16524 bytes; was 3,868 bytes after WISHENKA-108), re-downloaded
  on every page load. Note on WISHENKA-139 (no new issue).

## Deviations from Architecture

Checked against `20-architecture.md` and the code:

- Implemented as designed: handle moved into `.item-card-summary` before the thumbnail, only
  under `can_edit_wishlist` (`item_card.html:15-19`), `data-no-toggle`, `aria-hidden="true"`,
  removed from `.item-actions`; pointer events for `pointerType === 'touch'` only
  (`wishlist.js:415-451`); `armed`/`active` states with `DRAG_START_THRESHOLD_PX = 4`; pointer
  capture; cancel on `pointercancel` (`:488`), `lostpointercapture` (`:494`), second pointer
  (`:419-423`), Escape (`:500`), `visibilitychange` and `blur` (`:506-512`), `htmx:beforeSwap` on
  `#items-list` (`:520-525`), `contextmenu` suppressed (`:514-518`); one `submitReorder` shared by
  mouse and touch, single `htmx.ajax` (`:112`); `isAfterMidpoint` shared (`:84`); Telegram
  swipes 7.7 and haptics 6.1 guarded and in try/catch; CSS touch rules and drop indicators;
  summary without `touch-action`.
- Deviation 1 (accepted): the click-suppression window is a fixed 400 ms timer rather than
  `setTimeout(..., 0)` with a 400 ms cap (see Shortcuts).
- Deviation 2 (accepted, documented as optional in the architecture): `card.draggable = false`
  during the gesture was not implemented; only the `dragstart` guard (see Shortcuts).
- Deviation 3 (accepted): `html.is-touch-reordering { overscroll-behavior-y: contain; }` and the
  `touch-action: none` on the handle are the pull-to-refresh/overscroll defence; the
  architecture text lists only `body.is-touch-reordering` for `user-select`. The extra `html`
  class is added in `activateTouchDrag` (`wishlist.js:343`) and removed in `endTouchDrag`
  (`:246`). Harmless, recorded for completeness; whether it actually blocks Telegram's own pull
  gesture is part of follow-up 1.
- Deviation 4 (accepted, UX): the `hide details at drag start` layout jump (see Shortcuts) is the
  consequence of the architecture decision, not of the implementation.

## Hardcoded Values

All named constants live at the top of `wishlist.js:12-22`, so each is a one-line change.
None was derived from a source or a device measurement (the architecture says so for the
autoscroll numbers: "эвристика проекта"):

- `DRAG_START_THRESHOLD_PX = 4` (`:17`): smaller than the common 8-10 px touch slop. With
  `touch-action: none` on the handle there is no scroll to disambiguate, so a small value is
  intended; on a real finger a tap can easily move 4 px, which would start a drag and then
  suppress the click and trigger haptics for what the user meant as a tap on the handle (tap on
  the handle does nothing anyway, so the visible effect is a brief lift and a suppressed click
  within 400 ms). Not verified on device.
- `AUTOSCROLL_EDGE_PX = 64`, `AUTOSCROLL_MAX_PX = 14` per frame (`:18-19`): speed is per frame,
  so it is about 840 px/s at 60 Hz and about 1680 px/s on a 120 Hz display; frame-rate dependent
  (no time delta). Telegram's own top bar and the safe-area inset are not taken into account for
  the edge zones (`window.innerHeight` only). Feel not verified on device; the autoscroll path
  was not exercised in the CDP run.
- `CLICK_SUPPRESS_MS = 400` (`:20`): see Shortcuts.
- `SWIPES_MIN_VERSION = '7.7'` and `HAPTIC_MIN_VERSION = '6.1'` (`:21-22`): Bot API versions for
  `disableVerticalSwipes` and `HapticFeedback`, taken from the research in `20-architecture.md`
  (section on Telegram); the Bot API changelog is the source of truth and the check is
  duplicated in code and documentation.
- CSS colour `#6d28d9` for the drop indicators (`miniapp.css` `.drop-before`, `.drop-after`)
  duplicates the existing `.badge-category` colour in the same file; there is no CSS variable for
  the palette. Also `44px` (`.item-drag-handle`) duplicates the 44 px used for
  `.btn-move-up, .btn-move-down`, the shadow values and `opacity: .85`, `z-index: 10`.
  Cosmetic. Follow-up 4.
- Selectors and class names as string literals (`'.drop-before, .drop-after'` at `:207`,
  `'#items-list'` at `:281`, `:389`, `:398`, `:427`, `:522`; `'.item-card[draggable="true"]'` at
  `:379`, `:426`); `HANDLE_SELECTOR` and `CARD_SELECTOR` are named, the rest are not. The DOM
  contract is documented; same family as WISHENKA-141.

## Unverified on Real Devices

Everything below rests on assumptions that CDP touch emulation (Chromium, not a real touch
stack, not Telegram WebView) cannot confirm. Recorded as ONE manual-verification follow-up
(follow-up 1) using the checklist from `20-architecture.md` section (d):

- real Telegram WebView on iOS and Android (and Telegram Web);
- `disableVerticalSwipes()` called from `pointerdown` (`wishlist.js:450`) is early enough to stop
  the minimize/close swipe that begins on the same touch (the call is synchronous but the client
  applies it asynchronously; not known), and that `enableVerticalSwipes()` in `endTouchDrag`
  restores the state the app had;
- whether `pointerdown` is delivered at all for a touch that Telegram's native layer may claim
  first on older clients (< 7.7 only the documented limitation applies);
- native `dragstart` behaviour on long-press of a `draggable="true"` card on Chrome Android
  (the `dragstart` guard at `:373-377` is untested on a device) and the user-select/callout
  suppression on iOS (`-webkit-touch-callout: none`);
- pull-to-refresh and overscroll (`overscroll-behavior-y: contain`, `touch-action: none` on the
  handle);
- autoscroll feel, speed and edge zones, behaviour under a Telegram header or safe area;
- pointer capture while the dragged card has `pointer-events: none` (capture is on the handle
  inside that card; the CDP run worked, real browsers may release capture on `pointer-events`
  change, which would fire `lostpointercapture` and cancel the gesture silently, see `:494-498`);
- whether a click follows the pointerup after a drag on these WebViews (decides the click
  suppressor question);
- haptic calls on devices without haptics.

Checklist to run (from `20-architecture.md` section (d)):

1. tap on summary expands/collapses; tap on handle does nothing;
2. drag from a collapsed card (upper and lower half of the target), drag of an expanded card;
3. vertical swipe on a card outside the handle scrolls and reorders nothing;
4. autoscroll at the edge in a long list;
5. second finger, app minimize, Escape (emulator): nothing is saved;
6. after reorder a repeat drag works without reload, one request per gesture;
7. Mini App does not minimize during the gesture on clients 7.7 and newer, and the limitation
   for older clients is documented;
8. share page: no handle.

## Out of Scope (existing tickets, referenced not duplicated)

- Browser-level (Playwright/CDP) automated tests including touch emulation: **WISHENKA-110**.
- Moving the remaining inline script and `onclick` handlers to static files (strict CSP):
  **WISHENKA-140**. Interplay: it only adds more static scripts; `wishlist.js` is already
  external, and nothing in this task adds inline JS (`test_no_new_third_party_scripts`,
  `test_wishlist_touch_reorder.py:229`, covers only third-party tags). If WISHENKA-140 splits
  `base.html` JS into modules, the Telegram SDK wrapper in `wishlist.js` (`:120-200`) should be
  reused rather than duplicated. Note on WISHENKA-140.
- `data-reorder-url` instead of a hardcoded URL: **WISHENKA-141** (see Code Quality).
- `Cache-Control: no-store` for `/static/*`: **WISHENKA-139**.
- Untracked `core` file: **WISHENKA-126**.
- `items_ui.py`/`store.py` refactoring (WISHENKA-112): no overlap, no Python production code
  changed (template and static files only).

## Follow-up Tasks

There are no BLOCKER items. Every item below is NON-BLOCKER; none prevents Step 8, the commit,
or closing WISHENKA-109. Jira handling is proposed here; Phase D adds the links.

1. **NON-BLOCKER, NEW Jira Debt issue:** Manual verification of touch reorder on real devices:
   Jira: [WISHENKA-143](https://pypost.atlassian.net/browse/WISHENKA-143)
   Telegram iOS, Telegram Android, Telegram Web, Chrome Android. Run the 8-item checklist in
   "Unverified on Real Devices" and record the result. Decide from the results: the
   `DRAG_START_THRESHOLD_PX`, autoscroll constants (and make autoscroll time-based instead of
   per-frame if the speed differs between 60 and 120 Hz), whether `card.draggable = false` is
   needed during the gesture, whether the click suppressor should be cleared on the next
   `pointerdown`, whether `disableVerticalSwipes` at `pointerdown` is early enough, and whether
   pointer capture survives `pointer-events: none`. Estimate 2 to 3 SP (needs devices).
2. **NON-BLOCKER, note on existing WISHENKA-110 (no new issue):** Committed CDP/Playwright
   Jira: noted as a comment on [WISHENKA-110](https://pypost.atlassian.net/browse/WISHENKA-110) (no new issue).
   touch tests for the scenarios listed in "Missing Tests"; after they land, delete or reduce the
   string-token checks in `tests/test_wishlist_touch_reorder.py` (lines 242-282) and the
   WISHENKA-108 string checks. Reference `20-architecture.md` section (d) for the CDP method
   (`Emulation.setTouchEmulationEnabled`, `Input.dispatchTouchEvent`).
3. **NON-BLOCKER, NEW Jira Debt issue (small, 1 to 2 SP) after follow-up 1:** UX of dragging an
   Jira: [WISHENKA-142](https://pypost.atlassian.net/browse/WISHENKA-142)
   expanded card: the list jumps up under the finger when the details are hidden at drag start.
   Options: animate the collapse, keep details and dim them, or keep the card height with a
   placeholder. Decide with the device results; do not start before follow-up 1, since the
   severity is not verified on a real phone. If follow-up 1 shows it is acceptable, close as
   won't fix.
4. **NON-BLOCKER, NEW Jira Debt issue (1 SP, low priority; may be merged with the first
   Jira: [WISHENKA-144](https://pypost.atlassian.net/browse/WISHENKA-144)
   `wishlist.js` change that follows):** `wishlist.js` tidying: wrap the two 110-character lines
   (`:141`, `:198`), consider splitting the file into toggle, reorder and Telegram-bridge modules
   after WISHENKA-140, and introduce CSS variables for the repeated palette values (`#6d28d9`,
   44 px). Pure style/structure, no behaviour change.
5. **NON-BLOCKER, note on existing WISHENKA-141 (no new issue):** `submitReorder` is now the
   Jira: noted as a comment on [WISHENKA-141](https://pypost.atlassian.net/browse/WISHENKA-141) (no new issue).
   only user of the hardcoded URL and the numeric-id regex for both mouse and touch
   (`wishlist.js:95-118`); the change stays local to that function and the two templates.
6. **NON-BLOCKER, note on existing WISHENKA-140 (no new issue):** reuse the Telegram SDK wrapper
   Jira: noted as a comment on [WISHENKA-140](https://pypost.atlassian.net/browse/WISHENKA-140) (no new issue).
   (`telegramWebApp`, `warnSdk`, version guards) from `wishlist.js` when the inline script in
   `base.html` is moved; do not duplicate it.
7. **NON-BLOCKER, note on existing WISHENKA-139 (no new issue):** `wishlist.js` and `miniapp.css`
   Jira: noted as a comment on [WISHENKA-139](https://pypost.atlassian.net/browse/WISHENKA-139) (no new issue).
   grew in this task and are served with `no-store`.
8. **NON-BLOCKER, references only:** WISHENKA-126 (`core` file), WISHENKA-112 (no overlap).
   Accepted and recorded without a ticket: pen input falls through to native DnD, keyboard and
   screen-reader reorder only through the move buttons, `aria-hidden` handle replacing the old
   `aria-label`.
