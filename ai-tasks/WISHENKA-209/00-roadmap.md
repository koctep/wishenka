# Roadmap: WISHENKA-209

## Task Metadata

- **Implementation language**: Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - [/] `ai-tasks/WISHENKA-209/10-requirements.md`
- [x] **STEP 2: High-Level Architecture Design**
  - [/] `ai-tasks/WISHENKA-209/20-architecture.md`
- [x] **STEP 3: Failing Repro Test**
  - [/] `tests/test_wishenka_209_create_modal_repro.py`
- [x] **STEP 4: Development**
  - [x] Added dedicated `POST /web/wishlists/{wishlist_id}/items/new` (`submit_new_item`) endpoint in `wishenka/web/routes/items_ui.py` and updated `wishenka/web/templates/partials/item_edit_modal.html` (`is_edit=False`) to submit to `/items/new` and compare `recipient_user_id` via `|string`.
  - [x] Extracted `_parse_item_modal_form`, `_render_created_item_response`, and `_render_item_modal_error` in `wishenka/web/routes/items_ui.py` so `submit_new_item` preserves all submitted fields, error banner, and collaborative recipient options/selection on `400` errors while keeping `quick_add_item` (`POST /items/quick`) isolated.
- [x] **STEP 5: Code Cleanup**
  - [/] `ai-tasks/WISHENKA-209/40-code-cleanup.md`
- [x] **STEP 6: Observability**
  - [/] `ai-tasks/WISHENKA-209/50-observability.md`
- [x] **STEP 7: Technical Debt Analysis**
  - [/] `ai-tasks/WISHENKA-209/60-tech-debt.md`
- [x] **STEP 8: Dev Docs**
  - [x] `doc/dev/miniapp.md`
  - [x] `doc/dev/items.md`
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-209/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-209/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-209/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-209/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-209/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
