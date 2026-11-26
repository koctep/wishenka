# Roadmap: WISHENKA-305

## Task Metadata

- **Implementation language**: Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-305/10-requirements.md`: one view-recorded event and one
    view-listed event per action; a deleted-wishlist history refusal is not a
    favorites denial; the counted service-level denial stays.
  - Implementation language determined (Python) and recorded above.
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-305/20-architecture.md`: one service owner for
    `view_history_recorded` and `view_history_listed`; the route stops repeating
    them. A deleted-wishlist history refusal stays
    `view_history_deleted_wishlist_denied` on `record_view`.
    `favorite_deleted_wishlist_denied` stays on `add_favorite` only.
- [x] **STEP 3: Failing Repro Test**
  - `tests/test_wishenka_305_history_log_once.py`: one `view_history_recorded`
    and one `view_history_listed` per action, owned by `wishenka.wishlists`.
    Deleted-wishlist `record_view` keeps `view_history_deleted_wishlist_denied`
    and does not emit `favorite_deleted_wishlist_denied`.
- [x] **STEP 4: Development**
  - [x] Moved `view_history_recorded` and `view_history_listed` onto `record_view` and `get_history` in `WishlistService` and `RepoWishlistOps`. The history route no longer writes those events. `record_view` keeps `view_history_deleted_wishlist_denied`. `add_favorite` keeps `favorite_deleted_wishlist_denied`.
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-305/40-code-cleanup.md`: ruff and mypy clean. Stale repro
    docstring corrected. Log owners and test assertions unchanged.
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-305/50-observability.md`: one `view_history_recorded`
    and one `view_history_listed` on `wishenka.wishlists`. Deleted-wishlist
    history stays `view_history_deleted_wishlist_denied` on `record_view`.
    `favorite_deleted_wishlist_denied` stays on `add_favorite`. No production
    log line added or removed.
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-305/60-tech-debt.md`: WISHENKA-292 item 3 is
    addressed. Each success event is written once by the domain operation.
    The history route does not repeat it. Deleted-wishlist `record_view`
    stays `view_history_deleted_wishlist_denied`.
    `favorite_deleted_wishlist_denied` stays on `add_favorite`. No new
    follow-up (count 0). The full suite was not run.
- [x] **STEP 8: Dev Docs**
  - `doc/dev/wishlists.md`: `view_history_recorded` and `view_history_listed`
    are each written once by the domain operation on `wishenka.wishlists`.
    The history route does not write them. A deleted wishlist on record uses
    `view_history_deleted_wishlist_denied`.
    `favorite_deleted_wishlist_denied` stays on adding a favorite. Those
    handler events are not `HTTP request completed`.
  - `doc/dev/miniapp.md`: the history-screen troubleshooting notes use the
    same owners and the same middleware distinction.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-305/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-305/20-architecture.md`

### STEP 3: Failing Repro

- `tests/test_wishenka_305_history_log_once.py`

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-305/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-305/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-305/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/wishlists.md`
- `doc/dev/miniapp.md`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
