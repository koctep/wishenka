# WISHENKA-28: Technical Debt Analysis

## Shortcuts Taken

- The bot capture handler uses the existing wishlist store's private `_read` and `_write` methods
  within its own transaction to atomically combine domain changes with a save receipt. This
  preserves the current consistency boundary, but couples the bot to the store's internal snapshot
  persistence contract in `wishenka/bot/capture.py`.
- The draft and receipt lifetimes and the cleanup batch size are fixed at 24 hours, seven days,
  and 100 records respectively. The cleanup loop runs hourly and retries a failed pass in one
  minute. These values implement the approved design; there is no measured production workload yet.

## Code Quality Issues

- `bot_capture_order` stores an owner Telegram ID, chat ID, and latest message ID in a separate
  durable table. Its migration has no expiry or foreign key, and `cleanup_drafts` removes only
  expired `bot_drafts`. Consequently these ordering records remain after draft and receipt expiry.
  Removing them without considering delayed Telegram updates could weaken the ordering guarantee.
- Existing Jira Story [WISHENKA-35](https://pypost.atlassian.net/browse/WISHENKA-35) covers
  account deletion and personal-data cleanup generally, but its description does not name these
  new tables. Its implementation must account for both drafts and ordering records. A separate
  retention policy for users who do not delete their account is not specified by that Story.

## Missing Tests

- Capture tests cover draft persistence, interruption, retry, stale callbacks, preview ordering,
  unsafe links, authorization, and cleanup retry. Account deletion does not exist yet, so no test
  can demonstrate that deleting an account removes the new bot state. Add that verification as
  part of WISHENKA-35 alongside its implementation.
- The Step 5 report records explicit timeout markers for all 909 tests then collected. Step 6
  added tests in the same marked module. The latest reported full quality gate before the Step 6
  review fix passed 910 tests; targeted checks passed after that fix.

## Performance Concerns

- Cleanup removes at most 100 expired draft or receipt rows per pass. If the expiry arrival rate
  persistently exceeds the hourly cleanup rate, expired records can accumulate. No production
  measurement establishes that this currently occurs. Monitor cleanup backlog and tune or drain
  bounded batches if workload requires it.
- No benchmark establishes whether the current store snapshot persistence causes a bottleneck in
  this bot flow; avoid claiming a performance regression without measurement.

## Follow-up Tasks

1. **NON-BLOCKER, Medium:** Define and implement bounded retention for `bot_capture_order` while
   preserving protection against delayed or replayed messages. Include tests for late delivery,
   cleanup, and active conversations. Coordinate with account deletion; deleting watermarks solely
   on draft expiry could permit an old message to become current again.
   Jira: [WISHENKA-178](https://pypost.atlassian.net/browse/WISHENKA-178).
2. **NON-BLOCKER, Medium:** Ensure account deletion removes or anonymizes both `bot_drafts`
   (including receipts) and `bot_capture_order` for the actor, and test the result and retries.
   Existing scope: [WISHENKA-35](https://pypost.atlassian.net/browse/WISHENKA-35).
3. **NON-BLOCKER, Low:** Expose a supported store operation for atomically saving a draft and its
   receipt with domain mutations, replacing direct dependence on private snapshot methods. Preserve
   rollback, concurrency, and idempotency tests when refactoring.
   Jira: [WISHENKA-179](https://pypost.atlassian.net/browse/WISHENKA-179).

No task-specific acceptance blocker is asserted by this analysis. The independent blocker review
must assess the current implementation against the approved requirements before closure.
