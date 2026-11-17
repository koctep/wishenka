# Roadmap: WISHENKA-73

## Task Metadata

- **Implementation language**: Python (with JavaScript for Mini App client UI)

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - [/] `ai-tasks/WISHENKA-73/00-roadmap.md` — created roadmap and recorded implementation language
  - [/] `ai-tasks/WISHENKA-73/10-requirements.md` — documented business requirements, user stories, scope, and DoD
- [x] **STEP 2: High-Level Architecture Design**
  - [/] `ai-tasks/WISHENKA-73/20-architecture.md` — documented i18n delivery architecture, module contracts, and Step 3 failing-repro plan
- [x] **STEP 3: Failing Repro Test**
  - [x] `tests/test_miniapp_i18n_repro.py` — automated red repro tests for centralized Mini App i18n delivery and RU/EN rendering across all screens
- [x] **STEP 4: Development**
  - [x] Iteration 1: Added centralized `miniapp.*` RU/EN keys and `miniapp_catalog()` in `wishenka/i18n/catalog.py` and exported it in `wishenka/i18n/__init__.py`
  - [x] Iteration 2: Embedded XSS-safe `<script id="miniapp-i18n" type="application/json">` in `wishenka/web/routes/miniapp.py`
  - [x] Iteration 3: Migrated `wishenka/web/static/miniapp.js` off `HOME_I18N` and hardcoded strings to centralized `t(...)`, `activeLocale()`, `roleLabel()`, and `formatDateTime()`
  - [x] Iteration 4: Updated `tests/test_i18n_unit.py::test_miniapp_js_localizes_home_nav_shell_and_settings_label`, added `test_miniapp_catalog_projection_and_json_xss_escaping`, and verified all repro and unit tests pass
- [x] **STEP 5: Code Cleanup**
  - [/] `ai-tasks/WISHENKA-73/40-code-cleanup.md` — static analysis, formatting, cleanup, and test verification
- [x] **STEP 6: Observability**
  - [/] `ai-tasks/WISHENKA-73/50-observability.md` — observability analysis and logging evaluation
- [x] **STEP 7: Technical Debt Analysis**
  - [/] `ai-tasks/WISHENKA-73/60-tech-debt.md` — documented technical debt, timeout-marker verification, and non-blocking follow-ups
- [x] **STEP 8: Dev Docs**
  - [x] `doc/dev/i18n.md` — documented `miniapp_catalog()`, `<script id="miniapp-i18n" type="application/json">` delivery in `GET /`, `miniapp.js` client helpers (`t()`, `activeLocale()`, `roleLabel()`, `formatDateTime()`), `miniapp_catalog_embedded` debug log, and `tests/test_miniapp_i18n_repro.py`
  - [x] `doc/dev/miniapp.md` — cross-referenced centralized `#miniapp-i18n` delivery and client localization in `GET /` and `static/miniapp.js`
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-73/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-73/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-73/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-73/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-73/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
