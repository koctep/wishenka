# WISHENKA-307: Developer Documentation

## Changed Files

- `doc/dev/miniapp.md`
  - New subsection "Settings switches (WISHENKA-307)" in the personal settings section: markup
    contract, geometry, state table, cascade rule, `aria-busy` guard in `refreshDisabled`,
    reduced-motion and forced-colors behavior, known limitations.
  - Settings selectors list, states bullet, layout bullet and Overview updated; one
    troubleshooting item for the switch look.
  - Palette bullet: `--accent` role clarified.
- `doc/dev/testing.md`: new section "Тесты переключателей экрана настроек (WISHENKA-307)"
  (33 tests, R1-R10, measurement rules, pending and unknown overrides, limits with
  WISHENKA-313..315); note in the `test_personal_settings_browser.py` entry; pointer under
  "Известные ограничения".
- `doc/dev/users.md`: `tests/test_settings_switch_browser.py` added to the verification suites.
- `doc/dev/notifications.md`, `doc/dev/i18n.md`: checked, no stale statement about the switch look.

## Reconciled Stale Statements

- `miniapp.md` Overview: "Every toggle has visible on/off text" now says the toggles are skinned
  switches and links to the new subsection.
- `miniapp.md` palette: `--accent` was described as the checkbox `accent-color` only; now also
  the on track of the switches (`accent-color` stays for plain checkboxes, `miniapp.css:70`).
- `miniapp.md` states bullet: pending now mentions `aria-busy="true"` on global switches.
- `miniapp.md` selectors list: added `role="switch"`, `aria-labelledby`, `#label-{category}`,
  `aria-hidden` on `#state-{category}`.
- `testing.md`: personal settings browser entry points to the new module and the shared private
  helpers.

## Deviations from `20-architecture.md` Recorded in the Docs

- The docs record the actual plain disabled selector with its two guards,
  `:disabled:not([aria-busy="true"]):not([data-unknown="1"])`; the focus state has no
  switch-specific rule.
- The architecture only mentioned the forced-colors limitation indirectly; the docs describe it
  as in `60-tech-debt.md`.

## Follow-ups Linked

WISHENKA-313 (cross-browser, speech control), WISHENKA-314 (forced-colors, narrow labels),
WISHENKA-315 (shared test helpers).
