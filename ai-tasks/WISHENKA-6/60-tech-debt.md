# WISHENKA-6: Technical Debt Analysis

## Shortcuts Taken

1. **In-Memory Volatile Storage in `WishlistService`**:
   - `WishlistService` currently stores wishlists, members, items, and reservations in in-memory Python dictionaries (`_wishlists`, `_items`, `_reservations`) with integer auto-increment counters (`_next_wishlist_id`, etc.).
   - This was done deliberately to decouple domain logic, RBAC/ABAC authorization, and Surprise Invariant zero-leak projections from the database schema implementation, enabling high-speed unit test execution without database setup overhead.
   - Data is non-persistent and will reset across process restarts or ASGI worker boundaries.

2. **Hardcoded Default Expiration Duration**:
   - Default invite token time-to-live is set to 7 days (`timedelta(days=7)`) directly in `WishlistService.create_wishlist` and `regenerate_tokens` when not explicitly specified, rather than being driven by centralized application configuration (`Settings`).

3. **Absence of Transactional Rollback Boundaries**:
   - In-memory mutations modify model collections directly (e.g. updating reservation status, appending to member lists) without atomic rollback capabilities if downstream failures occur.

## Code Quality Issues

1. **Coupling of Domain Logic and Storage Operations**:
   - `WishlistService` currently combines state management/indexing with domain authorization and DTO projection logic.
   - When database persistence is introduced, storage operations should be extracted into a dedicated Repository pattern / Unit of Work layer (`WishlistRepository`, `ItemRepository`, `ReservationRepository`), leaving `WishlistService` focused purely on business orchestration and policy enforcement.

2. **In-Memory Mutable Entity Modification**:
   - Lists of members and items are maintained as mutable Python lists inside `Wishlist` models (`wishlist.members.append(...)`), which creates potential side effects when referenced concurrently in memory.

3. **Direct Entity Filtering in Memory**:
   - Token lookup and reservation counting rely on generator expressions and list comprehensions (e.g., `[r for r in self._reservations.values() if r.item_id == item.id and r.status == ReservationStatus.ACTIVE]`) rather than optimized relational queries.

## Missing Tests

1. **High-Concurrency Race Condition Tests**:
   - Concurrent reservation attempts for limited-quantity items (e.g., multiple gifters attempting to claim the final remaining unit of a wish simultaneously) are not tested under high-concurrency async load or thread pools.

2. **Persistent Database Integration & Transaction Rollback Tests**:
   - Tests validating persistence, constraints, foreign keys, and atomic rollbacks with SQLite WAL (`aiosqlite` + SQLAlchemy async session) are deferred until the database schema and repository integration tasks.

3. **HTTP API Route & HTMX View Tests**:
   - Endpoints exposing wishlist CRUD, member invitations, and token regeneration via FastAPI routes and HTMX partials are not included in this domain layer task and require end-to-end HTTP tests in subsequent user-facing tasks.

4. **Token Collision and Brute-Force Rate Limiting Tests**:
   - While tokens have 128-bit/192-bit cryptographic entropy, rate limiting for token lookup and public link access has not yet been implemented or tested.

> [!NOTE]
> All pytest test suites in the repository strictly include timeout markers (`@pytest.mark.timeout(...)`), satisfying the `do-testing` contract without any blocker violations.

## Performance Concerns

1. **Linear Search Over Dictionaries ($O(N)$ lookup)**:
   - Lookup by `public_token` and `invite_token` iterates over all wishlists in memory (`next((w for w in ...))` instead of constant-time indexing. In production with a relational database, this must be backed by unique B-tree indexes (`UNIQUE INDEX idx_wishlists_public_token`).

2. **Unindexed Aggregation of Reservations**:
   - Calculating available gift quantities performs linear scans over the `_reservations` dictionary. Relational database schema should leverage index-backed queries or aggregated subqueries to avoid performance degradation as reservation volume grows.

3. **Memory Footprint in ASGI Multi-Worker Deployments**:
   - In-memory state cannot be shared across multiple Uvicorn worker processes. Scaling beyond a single worker requires database persistence.

## Follow-up Tasks

1. **[WISHENKA-48](https://pypost.atlassian.net/browse/WISHENKA-48): База данных: схема SQLite WAL и SQLAlchemy async репозитории для вишлистов** (5.0 SP):
   - Implement SQLAlchemy models, Alembic migrations, and async repository implementations for `wishlists`, `wishlist_members`, `wish_items`, and `reservations` in SQLite WAL.

2. **[WISHENKA-49](https://pypost.atlassian.net/browse/WISHENKA-49): Блокировки и изоляция транзакций при бронировании подарков** (3.0 SP):
   - Implement database-level transaction locking (or optimistic concurrency checks) during gift reservations to prevent overselling items under race conditions.

3. **[WISHENKA-50](https://pypost.atlassian.net/browse/WISHENKA-50): Конфигурируемый TTL токенов и фоновая очистка истекших приглашений** (3.0 SP):
   - Move invite token TTL defaults to `wishenka.core.config.Settings`.
   - Implement background task to periodically clean up expired invite tokens and purge soft-deleted wishlists beyond the retention period.

4. **[WISHENKA-51](https://pypost.atlassian.net/browse/WISHENKA-51): Эндпоинты FastAPI и HTMX-представления для вишлистов и шеринга** (5.0 SP):
   - Build REST/HTMX routes connecting `WishlistService` with Telegram Mini App web views and collaborative invite links.
