# Roadmap: WISHENKA-328

## Task Metadata

- **Implementation language**: Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-328/10-requirements.md`
  - Birthday list and the profile chat lookup must leave the exclusive lock to
    saves. Two bot saves must use the existing temporary-unavailable outcome.
    The shared wishlist request and WISHENKA-342 stay unchanged.
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-328/20-architecture.md` — birthday list and the
    post-locale chat lookup use a read-only `BEGIN`. The private-chat save
    and the confirmation save go through `UserStore._immediate`.
- [x] **STEP 3: Failing Repro Test**
  - `tests/test_wishenka_328_read_lock_and_bot_busy_repro.py`
  - Birthday list and the profile chat lookup still open with `BEGIN IMMEDIATE`.
    A locked private-chat save and a locked confirmation save still raise the
    driver database error instead of `UserStoreBusyError`.
- [x] **STEP 4: Development**
  - [x] Birthday list and the active-chat lookup open with `read_only`
    `begin()`. Private-chat and confirmation saves call `UserStore.write`.
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-328/40-code-cleanup.md`
  - Scoped files already met Ruff, Mypy, and the 100-character limit. No edits.
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-328/50-observability.md`
  - Birthday list and the chat lookup emit `BEGIN` through the existing
    listener and add no log. `UserStore.write` forwards to `_immediate`.
    A busy save uses the existing `user_store_busy` warning. No production
    change.
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-328/60-tech-debt.md`
  - No new follow-up. Birthday list and the active-chat lookup open with
    read-only `BEGIN`. Private-chat and confirmation saves call
    `UserStore.write`. The repro file has `pytest.mark.timeout(30)`.
- [x] **STEP 8: Dev Docs**
  - `doc/dev/notifications.md` — the birthday list opens with read-only `begin()` so the listener emits `BEGIN`. Recording a private chat and reservation confirmations call `UserStore.write`.
  - `doc/dev/users.md` — the active-chat lookup opens with read-only `begin()` so the listener emits `BEGIN`. `UserStore.write` forwards to `_immediate` once.
  - `doc/dev/bot-scenarios.md` and `doc/dev/bot-support.md` — recording a private chat calls `UserStore.write` with operation `record_private_chat`.
  - `UserStore._read` (WISHENKA-342) and the wishlist dependency stay as documented.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-328/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-328/20-architecture.md`

### STEP 3: Failing Repro

- `tests/test_wishenka_328_read_lock_and_bot_busy_repro.py`

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-328/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-328/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-328/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
