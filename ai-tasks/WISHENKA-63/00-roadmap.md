# Roadmap: WISHENKA-63

## Task Metadata

- **Implementation language**: Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - Business requirements: `ai-tasks/WISHENKA-63/10-requirements.md`
- [x] **STEP 2: High-Level Architecture Design**
  - Architecture document: `ai-tasks/WISHENKA-63/20-architecture.md`
- [x] **STEP 3: Failing Repro Test**
  - `tests/test_wishenka_63_repro.py`
- [x] **STEP 4: Development**
  - [x] Iteration 1: Consolidated `project_wish_item(item, None)` to return `recipient_view(item)` and unified `GET /api/public/wishlists/{token}` and `GET /api/public/wishlists/{token}/view` on `WishlistService.get_wishlist_by_public_token`.
  - [x] Iteration 2: Enforced explicit persistent `WishlistStore` boundary in `WishlistService.__init__` (`store=None` raises `ValueError` unless `_allow_in_memory=True` via `WishlistService.in_memory()`), updated `WishlistStore` hydration and 12 unit test modules to `WishlistService.in_memory()`.
  - [x] Iteration 3: Expanded `tests/test_wishenka_63_repro.py` with anonymous, recipient (personal + collaborative), gifter, and persistence-boundary tests.
  - [x] Iteration 4: Removed unused `projection()` helper from `wishenka/web/routes/wishlists.py` and reverted out-of-scope file modifications.
- [x] **STEP 5: Code Cleanup**
  - Cleanup report: `ai-tasks/WISHENKA-63/40-code-cleanup.md`
- [x] **STEP 6: Observability**
  - Observability report: `ai-tasks/WISHENKA-63/50-observability.md`
- [x] **STEP 7: Technical Debt Analysis**
  - Technical debt analysis: `ai-tasks/WISHENKA-63/60-tech-debt.md`
- [x] **STEP 8: Dev Docs**
  - `doc/dev/wishlists.md`: documented consolidated public-link projection (`project_wish_item(item, None)` -> `recipient_view(item)` / `WishItemRecipientViewDTO` and `WishlistService.get_wishlist_by_public_token` across `/share/{public_token}`, `/api/public/wishlists/{token}`, and `/api/public/wishlists/{token}/view`), explicit persistent `WishlistStore` boundary (`WishlistService.in_memory()`), and structured observability events (`public_wishlist_resolved`, `wishlist_service_store_required`, `wishlist_service_in_memory_created`).
  - `doc/dev/items.md`: updated in-memory `WishlistService()` example to `WishlistService.in_memory()`.
  - `doc/dev/reservations.md`: updated `WishlistService()` references/examples to `WishlistService.in_memory()`.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-63/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-63/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-63/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-63/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-63/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
