# WISHENKA-253: Direct Unit Tests for `WishlistStore.execute_read` and `ensure_private_bot_user` Edge Cases

## Research

### Existing Implementation & Contracts

1. **`WishlistStore.execute_read`** ([wishenka/wishlists/store.py](file:///home/src/wishenka/wishlists/store.py#L1719-L1728)):
   - Opens a connection from `self.engine.connect()`, applies `execution_options(read_only=True)`, starts a transaction with `await conn.begin()`, awaits `work(conn)`, and always rolls back in `finally` if `conn.in_transaction()` is true.
   - In [wishenka/sqlite.py](file:///home/src/wishenka/sqlite.py#L36-L39), the `connect` / `begin` listener checks `conn.get_execution_options().get("read_only")`: when truthy, it skips `BEGIN IMMEDIATE`, allowing SQLite WAL deferred read transactions to run concurrently without waiting on an active `BEGIN IMMEDIATE` write lock.
   - Conversely, `WishlistStore.transaction` ([wishenka/wishlists/store.py](file:///home/src/wishenka/wishlists/store.py#L1711-L1717)) delegates to `_immediate`, which acquires a `BEGIN IMMEDIATE` write lock and commits on success.

2. **`ensure_private_bot_user`** ([wishenka/bot/principal.py](file:///home/src/wishenka/bot/principal.py#L27-L53)):
   - Guard clause: extracts `users = getattr(dependencies, "user_store", None)`; returns `None` immediately if `user is None`, `users is None`, or `chat_id != user.id`.
   - Resolution: if `user_record` is `None`, calls `await users.get_by_telegram_id(user.id)`; if still `None`, sets `_private_bot_user` contextvar to `True` and calls `await users.upsert_from_bot(user)`.
   - Timestamp normalization via `_resolve_effective_now(dependencies, now)` ([wishenka/bot/principal.py](file:///home/src/wishenka/bot/principal.py#L16-L24)):
     - If `now is not None`, returns `int(now)`.
     - Otherwise reads `getattr(dependencies, "clock", None)`. If not callable, returns `None`.
     - Otherwise calls `clock()` and converts `datetime` via `int(value.timestamp())`, else `int(value)`.
   - Destination activation: opens `async with users.engine.begin() as conn:` and calls `await upsert_bot_destination(conn, int(record.telegram_id), chat_id, effective_now)` ([wishenka/notices/destinations.py](file:///home/src/wishenka/notices/destinations.py#L11-L26)), which upserts `bot_destinations(user_id, chat_id, active=1, updated_at=effective_now)` (defaulting `None` to `int(time.time())`).

3. **Existing Test Conventions**:
   - [tests/test_wishlists_sqlite_repo.py](file:///home/src/tests/test_wishlists_sqlite_repo.py) already houses SQLite WAL and `WishlistStore` repository unit tests with `pytestmark = pytest.mark.timeout(10)` and `tmp_path`-backed `sqlite+aiosqlite:///...` databases.
   - [tests/test_wishenka_182_repro.py](file:///home/src/tests/test_wishenka_182_repro.py#L397-L427) tests `ensure_private_bot_user` log suppression using `WishlistStore` + `UserStore` initialized on the same `tmp_path` SQLite URL (needed because `bot_destinations` is provisioned by `WishlistStore` schema/migrations).
   - Per `do-testing` and `lsr-python`, every test module must declare an explicit `pytestmark = pytest.mark.timeout(...)` and bound all internal `asyncio` waits (e.g., `asyncio.wait_for(..., timeout=...)`).

## Implementation Plan

Add direct, isolated unit tests without modifying production code:

1. **`WishlistStore.execute_read` unit tests** in [tests/test_wishlists_sqlite_repo.py](file:///home/src/tests/test_wishlists_sqlite_repo.py):
   - `test_execute_read_rolls_back_mutations_on_normal_return`: seed committed row(s), run an `UPDATE`/`INSERT` inside `store.execute_read`, return normally, then verify via a subsequent `execute_read` that the uncommitted mutation was rolled back.
   - `test_execute_read_rolls_back_mutations_on_exception`: run an `UPDATE`/`INSERT` inside `store.execute_read` and raise a custom exception; assert the exception propagates and a subsequent `execute_read` sees only the original committed state.
   - `test_execute_read_does_not_block_on_active_immediate_transaction`: start `store.transaction(...)` (`BEGIN IMMEDIATE`) in a background task, write an uncommitted row, and signal `write_locked: asyncio.Event`; wait for `write_locked` with `asyncio.wait_for(..., timeout=2.0)`, execute `store.execute_read(...)` while the write lock is held, assert it completes without blocking and sees only previously committed data (WAL snapshot isolation), then set `release_write: asyncio.Event`, await the write task, and verify the new row is now visible.

2. **`ensure_private_bot_user` unit tests** in a new dedicated module [tests/test_bot_principal.py](file:///home/src/tests/test_bot_principal.py) (`pytestmark = pytest.mark.timeout(10)`):
   - Helper/fixture creating an initialized `WishlistStore` + `UserStore` on `tmp_path` with guaranteed `engine.dispose()` cleanup, plus factories for fake Telegram `user` (`SimpleNamespace`) and `UserRecord`.
   - `test_ensure_private_bot_user_returns_none_when_user_missing`: `user=None` returns `None` and makes zero calls to `user_store`.
   - `test_ensure_private_bot_user_returns_none_when_user_store_missing`: `SimpleNamespace()` (absent `user_store`) and `SimpleNamespace(user_store=None)` return `None` without raising.
   - `test_ensure_private_bot_user_returns_none_for_group_chat`: `chat_id != user.id` (e.g., `-100123456`) returns `None` and makes zero calls to `user_store` and writes no `bot_destinations` row.
   - `test_ensure_private_bot_user_uses_preresolved_user_record`: passing `user_record` skips `get_by_telegram_id` and `upsert_from_bot`, activates `bot_destinations` for `(user_record.telegram_id, chat_id)`, and returns `user_record`.
   - `test_ensure_private_bot_user_clock_and_now_normalization`: parametrized / explicit cases verifying:
     - explicit `now` overrides `dependencies.clock()` and persists `updated_at == now`;
     - `now=None` with `clock()` returning `datetime` persists `int(dt.timestamp())`;
     - `now=None` with `clock()` returning `int` persists that integer;
     - `now=None` with `clock` absent or non-callable passes `effective_now=None` to `upsert_bot_destination` (verified via monkeypatch/spy) and still activates the destination.

**Mandatory — Failing Repro (next Step 3):** `N/A — no behavioral change`. `WISHENKA-253` is a pure test-addition task covering existing contracts of `WishlistStore.execute_read` and `ensure_private_bot_user`; no production behavior is being changed.

## Architecture

No production module boundaries, interfaces, or runtime dependencies change. The test architecture mirrors the existing two-component split:

```text
tests/test_wishlists_sqlite_repo.py
  └── tests WishlistStore.execute_read (wishenka/wishlists/store.py)
        ├── Rollback on normal return
        ├── Rollback on exception
        └── Non-blocking WAL read alongside BEGIN IMMEDIATE (store.transaction)

tests/test_bot_principal.py
  └── tests ensure_private_bot_user (wishenka/bot/principal.py)
        ├── Guard clauses (user=None, user_store=None/absent, chat_id != user.id)
        ├── Pre-resolved user_record bypasses lookup/upsert & activates destination
        └── _resolve_effective_now (explicit now, datetime clock, int clock, missing/non-callable clock)
```

### Design Choices & Justification

- **Separate [tests/test_bot_principal.py](file:///home/src/tests/test_bot_principal.py) vs appending to `test_bot_support.py`**: `ensure_private_bot_user` is a shared helper in [wishenka/bot/principal.py](file:///home/src/wishenka/bot/principal.py) used across `entry`, `capture`, `birthdays`, and `support`; placing its unit tests in `tests/test_bot_principal.py` keeps module-to-test mapping 1:1.
- **Reusing [tests/test_wishlists_sqlite_repo.py](file:///home/src/tests/test_wishlists_sqlite_repo.py) for `execute_read`**: That file already owns `WishlistStore` SQLite WAL and transaction boundary tests; adding the 3 `execute_read` tests there avoids proliferating single-method test files.
- **Real SQLite WAL + `UserStore` for DB-backed branches, lightweight spies for guard branches**: Using a real `tmp_path` SQLite database ensures `BEGIN IMMEDIATE`, WAL snapshot isolation, and `bot_destinations` SQL upserts are genuinely exercised, while wrapping/spying `get_by_telegram_id`, `upsert_from_bot`, and `upsert_bot_destination` verifies exact call-skipping and `effective_now=None` forwarding.

## Q&A

1. **Q: Should `WishlistStore.execute_read` be modified to enforce `PRAGMA query_only`?**
   **A:** No. Out of scope for `WISHENKA-253` (tracked in `WISHENKA-254`).
2. **Q: Why does `test_bot_principal.py` initialize both `WishlistStore` and `UserStore` on the same SQLite URL?**
   **A:** `ensure_private_bot_user` writes to `bot_destinations` via `users.engine`, and the `bot_destinations` table is created by `WishlistStore.initialize()` / migrations, matching the pattern in [tests/test_wishenka_182_repro.py](file:///home/src/tests/test_wishenka_182_repro.py#L404-L407).
