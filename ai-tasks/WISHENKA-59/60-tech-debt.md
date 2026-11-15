# WISHENKA-59: Technical Debt Analysis

## Shortcuts Taken

- The SQLite cabinet reads reuse the existing immediate transaction helper to obtain a consistent
  snapshot. This takes a reserved write lock even though these operations only read.

## Code Quality Issues

- No additional code-quality follow-up was identified. The user index is derived from the
  authoritative reservation objects, and the SQLite path reuses the existing projection.

## Missing Tests

- The focused tests cover indexed selection, lifecycle changes, rollback, restart, isolation,
  concurrent reads and writes, missing wishes, query plans, and storage-error logging. Both new
  test modules declare explicit timeouts. No additional test gap was identified.
- The complete `make check` passed 835 tests before the subsequent read-error logging fix; that
  fix passed its focused tests, Ruff, and mypy. A final full check should include the fix.

## Performance Concerns

- Cabinet list hydration executes an item query and an occupant query per distinct matching wish,
  plus a wishlist header query per distinct wishlist. These queries use targeted keys and avoid a
  full reservation-table scan, but the number of round trips grows with the result size. The
  immediate transaction also serializes the read with SQLite writers for its duration.
- In-memory lookup is expected O(1) for a user bucket, followed by work proportional to matches.
  SQLite uses B-tree indexes rather than strict O(1) lookup, and availability requires inspecting
  reservations on the caller's matching wishes.

## Follow-up Tasks

- **NON-BLOCKER — Medium:** Batch targeted cabinet hydration and investigate a deferred read
  transaction that preserves a single consistent snapshot without acquiring a reserved write
  lock. Validate response parity, concurrent writes, query plans, and latency under representative
  cabinet sizes. The current approach meets the no-full-scan requirement and preserves consistency.

  Jira: [WISHENKA-176](https://pypost.atlassian.net/browse/WISHENKA-176)
