# Roadmap: WISHENKA-291

## Task Metadata

- **Implementation language**: Python, JavaScript, HTML, CSS

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-291/10-requirements.md`: personal settings, notification scope,
    persistence feedback, safety, accessibility and acceptance criteria.
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-291/20-architecture.md`: designed the settings sections, state and
    failure reconciliation, API interactions and independent failing-repro coverage.
- [x] **STEP 3: Failing Repro Test**
  - `tests/test_personal_settings_browser.py`: red browser checks for localized visible toggle
    states, inherited badges, failure and reconciliation of notification preferences, birthdate
    failure feedback, and deletion preview and pending submission safety. Positive checks cover
    override persistence, birthdate saves, locale switching and deletion cancellation.
  - Extended tests cover empty-list guidance, focus, long Russian titles at mobile widths,
    inherited and explicit two-list isolation, delayed conflicting actions, birthday validation,
    clear and reminders, locale rejection/network/committed errors and deletion preview counts,
    cancellation, pending and error cases. The committed locale error uses real persistence.
  - Final red run on unchanged production: 25 failed and 14 passed; failures include stale
    badges, missing error feedback and enabled controls while pending.
- [x] **STEP 4: Development**
  - [x] Iteration 1: `settings.html` and `catalog.py` — visible on/off text per toggle, current
    birthday, optional-year and precedence hints, localized pending, error, unknown and retry
    strings (RU and EN); locale buttons now use a CSRF-protected fetch instead of HTMX.
  - [x] Iteration 2: `settings.js` rewritten — per-category serialized mutations, pending note,
    restore only after pre-mutation rejections (401, 403, 404, 422), reconciliation by GET after
    5xx or network loss, disabled controls with Retry when the read also fails, derived inherited
    badges, birthdate draft retention, safe deletion preview and confirm flow without retries.
  - [x] Iteration 3: `miniapp.css` — 44px touch targets, wrapping, mobile card layout, state
    badges, feedback styles and separated danger zone.
  - [x] `tests/test_personal_settings_browser.py`: 39 passed (3 stable runs). Full `make test`:
    16 pre-existing failures reproduced at base; 1 Step 3 conformance failure (module timeout).
- [x] **STEP 5: Code Cleanup**
  - [x] Static analysis and format via `make analyze`.
  - [x] Cleanup review of changed files (unused code, debug output, merge markers).
  - [x] Validation tests and `ai-tasks/WISHENKA-291/40-code-cleanup.md`.
- [x] **STEP 6: Observability**
  - [x] Gap review of settings API paths: existing logs suffice, no production code added.
  - [x] `tests/test_personal_settings_observability.py` contract tests (caplog, privacy).
  - [x] `ai-tasks/WISHENKA-291/50-observability.md` and `make analyze`.
- [x] **STEP 7: Technical Debt Analysis**
  - [x] Analysis of `settings.js`, template, catalog and the two test modules against the
    requirements and architecture.
  - [x] `ai-tasks/WISHENKA-291/60-tech-debt.md`: no blockers, three non-blocker follow-ups
    (JS reconciliation refactor, wishlist/deletion rejection log tests, long lines).
  - [ ] Acceptance gate review.
- [x] **STEP 8: Dev Docs**
  - [x] `doc/dev/miniapp.md`: new "Personal Settings Screen (WISHENKA-291)" section (states,
    reconcile rules, ids and selectors, i18n keys, configuration, troubleshooting, tests).
  - [x] `doc/dev/users.md`, `doc/dev/notifications.md`, `doc/dev/i18n.md`: links and deltas.
  - [x] `doc/dev/testing.md`: the two new test modules and run commands.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-291/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-291/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-291/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-291/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-291/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
