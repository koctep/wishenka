# Roadmap: WISHENKA-218

## Task Metadata

- **Implementation language**: `Python`

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-218/00-roadmap.md`
  - `ai-tasks/WISHENKA-218/10-requirements.md`
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-218/20-architecture.md`
- [x] **STEP 3: Failing Repro Test**
  - `tests/test_wishenka_218_repro.py`
- [x] **STEP 4: Development**
  - [x] Replaced occupied-units floor with `max(1, received_quantity)` in `WishlistService.update_wish_item` (`wishenka/wishlists/service.py`), preserving open promises on over-booking and queuing `item_quantity_overbooked` events for open-promise givers (excluding them from `item_updated`).
  - [x] Added `item_quantity_overbooked` support in `wishenka/notices/events.py`, `wishenka/notices/reminders.py`, and EN/RU `wishenka/i18n/catalog.py`, and updated `web.item.quantity_below_reserved` to cite only `received_quantity`.
  - [x] Removed `reserved_quantity` / `locked_quantity` display and validation from `wishenka/web/routes/items_ui.py` and `wishenka/web/templates/partials/item_edit_modal.html`.
  - [x] Updated legacy tests (`test_wish_items_tma_ui.py`, `test_wish_items_crud_api.py`, `test_gift_receipt_service.py`, `test_shared_inventory_multiprocess.py`, `test_item_observability.py`, `test_reservations_surprise_invariant.py`) to align with FR-5 / Q12 and verified `tests/test_wishenka_218_repro.py` green.
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-218/40-code-cleanup.md`
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-218/50-observability.md`
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-218/60-tech-debt.md`
- [x] **STEP 8: Dev Docs**
  - Updated `doc/dev/items.md`, `reservations.md`, `miniapp.md`, `gift-receipt.md`, and
    `notifications.md` for quantity editing, privacy, and notice delivery.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-218/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-218/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-218/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-218/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-218/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
