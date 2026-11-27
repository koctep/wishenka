# Roadmap: WISHENKA-342

## Task Metadata

- **Implementation language**: Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-342/10-requirements.md`
  - Person lookups by Telegram id and by internal id already leave the
    exclusive save lock free. They still allow a change until the lookup
    ends, and a busy lookup is an ordinary database failure. The lookup
    must refuse a change, stay quiet on success, and use the existing
    temporary-unavailable outcome when the database is busy.
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-342/20-architecture.md`
  - Person lookups stay on `UserStore._read`. That method gains the wishlist
    `query_only` on/off sequence, the `AUTOCOMMIT` reset, and invalidate when
    the reset fails. A busy lookup reuses `is_sqlite_busy`,
    `UserStoreBusyError`, and the existing `user_store_busy` warning. Other
    storage errors stay on the current `_read` path. Wishlist reads and the
    WISHENKA-328 reads stay as they are.
- [x] **STEP 3: Failing Repro Test**
  - `tests/test_wishenka_342_user_read_hardening_repro.py`
  - Red on current `UserStore._read`: a person lookup does not set
    `PRAGMA query_only = ON` or reset it `OFF` through `AUTOCOMMIT`, and a
    busy lookup is an ordinary storage failure. The lookup must raise the
    existing `UserStoreBusyError` and emit the existing `user_store_busy`
    warning. A successful lookup must not add a log.
- [x] **STEP 4: Development**
  - [x] Implemented `UserStore._read`: `PRAGMA query_only` on before the lookup, reset off through `AUTOCOMMIT`, busy lookups reuse `UserStoreBusyError` and `user_store_busy`, and a failed reset invalidates while keeping an in-flight work error.
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-342/40-code-cleanup.md`
  - `UserStore._read` was already clean. `make analyze` passed. No
    production or repro edits. Hashes match the accepted PASS.
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-342/50-observability.md`
  - Person lookups stay quiet on success. A busy lookup reuses the
    existing `user_store_busy` warning. A failed `query_only` reset logs
    `user_store_query_only_reset_failed`. Other SQLAlchemy errors stay
    unwrapped and unlogged on `_read`. No production change.
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-342/60-tech-debt.md`
  - `UserStore._read` now sets `PRAGMA query_only`, resets it off through
    `AUTOCOMMIT`, invalidates when that reset fails, and maps
    `is_sqlite_busy` to `UserStoreBusyError`. That closes WISHENKA-254 TD-1.
    The repro module has `pytestmark = pytest.mark.timeout(30)`. No new
    follow-up. WISHENKA-328 and WISHENKA-338 stay as they are. User-facing
    `doc/` text was left unchanged. The stale read sentence in
    `doc/dev/users.md` belongs to Step 8.
- [x] **STEP 8: Dev Docs**
  - `doc/dev/users.md`
  - `doc/dev/architecture.md`
  - `UserStore._read` sets `PRAGMA query_only = ON` and resets it `OFF`
    through `AUTOCOMMIT`. A failed reset logs
    `user_store_query_only_reset_failed` and invalidates the connection.
    A busy lookup reuses `user_store_busy` and `UserStoreBusyError`.
    Other `SQLAlchemyError` is re-raised. A successful lookup adds no log.
    Writes stay on `_immediate`. Birthday listing and the private-chat
    lookup stay as WISHENKA-328 left them.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-342/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-342/20-architecture.md`

### STEP 3: Failing Repro

- `tests/test_wishenka_342_user_read_hardening_repro.py`

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-342/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-342/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-342/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
