# Roadmap: WISHENKA-2

## Task Metadata

- **Implementation language**: Python (FastAPI + aiogram v3 + Jinja2 + HTMX)

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - [x] Document business requirements for system architecture and domain models: `ai-tasks/WISHENKA-2/10-requirements.md`
- [x] **STEP 2: High-Level Architecture Design**
  - [x] Interactive architecture design session (grill-me)
  - [x] Document high-level system architecture and data schema: `ai-tasks/WISHENKA-2/20-architecture.md`
- [x] **STEP 3: Failing Repro Test**
  - [x] N/A — no behavioral change (architectural specification and schema design task)
- [x] **STEP 4: Development**
  - [x] Documented architectural agreements, stack selection, and database schema in `20-architecture.md` (specification-only deliverable)
- [x] **STEP 5: Code Cleanup**
  - [x] Created `ai-tasks/WISHENKA-2/40-code-cleanup.md`, verified markdown formatting and removed temporary stubs
- [x] **STEP 6: Observability**
  - [x] Created `ai-tasks/WISHENKA-2/50-observability.md` documenting logging levels and Transactional Outbox monitoring
- [x] **STEP 7: Technical Debt Analysis**
  - [x] Created `ai-tasks/WISHENKA-2/60-tech-debt.md` confirming zero debt and tracking follow-up Jira stories
- [x] **STEP 8: Dev Docs**
  - [x] Created developer documentation: `doc/dev/architecture.md`
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-2/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-2/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-2/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-2/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-2/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
