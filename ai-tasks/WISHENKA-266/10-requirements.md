# WISHENKA-266: Dark-theme receipt close button stays readable

## Goals

A list author recording a received gift opens the receipt sheet in the Mini
App. Telegram may be using a dark theme. The control that closes that sheet
must stay readable against the sheet behind it. Readable means contrast of
at least 4.5, the same bar the product already uses for receipt text
(WCAG).

Today that close control fails the bar in the dark theme. At base
`e433223`,
`tests/test_receipt_theme_browser.py::test_receipt_text_has_readable_contrast[dark]`
reports contrast 1.090230993517392 where at least 4.5 is required. The light
theme and the default theme (no Telegram colors set) are not that recorded
failure. They stay readable.

Who may record a receipt, what a full or partial receipt means, and what a
recipient is allowed to learn stay as they are. The shared Mini App script
is outside this change.

Implementation language: CSS for the receipt sheet appearance, and Python
for the existing browser check.

## User Stories

- As a **wishlist owner** recording a received gift in Telegram's dark
  theme, I can see the close control on the receipt sheet against the sheet
  behind it.
- As an **administrator** or **co-author** recording a receipt in the dark
  theme, I see that same readable close control.
- As a list author recording a receipt in the light theme, or with no
  Telegram theme colors, I still see a readable close control and readable
  receipt text on that sheet.
- As a **recipient**, I still never learn who reserved or bought a wish from
  this sheet.
- As a **giver**, I do not gain a receipt sheet or a way to record receipt.
- As a **maintainer**, I can trust
  `test_receipt_text_has_readable_contrast` to describe readable receipt
  text and the close control in the dark theme, the light theme, and the
  default theme.

## Definition of Done

1. **Dark theme.** On the receipt sheet, the close control has contrast of
   at least 4.5 against the surface behind it when Telegram's dark theme
   colors are in effect.
2. **Light theme.** That close control, and the receipt wording the
   standing check already covers, stay at or above 4.5 in the light theme.
3. **Default theme.** With no Telegram theme colors set, that close control
   and that receipt wording stay at or above 4.5.
4. **Standing check.**
   `tests/test_receipt_theme_browser.py::test_receipt_text_has_readable_contrast`
   passes for `dark`, `light`, and `fallback`. The dark case is no longer
   the close-control failure recorded at `e433223` (contrast about 1.09,
   expected at least 4.5).
5. **Receipt meaning.** Who may record a receipt, what a full or partial
   receipt means, and what a recipient may learn are unchanged.
6. **Shared script.** `wishenka/web/static/app.js` is unchanged and stays
   free of the substring `receipt` (WISHENKA-214).

## Task Description

### Problem

The receipt sheet is how a list author records that a gift was received.
It includes a close control. In Telegram's dark theme that control does not
stand out from the sheet: the recorded contrast is about 1.09, below the
4.5 bar used for readable receipt text. A person can miss how to dismiss
the sheet.

The light theme and the default theme are not the recorded failure. Other
receipt text on the sheet is not the recorded failure. The dark-theme close
control is the gap.

### Scope

- A readable close control on the receipt sheet in the dark theme, with
  contrast of at least 4.5 against the sheet behind it.
- The light theme and the default theme remain readable for that control
  and for the receipt text the standing check already covers.
- The meaning of `test_receipt_text_has_readable_contrast` for `dark`,
  `light`, and `fallback`.

### Constraints

- Leave who may record a receipt, and what recording it does, unchanged.
- Leave surprise secrecy unchanged.
- Leave `wishenka/web/static/app.js` unchanged. That file stays free of the
  substring `receipt` (WISHENKA-214).
- Leave WISHENKA-267, WISHENKA-283, WISHENKA-298, WISHENKA-311,
  WISHENKA-354, WISHENKA-356, and WISHENKA-357 out of this task.
- The baseline commit on the ticket is `e433223`. This step records that
  known failure and does not re-run the historical baseline.

### Non-goals

- A new receipt screen, a new close label, or a new theme picker.
- A redesign of the light theme beyond keeping it readable.
- Any other failing check from the sprint, including the tickets named
  above.
- Gift-receipt behavior in the shared Mini App script.

### Main entities

- **Wishlist** — the list whose author records a received gift.
- **Wish** — the entry the receipt sheet is about.
- **List author** — owner, administrator, or co-author who may open the
  receipt sheet and record receipt.
- **Receipt sheet** — the surface used to record that a gift was received,
  including its close control.
- **Theme** — dark, light, or the default when Telegram supplies no theme
  colors. Dark is the theme where the close control is unreadable today.
- **Recipient** — must not learn giver identity, a reservation, or a
  purchase from this sheet.
- **Giver** — does not record the receipt on this sheet.

## Q&A

- **Q:** Why does the dark check fail?
  **A:** The close control on the receipt sheet has contrast about 1.09
  against the sheet, and the bar is at least 4.5. At `e433223` that is the
  recorded failure of
  `test_receipt_text_has_readable_contrast[dark]`. This step does not
  diagnose the color pairing.

- **Q:** What must a person see in the dark theme?
  **A:** The close control on the receipt sheet is readable against the
  sheet behind it, at contrast of at least 4.5.

- **Q:** What happens to the light theme?
  **A:** It stays readable. The same bar of 4.5 still holds for the close
  control and for the receipt text the standing check already covers, in
  the light theme and in the default theme.

- **Q:** Does this task change what a receipt means?
  **A:** No. Who may record a receipt, what a full or partial receipt
  means, and what a recipient may learn stay as they are.

- **Q:** May the shared Mini App script carry this fix?
  **A:** No. `wishenka/web/static/app.js` stays unchanged and free of the
  substring `receipt` (WISHENKA-214).

- **Q:** Are the other open sprint failures part of this task?
  **A:** No. WISHENKA-267, WISHENKA-283, WISHENKA-298, WISHENKA-311,
  WISHENKA-354, WISHENKA-356, and WISHENKA-357 stay out of scope.
