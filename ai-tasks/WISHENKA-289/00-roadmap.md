# Roadmap: WISHENKA-289

## Task Metadata

- **Implementation language**: Python, JavaScript, HTML, CSS

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-289/10-requirements.md`: documented business goal, home overview scope and
    Sprint 2120 boundaries (including `WISHENKA-296` creation-trigger compatibility), user stories,
    functional requirements for sections, card scannability, navigation, helpful empty states,
    recently deleted recovery, RU/EN mobile ergonomics, and verifiable Definition of Done.
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-289/20-architecture.md`: designed `#app` hub/nav hierarchy,
    `.reservations-card` entry, direct-child sections with `owner > admin > member > favorite`
    deduplication, scannable card open vs subordinate favorite removal, two-part empty states,
    RU/EN `<= 412px` CSS specs, preserved test contracts, and Step 3 red repro suites.
- [x] **STEP 3: Failing Repro Test**
  - [x] `tests/test_home_overview_ui.py`, `tests/test_home_overview_browser.py`: RED (`17 failed,
    2 passed` of 19; `startapp=create`/AST contract tests pass): failing on missing
    `miniapp.home.*` keys, collab-favorite dedup, `.reservations-card`,
    `.wishlist-card-open`/`.wishlist-card-remove`, two-part `.empty-state`, and deleted header.
- [x] **STEP 4: Development**
  - [x] `wishenka/i18n/catalog.py`: added 13 paired EN/RU `miniapp.home.*` keys for header lead,
    reservations hint, section subtitles, two-part empty-state hints, and `Open`/`Remove from
    favorites` labels with WCAG 2.5.3 Label-in-Name `aria-label` templates.
  - [x] `wishenka/web/static/miniapp.js`: implemented `#app` header + `.home-lead`,
    `.top-nav.home-top-nav` (2 buttons + `/settings`), `.reservations-card` via `DOMParser` +
    `node()`, direct-child `.wishlist-section` (`--owned`, `--collab`, `--favorites`, conditional
    `--deleted`) with `owner > admin > member > favorite` dedup, scannable `.wishlist-card`
    (`Open` vs subordinate `Remove from favorites`), and two-part `.empty-state`.
  - [x] `wishenka/web/static/miniapp.css`: added `WISHENKA-288`-aligned `#app` Home hub,
    `.reservations-card`, section border cues, card anatomy, `.empty-state`, `>= 44px` touch
    targets, `:focus-visible`, and `<= 412px` / `360px` wrap rules with zero horizontal overflow.
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-289/40-code-cleanup.md`: simplified `.history-time`/`.deleted-meta` CSS
    order, added helper docstrings in `tests/test_home_overview_ui.py`, removed unused `"fav_id"`
    in `tests/test_home_overview_browser.py`, and verified linters, `<= 100` line lengths, and
    102 passing tests across 10 suites.
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-289/50-observability.md`: audited WISHENKA-289 client/i18n/CSS scope,
    documented existing server and client observability covering Home overview endpoints and error
    fallbacks, and verified observability, i18n, and Home overview test suites.
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-289/60-tech-debt.md`: analyzed shortcuts, code quality, test coverage,
    performance, architecture alignment, and follow-up debt (`0` blockers, `0` new unticketed
    follow-ups; sibling Sprint 2120 stories and tracked Jira debt cross-referenced).
- [x] **STEP 8: Dev Docs**
  - `doc/dev/miniapp.md`, `doc/dev/testing.md`: documented WISHENKA-289 Home overview hub,
    `.reservations-card`, section modifiers and role-precedence deduplication, scannable card
    anatomy, two-part empty states, additive CSS tokens, `miniapp.home.*` i18n keys, and the
    `test_home_overview_ui.py` / `test_home_overview_browser.py` test suites.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-289/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-289/20-architecture.md`

### STEP 3: Failing Repro

- `tests/test_home_overview_ui.py`
- `tests/test_home_overview_browser.py`

### STEP 4: Development

- `wishenka/i18n/catalog.py`
- `wishenka/web/static/miniapp.js`
- `wishenka/web/static/miniapp.css`

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-289/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-289/50-observability.md`

### STEP 7: Technical Debt Analysis

- `ai-tasks/WISHENKA-289/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
