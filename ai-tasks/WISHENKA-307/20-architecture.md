# WISHENKA-307: Switches in settings page are not following design

## Research

### Verified baseline (all facts checked in code on master, 94382c0)

- **Markup** (`wishenka/web/templates/settings.html`): the birthday reminder switch is
  `<label class="toggle-row">` at line 104, `<input type="checkbox"
  id="toggle-birthday-reminders" data-global-category="birthday_reminders"
  data-feedback-target=...>` at lines 105-109, `<span class="toggle-label">` at line 110 and
  `<span class="toggle-state" id="state-birthday_reminders">` at lines 111-115. The category
  switches are the same structure inside `{% for cat in wishlist_categories %}`: label at line
  126, input 127-130, label span 131, state span 132-136 (four categories:
  `wishlist_changes`, `reservation_changes`, `gift_received`, `reminders`,
  `wishenka/notices/preferences.py:26`), state ids `state-{cat}`, no input id.
  `birthday_reminders` is not in that loop, so no duplicate ids. The text of state comes from
  `settings.state.enabled|disabled` (`wishenka/i18n/catalog.py:66-67` en, `676-677` ru).
- **No ARIA** on these inputs: no `role`, no `aria-labelledby`, no `aria-describedby`. The
  accessible name is the whole `<label>` text: "name + Enabled/Disabled", and the state is
  announced twice (checkbox "checked" plus the text).
- **CSS** (`wishenka/web/static/miniapp.css`): `.toggle-row` (562-565, flex, min-height 44px);
  `.toggle-row input[type="checkbox"]` (566-569, box `44px x 44px`, native appearance);
  `.toggle-label` (570); `.toggle-state` (571-574, bordered pill 0.85rem, bold). Native look
  comes from `input[type="checkbox"] { width: auto; accent-color: var(--accent) }` (line 70).
  The global rule `input { max-width:100%; width:100%; border:1px solid #aa8998;
  border-radius:.5rem }` (line 63; line 64 is `input:not([type="checkbox"]) { padding }`)
  also matches checkboxes, so it will show its border as soon as `appearance: none` is set;
  the new rule must reset it. Lines 42-44 (`button, input, ...`: `box-sizing: border-box;
  min-height: var(--touch-target); margin: .25rem`) also apply; `margin: 0` in D-1 resets the
  margin, and the 44 px min-height equals the input height.
  Global `label { display:block; margin:.5rem 0 }`
  (line 71) is overridden by `.toggle-row`.
- **Focus**: global `:focus-visible { outline: 3px solid var(--focus); outline-offset: 3px }`
  (line 54). `assert_contrast_and_focus` (`tests/browser_screens.py:447`) reads the outline of
  the focused element itself, so the ring must stay on the `<input>`.
- **Tokens** (`:root`, lines 1-27): `--touch-target 44px`, `--surface #fff`,
  `--surface-subtle #fffafd`, `--muted-border #d5c1ca`, `--muted #695663`, `--accent #8c2551`,
  `--accent-dark`, `--focus #71319a`, `--danger #a61335`, `--ink`.
- **Themes**: the settings page has no dark theme: no `prefers-color-scheme`, no
  `color-scheme`, no `data-theme` anywhere in `wishenka/web`. `--tg-theme-*` appears only
  in `--receipt-bg`/`--receipt-text` (lines 11-12) and line 305, used by `.receipt-sheet` and
  `.modal-sheet` (not by `.settings-page`). So the "light, dark and Telegram" requirement
  is satisfied for the settings page by using only the fixed identity tokens (they are the
  same in the browser and Telegram), and any later re-definition of those tokens flows into
  the switch. No new theme support is added (out of scope). `.modal-sheet
  input[type="checkbox"]` (lines 510-514) does not apply to the settings page.
- **No `forced-colors`, no `prefers-reduced-motion`, no RTL rules** exist in the CSS;
  supported locales are `ru` and `en` (both LTR).
- **settings.js** (`wishenka/web/static/settings.js`): `refreshDisabled(category)` (lines
  218-223) sets `el.disabled = busy > 0 || el.dataset.unknown === '1'` for the global input and
  all list `<select>`s of the category. So *pending* and *unknown* are both `:disabled` and
  look the same; they differ only by `data-unknown="1"` (set by `markUnknown`, cleared in
  `applyCategoryFromPreferences`) and by the live regions (`Saving...` note, error message
  with Retry). The page-level `section[aria-busy]` is set by `setPending` for the whole
  section, so it cannot mark one switch. The script reads/writes only `input.checked`,
  `input.dataset.confirmed`, `#state-{category}.textContent`, and listens to `change` on the
  page; it uses no switch CSS class. Rejection restores `checked` through `setGlobalValue`
  (so a pure `:checked` CSS follows without extra JS).
- **Tests relying on the hooks**: `tests/test_personal_settings_browser.py`
  `test_settings_sections_visible_states_and_mobile_layout` (line 123, widths 320/375, ru/en)
  reads `input[data-global-category]`, `.checked`, `label.innerText` (must contain the
  Enabled/Disabled text), `label.textContent`, requires every visible `.settings-page`
  button/select/input `height >= 44` and no horizontal overflow; `.checked` is read in many
  tests (for example lines 195, 244); lines 848-870 click `#toggle-birthday-reminders` with a
  real mouse at the element centre and read `.checked`. `_click` uses `page.click(selector)`
  (centre of the element box). Pending is reached there by the fetch override at lines 606-625
  and unknown by the `_intercept` helper (line 76).
- `doc/dev/miniapp.md` (section "Personal Settings Screen (WISHENKA-291)", lines ~498-556)
  says at line 503 "Every toggle has visible on/off text", lists `input[data-global-category]`
  (line ~548), `#state-{category}` and `#toggle-birthday-reminders` as script dependencies,
  and describes pending as "control disabled" (States bullet, line ~518). Line 136 says
  `--accent` is used for "checkbox `accent-color`".
- Controls with `aria-busy` have precedent: `withPending` in `miniapp.js:87-98` sets
  `aria-busy="true"` on a disabled control and calls `clearAttribute(control, 'aria-busy')`
  (helper at `miniapp.js:75`) in `finally`; `receipt.js:360` sets and `receipt.js:322` removes
  `aria-busy` on a form; `miniapp.css:91` already has `:is(.is-pending, [aria-busy="true"])
  { cursor: progress }`. No test asserts `aria-busy` on a settings control (grep over
  `tests/` for `aria-busy` finds only receipt, history and cross-screen quick-add tests).

### Defects

1. **D1** The control is a native checkbox (`appearance: auto`, tinted by `accent-color`),
   enlarged to a 44 px square: not recognizable as a switch, and its look differs per browser.
2. **D2** No switch semantics: role is `checkbox`, not `switch`.
3. **D3** Accessible name includes the state text, and the state is announced twice
   (name "... Enabled" plus "checked"); after a change the name text and state can diverge
   for a moment.
4. **D4** Pending (`disabled`) and unknown (`disabled` + `data-unknown`) are visually the
   same greyed native box; disabled is not designed.
5. **D5** The state pill `.toggle-state` looks like a button/chip separate from the control
   (bordered pill), competing with the control.
6. **D6** Off vs on in a native checkbox is by a tick glyph only in the browser's own style.

## Implementation Plan

Pure presentation change: one CSS block, a small markup change in `settings.html`, and a
few lines in `settings.js` (`refreshDisabled`). No i18n key, backend, API or data change.

1. `settings.html`: for the five switches add `role="switch"`, `aria-labelledby` pointing to
   the label span (new ids), `aria-hidden="true"` on the visible state text. Keep input
   position and all ids/data attributes.
2. `settings.js`: in `refreshDisabled` mirror the pending lock to `aria-busy` on the switch
   inputs only (`[data-global-category]`, see D-6). Nothing else changes.
3. `miniapp.css`: replace the `.toggle-row` input / `.toggle-state` rules with the switch
   construction below, add state selectors, `forced-colors` and `prefers-reduced-motion`
   blocks. Keep `.toggle-row` and `.toggle-label` as they are.
4. `doc/dev/miniapp.md`, `doc/dev/testing.md`, `doc/dev/users.md`: update the statements
   listed in "Docs to update" (Step 8).

**Failing Repro (next Step 3).** One new module `tests/test_settings_switch_browser.py`
(decided, not an extension of `test_personal_settings_browser.py`). Reasons: that module is
about 905 lines of save/failure behaviour and WISHENKA-295 may edit it (see Overlap); a new
file keeps the switch skin tests disjoint and reviewable. Rules from
`tests/test_browser_prerequisites.py:522-549`: the module is named `test_*_browser.py`, has
module-level `pytestmark = [pytest.mark.timeout(45), pytest.mark.browser]` (exactly
`timeout(45)`), and every top-level `test_*` is covered by that marker. Fixtures
(`seed_wishlist`, `wishlist_server`, `chromium_browser`, `_browser_pages`) come from
`tests/conftest.py`; the helpers `_open`, `_click`, `_intercept` of the other module are
module-private, so the new module defines its own minimal `_open` (cookie, navigate
`/settings`, wait for `#birthdate-form`) and `_pending_override` (a copy of the fetch
override at `tests/test_personal_settings_browser.py:606-625`). It runs at 320 and 375 px in
`ru` and `en` and asserts on unchanged production code.

Measurement rules shared by all geometry and colour reads (R3, R4, R8, R10):

- Every read of pseudo-element geometry or colour happens after
  `page._send("Emulation.setEmulatedMedia", {"features": [{"name": "prefers-reduced-motion",
  "value": "reduce"}]})` (`CdpPage._send`, `tests/browser_cdp.py:206`), so the 0.15 s
  transition cannot leave a half-moved thumb (headless Chromium defaults to `no-preference`;
  a read right after `input.checked = true` otherwise sees the old `left`). The emulation
  was probed here on Chromium 156: `matchMedia('(prefers-reduced-motion: reduce)')` flips to
  `true`.
- Only one test (R10) runs under `no-preference` and checks that a transition is declared.

Assertions (R1-R4, R7, R8, R10 fail red on current code; R5, R6, R9 are regression guards
that already pass on current code and must stay green):

- **R1 switch semantics** (red: role absent): `input[data-global-category]` (birthday plus
  four categories, five in all) has `getAttribute('role') === 'switch'`.
- **R2 not a native look** (red: `auto`): `getComputedStyle(input).appearance === 'none'`.
- **R3 track/thumb geometry** (red: `content: normal`, no box): pseudo-element styles
  `getComputedStyle(input, '::before')` (track) and `'::after'` (thumb): track width between
  44 and 64 px and height between 24 and 36 px, `borderRadius` at least half of its height
  (pill), thumb is a circle (equal width and height, `border-radius` at least half), thumb
  width at least 18 px and smaller than the track height.
- **R4 state by position and colour** (red: no thumb): under reduced-motion emulation, for
  each switch read the thumb computed `left` and `width` and the input `offsetWidth`; the
  thumb centre is left of the input centre when unchecked and right of it when checked (set
  `.checked` directly, no change event, then read in the same tick). Track
  `backgroundColor` differs between checked and unchecked, and the checked track equals the
  resolved `--accent`. Contrast of thumb against track (both states) and of track border
  against `--surface` at least 3:1 (WCAG 1.4.11, computed in the test).
- **R5 target** (guard): input box height and width at least 44; the `label.toggle-row`
  rectangle is at least 44 high and fully inside the viewport (`left >= 0`, `right <=
  innerWidth`); clicking the label text (not the input) toggles `.checked` (real mouse
  click on `.toggle-label`), neighbouring rows are not toggled.
- **R6 focus** (guard): after `Tab` onto a switch its own computed `outlineStyle != none`,
  `outlineWidth >= 2`, outline colour is `--focus`, `outlineOffset` is `3px` (the global
  rule); Space toggles `.checked`.
- **R7 state announced once, name says what it controls** (red: role, `aria-hidden`
  missing): decided approach is the accessibility tree plus two attribute checks.
  `page._send("Accessibility.getFullAXTree")["nodes"]`, keep nodes with
  `role["value"] == "switch"` and `ignored` false: exactly five, in DOM order; for each
  `name["value"]` equals the catalog text of `settings.birthday_reminders_label` or
  `settings.category.{cat}` for the locale (so it does not contain the state word), and the
  `properties` entry with `name == "checked"` has `value["value"]` equal to `"true"` or
  `"false"` matching `input.checked`. The shape was probed on Chromium 156
  (`('switch', 'Name', [... ('checked', {'value': 'true'}) ...])`). Attribute checks: each
  `.toggle-state` has `aria-hidden="true"`, its text equals the catalog Enabled/Disabled and
  matches `.checked`.
- **R8 pending, unknown, disabled distinguishable** (red: no pseudo-elements, no
  `aria-busy`). Run under reduced-motion emulation. Pending is reached with the existing
  override pattern (`tests/test_personal_settings_browser.py:606-625`: `window.fetch` wrapper
  that sets `window.globalPending` and awaits `window.releaseGlobal` for
  `/api/profile/notifications/global`); the test is parametrised by the initial value of the
  `reminders` category (on, off; set through the API before opening the page) so that during
  pending the switch is read both with `.checked` true and false. Unknown is reached with
  `_intercept(page, "/api/profile/notifications/global", "commit", fail_read=True)` (line
  76; used by `test_ambiguous_preference_and_failed_read_disable_control`, line 286) and a
  click, then waiting until all of these hold, because `reconcileGlobal` calls `markUnknown`
  (`settings.js:317-321`, called at ~371) before the `finally` block runs `setPending(...,
  false)` and `changeBusy(category, -1)` (lines 360-361), so `aria-busy` is still `true`
  right after `data-unknown` appears: `data-unknown === '1'`, the input has no `aria-busy`
  attribute, the input is `disabled`, and `#global-notifications-feedback-pending` exists
  (`setPending` creates it lazily, `settings.js:177-185`) and is `hidden`; a missing element
  fails the assertion explicitly instead of raising a TypeError (the `_retry` helper there is
  not needed). The pending test calls
  `window.releaseGlobal()` before teardown, as line 628 of that module does.
  Read targets: `borderTopStyle`, border colour and track `backgroundColor` are read on
  `getComputedStyle(input, '::before')`; glyph `content` and the thumb centre on
  `getComputedStyle(input, '::after')` (with the input box); `opacity` and `cursor` on the
  input itself.
  Assertions in pending: `aria-busy === 'true'`, `disabled`, `borderTopStyle === 'dashed'`,
  border colour equals `--accent`, track `backgroundColor` equals `--surface-subtle` and
  differs from the resolved `--accent` (also when `.checked` is true), `opacity === '1'`,
  `cursor === 'progress'`, thumb `content` contains the ellipsis. In unknown: `disabled`,
  `data-unknown === '1'`, `borderTopStyle === 'solid'`, border colour equals `--danger`,
  track `backgroundColor` equals `--surface-subtle` and differs from `--accent`,
  `opacity === '1'`, `cursor === 'not-allowed'`, thumb `content` contains `?` and thumb
  centre equals the input centre (within 1 px). Unknown plus busy (retry): in the test set
  `aria-busy="true"` on the unknown switch and assert the thumb is still centred, border
  `dashed`, glyph is the ellipsis. A plain disabled switch (fresh page, an unchecked switch,
  `el.disabled = true`, no markers): `opacity` below 1, `cursor === 'not-allowed'`, thumb
  `content === '""'` (the base empty string; Chromium serialises it as two quote
  characters). Signatures (measured in Chromium with the real cascade): pending is dashed /
  ellipsis / `progress`; unknown is solid / `?` / `not-allowed`; plain disabled is solid /
  `""` / `not-allowed`. Assertions: pending differs from both others in border style, glyph
  and cursor; unknown and plain disabled share border style and cursor, so a separate
  unknown-vs-disabled assertion requires that they differ in glyph (`?` vs `""`), in
  `opacity` (unknown `1`, disabled below 1) and in track border colour (unknown equals the
  resolved `--danger`, disabled equals the resolved `--muted`, both read from the tokens,
  not literals).
- **R9 no overflow** (guard): `documentElement.scrollWidth <= innerWidth` at 320, 360 and
  375, with a long Russian category label. Each `.toggle-row` child (input, `.toggle-label`,
  `.toggle-state`) stays within the row (`right <=` row right), the label wraps (height may
  grow) and the row is never lower than 44 px.
- **R10 forced colors / reduced motion** (red: no media blocks), decided as CDP emulation
  with `Emulation.setEmulatedMedia`, which was probed here on Chromium 156 for the
  `features` names `prefers-reduced-motion` and `forced-colors` (both `matchMedia` queries
  flip to `true`). (a) Under `no-preference` (set explicitly): thumb and track
  `transitionDuration` is not `0s` and `transitionProperty` lists `inset-inline-start`.
  (b) Under `reduce`: `transitionDuration` is `0s` on `::before` and `::after`.
  (c) Under `forced-colors: active`: create probe elements with `background-color:
  Highlight`, `border-color: ButtonText` and `background-color: Canvas`; assert the checked
  track `backgroundColor` equals the Highlight probe, the unchecked track `borderTopColor`
  equals the ButtonText probe, and the checked thumb `backgroundColor` equals the
  HighlightText probe.
- **Existing tests that must stay green** (regression guards, all run in Step 4):
  - `tests/test_personal_settings_browser.py`: the layout test (`input` height >= 44, kept
    by the 44 px input box; `label.innerText` still contains the state text; `aria-hidden`
    does not change `innerText`/`textContent`), the `.checked` readers, the click on
    `#toggle-birthday-reminders` (the centre of the 52x44 box is on the input; its pseudo
    elements are part of it).
  - `tests/test_cross_screen_comfort_browser.py::test_control_contrast_and_focus_on_every_screen`
    (line 1101; the settings screen is in its list at line 1130 with
    `owner_token`, and `assert_contrast_and_focus` at line ~1134 checks that no text on
    `/settings` is below WCAG AA, which scans `.toggle-state` among all text, and that a
    `Tab`-focused control has a non-`none` outline of width > 0). The state text keeps
    `--muted` on a light surface (6.75:1 on `#fff`), so it passes; the focused switch keeps
    the global outline.
  - `tests/test_cross_screen_comfort_browser.py::test_control_settings_and_invitations_fit`
    (line 1009): `assert_screen_fits(settings, targets=True)` at line 1026 at 320, 360,
    375, 390 and 412 px (`WIDTHS` in `tests/browser_screens.py:30`) checks overflow,
    off-screen elements and clipped leaf text via `GEOMETRY_JS`; the 44 px `TARGETS` list
    excludes checkboxes, and `.toggle-state` is a leaf flex item, so the `min-width: 5.5rem`
    plus 52 px switch must not clip it at 320 px (D-5).
  - Step 4 run list: `tests/test_settings_switch_browser.py`,
    `tests/test_personal_settings_browser.py`, `tests/test_cross_screen_comfort_browser.py`,
    `tests/test_browser_prerequisites.py` (marker and timeout rule for the new module).
- **Sequencing**: research (this document) -> Step 3 red test against unchanged code
  (R1-R4, R7, R8, R10 red; R5, R6, R9 green as regression guards) -> Step 4 fix until green.

## Architecture

### Components and responsibilities

```
settings.html (markup + ARIA)  --class/ARIA/data hooks-->  miniapp.css (all visuals)
        ^                                                     ^
        |  input.checked, disabled, data-unknown, aria-busy   |
settings.js (state machine, unchanged logic)  ----------------+
```

- **settings.html**: structure, switch role, accessible name, hiding the duplicate state text.
- **miniapp.css**: all visuals; the switch is CSS-only on top of the real `<input>`.
- **settings.js**: remains the single owner of states; exposes them as DOM attributes only.
- Pattern: *native input as the single source of truth* (progressive enhancement). The
  `<input type="checkbox" role="switch">` keeps keyboard, label click, form semantics,
  `.checked` and `change`; the look is a pure `appearance: none` skin. No new JS widget,
  no hidden second control, no custom element.

### Decisions

**D-1 Construction.** Keep the real checkbox and skin it:
`.toggle-row input[type="checkbox"]` gets `appearance: none; -webkit-appearance: none;
position: relative; flex: 0 0 52px; width: 52px; height: var(--touch-target);
margin: 0; border: 0; border-radius: 999px; background: transparent; cursor: pointer`. The
input box is the 52x44 hit area and keeps the 44 px rule of the existing layout test. Visible
parts are pseudo-elements of the input. Pseudo-elements on an `appearance: none` checkbox
were validated only in Chromium here (not in WebKit or Gecko); the control stays a working
native checkbox if an engine ignores them. The input width and the thumb offsets (4px,
24px, 14px) are all in px (one unit, 52px = 4 + 24 + 24), so the geometry cannot drift with
the root font size.
- **track** `::before`: `content: ""; position: absolute; inset-block: 6px; inset-inline: 0;
  box-sizing: border-box; border: 2px solid var(--muted); border-radius: 999px;
  background: var(--surface-subtle)` (52x32 pill).
- **thumb** `::after`: `position: absolute; top: 50%; width: 24px; height: 24px; margin-top:
  -12px; border-radius: 50%; inset-inline-start: 4px; background: var(--muted); color:
  var(--surface); font: 700 14px/24px system-ui; text-align: center; content: ""`.
- **on** (`:checked`): track `background: var(--accent); border-color: var(--accent)`; thumb
  `inset-inline-start: 24px` (52 - 4 - 24), `background: var(--surface)`, `color:
  var(--accent)`, `content: "\2713"` (check glyph).
- Off thumb carries no glyph; on thumb carries the check, so state is conveyed by position,
  glyph and colour (requirement 3). `inset-inline-start` (not `left`/`transform`) keeps the
  switch correct in a hypothetical RTL locale.
- Visual details without the screenshot (assumption, per orchestrator): taken from the shared
  identity only: accent plum fill when on, muted border when off, pill shape like the
  `border-radius: 999px` chips and 0.5-0.75rem rounded controls, 44 px target, 3 px focus
  ring. The reviewer who sees the screenshot may adjust sizes/colours; the structure
  (native input + pseudo track/thumb, states by attributes) does not depend on them.
- Layout of the row: `[switch][label (flex 1, wraps)][state text]`; the switch stays first
  (DOM order unchanged, tests and tab order unchanged) with `align-self: center`.

**D-2 State text (kept).** The text `Enabled/Disabled` stays in the same `<label>` (it keeps
helping users who do not read the glyph, and `innerText` assertions stay valid) but
becomes plain secondary text, not a pill: `.toggle-state { flex: 0 0 auto; border: 0;
padding: 0; background: none; font-size: .85rem; font-weight: 700; color: var(--muted);
min-width: 5.5rem; text-align: end }` (width fits "Disabled"/"Отключено" so rows align;
`min-width` is dropped below 360 px via `@media (max-width: 359px) { min-width: 0 }` to
protect the label). The per-wishlist `<select>` and `.effective-badge` keep their form;
their words already come from the same catalog keys (`settings.state.*`), so wording stays
consistent and nothing changes there.

**D-3 Accessible name and single announcement.**
- Inputs get `role="switch"` (valid on `input type=checkbox`; exposes `checked` as on/off) and
  `aria-labelledby="label-{category}"`; the `.toggle-label` span gets `id="label-{category}"`
  (birthday: `label-birthday_reminders`, loop: `label-{{ cat }}`). The name is therefore only
  the label text ("Send birthday reminders", "Wish & wishlist changes").
- The state span gets `aria-hidden="true"`: the state is announced once by the switch role
  ("on/off"), never as a second contradicting word (the text is updated by JS only after the
  control, and a screen reader may read it before the update). `aria-hidden` removes it from
  the accessibility tree only; `innerText`, `textContent`, layout and the existing test are
  unaffected. The state span keeps its ids `state-{category}`.
- Clicking the whole `<label>` (label text and state text) still toggles the input: the label
  stays the wrapper.
- Result messages stay in the existing `role="status"` live regions (unchanged, announced
  once as today).

**D-4 States (pure CSS hooks, not colour only).** Hooks are attributes that exist or are set
by settings.js; no new classes:

  - **on** (hook `:checked`):
    accent track, thumb right, check glyph.
    Non-colour signal: position, glyph.
  - **off** (hook not checked):
    muted border, thumb left, no glyph.
    Non-colour signal: position.
  - **focus** (hook `:focus-visible`):
    the global rule is kept unchanged: `outline: 3px solid var(--focus)` with
    `outline-offset: 3px` (`miniapp.css:54`); no override. The ring follows the 52x44
    pill (`border-radius: 999px`) of the input.
    Non-colour signal: ring shape.
  - **pending** (hook `[aria-busy="true"]`, set on the switch inputs only by
    `refreshDisabled`): the track `background` is overridden to `var(--surface-subtle)`
    regardless of `:checked`, so a checked switch no longer shows the accent fill; the
    border is `2px dashed var(--accent)`; the thumb keeps its side (right if checked, left
    if not) but takes `background: var(--muted); color: var(--surface)` (visible on the
    light track) and glyph `"\2026"` (ellipsis); `cursor: progress`, `opacity` stays 1.
    Non-colour signal: dashed border, glyph, no accent fill.
  - **unknown** (hook `[data-unknown="1"]`): the track `background` is overridden to
    `var(--surface-subtle)` regardless of `:checked`; the border is `2px solid
    var(--danger)`; the thumb is centred (`inset-inline-start: 14px`), `background:
    var(--danger); color: var(--surface)`, glyph `"?"`; `cursor: not-allowed`, `opacity`
    stays 1. An unknown switch therefore never reads as "on".
    Non-colour signal: centred thumb, glyph, no accent fill.
  - **disabled (other)** (hook `:disabled` without the two hooks above):
    `opacity: .55`, `cursor: not-allowed`, no extra glyph (an unchecked one has none; a
    checked disabled switch keeps the check glyph of `:checked`).
    Non-colour signal: faded (unknown is not faded and has the `?` glyph and a `--danger`
    border; pending differs from both by border style, glyph and cursor).

  Cascade (decided). All state selectors use the prefix
  `.toggle-row input[type="checkbox"]` (with the pseudo-element suffix where needed), in
  this source order: base, `:checked`, `[data-unknown="1"]`, `[aria-busy="true"]`, and the
  generic disabled rule. Specificity: base is (0,2,1); `:checked`, `[data-unknown]` and
  `[aria-busy]` are (0,3,1), so source order decides among them (busy over unknown over
  checked). The generic rule `:disabled:not([aria-busy="true"]):not([data-unknown="1"])` is
  (0,5,1) and beats all of them for any property it sets, so it is restricted to `opacity`
  and `cursor` and must never set `content`, `background` or `border`. Its `:not(...)`
  exclusions mean it never fades a pending or unknown switch (no reset rules are needed).
  Unknown and busy together (Retry in progress): the thumb stays
  centred (the busy rule does not set `inset-inline-start`); busy sets only the dashed
  accent border, the ellipsis glyph and the thumb colours, `cursor: progress`; the track
  stays `--surface-subtle`. After a failed retry `aria-busy` is removed and the unknown look
  returns. Each state is also backed by text in the live region (`Saving...`, or the unknown
  message with Retry). The "disabled (other)" state is not reachable today (settings.js
  disables only for pending/unknown) but is designed so a future disabled switch is not
  mistaken for pending.
- Transitions: `transition: background-color .15s, border-color .15s,
  inset-inline-start .15s` on track and thumb, only inside `@media
  (prefers-reduced-motion: no-preference)`; reduced motion gets no transition (default
  `0s`).
- Forced colors / Windows high contrast: `@media (forced-colors: active)` block with system
  colours: track `border-color: ButtonText; background: Canvas`; on: track `background:
  Highlight; border-color: Highlight`, thumb `background: HighlightText; color: Highlight`;
  off thumb `background: ButtonText`; disabled/pending/unknown: `border-color: GrayText`
  (pending dashed and unknown centred thumb with glyphs still differ, since shape not
  colour carries them); focus ring uses the UA focus colour (outline stays). Position and
  glyphs keep the state readable even if all colours collapse.
- Contrast: all colours are existing tokens. Computed ratios: `--muted` (#695663) on `#fff`
  6.75:1 and on `--surface-subtle` 6.54:1; `--accent` (#8c2551) on `#fff` 8.4:1 (so also the
  `--surface` thumb on the `--accent` track); `--danger` (#a61335) on `#fff` 7.59:1. Every
  pair used by the switch is at least 6.5:1, above the 3:1 non-text requirement (WCAG
  1.4.11); R4 asserts it. The state text `--muted` on `--surface` is text above 4.5:1.
- Themes: only tokens, never literals (thumb uses `var(--surface)` instead of white). The
  settings page has a single (light, fixed-token) skin in browser and Telegram; there is no
  dark or Telegram-variable skin of this page to extend (see baseline), so nothing theme
  specific is added; the switch will follow if tokens are ever redefined.

**D-5 Wrapping at 320-375 px and long labels.** Row width at 320 px: 320 - 2x16 (body) - 2x16
(section) = 256 px; switch 52 + gaps 2x12 = 76 leaves 180 px for label + state (state 5.5rem
= 88 px at most; label at least 92 px and wraps with `overflow-wrap: anywhere` already set on
`.settings-page`). If the label wraps to many lines the row grows (`min-height`, not
`height`); `.toggle-label { min-width: 0 }` stays. Below 360 px the state `min-width` is
released so the label gets the space. The switch never shrinks (`flex: 0 0 52px`) and
cannot be pushed out of view. Verified by R9 and by the cross-screen fit test.

**D-6 settings.js.** Logic unchanged. Minimal change in `refreshDisabled`
(`settings.js:218-223`), next to the existing `el.disabled = ...`:
`if (locked) el.setAttribute('aria-busy', 'true'); else el.removeAttribute('aria-busy');`
(`removeAttribute` when not locked, as `miniapp.js:97` does with `clearAttribute`; no
`aria-busy="false"`). Precedent for `aria-busy` on a disabled control: `miniapp.js:87-98`,
`receipt.js:360`, and the global `[aria-busy="true"] { cursor: progress }` at
`miniapp.css:91`. `categoryControls(category)` returns the global switch and all list
`<select>`s of the category. The `aria-busy` write is restricted to the switch inputs, i.e.
elements matching `[data-global-category]` (the birthday switch and the four category
switches all carry it, `settings.js:850` selects them the same way; the selects carry
`data-wishlist-override` instead): `el.matches('[data-global-category]')` guards the
write. So the selects get no `aria-busy` and keep their cursor (the global `cursor:
progress` rule is not triggered for them). A pending save of a wishlist override still
locks the category, so the global switch of that category shows as pending (same as
today's `disabled` behaviour; `disabled` itself stays on all controls).
The unknown hook `data-unknown` and `.checked`/`dataset.confirmed`/`#state-*` handling are
reused as they are. Alternative rejected: deriving pending as `:disabled:not([data-unknown])`
(no JS change) would make a generic disabled switch indistinguishable from pending, which
violates the orchestrator clarification (b).

**D-7 Compatibility with existing hooks.** All ids, `data-global-category`,
`data-feedback-target`, `#state-*`, `#toggle-birthday-reminders`, `.toggle-row`,
`.toggle-label`, `.toggle-state`, `.checked` semantics, `change` event and DOM order are
kept. Added: `role`, `aria-labelledby`, `id="label-*"`, `aria-hidden`, `aria-busy`.

### Docs to update (Step 8, listed here so Step 4 does not forget)

`doc/dev/miniapp.md`: (a) line ~503 Personal Settings overview: "Every toggle has visible
on/off text" becomes "Every toggle is a `role="switch"` skinned checkbox with visible on/off
text (not announced; `aria-hidden`)"; (b) States bullet (~518): pending also sets
`aria-busy="true"` on the control and has a dashed track border plus ellipsis glyph, unknown
has a centred thumb and `?`, neither shows the accent fill; (c) selectors list (~548): add
`label-{category}` ids and `role="switch"`; (d) line ~136 tokens: `--accent` also fills the
switch track, and mention `--muted`, `--surface-subtle`, `--danger`, `--focus` as switch
tokens; (e) note the `forced-colors` and `prefers-reduced-motion` blocks.
`doc/dev/testing.md`: in the Russian section
"Тесты экрана личных настроек (WISHENKA-291)" (entry for
`test_personal_settings_browser.py`, lines ~511-516) add a bullet for
`tests/test_settings_switch_browser.py` (WISHENKA-307: switch semantics, geometry, pending,
unknown and disabled looks, forced-colors and reduced-motion emulation) and name the two
cross-screen guards. `doc/dev/users.md` (line ~365, the `WISHENKA-291` verification suites
bullet): add the new module next to the two settings suites.

### Risks

- **R-a** Pseudo-elements on `<input>` were validated only in Chromium here (not WebKit or
  Gecko); older engines may ignore them, in which case the control stays a working native
  checkbox. Acceptable for the supported Telegram WebView / current browsers.
- **R-b** Global `input` rule (border, `width: 100%`) leaks into the skin: neutralised by the
  explicit `border: 0; width: 52px` in the more specific `.toggle-row` rule; Step 3 test
  R3/R5 checks real geometry.
- **R-c** The focus ring uses the global `outline-offset: 3px` (decided, no override), so it
  is drawn around the 52x44 hit area, larger than the visible 52x32 track; accepted
  (consistent with other controls, compatible with `assert_contrast_and_focus`, which reads
  the outline of the input itself).
- **R-d** Without the screenshot the visual may differ from the reporter's expectation;
  mitigated by the identity-only rule and the review gate.
- **R-e** `aria-hidden` on visible text: allowed because the information is exposed by the
  switch state; the state word is not available to a screen reader in the user language
  ("on/off" comes from the AT locale). A speech-control user saying the visible "Enabled"
  will not match the switch, since the text is `aria-hidden` and not part of the name. The
  gain is a single announcement instead of double or stale. Accepted trade-off.
- **R-f** `aria-busy` on a form control has uneven AT support: it is an additional hint only;
  the pending message in the `role="status"` region and `disabled` remain.

### Overlap with other sprint tasks (sprint 2120)

- WISHENKA-295 (owner deletes wishlist) and WISHENKA-296 (create-flow bug): neither has an
  `ai-tasks/` directory yet (verified), `ai-tasks/sprint-2120/00-sprint-state.md` lists them as
  open. By subject they touch wishlist detail/create flows (`miniapp.js`, `wishlist.js`,
  wishlist routes/templates). 295 may also touch the per-wishlist cards in `settings.html`
  (`.wishlist-pref-card`, line ~151, outside the toggle rows) and
  `tests/test_personal_settings_browser.py`; that is disjoint from the toggle block (lines
  104-136 of `settings.html`, `settings.js:218-223`, `.toggle-*` CSS) and from the new test
  module, but is named here. `.toggle-*` classes are used only in `settings.html` and
  `miniapp.css` (grep verified). The only shared CSS file is `miniapp.css`; the changes touch
  disjoint rules (the toggle block near line 562) and the sprint runs tasks sequentially, so
  no conflict. Any `input[type="checkbox"]` rule changes are scoped to `.toggle-row`, so the
  item archive modal checkbox (`tests/test_visual_identity_browser.py:251`) is unaffected.
- Previous sprint stories (WISHENKA-291, 294) are already merged on master; this task fixes a
  defect of 291 and does not alter 294's cross-screen conventions (44 px, focus ring).

## Q&A

- **Why keep a native checkbox and not `<button role="switch" aria-checked>`?** It keeps
  `.checked`, `change`, label click and keyboard for free, so `settings.js` and the existing
  tests stay unchanged; a button would need a state mirror in JS and rewriting tests.
- **Why keep the Enabled/Disabled text?** Requirements allow it; it keeps the state readable
  without colour and the existing assertions valid. It is demoted to plain text and hidden
  from assistive technology to avoid double announcement.
- **Why not use `<input switch>`?** Supported only by Safari 17.4+; `role="switch"` is
  portable.
- **Does the screenshot matter?** It was unavailable; details (sizes, colours) follow the
  identity and are adjustable in review without structural change.
- **Does behavior change?** No: saving, serialization, restore/reconcile, unknown handling
  are untouched; the only JS change mirrors an existing lock into `aria-busy`.
- **Are the per-wishlist selects and badge changed?** No (orchestrator scope decision); they
  already use the same state words from `settings.state.*`.
