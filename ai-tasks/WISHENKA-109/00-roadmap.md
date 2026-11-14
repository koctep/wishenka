# Roadmap: WISHENKA-109

## Task Metadata

- **Implementation language**: Python (page templates and backend; primary) with JavaScript for the client script

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
- [x] **STEP 2: High-Level Architecture Design**
  - Artifact: `ai-tasks/WISHENKA-109/20-architecture.md` (own pointer-events implementation, visible handle in summary, Telegram disableVerticalSwipes 7.7+ with degradation; no committed CDP test, left to WISHENKA-110)
- [x] **STEP 3: Failing Repro Test**
  - [/] `tests/test_wishlist_touch_reorder.py` (red: 31 failed, 6 passed guards; failures: handle not in summary and still in details, wishlist.js lacks pointer/touch/Telegram tokens, miniapp.css lacks handle touch declarations and drag feedback rules)
- [x] **STEP 4: Development**
  - [x] Markup: `partials/item_card.html` handle moved into `.item-card-summary` inner flex row before the thumbnail (`data-no-toggle`, `aria-hidden="true"`, only under `can_edit_wishlist`); removed from `.item-actions`
  - [x] CSS: `miniapp.css` handle (touch-action none, user-select none, -webkit-touch-callout none, min 44px), `.is-touch-dragging` (hides details via display none, no change to `hidden`/`aria-expanded`), `.drop-before`, `.drop-after`, `body/html.is-touch-reordering`; summary has no touch-action
  - [x] JS: `wishlist.js` Pointer Events touch reorder (touch only, 4 px threshold, pointer capture, all cancel triggers, elementFromPoint hit-test, rAF autoscroll, click suppressor, dragstart guard, Telegram swipes 7.7 guarded and restored, haptics guarded, SDK calls in try/catch); mouse `drop` refactored onto shared `isAfterMidpoint` and `submitReorder` (single `htmx.ajax`, same warn message and guards)
  - [x] Green: `tests/test_wishlist_touch_reorder.py` 37 passed; also test_wishlist_static_script, test_wish_items_list_reorder_ui, test_wish_card_giver_controls, test_reservations_cabinet_ui (44 passed), test_wish_items_tma_ui (12 passed); `make analyze` clean (ruff, format, mypy); `node --check` ok. No other test depended on the old handle location (grep of tests/)
  - [x] Throwaway Chromium CDP run (not committed; mobile viewport 390x844, touch emulation, offline htmx stub recording `htmx.ajax`, Telegram WebApp stub): touch drag from collapsed card handle onto lower half of last card sent exactly one POST `/web/wishlists/1/items/reorder` with ids [2,3,1] and cleared transform/classes; Telegram stub saw disable, impact, selection, enable in order; tap on handle did nothing (no toggle, no request); tap on summary toggled `aria-expanded`; expanded-card drag sent one request; touchCancel, Escape, second finger, drop on self: no request and state cleaned; vertical swipe outside handle sent no request; synthetic mouse dragstart/drop path sent the same request as before
  - [x] Observation: dragging an expanded card hides its details (display none) so the list shifts up under the finger at drag start; the hit-test uses live layout so the drop works, but the jump is visible. Candidate for Step 7 tech debt or a UX decision
  - [ ] Not verified (needs real devices): real Telegram WebView on iOS and Android, whether `disableVerticalSwipes()` at pointerdown is early enough to stop the minimize swipe, native `dragstart` behaviour from long-press on Chrome Android, pull-to-refresh/overscroll, autoscroll feel and speed constants, and the autoscroll path (not exercised in CDP run); CDP touch emulation is not a real touch stack. Manual checklist in 20-architecture.md section (d) remains open
- [x] **STEP 5: Code Cleanup**
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-109/50-observability.md` (server logs reviewed, not changed; SDK warning now names the failing call; no metrics or client telemetry, N/A)
- [x] **STEP 7: Technical Debt Analysis**
- [x] **STEP 8: Dev Docs**
  - [x] `doc/dev/miniapp.md`: 9.8 (handle in summary, manual order), 9.8.1 (shared `isAfterMidpoint`/`submitReorder`, touch reorder, Telegram integration, warnings, accessibility, limits, tests, related debts WISHENKA-139 to 144), troubleshooting item 12
  - [x] `doc/dev/wishlists.md`: static tree comment, `base.html` and `item_card.html` descriptions (handle location)
  - [x] `doc/dev/reservations.md`, `items.md`, `architecture.md`, `in-docs/`, `specs/`: grep found no stale handle or touch statements, no change
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-109/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-109/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-109/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-109/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-109/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
