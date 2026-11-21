# Roadmap: WISHENKA-114

## Task Metadata

- **Implementation language**: Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-114/10-requirements.md`
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-114/20-architecture.md`
- [x] **STEP 3: Failing Repro Test**
  - `tests/test_preview_supported_routes.py` — offline security and ownership repros.
- [x] **STEP 4: Development**
  - [x] Added explicit route snapshots, controlled replay/direct/deny factories, isolated clients,
    fail-closed opaque-client handling, and route-partitioned cache.
  - [x] Migrated application lifespan to owned safe route; added fixture-only cassette conversion.
  - [x] Migrated cassette replay and legacy preview tests to explicit routes or stream checks.
  - [x] Removed synthetic DNS-cache writes from cassette replay and recording; added regressions.
  - [x] Restored cassette-miss errors and implemented offline verification without network DNS.
  - [x] Completed focused checks and passed the independent Step 4 review.
  - Full suite timed out and remains unverified; follow-up is recorded in `60-tech-debt.md`.
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-114/40-code-cleanup.md`
  - `make analyze` passed; 90 focused route, resource-reuse, and cassette tests passed.
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-114/50-observability.md`
  - Added structured route-rejection diagnostics without URL, headers, or credentials.
  - Focused preview-route and observability suite: 23 passed; Ruff and diff-check passed.
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-114/60-tech-debt.md`
- [x] **STEP 8: Dev Docs**
  - `doc/dev/items.md` — supported routes, lifecycle, offline replay, and upgrade guidance.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-114/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-114/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-114/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-114/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-114/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
