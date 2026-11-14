# Roadmap: WISHENKA-112

## Task Metadata

- **Implementation language**: Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-112/10-requirements.md` — requirements for the behaviour-preserving cleanup documented; debt items re-verified against current code.
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-112/20-architecture.md` — name `_DOMAIN_ERRORS`; callback `Callable[[list[int]], list[int]]`; hasattr/getattr cleaned in store.py (x3) and repository.py (x2); Step 3 = structure tests (red) + characterization tests (green before/after).
- [x] **STEP 3: Failing Repro Test**
  - `tests/test_wishenka_112_structure.py` — RED now (3 failed, 0 passed; AssertionError only, no import/collection errors), GREEN expected after Step 4. Reason lines: `hasattr(items_ui, '_NOT_FOUND_ERRORS')` is True; `reorder` hint args `[WishlistService, list[int]]` != `[list[int]]`; AST scan finds 5 `hasattr`/`getattr` probes (store.py:89x/893 and others, repository.py:102).
  - `tests/test_items_ui_error_mapping.py` — characterization, GREEN now (24 passed, ~42 s): 409/404 over reorder, move, archive-confirm, archive, restore; 400 "Invalid item order" + `ui_items_reorder_rejected` (WARNING, `invalid_permutation`); `reorder_wish_items` spy (0 calls unchanged, 1 per real move/reorder); `ui_items_reordered`/`ui_item_moved` INFO present on success, absent on 404/409.
  - Verified against real routes: reorder with unknown id inside `item_ids` -> 400 (not 404), so unknown-item 404 is parametrized over move/archive-confirm/archive/restore only; unknown wishlist and non-member -> 404 on all five; archived wishlist -> 409 on all five. Correction to architecture: none of its assumptions failed besides this reviewer note.
  - `make analyze`: ruff, format, mypy clean (105 files).
- [x] **STEP 4: Development**
  - [x] items_ui.py: `_NOT_FOUND_ERRORS` -> `_DOMAIN_ERRORS` (+comment, 4 except sites); `_reordered_response` callback `Callable[[list[int]], list[int]]`, `current_ids` computed once; `reorder_items_ui`/`move_item_ui` adapted.
  - [x] store.py (3 sites) and repository.py (2 sites): removed `hasattr`/`getattr` column probes; None guards and `or 0` kept.
- [x] **STEP 5: Code Cleanup**
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-112/50-observability.md` — no new logging/metrics (behaviour-preserving); existing events unchanged and pinned by `tests/test_items_ui_error_mapping.py`; missing-column AttributeError -> 500 via middleware `logger.exception`.
- [x] **STEP 7: Technical Debt Analysis**
- [x] **STEP 8: Dev Docs**
- [ ] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-112/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-112/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-112/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-112/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-112/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
