# Roadmap: WISHENKA-128

## Task Metadata

- **Implementation language**: Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - [x] `ai-tasks/WISHENKA-128/10-requirements.md`
- [x] **STEP 2: High-Level Architecture Design**
  - [x] `ai-tasks/WISHENKA-128/20-architecture.md`
- [x] **STEP 3: Failing Repro Test**
  - [x] `tests/test_wishlist_migration_rollback_policy.py`
- [x] **STEP 4: Development**
  - [x] Declared `ROLLBACK_POLICY` (`"one-way"` / `"reversible"`) across all 16 Alembic revisions under `wishenka/wishlists/alembic/versions/` and added `ROLLBACK_POLICY` to `wishenka/wishlists/alembic/script.py.mako`
  - [x] Guarded `base_normalized.downgrade()` by default with `NotImplementedError` + backup guidance and `WISHENKA_ALLOW_DESTRUCTIVE_BASELINE_DOWNGRADE=1` opt-in, and standardized backup-restoration `NotImplementedError` messages on `add_warn_on_delete_reserved`, `add_display_order`, and `add_gift_receipts`
  - [x] Fixed offline (`sql=True`) execution in `add_gift_receipts.py`, `add_notice_uncertain.py`, `add_user_locale.py`, `add_notice_retention_columns.py`, and `add_user_fk_cascades.py` using `context.is_offline_mode()`
  - [x] Added `test_baseline_downgrade_succeeds_with_explicit_opt_in` and updated offline test in `tests/test_wishlist_migration_rollback_policy.py`; verified 11/11 pass and `make analyze` clean
- [x] **STEP 5: Code Cleanup**
  - [x] `ai-tasks/WISHENKA-128/40-code-cleanup.md`
- [x] **STEP 6: Observability**
  - [x] `ai-tasks/WISHENKA-128/50-observability.md`
- [x] **STEP 7: Technical Debt Analysis**
  - [x] `ai-tasks/WISHENKA-128/60-tech-debt.md`
- [x] **STEP 8: Dev Docs**
  - `doc/dev/migrations.md`
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-128/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-128/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-128/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-128/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-128/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
