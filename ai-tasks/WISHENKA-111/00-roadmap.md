# Roadmap: WISHENKA-111

## Task Metadata

- **Implementation language**: Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-111/10-requirements.md` — business requirements documented.
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-111/20-architecture.md` — migration architecture and test plan.
- [x] **STEP 3: Failing Repro Test**
  - `tests/test_wishlist_alembic_migrations.py` — red legacy upgrade-path repro.
- [x] **STEP 4: Development**
  - [x] Added versioned Alembic baseline and ordered SQLite revisions for the two legacy fields and ordering index.
  - [x] Replaced runtime schema mutation with migration startup and safe recognized-schema adoption.
  - [x] Made the legacy upgrade-path repro pass while preserving its seeded wishlist row.
  - [x] Validated legacy schemas against the complete baseline structural contract before stamping.
  - [x] Covered fresh-file and isolated in-memory startup at the Alembic head revision.
  - [x] Enforced index ordering during legacy adoption and added owned cleanup for memory-store files.
  - [x] Routed application shutdown through `WishlistStore.dispose()` and covered in-memory lifespan cleanup.
  - [x] Validated exact historical marker signatures before selecting a legacy revision.
  - [x] Asserted public startup rejects an ascending legacy history index without stamping it.
  - [x] Removed duplicate malformed-marker startup assertion while retaining rejection coverage.
  - [x] Moved persistent WAL selection to migration startup so concurrent pooled connections do not contend for a mode-change lock.
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-111/40-code-cleanup.md` — static analysis passed; full suite awaiting runner triage after an extended active pytest process.
  - [x] Reconciled the full-suite result against baseline and WISHENKA-124; reran analysis and seven focused migration/concurrency tests.
- [x] **STEP 6: Observability**
  - `wishenka/wishlists/migrations.py` — structured migration lifecycle logs with duration.
  - `ai-tasks/WISHENKA-111/50-observability.md` — observability scope and validation record.
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-111/60-tech-debt.md` — debt analysis written; awaiting gate.
- [x] **STEP 8: Dev Docs**
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-111/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-111/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-111/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-111/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-111/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
