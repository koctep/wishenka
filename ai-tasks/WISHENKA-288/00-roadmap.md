# Roadmap: WISHENKA-288

## Task Metadata

- **Implementation language**: HTML, CSS, JavaScript

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-288/10-requirements.md`
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-288/20-architecture.md`
- [x] **STEP 3: Failing Repro Test**
  - `tests/test_visual_identity_browser.py`: real offline Chromium checks on Mini App home and
    server-rendered settings; initial run produced two intended failures: create/history and
    save/clear/delete actions have identical computed styles. Selected, disabled and keyboard
    focus semantics are also checked. Both shells are additionally checked for coherent light
    canvases and distinguishable light section surfaces; these existing baseline properties pass.
  - RED: `CHROMIUM_LIB=/tmp/wishenka-chromium/usr/lib/aarch64-linux-gnu;
    WISHENKA_CHROMIUM_BIN=/tmp/wishenka-chromium/usr/lib/chromium/chromium-headless-shell
    LD_LIBRARY_PATH="$CHROMIUM_LIB:$CHROMIUM_LIB/pulseaudio"
    make test-serial PYTEST_ARGS='tests/test_visual_identity_browser.py -q --tb=short'`:
    2 failed for the expected visual distinctions. Chromium ARM64 and its dependencies were
    extracted into `/tmp/wishenka-chromium` without changing system packages.
- [x] **STEP 4: Development**
  - [x] Introduced shared blush, plum and cherry tokens, light surfaces, readable fields, focus
    and disabled states, action hierarchy, card styling and explicit semantic hooks in Mini App
    and settings; preserved existing handlers, roles and Telegram themed modal colors.
  - [x] Preserved the receipt/modal theme pair and corrected close-button contrast in dark theme;
    inspected mobile home and settings in English and Russian against the supplied reference.
  - [x] Browser regression: 38 passed across visual identity, receipt theme/accessibility,
    localization, surprise privacy and Telegram Mini App suites. `make analyze`, `node --check`
    and `git diff --check` passed. An additional existing HTMX smoke test failed waiting for
    a CSRF token (HTTP 401), tracked in WISHENKA-267 and reported in the WISHENKA-93 baseline.
  - [x] Closed Step 4 B2 review gaps: inherited heading foreground (`h1`/`h2`/`h3`) inside
    `.receipt-sheet` and `.modal-sheet`, added shared button geometry and 44px touch-target
    sizing for link buttons (`a.btn`, `a.btn-primary`, `a.btn-danger`), enforced high-contrast
    `:focus-visible` outlines inside `.receipt-sheet` and `.modal-sheet`, and added browser
    regression checks in `tests/test_visual_identity_browser.py`.
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-288/40-code-cleanup.md`: removed dead `--border` token and duplicate
    hover/`:focus-visible` CSS rules in `miniapp.css`, wrapped long CSS, Python and template
    lines (`member_list.html`, `settings.html`), consolidated `_assert_focus_visible` and fixed
    `focus` shadowing in `tests/test_visual_identity_browser.py`; verified `node --check`,
    `git diff --check`, `make analyze` (250 files), and 68 targeted browser/i18n tests passed.
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-288/50-observability.md`: audited presentation-only scope (`miniapp.css`,
    `miniapp.js` UI classes, `member_list.html`, `settings.html`); no new production logging
    needed, existing structured logs and checks verified (`72 passed`).
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-288/60-tech-debt.md`: `0` blockers and `0` new unticketed follow-ups
    beyond Sprint 2120 stories (`WISHENKA-289`..`WISHENKA-296`) and tracked Jira baseline items
    (`WISHENKA-297`, `WISHENKA-267`, `WISHENKA-226`, `WISHENKA-235`, `WISHENKA-266`,
    `WISHENKA-239`, `WISHENKA-240`).
- [x] **STEP 8: Dev Docs**
  - `doc/dev/miniapp.md`, `doc/dev/testing.md`: documented shared `miniapp.css` palette tokens,
    action hierarchy, 44px link-button targets, `:focus-visible`/disabled/active locale states,
    scoped `.receipt-sheet`/`.modal-sheet` Telegram theme boundary, JS/template semantic button
    contracts, and `tests/test_visual_identity_browser.py` coverage.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-288/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-288/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-288/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-288/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-288/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
