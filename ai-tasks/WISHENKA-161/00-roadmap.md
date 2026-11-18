# Roadmap: WISHENKA-161

## Task Metadata

- **Implementation language**: Python, JavaScript

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - [/] `ai-tasks/WISHENKA-161/00-roadmap.md` created from template; Implementation language set to Python, JavaScript
  - [/] `ai-tasks/WISHENKA-161/10-requirements.md` written (covering T-2 of `ai-tasks/WISHENKA-24/60-tech-debt.md`: focus return on receipt/refusal, modal focus containment and screen-reader isolation, «Подаренные» state preservation, scalable quantity selection, and browser verification of focus, 44 px touch targets, and quick-add bar overlay)
- [x] **STEP 2: High-Level Architecture Design**
  - [/] `ai-tasks/WISHENKA-161/20-architecture.md` written (focus lifecycle, `inert`/`aria-hidden` isolation & Tab trap, `gifted-items-details` open-state preservation, thresholded quantity stepper, mobile 44 px touch targets & quick-add layering, and Step 3 Chromium CDP failing-repro plan)
- [x] **STEP 3: Failing Repro Test**
  - [/] `tests/test_receipt_ui_routes.py::test_get_modal_large_quantity_renders_stepper_not_large_select` — red (`<select>` with 500 `<option>`s rendered instead of `input[type="number"]` + `[data-receipt-step]` stepper)
  - [/] `tests/test_receipt_accessibility_browser.py` (5 browser CDP tests at `390x844`) — all 5 red: missing `aria-modal="true"` / `inert` isolation / `Tab` trap, focus lost on partial receipt (`PageWaitTimeout`), `details.gifted-items-details.open` reset to `false` on OOB swap, `<select>` rendered for `remaining=500`, and missing stepper controls in touch-target check
  - [/] `tests/browser_cdp.py` — added `Tab` and `Shift+Tab` support to `CdpPage.press_key`
- [x] **STEP 4: Development**
  - [x] Iteration 1: Added `aria-modal="true"` and `tabindex="-1"` on `#receipt-feedback` in `item_receipt_modal.html`, `receipt_edit_modal.html`, and `receipt_cancel_modal.html`; added `tabindex="-1"` on `#list-notice` in `wishlist_detail.html`; added `RECEIPT_SELECT_MAX = 20` in `receipts_ui.py` with thresholded `<select>` (`<= 20`) vs `.quantity-control` stepper/number input (`> 20`) in `item_receipt_modal.html`; updated `miniapp.css` for 44 px touch targets on `.receipt-sheet .quantity-control input` and `.btn-step`.
  - [x] Iteration 2: Updated `receipt.js` with ancestor-sibling `inert`/`aria-hidden` isolation (`setBackgroundInert`), `Tab`/`Shift+Tab` focus trap (`getFocusable`), focus lifecycle for open/dismissal/partial/full receipt/refusal (`focusDialog`, `restoreFocusToPage`, `finishAttempt`), `details.gifted-items-details` open-state preservation across OOB swaps, and `[data-receipt-step]`/`[data-receipt-quantity]` stepper & numeric validation (preserving `REASON_LIKE` and `base.html` SHA-256 invariants). Fixed `monkeypatch` ordering in `tests/test_receipt_accessibility_browser.py::test_focus_return_partial_full_and_refusal` so `open_receipt_dialog` GET does not consume the simulated 503 busy state.
- [x] **STEP 5: Code Cleanup**
  - [/] `ai-tasks/WISHENKA-161/40-code-cleanup.md` written; verified `ruff check`, `ruff format --check`, `mypy` (all 0 issues across 204 files), line lengths <= 100, timeout markers, and receipt test suites (53/54 passed; 1 pre-existing `base.html` inline-script failure unrelated to WISHENKA-161).
- [x] **STEP 6: Observability**
  - [/] `ai-tasks/WISHENKA-161/50-observability.md` written; verified existing structured logging in `wishenka/web/routes/receipts_ui.py` (`tests/test_receipt_ui_observability.py` passed) and `receipt.js` `console.*` prohibition (`tests/test_receipt_static_script.py`); no new logs or metrics required for client-side UI/accessibility/stepper changes.
- [x] **STEP 7: Technical Debt Analysis**
  - [/] `ai-tasks/WISHENKA-161/60-tech-debt.md` written (documented custom `inert`/Tab-trap vs native `<dialog>`, `receipt_edit_modal.html` touch-target/stepper gap, `#gifted-items-section` OOB focus fallback, missing `20`/`21` boundary & invalid-input browser tests, verified explicit `pytest.mark.timeout` markers, and recorded pre-existing non-blockers `WISHENKA-214` and `WISHENKA-220`).
- [x] **STEP 8: Dev Docs**
  - [/] `doc/dev/gift-receipt.md` updated (WISHENKA-161 modal `aria-modal="true"`, `inert`/`aria-hidden` isolation, `Tab`/`Shift+Tab` trap, focus lifecycle across dismissal/partial/full/refusal, `details.gifted-items-details` open-state preservation, `RECEIPT_SELECT_MAX = 20` `.quantity-control` stepper, resolved S-3/S-4, and `tests/test_receipt_accessibility_browser.py`)
  - [/] `doc/dev/miniapp.md` updated (`--layer-receipt`/`--touch-target` on `.receipt-sheet` stepper controls, `#list-notice[tabindex="-1"]`, and cross-reference to `gift-receipt.md`)
  - [/] `doc/dev/testing.md` updated (`Tab`/`Shift+Tab` in `tests/browser_cdp.py` and 5-test `tests/test_receipt_accessibility_browser.py` suite at `390x844`)
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-161/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-161/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-161/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-161/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-161/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
