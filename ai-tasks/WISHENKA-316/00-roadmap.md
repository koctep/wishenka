# Roadmap: WISHENKA-316

## Task Metadata

- **Implementation language**: Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-316/10-requirements.md`: one product rule decides whether a
    deleted wishlist can still be restored, and one deletion action applies that
    outcome. The Mini App and every other owner path use the same retention period
    and the same delete result. Logs, event fields, and existing deletion behavior
    stay as they are.
  - Implementation language determined and recorded above.
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-316/20-architecture.md`: deletion classification and the
    retention comparison move behind one shared rule. `WishlistService` and
    `RepoWishlistOps` both apply it. One typed accessor reads
    `Settings.wishlist_retention_days`. The delete route stops reading private
    storage. Log event names and fields stay. Existing delete tests stay the
    behavior lock.
- [x] **STEP 3: Failing Repro Test**
  - `tests/test_wishlist_retention_single_rule.py`: a list deleted inside the
    configured window stays restorable on delete, recently deleted, and restore
    even when `wishenka.wishlists.retention.is_retention_expired` is forced to
    report expiry. Those paths still use their own comparisons.
- [x] **STEP 4: Development**
  - [x] Shared rule: `wishenka/wishlists/retention.py` plus `Settings.wishlist_retention_days`. The wishlists package loads public names on first use so `Settings` can import the usual 30 without a cycle.
  - [x] Both backends classify an owner delete with `is_retention_expired` looked up on that module at call time. List and restore use the same comparison.
  - [x] Delete route, Mini App shell, and cleanup read the period through `wishlist_retention_days`. The delete route no longer reads private wishlist storage.
  - [x] `tests/test_wishlist_retention_single_rule.py` is green. Existing delete and cleanup modules: 124 passed.
  - [x] Full `make test`: 2482 passed, 2 skipped, 25 failed. The 25 failures are the filed pre-existing set (WISHENKA-348, WISHENKA-264, WISHENKA-265, WISHENKA-220, WISHENKA-235, WISHENKA-245, WISHENKA-232, WISHENKA-298, WISHENKA-267, WISHENKA-212). WISHENKA-311 did not fail this run.
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-316/40-code-cleanup.md`: `make analyze` passed
    (Ruff and Mypy, 288 files). No unused imports, dead code, debug prints,
    or format edits in the task diff. Behavior unchanged. Full suite not
    re-run; Step 4 result stands (2482 passed, 2 skipped, 25 pre-existing
    failures).
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-316/50-observability.md`: no new log. Existing delete,
    list, restore, and cleanup events stay, including
    `wishlist_retention_expired` on the expired delete path.
    `wishlist_mutation_committed` is written before the handler returns. The
    repository dependency commits after the response is sent.
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-316/60-tech-debt.md`: S-1, S-2, and S-3 from
    WISHENKA-295 are addressed. No new follow-up. Out of scope stays on
    WISHENKA-317 and WISHENKA-318. The 25 full-suite failures stay the filed
    pre-existing set. WISHENKA-311 did not fail that run.
  - User documentation in `doc/`: N/A. Owner-visible behavior did not change.
    Developer docs stay with Step 8.
- [x] **STEP 8: Dev Docs**
  - `doc/dev/wishlists.md`: one period (`wishlist_retention_days`) and one
    comparison (`is_retention_expired`). Delete classifies before writing. An
    ended window is 410 `retention_expired`. `wishlist_mutation_committed`
    means the handler action returned and is written before the repository
    commit.
  - `doc/dev/miniapp.md`: shell `data-retention-days`, recently deleted, and
    restore use that same period and the same 410.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-316/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-316/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-316/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-316/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-316/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
