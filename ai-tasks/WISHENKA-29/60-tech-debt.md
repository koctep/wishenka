# WISHENKA-29: Technical Debt Analysis

## Shortcuts Taken

- The delivery worker coordinates receipt and service queues and the hourly reminder scan in one
  process. Scheduler errors are isolated from delivery, but a backlog or resource contention can
  still increase latency. The existing operator command resolves ambiguous sends explicitly; it
  cannot establish whether Telegram accepted a request when its response was lost.
- Existing receipt rows cannot prove their historical membership at enqueue time. The migration
  sets `requires_membership` on all legacy rows and the worker rechecks membership, deliberately
  suppressing some notices whose former access cannot be reconstructed.

## Code Quality Issues

- `birthday_entries` retains the label, date and owner after the user deletes an entry: deletion in
  `wishenka/bot/birthdays.py` marks the row deleted and increments its revision. Deleted entries
  no longer generate reminders, but no physical purge is implemented.
- `reminder_outbox` retains completed and skipped occurrences and their keys, user IDs and source
  references; no corresponding purge exists in `wishenka/notices/reminders.py`. The receipt queue
  can purge terminal rows, but `notice_receipt_keys` retains deduplication keys until their receipt
  is deleted. This prevents duplicate scheduling but requires a bounded, replay-safe retention
  policy. `bot_destinations`, `birthday_entries`, `birthday_input`, `reminder_outbox`,
  `notice_receipt_keys`, and chat-specific `notice_rate_slots` must also be included in account
  deletion or anonymization. Existing [WISHENKA-35](https://pypost.atlassian.net/browse/WISHENKA-35)
  covers personal-data deletion generally but predates these tables.
- The reminder worker accesses the wishlist store's internal `_store` to share its transaction
  boundary. This couples the delivery implementation to a private store attribute; a supported
  transaction interface would make future storage changes easier to validate.

## Missing Tests

- The Step 5 quality gate audited explicit timeout markers for all 976 tests then collected. Step 6
  adds tests in `tests/test_service_notice_observability.py`, which has an explicit module timeout.
  The latest full gate after Step 6 reported 985 passing tests; no pre-existing failures were filed.
- Worker tests use fake Telegram senders. The existing
  [WISHENKA-156](https://pypost.atlassian.net/browse/WISHENKA-156) tracks an opt-in real Telegram
  smoke test and a two-process receipt-worker race. Its implementation should include the expanded
  service queue and shared rate limits where applicable; no real Telegram call was made here.

## Performance Concerns

- The scheduler scans bounded pages and resumes promptly when more pages remain; the worker
  drains its delivery queues between scans. Cursors and occurrence keys persist across restarts.
  Actual throughput remains workload-dependent, so production backlog should be monitored.
- Each list scan fetches its recipients separately inside the transaction. This is an N+1 query
  pattern; measure database lock time and throughput before selecting a batching strategy.
- Windowed observability counters are held in process memory and can be lost on abrupt shutdown;
  durable queue state remains available for operational inspection.

## Follow-up Tasks

1. **NON-BLOCKER, High:** Define and implement retention and deletion for private birthday data,
   inactive bot destinations, terminal reminder rows and receipt deduplication keys. Preserve
   idempotence and prevent late or replayed events from producing duplicate notices. Verify that
   a user's removal of a birthday removes or anonymizes its stored private values within the chosen
   retention policy, and test recovery, deletion and outstanding `uncertain` rows. Jira:
   [WISHENKA-181](https://pypost.atlassian.net/browse/WISHENKA-181).
2. **NON-BLOCKER, High:** Include all new notification and birthday tables in account deletion or
   anonymization, including pending input, destination and rate-bucket identifiers, with tests for
   retries and mixed pending/terminal queues. Existing scope:
   [WISHENKA-35](https://pypost.atlassian.net/browse/WISHENKA-35).
3. **NON-BLOCKER, Low:** Expose a supported transaction/store interface for reminder scheduling and
   delivery instead of relying on the private `_store` attribute, preserving atomicity and tests.
   Jira: [WISHENKA-180](https://pypost.atlassian.net/browse/WISHENKA-180).
4. **NON-BLOCKER, Low:** Extend the existing real-provider and multiprocess worker coverage for the
   shared service queue and rate limits under
   [WISHENKA-156](https://pypost.atlassian.net/browse/WISHENKA-156).

The independent blocker review must assess all items against the requirements and current
implementation before closure.
