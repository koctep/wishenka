# Roadmap: WISHENKA-35

## Task Metadata

- **Implementation language**: Python (with HTML/JS for Mini App templates)

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-35/10-requirements.md` — бизнес-требования, пользовательские истории, функциональные/нефункциональные требования, бизнес-сущности и критерии приёмки по механизму удаления профиля, подтверждению в Mini App, каскадной обработке списков и броней, очистке персональных данных и отзыву сессий.
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-35/20-architecture.md` — архитектура механизма удаления профиля, очистки персональных данных, передачи владения совместными вишлистами, отзыва сессий и план Failing Repro.
- [x] **STEP 3: Failing Repro Test**
  - `tests/test_account_deletion_repro.py` — red automated repro covering `/api/profile/deletion-preview`, `/api/profile/delete`, `AccountDeletionService` cascade, ownership transfer, reservation cleanup, PII removal, and session token revocation.
- [x] **STEP 4: Development**
  - [x] Iteration 1: Added Alembic migration `add_deleted_session_revocations` and `wishenka/wishlists/deletion.py` (`AccountDeletionService`, `DeletionPreviewDTO`, `DeletionResultDTO`, deterministic ownership transfer, item anonymization, PII/bot state cleanup, and revocation recording).
  - [x] Iteration 2: Added session liveness & revocation checks in `wishenka/auth/dependencies.py` (`get_optional_current_user`) and expired revocation cleanup in `wishenka/wishlists/store.py` and `wishenka/wishlists/cleanup.py`.
  - [x] Iteration 3: Added `GET /api/profile/deletion-preview` and `POST /api/profile/delete` in `wishenka/web/routes/profile.py`, bilingual RU/EN strings in `wishenka/i18n/catalog.py`, and Delete Account UI with preview & explicit confirmation in `wishenka/web/templates/settings.html`; `tests/test_account_deletion_repro.py` is now green.
  - [x] Iteration 4: Added comprehensive unit/integration tests in `tests/test_account_deletion.py`, resolved circular import in `wishenka/auth/dependencies.py` by moving `compute_revocation_subject_hash` to `wishenka/auth/session.py`, and verified `make analyze` and `make test` (1086 passed).
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-35/40-code-cleanup.md` — code cleanup, formatting, linter, and quality validation report.
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-35/50-observability.md` — structured logging and observability validation for account deletion, session revocation, and cleanup.
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-35/60-tech-debt.md` — technical debt analysis and follow-up items for WISHENKA-35.
- [x] **STEP 8: Dev Docs**
  - `doc/dev/users.md` — updated `WISHENKA-35` status to Implemented, `AccountDeletionService` (`wishenka/wishlists/deletion.py`) cascade & `anonymized_items` contract, `deleted_session_revocations` Alembic revision (`add_deleted_session_revocations`), `/api/profile/deletion-preview` & `/api/profile/delete`, exact structured log events, and verification suites.
  - `doc/dev/auth.md` — documented `compute_revocation_subject_hash`, `_is_session_active` liveness/revocation checks in `get_optional_current_user`, `session_rejected_revoked_or_deleted` log event, and `401 Session revoked or account deleted` troubleshooting.
  - `doc/dev/wishlists.md` — updated `run_cleanup_cycle` / `CleanupStats` with `cleanup_expired_session_revocations` (`session_revocations_cleaned`) and added `AccountDeletionService` & `session_revocations_purged` audit events.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-35/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-35/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-35/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-35/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-35/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
