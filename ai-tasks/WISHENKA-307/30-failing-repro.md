# WISHENKA-307: Failing repro (Step 3)

Module: `tests/test_settings_switch_browser.py` (new; `pytestmark = [timeout(45), browser]`).
Production code is untouched. Geometry and colour reads run under emulated
`prefers-reduced-motion: reduce` (`Emulation.setEmulatedMedia` through `CdpPage._send`).

## Inventory

Format: requirement: test; cases; expected on current code.

- control (harness): `test_harness_reads_known_element_and_emulation_works`
  - cases: 1
  - expected on current code: green: emulation flips `matchMedia`, readers return the values of a
    probe pseudo-element, tokens resolve, AX tree lists the 5 controls
- R1 role=switch: `test_switches_have_switch_role`
  - cases: en/ru x 320/375
  - expected on current code: red: `role=None`
- R2 appearance none: `test_switches_are_not_native_looking`
  - cases: 4
  - expected on current code: red: `appearance='auto'`
- R3 track/thumb geometry: `test_track_and_thumb_geometry`
  - cases: en-375, ru-320
  - expected on current code: red: `::before` width `auto`, no box
- R4 position, colour, 3:1: `test_state_shown_by_thumb_position_and_colour`
  - cases: en-375, ru-320
  - expected on current code: red: transparent pseudo, no thumb position
- R5 44 px, label click: `test_switch_target_is_large_and_label_text_toggles`
  - cases: 4
  - expected on current code: green (guard)
- R6 focus ring, Space: `test_switch_focus_ring_and_space_toggle`
  - cases: en, ru
  - expected on current code: green (guard)
- R7 AX name/role/checked, `aria-hidden`: `test_switch_announced_once_with_name_of_what_it_controls`
  - cases: 4
  - expected on current code: red: 0 switch nodes, no `aria-hidden`
- R8 pending: `test_pending_switch_look`
  - cases: checked on/off
  - expected on current code: red: no `aria-busy`, border `none`, cursor `default`, no ellipsis
- R8 unknown (+busy): `test_unknown_switch_look`
  - cases: 1
  - expected on current code: red: border `none`, no `?`, thumb not centred
- R8 plain disabled: `test_plain_disabled_switch_look`
  - cases: 1
  - expected on current code: red: opacity 1, cursor `default`, content `none`
- R8 distinguishable: `test_pending_unknown_and_disabled_are_distinguishable`
  - cases: 1
  - expected on current code: red: all three share border/glyph/cursor
- R9 no overflow: `test_switch_rows_do_not_overflow_with_long_label`
  - cases: 320/360/375 (ru)
  - expected on current code: green (guard)
- R10 transition / reduced motion: `test_transition_declared_and_off_under_reduced_motion`
  - cases: 1
  - expected on current code: red: duration `0s`, property `all`
- R10 forced colors: `test_forced_colors_use_system_colours`
  - cases: 1
  - expected on current code: red: transparent track and thumb

Each test collects all problems and reports them in one assertion with the failing switch and the
actual value, so a red result names the missing design feature, not a harness error. Pending is
held with the `window.globalPending` / `releaseGlobal()` fetch override (released in `finally`);
unknown uses `_intercept(..., "commit", fail_read=True)` and waits for `data-unknown === '1'`, no
`aria-busy`, disabled, hidden `#global-notifications-feedback-pending`.

## Evidence (3 runs of the module, identical)

| Run | Passed | Failed |
|---|---|---|
| 1 | 10 | 23 |
| 2 | 10 | 23 |
| 3 | 10 | 23 |

Green (stable in all runs): the control, R5 x4, R6 x2, R9 x3. Red: the other 23 cases.
Other suites on unchanged code: `tests/test_browser_prerequisites.py` 48 passed;
`tests/test_personal_settings_browser.py` 39 passed.

## Run

```
make test-serial PYTEST_ARGS="tests/test_settings_switch_browser.py -q"
make test-serial PYTEST_ARGS="tests/test_browser_prerequisites.py -q"
```

## Notes

- `_api`, `_click`, `_intercept`, `_open` are imported from
  `tests/test_personal_settings_browser.py`
  (the repo already imports private helpers across test modules) instead of copied; the pending
  fetch override is a local copy because the original is inline in a test.
- No change to `tests/browser_cdp.py` or `tests/browser_screens.py`.
