# WISHENKA-213: Scoping Wishlist Mutation State Loading to Target Wishlist

## Goals

Every wish lifecycle mutation that does not already operate on a single-wish fast path (such as adding a wish, reordering wishes, archiving/restoring wishes, updating wishlist metadata, or managing wishlist membership) currently loads the entire wishlist database into memory before applying the change and persisting the result. As the number of users, wishlists, and items grows, the latency, memory footprint, and write-lock hold time of every individual wishlist mutation degrade linearly with total system size rather than remaining proportional to the size of the affected wishlist.

The business goal of this task is to ensure that single-wishlist operations scale with the size of the target wishlist rather than the total database size, keeping user-facing wish management responsive under growth and concurrent load while preserving 100% functional parity, data integrity, and isolation across wishlists.

## User Stories

- **As a Wishlist Owner or Co-author**, I want adding, editing, reordering, archiving, or restoring wishes in my wishlist to remain fast regardless of how many other wishlists exist in the system, so that the app stays responsive as the platform grows.
- **As a Platform Operator**, I want single-wishlist mutations to hold write locks for minimal duration and read only the data needed for the target wishlist, so that concurrent users editing different wishlists experience minimal contention and predictable resource usage.
- **As a Wishlist User**, I want all permission checks, notifications, capability/invite token uniqueness, and concurrent updates to behave identically before and after the optimization, so that no regressions or data corruption occur.

## Definition of Done

1. **Measurable Read/Row-Load Reduction**: Single-wishlist mutations scoped to a target `wishlist_id` load only the state relevant to that wishlist (plus any required global uniqueness/counter/setting checks) rather than hydrating all wishlists, items, reservations, members, receipts, favorites, and view history across the entire database. A repeatable measurement demonstrates a clear reduction in rows read (and/or query volume) for a target wishlist mutation in a multi-wishlist database compared to full-database hydration.
2. **Correctness Parity**: All existing wish lifecycle, wishlist management, membership, notification, and capability/invite token behaviors produce identical outcomes (return values, domain errors, persisted state, emitted notices, shared events, and audit/commit logs) when scoped to a target wishlist as they do under full-database hydration.
3. **Token Collision Safety**: Public and invite capability token generation and rotation remain globally unique across all wishlists; collisions are still detected and safely retried without overwriting or conflicting with another wishlist's tokens.
4. **Concurrent Write Safety & Isolation**: Concurrent mutations on the same wishlist and across different wishlists preserve atomicity, serialization guarantees, ID allocation uniqueness, and cross-wishlist isolation without lost updates, stale snapshot corruption, or partial commits.
5. **Unscoped Operations Preserved**: Operations that genuinely span multiple wishlists or cannot be scoped to a single `wishlist_id` (e.g., cross-wishlist user views, user-level operations without a single target wishlist) continue to work without regression.
6. **Quality Gate**: Automated tests (including existing wishlist lifecycle and concurrency/stress suites) pass without regressions.

## Task Description

### Programming Language
- **Python** (existing backend domain and storage layer).

### Problem Statement
Currently, general wishlist mutations load every wishlist, member, item, reservation, receipt, notification setting, favorite, and view history entry in the database into memory, run the domain operation, and diff/persist changes back to storage inside an exclusive write transaction. This causes:
- Unnecessary I/O and memory allocation proportional to total database size.
- Longer exclusive write-lock hold times, increasing contention across unrelated wishlists.
- Slower execution of wish lifecycle operations (e.g., add, reorder, archive, restore) and stress tests.

### Functional Requirements
1. **Wishlist-Scoped Execution**:
   - Operations targeting a single `wishlist_id` must be able to execute with state hydration limited to that target wishlist and its associated domain data (members, items, reservations, receipts, and relevant notification settings/counters).
   - Unscoped operations (those without a single `wishlist_id` or spanning multiple wishlists) must remain supported with full correctness.
2. **Domain Behavior Parity**:
   - Permission checks (Owner, Admin, Member, Viewer), collaborative wishlist rules, item ordering, archiving/restoring, reservation interactions, and notice/shared-event generation must behave identically to unscoped execution.
   - Domain errors (e.g., not found, permission denied, deleted wishlist, stale reorder validation) must raise the exact same exceptions and leave persisted state unchanged.
3. **Global Invariants**:
   - **Token Uniqueness**: Public tokens and invite tokens must remain globally unique across all wishlists, with collision detection and retry behavior preserved.
   - **ID Allocation**: New entity identifiers (wishlists, members, items, reservations, view history) must remain globally unique and monotonic even when only a single wishlist is loaded.
   - **Counters & Cross-Cutting Data**: Shared counters and user-level settings required by the operation must remain accurate and consistent.

### Non-Functional Requirements
1. **Performance & Scalability**:
   - For a database containing $N$ wishlists, a single-wishlist mutation must read $O(\text{target wishlist size})$ domain rows rather than $O(\text{total database size})$ rows.
   - The reduction in rows read / hydration scope must be verifiable by automated tests.
2. **Concurrency & Atomicity**:
   - All writes within a wishlist-scoped operation must remain atomic (all-or-nothing on failure or busy timeout).
   - Concurrent operations on different wishlists and on the same wishlist must remain safe under SQLite WAL contention.
3. **Observability**:
   - Storage read/write telemetry and rollback/error logging must remain accurate and must not leak sensitive user/gifter identifiers or raw driver dumps.

### Scope & Boundaries
- **In Scope**:
  - Scoping single-wishlist mutation execution to the target `wishlist_id` (and evaluating whether targeted updates or scoped hydration is appropriate for wish lifecycle mutations).
  - Ensuring all callers that have a known `wishlist_id` can benefit safely without breaking callers that do not.
  - Verifying correctness parity, token collision safety, concurrent write safety, and measurable row-read reduction via tests.
- **Out of Scope**:
  - Changing product/business rules of wishlists, items, reservations, or notifications.
  - Migrating away from SQLite WAL or redesigning the external HTTP/bot APIs.
  - Modifying unrelated subsystems (such as the notice scheduler or bot draft storage beyond existing integration boundaries).

### Main Domain Entities (Business Perspective)
- **Wishlist**: A named collection of wishes owned by a user, with status, collaboration settings, and unique public/invite capability tokens.
- **Wishlist Member**: A user's role (`Owner`, `Admin`, `Member`) within a specific wishlist.
- **Wish Item**: An item within a wishlist, with display order, quantity, received quantity, and archive status.
- **Reservation**: A promise by a giver to fulfill a quantity of a wish item.
- **Receipt**: A record of gift delivery/completion linked to a wish item.
- **Notification Settings & Notices**: Per-user and per-wishlist preferences governing notifications emitted on domain events.

### Constraints & Assumptions
- The storage layer uses SQLite in WAL mode with `BEGIN IMMEDIATE` write serialization and a bounded `busy_timeout`.
- Existing single-wish fast paths (`execute_wish` / `execute_wish_idempotent` for item/reservation inventory changes) already exist and should remain intact or consistent with the wishlist-scoped model.

## Q&A

- **Q: Why is this technical debt being addressed?**
  - **A**: Identified in [WISHENKA-102 Technical Debt Analysis](file:///home/src/ai-tasks/WISHENKA-102/60-tech-debt.md) — full-database hydration on every wish lifecycle mutation (`add_wish_item`, `reorder_wish_items`, `archive_wish_item`, etc.) causes every mutation to scale with total DB size and serialize globally for longer than necessary, degrading scalability and stress-test performance.
- **Q: Should all `execute()` callers be forced to provide a `wishlist_id`?**
  - **A**: No. Callers that genuinely span multiple wishlists or operate without a single target `wishlist_id` (e.g., creating a new wishlist or cross-wishlist operations) must continue to work; scoping applies where a target `wishlist_id` is known or applicable.
