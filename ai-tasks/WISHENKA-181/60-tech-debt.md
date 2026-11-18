# WISHENKA-181: Technical Debt Analysis

## Shortcuts Taken

1. **Migration backfill fallback for orphaned `notice_receipt_keys` (`wishenka/wishlists/alembic/versions/add_notice_retention_columns.py`)**:
   When backfilling `notice_receipt_keys.created_at`, rows whose corresponding `notification_outbox` row was already purged fall back to `CAST(strftime('%s', 'now') AS INTEGER)`, resetting their retention window to the migration timestamp rather than joining `wl_receipts.created_at`.
2. **Unbatched retention `DELETE` statements (`wishenka/notices/store.py`)**:
   Both `NoticeStore.purge_finished` and `NoticeStore.purge_retention_records` delete all matching expired rows in a single `BEGIN IMMEDIATE` transaction without a `LIMIT`/batch loop. This is simple and deterministic for current SQLite volumes, but assumes expired-row bursts remain small enough not to stall concurrent writers.
3. **Private-chat `chat_id == user_id` assumption in `deactivate_bot_destination` (`wishenka/notices/store.py`)**:
   `NoticeStore.settle` passes `claim.giver_user_id` as the `chat_id` argument to `deactivate_bot_destination(conn, claim.giver_user_id, now)`. This matches the current 1:1 private-chat model where `bot_destinations.chat_id` equals `user_id`, but would break if non-private chat destinations were ever introduced.

## Code Quality Issues

1. **Combined `try/except` in `_purge_notices` (`wishenka/wishlists/cleanup.py`)**:
   `_purge_notices` wraps both `notice_store.purge_finished(...)` and `notice_store.purge_retention_records(...)` in one `try ... except Exception` block. Because each method commits its own `self._store.transaction(work)`, if `purge_finished` succeeds and `purge_retention_records` fails, `receipt_notice_rows_purged` is not logged for the already-committed outbox purge.
2. **Raw `sqlite3` / `time.time()` vs injected clock in `wishenka/bot/birthdays.py`**:
   While `birthday:d:` deletion uses `_now_epoch(dependencies)` (which respects `dependencies.now` when provided), the adjacent `birthday_input` expiry (`int(time.time()) + 3600` on line 212) still calls `time.time()` directly rather than `_now_epoch(dependencies)`.

## Missing Tests

1. **All new test files satisfy `do-testing` timeout rules**:
   Verified explicit module-level markers in `tests/test_wishenka_181_repro.py` (`pytestmark = pytest.mark.timeout(30)`), `tests/test_notice_retention.py` (`pytestmark = pytest.mark.timeout(60)`), and `tests/test_wishenka_181_observability.py` (`pytestmark = pytest.mark.timeout(30)`).
2. **`deleted_at IS NULL` fallback path in `purge_retention_records`**:
   The SQL predicate `(deleted_at IS NULL OR deleted_at <= :birthday_cutoff)` in `NoticeStore.purge_retention_records` is verified indirectly via migration backfill, but there is no dedicated unit test inserting a legacy `deleted=1, deleted_at=NULL` row directly and asserting it is purged.
3. **Partial failure between `purge_finished` and `purge_retention_records`**:
   `tests/test_wishenka_181_observability.py` tests `purge_finished` raising, but does not cover the case where `purge_finished` commits rows and `purge_retention_records` subsequently raises.

## Performance Concerns

1. **Missing lookup indexes for `NOT EXISTS` subqueries in `NoticeStore.purge_retention_records` (`wishenka/notices/store.py`, `wishenka/wishlists/alembic/versions/add_notice_retention_columns.py`)**:
   - `birthday_entries` purge checks `NOT EXISTS (SELECT 1 FROM reminder_outbox r WHERE r.birthday_id = birthday_entries.id AND r.status IN ('pending', 'sending', 'uncertain'))`, while `reminder_outbox` only has `idx_reminders_due(status, next_attempt_at)` (no index on `birthday_id`).
   - `notice_receipt_keys` purge checks `NOT EXISTS (SELECT 1 FROM notification_outbox o WHERE o.event_type = notice_receipt_keys.event_type AND o.receipt_id = notice_receipt_keys.receipt_id AND o.giver_user_id = notice_receipt_keys.giver_user_id)`, while `notification_outbox` only has `idx_notice_outbox_due(status, next_attempt_at)`.
   Under large outbox backlogs, each cleanup cycle will perform repeated scans of `reminder_outbox` / `notification_outbox` for candidate expired rows.
2. **SQLite write-lock duration on large purge batches**:
   Without batched `DELETE`s (e.g., `DELETE ... WHERE id IN (SELECT id ... LIMIT 500)`), a large backlog of expired rows after a long outage or retention-window reduction will hold the SQLite write lock for the entire delete transaction.

## Follow-up Tasks

- **Add covering indexes and batched deletes for notice retention purges** (`NON-BLOCKER`, Jira: [WISHENKA-223](https://pypost.atlassian.net/browse/WISHENKA-223)):
  Add Alembic indexes on `reminder_outbox(birthday_id, status)` and `notification_outbox(event_type, receipt_id, giver_user_id)`, and optionally batch `purge_finished` / `purge_retention_records` deletes if outbox volume grows.
- **Split `_purge_notices` error handling in `wishenka/wishlists/cleanup.py`** (`NON-BLOCKER`, Jira: [WISHENKA-224](https://pypost.atlassian.net/browse/WISHENKA-224)):
  Isolate `purge_finished` and `purge_retention_records` `try/except` blocks so `receipt_notice_rows_purged` is still logged if `purge_finished` succeeds before `purge_retention_records` fails, and add a unit test for the partial-failure and `deleted_at IS NULL` cases.
