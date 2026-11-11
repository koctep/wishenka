# Roadmap: WISHENKA-9

## Task Metadata

- **Implementation language**: Python and JavaScript

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - Business requirements: `ai-tasks/WISHENKA-9/10-requirements.md`
- [x] **STEP 2: High-Level Architecture Design**
  - Architecture: `ai-tasks/WISHENKA-9/20-architecture.md`
- [x] **STEP 3: Failing Repro Test**
  - [x] `tests/test_wishlist_sections_ui.py`
- [x] **STEP 4: Development**
  - [x] Iteration 1: Domain models (`WishlistFavorite`, `ViewHistoryEntry`), SQLite tables (`wl_favorites`, `wl_view_history`), and transactional persistence in WishlistStore
  - [x] Iteration 2: Domain service logic for Favorites and Viewing History (`add_favorite`, `remove_favorite`, `list_favorites`, `record_view`, `get_history`, `clear_history`) with self-favorite guard, 20-entry bound, deduplication, and Surprise Invariant
  - [x] Iteration 3: FastAPI REST endpoints for `/api/favorites` and `/api/history` with CSRF protection, session validation, and role badge precedence
  - [x] Iteration 4: Mini App frontend UI update in `miniapp.js` and `miniapp.css` (categorized sections "My wishlists", "Collaborating", "Favorites", role badges, viewing history view, and favorite toggle)
- [x] **STEP 5: Code Cleanup**
  - Code cleanup report: `ai-tasks/WISHENKA-9/40-code-cleanup.md`
- [x] **STEP 6: Observability**
  - Observability report: `ai-tasks/WISHENKA-9/50-observability.md`
- [x] **STEP 7: Technical Debt Analysis**
  - Technical debt report: `ai-tasks/WISHENKA-9/60-tech-debt.md`
  - Technical debt report: `ai-tasks/WISHENKA-9/60-tech-debt.md`
- [x] **STEP 8: Dev Docs**
  - Developer docs: `doc/dev/miniapp.md`, `doc/dev/wishlists.md`
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-9/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-9/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-9/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-9/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-9/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
