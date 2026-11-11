"""Failing reproduction tests for WISHENKA-48: SQLite WAL schema and async repository."""

import importlib
from pathlib import Path
from typing import Any, cast

import pytest
from sqlalchemy import event, text

from wishenka.auth.models import AuthenticatedUser
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
