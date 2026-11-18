# Roadmap: WISHENKA-181

## Task Metadata

- **Implementation language**: Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - [x] `ai-tasks/WISHENKA-181/00-roadmap.md`
  - [x] `ai-tasks/WISHENKA-181/10-requirements.md`
- [x] **STEP 2: High-Level Architecture Design**
  - [x] `ai-tasks/WISHENKA-181/20-architecture.md`
- [x] **STEP 3: Failing Repro Test**
  - [ ] `tests/test_wishenka_181_repro.py`
- [x] **STEP 4: Development**
  - [x] Iteration 1: Added Alembic migration `add_notice_retention_columns` (backfilling legacy deleted birthdays, `bot_destinations.updated_at`, and `notice_receipt_keys.created_at`) and retention settings in `wishenka/config.py`.
  - [x] Iteration 2: Extracted `wishenka/notices/destinations.py` (`upsert_bot_destination`, `deactivate_bot_destination`), wired all bot/notice call sites, added immediate PII anonymization on birthday deletion in `wishenka/bot/birthdays.py`, and timestamped `notice_receipt_keys` inserts in `wishenka/wishlists/store.py`.
  - [x] Iteration 3: Added active-cycle guard to `NoticeStore.purge_finished`, implemented `NoticeStore.purge_retention_records`, wired both into `run_cleanup_cycle` (`CleanupStats`), and verified all 4 repro tests in `tests/test_wishenka_181_repro.py` pass.
  - [x] Iteration 4: Added edge-case unit/integration tests in `tests/test_notice_retention.py` (Alembic upgrade/downgrade, uncertain recovery resolution, replay protection, settings validation) and verified `make analyze` and `make test`.
- [x] **STEP 5: Code Cleanup**
  - [x] `ai-tasks/WISHENKA-181/40-code-cleanup.md`
- [x] **STEP 6: Observability**
  - [x] `ai-tasks/WISHENKA-181/50-observability.md`
- [x] **STEP 7: Technical Debt Analysis**
  - [x] `ai-tasks/WISHENKA-181/60-tech-debt.md`
- [x] **STEP 8: Dev Docs**
  - [x] `doc/dev/notifications.md`
  - [x] `doc/dev/migrations.md`
  - [x] `doc/dev/wishlists.md`
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-181/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-181/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-181/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-181/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-181/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
