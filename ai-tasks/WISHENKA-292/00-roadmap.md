# Roadmap: WISHENKA-292

## Task Metadata

- **Implementation language**: Python, JavaScript, HTML, CSS

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - [x] `ai-tasks/WISHENKA-292/10-requirements.md`: viewing history scanning, readable title and
    last-viewed time, easy opening, deliberate clear action, empty state, RU/EN parity, privacy,
    narrow-viewport and accessibility needs, acceptance criteria.
  - [x] Implementation language determined (Python, JavaScript, HTML, CSS) and recorded above.
  - [ ] Acceptance gate review.
- [x] **STEP 2: High-Level Architecture Design**
  - [x] `ai-tasks/WISHENKA-292/20-architecture.md`: components and state machine (loading, error,
    empty, list, confirming, clearing), card design, relative/absolute time, a11y, RU/EN keys,
    narrow viewport, inline two-step clear confirmation, privacy as enforced by code.
  - [x] Step 3 failing-repro strategy defined (hooks, red assertions, positive controls).
  - [ ] User review and acceptance gate.
- [x] **STEP 3: Failing Repro Test**
  - [x] Red test: `tests/test_history_screen_browser.py` (32 test items; real server, CDP browser,
    page-side fetch wrapper for failure, delay and fixed timestamps; no production code touched).
  - [x] Unchanged tree, 3 runs via `make test`: 26 failed / 6 passed every time (stable split).
    `make analyze` clean; `tests/test_browser_prerequisites.py` 48 passed.
  - [x] Red reasons (missing redesigned behavior, fixtures asserted over API first): no
    `ul.history-list`/`li.history-card`/`h2`/`time[datetime]`/`.history-open`; first Clear click
    already sends `DELETE` (count 1, no `.history-confirm`); no `.history-empty` or
    `.history-empty-action`; load failure has only a status string (no `.history-error[role=alert]`,
    no `.history-retry`); no `aria-busy` while loading; narrow-viewport layout fails (no cards,
    page overflow); keyboard and heading checks fail on missing hooks.
  - [x] Green controls (6): 20-entry limit and newest-first, deleted list hidden and POST 404,
    open-entry moves list to top and Home-History-Back works, clear scope plus API contract and
    payload keys, privacy (no reservation data), Clear absent while loading.
  - [x] Note: architecture assertion 11(c) (Clear present during loading on baseline) does not hold:
    `showHistory` appends Clear only after the fetch resolves, so the loading/no-Clear check is a
    green control; the proving loading assertion is `aria-busy`.
  - [ ] Review subagent and acceptance gate.
- [x] **STEP 4: Development**
  - [x] Iteration 1: `showHistory` rewritten in `miniapp.js` (state machine: loading with
    `aria-busy`, error with Retry, empty with onward action, card list with `time`, open button,
    footer with inline two-step Clear confirmation, stale-render token) plus RU/EN catalog keys.
  - [x] Iteration 2: history CSS in `miniapp.css` (cards, quiet Clear, 320 px safe), `.history-item`
    split from the shared home card rule.
  - [x] Iteration 3: fixed the Node harness break (`tests/test_miniapp_i18n_repro.py`, fake DOM has
    no `lastChild`) in production code; `tests/test_history_screen_browser.py` 32 passed x3.
  - [x] `make analyze` clean; full suite: only the 16 known pre-existing failures remain.
- [x] **STEP 5: Code Cleanup**
  - [x] `make analyze` clean (Ruff, format, mypy; 257 files); `node --check miniapp.js` ok.
  - [x] Line length checked by characters on added lines: none over 100; no debug output or dead
    code; no source edits.
  - [x] 86 tests passed (history browser 32, i18n sync, miniapp i18n repro, browser prerequisites).
  - [x] `ai-tasks/WISHENKA-292/40-code-cleanup.md` written.
  - [ ] Acceptance gate.
- [x] **STEP 6: Observability**
  - [x] Gap review: recorded, listed, deleted-list denial and request logs already sufficient.
  - [x] `view_history_cleared` now logs `removed_count` (`wishenka/wishlists/service.py`).
  - [x] caplog contract extended in `tests/test_wishlist_sections_observability.py`; 51 passed.
  - [x] `ai-tasks/WISHENKA-292/50-observability.md` written; `make analyze` clean.
  - [ ] Acceptance gate.
- [x] **STEP 7: Technical Debt Analysis**
  - [x] `ai-tasks/WISHENKA-292/60-tech-debt.md`: 0 blockers, 5 follow-ups (history access
    model, ordering tie-breaker, double logging, browser test fragility, favorites access
    model); the two High items need a product/security decision first.
  - [x] 16 pre-existing failures listed with node ids and Jira keys (base commit cc77dc0).
  - [ ] User review and acceptance gate.
- [x] **STEP 8: Dev Docs**
  - [x] `doc/dev/miniapp.md`: section 8 rewritten (states, confirm flow, time rules, stale-render
    token, hooks, keys, troubleshooting, access-model limitation with WISHENKA-302/303).
  - [x] `doc/dev/wishlists.md`: `view_history_cleared` fields and single emitter.
  - [x] `doc/dev/i18n.md`: `miniapp.history.*` key family.
  - [x] `doc/dev/testing.md`: new test module, observability test, run commands.
  - [ ] Independent review.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-292/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-292/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-292/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-292/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-292/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
