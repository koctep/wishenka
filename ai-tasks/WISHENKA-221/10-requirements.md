# WISHENKA-221: Receipt Edit Touch-Target Alignment and Edit/Cancel Modal Accessibility Verification

## Goals

Ensure a consistent, mobile-friendly, and accessible experience across all gift-receipt management dialogs (recording, editing, and cancelling a receipt), and verify these guarantees automatically in a real mobile browser:

1. **Consistent mobile quantity input**: Wishlist owners editing a gift receipt on a mobile device should have the same comfortable, touch-friendly quantity adjustment experience (stepper controls and minimum 44 px tap targets) as when recording a new receipt.
2. **Predictable keyboard focus after editing or cancelling a receipt**: When a wishlist owner opens the edit or cancel dialog from the "Gifted" items section and either dismisses or submits it, keyboard and screen-reader focus must return to a meaningful element in the "Gifted" section (or the section summary/notice if the item was fully removed) rather than being lost or jumping unexpectedly to an unrelated part of the page.
3. **Regression protection for edit and cancel dialogs**: Automated mobile-viewport browser tests must cover modal semantics, background isolation, keyboard navigation, touch-target sizes, and focus restoration for both the edit and cancel receipt dialogs.

## User Stories

- **US-1 (Mobile quantity adjustment when editing a receipt)**: As a **Wishlist Owner** on a mobile device, I want the quantity input and +/- adjustment controls in the receipt-edit dialog to meet at least 44×44 px touch-target dimensions and behave consistently with the receipt-creation dialog, so I can adjust a gift quantity accurately with one thumb without mis-tapping.
- **US-2 (Keyboard & screen-reader focus restoration from Gifted items)**: As a **Wishlist Owner** using a keyboard or screen reader, when I open a receipt edit or cancel dialog from an entry in the "Gifted" items section and then close it or confirm the change, I want focus to return to the relevant gifted-item entry (or to the "Gifted" section header / page notice if that entry no longer exists), so I keep my place in the list.
- **US-3 (Modal accessibility parity for edit and cancel dialogs)**: As a **Wishlist Owner** using assistive technology, I want the receipt-edit and receipt-cancel dialogs to isolate background page content, trap keyboard navigation inside the dialog, support closing via Escape, and announce validation or conflict errors just like the receipt-creation dialog.

## Definition of Done

1. **Edit-dialog quantity control & touch targets**:
   - The receipt-edit dialog presents quantity adjustment with decrement/increment stepper controls and numeric input, matching the visual style and interaction of the receipt-creation dialog.
   - All interactive controls in the receipt-edit dialog (decrement/increment buttons, quantity input, confirm button, cancel/close button) have rendered hit areas of at least 44×44 px on a mobile viewport (390×844).
   - Stepper buttons respect the minimum (`1`) and maximum allowed quantity for the receipt being edited, and invalid/out-of-range submissions are prevented or clamped cleanly.
2. **Focus restoration for Gifted items**:
   - Dismissing (Escape or Cancel) an edit or cancel dialog opened from the "Gifted" section returns focus to the triggering control or its gifted-item entry.
   - Submitting an edit or cancel dialog that updates the "Gifted" section restores focus to the updated gifted-item entry (if still present) or to the "Gifted" section toggle / page notice (if the item or section was removed), while preserving the expanded state of the "Gifted" section when items remain.
3. **Automated browser accessibility & UX coverage**:
   - Browser tests at mobile viewport (390×844) verify modal semantics, background isolation, `Tab`/`Shift+Tab` trapping, `Escape` dismissal, touch-target dimensions (>= 44 px), and focus restoration for both receipt-edit and receipt-cancel workflows (including error/refusal feedback focus).
   - All existing and new tests, linters, and type checks pass without regressions.

## Task Description

### Problem Context

During WISHENKA-161, accessibility improvements (modal isolation, focus trapping, focus return, and 44 px touch targets with `.quantity-control` steppers) were implemented for the primary receipt-creation dialog, and automated browser tests were added for that flow. A follow-up audit (`ai-tasks/WISHENKA-161/60-tech-debt.md`) identified three remaining gaps:

1. The receipt-edit dialog still uses a plain number input without +/- stepper controls and without the 44 px minimum touch-target height applied to its quantity input.
2. When an edit or cancel dialog is opened from the "Gifted" items section and the section refreshes after submission, the original triggering button is replaced, causing focus restoration to lose its place in the "Gifted" section and fall back to the top-level page notice.
3. Automated browser accessibility and touch-target tests only exercise the receipt-creation dialog, leaving the edit and cancel dialogs unverified in a real browser.

### Programming Language

- **Python, JavaScript** (plus HTML templates and CSS styling used by the mini-app web UI and pytest browser test suite).

### Scope and Boundaries

- **In scope**:
  - Receipt-edit dialog quantity control structure and 44 px mobile touch-target styling.
  - Focus restoration behavior when dismissing or submitting receipt-edit and receipt-cancel dialogs opened from the "Gifted" items section.
  - Automated mobile-viewport browser tests for receipt-edit and receipt-cancel dialogs (accessibility semantics, focus trap, focus restoration, error feedback focus, and >= 44 px touch targets).
- **Out of scope**:
  - Receipt-creation threshold (`RECEIPT_SELECT_MAX` boundary tests) and out-of-range clamping tests for the creation dialog (tracked separately in `WISHENKA-222`).
  - Replacing the custom modal isolation mechanism with native `<dialog>.showModal()`.
  - Changes to backend receipt business rules, permissions, or database schema.
  - Pre-existing unrelated test failures (`WISHENKA-214`, `WISHENKA-220`).

### Main Business Entities

- **Wishlist Owner**: Authenticated user who owns or edits the wishlist and manages recorded gift receipts.
- **Gift Receipt**: A recorded act of gifting a specific quantity of a wish item, which can be edited (quantity adjusted within allowed limits) or cancelled.
- **Gifted Items Section**: Collapsible summary section on the wishlist page listing items that have received gifts and exposing Edit/Cancel actions per receipt.
- **Receipt Edit / Cancel Dialog**: Modal dialog presented over the wishlist page for modifying a receipt's quantity or cancelling a receipt.

### Non-Functional Requirements

- **Accessibility (WCAG / Mobile UX)**: All interactive controls in receipt dialogs must meet >= 44×44 px touch targets on mobile viewports; keyboard focus must remain trapped inside open modals and return predictably on close/submit.
- **Localization & Security**: Existing i18n labels and inline-script security constraints must be preserved without introducing hardcoded user-facing strings or inline scripts.
- **Testability**: All new automated browser tests must include explicit timeouts and run deterministically without external network calls.

### Constraints and Assumptions

- The edit dialog always edits an existing receipt whose allowed maximum depends on the item's remaining ungifted quantity plus the receipt's current quantity.
- No backend API or domain-model changes are needed unless required to support the edit dialog's UI state.

## Q&A

- **Q**: Why does `WISHENKA-221` exist as a separate task from `WISHENKA-161`?
  **A**: It addresses the non-blocking technical debt items documented in `ai-tasks/WISHENKA-161/60-tech-debt.md` so that receipt-edit and receipt-cancel dialogs achieve full parity with the receipt-creation dialog in mobile touch ergonomics, focus restoration, and browser test coverage.
