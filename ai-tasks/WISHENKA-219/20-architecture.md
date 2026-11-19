# WISHENKA-219: Complete purchased promises

## Research

- `ReservationStatus.COMPLETED` already exists, and `wl_reservations.status` is stored as
  unconstrained text. Existing occupancy and cabinet summary calculations include only `active`
  and `purchased`. Completion therefore needs no status migration or quantity mutation.
- `WishlistStore.execute_wish` loads and persists one wish in a `BEGIN IMMEDIATE` transaction.
  Receipt actions use the same wish inventory boundary. SQLite serializes writers, and an
  immediate transaction obtains the write reservation before reading eligibility; see the
  [SQLite transaction documentation](https://www.sqlite.org/lang_transaction.html).
- Receipt events are currently addressed to a distinct giver per wish, not to a reservation.
  Service reminders recheck for an open reservation; the gift-received outbox currently checks
  only for the existence of a reservation, regardless of status. Both queues must be addressed.
- The cabinet projection is currently limited to open reservations. An archived list currently
  prevents all mutation through `_guard_reservation_mutation`, while this task's requirements
  make completion available for eligible purchased promises without an archived-list exception.

## Implementation Plan

1. Add an explicit owner-only completion transition through the wish transaction boundary.
   Preserve receipt records, wish quantity, and other reservations. Return the existing safe
   promise projection and reject stale or ineligible requests with a clear generic outcome.
2. Add an eligible action to the giver's cabinet, including archived lists, and localized
   English/Russian success and refusal feedback. Refresh the cabinet and its active count.
3. Apply open-promise eligibility to both receipt notification paths and fence delivery against
   concurrent completion. Keep another open promise of the same giver and wish eligible.
4. Verify persisted status, occupancy, active distinct counts, privacy, retries and receipt
   correction behavior. No production code changes occur during Step 3.

### Mandatory failing repro (Step 3)

Create `tests/test_wishenka_219_repro.py` using isolated SQLite and existing authenticated HTTP
fixtures, with explicit pytest timeouts and no live Telegram dependency. Before implementing the
feature, assert that a giver's purchased promise on a fully received wish can be completed through
its API and cabinet; assert `completed`, unchanged receipt, freed occupied units, a lower active
count and no completion of a second giver's promise. The test must fail on the current missing
endpoint/action, not on fixture setup. Add targeted red coverage for rejecting intended/partial and
foreign promises, repeat/concurrent actions, and both queued receipt notice paths. After independent
review of the red tests, implement the design and run those tests until green.

## Architecture

```text
Giver cabinet (HTMX + locale) ──POST complete──> reservation API
                                                    │
                                  execute_wish / idempotent execution
                                                    │
                                  WishlistService eligibility + transition
                                                    │
                               SQLite reservation + outbox transaction
                                                    │
Receipt change ──> both notification queues ──> claim/refresh ──> sender
                         eligibility and delivery/completion fence
```

### Components and interfaces

- **Domain (`wishlists/models.py`, `service.py`).** Introduce
  `complete_reservation(reservation_id, user, *, wishlist_id, item_id) -> Reservation`.
  Resolve the exact path and owner without exposing another giver's promise. Inside the wish
  lock and fresh transaction, require status `PURCHASED` and `item.is_fully_received`; set only
  the selected reservation to `COMPLETED` and update its timestamp. A missing, foreign, closed,
  intended or no-longer-fully-received target must not mutate state. Use generic 404 for private
  inaccessible resources and existing 409 conflict conventions for owner-visible stale state.
  Do not reuse the blanket archived-list mutation guard: allow completion on an archived list
  while continuing to reject deleted or inaccessible lists, with no changes to cancellation rules.
- **Store (`wishlists/store.py`).** Route persistent completion through `execute_wish` or its
  idempotent variant, resolving the reservation and loading current receipt and reservation data
  under the write transaction. Verify eligibility and persist state in the same transaction.
  A repeat without a replay key is a conflict; the same valid idempotency key replays the
  original result, without a second transition. Serialization ensures receipt undo and competing
  completion observe an ordered state; busy/rollback responses leave all business state intact.
  Preserve correct behavior for the injected in-memory service using its item coordinator.
- **API (`web/routes/reservations.py`).** Add
  `POST /api/wishlists/{wishlist_id}/items/{item_id}/reservations/{reservation_id}/complete`.
  Use authenticated `User`, existing `execute`/idempotency and `PromiseActionDTO` projection,
  exact path checking, CSRF protections and standard error mapping. The response to an authorized
  giver identifies the result as `completed`; never disclose foreign status or quantity. Replays
  must recheck caller ownership as well as current privacy permissions.
- **Cabinet (`reservations_ui.py`, `reservations_list.html`, `app.js`, i18n).** Show Complete only
  for the caller's purchased promise on a fully received wish, including an archived list when
  still accessible. Preserve existing cancel/purchase controls and their rules. On success refresh
  the list and home badge and show a localized completion result; on stale state, busy, or access
  refusal show a localized actionable result. Closed rows stay out of the active cabinet. If a
  completed promise is displayed elsewhere, render its distinct completed status, never cancelled.
- **Receipt notices (`notices/store.py`, `notices/reminders.py`, `notices/worker.py`).** Both the
  gift-received queue and receipt-increased/reverted service queue must verify an `active` or
  `purchased` entitlement at claim and immediately before sending. On completion suppress queued
  rows only when no other eligible open promise of that giver for that wish remains; do not affect
  other givers or unrelated notices. The existing event model is giver/wish scoped and deduplicated,
  so a shared notice remains eligible for an independently open promise. Never infer a receipt's
  giver from this check or expose it in any recipient-facing projection.

### Delivery and concurrency boundary

Receipt notice suppression includes already-claimed rows. The coordination key is the stable
`(wish_id, giver_user_id)` pair, shared by both receipt queues. All web and worker processes use
the same local directory beside the SQLite database on one host, with reliable advisory file locks.
A deployment that cannot provide this common lock namespace must fail closed; SQLite WAL itself
requires processes sharing the database to run on one host. Use a stable hash of the key as the
lock-file name, never delete or replace lock files while the application is running, and restrict
directory permissions. Each attempt opens a separate descriptor and takes a nonblocking exclusive
OS lock; a local async keyed lock also serializes tasks within a process. Acquire locks before any
SQLite write transaction, and always release the descriptor in `finally` after the transaction and
network lifecycle. No SQLite transaction remains open during network I/O.

The database stores a durable delivery fence for each key, with an attempt ID, queue and row ID,
and state `in_flight` or `uncertain`. Creation, transition and deletion occur under the OS lock in
short `BEGIN IMMEDIATE` transactions. This is independent of the existing queue claim lease:
claim expiry or a new claim token never clears or overrides the fence.

1. A worker may claim as today, but before any receipt send it takes the key lock. In a fresh write
   transaction it checks its claim token and current open-promise authorization, checks that no
   fence exists, then writes an `in_flight` fence with a fresh attempt ID and commits. If a check
   fails it releases the lock and skips or reschedules without sending. This procedure is identical
   for gift-received and receipt-increased/reverted notices. Workers must recheck the token after
   taking the lock even if a previous refresh succeeded.
2. The worker holds the lock across the external send and result settlement. A definitive result
   is recorded against the same attempt and queue token and the fence removed in one transaction;
   an ambiguous result or inability to settle changes the fence to `uncertain`, never to absent.
   If the process dies before that update, its persisted `in_flight` fence is also treated as
   `uncertain` on the next lock acquisition. Timeout, task cancellation and lease expiry alone are
   not proof that the external call stopped, nor that its remote outcome is known.
3. Completion takes the same lock *before* its wish transaction. If lock acquisition fails, or if
   an `in_flight` or `uncertain` fence remains, it returns retryable busy without changing state.
   Otherwise, in one transaction it rechecks ownership, receipt and status, completes the promise
   and suppresses eligible queued rows only if no other open promise for the key remains. It commits
   before releasing the lock. A later worker takes the lock and sees the completed state; it skips
   unless another open promise independently authorizes the notice.
4. A worker suspended across claim expiry still holds the OS lock and prevents completion or a
   second send. On process death the OS releases the lock, but the durable fence remains. Recovery
   must not automatically steal, retry or clear it: an operator or transport reconciliation may
   resolve it only with evidence that no old sender can resume and the downstream outcome is final.
   The resolution is audited; absent that evidence, completion remains busy. Queue retries use
   their existing token checks after the fence is safely resolved. A process resumed after a mere
   lease expiry cannot bypass the lock, attempt ID or durable fence.

There is a fundamental external-delivery limit: a Telegram request accepted before completion can
be displayed to the recipient after completion, and this application cannot recall it or prove when
it was displayed. This design prevents *initiating* a new send after successful completion, and
fails closed for an unknown handoff; it cannot guarantee the wall-clock display order of an already
accepted message. Do not claim that stronger guarantee in the API or tests. If the requirement
literally prohibits late display of previously accepted messages, it needs a product decision or a
transport with revocable/acknowledged delivery before the feature can meet it.

Tests use two processes and controllable fake senders for each queue: pause before and during send,
expire the queue lease, attempt a second claim and completion, resume the original worker, and
assert neither competing send nor successful completion crosses the held lock. Kill a sender after
fence persistence, verify completion and retry remain busy after lock release and across restart,
and verify an explicit evidence-backed resolution permits progress. Also exercise completion-first,
ambiguous timeout, a crash before network handoff, transaction rollback, multiple open promises,
and both lock acquisition orders. Tests assert call initiation order and persisted outcomes, not
unobservable Telegram display time.

### Patterns and privacy

The existing service/transaction boundary remains the single source of transition rules. SQLite
write serialization plus the existing per-item in-process coordinator gives atomic inventory
changes; the delivery fence separately coordinates external I/O. Project only the giver's own
promise; receipt records remain anonymous and unchanged. Status filters apply to active counts,
availability, notification authorization and all status serialization paths. No new shared
purchase semantics or recipient-visible booking data are introduced.

## Q&A

- **Does receipt itself complete a promise?** No; only the giver's explicit action transitions it.
- **Do completed units reopen a fully received wish?** No; received units still make availability
  zero. Undo may later change availability, but does not reopen a completed promise.
- **Can another open promise retain a notice?** Yes. Notices are deduplicated per giver/wish;
  delivery remains authorized when that same giver has another qualifying open promise.
- **What happens to stale requests?** Current state is checked atomically; a clear refusal or
  retryable busy response makes no partial change. A previously committed idempotent request
  returns its original success only after access is revalidated.
