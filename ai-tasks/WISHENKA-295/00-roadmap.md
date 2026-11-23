# Roadmap: WISHENKA-295

## Task Metadata

- **Implementation language**: Python, JavaScript, HTML, CSS

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-295/10-requirements.md`: the owner deletes their own wishlist from the
    wishlist settings with an explicit confirmation, a clear result, owner-only access and
    restoration under the existing "Recently deleted" rules.
  - Implementation language determined (Python, JavaScript, HTML, CSS) and recorded above.
  - Open questions and chosen decisions recorded in the Q&A of the requirements; awaiting the
    acceptance gate.
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-295/20-architecture.md`: owner-only idempotent `DELETE /api/wishlists/{id}`, inline
    confirmation panel in the Mini App list settings, i18n/CSS/a11y, observability, test strategy;
    awaiting the acceptance gate.
- [x] **STEP 3: Failing Repro Test**
  - `tests/test_wishlist_delete_api.py` (31 red), `tests/test_wishlist_delete_ui.py` (24 red,
    25 green guards/control), `tests/test_wishlist_delete_browser.py` (15 red); `make analyze`
    green; red reason: route and UI missing (405, no zone, missing catalog keys); no production
    change; awaiting the review subagent and the acceptance gate.
  - `ai-tasks/WISHENKA-295/30-failing-repro.md`: inventory, run commands, red evidence, mapping.
- [x] **STEP 4: Development**
  - [x] `DELETE /api/wishlists/{id}` (classify-first, idempotent 200, 410, 409, uniform 404),
    committed-mutation entry, `data-retention-days` on the Mini App shell, events
    `wishlist_deleted_by_owner` and `wishlist_delete_not_found`.
  - [x] Mini App delete zone, confirmation, pending, failure and success flow in `miniapp.js`,
    `miniapp.css` rules, 12 RU and EN `miniapp.wishlist_delete.*` keys in the embedded catalog.
  - [x] Red tests green: `tests/test_wishlist_delete_api.py`, `_ui.py`, `_browser.py` (95 of
    95); six test fixes for races and wrong helpers (offscreen clicks, deleted-list lookup,
    status wait, caplog setup record, ambiguous Cancel label), intent unchanged.
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-295/40-code-cleanup.md`: `make analyze` clean; removed one duplicate CSS
    rule; 119 tests green; awaiting the acceptance gate.
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-295/50-observability.md`: added WARNING `wishlist_delete_denied` (ids only);
    other paths pinned by `tests/test_wishlist_delete_observability.py` (8 tests); `make analyze`
    green; awaiting the acceptance gate. Step 8: add `wishlist_delete_denied`,
    `wishlist_delete_not_found`, `wishlist_deleted_by_owner` to the `doc/dev/wishlists.md` event
    table (~lines 1470-1514); `wishlist_delete_denied` is an addition to the D-7 table.
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-295/60-tech-debt.md`: no blockers; 4 new NON-BLOCKER follow-ups (Medium x2,
    Low x2) plus scope additions to WISHENKA-302/303; Jira links to be written by the orchestrator;
    awaiting review and the acceptance gate.
- [x] **STEP 8: Dev Docs**
  - `ai-tasks/WISHENKA-295/70-dev-docs.md`: updates of `doc/dev/wishlists.md`, `miniapp.md`,
    `i18n.md`, `testing.md`, `architecture.md`; awaiting review and the acceptance gate.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-295/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-295/20-architecture.md`

### STEP 3: Failing Repro

- Red automated test(s) or an `N/A` note
- `ai-tasks/WISHENKA-295/30-failing-repro.md`

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-295/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-295/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-295/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
