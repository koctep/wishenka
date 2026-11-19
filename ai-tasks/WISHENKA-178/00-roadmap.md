# Roadmap: WISHENKA-178

## Task Metadata

- **Implementation language**: Python 3.12+

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - [x] `ai-tasks/WISHENKA-178/10-requirements.md` — documented business goals, user stories, functional scope, non-functional requirements, constraints, business entities, scenarios, and Q&A
- [x] **STEP 2: High-Level Architecture Design**
  - [/] `ai-tasks/WISHENKA-178/20-architecture.md` — high-level architecture, schema migration, retention & cleanup design, and Step 3 failing-repro plan
- [x] **STEP 3: Failing Repro Test**
  - [ ] `tests/test_bot_capture_order_retention_repro.py` — red repro tests for schema/backfill/index, bounded stale watermark cleanup, late-delivery protection after draft expiry, active-conversation preservation, and fresh baseline after cleanup
- [x] **STEP 4: Development**
  - [x] Added `wishenka/wishlists/alembic/versions/add_bot_capture_order_retention.py` (`updated_at INTEGER`, `idx_bot_capture_order_updated_at`, backfill, reversible downgrade) and `bot_capture_order_retention_days` (`default=30, ge=2`) in `wishenka/config.py`
  - [x] Updated `wishenka/bot/capture.py` (`reserve()`, `update()`, `mutate()`, `_touch_capture_order()`, bounded `cleanup_drafts()` with active-draft guard) and `wishenka/bot/__main__.py` (`cleanup_loop` forwarding `order_retention_days`)
  - [x] Added `tests/test_bot_capture_order_retention.py` (watermark refresh on edit/save, settings validation, `cleanup_loop` forwarding, immediate account deletion, Alembic downgrade) and verified all repro and related tests pass
- [x] **STEP 5: Code Cleanup**
  - [/] `ai-tasks/WISHENKA-178/40-code-cleanup.md` — code cleanup and static analysis report
- [x] **STEP 6: Observability**
  - [/] `ai-tasks/WISHENKA-178/50-observability.md` — observability analysis and logging verification
- [x] **STEP 7: Technical Debt Analysis**
  - [/] `ai-tasks/WISHENKA-178/60-tech-debt.md` — technical debt analysis
- [x] **STEP 8: Dev Docs**
  - [x] `doc/dev/bot-scenarios.md` — documented `bot_capture_order.updated_at` retention, `WISHENKA_BOT_CAPTURE_ORDER_RETENTION_DAYS` (`Settings.bot_capture_order_retention_days = 30`, `ge=2`), bounded `LIMIT 100` `cleanup_drafts` purge with active-draft guard, `bot_draft_cleanup_completed` structured logging, and retention test commands
  - [x] `doc/dev/migrations.md` — added `add_bot_capture_order_retention` (`head`, `reversible` rollback policy, offline-mode branching)
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-178/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-178/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-178/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-178/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-178/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
