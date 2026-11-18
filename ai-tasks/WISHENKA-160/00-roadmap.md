# Roadmap: WISHENKA-160

## Task Metadata

- **Implementation language**: Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - [x] `ai-tasks/WISHENKA-160/10-requirements.md`
- [x] **STEP 2: High-Level Architecture Design**
  - [x] `ai-tasks/WISHENKA-160/20-architecture.md`
- [x] **STEP 3: Failing Repro Test**
  - [x] `tests/test_item_modals_repro.py`
- [x] **STEP 4: Development**
  - [x] Added `--layer-modal: 100`, `.modal-backdrop`, `.modal-sheet`, and modal form/alert/button styles in `wishenka/web/static/miniapp.css`, and added `hx-target="#item-modal-container"` + `hx-swap="none"` on `.btn-archive-item` in `wishenka/web/templates/partials/item_edit_modal.html`.
  - [x] Added scoped `htmx:beforeSwap` error-swap opt-in for modal HTML 4xx/5xx responses in `wishenka/web/templates/base.html` (excluding `X-Reorder-Refusal`, `X-Receipt-Refusal`, `/reservations`, and non-HTML).
  - [x] Added localized modal error strings in `wishenka/i18n/catalog.py` and updated `wishenka/web/routes/items_ui.py` to return `HX-Retarget: #item-modal-container` + `HX-Reswap: innerHTML` on edit 400/409/503 and OOB `#item-modal-container` + `#list-notice` HTML on 404/409 archived/missing-resource errors.
- [x] **STEP 5: Code Cleanup**
  - [x] `ai-tasks/WISHENKA-160/40-code-cleanup.md`
- [x] **STEP 6: Observability**
  - [x] `ai-tasks/WISHENKA-160/50-observability.md`
- [x] **STEP 7: Technical Debt Analysis**
  - [x] `ai-tasks/WISHENKA-160/60-tech-debt.md`
- [x] **STEP 8: Dev Docs**
  - [x] `doc/dev/miniapp.md` (added Section 9.9 on modal CSS layering, `htmx:beforeSwap` 4xx/5xx opt-in, `HX-Retarget`/OOB error contracts, and updated `wishenka.web.items_ui` observability events)
  - [x] `doc/dev/items.md` (updated `items_ui.py` edit/archive error response contracts and `wishenka.web.items_ui` observability events table)
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-160/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-160/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-160/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-160/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-160/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
