# WISHENKA-82: SQLite reservation contention test

## Research

- `WishlistStore.initialize()` runs migrations and selects WAL; its engine uses a five-second
  SQLite busy timeout and starts inventory transactions with `BEGIN IMMEDIATE`.
- `WishlistStore.execute_wish()` loads and persists the target wish inside one transaction.
  `WishlistService.create_reservation()` rejects insufficient quantity before creating a row.
- `tests/test_booking_ceiling_r5.py` races five distinct users through this path and treats
  `InsufficientQuantityError` as the expected refusal; it does not cover the requested 50.
- SQLite permits readers and a writer concurrently in WAL but still serializes writers; see
  [SQLite WAL documentation](https://www.sqlite.org/wal.html). Simultaneous coroutine scheduling
  is not evidence of simultaneous writes.

## Implementation Plan

1. Add a bounded async integration test to `tests/test_wishlists_sqlite_repo.py`, overriding its
   existing ten-second module timeout with an explicit timeout for this contention test.
2. Initialize a temporary file-backed `WishlistStore`, create a wishlist and a wish of quantity
   one, and verify the database uses WAL and its connections have the configured busy timeout.
3. Release 50 distinct giver coroutines from a bounded start gate and call `execute_wish()` with
   `create_reservation(..., quantity=1)` for each. Schedule all 50 before releasing the gate.
   Connection pooling can limit the number of simultaneous database writers; no in-memory mock or
   per-test global service lock should stand in for SQLite transactions.
4. Collect all results with `asyncio.gather`, bounded by `asyncio.wait_for`. Count exactly one
   successful reservation and 49 `InsufficientQuantityError` refusals; fail on all other errors,
   including busy and timeout exceptions. Inspect persisted rows and quantity to prove exactly one
   active reservation of one unit and no overbooking. Dispose the store even on failure.
5. Validate the busy wait path separately using two independent connections: hold an immediate
   write transaction, start a reservation attempt on another connection, show it has reached the
   database while the lock is held, release the holder before the five-second limit, and assert
   the attempt completes. Coordinate with events and bounded waits, not arbitrary sleeps. Cleanup
   must release the lock and cancel and await pending tasks on every exit path.
6. Run the focused test and full suite. If stress reveals a genuine existing failure, record and
   investigate it; do not count an unexpected storage error as a business refusal.

**Failing repro (Step 3):** N/A — no behavioral change. The task adds coverage of an existing
reservation invariant; the requested test is expected to pass against current production code.
If it does not, establish its failure reason and handle the discovered defect through the workflow.

## Architecture

```text
50 giver coroutines -> start gate -> WishlistStore.execute_wish
    -> SQLite BEGIN IMMEDIATE / busy timeout -> WishlistService.create_reservation
    -> one commit or 49 shortage rollbacks -> persisted reservation assertions
```

- The test owns a fresh database, user identities, bounded gates, result classification, and
  resource cleanup. It does not change the service or storage implementation.
- The store provides pooled SQLite connections and transaction isolation; the service enforces
  the quantity rule. The existing repository persists the resulting row.
- The separate controlled lock scenario exercises a waiter and release within the busy timeout;
  the 50-attempt test validates the overall reservation outcome under contention.

## Q&A

- **Why use `execute_wish`?** It is the production inventory transaction used by reservation
  requests and prevents the test from bypassing the relevant storage path.
- **Does 50 coroutines mean 50 simultaneous writes?** No. The pool and SQLite serialize access;
  the test launches 50 attempts and validates correctness rather than claiming throughput.
- **What is an acceptable refusal?** Only the expected insufficient-quantity domain exception;
  other failures must remain visible.
