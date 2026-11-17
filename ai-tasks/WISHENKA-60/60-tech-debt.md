# WISHENKA-60: Technical Debt Analysis

## Shortcuts Taken

- **Reusing `reminder_outbox.next_attempt_at` as the settlement timestamp for retention cleanup:**
  To avoid an Alembic schema migration in `WISHENKA-60`, `claim_reminder` in
  [`wishenka/notices/reminders.py`](../../wishenka/notices/reminders.py) and `NoticeWorker.run_once`
  in [`wishenka/notices/worker.py`](../../wishenka/notices/worker.py) stamp
  `next_attempt_at = now` on terminal transitions (`sent`, `skipped`, `failed`), and
  `NoticeStore.purge_finished` in [`wishenka/notices/store.py`](../../wishenka/notices/store.py)
  deletes terminal `reminder_outbox` rows using `next_attempt_at <= :threshold_epoch`. Unlike
  `notification_outbox`, which has an explicit `updated_at` column, `reminder_outbox` relies on
  overloading `next_attempt_at` for both scheduling and retention age.
- **Routes calling private `WishlistService._record_shared_event` directly:**
  In [`wishenka/web/routes/wishlists.py`](../../wishenka/web/routes/wishlists.py),
  `update_wishlist` (`PATCH /api/wishlists/{wishlist_id}`) and `set_role`
  (`PATCH /api/wishlists/{wishlist_id}/members/{user_id}/role`) mutate `Wishlist` / `WishlistMember`
  fields in the HTTP route handler and call `service._record_shared_event(...)` directly instead of
  delegating the domain mutation to public `WishlistService` methods.
- **Persistent receipt deduplication keys and account-deletion scope:**
  `notice_receipt_keys` retains deduplication keys after `NoticeStore.purge_finished` deletes
  terminal `notification_outbox` rows, and notification/outbox tables (`notification_outbox`,
  `notice_receipt_keys`, `reminder_outbox`, `bot_destinations`, `notice_rate_slots`) still require
  full account-deletion/anonymization integration. Both are already tracked under
  [WISHENKA-181](https://pypost.atlassian.net/browse/WISHENKA-181) and
  [WISHENKA-35](https://pypost.atlassian.net/browse/WISHENKA-35).

## Code Quality Issues

- **Duplicated live-eligibility SQL across `claim_reminder` and `refresh_reminder`:**
  In [`wishenka/notices/reminders.py`](../../wishenka/notices/reminders.py), both `claim_reminder`
  and `refresh_reminder` embed nearly identical multi-join SQL queries to verify wishlist status,
  membership, open-reservation eligibility for
  `('list_archived', 'list_restored', 'list_updated')`, and recipient exclusion
  (`(ri.recipient_user_id IS NULL OR ri.recipient_user_id<>:user) AND (l.is_collaborative=1 OR l.owner_id<>:user)`).
  Future changes to shared-event authorization must keep both queries synchronized until extracted
  into a shared query helper.
- **Private store and service attribute coupling:**
  `NoticeWorker.run_once` in [`wishenka/notices/worker.py`](../../wishenka/notices/worker.py)
  continues to pass `self._store._store` to `claim_reminder`, `refresh_reminder`, and
  `settle_reminder` (already tracked in
  [WISHENKA-180](https://pypost.atlassian.net/browse/WISHENKA-180)). Similarly,
  `WishlistStore._flush_receipt_effects` in
  [`wishenka/wishlists/store.py`](../../wishenka/wishlists/store.py) reads and clears
  `service._flushed_shared_events` to pass post-commit log counts out of `_execute_once` and
  `execute_wish`.

## Missing Tests

- **Per-test timeout marker audit (`do-testing`):**
  Audited across the entire repository via
  `.venv/bin/pytest --collect-only -q -m "not timeout" -p no:cacheprovider -n 0`: **1009 collected
  tests, 1009 deselected, 0 tests missing explicit `pytest.mark.timeout` markers** (no BLOCKER).
  Both `tests/test_wishenka_60_repro.py` (5 test items) and
  `tests/test_wishenka_60_observability.py` (4 test items) declare
  `pytestmark = pytest.mark.timeout(60)` at module scope. No pre-existing test failures were
  encountered.
- **Real Telegram Bot API smoke test and multi-process worker race:**
  `WISHENKA-60` tests use `FakeNoticeSender` and single-process `NoticeWorker.run_once` calls.
  Opt-in real Telegram API smoke testing and two-process worker contention coverage are already
  tracked under [WISHENKA-156](https://pypost.atlassian.net/browse/WISHENKA-156).

## Performance Concerns

- **Unbounded single-transaction `DELETE` in `NoticeStore.purge_finished`:**
  In [`wishenka/notices/store.py`](../../wishenka/notices/store.py), `NoticeStore.purge_finished`
  executes unbatched `DELETE FROM notification_outbox ...` and `DELETE FROM reminder_outbox ...`
  statements inside a single `BEGIN IMMEDIATE` write transaction. Under a large historical backlog
  (for example, after prolonged worker downtime or retention-window changes), deleting many rows in
  one transaction can hold the SQLite writer lock longer than necessary; batching deletes with a
  bounded `LIMIT` per pass would keep lock duration predictable.
- **Correlated `EXISTS` subqueries on `wl_reservations` in `claim_reminder` and `refresh_reminder`:**
  Evaluating open-reservation eligibility for `list_archived`, `list_restored`, and `list_updated`
  joins `wl_reservations` to `wl_items` per candidate row in `reminder_outbox`. Current test
  workloads are fast, but production query latency should be monitored as wishlist and reservation
  volumes grow.

## Follow-up Tasks

1. **NON-BLOCKER, Medium:** Extract the duplicated live-eligibility SQL in `claim_reminder` and
   `refresh_reminder` ([`wishenka/notices/reminders.py`](../../wishenka/notices/reminders.py)) into
   a shared helper, and move `update_wishlist` / `set_role` domain mutations from
   [`wishenka/web/routes/wishlists.py`](../../wishenka/web/routes/wishlists.py) into public
   `WishlistService` methods so HTTP routes no longer call `service._record_shared_event` directly.
   Jira: [WISHENKA-184](https://pypost.atlassian.net/browse/WISHENKA-184).
2. **NON-BLOCKER, Low:** Batch `NoticeStore.purge_finished` deletions in
   [`wishenka/notices/store.py`](../../wishenka/notices/store.py) with a bounded `LIMIT` per pass
   (and evaluate adding a dedicated `updated_at` column to `reminder_outbox` if retention semantics
   diverge from `next_attempt_at`).
   Jira: [WISHENKA-183](https://pypost.atlassian.net/browse/WISHENKA-183).
3. **NON-BLOCKER, High:** Include `notification_outbox`, `notice_receipt_keys`,
   `reminder_outbox`, `bot_destinations`, and `notice_rate_slots` in account deletion /
   anonymization. Existing scope:
   [WISHENKA-35](https://pypost.atlassian.net/browse/WISHENKA-35).
4. **NON-BLOCKER, High:** Define bounded retention for `notice_receipt_keys` and related
   notification/birthday data while preserving idempotence. Existing scope:
   [WISHENKA-181](https://pypost.atlassian.net/browse/WISHENKA-181).
5. **NON-BLOCKER, Low:** Expose a supported transaction/store interface for reminder scheduling and
   delivery instead of accessing `self._store._store`. Existing scope:
   [WISHENKA-180](https://pypost.atlassian.net/browse/WISHENKA-180).
6. **NON-BLOCKER, Low:** Extend opt-in real Telegram smoke testing and multi-process worker race
   coverage to exercise the shared service queue and rate limits. Existing scope:
   [WISHENKA-156](https://pypost.atlassian.net/browse/WISHENKA-156).
