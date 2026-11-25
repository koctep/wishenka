# WISHENKA-132 Roadmap

**Task**: Освобождать ресурсы WishlistStore при ошибке initialize()
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
  - [x] Failing repro test: `tests/test_wishenka_132_initialize_dispose_repro.py`
- [x] **STEP 4: Development**
  - [x] Wrapped `WishlistStore.initialize()` in `except BaseException:` to call `await self.dispose()` on failure and extended `WishlistStore.dispose()` to remove SQLite sidecar files (`-wal`, `-shm`, `-journal`)
- [x] **STEP 5: Code Cleanup**
- [x] **STEP 6: Observability**
- [x] **STEP 7: Technical Debt Analysis**
- [x] **STEP 8: Dev Docs**
- [x] **COMMIT: Commit Changes**
