# Roadmap: WISHENKA-232

## Task Metadata

- **Implementation language**: Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-232/10-requirements.md`
  - An existing wishlist's notice history must survive applying the data
    upgrade more than once. The second pass completes and leaves that
    history, recorded gift receipts, and archive state unchanged.
    `tests/test_gift_receipt_migration.py::test_upgrade_is_repeatable` is the
    standing check. It currently stops with a storage error on the second
    upgrade.
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-232/20-architecture.md`
  - Name the three key columns on the `notice_receipt_keys` copy in
    `add_notice_uncertain`. Make `add_receipt_delivery_fence` skip tables
    that already exist. A second upgrade from `add_item_order_index` can
    then commit with notice history, receipts, and archive state unchanged.
- [x] **STEP 3: Failing Repro Test**
  - `tests/test_gift_receipt_migration.py::test_upgrade_is_repeatable`
  - Node: `tests/test_gift_receipt_migration.py::test_upgrade_is_repeatable`
  - Command: `td-log run test --task WISHENKA-232 -- make test-serial`
    `PYTEST_ARGS="tests/test_gift_receipt_migration.py::test_upgrade_is_repeatable"`
  - Failure (exit 2): second upgrade stops in `add_notice_uncertain` before the
    history assertions. `sqlite3.OperationalError: table notice_receipt_keys has
    4 columns but 3 values were supplied` on
    `INSERT OR IGNORE INTO notice_receipt_keys SELECT event_type,receipt_id,giver_user_id
    FROM notification_outbox`.
- [x] **STEP 4: Development**
  - [x] Named `event_type`, `receipt_id`, and `giver_user_id` on the
    `notice_receipt_keys` copy in `add_notice_uncertain`, and created both
    fence tables with `CREATE TABLE IF NOT EXISTS` in
    `add_receipt_delivery_fence`. The outbox rebuild and runtime writer are
    unchanged.
    `tests/test_gift_receipt_migration.py` — 4 passed.
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-232/40-code-cleanup.md`
  - Ruff format joined the fence SELECT in
    `tests/test_gift_receipt_migration.py` (100 characters). The two migration
    edits needed no cleanup. `make analyze` passed. Migration tests: 4 passed.
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-232/50-observability.md`
  - No new production logs or metrics. A failed upgrade is already logged as
    `wishlist_migration_failed` with the Alembic/SQL exception. The two
    revision edits do not log.
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-232/60-tech-debt.md`
  - No new debt. The named key insert, `CREATE TABLE IF NOT EXISTS` on both
    fence tables, and the extended `test_upgrade_is_repeatable` match the
    architecture. `pytestmark = pytest.mark.timeout(60)` in
    `tests/test_gift_receipt_migration.py` covers that test. No user-doc
    edit: the revision descriptions are still true.
- [x] **STEP 8: Dev Docs**
  - `doc/dev/migrations.md`
  - `doc/dev/notifications.md`
  - `add_notice_uncertain` copies `notice_receipt_keys` with named columns
    `event_type`, `receipt_id`, and `giver_user_id`, so a later `created_at`
    is not overwritten. Both fence tables use `CREATE TABLE IF NOT EXISTS`,
    so a second upgrade keeps existing fence rows. Standing check:
    `tests/test_gift_receipt_migration.py::test_upgrade_is_repeatable`.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-232/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-232/20-architecture.md`

### STEP 3: Failing Repro

- `tests/test_gift_receipt_migration.py::test_upgrade_is_repeatable`

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-232/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-232/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-232/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
