# Roadmap: WISHENKA-30

## Task Metadata

- **Implementation language**: Python 3.12+

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-30/10-requirements.md`
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-30/20-architecture.md`
- [x] **STEP 3: Failing Repro Test**
  - `tests/test_bot_support_repro.py`
- [x] **STEP 4: Development**
  - [x] Iteration 1: Added support channel configuration to `wishenka/config.py`, Alembic migration `add_support_channel.py` (`support_input` and `support_tickets`), and extended `cleanup_drafts` in `wishenka/bot/capture.py`.
  - [x] Iteration 2: Implemented `DiagnosticContext`, `generate_ticket_ref`, `redact_capabilities`, `format_support_ticket`, and `clear_support_session` in `wishenka/bot/support.py`.
  - [x] Iteration 3: Added localized RU/EN support copy and metadata-only `collect_diagnostic_context` query helper in `wishenka/bot/support.py`.
  - [x] Iteration 4: Added clock, destination resolution, cancel keyboard, and atomic `_open_support_session` helpers in `wishenka/bot/support.py`.
  - [x] Iteration 5: Implemented `_submit_support_message` with validation, sliding-window rate limiting, capability redaction, multi-destination delivery, and truthful failure handling in `wishenka/bot/support.py`.
  - [x] Iteration 6: Implemented `create_support_router` handling `/support`, `support:open`, `support:cancel`, `/cancel`, non-text rejections, and active session text interception in `wishenka/bot/support.py`.
  - [x] Iteration 7: Wired `create_support_router`, `/help`, menu support button, and session superseding into `wishenka/bot/entry.py`, `wishenka/bot/birthdays.py`, and `wishenka/bot/__main__.py`.
  - [x] Iteration 8: Refined `generate_ticket_ref` and `DiagnosticContext.submitted_at_iso` formatting in `wishenka/bot/support.py` so `tests/test_bot_support_repro.py` passes completely.
  - [x] Iteration 9: Added unit and Alembic migration upgrade/downgrade tests in `tests/test_bot_support.py`.
  - [x] Iteration 10: Added integration tests for session mutual exclusion, partial destination delivery, stored language preference, and ticket retention cleanup in `tests/test_bot_support.py`.
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-30/40-code-cleanup.md`
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-30/50-observability.md`
  - `wishenka/bot/support.py` (added partial destination failure `WARNING` event `bot_support_unavailable` with `reason="partial_send_failed"` and `outcome="partial"` on `bot_support_submitted`)
  - `tests/test_bot_support.py` (added observability event, `JsonFormatter`, partial-delivery, and dispatcher error-boundary redaction tests)
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-30/60-tech-debt.md`
- [x] **STEP 8: Dev Docs**
  - `doc/dev/bot-support.md`
  - `doc/dev/bot-scenarios.md`
  - `doc/dev/migrations.md`
  - `doc/dev/architecture.md`
  - `doc/dev/gift-receipt.md`
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-30/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-30/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-30/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-30/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-30/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
