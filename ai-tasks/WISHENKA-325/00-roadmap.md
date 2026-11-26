# Roadmap: WISHENKA-325

## Task Metadata

- **Implementation language**: Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-325/10-requirements.md`
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-325/20-architecture.md`
  - Opening history batch-loads headers with `get_wishlist_headers_by_ids` and the viewer's membership rows. Per-entry `get_wishlist` goes away. The cap, stored visits, and access checks stay.
  - Correction: the red test rejects `FROM wl_lists WHERE id = :id` from
    `get_wishlist`. The unchanged `list_view_history` join
    `ON l.id = vh.wishlist_id` does not count, and neither does `wishlist_id =`.
  - Correction: match compiled `FROM wl_lists WHERE id = ?`. The colon form never appears.
- [x] **STEP 3: Failing Repro Test**
  - `tests/test_wishenka_325_history_batch_repro.py`
- [x] **STEP 4: Development**
  - [x] `RepoWishlistOps.get_history` loads headers with `get_wishlist_headers_by_ids` and this person's memberships with `list_user_memberships_by_wishlist_ids`. An empty visit list skips both batches. Cap, stored rows, share checks, and the person-facing list stay.
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-325/40-code-cleanup.md`
  - Scoped files were already within the 100-character limit. The history
    test docstring now describes the green batch check. `make analyze` is
    clean. The history batch test passed.
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-325/50-observability.md`
  - No new log. Success stays `view_history_listed` plus debug
    `wishlist_repo_batch_read` on the header and membership batches. A
    database failure on either batch stays `wishlist_store_error`, or
    `wishlist_inventory_busy` when the store path sees a lock wait.
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-325/60-tech-debt.md`
  - Header and membership batches match the architecture. One new follow-up, priority Low, [WISHENKA-353](https://pypost.atlassian.net/browse/WISHENKA-353): the remaining per-row share-grant reads. The history test already has `pytestmark = pytest.mark.timeout(30)`. Developer docs stay for Step 8.
- [x] **STEP 8: Dev Docs**
  - `doc/dev/wishlists.md`: opening history loads the capped visit list, then one header batch (`get_wishlist_headers_by_ids`, items stay empty) and one membership batch (`list_user_memberships_by_wishlist_ids`). An empty visit list skips both. The catalog lists the membership method. `wishlist_repo_batch_read` includes entity `wishlist_member`. Per-row `has_valid_share_access` stays and points at WISHENKA-353. No other `doc/dev` page said opening history loads each wishlist with `get_wishlist`.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-325/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-325/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)
- `tests/test_wishenka_325_history_batch_repro.py`

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-325/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-325/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-325/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
