# Roadmap: WISHENKA-75

## Task Metadata

- **Implementation language**: Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-75/10-requirements.md` — бизнес-требования, цели целостности данных, пользовательские истории и критерии приёмки
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-75/20-architecture.md` — архитектура ссылочной целостности и каскадной очистки (`wl_favorites`, `wl_view_history`, `wl_members` → `users.telegram_id`), план миграции Alembic и план Failing Repro для Шага 3
- [x] **STEP 3: Failing Repro Test**
  - `tests/test_wishenka_75_user_fk_cascade.py` — automated red repro tests (3 failed as expected on current codebase: missing `IntegrityError` on nonexistent `user_id`, missing `ON DELETE CASCADE` on `DELETE FROM users`, and uncleaned orphan rows on Alembic upgrade)
- [x] **STEP 4: Development**
  - [x] Iteration 1: Added `add_user_fk_cascades` Alembic migration (`wl_members`, `wl_favorites`, `wl_view_history` `user_id` FK to `users(telegram_id)` with `ON DELETE CASCADE` and orphan cleanup) and updated `wishenka/wishlists/db_models.py`
  - [x] Iteration 2: Fixed `test_wishenka_75_user_fk_cascade.py` assertions (`RuntimeError` wrapping `IntegrityError` + direct SQLite `IntegrityError`, `wl_lists.owner_id` check + preserved `wl_members` row) and resolved all `E501` lint errors
  - [x] Iteration 3: Added Alembic `downgrade()`/`upgrade()` and `AccountDeletionService.delete_account()` end-to-end cascade tests to `tests/test_wishenka_75_user_fk_cascade.py`, added `UserRefRow` to `wishenka/wishlists/db_models.py`, and updated existing test fixtures/helpers to seed `users` rows before creating user-linked wishlist records
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-75/40-code-cleanup.md` — static analysis, formatting, dead code, and test quality check
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-75/50-observability.md` — structured migration orphan-cleanup/FK logging in `add_user_fk_cascades.py`, FK integrity & account deletion log verification, and `caplog` test coverage
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-75/60-tech-debt.md` — анализ технического долга, компромиссов и отложенных задач
- [x] **STEP 8: Dev Docs**
  - `doc/dev/migrations.md` — documented `add_user_fk_cascades` revision (new head after `add_notice_retention_columns`), orphan cleanup, downgrade caveat, and structured migration observability events (`user_fk_migration_orphans_cleaned`, `user_fk_migration_table_rebuilt`, `user_fk_migration_completed`, `user_fk_downgrade_table_rebuilt`, `user_fk_downgrade_completed`)
  - `doc/dev/wishlists.md` — documented `REFERENCES users(telegram_id) ON DELETE CASCADE` on `wl_members`, `wl_favorites`, and `wl_view_history`, `UserRefRow` and `ForeignKey("users.telegram_id", ondelete="CASCADE")` in `wishenka/wishlists/db_models.py`, and `PRAGMA foreign_keys = ON` / `AccountDeletionService` cascade semantics
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-75/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-75/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-75/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-75/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-75/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
