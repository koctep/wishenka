# WISHENKA-232: Code Cleanup Report

## Linter Fixes

Describe fixed linter errors and warnings:

- Fixed: none. Ruff and Mypy reported no issues in the two migration edits
  or the test extension. `make analyze` passed for the repository
  (306 source files).

## Code Formatting

Applied formatting changes:

- [x] Automatic code formatting
- [ ] Indentation and alignment fixes
- [x] Line length correction

Ruff format joined the fence snapshot query in
`tests/test_gift_receipt_migration.py` onto one line of 100 characters.
`add_notice_uncertain.py` and `add_receipt_delivery_fence.py` were already
formatted. Indentation in the new lines was already correct, so no alignment
edit was applied.

## Code Cleanup

Cleanup actions performed:

- Removed unused imports: 0
- Removed unused variables: 0
- Removed commented-out code: none in the task diff
- Removed debug prints: none in the task diff

The named `notice_receipt_keys` columns and both `CREATE TABLE IF NOT EXISTS`
statements stay as written. The module marker
`pytestmark = pytest.mark.timeout(60)` covers `test_upgrade_is_repeatable`.

## Validation Results

Validation results:

- [x] All tests passed
- [x] All tests have explicit timeout markers
- [x] No merge conflicts
- [x] Syntax is valid
- [x] Types are correct (if applicable)

Command:

```sh
td-log run test --task WISHENKA-232 -- make test-serial \
  PYTEST_ARGS="tests/test_gift_receipt_migration.py"
```

Result: 4 passed in `tests/test_gift_receipt_migration.py`.

- `test_revisions_backfill_and_normalise`
- `test_upgrade_is_repeatable`
- `test_receipt_table_has_no_giver_column_and_downgrade_is_irreversible`
- `test_cascade_on_purge_and_soft_delete_keeps_rows`

`git diff --check` on the three task files passed. No conflict markers.

## Notes

Cleanup stayed inside the task diff: the column list on the
`notice_receipt_keys` copy, `IF NOT EXISTS` on the two fence tables, and the
repeatable-upgrade snapshot in `tests/test_gift_receipt_migration.py`.
The outbox rebuild, downgrades, and the runtime writer were left unchanged.
