# WISHENKA-254 Roadmap

**Task**: [Техдолг] Усиление WishlistStore.execute_read: PRAGMA query_only и обработка SQLITE_BUSY
**Story Points**: 2
**Priority**: Low

## Status Legend
- `[ ]` Pending
- `[/]` In Progress
- `[x]` Done (after review PASS)

## Steps
- [x] **STEP 1: Requirements**
- [x] **STEP 2: Architecture**
- [x] **STEP 3: Failing Repro**
  - [x] `tests/test_wishenka_254_execute_read_hardening_repro.py`
- [x] **STEP 4: Development**
  - [x] Enforced `PRAGMA query_only = ON`/`OFF` and `SQLITE_BUSY` -> `InventoryBusyError` mapping in `WishlistStore.execute_read`; aligned `tests/test_wishlists_sqlite_repo.py`
- [x] **STEP 5: Code Cleanup**
- [x] **STEP 6: Observability**
- [x] **STEP 7: Technical Debt Analysis**
- [x] **STEP 8: Dev Docs**
- [x] **COMMIT: Commit Changes**
