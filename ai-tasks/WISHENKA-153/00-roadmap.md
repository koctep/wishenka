# Roadmap: WISHENKA-153

## Task Metadata

- **Implementation language**: Python 3.12+ (FastAPI backend and Jinja2/HTMX web routes), JavaScript (classic script), CSS

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - [/] `ai-tasks/WISHENKA-153/00-roadmap.md` created from template
  - [/] Implementation language recorded in Task Metadata: Python 3.12+ (FastAPI/Jinja2/HTMX), JavaScript, CSS
  - [/] `ai-tasks/WISHENKA-153/10-requirements.md` written with business requirements, corner cases, and autonomous product decisions in Q&A
- [x] **STEP 2: High-Level Architecture Design**
  - [/] `ai-tasks/WISHENKA-153/20-architecture.md` written with codebase research, implementation plan (including Step 3 failing repros), Mermaid diagram, module responsibilities, transaction flow, and interfaces
- [x] **STEP 3: Failing Repro Test**
  - [/] `tests/test_receipt_undo_correction_repro.py` — 5 failed in 19.33s (`WishlistService.cancel_item_receipt` missing, `WishlistService.correct_item_receipt` missing, `ReceiptEntryDTO.id` missing)
- [x] **STEP 4: Development**
  - [x] Iteration 1 (Domain & Store): Added `ReceiptNotFoundError`, `ReceiptEntryDTO.id`, `WishlistService.cancel_item_receipt` & `correct_item_receipt` (with fixed-order guards, date/`is_approximate` preservation, no-op handling, and `SharedEvent` queuing for open-promise givers), and `WishlistStore._flush_receipt_effects` `UPDATE`/`DELETE` on `wl_receipts`
  - [x] Iteration 2 (Notifications & i18n): Registered `receipt_reverted` and `receipt_increased` in `SAFE_SHARED_EVENTS`, mapped both to `gift_received` settings and open-promise/non-recipient checks in `wishenka/notices/reminders.py`, and added RU/EN strings (`notices.receipt_reverted`, `web.receipt.*`) in `wishenka/i18n/catalog.py`
  - [x] Iteration 3 (JSON API): Added `DELETE` and `PATCH /api/wishlists/{wishlist_id}/items/{item_id}/receipts/{receipt_id}` with `Idempotency-Key` support and `ReceiptNotFoundError` (`receipt_not_found`, 404) in `wishenka/web/routes/receipts.py`
  - [x] Iteration 4 (Mini App UI & Tests): Added `GiftedAct.receipt_id`, per-act edit/cancel buttons on active lists in `partials/gifted_items_section.html`, `receipt_edit_modal.html` & `receipt_cancel_modal.html`, `GET`/`POST` edit/cancel routes with OOB updates in `wishenka/web/routes/receipts_ui.py`, `receipt.js` support without touching `base.html` inline script, and updated affected existing tests; `tests/test_receipt_undo_correction_repro.py` and static checks pass
- [x] **STEP 5: Code Cleanup**
  - [/] `ai-tasks/WISHENKA-153/40-code-cleanup.md` written; `ruff check`, `ruff format --check`, `mypy` (203 files) and 90 receipt/UI tests pass; wrapped >100-char line in `wishenka/web/static/receipt.js`
- [x] **STEP 6: Observability**
  - [/] `ai-tasks/WISHENKA-153/50-observability.md` written; verified service/store/notice/API logging for privacy invariants and added `INFO` logs (`ui_receipt_entry_form_opened`, `receipt_corrected_http`, `receipt_cancelled_http`) to `wishenka/web/routes/receipts_ui.py`
- [x] **STEP 7: Technical Debt Analysis**
  - [/] `ai-tasks/WISHENKA-153/60-tech-debt.md` written with shortcuts, code quality issues, missing tests (all receipt/UI test files verified to have explicit `pytestmark = pytest.mark.timeout(...)`), performance concerns, and follow-up tasks (including pre-existing `tests/test_receipt_static_script.py::test_inline_script_is_unchanged_and_free_of_receipt_code` tracked as `NON-BLOCKER — pre-existing` in WISHENKA-214)
- [x] **STEP 8: Dev Docs**
  - [/] `doc/dev/gift-receipt.md`: documented `cancel_item_receipt` & `correct_item_receipt`, `ReceiptNotFoundError` (`receipt_not_found`), `DELETE`/`PATCH /api/wishlists/{wishlist_id}/items/{item_id}/receipts/{receipt_id}`, `ReceiptEntryDTO.id`, Mini App «Подаренные» edit/cancel UI routes & modals (`receipt_edit_modal.html`, `receipt_cancel_modal.html`), `reminder_outbox` (`receipt_reverted`/`receipt_increased`), logging events, and `tests/test_receipt_undo_correction_repro.py`
  - [/] `doc/dev/notifications.md`: documented `receipt_reverted` & `receipt_increased` in `SAFE_SHARED_EVENTS`, `gift_received` preference mapping, and live verification rules in `claim_reminder`/`refresh_reminder`
  - [/] `doc/dev/miniapp.md`: documented per-act edit/cancel controls in «Подаренные» (`partials/gifted_items_section.html`) and `receipts_ui` entry-level log events
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-153/00-roadmap.md`
- `ai-tasks/WISHENKA-153/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-153/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-153/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-153/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-153/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
