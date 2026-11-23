# Roadmap: WISHENKA-307

## Task Metadata

- **Implementation language**: Python, JavaScript, HTML, CSS

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - [x] `ai-tasks/WISHENKA-307/10-requirements.md`: switches on the personal settings page do
    not follow the Wishenka design (defect of WISHENKA-291); required look and behavior of
    on/off switches in all states, accessibility, themes, languages, unchanged save behavior.
  - [x] Implementation language determined (Python, JavaScript, HTML, CSS) and recorded above.
  - [x] Ticket screenshot unavailable to the executing agent; assumption recorded in Q&A.
  - [x] Acceptance gate review (independent review PASS).
- [x] **STEP 2: High-Level Architecture Design**
- [x] **STEP 3: Failing Repro Test**
  - [x] Bug repro: red automated test `tests/test_settings_switch_browser.py` (23 red, 10 green
    guards/control on unchanged production code); evidence in
    `ai-tasks/WISHENKA-307/30-failing-repro.md`.
  - [x] Independent review of the repro (PASS after one fix round).
- [x] **STEP 4: Development**
  - [x] Switch skin in `miniapp.css`, switch roles and ids in `settings.html`, `aria-busy` in
    `settings.js`; 33 of 33 tests in `tests/test_settings_switch_browser.py` pass.
- [x] **STEP 5: Code Cleanup**
- [x] **STEP 6: Observability**
- [x] **STEP 7: Technical Debt Analysis**
- [x] **STEP 8: Dev Docs**
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-307/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-307/20-architecture.md`

### STEP 3: Failing Repro

- `tests/test_settings_switch_browser.py`
- `ai-tasks/WISHENKA-307/30-failing-repro.md`

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-307/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-307/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-307/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
