# Roadmap: WISHENKA-108

## Task Metadata

- **Implementation language**: Python (primary: backend and Jinja templates); JavaScript for the extracted static script

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-108/10-requirements.md` — business requirements documented.
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-108/20-architecture.md` — architecture, test strategy and failing-repro plan drafted.
- [x] **STEP 3: Failing Repro Test**
  - [x] `tests/test_wishlist_static_script.py` — groups A-D (11 tests): 10 red (inline toggle/DnD still in `base.html`, `/static/wishlist.js` returns 404, inline `onclick`/`onkeydown` on cards, no `data-wishlist-id` on `#items-list`); 1 green by design (`test_guard_no_swap_replaces_items_list_container`, hx-swap guard). `make analyze` clean.
- [x] **STEP 4: Development**
  - [x] Added `wishenka/web/static/wishlist.js` (IIFE; delegated click/keydown toggle; DnD reads id from `#items-list[data-wishlist-id]`); removed toggle/DnD from `base.html`, inline handlers from `item_card.html`; added `data-wishlist-id` to owner and share pages; red repro `tests/test_wishlist_static_script.py` is green (11 passed)
  - [x] Updated `tests/test_wish_items_list_reorder_ui.py` and `tests/test_wish_card_giver_controls.py` (location-only); related UI tests green (reorder, giver controls, reservations cabinet, items CRUD/TMA: 73 passed); `make analyze` green
  - [x] Manual Chromium CDP sanity (throwaway script, not committed; htmx stubbed, CDN blocked): click toggles aria-expanded, Enter toggles back, simulated drop sends POST `/web/wishlists/1/items/reorder` with `item_ids` ["2","1"]
- [x] **STEP 5: Code Cleanup**
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-108/50-observability.md` — reorder server logs already exist (reviewed); client `console.warn` made specific; metrics and client telemetry N/A.
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-108/60-tech-debt.md` — 5 follow-ups, all NON-BLOCKER; no timeout-marker blocker.
- [x] **STEP 8: Dev Docs**
  - [x] `doc/dev/miniapp.md` — component list, 9.8 toggle/DnD text, new 9.8.1 `wishlist.js` section
  - [x] `doc/dev/wishlists.md` — template/static tree, `base.html` and `share_wishlist.html` specs, card toggle
  - [x] `doc/dev/reservations.md` — toggle exclusion note; CSRF and reservation inline-script mentions unchanged
  - [x] `doc/dev/items.md`, `doc/dev/architecture.md` — no toggle/DnD client code described; no change
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-108/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-108/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-108/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-108/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-108/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
