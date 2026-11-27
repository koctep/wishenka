# WISHENKA-232: Technical Debt Analysis

No new technical debt. The second upgrade now finishes, and the notice
history this task owns stays as it was after the first pass.

The change is the two statements named in the architecture, plus the
standing check that already lived in `tests/test_gift_receipt_migration.py`.
`add_notice_uncertain` names `event_type`, `receipt_id`, and
`giver_user_id` on the `notice_receipt_keys` copy. `created_at` stays on
`add_notice_retention_columns`, which still backfills only
`WHERE created_at = 0`. `add_receipt_delivery_fence` creates
`receipt_delivery_fence` and `receipt_delivery_fence_audit` with
`CREATE TABLE IF NOT EXISTS` and does not drop or rewrite rows on the way
up. `downgrade()` still drops both tables.

There is no `do-testing` blocker. `tests/test_gift_receipt_migration.py`
sets `pytestmark = pytest.mark.timeout(60)` at module scope. That mark
covers `test_upgrade_is_repeatable` and the other three tests in the file.
No test in that module overrides it.

Reviewed: `wishenka/wishlists/alembic/versions/add_notice_uncertain.py`,
`wishenka/wishlists/alembic/versions/add_receipt_delivery_fence.py`,
`wishenka/wishlists/alembic/versions/add_notice_retention_columns.py`,
`tests/test_gift_receipt_migration.py`, `10-requirements.md`,
`20-architecture.md`, `40-code-cleanup.md`, and `50-observability.md`.

Developer docs in `doc/dev/notifications.md` and `doc/dev/migrations.md`
still describe what these revisions produce: an uncertain outbox, receipt
keys filled from that outbox, and the two fence tables. They do not claim
an unnamed insert or a bare `CREATE TABLE`. Nothing written there is now
false, so this step does not edit them.

## Shortcuts Taken

None that need a follow-up. The two SQL edits are the design, not a
temporary bypass.

- **The outbox rebuild stays** (accepted). `add_notice_uncertain` still
  rebuilds `notification_outbox`, omits `claim_token` on the copy, and sets
  `requires_membership = 1` on every copied row. The architecture left that
  rebuild in place. Claim selection is still `pending` only, so an
  `uncertain` row is not an automatic retry. The standing check asserts
  `status`, not `claim_token`.
- **Fence tables are skipped when they already exist** (accepted).
  `CREATE TABLE IF NOT EXISTS` does not alter a table that is already
  there. No later revision changes these two tables. Existing
  `in_flight` and `uncertain` fence rows stay. The audit table is not
  rewritten.
- **The birthday replay join stays out** (accepted, pre-existing).
  `unify_user_keys_and_cascades` can drop birthday rows on a later replay
  because `owner_id` already holds `telegram_id`. The legacy fixture has
  no birthday rows, and birthday rows are not the history this task keeps.
  That revision is not edited here.

## Code Quality Issues

None that need a follow-up.

The named column list matches the three columns this revision creates.
`INSERT OR IGNORE` is unchanged. Both fence statements use the same
`CREATE TABLE IF NOT EXISTS` pattern already used for
`notice_receipt_keys`. The test seeds one receipt, one uncertain outbox
row, one key with `created_at` `1700000000`, and one `uncertain` fence,
which is the fixture the architecture specified. Giver `501` and that
timestamp are fixture values, not production constants.

## Missing Tests

No blocker. The module timeout above covers `test_upgrade_is_repeatable`.

That test, after the second `upgrade_to_head_sync`, compares receipt rows,
archive flags, the key row including `created_at`, the outbox association
and `status`, and the fence triple (`wish_item_id`, `user_id`, `state`).
The first-upgrade check in the same file still covers approximate receipts
and archive normalisation.

`receipt_delivery_fence_audit` is not seeded. The revision does not delete
or update that table when it already exists, and this task's history is
the fence row, not an audit row. A downgrade of the fence revision is
unchanged and is not part of this check.

## Performance Concerns

None added. The key copy is still one `INSERT OR IGNORE` of the outbox
keys. Each fence statement is one create that SQLite skips when the table
is present. A repeated upgrade still walks the wishlist history inside the
existing Alembic transaction. That walk is unchanged.

## Follow-up Tasks

No new follow-up. Nothing in this change needs a Debt issue.

This task's tests did not expose a new failing node. Pre-existing suite
failures are not listed here.
