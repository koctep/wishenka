# Roadmap: WISHENKA-182

## Task Metadata

- **Implementation language**: Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - Artifact: `ai-tasks/WISHENKA-182/10-requirements.md`
- [x] **STEP 2: High-Level Architecture Design**
  - Artifact: `ai-tasks/WISHENKA-182/20-architecture.md`
- [x] **STEP 3: Failing Repro Test**
  - `tests/test_wishenka_182_repro.py`
- [x] **STEP 4: Development**
  - [x] Added `WishlistStore.execute_read(work)` with `execution_options(read_only=True)` and deferred `BEGIN` in `_configure_immediate_transactions` (`wishenka/wishlists/store.py`)
  - [x] Replaced full-table token scans in `collect_diagnostic_context` with user-scoped lookups and moved rate-limit check + diagnostic collection onto `store.execute_read(...)` (`wishenka/bot/support.py`)
  - [x] Implemented `ensure_private_bot_user(...)` in `wishenka/bot/principal.py` and refactored `entry.py`, `support.py`, `birthdays.py`, and `capture.py` to delegate to it
  - [x] Verified `tests/test_wishenka_182_repro.py` (4 passed), `tests/test_bot_*.py` (97 passed total), `ruff check`, and `mypy wishenka`
- [x] **STEP 5: Code Cleanup**
  - [x] Verified `make analyze`, `ruff format --check wishenka tests`, `ruff check wishenka tests`, `mypy wishenka`, and `tests/test_wishenka_182_repro.py` (4 passed)
  - [x] Artifact: `ai-tasks/WISHENKA-182/40-code-cleanup.md`
- [x] **STEP 6: Observability**
  - [x] Audited `store.py`, `principal.py`, `support.py`, `entry.py`, `birthdays.py`, and `capture.py`; confirmed existing structured logging, `_private_bot_user` log suppression, `hide_parameters=True` / `aiosqlite` `WARNING` cap, and `redact_capabilities` cover observability without new log/metric additions
  - [x] Artifact: `ai-tasks/WISHENKA-182/50-observability.md`
- [x] **STEP 7: Technical Debt Analysis**
  - [x] Audited `store.py`, `principal.py`, `support.py`, `entry.py`, `birthdays.py`, `capture.py`, and `tests/test_wishenka_182_repro.py`; no Blocker or High severity debt found (1 Medium, 3 Low follow-ups documented)
  - [x] Artifact: `ai-tasks/WISHENKA-182/60-tech-debt.md`
- [x] **STEP 8: Dev Docs**
  - [x] Updated `doc/dev/wishlists.md` (`WishlistStore.execute_read` and deferred `BEGIN` via `read_only=True`)
  - [x] Updated `doc/dev/bot-support.md` (`ensure_private_bot_user`, user-scoped token lookup & regex-only redaction in `collect_diagnostic_context`, `execute_read` usage)
  - [x] Updated `doc/dev/bot-scenarios.md` (unified `wishenka/bot/principal.py:ensure_private_bot_user` and `bot_destinations` activation across `entry.py`, `support.py`, `birthdays.py`, `capture.py`)
  - [x] Updated `doc/dev/testing.md` (added `tests/test_wishenka_182_repro.py` coverage)
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-182/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-182/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-182/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-182/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-182/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
