# Roadmap: WISHENKA-86

## Task Metadata

- **Implementation language**: Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-86/10-requirements.md`
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-86/20-architecture.md`
- [x] **STEP 3: Failing Repro Test**
  - [x] `tests/test_wishlist_deleted_restore.py`
- [x] **STEP 4: Development**
  - [x] Iteration 1: Added `WishlistRetentionExpiredError`, `WishlistAccessPolicy.can_restore_deleted`, `WishlistService.list_deleted_wishlists`, and `WishlistService.restore_deleted_wishlist` (with token rotation and retention boundary enforcement)
  - [x] Iteration 2: Added `GET /api/wishlists/deleted` and `POST /api/wishlists/{wishlist_id}/restore-deleted` HTTP endpoints (`410 Gone` on expired retention, `404` on non-owner/missing, `409` on archived); `tests/test_wishlist_deleted_restore.py` passes
  - [x] Iteration 3: Added `RU`/`EN` `miniapp.deleted.*` keys in `wishenka/i18n/catalog.py` and `Recently deleted` UI section with restore action and error handling in `wishenka/web/static/miniapp.js`
  - [x] Iteration 4: Added unit/integration edge-case tests in `tests/test_wishlist_deleted_restore.py` (`409` on archived, `404` on missing, sorting & `days_remaining` ceiling, i18n & UI wiring); verified `ruff`, `mypy`, and full `pytest` suite (`1097 passed`)
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-86/40-code-cleanup.md`
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-86/50-observability.md`
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-86/60-tech-debt.md`
- [x] **STEP 8: Dev Docs**
  - `doc/dev/wishlists.md`
  - `doc/dev/miniapp.md`
  - `ai-tasks/WISHENKA-86/70-dev-docs.md`
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-86/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-86/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-86/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-86/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-86/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
