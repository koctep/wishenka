# WISHENKA-17: Technical Debt Analysis

## Shortcuts Taken

### 1. In-Memory Keyed Mutex Coordinator Limited to Single Process
- **Context**: `ItemConcurrencyCoordinator` in `wishenka/wishlists/concurrency.py` coordinates per-item critical sections using in-memory `asyncio.Lock` instances mapped in a dictionary (`self._locks: dict[int, asyncio.Lock]`).
- **Trade-off / Limitation**: Concurrency synchronization is isolated strictly to a single Python event loop within a single OS process. In production setups using multiple Uvicorn worker processes (`uvicorn --workers N`), containerized auto-scaling pods, or load balancers, locks are not shared across processes. A concurrent race condition across separate worker processes could bypass in-memory mutual exclusion and cause inventory overbooking.
- **Compromise**: Avoided introducing external distributed coordination systems (e.g., Redis Redlock, Consul, or database transaction locks) during initial core domain model development.

### 2. Ephemeral In-Memory Storage in `WishlistService`
- **Context**: State across wishlists, items, and reservations is retained inside Python dictionaries (`self._wishlists`, `self._items`, `self._reservations`).
- **Trade-off / Limitation**: Data is volatile and will be lost on process restart or failure. While designed as an intermediate in-memory domain repository pattern to allow rapid feature iteration, production deployment requires persistent SQLite WAL transactions.
- **Compromise**: Kept domain logic clean, self-contained, and isolated from database schema migrations while repository patterns are finalized in later sprint tasks.

### 3. Lack of Transactional Outbox for Gifter Notifications on Item Lifecycle Changes
- **Context**: When an item with active or purchased reservations is archived (`is_archived = True`), deleted, or fulfilled by the recipient (`record_item_fulfillment`), gifters who held reservations are not automatically notified via Telegram.
- **Trade-off / Limitation**: Without an event-driven notification queue (Transactional Outbox pattern), gifters might purchase or prepare a gift that the recipient has already fulfilled elsewhere or removed from their list, without receiving any proactive alert in Telegram.
- **Compromise**: Postponed asynchronous message queuing and Telegram notification dispatch to dedicated notification integration stories.

### 4. Absence of Client Idempotency Keys on Reservation Mutations
- **Context**: Reservation endpoints (`create_reservation`, `mark_reservation_purchased`, `cancel_reservation`, `update_reservation_quantity`) do not accept or validate an `Idempotency-Key` HTTP header.
- **Trade-off / Limitation**: Unstable mobile connections inside Telegram Mini Apps frequently trigger automatic client retries or accidental double-taps by users. Retrying `create_reservation` without idempotency protection will fail with `InsufficientQuantityError` (if remaining quantity was exhausted by the first attempt) rather than returning the existing reservation entity idempotently.
- **Compromise**: Relied on standard validation error handling rather than an idempotency middleware/cache layer for the initial baseline.

## Code Quality Issues

### 1. Monolithic Service Layer in `WishlistService`
- **Context**: `wishenka/wishlists/service.py` has grown to over 1,600 lines, encapsulating wishlist creation, token lifecycle, RBAC access policies, collaborator management, item CRUD, item fulfillment, and reservation workflows.
- **Improvement**: As the domain grows, reservation operations should be decomposed into a dedicated `ReservationService` or encapsulated in an aggregate root entity pattern, keeping `WishlistService` focused on wishlist container lifecycle.

### 2. Indefinite Lock Retention in `ItemConcurrencyCoordinator`
- **Context**: In `ItemConcurrencyCoordinator`, once an `asyncio.Lock` is allocated for an `item_id`, it remains stored in `self._locks` indefinitely.
- **Improvement**: Items that are archived, deleted, or have zero active reservations never have their lock objects garbage-collected, creating a slow memory leak over prolonged operational lifetimes. The coordinator needs an eviction policy (e.g. `weakref.WeakValueDictionary` or an LRU / idle lock pruning mechanism).

### 3. Scattered Domain Logic and Magic Constants
- **Context**: Configuration items such as default currency codes (`"RUB"`), default invite token lifetimes (`timedelta(days=7)`), and hardcoded reservation bounds are directly embedded across domain models and service functions.
- **Improvement**: Extract domain constants and defaults into centralized application settings (`wishenka.config.Settings`) and domain value objects.

### 4. Direct Logging Instead of Strongly-Typed Domain Event Bus
- **Context**: Domain mutations log directly to `logger.info(..., extra={"event": ...})`.
- **Improvement**: Implementing a lightweight Domain Event Bus (`ItemReservedEvent`, `ReservationPurchasedEvent`, `ReservationCancelledEvent`) would decouple business logic from observability, metrics collection, and downstream notification dispatchers.

## Missing Tests

### 1. High-Scale Concurrency Stress Suite (>100–500 Workers)
- **Context**: Existing concurrency tests in `tests/test_reservations_surprise_invariant.py` validate safety across small batches (2–10 parallel coroutines).
- **Missing Scenario**: Massive high-contention stress tests with 100+ concurrent coroutines competing for the final item unit, simultaneous cancellations mixed with reservation attempts, and high-frequency quantity adjustments under heavy simulated latency.

### 2. Multi-Process and Distributed Lock Concurrency Tests
- **Context**: Current automated tests run strictly inside a single Python test process.
- **Missing Scenario**: Multi-worker tests simulating concurrent processes (e.g. `multiprocessing` or multi-worker uvicorn instances) to verify database-level serializable isolation and distributed locking once SQLite persistence is plugged in.

### 3. Clock Skew and Drift Edge Cases
- **Context**: Expiration and timestamps use `datetime.now(UTC)`.
- **Missing Scenario**: Tests verifying graceful behavior when system clock experiences sudden forward/backward jumps (NTP clock drift, leap seconds) during reservation state transitions and token validations.

### 4. Property-Based and Fuzzing Invariant Verification (Hypothesis)
- **Context**: All test cases use deterministic fixed fixture data.
- **Missing Scenario**: Property-based tests (using `hypothesis`) executing random valid permutations of reservations, purchases, reverts, cancellations, fulfillments, and quantity reductions to fuzz test invariant integrity:
  `reserved_quantity + fulfilled_quantity <= desired_quantity` and `available_quantity >= 0`.

## Performance Concerns

### 1. Monotonic Lock Memory Growth in `ItemConcurrencyCoordinator`
- **Impact**: Each unique item accessed creates an entry in `self._locks`. Over prolonged service execution with hundreds of thousands of items, `ItemConcurrencyCoordinator._locks` will grow monotonically without cleanup, slowly increasing memory footprint.
- **Remediation**: Use `weakref.WeakValueDictionary` or periodic cleanup of unreferenced locks when `lock.locked()` is False.

### 2. Linear O(N) Scans in In-Memory Reservation Queries
- **Impact**: `get_user_reservations` and `get_user_reservations_summary` iterate sequentially over `self._reservations.values()` (`for res in self._reservations.values():`).
- **Scale Risk**: As total reservations across all users grow, query latency will degrade linearly (O(N) search time).
- **Remediation**: Maintain a secondary lookup index (e.g. `self._user_reservations: dict[int, set[int]]`) or rely on a database index on `reservations.user_id` when transitioning to SQLite WAL.

### 3. Master Lock Contention in Concurrency Coordinator
- **Impact**: All reservation mutations pass through `async with self._master_lock:` to retrieve or initialize the per-item lock.
- **Scale Risk**: Under high global request throughput across many distinct items, acquiring the master lock introduces a point of contention, momentarily serializing unrelated item operations.
- **Remediation**: Replace master lock with lock-free atomic dictionary access (`self._locks.setdefault(item_id, asyncio.Lock())`) or shard locks by `hash(item_id) % N`.

## Follow-up Tasks

- **DEBT-1: SQLite WAL transactional concurrency & distributed locking engine**
  - *Jira Issue*: [WISHENKA-57](https://pypost.atlassian.net/browse/WISHENKA-57) (5.0 Story Points)
  - *Target Epic*: WISHENKA-16
  - *Priority*: High
  - *Estimated Points*: 5.0
  - *Description*: Replace in-memory `ItemConcurrencyCoordinator` and ephemeral dictionaries with persistent SQLite WAL transactional isolation (`BEGIN IMMEDIATE` / write lock serializability) or distributed locks to safely support multi-worker Uvicorn setups without overbooking risks.

- **DEBT-2: Lock dictionary garbage collection & memory eviction in concurrency coordinator**
  - *Jira Issue*: [WISHENKA-58](https://pypost.atlassian.net/browse/WISHENKA-58) (2.0 Story Points)
  - *Target Epic*: WISHENKA-16
  - *Priority*: Medium
  - *Estimated Points*: 2.0
  - *Description*: Implement weak-reference management (`weakref.WeakValueDictionary`) or idle lock pruning for `ItemConcurrencyCoordinator._locks` to prevent unbounded memory growth on long-running instances.

- **DEBT-3: Secondary user-reservation indexes to eliminate O(N) scan overhead**
  - *Jira Issue*: [WISHENKA-59](https://pypost.atlassian.net/browse/WISHENKA-59) (2.0 Story Points)
  - *Target Epic*: WISHENKA-16
  - *Priority*: Medium
  - *Estimated Points*: 2.0
  - *Description*: Introduce index mapping `user_id -> set[reservation_id]` in domain repositories and SQL indexes on `reservations(user_id, status)` to ensure sub-millisecond retrieval in "My Reservations" cabinet.

- **DEBT-4: Transactional outbox & notification dispatcher for gift lifecycle events**
  - *Jira Issue*: [WISHENKA-60](https://pypost.atlassian.net/browse/WISHENKA-60) (3.0 Story Points)
  - *Target Epic*: WISHENKA-16
  - *Priority*: Medium
  - *Estimated Points*: 3.0
  - *Description*: Implement a transactional outbox queue to notify gifters via Telegram bot when reserved items are fulfilled, edited, or archived by wishlist owners, preventing orphaned reservations.

- **DEBT-5: Client idempotency keys for reservation mutations**
  - *Jira Issue*: [WISHENKA-61](https://pypost.atlassian.net/browse/WISHENKA-61) (3.0 Story Points)
  - *Target Epic*: WISHENKA-16
  - *Priority*: Low
  - *Estimated Points*: 3.0
  - *Description*: Add `Idempotency-Key` header support to reservation mutating endpoints (`create_reservation`, `mark_reservation_purchased`, `cancel_reservation`, `update_reservation_quantity`) to safely handle mobile network retries and UI double-clicks without raising false concurrency errors.

- **DEBT-6: High-scale concurrency stress suite and property-based invariant fuzzing**
  - *Jira Issue*: [WISHENKA-62](https://pypost.atlassian.net/browse/WISHENKA-62) (3.0 Story Points)
  - *Target Epic*: WISHENKA-16
  - *Priority*: Low
  - *Estimated Points*: 3.0
  - *Description*: Create automated stress test fixtures simulating >100 concurrent workers and Hypothesis property-based fuzz tests to mathematically verify surprise invariants and inventory non-negativity under extreme contention.

- **Pre-existing test failures**:
  - `None` (All 92 automated tests in the test suite pass with 0 errors).
