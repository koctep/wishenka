# WISHENKA-7: Technical Debt Analysis

## Shortcuts Taken

- The store serializes domain dataclasses as JSON payloads and initializes tables with
  `CREATE TABLE IF NOT EXISTS`. There is no schema version or migration path for future
  dataclass field changes. Existing database files may fail to load after an incompatible
  model change. Coordinate schema evolution with the existing
  [WISHENKA-48](https://pypost.atlassian.net/browse/WISHENKA-48) persistence work.
- `WishlistService()` without an injected store still creates an independent in-memory
  service. The application exposes a store-backed service, but future production callers
  could accidentally bypass persistence. Make the intended construction boundary explicit
  when integrating other routes and workers.
- The approved architecture calls for database-managed sequences, but `WishlistService`
  increments application counters that `WishlistStore` persists in `wl_counters`. The
  store reads and writes those counters inside `BEGIN IMMEDIATE`, serializing cooperating
  writers and retaining allocated IDs across restart; a rolled-back allocation may be
  reused. Correctness depends on every writer using that transaction boundary, and direct
  database writes or counter corruption can produce collisions. Move ID allocation into
  database-managed sequences or equivalent atomic allocation when replacing the store.
  The concurrent-instance test checks distinct IDs, but does not cover external writers.

## Code Quality Issues

- Routes access service internals (`_wishlists`) and edit wishlist attributes directly.
  This couples HTTP handlers to the temporary in-memory aggregate representation and can
  bypass future domain validation. Move list lookup and settings updates behind explicit
  application-service methods during repository integration.
- The legacy domain public-token lookup selects a giver projection for anonymous callers;
  the new HTTP route uses a separate safe allowlist. Reusing that domain method for a future
  public endpoint could disclose reservation details. Consolidate public projections before
  exposing it through another entry point.

## Missing Tests

- Current tests cover concurrent app instances and persistence, but do not exercise
  separate operating-system processes or restart during a write. Add process-level
  contention and interrupted-transaction coverage as part of persistence hardening.
- There is no migration compatibility test for a database created by an older schema;
  add one when versioned migrations are introduced.

## Performance Concerns

- Every store operation acquires `BEGIN IMMEDIATE`, loads every wishlist, item, member and
  reservation, and rewrites the full aggregate graph even for reads. Runtime and write
  contention grow with total database size, and reads compete for the SQLite writer lock.
  No quantitative performance target is specified for this story. Replace whole-store
  serialization with targeted queries and writes, and benchmark representative workloads;
  coordinate with [WISHENKA-48](https://pypost.atlassian.net/browse/WISHENKA-48) and
  [WISHENKA-57](https://pypost.atlassian.net/browse/WISHENKA-57).
- The issued-token registry keeps every revoked capability to guarantee non-reuse and has
  no retention or compaction strategy. Its growth should be measured before selecting a
  scheme that preserves the non-reuse guarantee.

## Follow-up Tasks

1. **NON-BLOCKER, Medium:** Add versioned schema migrations and compatibility tests;
   tracked by [WISHENKA-48](https://pypost.atlassian.net/browse/WISHENKA-48).
2. **NON-BLOCKER, Medium:** Replace whole-store load/rewrite with targeted transactional
   repository operations and add process-level contention and crash-recovery tests;
   coordinate with [WISHENKA-48](https://pypost.atlassian.net/browse/WISHENKA-48) and
   [WISHENKA-57](https://pypost.atlassian.net/browse/WISHENKA-57).
3. **NON-BLOCKER, Medium:** Consolidate public projections and restrict accidental use of
   in-memory services by production entry points; test anonymous and recipient views.
   Jira: [WISHENKA-63](https://pypost.atlassian.net/browse/WISHENKA-63).
4. **NON-BLOCKER, Low:** Define a bounded-growth strategy for issued-token history that
   preserves revocation and permanent non-reuse guarantees.
   Jira: [WISHENKA-64](https://pypost.atlassian.net/browse/WISHENKA-64).
5. **NON-BLOCKER, Medium:** Replace persisted application ID counters with database-managed
   allocation and test concurrent writers, rollbacks, restarts and external writes;
   coordinate with [WISHENKA-48](https://pypost.atlassian.net/browse/WISHENKA-48).

No pre-existing red test failures were reported during this task. The latest `make check`
passed 111 tests; the new API test module declares an explicit pytest timeout.
