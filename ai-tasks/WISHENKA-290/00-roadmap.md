# Roadmap: WISHENKA-290

## Task Metadata

- **Implementation language**: Python, JavaScript, HTML, CSS

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-290/10-requirements.md`: documented business goal, specific wishlist view
    and management workspace scope and Sprint 2120 boundaries, business entities, user stories,
    functional requirements for wishlist header/wishes priority, non-distracting settings with
    save vs cancel clarity, public sharing vs collaborator invitation separation, self-explanatory
    member roles and controls, RU/EN mobile ergonomics, Surprise Invariant preservation, and
    verifiable Definition of Done.
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-290/20-architecture.md`: defined wishlist workspace hierarchy (header with
    occasion metadata, wishes-first section, non-distracting settings with save/cancel feedback,
    public gift link vs co-author invite separation, badged member rows), preserved test contracts,
    and Step 3 red repro plan.
- [x] **STEP 3: Failing Repro Test**
  - `tests/test_wishlist_detail_ui.py`: red Node VM and catalog assertions for wishlist regions,
    archived controls, role-based restoration, optional header data, fallback titles, and localized
    role badges in both locales, including badges on each member row.
  - `tests/test_wishlist_detail_browser.py`: mobile region order, overflow, and touch targets in
    both locales; required action groups and non-overlapping controls with long Russian text;
    visual distinctions; settings
    save/cancel/failure; public and invitation copy/share; member actions; favorite and restore.
  - Chromium is available at `/usr/bin/chromium`. Targeted tests ran red on missing new workspace
    regions, controls, and translations; production code remains unchanged. The interactions after
    the first missing control require verification once development implements the new interface.
  - Follow-up: browser fixtures configure share links and scroll before clicking controls.
- [x] **STEP 4: Development**
  - [x] Reworked the wishlist header and wishes-first content while preserving role restrictions.
  - [x] Grouped settings, gift links, collaborator invitations, and participant controls with
    change feedback, localized copy, and responsive detail styles.
  - [x] Targeted regression run: 73 passed, including Chromium and localization tests.
  - [x] Full suite: 2,023 passed, 2 skipped, and 16 failed; all 16 failures reproduce at HEAD.
    The orchestrator is responsible for recording the pre-existing failures in Jira.
  - [x] Distinguish failed refresh after save from a failed save, and retain the load error after
    failed cancellation; added browser coverage for both paths (31 targeted tests passed).
  - [x] Hide outdated controls during refresh after changes and offer retry if loading fails;
    covered link replacement, roles, membership, favorites, and restore in browser tests.
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-290/40-code-cleanup.md`: recorded formatting, typing and validation.
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-290/50-observability.md`: documented existing request and operation logs,
    privacy boundaries, client-only failure visibility, metrics decision, and validation.
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-290/60-tech-debt.md`: recorded implementation trade-offs and the
    existing Jira issues covering the 16 baseline test failures.
- [x] **STEP 8: Dev Docs**
  - `doc/dev/miniapp.md`: documented detail layout, role-specific controls, link configuration,
    refresh failures, and focused verification; corrected cancellation and public-link behavior.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-290/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-290/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-290/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-290/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-290/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
