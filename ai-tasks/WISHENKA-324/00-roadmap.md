# Roadmap: WISHENKA-324

## Task Metadata

- **Implementation language**: Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-324/10-requirements.md`
  - Gift-receipt screens must receive wishlist access as an argument. The
    hidden slot and the empty-slot fallback go away. The quantity-refusal
    look stays. Opening a receipt,
    correction, or cancellation dialog stays a read on the access it
    already receives. Recording, correcting, and cancelling stay saves on
    the exclusive lock.
  - Correction: a successful record, correction, or cancellation that
    carries the repeat key composes the list on the save. A true repeat
    returns the stored answer. Opening dialogs stay reads. This task does
    not move that successful keyed list off the save. The empty-slot
    opening is not limited to a missing repeat key: a refused record that
    carries the key also opens a new shared repository when the slot is
    empty. This task removes only that hidden fallback and does not hand
    the successful list a separate shared access. The quantity-refusal
    look stays.
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-324/20-architecture.md`
  - Gift-receipt looks take the wishlist repository as an argument.
    `_repo_ctx` and the empty-slot `get_wishlist_repository` opening go
    away. Openings stay on `WishlistReadRepo`. The quantity-refusal look
    uses the access the screen already has. A keyed save still composes
    the list on that save. A true repeat returns the stored answer.
- [x] **STEP 3: Failing Repro Test**
  - `tests/test_wishenka_324_receipt_access_repro.py`
  - A gift-receipt look with an empty hidden slot still opens
    `get_wishlist_repository`. The quantity-refusal look is covered,
    including a refused record that carries the repeat key. A successful
    keyed save still composes the list on that save.
- [x] **STEP 4: Development**
  - [x] Gift-receipt looks take the repository they are given. `_repo_ctx`
    and the empty-slot `get_wishlist_repository` opening are gone.
    Opening dialogs pass the read repository they already receive. A
    quantity refusal, including one that still carries the repeat key,
    paints through `run_repository_read` after rollback. A keyed save
    still composes the list on that save; a true repeat returns the
    stored answer. An unkeyed save calls `execute_wish`, then reads the
    list through `run_repository_read`.
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-324/40-code-cleanup.md`
  - `make analyze` passed: Ruff check, Ruff format (301 files), and Mypy
    (301 files). The WISHENKA-324 diff had no format, lint, or type
    issues. Production code was not edited, so the repro was not re-run.
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-324/50-observability.md`
  - No new log and no new metric. A gift-receipt look is not logged.
    A busy save still logs `wishlist_inventory_busy` and
    `receipt_inventory_busy`. A busy read still logs `wishlist_read_busy`.
    A storage error on a save still logs `wishlist_store_error`. A storage
    error on a read still reaches `RequestLoggingMiddleware`. Production
    code was not edited.
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-324/60-tech-debt.md`
  - No new follow-up. Gift-receipt looks take the repository they are
    given. The hidden fallback is gone. A successful keyed save still
    composes the list on that save. The new repro and the updated receipt
    tests keep `pytest.mark.timeout`. WISHENKA-335, 338, 339, 340, 342,
    350, 351, 352, and 353 were not re-filed.
- [x] **STEP 8: Dev Docs**
  - `doc/dev/wishlists.md`
  - `doc/dev/architecture.md`
  - `doc/dev/gift-receipt.md`
  - Gift-receipt looks take the wishlist repository the screen already has.
    The hidden fallback that opened a shared repository is gone. A successful
    keyed save still composes the list on that save.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-324/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-324/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-324/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-324/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-324/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
