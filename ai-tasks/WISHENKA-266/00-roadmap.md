# Roadmap: WISHENKA-266

## Task Metadata

- **Implementation language**: CSS (receipt sheet appearance) and Python
  (the existing browser check)

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-266/00-roadmap.md` created from the template
  - Implementation language recorded in Task Metadata: CSS and Python
  - `ai-tasks/WISHENKA-266/10-requirements.md` written: in the dark theme the
    receipt sheet close control meets contrast of at least 4.5; light and
    the default theme stay readable
  - Awaiting review and the acceptance gate (the gate owner marks `[x]`)
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-266/20-architecture.md` written
  - Dark failure is inherited `#f5f5f5` on the button’s opaque `--surface`
    (`#ffffff`), contrast 1.090230993517392
  - Measured selector is `.receipt-sheet .btn-modal-close` in
    `wishenka/web/static/miniapp.css`, paired with `--receipt-bg` and
    `--receipt-text` (already present; dark probe 14.94)
  - Awaiting review and the acceptance gate (the gate owner marks `[x]`)
- [x] **STEP 3: Failing Repro Test**
  - [/] `ai-tasks/WISHENKA-266/30-failing-repro.md` written. N/A — no new red test; the standing contrast nodes passed when the app could load. Isolated setup ERROR is WISHENKA-357 and out of scope.
- [x] **STEP 4: Development**
  - [x] Left `wishenka/web/static/miniapp.css` unchanged. The close control
    already uses `background: var(--receipt-bg)` and
    `color: var(--receipt-text)` on `.receipt-sheet .btn-modal-close`.
  - [x] `.venv/bin/pytest
    tests/test_receipt_modal_browser.py::test_stale_giver_card_is_neutral
    tests/test_receipt_theme_browser.py -q` passed 4 tests, including
    fallback, light, and dark. No contrast assertion failed, so the
    stylesheet stayed as it is. `app.js` and the WishlistStore cycle
    (WISHENKA-357) were not changed.
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-266/40-code-cleanup.md` written
  - No cleanup edit required. Close-button rule already in
    `wishenka/web/static/miniapp.css`. `app.js` and `miniapp.css` not edited.
  - `make analyze` exited 0: Ruff all checks passed, 306 files already
    formatted, mypy no issues in 306 source files. WISHENKA-357 not fixed.
  - Awaiting review and the acceptance gate (the gate owner marks `[x]`)
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-266/50-observability.md` written
  - No production log added. The change is the existing CSS pair on the
    receipt close button, not a server event. An operator still sees the
    existing receipt-dialog request logs; this step adds none.
  - Awaiting review and the acceptance gate (the gate owner marks `[x]`)
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-266/60-tech-debt.md` written
  - No new technical debt. The close button already uses
    `background: var(--receipt-bg)` and `color: var(--receipt-text)`.
    Product code was not edited.
  - The isolated pytest `ImportError` is existing work, already
    WISHENKA-357. It is not a new follow-up. No new follow-ups.
  - User documentation under `doc/` was left unchanged.
  - Awaiting review and the acceptance gate (the gate owner marks `[x]`)
- [x] **STEP 8: Dev Docs**
  - `doc/dev/` already matches the receipt close control and was left
    unchanged. No new section.
  - `doc/dev/miniapp.md` already states `.receipt-sheet .btn-modal-close`
    uses `background: var(--receipt-bg)` and `color: var(--receipt-text)`.
    No sentence says that control inherits a light surface or fails
    contrast.
  - Isolated pytest of `tests/test_receipt_theme_browser.py` still errors
    on the existing WishlistStore cycle (WISHENKA-357). That issue is not
    fixed. The three theme nodes pass when collected after
    `tests/test_receipt_modal_browser.py::test_stale_giver_card_is_neutral`.
  - Awaiting review and the acceptance gate (the gate owner marks `[x]`)
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-266/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-266/20-architecture.md`

### STEP 3: Failing Repro

- `ai-tasks/WISHENKA-266/30-failing-repro.md` (N/A — standing contrast check; no new red test)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-266/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-266/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-266/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
