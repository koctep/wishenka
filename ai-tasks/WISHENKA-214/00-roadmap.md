# Roadmap: WISHENKA-214

## Task Metadata

- **Implementation language**: Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-214/10-requirements.md`
  - Wishlist authors must still see edit and archive failures in the dialog,
    and a refused gift receipt must keep the receipt flow's own feedback.
    The standing check that shared page behavior stays free of gift-receipt
    references must pass at the same time.
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-214/20-architecture.md`
  - Confirmed: `test_inline_script_is_unchanged_and_free_of_receipt_code` is gone.
    Successor `test_base_has_no_inline_scripts_and_loads_app_script_deferred` only
    forbids `/receipt` in comment-stripped `app.js` and is already green.
    `app.js` still names `X-Receipt-Refusal` and `.receipt-sheet`.
  - Design: `receipt.js` claims those responses in the capture phase with a
    neutral `detail.skipSharedDialog` flag. Shared `app.js` honors the flag
    and `[data-own-feedback]`, and no longer names the receipt header or sheet.
  - Failing repro compares `app.js` case-insensitively, so both
    `X-Receipt-Refusal` header reads and the lowercase `receipt` comments
    stay red.
- [x] **STEP 3: Failing Repro Test**
  - `tests/test_receipt_static_script.py::test_shared_app_script_has_no_gift_receipt_reference`
  - Red on current `app.js`: case-insensitive compare of the raw
    `/static/app.js` body and the same body after `strip_js_comments`
    still finds `X-Receipt-Refusal` (two header reads), `.receipt-sheet`,
    and the substring `receipt`. Comment stripping drops the prose and
    leaves those header reads failing.
- [x] **STEP 4: Development**
  - [x] Iteration 1: `receipt.js` claims every `X-Receipt-Refusal` response in the capture phase, sets `detail.skipSharedDialog`, and opts into the swap only for `REFUSAL_REASONS`. A capture `htmx:responseError` listener stops that header from reaching shared feedback. `app.js` returns on the flag, keeps the reorder and reservation exclusions, and uses `[data-own-feedback]` instead of `.receipt-sheet`. The shared script, comments included, has no `receipt` substring. The three receipt dialog roots carry `data-own-feedback`. Server headers, sentences, and roles are unchanged.
  - `tests/test_receipt_static_script.py::test_shared_app_script_has_no_gift_receipt_reference` is green. The rest of that file, the receipt refusal and reorder header unit tests, and the dialog, receipt, reorder, and reservation browser tests listed in the step report passed.
  - Pre-existing at `1acdffc`, not fixed here: `tests/test_receipt_modal_browser.py::test_unmarked_error_neither_shows_notice_nor_reloads` (WISHENKA-220, PageWaitTimeout) and `tests/test_receipt_modal_browser.py::test_busy_keeps_dialog_and_chosen_quantity` (WISHENKA-354, PageWaitTimeout waiting for the busy sentence).
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-214/40-code-cleanup.md`
  - Wrapped `data-own-feedback` onto its own line on the three receipt dialog
    roots. The attribute had pushed the opening tag past 100 characters.
  - Capture-phase note in `receipt.js` uses the file's block-comment style.
  - Case-insensitive `app.js` guard unchanged. `make analyze` passed.
    `tests/test_receipt_static_script.py` passed (11).
  - WISHENKA-220 and WISHENKA-354 were left alone.
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-214/50-observability.md`
  - No new log or metric. The client claim (`skipSharedDialog`,
    `data-own-feedback`) does not change the refusal the server already
    records (`receipt_refused`, `ui_receipt_form_refused`,
    `wish_archive_refused`). `receipt.js` still forbids `console.`.
    Response body, sentence, and title stay out of logs.
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-214/60-tech-debt.md`
  - No blocker against the acceptance criteria. `receipt.js` claims every
    `X-Receipt-Refusal` in the capture phase; `app.js` honors
    `skipSharedDialog` and `[data-own-feedback]` and names no gift receipt.
  - One unticketed follow-up: a test for modal-targeted
    `idempotency_conflict`, `data-own-feedback` on the three receipt
    dialog roots, and `htmx:responseError` `stopPropagation` so
    `#feedback` stays empty. WISHENKA-220 and WISHENKA-354 stay
    `NON-BLOCKER — pre-existing`. User docs under `doc/` were left unchanged.
    Stale `doc/dev/` wording is Step 8.
- [x] **STEP 8: Dev Docs**
  - `doc/dev/gift-receipt.md`: `receipt.js` claims every `X-Receipt-Refusal`
    in the capture phase (`skipSharedDialog`, closed `REFUSAL_REASONS` opt-in,
    `htmx:responseError` `stopPropagation`). The three dialog roots carry
    `data-own-feedback`.
  - `doc/dev/miniapp.md`: `app.js` honors `skipSharedDialog` and
    `[data-own-feedback]` and does not name the receipt header or
    `.receipt-sheet`.
  - No user-facing copy change. No Jira issue.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-214/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-214/20-architecture.md`

### STEP 3: Failing Repro

- `tests/test_receipt_static_script.py::test_shared_app_script_has_no_gift_receipt_reference`

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-214/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-214/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-214/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
