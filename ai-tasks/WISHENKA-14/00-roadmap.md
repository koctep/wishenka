# Roadmap: WISHENKA-14

## Task Metadata

- **Task Key**: WISHENKA-14
- **Summary**: [Frontend/TMA] Форма быстрого добавления (универсальный инпут) и детального редактирования желания
- **Story Points**: 5.0
- **Implementation language**: Python 3.12+ (Jinja2 / HTMX / TMA Web)

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - [x] `ai-tasks/WISHENKA-14/10-requirements.md`
- [x] **STEP 2: High-Level Architecture Design**
  - [x] `ai-tasks/WISHENKA-14/20-architecture.md`
- [x] **STEP 3: Failing Repro Test**
  - [x] `tests/test_wish_items_tma_ui.py`
- [x] **STEP 4: Development**
  - [x] Implemented HTMX UI router (`wishenka/web/routes/items_ui.py`) and registered in `wishenka/web/app.py`
  - [x] Created `wishlist_detail.html`, `partials/item_quick_add.html`, `partials/item_preview_card.html`, `partials/item_edit_modal.html`
  - [x] Updated `partials/item_card.html` (removed `|safe` XSS vector, added RBAC-gated edit button) and `wishenka/web/static/miniapp.css`
  - [x] Verified all 10 tests in `tests/test_wish_items_tma_ui.py` pass (GREEN) and `ruff`/`mypy` succeed
- [x] **STEP 5: Code Cleanup**
  - [x] `ai-tasks/WISHENKA-14/40-code-cleanup.md`
- [x] **STEP 6: Observability**
  - [x] `ai-tasks/WISHENKA-14/50-observability.md`
  - [x] Added structured UI lifecycle and invariant logging in `wishenka/web/routes/items_ui.py` and `caplog` tests in `tests/test_wish_items_tma_ui.py`
- [x] **STEP 7: Technical Debt Analysis**
  - [x] `ai-tasks/WISHENKA-14/60-tech-debt.md`
- [x] **STEP 8: Dev Docs**
  - [x] `doc/dev/items.md` / `doc/dev/miniapp.md`
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-14/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-14/20-architecture.md`

### STEP 3: Failing Repro

- `tests/test_wish_items_tma_ui.py`

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-14/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-14/50-observability.md`

### STEP 7: Technical Debt Analysis

- `ai-tasks/WISHENKA-14/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/items.md`
- `doc/dev/miniapp.md`
