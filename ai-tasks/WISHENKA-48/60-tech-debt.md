# WISHENKA-48: Technical Debt Analysis

## Shortcuts Taken

1. **In-Memory Service Snapshotting in `WishlistStore.execute`**:
   - To maintain zero-regression backwards compatibility with existing route handlers and tests,
     `WishlistStore.execute` reads existing records into a transient `WishlistService` instance,
     runs the caller-supplied domain operation, and persists modified rows using diff snapshots.
   - While destructive full-table truncations (`DELETE FROM <table>`) were eliminated, snapshotting
     loads active entities into memory. Web routes should migrate to direct repository queries.

2. **Inline DDL Schema Initialization**:
   - `WishlistStore._initialize` executes raw SQLite `CREATE TABLE IF NOT EXISTS` DDL statements
     and checks `PRAGMA table_info(wl_lists)` to drop legacy JSON payload tables.
   - While robust for automated testing and initial bootstrapping, schema evolution should be
     managed by versioned migration scripts rather than runtime DDL checks.

3. **Direct `AsyncConnection` Usage Instead of `AsyncSession` Unit of Work**:
   - `WishlistStore` and `WishlistRepository` interact with the SQLite engine via `AsyncConnection`
     and raw `text()` SQL queries.
   - Utilizing SQLAlchemy's `AsyncSession` and `async_sessionmaker` would provide standardized
     unit-of-work lifecycle handling, identity mapping, and declarative ORM integration.

4. **Separate AsyncEngine Instances Across Stores**:
   - `WishlistStore` and `UserStore` construct independent `create_async_engine` pools against
     the configured SQLite database URL.
   - Both engines run with SQLite WAL mode, but consolidating connection management into a
     shared provider avoids redundant pool allocations and file descriptor usage.

## Code Quality Issues

1. **Dual Representation Between Domain Dataclasses and Relational Mappings**:
   - Domain models (`Wishlist`, `WishItem`, `Reservation`) are defined as standard dataclasses,
     while `wishenka/wishlists/db_models.py` defines declarative ORM row models
     (`WishlistRow`, etc.).
   - Converting between SQL rows and domain models is handled manually through helper functions in
     `repository.py` and `store.py`. Establishing unified mappings or automated serializers will
     reduce boilerplate.

2. **Absence of Repository Protocol / Abstract Interface**:
   - `WishlistRepository` is a concrete class coupled directly to SQLite `AsyncConnection`.
   - Defining a `Protocol` interface (`WishlistRepositoryProtocol`) will facilitate unit test
     mocking and support future storage backends (e.g., PostgreSQL for high-scale deployments).

3. **Legacy Snapshot Diffing Logic in `WishlistStore`**:
   - `WishlistStore._write` tracks entity ID sets before and after mutation to issue granular
     `UPDATE`, `INSERT`, and `DELETE` queries.
   - Once web routes interact directly with `WishlistRepository`, the snapshot diffing engine
     can be safely retired.

## Missing Tests

1. **High-Concurrency Contention Stress Suite for Item Reservations**:
   - Existing tests verify reservation isolation, transactional rollbacks, and atomic counters.
   - A high-contention test running 50+ concurrent reservation attempts against a single-quantity
     item under parallel `asyncio.gather` execution will further validate SQLite `busy_timeout`
     and overbooking protection.

2. **Schema Upgrade Verification from Legacy Pre-Normalized Databases**:
   - `WishlistStore._initialize` automatically detects legacy payload columns and drops legacy
     tables.
   - Comprehensive migration tests validating data preservation when migrating historical JSON
     payloads into relational rows should be added when Alembic migrations are introduced.

> [!NOTE]
> All existing tests in `tests/test_wishlists_sqlite_repo.py` and domain test suites declare
> explicit module timeouts via `pytestmark = pytest.mark.timeout(10)`, satisfying `do-testing`
> requirements.

## Performance Concerns

1. **In-Memory Graph Construction Overhead on `WishlistStore.execute`**:
   - Loading all wishlists into `WishlistService` during `execute()` incurs memory allocation and
     deserialization overhead on write operations. Direct repository calls eliminate this burden.

2. **Token Uniqueness Retry Round-Trips**:
   - Generating capability tokens executes database queries to verify uniqueness against existing
     records. Caching active tokens or relying on cryptographic collision resistance can reduce
     unnecessary round-trips.

3. **Independent Connection Pools Competing for SQLite Locks**:
   - Independent `AsyncEngine` instances in `WishlistStore` and `UserStore` maintain separate
     connection pools. Merging them into a shared engine manager ensures optimal WAL coordination.

## Follow-up Tasks

- **DEBT-W48-1**: Alembic Migration Engine and Version Tracking for Relational Schema
  - **Severity / Impact**: Medium
  - **Recommended Jira Priority**: Medium
  - **Description**: Relational schemas in `WishlistStore._initialize` and `UserStore.initialize`
    are created using raw DDL statements (`CREATE TABLE IF NOT EXISTS`) and programmatic column
    checks (`PRAGMA table_info`). This ad-hoc approach lacks linear revision history, automated
    upgrade/downgrade paths, schema diffing, and safe production migration mechanics. As features
    evolve, managing relational schema changes requires an automated migration tool.
  - **Suggested Remediation**: Integrate Alembic with an async migration runner (`env.py`
    configured with SQLAlchemy 2.0 async engine and declarative models). Generate baseline
    migration revisions for existing tables (`wl_lists`, `wl_members`, `wl_items`,
    `wl_reservations`, `wl_favorites`, `wl_view_history`, `wl_tokens`, `wl_invite_tokens`,
    `wl_counters`, `users`), and deprecate inline DDL creation inside store initializers.
  - **Acceptance Criteria**:
    1. Alembic configuration and migration environment are established in repository root.
    2. Initial baseline migration creates all normalized tables and indexes.
    3. Automatic migrations run cleanly on startup or via CLI command (`alembic upgrade head`).
    4. Inline raw DDL execution in `WishlistStore` and `UserStore` is removed.
  - **Story Points**: 3
  - **Jira Ticket**: [WISHENKA-79](https://pypost.atlassian.net/browse/WISHENKA-79)

- **DEBT-W48-2**: Direct Repository Dependency Injection in Web Routes
  - **Severity / Impact**: High
  - **Recommended Jira Priority**: High
  - **Description**: Existing FastAPI route handlers in `wishenka/web/routes/` interact with
    storage through `WishlistStore.execute(op)`. While this adapter eliminated destructive table
    wipes, `execute()` still reads the full active dataset into a transient in-memory
    `WishlistService` and reconciles state via diff snapshots. Directly injecting
    `WishlistRepository` into web routes will allow granular single-row queries and updates
    without in-memory service deserialization.
  - **Suggested Remediation**: Introduce FastAPI dependency providers for `WishlistRepository`
    and refactor route endpoints to execute granular queries directly via repository methods.
    Retain domain validation logic within specialized domain use cases or service methods.
  - **Acceptance Criteria**:
    1. FastAPI route handlers receive `WishlistRepository` via `Depends(get_wishlist_repository)`.
    2. Wishlist item updates, reservation creations, and view operations invoke targeted
       repository methods without executing full in-memory dataset diffing.
    3. Deprecate `WishlistStore.execute()` for web routes once all endpoints are migrated.
    4. All existing API integration tests continue passing with verified performance gains.
  - **Story Points**: 5
  - **Jira Ticket**: [WISHENKA-80](https://pypost.atlassian.net/browse/WISHENKA-80)

- **DEBT-W48-3**: Connection Pool Session Management and AsyncSession Factory
  - **Severity / Impact**: Medium
  - **Recommended Jira Priority**: Medium
  - **Description**: `WishlistStore` and `WishlistRepository` currently operate directly on
    `AsyncConnection` instances obtained from `engine.begin()`. This bypasses SQLAlchemy's standard
    `AsyncSession` lifecycle and `async_sessionmaker` unit-of-work patterns. Standardizing on
    `AsyncSession` across `WishlistRepository` and `UserStore` will provide unified transaction
    boundaries, identity mapping, and clean contextual cleanup.
  - **Suggested Remediation**: Configure a shared `async_sessionmaker[AsyncSession]` attached to
    the central database engine. Refactor `WishlistRepository` and other stores to accept an
    `AsyncSession` instance, utilizing `async with session.begin():` for transaction management.
  - **Acceptance Criteria**:
    1. Centralized database configuration provides an `async_sessionmaker[AsyncSession]` factory.
    2. `WishlistRepository` accepts and executes operations using `AsyncSession`.
    3. FastAPI request dependency injects scoped async sessions with automatic commit on success
       and rollback on exception.
    4. All unit and repository integration tests verify clean session closure without connection
     leaks.
  - **Story Points**: 3
  - **Jira Ticket**: [WISHENKA-81](https://pypost.atlassian.net/browse/WISHENKA-81)

- **DEBT-W48-4**: High-Concurrency Contention Stress Test Suite for Reservations
  - **Severity / Impact**: Low
  - **Recommended Jira Priority**: Low
  - **Description**: While `tests/test_wishlists_sqlite_repo.py` verifies rollback and basic
    concurrency, a high-contention stress test with 50+ concurrent gifters reserving the last
    remaining quantity of an item is needed to stress-test SQLite `busy_timeout` and reservation
    limits under extreme load.
  - **Suggested Remediation**: Add a dedicated concurrency stress test in
    `tests/test_wishlists_sqlite_repo.py` using `asyncio.gather` with 50 parallel reservation
    requests for a quantity-1 wish item.
  - **Acceptance Criteria**:
    1. Test executes 50 concurrent reservation requests against a single item with quantity 1.
    2. Exactly one reservation succeeds and 49 receive sold-out / overbooking rejection.
    3. Test satisfies explicit timeout constraints per `do-testing`.
  - **Story Points**: 2
  - **Jira Ticket**: [WISHENKA-82](https://pypost.atlassian.net/browse/WISHENKA-82)

## Pre-Existing Test Failures

None. All automated tests in the test suite pass with 0 errors.
