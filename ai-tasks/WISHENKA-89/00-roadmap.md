# Roadmap: WISHENKA-89

## Task Metadata

- **Implementation language**: Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-89/10-requirements.md`
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-89/20-architecture.md`
- [x] **STEP 3: Failing Repro Test**
  - `tests/test_ssr_i18n_repro.py`
- [x] **STEP 4: Development**
  - [x] Added `wishenka/i18n/formatters.py` (`format_date` exported from `wishenka.i18n` and registered as Jinja2 filter/global in `wishenka/web/templates.py`).
  - [x] Added `web.*` translation keys in `wishenka/i18n/catalog.py` with full RU/EN key and placeholder parity.
  - [x] Wired `LocaleDep` and localized strings/date formatting across `wishenka/web/gifted_view.py`, `wishenka/web/routes/sharing.py`, `wishenka/web/routes/items_ui.py`, `wishenka/web/routes/receipts_ui.py`, and `wishenka/web/routes/reservations_ui.py`.
  - [x] Localized `base.html`, `wishlist_detail.html`, `share_wishlist.html`, `invite_preview.html`, `reservations_cabinet.html`, all 13 SSR partials, and `receipt.js`/`wishlist.js` via DOM `data-i18n-*` attributes (leaving `miniapp.js` untouched).
  - [x] Verified `tests/test_ssr_i18n_repro.py` (7/7), `tests/test_i18n_unit.py` (37/37), `make analyze` (Ruff + Mypy), and full 1105-test suite (651 + 454 passed).
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-89/40-code-cleanup.md`
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-89/50-observability.md`
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-89/60-tech-debt.md`
- [x] **STEP 8: Dev Docs**
  - `ai-tasks/WISHENKA-89/70-dev-docs.md`
  - `doc/dev/i18n.md`
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-89/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-89/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-89/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-89/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-89/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
