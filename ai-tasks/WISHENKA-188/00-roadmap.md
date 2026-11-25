# Roadmap: WISHENKA-188

## Task Metadata

- **Implementation language**: `python`

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-188/10-requirements.md` — бизнес-требования, пользовательские истории, функциональные и нефункциональные требования, доменные сущности и критерии приёмки.
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-188/20-architecture.md` — архитектурный дизайн унификации ключей пользователя, FK-каскадов и консолидации DDL `users` в Alembic.
- [x] **STEP 3: Failing Repro Test**
  - `tests/test_wishenka_188_user_key_unification_repro.py` — red repro tests for `UserStore` Alembic delegation, legacy key migration (`users.id` → `users.telegram_id`) & FK cascades, `wl_lists` cascade deletes, and end-to-end `telegram_id` usage.
- [x] **STEP 4: Development**
  - [x] Added Alembic revision `unify_user_keys_and_cascades` (`down_revision = "add_receipt_delivery_fence"`) consolidating `users` DDL (including `birth_day`, `birth_month`, `birth_year`, `birthdate_source`), migrating `bot_destinations`, `birthday_entries`, `birthday_input`, `support_input`, and `support_tickets` to `users.telegram_id` (`ON DELETE CASCADE`), and adding `ON DELETE CASCADE` FKs on `wl_tokens`, `wl_invite_tokens` (with `wishlist_id` backfill), and `reminder_outbox`.
  - [x] Removed duplicate `users` DDL from `wishenka/users/store.py` and delegated `UserStore.initialize()` to `upgrade_to_head(self.database_url)`.
  - [x] Updated `wishenka/wishlists/db_models.py`, `wishenka/wishlists/repository.py`, `wishenka/wishlists/store.py`, `wishenka/wishlists/deletion.py`, `wishenka/web/routes/profile.py`, `wishenka/bot/` (`principal.py`, `birthdays.py`, `entry.py`, `support.py`), and `wishenka/notices/` (`events.py`, `scheduler.py`, `reminders.py`, `store.py`) to use `telegram_id` and `wl_invite_tokens.wishlist_id` uniformly.
  - [x] Updated affected tests for `telegram_id` keys and `wl_invite_tokens.wishlist_id` / `support_tickets` schema; verified green pytest, ruff, and mypy.
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

- `ai-tasks/WISHENKA-188/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-188/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-188/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-188/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-188/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
