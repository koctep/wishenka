# Roadmap: WISHENKA-338

## Task Metadata

- **Implementation language**: Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-338/10-requirements.md`
  - Opening one wishlist, its members, its wishes, its gifted wishes, or
    its favorite mark still takes the exclusive lock a save takes. The lock
    is not already free. Looking does not itself save the wishlist.
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-338/20-architecture.md`
  - The seven one-wishlist openings use the existing read-only transaction
    (`BEGIN` plus `query_only`). Saves, and any request that also writes,
    keep `BEGIN IMMEDIATE` on the shared repository path.
- [x] **STEP 3: Failing Repro Test**
  - `tests/test_wishenka_338_read_openings_repro.py`
  - The seven openings and the pure-read GETs still block on `BEGIN IMMEDIATE`
    while a save holds the lock. A save still does not finish within 2 seconds.
- [x] **STEP 4: Development**
  - [x] One-wishlist openings and pure-read HTTP GETs use `read_transaction` (`BEGIN` plus `query_only`). Saves and write requests stay on `BEGIN IMMEDIATE`.
  - [x] Session lookup on the wishlist engine uses that same read transaction, so a pure-read GET does not take the save lock.
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-338/40-code-cleanup.md`
  - `make analyze` passed. No format, lint, or type edits. Production code
    was left unchanged, so the repro was not re-run.
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-338/50-observability.md`
  - No new log or metric. A successful one-wishlist read stays quiet. A
    failed read keeps the existing error. Busy and `query_only` reset
    failures already log inside `read_transaction`.
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-338/60-tech-debt.md`
  - One-wishlist openings use a read-only transaction. Saves and mixed
    requests through `get_wishlist_repository` still use `BEGIN IMMEDIATE`.
    `UserStore._read` was not changed. The repro keeps
    `pytestmark = pytest.mark.timeout(30)`. No new follow-up.
  - User documentation under `doc/` was left unchanged. Developer docs stay
    on Step 8.
- [x] **STEP 8: Dev Docs**
  - `doc/dev/wishlists.md`, `doc/dev/architecture.md`, `doc/dev/items.md`,
    `doc/dev/gift-receipt.md`, `doc/dev/auth.md`, `doc/dev/bot-support.md`
  - One-wishlist openings and the pure-read GETs that show them use
    `read_transaction` (`BEGIN` plus `query_only`) and do not take the save
    lock. A save and a request that also writes stay on `BEGIN IMMEDIATE`.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-338/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-338/20-architecture.md`

### STEP 3: Failing Repro

- `tests/test_wishenka_338_read_openings_repro.py`

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-338/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-338/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-338/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/wishlists.md`
- `doc/dev/architecture.md`
- `doc/dev/items.md`
- `doc/dev/gift-receipt.md`
- `doc/dev/auth.md`
- `doc/dev/bot-support.md`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
