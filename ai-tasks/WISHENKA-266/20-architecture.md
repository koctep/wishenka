# WISHENKA-266: Dark-theme receipt close button stays readable

## Research

`tests/test_receipt_theme_browser.py::test_receipt_text_has_readable_contrast`
opens the receipt dialog, then for `dark` sets
`--tg-theme-bg-color: #202020` and `--tg-theme-text-color: #f5f5f5` on
`document.documentElement`. Those are the same custom properties Telegram
Mini Apps publish as theme params
([theme params](https://core.telegram.org/bots/webapps#themeparams)).
`:root` in `wishenka/web/static/miniapp.css` maps them:

- `--receipt-bg: var(--tg-theme-bg-color, #ffffff)`
- `--receipt-text: var(--tg-theme-text-color, #29222b)`

The check then reads computed style for `.receipt-sheet .btn-modal-close`
(among other receipt nodes). Contrast is the WCAG 2.1 ratio
`(L1 + 0.05) / (L2 + 0.05)` after sRGB linearization
([WCAG 2.1](https://www.w3.org/TR/WCAG21/),
[Understanding 1.4.3](https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum)).
The surface is not assumed to be white. The script walks from the element
through ancestors while `backgroundColor`’s fourth parsed channel is `0`
(transparent `rgba(0, 0, 0, 0)`). An opaque `rgb(r, g, b)` has no fourth
channel, so the walk stops. The button’s own fill is the surface whenever
that fill is opaque.

At baseline `e433223` the close control only has
`.btn-modal-close { color: inherit }`. That beats the global
`button { color: var(--accent-dark) }` rule, so the label inherits
`--receipt-text` (`#f5f5f5` in the dark case). The background stays the
global `button { background: var(--surface) }`, and `--surface` is
`#ffffff`. The walker stops on that opaque white. `#f5f5f5` on `#ffffff`
is contrast **1.090230993517392**, the recorded dark failure. A headless
Chromium probe of the current stylesheet with that close rule removed
reproduces the same three results: dark `1.090230993517392`, light
`16.29`, fallback `15.46`.

The current tree already contains the pairing added with the shared visual
identity (commit `f01073b`):

```css
.receipt-sheet .btn-modal-close,
.modal-sheet .btn-modal-close,
.modal-sheet .btn-cancel {
  background: var(--receipt-bg);
  color: var(--receipt-text);
}
```

The receipt sheet element is `class="modal-sheet receipt-sheet"`, so both
sheet selectors match the same close control. The probe of the current
file, using the test’s formula, gives:

| Theme | Foreground | Surface the walker stops on | Contrast |
| --- | --- | --- | --- |
| dark | `rgb(245, 245, 245)` | `rgb(32, 32, 32)` on the button | 14.94 |
| light | `rgb(32, 32, 32)` | `rgb(255, 255, 255)` on the button | 16.29 |
| fallback | `rgb(41, 34, 43)` | `rgb(255, 255, 255)` on the button | 15.46 |

All three are at least 4.5. The same probe’s confirm control stays about
5.02 (`#ffffff` on `#15803d`), so the close-control rule does not disturb
the other nodes the test already covers.

`var()` fallbacks are the standard custom-property behavior
([MDN custom properties](https://developer.mozilla.org/en-US/docs/Web/CSS/Using_CSS_custom_properties)).
With no Telegram colors set, the pair is `#29222b` on `#ffffff`.

## Implementation Plan

Keep the theme boundary in CSS. The smallest change that makes
`.receipt-sheet .btn-modal-close` pass the dark case is the declaration
already in `wishenka/web/static/miniapp.css`: opaque
`background: var(--receipt-bg)` and `color: var(--receipt-text)` on
`.receipt-sheet .btn-modal-close`. Because the button fill is opaque, that
background is the surface the test measures. In the dark theme that surface
is `#202020` against `#f5f5f5`.

Leave the rule in the shared block with `.modal-sheet .btn-modal-close` and
`.modal-sheet .btn-cancel`. The receipt close control carries both sheet
classes, and splitting the block would not change the measured pair. Keep
the existing `:hover:not(:disabled)` companion that sets
`background: var(--receipt-bg)` on the same selectors, so the zero-specificity
`button` hover fill `#fff0f4` cannot replace the sheet surface. The standing
test does not hover.

Do not add a second close-control rule, a fixed dark color, or a new
property on `:root`. Do not edit `wishenka/web/static/app.js`. That file
stays free of the substring `receipt`. Do not change templates, routes, or
who may record a receipt.

**Mandatory — Failing Repro (next Step 3):** N/A — no further behavioral
change. The standing check
`tests/test_receipt_theme_browser.py::test_receipt_text_has_readable_contrast`
already asserts contrast of at least 4.5 for `.receipt-sheet .btn-modal-close`
in `dark`, `light`, and `fallback`. On this tree the dark case is green:
the stylesheet probe measures 14.94. Removing the pairing reproduces the
recorded 1.090230993517392 failure, and that removal is not part of the
work. Step 3 does not add another test and does not revert the rule to
force a red run. Step 4 runs the existing parametrized test and stops when
`dark`, `light`, and `fallback` pass.

## Architecture

```text
Telegram theme params (or none)
        │
        ▼
:root  --receipt-bg / --receipt-text
        │
        ▼
wishenka/web/static/miniapp.css
  .receipt-sheet .btn-modal-close
        │  color + opaque background
        ▼
computed style read by test_receipt_text_has_readable_contrast
```

- **Stylesheet** `wishenka/web/static/miniapp.css` owns the receipt sheet
  appearance. The selector that the dark check measures is
  `.receipt-sheet .btn-modal-close`. Its responsibility is to paint the
  close label and its own fill as the paired receipt tokens, so the
  contrast walk stops on a surface that meets 4.5 in dark, light, and
  fallback.
- **Global button rule** in the same file (`button { background: var(--surface); color: var(--accent-dark) }`
  and `.btn-modal-close { color: inherit }`) remains the default for other
  buttons. It is the source of the dark failure when the sheet selector is
  absent: inherited `#f5f5f5` on opaque `--surface` (`#ffffff`).
- **Receipt sheet markup** (`wishenka/web/templates/partials/item_receipt_modal.html`
  and the edit/cancel receipt partials) already puts
  `class="btn-modal-close"` inside `class="modal-sheet receipt-sheet"`.
  No template change.
- **Browser check** `tests/test_receipt_theme_browser.py` is the contract.
  It supplies the three theme inputs and the 4.5 threshold. Python test
  code stays as it is.
- **Receipt recording** (routes, roles, full and partial receipt, surprise
  secrecy) stays outside this change. `wishenka/web/static/app.js` stays
  unchanged.

Pattern: a CSS custom-property theme boundary, overridden only by a
higher-specificity sheet selector. Specificity of
`.receipt-sheet .btn-modal-close` is `(0, 2, 0)`, which beats `button`
`(0, 0, 1)` and `.btn-modal-close` `(0, 1, 0)`. No JavaScript theme
detection and no new HTTP interface.

The interface between modules is the custom properties
`--tg-theme-bg-color`, `--tg-theme-text-color`, `--receipt-bg`,
`--receipt-text`, and `--surface`, plus the class `btn-modal-close` on the
receipt sheet. The test reads computed `color` and the nearest opaque
`backgroundColor`. It does not read a new API.

## Q&A

- **Q:** Which file and selector must carry the dark-theme pair?
  **A:** `wishenka/web/static/miniapp.css`, selector
  `.receipt-sheet .btn-modal-close`, with
  `background: var(--receipt-bg); color: var(--receipt-text);`. That block
  is already present and is shared with `.modal-sheet .btn-modal-close` and
  `.modal-sheet .btn-cancel`.

- **Q:** Why is the recorded contrast exactly 1.090230993517392?
  **A:** The test compares `#f5f5f5` (`--receipt-text` in the dark case,
  inherited by `.btn-modal-close`) with the button’s opaque `--surface`
  fill `#ffffff`. Those two colors are that ratio. The sheet behind the
  button is `#202020`, and the walker never reaches it while the button
  fill is opaque.

- **Q:** Do light and fallback need a different selector?
  **A:** No. The same pair resolves to `#202020` on `#ffffff` (light,
  about 16.29) and `#29222b` on `#ffffff` (fallback, about 15.46).

- **Q:** Does Step 3 add a new red test?
  **A:** No. The existing parametrized test is the check, and on the
  current stylesheet the dark close control is already at 14.94. See
  Implementation Plan.

- **Q:** May `app.js` or receipt permissions change?
  **A:** No. `wishenka/web/static/app.js` stays unchanged and free of
  `receipt`. Who may record a receipt stays as it is.
