# Roadmap: WISHENKA-335

## Task Metadata

- **Implementation language**: Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-335/10-requirements.md`
  - One shared way to bring a database to the latest change in its own
    history. Wishlist startup and person startup both use that way today
    through the wishlist-owned path. There is one history, not a second
    private copy. Behavior of applying changes stays. The person-key
    change and its rollback check stay as they are.
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-335/20-architecture.md`
  - Shared apply procedure moves to `wishenka.db.migrations`. Wishlist
    and person startup both call `upgrade_to_head` there. The wishlist
    Alembic tree, legacy adoption, and the person-key revision stay in
    `wishenka.wishlists`. The WISHENKA-334 test file is not edited.
- [x] **STEP 3: Failing Repro Test**
  - `tests/test_wishenka_335_shared_migration_runner.py`
  - Wishlist and person startup must call
    `wishenka.db.migrations.upgrade_to_head`. The shared module is
    absent, so the check is red.
- [x] **STEP 4: Development**
  - [x] Moved the apply sequence into `wishenka.db.migrations`. Wishlist
    startup and person startup call `upgrade_to_head` there. The wishlist
    module keeps the product history and compatibility wrappers.
    `tests/test_wishenka_335_shared_migration_runner.py` is green.
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-335/40-code-cleanup.md`
  - `make analyze` passed. No format, lint, or type edits in the task diff.
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-335/50-observability.md`
  - No new log or metric. Start, failure, and completion stay on
    `wishenka.wishlists.migrations` with the same events. A successful
    apply still logs one completion record. Adoption stays in the
    wishlist history.
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-335/60-tech-debt.md`
  - No new follow-up.
    `tests/test_wishenka_335_shared_migration_runner.py` has
    `pytestmark = pytest.mark.timeout(10)`. Compatibility wrappers stay
    because the architecture required them.
- [x] **STEP 8: Dev Docs**
  - `doc/dev/migrations.md`
  - `doc/dev/architecture.md`
  - The shared apply procedure is documented in `wishenka.db.migrations`.
    Wishlist and person startup call it. The wishlist history stays in
    `wishenka.wishlists`.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-335/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-335/20-architecture.md`

### STEP 3: Failing Repro

- `tests/test_wishenka_335_shared_migration_runner.py`

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-335/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-335/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-335/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/migrations.md`
- `doc/dev/architecture.md`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
