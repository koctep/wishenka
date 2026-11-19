# Roadmap: WISHENKA-177

## Task Metadata

- **Implementation language**: Python 3.12+

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - [x] `ai-tasks/WISHENKA-177/10-requirements.md` — business requirements, acceptance criteria, scope, entities, and scenarios documented
  - [x] Implementation language determined: Python 3.12+
- [x] **STEP 2: High-Level Architecture Design**
  - [x] `ai-tasks/WISHENKA-177/20-architecture.md` — research, E2E test architecture, component boundaries, interfaces, and implementation plan
- [x] **STEP 3: Failing Repro Test**
  - [x] `N/A — no behavioral change` (test-only task verifying existing contract; see `20-architecture.md`)
- [x] **STEP 4: Development**
  - [x] Implemented `tests/test_bot_menu_miniapp_e2e_browser.py` (12 E2E browser tests covering `create`, `collection`, and `home` bot menu transitions in `en`/`ru`, no implicit wishlist creation, and invalid `startapp` safe recovery without data leakage)
  - [x] Verified `tests/test_bot_menu_miniapp_e2e_browser.py` (12 passed) and full-repo `ruff` / `mypy` checks (0 issues)
- [x] **STEP 5: Code Cleanup**
  - [x] `ai-tasks/WISHENKA-177/40-code-cleanup.md` — static analysis (`make analyze`: `ruff check`, `ruff format --check`, `mypy`), line-length/cleanup check, and targeted E2E browser test run (12 passed)
- [x] **STEP 6: Observability**
  - [x] `ai-tasks/WISHENKA-177/50-observability.md` — `N/A — test-only task` (only `tests/test_bot_menu_miniapp_e2e_browser.py` added; no production code changes)
- [x] **STEP 7: Technical Debt Analysis**
  - [x] `ai-tasks/WISHENKA-177/60-tech-debt.md` — technical debt analysis (shortcuts, `tests/browser_helpers.py` helper consolidation note, `initDataUnsafe.start_param` / `collection` coverage gaps, and script timeout note)
- [x] **STEP 8: Dev Docs**
  - [x] `doc/dev/bot-scenarios.md` — added `tests/test_bot_menu_miniapp_e2e_browser.py` verification command and E2E bot-menu-to-Mini-App coverage description
  - [x] `doc/dev/testing.md` — added `WISHENKA-177` subsection documenting `tests/test_bot_menu_miniapp_e2e_browser.py` (12 parametrized browser E2E tests and run command)
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-177/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-177/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-177/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-177/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-177/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
