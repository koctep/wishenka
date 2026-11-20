# WISHENKA-221: Technical Debt Analysis

## Shortcuts Taken

- **No `disabled` state on `.btn-step` at min/max boundaries**: In `wishenka/web/templates/partials/receipt_edit_modal.html` and `wishenka/web/static/receipt.js` (`handleStepClick`), decrement/increment buttons remain enabled when the quantity is at `1` or `max_allowed` (`data-remaining`); clicks at the boundary are clamped silently to `[1, remaining]`. This matches `wishenka/web/templates/partials/item_receipt_modal.html` and is a `NON-BLOCKER`, though disabling/updating `aria-disabled` at boundaries would improve screen-reader clarity.
- **`.quantity-control` markup duplicated across modal partials**: `wishenka/web/templates/partials/receipt_edit_modal.html` duplicates the `.quantity-control` stepper + numeric input HTML block already present in `wishenka/web/templates/partials/item_receipt_modal.html` (and `wishenka/web/templates/partials/item_edit_modal.html`). Keeping it inline avoided refactoring shared Jinja macros in this task (`NON-BLOCKER`).

## Code Quality Issues

- **Duplicated touch-target and modal-isolation assertions in `tests/test_receipt_accessibility_browser.py`**:
  - `test_edit_modal_touch_targets_and_stepper` (lines 438–458) duplicates the ~20-line JavaScript `getBoundingClientRect()` / `document.elementFromPoint()` check from `test_mobile_touch_targets_and_quick_add_overlay` (lines 319–339). Extracting a shared `_assert_touch_targets(page: CdpPage)` helper would remove this duplication (`NON-BLOCKER`).
  - `test_modal_semantics_background_isolation_and_tab_trap` (lines 78–118) retains an inline copy of the background-isolation and `Tab`/`Shift+Tab` assertions that were extracted into `_assert_modal_isolation_and_trap(page)` (lines 358–398) for the edit/cancel tests (`NON-BLOCKER`).
- **Misleading function name and redundant selector in `wishenka/web/static/receipt.js`**:
  - `updateSummary(field, clampValue)` now clamps `[data-receipt-quantity]` values even when `[data-receipt-summary]` is absent (as in `receipt_edit_modal.html`). Renaming it (e.g. `syncQuantityField` or separating `clampQuantity` from `updateSummary`) would better reflect its responsibility (`NON-BLOCKER`).
  - `PRIMARY_CONTROL_SELECTOR` still lists both `'[data-receipt-modal] [data-receipt-quantity]'` and `'[data-receipt-modal] #receipt-edit-quantity'`; the latter is now redundant because `#receipt-edit-quantity` carries `data-receipt-quantity` (`NON-BLOCKER`).

## Missing Tests

- **Timeout markers check**: `tests/test_receipt_accessibility_browser.py` declares module-level `pytestmark = [pytest.mark.timeout(45), pytest.mark.browser]` on line 32 — all 7 tests have an explicit 45-second timeout (**no blocker**).
- **Non-blocking coverage gaps in `tests/test_receipt_accessibility_browser.py`**:
  - **Cancel button / backdrop dismissal on edit & cancel modals**: `test_edit_and_cancel_modal_accessibility_and_focus_restoration` verifies `Escape` dismissal, but does not explicitly exercise clicking `.btn-modal-close` or the modal backdrop on edit/cancel dialogs (`NON-BLOCKER`).
  - **Edit-modal `change` clamping & stepper boundary clicks**: No browser assertion checks out-of-range clamping (`0` -> `1`, `> max_allowed` -> `max_allowed`) on `change` or clicking `-` at `1` / `+` at `max_allowed` in `receipt_edit_modal.html` (`NON-BLOCKER`).
  - **Blocked edit/cancel modal rendering (`{% if blocked %}`)**: No browser test opens an edit or cancel dialog in the `blocked` state to verify `#receipt-feedback` focus and `.btn-modal-close` dismissal (`NON-BLOCKER`).

## Performance Concerns

None. All changes in `wishenka/web/static/receipt.js` use existing delegated `document` event listeners with O(1) DOM lookups, and `wishenka/web/templates/partials/receipt_edit_modal.html` adds only static markup.

## Follow-up Tasks

- `NON-BLOCKER`: Extract `_assert_touch_targets(page)` and reuse `_assert_modal_isolation_and_trap(page)` in `tests/test_receipt_accessibility_browser.py`; add browser test cases for `.btn-modal-close`/backdrop dismissal, `change`-event clamping, and `blocked` state on edit/cancel modals. — Jira: [WISHENKA-276](https://pypost.atlassian.net/browse/WISHENKA-276)
- `NON-BLOCKER`: Clean up `receipt.js` (`PRIMARY_CONTROL_SELECTOR` redundant `#receipt-edit-quantity` entry, clarify/split `updateSummary` vs clamping) and consider extracting a shared Jinja2 macro for `.quantity-control` across receipt/item modal partials. — Jira: [WISHENKA-277](https://pypost.atlassian.net/browse/WISHENKA-277)
