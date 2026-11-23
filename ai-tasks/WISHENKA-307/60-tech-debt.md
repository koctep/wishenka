# WISHENKA-307: Technical Debt Analysis

No blockers were found. The switch skin, the `role="switch"` markup and the `aria-busy` hook are
covered by `tests/test_settings_switch_browser.py` (33 of 33 pass). All items below are
NON-BLOCKER follow-ups; none prevents shipping this task.

## Shortcuts Taken

- Verified only in Chromium (CDP harness). The skin relies on `appearance: none` plus
  `::before` / `::after` on `<input type="checkbox">` (`miniapp.css:566-603`). Safari (iOS
  Telegram) and Firefox render pseudo-elements on such inputs, but this was not checked there.
  Impact: a visual regression on iOS would go unnoticed. Fix: a manual pass on iOS Safari and
  Firefox, or a WebKit/Gecko run if the harness ever supports it.
- The visible `Enabled`/`Disabled` text is `aria-hidden="true"` (`settings.html:116`, `:140`)
  so the state is announced once. Impact: speech-control users who say the visible word
  ("click Enabled") may not match a control, because the accessible name is the label only.
  Fix: decide with an accessibility review; options are `aria-description` or dropping
  `aria-hidden` and using `aria-labelledby` on both spans only if the double announcement is
  acceptable.
- Per-wishlist overrides (`<select data-wishlist-override>`, `settings.html:165`) keep the old
  native look next to the new switches. Not a defect (they are three-state: inherit / on / off,
  the requirements keep them unchanged) but the page now mixes two styles.
- The `.toggle-row` switch geometry is hard-coded in px (`52px`, `24px` thumb, `4px`/`24px`
  offsets, `inset-block: 6px`, `miniapp.css:566-603`) and the transition property list is
  repeated for `::before` and `::after` (`:605-606`). The page has no root font scaling, so
  px is consistent today. Cosmetic; extract custom properties if the switch is reused.

## Code Quality Issues

- Forced-colors state precedence (`miniapp.css:609-616`): inside the block,
  `:checked::before` (Highlight track) has the same specificity as the state rules and is the
  last track rule, but the pending (`[aria-busy="true"]::before`, `:594`) and unknown
  (`[data-unknown="1"]::before`, `:587`) rules sit outside the block and have equal specificity,
  while the block comes later and wins for `:checked`. Result: a pending or unknown switch that
  is also `:checked` gets the Highlight track instead of Canvas. For a checked and busy switch
  the dashed border is Highlight on a Highlight track, so it is invisible and only the `...`
  glyph tells the state (unknown keeps the `?` glyph and a visible danger border), so the
  impact is limited to high-contrast users.
  Fix: add `[aria-busy="true"]::before` and `[data-unknown="1"]::before` rules resetting
  `background: Canvas` inside the forced-colors block, and assert it in
  `test_forced_colors_use_system_colours` (`tests/test_settings_switch_browser.py:721`).
- Narrow-width labels (`settings.html:111-140`, `miniapp.css:562-623`): at 320 px in ru the row
  is 52 px switch + two 12 px gaps + 88 px state `min-width` (`5.5rem`), which leaves a label
  box of about 100 px, while "Подтверждения" needs about 137 px, so a mid-word break
  ("Подтвер/ждения") is certain there. The cause is the width budget, not
  `overflow-wrap: anywhere` (`miniapp.css:31`). The old layout (44 px checkbox plus pill) left
  about 111 px, so the break almost certainly pre-dates this change. The `max-width: 359px`
  rule (`:623`) only drops the state `min-width`. Fix: below 360 px stack the state text under
  the label (or hide it, the glyph and the label already carry the state).

## Missing Tests

- `tests/test_settings_switch_browser.py:23` imports the private helpers `_api, _click,
  _intercept, _open` from `tests/test_personal_settings_browser.py`. Any edit of that module
  (for example by WISHENKA-295) can break this one. The pending fetch override
  (`_PENDING_OVERRIDE`, `:481`) is a local copy of similar logic. Fix: move the shared helpers
  to `tests/browser_screens.py` (or a new `tests/browser_settings.py`) as public functions.
- Coverage gaps: R3/R4/R8 are parametrized over a subset of en/ru x 320/375; the control
  that finds switches accepts role `checkbox` or `switch` (`:219`), so it does not prove the
  role by itself (R1 does); `test_transition_declared_and_off_under_reduced_motion` (`:699-718`)
  has a part (b) that passes vacuously on the old code. Fix: split it into two tests and
  widen the parametrization if the runtime stays acceptable.
- No WebKit/Gecko run (see Shortcuts Taken).

## Performance Concerns

None. CSS-only transitions limited to `prefers-reduced-motion: no-preference`; one attribute
write per category in `refreshDisabled` (`settings.js:222-224`).

## Follow-up Tasks

1. **Forced-colors precedence and narrow label wrapping in the settings switches: reset the
   track to Canvas for pending/unknown switches inside the forced-colors block (with an
   assertion); stop mid-word label breaks at 320 px (ru) by stacking or hiding the state text
   below 360 px; compare with the pre-change layout first.** NON-BLOCKER (accessibility and
   layout polish; states remain distinguishable, text stays readable), priority Low.
   Jira: [WISHENKA-314](https://pypost.atlassian.net/browse/WISHENKA-314).
2. **Share the browser test helpers of the settings screen: extract `_api`, `_click`,
   `_intercept`, `_open` and the pending fetch override into a public module, drop the
   private import in `tests/test_settings_switch_browser.py:23`, split the reduced-motion test
   (`:699-718`) and widen the R3/R4/R8 parametrization.** NON-BLOCKER (test maintainability only),
   priority Low. Jira: [WISHENKA-315](https://pypost.atlassian.net/browse/WISHENKA-315).
3. **Cross-browser and speech-control check of the switch skin: verify the
   `appearance: none` pseudo-element rendering in iOS Safari and Firefox, and decide how the
   visible `Enabled`/`Disabled` text should be exposed to speech-control users (currently
   `aria-hidden`); consider a matching look for the per-wishlist selects.** NON-BLOCKER
   (Chromium-verified, a manual check; no known defect), priority Low.
   Jira: [WISHENKA-313](https://pypost.atlassian.net/browse/WISHENKA-313).

Considered and dropped: the checkbox in `wishenka/web/templates/partials/item_archive_modal.html:25`
is a plain form option inside a modal (`.modal-sheet input[type="checkbox"]`,
`miniapp.css:510`), not an on/off setting, so it does not need the switch skin. The
`.toggle-state` color `var(--muted)` (#695663) on the white surface has a contrast of
about 6.7:1 on #ffffff
(computed; no test asserts it), disabled switches use `opacity: .55`, which WCAG 1.4.11
exempts as inactive components, and the `html` element has no font-size override, so the
52 px width does not conflict with the WISHENKA-294 relative sizing.

### Pre-existing test failures

The full-suite failures that reproduce on the base commit are listed with test node ids and
Jira keys in `ai-tasks/WISHENKA-292/60-tech-debt.md` (section "Pre-existing test failures",
WISHENKA-264, 235, 245, 265, 220, 232, 267, 298 and others). They are NON-BLOCKER —
pre-existing, already tracked, and not touched by this task.
