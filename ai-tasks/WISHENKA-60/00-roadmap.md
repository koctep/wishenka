# Roadmap: WISHENKA-60

## Task Metadata

- **Implementation language**: Python 3.12+

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - [/] `ai-tasks/WISHENKA-60/10-requirements.md`
- [x] **STEP 2: High-Level Architecture Design**
  - [/] `ai-tasks/WISHENKA-60/20-architecture.md`
- [x] **STEP 3: Failing Repro Test**
  - [/] `tests/test_wishenka_60_repro.py`
- [x] **STEP 4: Development**
  - [x] Iteration 1: Updated `NoticeStore._eligible` in `wishenka/notices/store.py` to check `i.received_quantity > 0` instead of `i.is_archived = 0` so pending `gift_received` notices survive partial archival.
  - [x] Iteration 2: Updated `WishlistService._record_shared_event` and `transfer_ownership` in `wishenka/wishlists/service.py` and `update_wishlist` / `set_role` in `wishenka/web/routes/wishlists.py` to emit `list_updated` and `membership_changed` events and include open-reservation givers for `list_restored` and `list_updated`.
  - [x] Iteration 3: Updated `WishlistService._record_shared_event` in `wishenka/wishlists/service.py` and `_event_authorized`, `claim_reminder`, `refresh_reminder` in `wishenka/notices/reminders.py` to enforce recipient exclusion on reservation-derived eligibility and support `list_restored` / `list_updated` / ownership promotion.
  - [x] Iteration 4: Updated `claim_reminder` in `wishenka/notices/reminders.py` and `NoticeWorker.run_once` in `wishenka/notices/worker.py` to stamp `next_attempt_at = now` on terminal settlements, and extended `NoticeStore.purge_finished` in `wishenka/notices/store.py` to purge terminal rows from both `notification_outbox` and `reminder_outbox`.
- [x] **STEP 5: Code Cleanup**
  - [/] `ai-tasks/WISHENKA-60/40-code-cleanup.md`
- [x] **STEP 6: Observability**
  - [/] `ai-tasks/WISHENKA-60/50-observability.md`
  - [/] `tests/test_wishenka_60_observability.py`
- [x] **STEP 7: Technical Debt Analysis**
  - [/] `ai-tasks/WISHENKA-60/60-tech-debt.md`
- [x] **STEP 8: Dev Docs**
  - `doc/dev/notifications.md`
  - `doc/dev/gift-receipt.md`
  - `doc/dev/architecture.md`
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-60/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-60/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-60/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-60/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-60/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
