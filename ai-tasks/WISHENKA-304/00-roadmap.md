# Roadmap: WISHENKA-304

## Task Metadata

- **Implementation language**: Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - [/] `ai-tasks/WISHENKA-304/10-requirements.md`: equal view times follow the recording
    sequence (list position or a counter), not entry identity; session and stored history;
    frozen-time regression.
  - [/] Implementation language determined (Python) and recorded above.
  - [ ] Acceptance gate review.
- [x] **STEP 2: High-Level Architecture Design**
  - [/] `ai-tasks/WISHENKA-304/20-architecture.md`: tie-break is a monotonic
    `recorded_seq` (not row id, not list position). Same key on the in-memory
    sorts and on the SQLite `ORDER BY` plus `LIMIT`.
- [x] **STEP 3: Failing Repro Test**
  - [/] `tests/test_wishenka_304_history_order_repro.py`: frozen view time; newest
    recording first when times match, on session and stored history, including
    the rows that stay inside the existing limit.
- [x] **STEP 4: Development**
  - [x] Added `recorded_seq` on the history entry and row, and reversible Alembic
    revision `add_view_history_recorded_seq` (backfill from `id`, counter
    `view_history_seq`, index on `viewed_at` then `recorded_seq`).
  - [x] `WishlistService` advances the sequence on every record, including a
    repeat, and sorts and prunes with `(viewed_at, recorded_seq)`.
  - [x] `WishlistRepository` allocates `view_history_seq` on insert and repeat,
    and lists with `ORDER BY viewed_at DESC, recorded_seq DESC` before `LIMIT`.
  - [x] `WishlistStore` loads and flushes `recorded_seq` and `view_history_seq`.
  - [x] Seed `view_history_seq` with `INSERT ... VALUES` and a scalar subquery.
    `INSERT ... SELECT ... ON CONFLICT` is a syntax error on this SQLite.
- [x] **STEP 5: Code Cleanup**
  - [/] `ai-tasks/WISHENKA-304/40-code-cleanup.md`
- [x] **STEP 6: Observability**
  - [/] `ai-tasks/WISHENKA-304/50-observability.md`: record and list stay on
    `view_history_recorded` and `view_history_listed`. Fields are ids and a
    count. `recorded_seq` is the order key and is not a title. No new log line.
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-304/60-tech-debt.md`: WISHENKA-292 item 2 is
    addressed. Equal view times follow `recorded_seq`, newest recording
    first, including a repeat that keeps the row id, in memory and in
    SQLite before `LIMIT`. The id copy is a one-time migration fill.
    No new follow-up. The repro timeout marker was already present.
    The full suite was not finished. Pre-existing failures were not
    re-filed. `doc/` was not changed.
- [x] **STEP 8: Dev Docs**
  - [/] `doc/dev/wishlists.md`: equal view times follow `recorded_seq`, newest
    recording first, in memory and in SQLite before the limit. A repeat keeps
    the row id and takes a new sequence. The id fill is one-time. Record and
    list logs stay ids and a count, not titles, not the middleware line, and
    not the commit.
  - [/] `doc/dev/testing.md`: `tests/test_wishenka_304_history_order_repro.py`.
  - [/] `doc/dev/migrations.md`: head is `add_view_history_recorded_seq`.
  - [/] `doc/dev/miniapp.md`: the history screen follows that server order.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-304/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-304/20-architecture.md`

### STEP 3: Failing Repro

- `tests/test_wishenka_304_history_order_repro.py`

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-304/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-304/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-304/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
