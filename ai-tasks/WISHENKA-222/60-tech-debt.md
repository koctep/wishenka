# WISHENKA-222: Technical Debt Analysis

## Shortcuts Taken

- **Synthetic DOM events in browser validation test (`tests/test_receipt_accessibility_browser.py`)**: `test_large_quantity_out_of_range_validation_and_clamping` sets `inp.value` via `page.evaluate(...)`, dispatches synthetic `input` / `change` events, and invokes `document.querySelector(CONFIRM).click()` via JS rather than typing with keyboard events and clicking with the pointer. This was chosen intentionally to test `submitReceipt` (`checkValidity()`) before a `blur`/`change` event clamps the field, and is acceptable as-is.

## Code Quality Issues

- **Minor assertion overlap in `tests/test_receipt_ui_routes.py`**: `test_get_modal_large_quantity_renders_stepper_not_large_select` (`remaining=500`, lines 233–251) and the `remaining=21` branch of `test_get_modal_select_max_boundary` (lines 254–282) repeat similar `input[type="number"]` and `[data-receipt-step]` assertions. Low impact; keeping both keeps each test self-contained and readable.
- **Explicit pytest timeout markers**: Verified present on both modified test modules — `tests/test_receipt_ui_routes.py` uses `pytestmark = pytest.mark.timeout(30)` (line 64) and `tests/test_receipt_accessibility_browser.py` uses `pytestmark = [pytest.mark.timeout(45), pytest.mark.browser]` (line 32). No timeout-marker blockers.

## Missing Tests

1. **Empty (`""`, `valueMissing`) and fractional (`"1.5"`, `stepMismatch`) numeric inputs in `wishenka/web/static/receipt.js`**:
   - `test_large_quantity_out_of_range_validation_and_clamping` covers `"0"` (`rangeUnderflow`) and `"501"` (`rangeOverflow`), but does not test clearing the field (`""`) or entering a decimal (`"1.5"`). Note that in `updateSummary` (`wishenka/web/static/receipt.js` lines 190–193), `Number.parseInt("", 10)` yields `NaN`, causing an early return on `change` without resetting `field.value` to `"1"`.
2. **Edit-receipt modal (`receipt_edit_modal.html`) out-of-range validation**:
   - `receipt_edit_modal.html` also renders `input[type="number"][data-receipt-quantity]` (`#receipt-edit-quantity`) handled by `updateSummary` and `submitReceipt` in `receipt.js`, but out-of-range validation/clamping is only tested on `item_receipt_modal.html`.
3. **Stepper button boundary clamping (`handleStepClick` at `1` and `remaining`)**:
   - Clicking `-1` when `quantity == 1` and clicking `+1` when `quantity == remaining` in `wishenka/web/static/receipt.js` (lines 218–233) are not explicitly covered by browser tests.

## Performance Concerns

None. `test_get_modal_select_max_boundary` adds two lightweight in-process route requests, and `test_large_quantity_out_of_range_validation_and_clamping` reuses the existing Chromium CDP fixture (`_mobile_owner_page`) without launching additional browser instances.

## Follow-up Tasks

- `NON-BLOCKER` — Add browser test coverage (and decide whether `updateSummary` should clamp empty `""` input on `change`) for `valueMissing` (`""`), `stepMismatch` (`"1.5"`), stepper bounds (`1` / `remaining`), and `receipt_edit_modal.html` out-of-range validation in `tests/test_receipt_accessibility_browser.py`. — Jira: [WISHENKA-278](https://pypost.atlassian.net/browse/WISHENKA-278)
