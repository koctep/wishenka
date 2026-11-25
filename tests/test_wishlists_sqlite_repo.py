"""Failing reproduction tests for WISHENKA-48: SQLite WAL schema and async repository."""

import asyncio
import importlib
from pathlib import Path
from typing import Any, cast

import pytest
from sqlalchemy import event, text

from wishenka.auth.models import AuthenticatedUser
from wishenka.wishlists.exceptions import InsufficientQuantityError
from wishenka.wishlists.models import Wishlist
from wishenka.wishlists.service import WishlistService
from wishenka.wishlists.store import WishlistStore

pytestmark = pytest.mark.timeout(10)


def _load_wishlist_repository() -> type[Any]:
    """Dynamically load WishlistRepository from repository module or store."""
    try:
        mod = importlib.import_module("wishenka.wishlists.repository")
        return cast(type[Any], mod.WishlistRepository)
    except ModuleNotFoundError as err:
        store_mod = importlib.import_module("wishenka.wishlists.store")
        if hasattr(store_mod, "WishlistRepository"):
            return cast(type[Any], store_mod.WishlistRepository)
        raise ModuleNotFoundError("No module named 'wishenka.wishlists.repository'") from err


@pytest.mark.asyncio
async def test_sqlite_schema_has_normalized_columns_no_payload_blob(tmp_path: Path) -> None:
    """Assert wl_lists and related tables use normalized columns and no JSON blob."""
    db_path = tmp_path / "normalized_schema.db"
    store = WishlistStore(f"sqlite+aiosqlite:///{db_path}")
    await store.initialize()

    async with store.engine.connect() as conn:
        cursor_lists = await conn.execute(text("PRAGMA table_info(wl_lists)"))
        list_columns = [row[1] for row in cursor_lists.fetchall()]

        cursor_items = await conn.execute(text("PRAGMA table_info(wl_items)"))
        item_columns = [row[1] for row in cursor_items.fetchall()]

        cursor_res = await conn.execute(text("PRAGMA table_info(wl_reservations)"))
        res_columns = [row[1] for row in cursor_res.fetchall()]

    await store.engine.dispose()

    # The current prototype schema stores all entity fields inside a JSON 'payload' column.
    # The target architecture replaces 'payload' with normalized relational columns.
    assert "payload" not in list_columns, "wl_lists must not contain 'payload' column"
    assert "payload" not in item_columns, "wl_items must not contain 'payload' column"
    assert "payload" not in res_columns, "wl_reservations must not contain 'payload' column"

    # Verify presence of key normalized columns
    expected_list_cols = {"id", "owner_id", "title", "status", "public_token"}
    assert expected_list_cols.issubset(set(list_columns))

    expected_item_cols = {"id", "wishlist_id", "title", "price", "currency", "quantity"}
    assert expected_item_cols.issubset(set(item_columns))


@pytest.mark.asyncio
async def test_wishlist_update_does_not_execute_mass_table_delete(tmp_path: Path) -> None:
    """Assert mutating an existing wishlist does not emit mass table wipe statements."""
    db_path = tmp_path / "no_mass_delete.db"
    store = WishlistStore(f"sqlite+aiosqlite:///{db_path}")
    await store.initialize()

    owner = AuthenticatedUser(telegram_id=42, first_name="Alice")

    # Create initial wishlist
    async def create_op(service: WishlistService) -> Wishlist:
        return await service.create_wishlist(owner=owner, title="My Birthday List")

    created = await store.execute(create_op)

    # Track all executed SQL queries during an update
    executed_statements: list[str] = []

    @event.listens_for(store.engine.sync_engine, "before_cursor_execute")
    def intercept_sql(conn, cursor, statement, parameters, context, executemany):
        executed_statements.append(statement.strip())

    # Mutate only the wishlist title
    async def update_op(service: WishlistService) -> Wishlist:
        return await service.update_wishlist_settings(
            wishlist_id=created.id,
            actor=owner,
            title="Updated Birthday List",
        )

    await store.execute(update_op)
    await store.engine.dispose()

    # The current prototype wipes all tables via 'DELETE FROM wl_lists' and re-inserts.
    # The target architecture performs granular UPDATE or targeted upserts.
    delete_queries = [
        stmt for stmt in executed_statements if "DELETE FROM WL_LISTS" in stmt.upper()
    ]
    assert not delete_queries, (
        f"Destructive mass table delete detected during wishlist update: {delete_queries}"
    )


@pytest.mark.asyncio
async def test_wishlist_repository_direct_granular_queries(tmp_path: Path) -> None:
    """Assert WishlistRepository exists and provides targeted indexed queries."""
    WishlistRepository = _load_wishlist_repository()

    db_path = tmp_path / "granular_repo.db"
    store = WishlistStore(f"sqlite+aiosqlite:///{db_path}")
    await store.initialize()

    u101 = AuthenticatedUser(telegram_id=101, first_name="User101")
    u202 = AuthenticatedUser(telegram_id=202, first_name="User202")

    async def create_data(service: WishlistService) -> tuple[int, int]:
        wl1 = await service.create_wishlist(owner=u101, title="List 101")
        wl2 = await service.create_wishlist(owner=u202, title="List 202")
        return wl1.id, wl2.id

    wl1_id, wl2_id = await store.execute(create_data)

    async with store.engine.connect() as conn:
        repo = WishlistRepository(conn)

        # Granular lookup by ID
        get_fn = getattr(repo, "get_wishlist_by_id", getattr(repo, "get_wishlist", None))
        assert get_fn is not None, "Repository must support get_wishlist_by_id or get_wishlist"
        wl = await get_fn(wl1_id)
        assert wl is not None
        assert wl.id == wl1_id
        assert wl.title == "List 101"

        # Granular lookup by owner
        list_fn = getattr(repo, "list_user_wishlists", getattr(repo, "list_by_owner", None))
        assert list_fn is not None, "Repository must support list_user_wishlists or list_by_owner"
        user_lists = await list_fn(101)
        assert len(user_lists) == 1
        assert user_lists[0].id == wl1_id

    await store.engine.dispose()


@pytest.mark.asyncio
async def test_atomic_reservation_allocation_and_rollback(tmp_path: Path) -> None:
    """Assert transactional rollback prevents partial reservation state on error."""
    db_path = tmp_path / "atomic_rollback.db"
    store = WishlistStore(f"sqlite+aiosqlite:///{db_path}")
    await store.initialize()

    owner = AuthenticatedUser(telegram_id=10, first_name="Owner")
    gifter = AuthenticatedUser(telegram_id=20, first_name="Gifter")

    # Create baseline wishlist with one item of quantity 2
    async def setup(service: WishlistService) -> tuple[int, int]:
        wl = await service.create_wishlist(owner=owner, title="Celebration")
        item = await service.add_wish_item(
            wishlist_id=wl.id,
            actor=owner,
            title="Watch",
            quantity=2,
        )
        return wl.id, item.id

    wl_id, item_id = await store.execute(setup)

    # First verify normalized schema for reservations table
    async with store.engine.connect() as conn:
        cursor = await conn.execute(text("PRAGMA table_info(wl_reservations)"))
        res_cols = {row[1] for row in cursor.fetchall()}

    assert "payload" not in res_cols, "wl_reservations must not use JSON payload column"
    assert "wish_item_id" in res_cols, (
        "wl_reservations must use normalized foreign key wish_item_id"
    )

    # Simulate an error during reservation mutation
    class AllocationFailure(RuntimeError):
        pass

    async def failing_reservation(service: WishlistService) -> None:
        await service.create_reservation(item_id=item_id, user=gifter, quantity=1)
        # Raise unexpected error before transaction commits
        raise AllocationFailure("Transient database failure during allocation")

    with pytest.raises(AllocationFailure):
        await store.execute(failing_reservation)

    # Verify no orphan or partial reservation rows remain in the database
    async with store.engine.connect() as conn:
        count = (await conn.execute(text("SELECT COUNT(*) FROM wl_reservations"))).scalar()
        assert count == 0, f"Expected 0 reservations after rollback, found {count}"

    # Verify item available quantity remains unaltered
    async def check_item(service: WishlistService) -> None:
        item = service._items.get(item_id)
        assert item is not None
        assert item.available_quantity == 2
        assert len(item.reservations) == 0

    await store.execute(check_item)
    await store.engine.dispose()


@pytest.mark.timeout(60)
async def test_fifty_concurrent_reservations_do_not_overbook(tmp_path: Path) -> None:
    """Fifty distinct gifters compete for one unit through SQLite transactions."""
    store = WishlistStore(f"sqlite+aiosqlite:///{tmp_path / 'race.db'}")
    owner = AuthenticatedUser(telegram_id=1, first_name="Owner")
    gate = asyncio.Event()
    ready = asyncio.Event()
    ready_count = 0

    try:
        await store.initialize()

        async def setup(service: WishlistService) -> int:
            wishlist = await service.create_wishlist(owner=owner, title="Race")
            item = await service.add_wish_item(
                wishlist_id=wishlist.id, actor=owner, title="Gift", quantity=1
            )
            return item.id

        item_id = await store.execute(setup)
        async with store.engine.connect() as conn:
            assert (await conn.execute(text("PRAGMA journal_mode"))).scalar_one() == "wal"
            assert (await conn.execute(text("PRAGMA busy_timeout"))).scalar_one() == 5000

        async def attempt(user_id: int) -> tuple[str, int]:
            nonlocal ready_count
            ready_count += 1
            if ready_count == 50:
                ready.set()
            await gate.wait()
            user = AuthenticatedUser(telegram_id=user_id, first_name="Giver")

            async def reserve(service: WishlistService) -> int:
                reservation = await service.create_reservation(
                    item_id=item_id, user=user, quantity=1
                )
                return reservation.id

            try:
                result = await store.execute_wish(reserve, item_id=item_id)
            except InsufficientQuantityError:
                return ("refused", user_id)
            return ("success", result)

        tasks = [asyncio.create_task(attempt(user_id)) for user_id in range(100, 150)]
        try:
            await asyncio.wait_for(ready.wait(), timeout=5)
            gate.set()
            outcomes = await asyncio.wait_for(asyncio.gather(*tasks), timeout=40)
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        successes = [result for status, result in outcomes if status == "success"]
        assert len(successes) == 1
        assert sum(status == "refused" for status, _ in outcomes) == 49
        async with store.engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        "SELECT id, quantity, status FROM wl_reservations "
                        "WHERE wish_item_id = :item_id"
                    ),
                    {"item_id": item_id},
                )
            ).all()
        assert len(rows) == 1
        assert rows[0].id == successes[0]
        assert rows[0].quantity == 1
        assert rows[0].status == "active"
    finally:
        await store.engine.dispose()


@pytest.mark.timeout(30)
async def test_reservation_waits_for_sqlite_writer(tmp_path: Path) -> None:
    """A second connection waits for the held write lock and then books successfully."""
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'wait.db'}"
    holder = WishlistStore(db_url)
    waiter = WishlistStore(db_url)
    owner = AuthenticatedUser(telegram_id=1, first_name="Owner")
    giver = AuthenticatedUser(telegram_id=2, first_name="Giver")
    begin_attempted = asyncio.Event()
    pending: asyncio.Task[int] | None = None
    try:
        await holder.initialize()

        async def setup(service: WishlistService) -> int:
            wishlist = await service.create_wishlist(owner=owner, title="Wait")
            item = await service.add_wish_item(
                wishlist_id=wishlist.id, actor=owner, title="Gift", quantity=1
            )
            return item.id

        item_id = await holder.execute(setup)

        @event.listens_for(waiter.engine.sync_engine, "before_cursor_execute")
        def on_statement(conn, cursor, statement, parameters, context, executemany):
            if statement.strip().upper() == "BEGIN IMMEDIATE":
                begin_attempted.set()

        async def reserve(service: WishlistService) -> int:
            reservation = await service.create_reservation(item_id=item_id, user=giver, quantity=1)
            return reservation.id

        async with holder.engine.connect() as conn:
            transaction = await conn.begin()
            try:
                pending = asyncio.create_task(waiter.execute_wish(reserve, item_id=item_id))
                await asyncio.wait_for(begin_attempted.wait(), timeout=5)
                done, _ = await asyncio.wait({pending}, timeout=0.2)
                assert not done, "reservation did not wait while the writer held its lock"
            finally:
                await transaction.rollback()
        assert await asyncio.wait_for(pending, timeout=5) > 0
    finally:
        if pending is not None and not pending.done():
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
        await waiter.engine.dispose()
        await holder.engine.dispose()


class _ReadProbeError(RuntimeError):
    """Sentinel exception for testing execute_read rollback."""


@pytest.mark.asyncio
async def test_execute_read_rolls_back_mutations_on_normal_return(tmp_path: Path) -> None:
    """execute_read must roll back uncommitted SQL mutations when work returns normally."""
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'execute_read_rollback.db'}"
    store = WishlistStore(db_url)
    owner = AuthenticatedUser(telegram_id=11, first_name="Reader")
    try:
        await store.initialize()

        async def seed(service: WishlistService) -> int:
            wishlist = await service.create_wishlist(owner=owner, title="Original")
            return wishlist.id

        wishlist_id = await store.execute(seed)

        async def mutate_in_read(conn: Any) -> str:
            await conn.execute(
                text("UPDATE wl_lists SET title = :title WHERE id = :id"),
                {"title": "Mutated", "id": wishlist_id},
            )
            return "done"

        assert await store.execute_read(mutate_in_read) == "done"

        async def read_title(conn: Any) -> str:
            row = (
                await conn.execute(
                    text("SELECT title FROM wl_lists WHERE id = :id"),
                    {"id": wishlist_id},
                )
            ).one()
            return str(row.title)

        assert await store.execute_read(read_title) == "Original"
    finally:
        await store.engine.dispose()


@pytest.mark.asyncio
async def test_execute_read_rolls_back_mutations_on_exception(tmp_path: Path) -> None:
    """execute_read must roll back uncommitted mutations and propagate exceptions."""
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'execute_read_exception.db'}"
    store = WishlistStore(db_url)
    owner = AuthenticatedUser(telegram_id=12, first_name="ReaderErr")
    try:
        await store.initialize()

        async def seed(service: WishlistService) -> int:
            wishlist = await service.create_wishlist(owner=owner, title="Committed")
            return wishlist.id

        wishlist_id = await store.execute(seed)

        async def failing_read(conn: Any) -> None:
            await conn.execute(
                text("UPDATE wl_lists SET title = :title WHERE id = :id"),
                {"title": "ShouldRollback", "id": wishlist_id},
            )
            raise _ReadProbeError("boom")

        with pytest.raises(_ReadProbeError, match="boom"):
            await store.execute_read(failing_read)

        async def read_title(conn: Any) -> str:
            row = (
                await conn.execute(
                    text("SELECT title FROM wl_lists WHERE id = :id"),
                    {"id": wishlist_id},
                )
            ).one()
            return str(row.title)

        assert await store.execute_read(read_title) == "Committed"
    finally:
        await store.engine.dispose()


@pytest.mark.asyncio
async def test_execute_read_does_not_block_on_active_immediate_transaction(
    tmp_path: Path,
) -> None:
    """execute_read must complete without waiting on an active BEGIN IMMEDIATE writer."""
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'execute_read_wal.db'}"
    writer = WishlistStore(db_url)
    reader = WishlistStore(db_url)
    owner = AuthenticatedUser(telegram_id=13, first_name="WalOwner")
    write_locked = asyncio.Event()
    release_write = asyncio.Event()
    writer_task: asyncio.Task[None] | None = None
    try:
        await writer.initialize()

        async def seed(service: WishlistService) -> int:
            wishlist = await service.create_wishlist(owner=owner, title="Before")
            return wishlist.id

        wishlist_id = await writer.execute(seed)

        async def hold_write(conn: Any) -> None:
            await conn.execute(
                text("UPDATE wl_lists SET title = :title WHERE id = :id"),
                {"title": "During", "id": wishlist_id},
            )
            write_locked.set()
            await asyncio.wait_for(release_write.wait(), timeout=5.0)

        async def read_title(conn: Any) -> str:
            row = (
                await conn.execute(
                    text("SELECT title FROM wl_lists WHERE id = :id"),
                    {"id": wishlist_id},
                )
            ).one()
            return str(row.title)

        writer_task = asyncio.create_task(writer.transaction(hold_write))
        await asyncio.wait_for(write_locked.wait(), timeout=2.0)

        observed_during_write = await asyncio.wait_for(reader.execute_read(read_title), timeout=2.0)
        assert observed_during_write == "Before"

        release_write.set()
        await asyncio.wait_for(writer_task, timeout=5.0)

        observed_after_commit = await asyncio.wait_for(reader.execute_read(read_title), timeout=2.0)
        assert observed_after_commit == "During"
    finally:
        if writer_task is not None and not writer_task.done():
            release_write.set()
            writer_task.cancel()
            await asyncio.gather(writer_task, return_exceptions=True)
        await reader.engine.dispose()
        await writer.engine.dispose()
