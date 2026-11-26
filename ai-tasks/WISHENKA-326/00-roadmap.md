# Roadmap: WISHENKA-326

## Task Metadata

- **Implementation language**: Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-326/10-requirements.md`
  - The brief wait is already shared. This task changes only the outcome
    after the wait, from an ordinary storage failure to the same temporarily
    unavailable outcome a store wishlist save already shows.
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-326/20-architecture.md`
  - Busy `SQLAlchemyError` in `get_wishlist_repository` becomes `InventoryBusyError` and `wishlist_inventory_busy`. Other database errors stay `RuntimeError` and `wishlist_store_error`. No second wait.
- [x] **STEP 3: Failing Repro Test**
  - `tests/test_wishenka_326_repository_busy_repro.py`
  - A busy `SQLAlchemyError` in `get_wishlist_repository` still raises `RuntimeError` (`Wishlist storage operation failed`). The same busy error through `wishlists.execute` is caught there first, so the dependency mapping never runs. A non-busy `SQLAlchemyError` still raises that `RuntimeError`.
- [x] **STEP 4: Development**
  - [x] Mapped a busy SQLAlchemyError in get_wishlist_repository to InventoryBusyError and wishlist_inventory_busy. wishlists.execute re-raises that busy error. An uncaught InventoryBusyError is HTTP 503 with the existing detail.
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-326/40-code-cleanup.md`
  - No unused imports or dead helpers in the busy mapping. Analyze and the
    shared-repository busy tests passed. Behavior is unchanged.
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-326/50-observability.md`
  - A busy `SQLAlchemyError` in `get_wishlist_repository` already logs one
    WARNING `wishlist_inventory_busy` and raises `InventoryBusyError`. The
    app handler returns HTTP 503 and does not log. `wishlists.execute`
    re-raises that busy error with no busy log of its own. No new log or
    metric. Production code was left unchanged.
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-326/60-tech-debt.md`
  - No new follow-up. `wishlists.execute` is the only route that catches `SQLAlchemyError`, and its busy branch re-raises. Other `WishlistRepo` routes leave that error for `get_wishlist_repository`. The new test module has `pytestmark = pytest.mark.timeout(30)`.
- [x] **STEP 8: Dev Docs**
  - `doc/dev/wishlists.md`
  - `doc/dev/items.md` event catalog only
  - A busy `SQLAlchemyError` in `get_wishlist_repository` is one WARNING `wishlist_inventory_busy` (`event` only) and `InventoryBusyError` after the connection closes. Any other `SQLAlchemyError` stays ERROR `wishlist_store_error` and `RuntimeError("Wishlist storage operation failed")`. `wishlists.execute` re-raises only the busy case. `install_inventory_busy_handler` returns HTTP 503 with `detail` `str(exc)` and does not log. The shared `busy_timeout` / `BEGIN IMMEDIATE` wait is unchanged. No second retry.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-326/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-326/20-architecture.md`

### STEP 3: Failing Repro

- `tests/test_wishenka_326_repository_busy_repro.py`

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-326/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-326/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-326/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
