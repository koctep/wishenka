# Roadmap: WISHENKA-95

## Task Metadata

- **Implementation language**: Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-95/10-requirements.md`
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-95/20-architecture.md`
- [x] **STEP 3: Failing Repro Test**
  - N/A — no behavioral change: this task adds regression coverage for existing policy and redirect behavior; no defect has been established. If coverage exposes a defect, preserve and independently review a deterministic red case before any production fix.
- [x] **STEP 4: Development**
  - [x] Added fixed IPv6 classification matrix for 6to4, Teredo, scoped, and equivalent compressed addresses.
  - [x] Added offline safe multi-hop, blocked later-hop, and circular redirect tests with dispatch assertions.
  - Focused test module: 38 passed; `make analyze` passed. On base commit `42fcae1`, `make test PYTEST_JOBS=4` yielded 13 failed, 1,843 passed, 2 skipped, and 115 browser setup errors; the same command on the task tree yielded 13 failed, 1,855 passed, 2 skipped, and 115 errors. Both runs produced identical failing node IDs, documented with Jira mapping and the missing-Chromium cause in `ai-tasks/WISHENKA-95/41-baseline-test-evidence.md`.
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-95/40-code-cleanup.md`
  - `make analyze` and the 38-test focused suite passed; full-suite baseline evidence is in `41-baseline-test-evidence.md`.
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-95/50-observability.md`
  - Test-only change; existing structured SSRF, fetch and fallback logging reviewed. Focused
    SSRF and logging suites passed (140 tests); no runtime metrics added.
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-95/60-tech-debt.md`
  - Assessed test design, explicit timeout, known baseline failures, and browser setup issue;
    no new unticketed follow-up or blocker identified.
- [x] **STEP 8: Dev Docs**
  - `doc/dev/items.md`: documented offline IPv6 and redirect regression coverage, focused test
    command, and troubleshooting for address classifications and browser prerequisites.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-95/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-95/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-95/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-95/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-95/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
