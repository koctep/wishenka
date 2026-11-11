# WISHENKA-48: Scalable SQLite Relational Storage and Repositories for Wishlists

## Goals

This task addresses critical technical debt in the wishlist storage layer:

- **Scalability & Resource Efficiency**: The current storage loads all wishlists, items,
  members, reservations, favorites, and view history into process memory and rewrites all
  tables on every mutation. As data volume grows, this approach leads to memory exhaustion,
  high latency, and SQLite write lock contention. Granular relational storage is required.
- **Reliability & Zero Data Loss**: Replacing full-table truncations and mass re-inserts with
  atomic, row-level updates eliminates catastrophic data loss risks during process crashes or
  unhandled exceptions.
- **Granular Domain Access**: Enable column-level queries and indexed lookups by ID, owner,
  member, or capability token without loading unrelated records.
- **Preservation of Domain Invariants**: Maintain strict access control (RBAC), item quantity
  accounting, and the **Surprise Invariant** (recipients must never see reservation details
  for items intended for them).

## User Stories

### Persona 1: System Operator / DevOps
- **US-1**: As a system operator, I want the application to query only the necessary records
  from SQLite WAL rather than deserializing the full database into RAM, so that memory usage
  and latency remain low and predictable under increasing load.
- **US-2**: As a system operator, I want every state mutation to execute within an atomic
  transaction without full-table wipes, so that unexpected process terminations never result
  in corrupted or lost data.

### Persona 2: Wishlist Owner
- **US-3**: As a wishlist owner, I want to create, update, archive, and delete my wishlists and
  items reliably, without performance degradation caused by unrelated users' activities.
- **US-4**: As a wishlist owner, I want gifts reserved by friends to remain hidden from my view,
  so that my surprises are never spoiled.

### Persona 3: Collaborator / Member
- **US-5**: As a collaborative wishlist member or admin, I want to view shared wishlists and
  manage items according to my granted permissions (Owner, Admin, or Member).

### Persona 4: Gifter / Guest
- **US-6**: As a gifter, I want to open a wishlist using a public access token, view available
  items and their remaining quantities, and reserve items without race conditions or overbooking.
- **US-7**: As a gifter, I want to update the status of my reservations (active, purchased,
  cancelled) reliably and independently from other gifters.

## Definition of Done

The implementation is considered complete when all of the following acceptance criteria are met:

1. **Granular Persistence Operations**:
   - Creating, reading, updating, or deleting a wishlist, item, member, or reservation affects
     only the relevant rows and aggregates.
   - The full-table delete and bulk re-insert pattern (`DELETE FROM <table>`) is completely
     eliminated.
2. **Zero Data Loss & Crash Resilience**:
   - All mutations execute within atomic transactions.
   - A failed mutation or database rollback leaves existing data unaltered.
3. **Domain Invariant Integrity**:
   - **Surprise Invariant**: When a recipient views an item (whether in a personal wishlist or
     as an assigned recipient in a collaborative wishlist), all reservation details, gifter
     identities, and reservation statuses are strictly excluded from the view projection.
   - **Quantity Integrity**: The sum of active and purchased reservations plus received
     quantities cannot exceed the item's desired quantity. Negative or zero-quantity
     reservations are rejected.
   - **Access Control (RBAC)**: Only authorized roles can modify wishlist settings, invite or
     remove members, or edit wishlist items, respecting wishlist lifecycle states (Active,
     Archived, Deleted).
4. **Concurrency Safety**:
   - Concurrent reservation attempts for the same item are serialized or guarded against
     overbooking, ensuring available quantity never drops below zero.
5. **Full Test Suite Compatibility**:
   - All existing domain tests, lifecycle tests, UI projection tests, and concurrency tests
     pass without regressions.

## Task Description

### Problem Statement
The current prototype implementation in `WishlistStore` serializes all entities as JSON
strings in SQLite tables (`wl_lists`, `wl_members`, `wl_items`, `wl_reservations`, etc.). On every
operation, it reads the entire database into memory to construct a transient `WishlistService`
instance. When any modification occurs, it deletes all rows across all tables and re-inserts
the entire dataset.

This pattern poses severe risks:
- Unbounded memory consumption scaling with total application data.
- SQLite database lock contention and latency spikes.
- Complete data loss vulnerability if a crash occurs between table deletion and re-insertion.
- Inability to perform efficient indexed relational lookups and pagination.

### Functional Scope
1. **Wishlists Management**:
   - Persistence and retrieval of wishlist aggregates by ID, owner ID, public share token, and
     invite token.
   - Support for personal and collaborative formats, lifecycle statuses (active, archived,
     deleted), and event metadata.
2. **Collaborator Membership**:
   - Managing members with specific roles (Owner, Admin, Member) and join timestamps.
   - Unique membership constraint per user and wishlist.
3. **Wish Items Management**:
   - Storing wish items with attributes: title, description, external link, pricing, currency,
     desired quantity, received quantity, priority, category, and recipient assignment.
   - Filtering and querying items by wishlist ID and recipient.
4. **Reservations & Gifter Lifecycle**:
   - Storing reservations linked to wish items with gifter ID, quantity, status (active,
     purchased, cancelled, completed), and timestamps.
   - Atomic quantity validation against item available capacity.
5. **Favorites & View History**:
   - Managing user favorites (unique bookmark per user and wishlist).
   - Managing chronological view history entries with duplicate prevention per user and wishlist.

### Non-Functional Requirements
- **Implementation Language**: Python (3.12+).
- **Storage Engine**: SQLite in WAL (Write-Ahead Logging) mode with foreign key enforcement and
  a bounded busy timeout.
- **Performance**: Individual item or wishlist queries must execute in O(1) or O(K) where K is
  the number of items in that specific wishlist, rather than O(N) over the entire database.
- **Maintainability**: Clear separation between domain models, access policies, and data
  access abstractions.

## Business Entities

- **Wishlist**: The root aggregate representing a gift registry. Has an owner, optional event
  details, format (personal or collaborative), status (active, archived, deleted), and unique
  capability tokens for public sharing and collaborative invitations.
- **Wishlist Member**: Represents a user's membership and permission role (Owner, Admin, Member)
  within a collaborative wishlist.
- **Wish Item**: An individual item desired within a wishlist, containing descriptive metadata,
  pricing, priority, desired quantity, received quantity, and optional recipient designation.
- **Reservation**: A commitment by a gifter to fulfill a specific quantity of a wish item,
  tracked through lifecycle states (active, purchased, cancelled, completed).
- **Wishlist Favorite**: A user bookmark referencing an accessible wishlist.
- **View History Entry**: A timestamped log entry recording a user's visit to a wishlist.
- **Capability Token**: Cryptographically secure, unguessable string granting specific access
  rights (public view or member invitation) to a wishlist.

## Q&A

- **Q1: Why is this considered technical debt rather than a feature?**
  - **A**: The feature set and business logic for wishlists already exist and function correctly
    in domain tests. However, the underlying storage implementation (in-memory deserialization
    and full-table overwrites) is a prototype shortcut that does not scale and introduces severe
    data safety risks.
- **Q2: Does this change alter the user experience or business rules?**
  - **A**: No. All business rules, access policies, role permissions, and the Surprise Invariant
    remain identical. The user experiences faster, more reliable interactions without data loss.
- **Q3: How is the Surprise Invariant maintained at the repository boundary?**
  - **A**: The repository persists item and reservation data with relational integrity. The
    domain service and projection layer continue to inspect the viewer's identity and strip
    all reservation records whenever the viewer is the item's recipient.
- **Q4: How are capabilities and access tokens managed?**
  - **A**: Tokens remain unique and unguessable keys associated with wishlists, ensuring fast
    indexed lookup and secure capability-based authorization without leaking private list IDs.
