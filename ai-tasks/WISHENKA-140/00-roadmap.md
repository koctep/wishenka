# Roadmap: WISHENKA-140

## Task Metadata

- **Implementation language**: Python / JavaScript

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-140/10-requirements.md`
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-140/20-architecture.md`
- [x] **STEP 3: Failing Repro Test**
  - [x] `tests/test_csp_inline_removal_repro.py`
- [x] **STEP 4: Development**
  - [x] Extracted `base.html` inline `<script>` into `wishenka/web/static/app.js` (IIFE with `'use strict'`, JSDoc, `window.prepareCsrf`, loaded with `defer` after `htmx.org` and before `wishlist.js`/`receipt.js`)
  - [x] Added delegated `click` handlers in `app.js` for `[data-clear-target]` and `[data-qty-step][data-qty-target]` (with `min`/`max` clamping and `NaN` fallback) and replaced all 6 inline `onclick` attributes in `item_edit_modal.html`, `item_archive_modal.html`, and `item_preview_card.html`
  - [x] Updated `test_receipt_static_script.py`, `test_wish_card_giver_controls.py`, and `test_reservations_cabinet_ui.py` to inspect `/static/app.js` and extended `test_pages_and_partials_carry_no_inline_handlers` to modal/preview partials; verified `test_csp_inline_removal_repro.py` (6/6) and `make analyze` (`ruff`, `mypy`) pass
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-140/40-code-cleanup.md`
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-140/50-observability.md`
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-140/60-tech-debt.md`
- [x] **STEP 8: Dev Docs**
  - `doc/dev/miniapp.md` (added section 9.8.2 documenting `static/app.js`, `static/settings.js`, `defer` load order, `window.prepareCsrf`, `<body>`/`.settings-page` `data-*` contracts, delegated `[data-clear-target]` and `[data-qty-step][data-qty-target]` handlers, and CSP readiness invariant/tests; updated 9.8.1 and 9.9)
  - `doc/dev/wishlists.md` (updated template/static tree and `base.html` specification for `app.js`, `receipt.js`, `settings.js`, and zero inline scripts)
  - `doc/dev/gift-receipt.md` (updated CSP readiness note for WISHENKA-140)
  - `doc/dev/i18n.md` (updated `data-i18n-prepare-error` / `data-i18n-busy-error` consumer reference to `static/app.js`)
  - `doc/dev/testing.md` (updated static-script / CSP regression test reference to `test_csp_inline_removal_repro.py` and `test_receipt_static_script.py`)
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-140/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-140/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-140/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-140/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-140/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
