# WISHENKA-44: Technical Debt Analysis

## Shortcuts Taken

1. **Dual AsyncEngine Instances for SQLite Connection Management**:
   - `UserStore` and `WishlistStore` independently create and configure separate SQLAlchemy
     `create_async_engine` pools using `database_url`.
   - In FastAPI lifespan startup (`wishenka/web/app.py`), both stores initialize schemas and
     dispose connection pools separately. While functional in SQLite WAL mode, sharing an engine
     or database session manager is preferable for resource management and connection pooling.

2. **Absence of Foreign Key Constraints to `users(id)` in Wishlist Tables**:
   - Domain tables (`wl_favorites`, `wl_view_history`, and `wl_members.payload->user_id`) store
     user IDs without foreign key references to `users(id)`.
   - Because `users` was introduced after wishlist tables, tables were not retrofitted with
     `REFERENCES users(id) ON DELETE CASCADE` to avoid breaking existing migrations or seed data.

3. **Preliminary SELECT Query to Distinguish Insert from Update for Logging**:
   - In `UserStore.upsert_user`, a `SELECT id FROM users WHERE telegram_id = :telegram_id` query
     is executed immediately before the `INSERT ... ON CONFLICT DO UPDATE` statement solely to
     determine whether to log `user_created` or `user_updated`.
   - While SQLite executes this query rapidly, it doubles round-trips to the database on login.

4. **StarletteDeprecationWarning with TestClient in Auth Test Suite**:
   - Running pytest displays `StarletteDeprecationWarning: Using 'httpx' with 'starlette.testclient'
     is deprecated; install 'httpx2' instead`.
   - The test suite should eventually standardize on `httpx.AsyncClient(transport=ASGITransport)`.

## Code Quality Issues

1. **Independent Store Lifecycle in FastAPI Application State**:
   - `wishenka/web/app.py` attaches `user_store` and `wishlist_store` separately onto `app.state`.
   - A consolidated storage or unit-of-work container would provide cleaner dependency injection
     and simpler lifecycle management during tests and application shutdown.

2. **JSON-Extracted User Identity in Wishlist Membership Table**:
   - In `wl_members`, member identity is extracted via `json_extract(payload, '$.user_id')`.
   - Migrating `user_id` to a first-class typed column in `wl_members` would permit direct SQL
     joins, strict foreign key constraints, and standard foreign index semantics.

3. **Lack of Repository Protocol / Abstract Base Class**:
   - `UserStore` is a concrete class injected directly via `Depends(get_user_store)`.
   - Defining a typing `Protocol` or abstract interface for `UserStore` would facilitate mocking
     and support alternative persistence engines (e.g., PostgreSQL or Redis) in future epics.

## Missing Tests

1. **High-Concurrency Stress Suite for Concurrent Login Upserts**:
   - Existing tests verify single-user updates and multi-attribute changes sequentially.
   - A high-contention test running 50+ concurrent requests for the same Telegram ID in parallel
     is needed to stress test SQLite `busy_timeout` and WAL locking behavior under peak loads.

2. **Unicode and Special Character Edge Cases in Telegram Profile**:
   - Unit tests cover ASCII and Cyrillic names.
   - Explicit tests for 4-byte UTF-8 emojis, RTL text, maximum-length names, and special symbols
     in `first_name`, `last_name`, and `username` would ensure edge-case robustness.

3. **Database Migration and Referential Integrity Integration Tests**:
   - When foreign keys are added linking `wl_favorites` to `users(id)`, migration scripts
     must be verified against existing databases containing legacy data.

> [!NOTE]
> All existing tests in `tests/test_auth_user_store.py` and
> `tests/test_auth_user_store_observability.py` declare explicit module timeouts via
> `pytestmark = pytest.mark.timeout(10)`, satisfying `do-testing` requirements.

## Performance Concerns

1. **Extra SELECT Query Round-Trip on Every Login**:
   - The pre-upsert `SELECT id FROM users WHERE telegram_id = :telegram_id` adds latency to
     the authentication endpoint. Under thousands of concurrent logins, this adds unnecessary
     read load.

2. **Direct Uncached Lookups for Frequently Accessed User Profiles**:
   - While session tokens cache `user_id` and `first_name`, future features requiring full user
     details (`get_by_id`, `get_by_telegram_id`) query SQLite directly on each call without an
     in-memory read-through cache.

3. **Dual Connection Pools against SQLite Database File**:
   - Multiple `AsyncEngine` instances create separate connection pools competing for SQLite file
     locks. Consolidating into a single engine reduces pool management overhead.

## Follow-up Tasks

- **DEBT-W44-1**: Unification of Database Initialization and Shared Connection Manager
  - **Severity / Impact**: Medium
  - **Recommended Jira Priority**: Medium
  - **Description**: Both `UserStore` and `WishlistStore` create separate `AsyncEngine` instances
    against `database_url`. In `wishenka/web/app.py`, each store initializes and disposes
    independently. Consolidating database lifecycle and connection management into a shared
    engine or provider reduces resource overhead and simplifies transaction coordination.
  - **Suggested Remediation**: Implement a centralized `DatabaseManager` or shared engine
    provider in `wishenka.storage` that provides single-engine access to both `UserStore` and
    `WishlistStore`.
  - **Acceptance Criteria**:
    1. A single `AsyncEngine` instance is shared across all repository stores.
    2. FastAPI lifespan startup and shutdown manage the engine centrally.
    3. All unit and integration tests execute successfully without connection leaks.
  - **Story Points**: 3
  - **Jira Ticket**: [WISHENKA-74](https://pypost.atlassian.net/browse/WISHENKA-74)

- **DEBT-W44-2**: Foreign Key Constraints Linking Wishlist Tables to users(id)
  - **Severity / Impact**: Medium
  - **Recommended Jira Priority**: Medium
  - **Description**: Wishlist tables (`wl_favorites`, `wl_view_history`, and `wl_members`) store
    user IDs without database-enforced foreign key constraints to `users(id)`. This prevents
    referential integrity verification and automated cascade deletion when users are purged.
  - **Suggested Remediation**: Add foreign key constraints
    (`REFERENCES users(id) ON DELETE CASCADE`) to `wl_favorites` and `wl_view_history`.
    In `wl_members`, extract `user_id` from JSON payload into a dedicated column with
    foreign key reference.
  - **Acceptance Criteria**:
    1. `wl_favorites.user_id` and `wl_view_history.user_id` reference `users(id)`
       with `ON DELETE CASCADE`.
    2. Inserting invalid `user_id` into favorites or view history fails referential integrity
       checks.
    3. Existing table schemas and tests are migrated cleanly.
  - **Story Points**: 3
  - **Jira Ticket**: [WISHENKA-75](https://pypost.atlassian.net/browse/WISHENKA-75)

- **DEBT-W44-3**: User Profile Retrieval and Read-Through Cache Optimization
  - **Severity / Impact**: Low
  - **Recommended Jira Priority**: Low
  - **Description**: Profile lookups (`UserStore.get_by_id` and `UserStore.get_by_telegram_id`)
    currently execute direct SQL queries against SQLite for each invocation. If future user
    surfaces or collaboration widgets frequently query user profiles, repeated disk reads could
    introduce latency spikes.
  - **Suggested Remediation**: Implement an in-memory read-through cache (e.g., using `cachetools`
    or an LRU cache) for user records with invalidation on `upsert_user`.
  - **Acceptance Criteria**:
    1. Repeated queries for the same user record hit in-memory cache without SQL queries.
    2. `upsert_user` invalidates or updates the cached entry immediately.
    3. Cache size is bounded and enforces TTL expiration to avoid unbounded memory growth.
  - **Story Points**: 3
  - **Jira Ticket**: [WISHENKA-76](https://pypost.atlassian.net/browse/WISHENKA-76)

- **DEBT-W44-4**: Eliminate Extra SELECT Query in UserStore.upsert_user for Logging
  - **Severity / Impact**: Low
  - **Recommended Jira Priority**: Low
  - **Description**: In `UserStore.upsert_user`, a preliminary SELECT query is issued prior to
    upsert solely to decide whether to emit a `user_created` or `user_updated` log event.
    Eliminating this query will reduce authentication latency and database round-trips.
  - **Suggested Remediation**: Determine new user creation status by comparing `created_at` with
    `updated_at`, using a conditional RETURNING expression, or inspecting SQLite change count.
  - **Acceptance Criteria**:
    1. `UserStore.upsert_user` executes in a single SQL query.
    2. `user_created` and `user_updated` events are still accurately emitted.
    3. All observability and store tests continue to pass.
  - **Story Points**: 1
  - **Jira Ticket**: [WISHENKA-77](https://pypost.atlassian.net/browse/WISHENKA-77)

- **DEBT-W44-5**: High-Concurrency Stress Test Suite for User Authentication Upsert
  - **Severity / Impact**: Low
  - **Recommended Jira Priority**: Low
  - **Description**: Although SQLite WAL mode and busy timeout are configured, there is no stress
    test verifying that 50+ concurrent requests authenticating the same Telegram user complete
    without lock contention failures or duplicate records.
  - **Suggested Remediation**: Add a concurrency stress test in `tests/test_auth_user_store.py`
    using `asyncio.gather` with 50 parallel login coroutines for the same user.
  - **Acceptance Criteria**:
    1. Test executes 50 concurrent login attempts for the same user identity.
    2. Exactly one database record is created and no lock timeout errors are raised.
    3. Test satisfies explicit timeout constraints per `do-testing`.
  - **Story Points**: 2
  - **Jira Ticket**: [WISHENKA-78](https://pypost.atlassian.net/browse/WISHENKA-78)

## Pre-Existing Test Failures

None. All automated tests in the test suite pass with 0 errors.
