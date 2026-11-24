# Roadmap: WISHENKA-121

## Task Metadata

- **Implementation language**: python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-121/10-requirements.md` — business requirements, scope boundaries, user stories, and acceptance criteria for serializing user write operations on the shared data store and surfacing lock timeouts as retryable errors.
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-121/20-architecture.md` — shared SQLite `BEGIN IMMEDIATE` contract for `UserStore`, `UserStoreBusyError` retryable mapping, read-only lookup isolation, HTTP 503 route handling, and Step 3 failing-repro plan.
- [x] **STEP 3: Failing Repro Test**
  - `tests/test_user_store_concurrency_repro.py` — red repro tests for `UserStore` `BEGIN IMMEDIATE` serialization, `UserStoreBusyError` mapping, and non-blocking read-only lookups
- [x] **STEP 4: Development**
  - [x] Extracted shared `configure_immediate_transactions` (with `AUTOCOMMIT` bypass for WAL setup) and `is_sqlite_busy` into `wishenka/sqlite.py` and updated `wishenka/wishlists/store.py` to use them.
  - [x] Added `UserStoreBusyError` to `wishenka/users/store.py` and `wishenka/users/__init__.py`; updated `UserStore` to configure WAL/synchronous/busy_timeout on autocommit in `initialize()`, execute writes via `_immediate` (`BEGIN IMMEDIATE`, mapping `SQLITE_BUSY` to `UserStoreBusyError`), and execute reads (`get_by_telegram_id`, `get_by_id`) via `_read` (`execution_options(read_only=True)`).
  - [x] Mapped `UserStoreBusyError` to HTTP 503 Service Unavailable in `wishenka/web/routes/auth.py` (`POST /api/auth/telegram`) and `wishenka/web/routes/profile.py` (`PATCH /api/profile/locale`, `PATCH /api/profile/birthdate`), and added HTTP 503 verification in `tests/test_user_store_concurrency_repro.py`.
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-121/40-code-cleanup.md` — static analysis (`ruff check`, `ruff format --check`, `mypy`), dead-code/debug-print audit, and test validation report for all 7 modified/new files.
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-121/50-observability.md` — observability audit across `wishenka/sqlite.py`, `wishenka/users/store.py`, `wishenka/web/routes/auth.py`, `wishenka/web/routes/profile.py`; added missing `user_store_error` log in `UserStore.initialize()`, `status_code=503` in `auth_user_store_busy`, `locale_user_not_found` log in `update_profile_locale`, and `caplog` observability tests in `tests/test_user_store_concurrency_repro.py`.
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-121/60-tech-debt.md` — technical debt analysis covering direct `UserStore.engine` callers, hardcoded 5000ms `busy_timeout`, duplicated error/503 mapping, missing test cases, and follow-up tasks.
- [x] **STEP 8: Dev Docs**
  - `doc/dev/architecture.md` — documented shared `wishenka/sqlite.py` helpers (`configure_immediate_transactions`, `is_sqlite_busy`) and `UserStore` `BEGIN IMMEDIATE` / `read_only=True` / `UserStoreBusyError` -> HTTP 503 contract.
  - `doc/dev/users.md` — documented `wishenka/sqlite.py`, `UserStore` `_immediate` / `_read` / `initialize()` WAL & busy-error contract, `UserStoreBusyError` -> HTTP 503 mapping on auth/profile routes, `WISHENKA-121` structured log events, and `tests/test_user_store_concurrency_repro.py`.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-121/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-121/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-121/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-121/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-121/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
