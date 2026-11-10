# Roadmap: WISHENKA-6

## Task Metadata

- **Implementation language**: Python (FastAPI + SQLAlchemy async + SQLite WAL)

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
- [x] **STEP 2: High-Level Architecture Design**
- [x] **STEP 3: Failing Repro Test**
- [x] **STEP 4: Development**
- [x] **STEP 5: Code Cleanup**
- [x] **STEP 6: Observability**
- [x] **STEP 7: Technical Debt Analysis**
- [x] **STEP 8: Dev Docs**
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-6/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-6/20-architecture.md`

### STEP 3: Failing Repro

- [x] Red repro test: `tests/test_wishlist_roles_lifecycle.py`

### STEP 4: Development

- [x] Source implementation and green tests
  - [x] Implemented domain models, enums, exceptions, schemas, and RBAC/ABAC access policy in `wishenka/wishlists/`
  - [x] Implemented `WishlistService` handling lifecycle transitions, token management, Surprise Invariant zero-leak projections
  - [x] All 16 tests in `tests/test_wishlist_roles_lifecycle.py` pass (red repro turned green)
  - [x] Quality gate `make check` passed (Ruff linter, Ruff formatter, Mypy strict, full 35 test suite)

### STEP 5: Code Cleanup

- [x] `ai-tasks/WISHENKA-6/40-code-cleanup.md`
  - [x] Ruff linter & formatter check passed (24 source files clean)
  - [x] Mypy strict type check passed (0 issues)
  - [x] Pytest suite passed (35/35 passed) with explicit timeouts on all test modules
  - [x] Cleanliness verified: no dead code, unused imports/variables, or debug print statements; all lines <= 100 chars

### STEP 6: Observability

- [x] `ai-tasks/WISHENKA-6/50-observability.md`
  - [x] Structured audit logging in `wishenka.wishlists.service.WishlistService` for lifecycle events, member management, token rotations, reservations
  - [x] Security-hardened: sensitive raw tokens excluded from logs, entities represented by IDs and enums
  - [x] Surprise invariant violation attempts and access denials captured at WARNING level
  - [x] Pytest test suite expanded with 6 caplog-based tests in `TestWishlistAuditLogging` (41/41 tests passing)

### STEP 7: Tech Debt

- [x] `ai-tasks/WISHENKA-6/60-tech-debt.md`
  - [x] Shortcuts documented (in-memory store in `WishlistService`, hardcoded default 7-day token expiration, absent rollback boundaries)
  - [x] Code quality areas identified (repository pattern decoupling, entity immutability, query abstraction)
  - [x] Missing tests identified (concurrency race conditions, persistent DB transaction rollback, FastAPI/HTMX endpoints)
  - [x] Performance concerns evaluated (linear scans vs B-tree indexes, reservation count queries, multi-worker ASGI limitations)
  - [x] Follow-up tasks created in Jira with SP estimates: WISHENKA-48 (5 SP), WISHENKA-49 (3 SP), WISHENKA-50 (3 SP), WISHENKA-51 (5 SP)
  - [x] Tech debt blocker review passed (Verdict: SAFE TO CLOSE)

### STEP 8: Dev Docs

- [x] `doc/dev/wishlists.md` developer documentation created and cross-linked in `doc/dev/architecture.md`
  - [x] Documented overview, role-based access model, lifecycle states, and sharing mechanisms
  - [x] Documented domain models (`Wishlist`, `WishlistMember`, `WishItem`, `Reservation`) and enums (`WishlistRole`, `WishlistStatus`, `WishlistFormat`, `WishlistTimeType`, `ReservationStatus`)
  - [x] Documented Contextual RBAC policy (`WishlistAccessPolicy`, `UserWishlistContext`, privilege matrix)
  - [x] Documented Surprise Invariant zero-leak projection design (`WishItemRecipientViewDTO` vs `WishItemGifterViewDTO`)
  - [x] Documented `WishlistService` API methods and cryptographic token schemas (16-char/128-bit public token, 24-char/192-bit invite token)
  - [x] Documented structured audit logging event tags, levels, and raw token leakage prevention
  - [x] Documented troubleshooting guide and domain exception hierarchy (`WishlistError` to `InsufficientQuantityError`)
  - [x] Cross-linked `doc/dev/wishlists.md` in `doc/dev/architecture.md`
