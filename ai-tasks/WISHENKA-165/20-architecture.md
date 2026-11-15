# WISHENKA-165: Presentation and currency consistency

## Research

The current CSS combines a Telegram background for the receipt sheet with a fixed dark root
text colour; the nested `form` also has a fixed white background. Receipt and notice styles
use fixed colours and repeated 44 px targets. `wishlist.js` already declares one 800 ms
`STALE_RELOAD_DELAY_MS` and uses it once. `gifted_view.py`, the four affected partials, and
`items_ui.py` duplicate RUB defaults; models, schemas, parser, repositories and services also
have runtime defaults. The historical database migration embeds its own SQL default.

[Telegram Mini Apps](https://core.telegram.org/bots/webapps#themeparams) exposes optional
background, text and destructive text theme variables and updates them on theme changes.
[MDN custom properties][mdn] documents `var()` fallbacks for unavailable custom properties.
A themed background alone does
not guarantee contrast: use paired foreground and background values for fixed-colour badges and
notices; check the actual rendered combinations, including nested form and controls.

## Implementation Plan

1. **Failing repro first:** add bounded browser tests in a receipt presentation test module under
   `tests/` using the existing CDP helpers. Render the actual stylesheet and receipt/notice markup
   with representative light and dark Telegram variables and without variables. Check computed
   foreground/background contrast for sheet text, nested form text, feedback and notice, and
   visibility of receipt controls. At least the dark sheet/form case must fail on the current CSS
   for insufficient contrast, before changing production code. Use local assets only, no Telegram
   or network service. Apply the project's timeout and bounded-wait rules. Existing receipt browser
   tests should remain intact.
2. Add a small shared currency constants module under `wishenka/` containing `DEFAULT_CURRENCY`
   and an ordered immutable sequence of the five `(code, label)` choices. Replace runtime default
   literals in the affected web, item and wishlist Python modules with the shared constant; register
   both values as Jinja globals in `wishenka/web/templates.py` and consume them in the affected
   partials. Preserve falsy/whitespace handling, explicit currencies and ordering. Do not alter
   historical migrations or currency symbols in the parser's normalization map.
3. Introduce semantic CSS custom properties for repeated palette, dimensions and overlay ordering.
   Preserve the existing 44 px target, 42 rem width, 90 vh limit and z-index relationships. Use
   Telegram text/background variables as a pair for sheet and nested form, with coherent fallbacks;
   give fixed semantic badge and notice backgrounds explicit matching foregrounds. Ensure inputs,
   selects and buttons remain readable. Keep live theme changes CSS-driven.
4. Keep the existing named 800 ms stale reload constant as the sole source for that delay; do not
   change reload semantics. Confirm the relevant tests retain the timing contract. Run focused
   browser and rendering tests, then the project's required quality gate.

Currency checks should render default and explicit values through item, preview, archive, edit
and gifted views, including all five edit choices; assert defaults at relevant API/model boundaries
and preserve supplied non-default values. These checks are separate from the red theme repro.

## Architecture

```text
Currency constants ──> item/wishlist defaults and web routes/gifted view
        │
        └───────────> Jinja environment globals ──> shared partials
Telegram CSS variables ──> semantic CSS tokens ──> sheet, controls, badges, notices
wishlist.js stale event ──> named 800 ms delay ──> reload
```

- The dependency-free currency constants module owns the default and display options. Existing
  validators, services and storage still own their current behavior and validation. Templates read
  globals through the existing shared Jinja environment, including direct partial/OOB renders.
- Python constants remain strings/tuples; form requests, response HTML, URL routes, and stored
  values retain their present interfaces. No schema or migration change is introduced.
- `miniapp.css` owns presentation tokens. Receipt and status components use them without adding
  theme state to Python or JavaScript. The Telegram-provided variables are optional external inputs;
  fallback pairs support non-Telegram rendering. Explicit semantic foreground/background pairs
  avoid inheriting a dark-theme foreground onto a light fixed notice or badge surface.
- `wishlist.js` owns the existing delay constant and stale event logic. No new timer or API
  is added.

## Q&A

- **How is dark mode detected?** No separate detection is needed: Telegram updates theme variables;
  CSS consumes them. The fallback palette is a complete light pair when they are unavailable.
- **Can arbitrary custom Telegram colours guarantee contrast?** Telegram supplies independent
  optional values; tests verify representative coherent palettes and fallbacks, not every possible
  third-party palette. Fixed semantic surfaces use matched text colours.
- **Does this change supported currencies?** No. The existing five labels, order and selected value
  remain unchanged; the default remains RUB. Explicit arbitrary currency handling is preserved.
- **Why retain the existing timer?** It is already a named single constant; changing or duplicating
  it would add risk without addressing the debt.

[mdn]: https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Values/var
