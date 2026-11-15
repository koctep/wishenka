# WISHENKA-59: Indexed access to a giver's reservations

## Research

- `WishlistService` owns an in-memory `_reservations` dictionary. Both cabinet methods scan
  its values; insertion order currently determines the list order. Creation writes directly
  to that dictionary; status and quantity changes mutate the existing reservation object.
- `WishlistStore._read` builds a complete service snapshot, and the cabinet routes call it
  through `execute`. Indexing only that temporary service would still scan all reservations on
  every database-backed request. `WishlistRepository.list_user_reservations` already filters
  by user and orders by ID; `idx_wl_reservations_user` and `idx_wl_reservations_item` already
  exist in the baseline SQLite schema.
- The list omits a reservation whose item is missing; the summary still counts it. The list's
  `change_ceiling` depends on all occupying reservations on the matching wish, not only the
  caller's reservation. Both methods include active and purchased statuses.
- Python dictionaries preserve insertion order
  ([Python documentation](https://docs.python.org/3/library/stdtypes.html#mapping-types-dict)).
  SQLite can use an index to restrict rows and order results, subject to its cost-based planner
  ([SQLite query planner](https://www.sqlite.org/queryplanner.html)). Database index lookup is
  logarithmic in index size, not literally O(1); it avoids a scan of unrelated reservations.

## Implementation Plan

1. Add a giver-to-reservation-ID index to the in-memory service and use it for both cabinet
   methods. Preserve primary dictionary iteration order for each giver, including updates,
   cancellation and later reactivation. Keep the primary reservation object authoritative.
2. Centralize registration/removal of reservations so creation and both store-loading paths
   maintain the index. Register all statuses and filter at read time, so status changes need no
   separate index mutation. Empty buckets are removed when entries are removed. If any path can
   change a reservation's giver, remove the old membership and insert the new membership in the
   same synchronous mutation; otherwise enforce giver immutability for registered entries.
3. Add dedicated database-backed cabinet read operations. Query matching user reservations
   using the existing user index, ordered by reservation ID. For the list, load only their
   associated wishes and wishlists and the reservations needed to calculate each wish's
   availability, using the existing item index. Reuse existing domain-to-DTO projection and
   recipient naming logic rather than create divergent business rules. Summary counts from the
   filtered reservations without requiring a corresponding wish.
4. Route the two cabinet reads through these targeted store operations when using SQLite, while
   retaining the indexed service methods for injected in-memory services. Do not pass these reads
   through the full-snapshot `execute` path. Keep all queries for one result in a single read
   transaction so concurrent updates cannot produce a mixed view. No schema migration is needed
   if the existing indexes are confirmed in both new and upgraded supported databases.
5. Preserve caller identity checks and response shape; index membership alone is not an access
   check. Keep per-wish availability data private to the existing projected fields.

### Failing repro before production changes

Add bounded pytest tests under `tests/` that populate multiple users and use a counting or
scan-forbidding reservation mapping to prove both in-memory methods return the expected caller's
results without calling `.values()` on the entire dictionary. The current implementation must
fail for that exact full scan. Add an integration repro for the SQLite cabinet path that observes
executed SQL and fails if it loads all `wl_reservations` through the full snapshot; seed multiple
users and assert the correct list and summary. Use a local temporary SQLite database and no live
services. Review the red result before production changes.

After the fix, verify insertion ordering and isolation; create, quantity change, purchase,
cancel, restore/reactivate, delete and missing-item cases; empty users; duplicate wishes; and
transaction failure or cancellation. Exercise both in-memory and SQLite modes, restart a
persistent database, compare both outputs against a reference scan, and check the SQLite query
plan uses the user index with representative data. Test concurrent updates and reads for a
consistent committed snapshot. Explicitly cover availability with another user's reservation.

## Architecture

```text
Cabinet HTTP routes -- authenticated user --> in-memory WishlistService
                   |                           |-- giver ID index --> reservations
                   +--> WishlistStore read transaction --> WishlistRepository
                                                       |-- user index --> reservations
                                                       +-- item index --> wish availability
                                  domain projection --> existing DTOs --> templates
```

- **In-memory service:** owns the primary reservation objects and a derived ordered mapping
  `user_id -> ordered reservation IDs`. Finding a user's bucket is expected O(1); iterating
  matching reservations is O(K). No asynchronous suspension may occur between updates to the
  primary mapping and its derived index. An index is rebuilt from authoritative entries during
  service hydration, not persisted separately. Status and quantity changes remain visible via
  the primary objects. Read order must match the previous primary dictionary order.
- **SQLite store/repository:** owns a read-only, targeted, transactionally consistent cabinet
  query. Existing indexes are maintained by SQLite as part of the same transaction as row
  changes, including rollback and cascades. Use the same DTO constructor and domain conversion
  rules as the service. The item-side lookup may process reservations from other givers on the
  caller's matching wishes because availability requires them; it must not scan the full table.
  Hydration work scales with matches and associated wishes/occupants, not all users' records.
- **Interface:** expose store methods analogous to `get_user_reservations(user_id)` and
  `get_user_reservations_summary(user_id)` returning existing DTOs. Keep service method
  signatures and routes' response contracts unchanged. Request-scoped SQLite reads use one
  connection and transaction; no cross-request cached index is introduced.
- **Persistence and failures:** existing store writes remain authoritative. A failed or
  cancelled transaction rolls back all changes; an ephemeral service and its index are discarded.
  Direct in-memory changes update primary data and index together without awaiting. Startup and
  wish-scoped hydration must use the same registration path; indexed reads must not rely on a
  partially hydrated service as if it represented the full database.

## Q&A

- **Why use two indexes?** The in-memory index serves a long-lived injected service; SQLite's
  existing user and wish indexes support targeted reads without creating a full snapshot.
- **Why not count only visible items?** Existing summary counts eligible reservation records
  even if a referenced wish is unavailable. The list intentionally omits those records.
- **Can lookup be strictly O(1) in SQLite?** No: a B-tree lookup is not a hash lookup. The
  practical guarantee is indexed selection without a table-wide scan, plus work proportional to
  the caller's matches and the related wishes needed for display.
