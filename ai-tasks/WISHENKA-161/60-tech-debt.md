# WISHENKA-161: Technical Debt Analysis

## Shortcuts Taken

1. **Custom `inert` / `aria-hidden` + `Tab` trap instead of native `<dialog>.showModal()`**:
   - `wishenka/web/static/receipt.js` isolates background content by walking ancestors from `#item-modal-container` to `document.body` (`setBackgroundInert`) and trapping `Tab` / `Shift+Tab` in a `document`-level `keydown` listener (`getFocusable`).
   - This avoids refactoring the `#item-modal-container` HTMX swap target and avoids touching `wishenka/web/templates/base.html` (whose inline script is SHA-256-pinned), at the cost of maintaining custom modal-isolation code.
2. **Thresholded stepper (`RECEIPT_SELECT_MAX = 20`) applied only to `item_receipt_modal.html`**:
   - `wishenka/web/routes/receipts_ui.py` passes `select_max = RECEIPT_SELECT_MAX` (`20`) to `partials/item_receipt_modal.html`, rendering `.quantity-control` with `-` / `+` `[data-receipt-step]` buttons for `remaining > 20`.
   - `wishenka/web/templates/partials/receipt_edit_modal.html` still renders a bare `<input id="receipt-edit-quantity" type="number">` without `.quantity-control` or `.btn-step` buttons, and `wishenka/web/static/miniapp.css` only applies the `44px` `--touch-target` rule to `.receipt-sheet select` and `.receipt-sheet .quantity-control input` (leaving `#receipt-edit-quantity` unstyled for touch-target height).
3. **Transient client-side `gifted-items-details` open-state preservation**:
   - `submitReceipt(form)` in `receipt.js` captures `details.gifted-items-details.open` before `htmx.ajax` and `finishAttempt(form, giftedWasOpen)` restores `details.open = true` after the swap.
   - If `#gifted-items-section` is ever OOB-replaced outside `submitReceipt` (or on page reload), the expanded state is not preserved.

## Code Quality Issues

1. **Focus restoration after OOB replacement of `#gifted-items-section` (`wishenka/web/static/receipt.js`)**:
   - `restoreFocusToPage()` falls back to `openerElement` when `openerCardId` is empty, and then to `#list-notice`. When a receipt edit or cancel modal is opened from inside `#gifted-items-section` and the section is OOB-replaced (`hx-swap-oob="outerHTML"`), `openerElement.isConnected` becomes `false`, so focus falls back to `#list-notice` instead of the updated `#gifted-item-{id}` or `details.gifted-items-details > summary`.
2. **Multi-purpose `click` listener in `receipt.js`**:
   - The `document` `click` listener (lines 213–242) combines opener tracking (`.btn-receipt-item`), stepper adjustments (`[data-receipt-step]`), and dialog dismissal (`[data-modal-close]` / backdrop click). Extracting small helper functions for stepper handling would keep the listener easier to scan.
3. **Hardcoded English fallback strings in `receipt.js`**:
   - `DEFAULT_GENERIC_FAILURE` and `DEFAULT_SUMMARY_TEMPLATE` are hardcoded English strings used when `data-i18n-receipt-failure` or `data-i18n-receipt-summary` is absent from `document.body`. Acceptable as defensive defaults since templates always provide the `data-i18n-*` attributes.

## Missing Tests

All new and modified Python test files declare explicit `pytest.mark.timeout` markers (`tests/test_receipt_ui_routes.py`: `pytestmark = pytest.mark.timeout(30)`; `tests/test_receipt_accessibility_browser.py`: `pytestmark = [pytest.mark.timeout(45), pytest.mark.browser]`). No timeout-marker blockers exist.

Remaining coverage gaps:
1. **`RECEIPT_SELECT_MAX` boundary (`20` vs `21`)**: `tests/test_receipt_ui_routes.py` tests `remaining=1`, `remaining=5`, and `remaining=500`, but does not explicitly assert the exact boundary (`remaining=20` renders `<select>`, `remaining=21` renders `.quantity-control`).
2. **Out-of-range numeric input clamping / validation in browser**: `tests/test_receipt_accessibility_browser.py` verifies `+` step and valid numeric input (`42`), but does not test entering `0` or `501` (for `remaining=500`) to assert `change` clamping and `checkValidity()`/`reportValidity()` submission blocking.
3. **Accessibility and focus return for `receipt_edit_modal.html` and `receipt_cancel_modal.html`**: `aria-modal="true"` and `tabindex="-1"` on `#receipt-feedback` were added to both templates, but browser focus-return and touch-target checks in `tests/test_receipt_accessibility_browser.py` only exercise `item_receipt_modal.html`.

## Performance Concerns

No performance concerns.
- `setBackgroundInert` touches only immediate siblings along the short ancestor chain from `#item-modal-container` to `document.body`.
- `getFocusable` queries only descendants of `#item-receipt-modal` on `Tab` / `Shift+Tab`.
- Thresholding `<select>` at `RECEIPT_SELECT_MAX = 20` eliminates rendering hundreds of `<option>` DOM nodes for large-quantity wishes.

## Follow-up Tasks

- **Pre-existing test failures (out of WISHENKA-161 scope)**:
  - `NON-BLOCKER — pre-existing`: `tests/test_receipt_static_script.py::test_inline_script_is_unchanged_and_free_of_receipt_code` — Jira: [WISHENKA-214](https://pypost.atlassian.net/browse/WISHENKA-214)
  - `NON-BLOCKER — pre-existing`: `tests/test_receipt_modal_browser.py::test_unmarked_error_neither_shows_notice_nor_reloads` — Jira: [WISHENKA-220](https://pypost.atlassian.net/browse/WISHENKA-220)
- **Suggested future improvements (non-blocking)**:
  - Align `receipt_edit_modal.html` with `.quantity-control` / `44px` touch-target styling and add `tests/test_receipt_accessibility_browser.py` coverage for edit/cancel modals and `#gifted-items-section` focus restoration. Jira: [WISHENKA-221](https://pypost.atlassian.net/browse/WISHENKA-221)
  - Add `RECEIPT_SELECT_MAX` boundary (`20` vs `21`) route test and out-of-range numeric input browser validation test. Jira: [WISHENKA-222](https://pypost.atlassian.net/browse/WISHENKA-222)
