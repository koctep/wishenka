# Roadmap: WISHENKA-156

## Task Metadata

- **Implementation language**: Python 3.12+

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-156/10-requirements.md`
- [x] **STEP 2: High-Level Architecture Design**
  - [x] `ai-tasks/WISHENKA-156/20-architecture.md`
- [x] **STEP 3: Failing Repro Test**
  - [x] `N/A — no behavioral change` (test and documentation task verifying existing notice worker/sender behavior; see `20-architecture.md`)
- [x] **STEP 4: Development**
  - [x] Iteration 1: Registered `telegram_smoke` marker in `pyproject.toml`.
  - [x] Iteration 2: Created `tests/test_telegram_notice_smoke.py` with opt-in live Telegram smoke tests (`WISHENKA_TELEGRAM_SMOKE_TOKEN`, `WISHENKA_TELEGRAM_SMOKE_CHAT_ID`, optional `WISHENKA_TELEGRAM_SMOKE_INVALID_CHAT_ID`) and offline guard checks.
  - [x] Iteration 3: Created `tests/test_notice_worker_concurrency.py` with 2-process spawned `NoticeStore` + `NoticeWorker.run_once` race test over WAL SQLite (`Barrier(2)`, `join(timeout=15)`).
  - [x] Verified `.venv/bin/pytest tests/test_telegram_notice_smoke.py tests/test_notice_worker_concurrency.py tests/test_receipt_notices.py tests/test_notice_operator.py` (37 passed, 2 skipped) and `make analyze` (`ruff check`, `ruff format --check`, `mypy` — all passed).
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-156/40-code-cleanup.md`
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-156/50-observability.md` (`N/A` — test and documentation task with no production code changes)
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-156/60-tech-debt.md`
- [x] **STEP 8: Dev Docs**
  - `doc/dev/notifications.md` (FR-2 manual verification checklist for live Telegram notice delivery)
  - `doc/dev/testing.md` (`tests/test_telegram_notice_smoke.py` with `telegram_smoke` marker and `tests/test_notice_worker_concurrency.py` 2-process worker race test)
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-156/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-156/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-156/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-156/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-156/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
