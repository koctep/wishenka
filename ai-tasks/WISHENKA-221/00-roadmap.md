# Roadmap: WISHENKA-221

## Task Metadata

- **Implementation language**: Python, JavaScript

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - [/] `ai-tasks/WISHENKA-221/10-requirements.md`
- [x] **STEP 2: High-Level Architecture Design**
  - [ ] `ai-tasks/WISHENKA-221/20-architecture.md`
- [x] **STEP 3: Failing Repro Test**
  - [/] `tests/test_receipt_accessibility_browser.py`
- [x] **STEP 4: Development**
  - [x] Wrapped `#receipt-edit-quantity` in `.quantity-control` with `-`/`+` `.btn-step` buttons, `data-receipt-quantity`, `data-remaining`, `step="1"`, and `inputmode="numeric"` in `wishenka/web/templates/partials/receipt_edit_modal.html`.
  - [x] Updated `wishenka/web/static/receipt.js` to track `.btn-receipt-edit`/`.btn-receipt-cancel` openers (`openerGiftedItemId`), restore focus to opener / `#gifted-item-{id}` / `details.gifted-items-details > summary` / `#list-notice`, clamp `[data-receipt-quantity]` in `updateSummary` even without `[data-receipt-summary]`, and extract `handleStepClick(stepBtn)`.
  - [x] Fixed `expected_race` quantity (`n=2`) in `tests/test_receipt_accessibility_browser.py` and formatted the test file; verified all 7 browser tests in `tests/test_receipt_accessibility_browser.py`, `ruff check`, `ruff format --check`, and `mypy` pass.
- [x] **STEP 5: Code Cleanup**
  - [/] `ai-tasks/WISHENKA-221/40-code-cleanup.md`
- [x] **STEP 6: Observability**
  - [/] `ai-tasks/WISHENKA-221/50-observability.md`
- [x] **STEP 7: Technical Debt Analysis**
  - [/] `ai-tasks/WISHENKA-221/60-tech-debt.md`
- [x] **STEP 8: Dev Docs**
  - [x] `doc/dev/gift-receipt.md`
  - [x] `doc/dev/miniapp.md`
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-221/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-221/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-221/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-221/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-221/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
