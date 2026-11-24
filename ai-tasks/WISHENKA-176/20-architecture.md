# WISHENKA-176: Batched Cabinet Loading and Non-Blocking Consistent Reads

## Research

### Current Cabinet Read Path (`WishlistStore` & `WishlistRepository`)

1. **Web Routes (`wishenka/web/routes/reservations_ui.py` & `wishenka/web/routes/reservations.py`):**
   - `reservations_ui.py` serves read-only cabinet endpoints: `GET /web/reservations/card` calls `source.get_user_reservations_summary(user_id=...)`, while `GET /web/reservations/list` and `GET /web/reservations` call `source.get_user_reservations(user_id=...)`.
   - `reservations.py` handles the five reservation mutation routes via `WishlistStore.execute_wish` / `execute_wish_idempotent`, which run under `BEGIN IMMEDIATE` write transactions. No route-layer changes are needed because `WishlistStore` already exposes the same async read methods as `WishlistService`.

2. **Per-Entity Hydration Bottleneck (`wishenka/wishlists/store.py`, `wishenka/wishlists/repository.py`):**
   - `WishlistStore._cabinet_service(conn, user_id, *, include_items)` first calls `repository.list_user_reservations(user_id)` (1 query using `idx_wl_reservations_user`).
   - When `include_items=True`, it iterates over each distinct `wish_item_id` and calls `repository.get_item(item_id)`, which issues **2 queries per wish** (`SELECT ... FROM wl_items WHERE id = :id` and `SELECT ... FROM wl_reservations WHERE wish_item_id = :item_id ORDER BY id ASC`).
   - For each distinct `wishlist_id`, it also calls `repository.get_wishlist_header(wishlist_id)` (**1 query per wishlist**).
   - For $K$ distinct wishes across $L$ distinct wishlists, `get_user_reservations` executes $1 + 2K + L$ SQL round trips inside a single transaction.

3. **Write-Lock Serialization (`wishenka/wishlists/store.py`, `wishenka/sqlite.py`):**
   - Both `WishlistStore.get_user_reservations` and `WishlistStore.get_user_reservations_summary` currently execute inside `self._immediate(work)`, which triggers `BEGIN IMMEDIATE` via `configure_immediate_transactions` in `wishenka/sqlite.py`.
   - `BEGIN IMMEDIATE` acquires SQLite's reserved write lock even for read-only cabinet queries, serializing cabinet reads with concurrent writers (`execute`, `execute_wish`, `execute_wish_idempotent`).
   - `WishlistStore` already provides `execute_read(work)` (`store.py`), which applies `execution_options(read_only=True)` on the connection. In `wishenka/sqlite.py`, `configure_immediate_transactions` checks `conn.get_execution_options().get("read_only")` and emits `BEGIN` (`BEGIN DEFERRED`) instead of `BEGIN IMMEDIATE`, and `execute_read` rolls back in `finally` to release the read snapshot promptly.

### SQLite WAL Deferred Read Snapshot Behavior

- In SQLite WAL mode (`PRAGMA journal_mode = WAL`), `BEGIN` (`BEGIN DEFERRED`) acquires no locks at transaction start. The WAL read mark (snapshot) is pinned lazily on the **first `SELECT` statement** executed in the transaction.
- Once pinned, all subsequent `SELECT` statements in the same transaction observe a single, consistent point-in-time snapshot of the database, isolated from concurrent writers that commit after the first `SELECT`.
- Concurrent writers (`BEGIN IMMEDIATE`) can acquire the write lock, append frames to the WAL, and commit without waiting for active deferred readers, and without causing `SQLITE_BUSY` for readers.
- Promptly ending `execute_read` via `ROLLBACK` in `finally` prevents long-lived read marks from blocking WAL checkpointing.
- **Note on `BEGIN DEFERRED` first-`SELECT` timing:** Because `list_user_reservations(user_id)` is always the first `SELECT` executed in `_cabinet_service`, the snapshot is pinned before any item, occupancy, or wishlist header query runs. If `list_user_reservations` returns an empty list, no further queries are needed and the transaction closes immediately.

### Existing Indexes and Schema (`wishenka/wishlists/alembic/versions/`)

- `wl_reservations`: `PRIMARY KEY (id)`, `idx_wl_reservations_item` on `(wish_item_id)`, `idx_wl_reservations_user` on `(user_id)`, `idx_wl_reservations_status` on `(status)`.
- `wl_items`: `PRIMARY KEY (id)`, `idx_wl_items_wishlist` on `(wishlist_id)`.
- `wl_lists`: `PRIMARY KEY (id)`.
- Batch queries using `WHERE id IN (...)` on `wl_items` and `wl_lists` use primary-key B-tree lookups (`SEARCH ... USING INTEGER PRIMARY KEY (rowid=?)`), and `WHERE wish_item_id IN (...)` on `wl_reservations` uses `idx_wl_reservations_item` (`SEARCH wl_reservations USING INDEX idx_wl_reservations_item`). No schema or index migrations are required.

---

## Implementation Plan

1. **Add Batched Read Methods to `WishlistRepository` (`wishenka/wishlists/repository.py`):**
   - Add `get_items_by_ids(self, item_ids: Sequence[int]) -> dict[int, WishItem]`:
     - Returns `{}` immediately if `item_ids` is empty.
     - Deduplicates `item_ids` while preserving order and chunks into bounded batches (e.g. size 500) to stay well below SQLite's bind-parameter limit (`SQLITE_MAX_VARIABLE_NUMBER`).
     - Fetches `wl_items WHERE id IN (...)` and populates `WishItem` instances keyed by `item.id`.
     - For the found item IDs, fetches `wl_reservations WHERE wish_item_id IN (...) ORDER BY id ASC` (chunked if needed) and attaches each `Reservation` to its `WishItem.reservations` list, matching `get_item` behavior identically.
   - Add `get_wishlist_headers_by_ids(self, wishlist_ids: Sequence[int]) -> dict[int, Wishlist]`:
     - Returns `{}` immediately if `wishlist_ids` is empty.
     - Deduplicates and chunks `wishlist_ids` (batch size 500), fetching `wl_lists WHERE id IN (...)` and returning `{wl.id: wl}`.

2. **Update `WishlistStore._cabinet_service` (`wishenka/wishlists/store.py`):**
   - Keep `reservations = await repository.list_user_reservations(user_id)` and register them on `WishlistService.in_memory()`.
   - When `include_items=True` and `reservations` is non-empty:
     - Call `items_by_id = await repository.get_items_by_ids(item_ids)` once (where `item_ids = list(dict.fromkeys(res.wish_item_id for res in reservations))`).
     - Collect `wishlist_ids = list(dict.fromkeys(item.wishlist_id for item in items_by_id.values()))`.
     - Call `wishlists_by_id = await repository.get_wishlist_headers_by_ids(wishlist_ids)` once.
     - Attach `item.wishlist = wishlists_by_id.get(item.wishlist_id)` and register `service._items[item.id] = item`.
   - When `include_items=False`, skip item/wishlist queries completely (preserving orphan-wish summary parity).

3. **Switch Cabinet Reads to `execute_read` (`wishenka/wishlists/store.py`):**
   - Update `WishlistStore.get_user_reservations` and `WishlistStore.get_user_reservations_summary` to call `await self.execute_read(work)` instead of `await self._immediate(work)`.
   - Keep the existing `except SQLAlchemyError as exc: _raise_for_storage_error(exc, cabinet_operation=...)` error mapping and structured logging (`reservation_cabinet_busy` / `reservation_cabinet_error`).
   - Update existing unit test mocks in `tests/test_reservation_index_lifecycle.py` that patch `store._immediate` for cabinet error logging so they patch `store.execute_read` instead.

4. **Verification:**
   - Verify response parity against `WishlistService` (in-memory authoritative projection) across empty cabinets, multi-wishlist cabinets, active/purchased/cancelled reservations, and missing/deleted wishes.
   - Verify `EXPLAIN QUERY PLAN` for all cabinet queries (no full-table scans; uses `idx_wl_reservations_user`, `idx_wl_reservations_item`, and primary keys).
   - Verify concurrent write non-blocking behavior and snapshot isolation under WAL.
   - Measure latency on representative cabinet sizes (e.g. 50–200 items across multiple wishlists).

**Mandatory — Failing Repro (next Step 3):**
- **Where it lives:** `tests/test_reservation_index_lifecycle.py` (or a dedicated `tests/test_cabinet_batch_snapshot_repro.py` with `pytestmark = pytest.mark.timeout(30)`).
- **What it asserts (two targeted red tests, without live external dependencies):**
  1. **Bounded query count (batched hydration):** Seed a file-backed `WishlistStore` with a giver holding reservations on $K = 15$ distinct wishes across $L = 5$ wishlists. Attach a SQLAlchemy `before_cursor_execute` counter on `store.engine.sync_engine` during `await store.get_user_reservations(giver_id)` and assert total `SELECT` queries executed is $\le 5$ (specifically 4: reservations, items, item-occupants, wishlist headers). Currently this executes $1 + 2(15) + 5 = 36$ queries and fails red.
  2. **Non-blocking deferred snapshot under concurrent writer:** Seed a file-backed `WishlistStore` with a reservation (`quantity=1` on an item with `quantity=5`). Monkeypatch `WishlistRepository.get_items_by_ids` (or `get_item` / `get_wishlist_headers_by_ids`) to pause on an `asyncio.Event` after `list_user_reservations` has executed (pinning the read snapshot). While the cabinet read is paused mid-transaction, run a concurrent `store.execute(...)` write (`BEGIN IMMEDIATE`) that updates the reservation quantity to `2`. Assert:
     - The concurrent write completes within a short bound (e.g. `< 2s`) *before* the read is released (proving the read did not hold a write lock; currently `store._immediate` blocks the write until the read releases, causing a timeout/deadlock if the read waits for the write to finish -> fails red!).
     - After releasing the read, `get_user_reservations` still returns the pre-write consistent snapshot (`reserved_quantity=1, change_ceiling=5`), and a subsequent read returns `reserved_quantity=2`.
- **Sequencing:** Research (done) -> Step 3 red tests -> Step 4 repository batching + `execute_read` switch until green -> Step 5+ cleanup/observability/docs.

---

## Architecture

### Module Breakdown & Dependencies

```
┌──────────────────────────────────────────────────────────┐
│ wishenka/web/routes/reservations_ui.py                   │
│  - GET /web/reservations, /list -> get_user_reservations │
│  - GET /web/reservations/card   -> ..._summary           │
└───────────────────────────┬──────────────────────────────┘
                            │ (unchanged interface)
                            ▼
┌──────────────────────────────────────────────────────────┐
│ wishenka/wishlists/store.py (WishlistStore)              │
│  - get_user_reservations()     ──► execute_read(work)    │
│  - get_user_reservations_summary() ──► execute_read(work)│
│  - _cabinet_service(conn, user_id, include_items)        │
└──────────────┬────────────────────────────┬──────────────┘
               │                            │
               ▼                            ▼
┌──────────────────────────────┐ ┌─────────────────────────┐
│ wishenka/sqlite.py           │ │ WishlistRepository      │
│  - read_only=True -> BEGIN   │ │ (repository.py)         │
│    (DEFERRED WAL snapshot)   │ │  - list_user_reservations│
│  - default -> BEGIN IMMEDIATE│ │  - get_items_by_ids     │
└──────────────────────────────┘ │  - get_wishlist_headers │
                                 │    _by_ids              │
                                 └─────────────────────────┘
```

### Module Responsibilities

- **`wishenka/wishlists/repository.py` (`WishlistRepository`):**
  - Owns targeted, chunked SQL queries for `wl_reservations`, `wl_items`, and `wl_lists`.
  - New methods:
    - `get_items_by_ids(item_ids: Sequence[int]) -> dict[int, WishItem]`
    - `get_wishlist_headers_by_ids(wishlist_ids: Sequence[int]) -> dict[int, Wishlist]`
  - Chunking helper (e.g. `_CHUNK_SIZE = 500`) ensures `IN (...)` clauses never exceed SQLite bind-parameter limits while keeping round trips $O(\lceil K / 500 \rceil)$.
- **`wishenka/wishlists/store.py` (`WishlistStore`):**
  - `get_user_reservations` and `get_user_reservations_summary` orchestrate read-only deferred transactions via `self.execute_read(...)`, preserving `_raise_for_storage_error(..., cabinet_operation=...)`.
  - `_cabinet_service` hydrates `WishlistService.in_memory()` using the batched repository methods and delegates DTO projection (`MyReservationItemDTO`, `UserReservationsSummaryDTO`) to `WishlistService`, guaranteeing 100% parity with in-memory behavior and Surprise Invariant rules.
- **`wishenka/sqlite.py`:**
  - Existing `configure_immediate_transactions` listener already emits `BEGIN` when `execution_options(read_only=True)` is set and `BEGIN IMMEDIATE` otherwise. No changes required.
- **`wishenka/web/routes/reservations_ui.py` & `reservations.py`:**
  - Unchanged. `reservations_ui.py` continues calling `get_user_reservations` / `get_user_reservations_summary` on `WishlistStore`; `reservations.py` continues executing writes via `execute_wish` / `execute_wish_idempotent`.

### Architectural Patterns & Justification

- **Repository Pattern with Batched Hydration:** Eliminates $1 + 2K + L$ N+1 queries by replacing per-item and per-wishlist loops with bounded `IN (...)` batch queries, while reusing `WishlistService` for DTO projection so business logic and Surprise Invariant rules are never duplicated.
- **WAL Deferred Read Snapshot (`execute_read`):** Using `BEGIN` (`read_only=True`) in SQLite WAL mode gives cabinet reads a single consistent snapshot pinned at the first `SELECT` (`list_user_reservations`) without acquiring a reserved write lock, eliminating reader-writer contention while preserving snapshot isolation.

---

## Q&A

- **Q: Why use `execute_read` (`BEGIN DEFERRED`) instead of `BEGIN IMMEDIATE` for cabinet reads?**
  - **A:** `BEGIN IMMEDIATE` acquires SQLite's reserved write lock, blocking concurrent reservation/wish writers for the entire duration of the cabinet read. Under SQLite WAL mode, `BEGIN` (`read_only=True`) pins a consistent read snapshot on the first `SELECT` and allows concurrent writers to commit without contention.
- **Q: Could `BEGIN DEFERRED` observe a torn state if a writer commits between `list_user_reservations` and `get_items_by_ids`?**
  - **A:** No. In SQLite WAL mode, once the first `SELECT` (`list_user_reservations`) executes inside `BEGIN`, the transaction's WAL read mark is fixed until `ROLLBACK`/`COMMIT`, so `get_items_by_ids` and `get_wishlist_headers_by_ids` read from the exact same snapshot.
- **Q: Why chunk `IN (...)` queries instead of a single unbounded `IN (...)` or `JOIN`?**
  - **A:** SQLite limits bound variables per statement (`SQLITE_MAX_VARIABLE_NUMBER`, historically 999). Chunking at 500 keeps typical cabinets (and even large ones) to a single batch per query type while remaining safe for arbitrary cabinet sizes. Separating the 4 targeted queries also keeps `EXPLAIN QUERY PLAN` simple and avoids Cartesian row multiplication across `wl_reservations` and `wl_items`.
