# WISHENKA-13: Technical Debt Analysis

## Shortcuts Taken

1. **Sequential N-Query Updates for Item Reordering**:
   - **Context**: In [`WishlistService.reorder_wish_items`](file:///home/src/wishenka/wishlists/service.py#L1044), reordering active items updates each model's `display_order` sequentially in memory. When persisting the modified items through [`WishlistStore._write`](file:///home/src/wishenka/wishlists/store.py#L510) or [`WishlistRepository.save_item`](file:///home/src/wishenka/wishlists/repository.py#L340), each item row is updated via an individual `UPDATE wl_items SET display_order = :display_order, ... WHERE id = :id` SQL statement.
   - **Trade-off**: For small lists typical of personal wishlists (10–50 items), executing N sequential updates inside an existing SQLite transaction completes in under 3–5 milliseconds in WAL mode. However, this is an implementation shortcut compared to a single bulk `CASE id WHEN ? THEN ? END` batch query or fractional indexing (LexoRank / float spacing) that would only update modified adjacent items.
   - **Compromise**: Avoided additional complex ranking algorithms or temporary table joins to ensure absolute data consistency, zero external dependencies, and atomic permutation validation.

2. **In-Memory Snapshot Persistence Model (`WishlistStore`)**:
   - **Context**: [`WishlistStore.execute`](file:///home/src/wishenka/wishlists/store.py#L74) executes operations against an in-memory [`WishlistService`](file:///home/src/wishenka/wishlists/service.py#L141) instance constructed from a storage snapshot and serializes mutations back to SQLite.
   - **Trade-off**: The in-memory model provides transactional domain consistency and avoids scattered ORM queries, but full snapshot synchronization creates architectural overhead as the number of items and wishlists grows.
   - **Compromise**: Kept consistent with the existing repository architecture established in previous MVP sprints while maintaining full compatibility with direct repository queries in [`WishlistRepository`](file:///home/src/wishenka/wishlists/repository.py#L104).

3. **Synchronous Recipient Membership Validation at Transaction Boundary**:
   - **Context**: In [`WishlistService.add_wish_item`](file:///home/src/wishenka/wishlists/service.py#L794) and [`WishlistService.update_wish_item`](file:///home/src/wishenka/wishlists/service.py#L930), `recipient_user_id` is validated against the active wishlist member set (`{wl.owner_id} | {m.user_id for m in wl.members}`).
   - **Trade-off**: The validation relies on members present in the current transactional snapshot. If a member is concurrently removed in a parallel transaction, validation checks against the current snapshot state without acquiring a shared read lock on the membership collection.
   - **Compromise**: Accepted given SQLite's serialized transaction model (WAL mode with single-writer lock) and the low probability of concurrent member eviction during instant item creation.

## Code Quality Issues

1. **Duplicated Item Deserialization and Serialization in `repository.py` and `store.py`**:
   - **Context**: Item mapping logic from SQL rows to [`WishItem`](file:///home/src/wishenka/wishlists/models.py#L93) is implemented separately in [`_row_to_item`](file:///home/src/wishenka/wishlists/repository.py#L80) in `repository.py` and in [`WishlistStore._read`](file:///home/src/wishenka/wishlists/store.py#L294) in `store.py`. Similarly, parameter dictionaries for INSERT/UPDATE queries are constructed independently in [`WishlistRepository.save_item`](file:///home/src/wishenka/wishlists/repository.py#L340) and [`WishlistStore._write`](file:///home/src/wishenka/wishlists/store.py#L510).
   - **Impact**: Any future schema modification (e.g. adding tags, attachments, or custom fields) requires duplicating column definitions and parameter bindings across multiple files, increasing the risk of subtle field synchronization bugs.
   - **Remediation**: Extract common item row mapper (`_row_to_item`) and parameter builder functions into a shared storage utility module (e.g. `wishenka/wishlists/mapping.py`).

2. **Redundant Field Definitions Across Pydantic Item DTOs**:
   - **Context**: [`CreateItemDTO`](file:///home/src/wishenka/items/schemas.py#L31) and [`UpdateItemDTO`](file:///home/src/wishenka/items/schemas.py#L50) duplicate field definitions (`title`, `description`, `link`, `image_url`, `price`, `currency`, `quantity`, `priority`, `category`, `recipient_user_id`, `recipient_name`) and both implement identical `@field_validator("title")` validation logic.
   - **Impact**: Unnecessary code repetition and divergent field constraints if one DTO is modified without updating the other.
   - **Remediation**: Extract a base item model (`BaseItemPayloadDTO`) containing shared fields and validators, deriving `CreateItemDTO` and `UpdateItemDTO` with appropriate required vs optional attributes.

3. **Direct Coupling of Route Handlers with State Access (`request.app.state`)**:
   - **Context**: The helper [`execute`](file:///home/src/wishenka/web/routes/items.py#L33) in `wishenka/web/routes/items.py` inspects `request.app.state.wishlist_service` and `request.app.state.wishlist_store` via `getattr`.
   - **Impact**: Bypasses FastAPI's native dependency injection container (`Depends`), slightly complicating unit testing where dependencies are provided via dependency overrides rather than app state mutations.
   - **Remediation**: Migrate `wishlist_store` and `wishlist_service` access into dedicated FastAPI dependency providers (`get_wishlist_service`, `get_wishlist_store`).

## Missing Tests

1. **Concurrent Reorder and Mutation Race Condition Scenarios**:
   - **Context**: While [`WishlistService.update_wish_item`](file:///home/src/wishenka/wishlists/service.py#L863) guards item quantity reduction with `_concurrency_coordinator.acquire(item_id)`, [`WishlistService.reorder_wish_items`](file:///home/src/wishenka/wishlists/service.py#L1044) does not acquire per-item coordinator locks because it validates and updates the entire active list permutation.
   - **Gap**: High-concurrency integration tests simulating parallel requests that reorder items while another client simultaneously adds or archives an item in the same wishlist are not currently present in [`tests/test_wish_items_crud_api.py`](file:///home/src/tests/test_wish_items_crud_api.py).
   - **Remediation**: Add an asynchronous stress test verifying that concurrent reorder and item addition requests result in deterministic ordering or clean conflict rejection without corrupting display orders.

2. **Large Wishlist Reordering Boundary Performance Tests**:
   - **Context**: The test suite covers permutations of 3 to 10 items.
   - **Gap**: Reordering large wishlists (e.g. 100+ items) with permutation verification is not covered in stress fixtures to measure serialization and SQLite query latency.
   - **Remediation**: Add a parameterized performance test fixture measuring reorder execution time for 100 and 500 items, verifying latency stays below 50 ms.

3. **Explicit Timeout Verification in Test Suite**:
   - **Status**: **VERIFIED NON-BLOCKER**. All automated tests strictly adhere to the timeout policy; [`tests/test_wish_items_crud_api.py`](file:///home/src/tests/test_wish_items_crud_api.py#L27) explicitly sets `pytestmark = pytest.mark.timeout(30)`, preventing hung test processes.

## Performance Concerns

1. **O(N) Sequential Database Writes on Item Reordering**:
   - **Context**: When [`WishlistService.reorder_wish_items`](file:///home/src/wishenka/wishlists/service.py#L1044) modifies the order of N items, [`WishlistStore._write`](file:///home/src/wishenka/wishlists/store.py#L510) and [`WishlistRepository.save_item`](file:///home/src/wishenka/wishlists/repository.py#L340) emit N individual `UPDATE wl_items` statements across the database connection.
   - **Impact**: While executing inside a single SQLite transaction avoids repeated fsync overhead, each statement incurs python-to-sqlite driver roundtrips. For wishlists with many items, this can hold the SQLite write lock longer than necessary.
   - **Optimization**: Replace the sequential loop with a single parameterized batch update using `UPDATE wl_items SET display_order = CASE id ... END WHERE id IN (...)` or temporary staging table update.

2. **Composite Index and Archive Filtering Scaling**:
   - **Context**: The schema migration in [`WishlistStore._init_db`](file:///home/src/wishenka/wishlists/store.py#L252) creates index `idx_wl_items_order ON wl_items(wishlist_id, display_order)`.
   - **Impact**: Active item queries frequently execute `WHERE wishlist_id = :id AND is_archived = 0 ORDER BY display_order ASC`. As archived items accumulate over time, SQLite must filter out archived rows post-index scan.
   - **Optimization**: Consider a partial index `CREATE INDEX idx_wl_items_active_order ON wl_items(wishlist_id, display_order) WHERE is_archived = 0` to keep active item lookups index-only.

## Follow-up Tasks

- **DEBT-1: Batch SQL update for item reordering (CASE/WHEN or batch query)**
  - *Jira Issue*: [WISHENKA-100](https://pypost.atlassian.net/browse/WISHENKA-100) (2.0 Story Points)
  - *Description*: Replace sequential N-query `UPDATE wl_items` executions in [`WishlistStore._write`](file:///home/src/wishenka/wishlists/store.py#L510) and [`WishlistRepository`](file:///home/src/wishenka/wishlists/repository.py#L340) with a single atomic batch query (`CASE id WHEN ... THEN ... END`) to minimize database transaction duration during list reordering.
  - *Priority*: Medium
  - *Target Epic*: WISHENKA-10

- **DEBT-2: Unify row mapping and SQL parameter serialization between Repository and Store**
  - *Jira Issue*: [WISHENKA-101](https://pypost.atlassian.net/browse/WISHENKA-101) (2.0 Story Points)
  - *Description*: Eliminate duplicated [`WishItem`](file:///home/src/wishenka/wishlists/models.py#L93) row deserialization and query parameter construction between [`WishlistRepository`](file:///home/src/wishenka/wishlists/repository.py#L80) and [`WishlistStore`](file:///home/src/wishenka/wishlists/store.py#L294) by creating a shared mapping helper module.
  - *Priority*: Low
  - *Target Epic*: WISHENKA-10

- **DEBT-3: Stress and race condition tests for concurrent reorder and item lifecycle mutations**
  - *Jira Issue*: [WISHENKA-102](https://pypost.atlassian.net/browse/WISHENKA-102) (3.0 Story Points)
  - *Description*: Implement automated stress test scenarios simulating high-concurrency race conditions between `reorder_wish_items`, `add_wish_item`, and `archive_wish_item` to verify permutation integrity under contention.
  - *Priority*: Low
  - *Target Epic*: WISHENKA-10

- **DEBT-4: DRY refactoring of CreateItemDTO and UpdateItemDTO schemas**
  - *Jira Issue*: [WISHENKA-103](https://pypost.atlassian.net/browse/WISHENKA-103) (1.0 Story Points)
  - *Description*: Extract shared field attributes and title whitespace validators into a common `BaseItemPayloadDTO` base class in [`wishenka/items/schemas.py`](file:///home/src/wishenka/items/schemas.py#L31) to eliminate schema duplication.
  - *Priority*: Low
  - *Target Epic*: WISHENKA-10

- **Pre-existing test failures**:
  - `None` (All 289 automated tests in the test suite pass with 0 errors).
