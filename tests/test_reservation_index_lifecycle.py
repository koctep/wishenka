"""Verify indexed cabinet reads remain equivalent to authoritative storage."""

import logging
import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncConnection

from wishenka.auth.models import AuthenticatedUser
from wishenka.wishlists.exceptions import InventoryBusyError
from wishenka.wishlists.models import WishItem
from wishenka.wishlists.schemas import MyReservationItemDTO, UserReservationsSummaryDTO
from wishenka.wishlists.service import WishlistService
from wishenka.wishlists.store import WishlistStore

pytestmark = pytest.mark.timeout(30)


@pytest.mark.parametrize(
    ("method", "operation"),
    [
        ("get_user_reservations", "reservations_list"),
        ("get_user_reservations_summary", "reservations_summary"),
    ],
)
@pytest.mark.parametrize("busy", [True, False])
async def test_cabinet_storage_error_logs_read_context_without_user_data(
    method: str, operation: str, busy: bool, caplog: pytest.LogCaptureFixture
) -> None:
    store = WishlistStore("sqlite+aiosqlite:///:memory:")
    detail = "database is locked" if busy else "private database detail"
    store._immediate = AsyncMock(  # type: ignore[method-assign]
        side_effect=OperationalError(
            "private SQL", {"user": 987654321}, sqlite3.OperationalError(detail)
        )
    )
    error_type = InventoryBusyError if busy else RuntimeError
    with (
        caplog.at_level(logging.WARNING, logger="wishenka.wishlists.store"),
        pytest.raises(error_type),
    ):
        await getattr(store, method)(987654321)
    records = [r for r in caplog.records if r.name == "wishenka.wishlists.store"]
    assert len(records) == 1
    assert getattr(records[0], "event", None) == (
        "reservation_cabinet_busy" if busy else "reservation_cabinet_error"
    )
    assert getattr(records[0], "operation", None) == operation
    assert "cabinet read" in records[0].getMessage()
    assert "987654321" not in records[0].getMessage()
    assert "private" not in records[0].getMessage()
    await store.engine.dispose()


def user(uid: int) -> AuthenticatedUser:
    return AuthenticatedUser(telegram_id=uid, first_name=str(uid), auth_method="session_token")


async def test_index_tracks_lifecycle_and_preserves_isolation() -> None:
    service = WishlistService()
    owner, giver, other = user(1), user(2), user(3)
    wishlist = await service.create_wishlist(owner=owner, title="List")
    item = await service.add_wish_item(
        wishlist_id=wishlist.id, actor=owner, title="Book", quantity=5
    )
    first = await service.create_reservation(item_id=item.id, user=giver, quantity=1)
    await service.create_reservation(item_id=item.id, user=other, quantity=1)
    duplicate = await service.create_reservation(item_id=item.id, user=giver, quantity=1)
    summary = await service.get_user_reservations_summary(2)
    assert (summary.total_active_reservations, summary.total_distinct_items) == (2, 1)
    await service.cancel_reservation(duplicate.id, giver)
    rows = await service.get_user_reservations(giver.telegram_id)
    assert [(r.reservation_id, r.change_ceiling) for r in rows] == [(first.id, 4)]
    assert await service.get_user_reservations(999) == []
    await service.update_reservation_quantity(first.id, giver, 2)
    await service.mark_reservation_purchased(first.id, giver)
    assert (await service.get_user_reservations(giver.telegram_id))[0].reserved_quantity == 2
    await service.revert_reservation_to_active(first.id, giver)
    await service.cancel_reservation(first.id, giver)
    assert (
        await service.get_user_reservations_summary(giver.telegram_id)
    ).total_distinct_items == 0
    second = await service.create_reservation(item_id=item.id, user=giver, quantity=1)
    assert [r.reservation_id for r in await service.get_user_reservations(2)] == [second.id]
    service._remove_reservation(first.id)
    service._remove_reservation(duplicate.id)
    service._remove_reservation(second.id)
    assert 2 not in service._reservations_by_user
    assert len(await service.get_user_reservations(3)) == 1
    service._items.pop(item.id)
    assert await service.get_user_reservations(3) == []
    orphan_summary = await service.get_user_reservations_summary(3)
    assert (orphan_summary.total_active_reservations, orphan_summary.total_distinct_items) == (1, 1)


async def test_sqlite_cabinet_matches_snapshot_after_changes_and_restart(tmp_path: Path) -> None:
    url = f"sqlite+aiosqlite:///{tmp_path / 'indexes.db'}"
    store = WishlistStore(url)
    await store.initialize()
    owner, giver, other = user(11), user(22), user(33)

    async def seed(service: WishlistService) -> int:
        wishlist = await service.create_wishlist(owner=owner, title="List")
        item = await service.add_wish_item(
            wishlist_id=wishlist.id, actor=owner, title="Gift", quantity=5
        )
        res = await service.create_reservation(item_id=item.id, user=giver, quantity=1)
        await service.create_reservation(item_id=item.id, user=other, quantity=1)
        return res.id

    async def compare() -> None:
        async def reference(
            service: WishlistService,
        ) -> tuple[list[MyReservationItemDTO], UserReservationsSummaryDTO]:
            return (
                await service.get_user_reservations(22),
                await service.get_user_reservations_summary(22),
            )

        expected_rows, expected_summary = await store.execute(reference)
        assert await store.get_user_reservations(22) == expected_rows
        assert await store.get_user_reservations_summary(22) == expected_summary
        assert await store.get_user_reservations(999) == []

    try:
        reservation_id = await store.execute(seed)
        await compare()

        async def buy(service: WishlistService) -> None:
            await service.mark_reservation_purchased(reservation_id, giver)

        await store.execute(buy)
        await compare()

        async def restore(service: WishlistService) -> None:
            await service.revert_reservation_to_active(reservation_id, giver)

        await store.execute(restore)
        await compare()

        async def cancel(service: WishlistService) -> None:
            await service.cancel_reservation(reservation_id, giver)

        await store.execute(cancel)
        await compare()
        assert await store.get_user_reservations(22) == []
        assert (await store.get_user_reservations_summary(22)).total_active_reservations == 0

        async def recreate(service: WishlistService) -> None:
            item_id = service._reservations[reservation_id].wish_item_id
            await service.create_reservation(item_id, giver, 1)

        await store.execute(recreate)
        await compare()
        assert len(await store.get_user_reservations(22)) == 1

        async def remove_cancelled(conn: AsyncConnection) -> None:
            await conn.execute(
                text("DELETE FROM wl_reservations WHERE id = :id"), {"id": reservation_id}
            )

        await store.transaction(remove_cancelled)
        await compare()

        async def fail(service: WishlistService) -> None:
            active_id = (await service.get_user_reservations(22))[0].reservation_id
            await service.mark_reservation_purchased(active_id, giver)
            raise RuntimeError("roll back")

        with pytest.raises(RuntimeError, match="roll back"):
            await store.execute(fail)
        await compare()
        async with store.engine.connect() as conn:
            result = await conn.execute(
                text("EXPLAIN QUERY PLAN SELECT id FROM wl_reservations WHERE user_id = :uid"),
                {"uid": 22},
            )
            assert any("idx_wl_reservations_user" in str(row) for row in result)
    finally:
        await store.dispose()
    store = WishlistStore(url)
    try:
        await store.initialize()
        await compare()
    finally:
        await store.dispose()


async def test_sqlite_read_is_consistent_with_concurrent_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio

    from wishenka.wishlists.repository import WishlistRepository

    store = WishlistStore(f"sqlite+aiosqlite:///{tmp_path / 'concurrent.db'}")
    await store.initialize()
    owner, giver = user(1), user(2)

    async def seed(service: WishlistService) -> int:
        wishlist = await service.create_wishlist(owner=owner, title="List")
        item = await service.add_wish_item(
            wishlist_id=wishlist.id, actor=owner, title="Gift", quantity=5
        )
        return (await service.create_reservation(item_id=item.id, user=giver, quantity=1)).id

    try:
        reservation_id = await store.execute(seed)
        entered, release = asyncio.Event(), asyncio.Event()
        original = WishlistRepository.get_item

        async def paused_get_item(self: WishlistRepository, item_id: int) -> WishItem | None:
            entered.set()
            await asyncio.wait_for(release.wait(), 5)
            return await original(self, item_id)

        monkeypatch.setattr(WishlistRepository, "get_item", paused_get_item)
        read_task = asyncio.create_task(store.get_user_reservations(2))
        await asyncio.wait_for(entered.wait(), 5)

        async def update(service: WishlistService) -> None:
            await service.update_reservation_quantity(reservation_id, giver, 2)

        write_task = asyncio.create_task(store.execute(update))
        await asyncio.sleep(0)
        release.set()
        rows = await asyncio.wait_for(read_task, 5)
        await asyncio.wait_for(write_task, 5)
        assert rows[0].reserved_quantity == 1
        assert rows[0].change_ceiling == 5
        assert (await store.get_user_reservations(2))[0].reserved_quantity == 2
    finally:
        await store.dispose()


async def test_sqlite_missing_wish_keeps_summary_but_omits_list(tmp_path: Path) -> None:
    path = tmp_path / "missing.db"
    url = f"sqlite+aiosqlite:///{path}"
    store = WishlistStore(url)
    await store.initialize()
    owner, giver = user(1), user(2)

    async def seed(service: WishlistService) -> int:
        wishlist = await service.create_wishlist(owner=owner, title="List")
        item = await service.add_wish_item(
            wishlist_id=wishlist.id, actor=owner, title="Gift", quantity=5
        )
        await service.create_reservation(item.id, giver, 1)
        await service.create_reservation(item.id, giver, 1)
        return item.id

    try:
        item_id = await store.execute(seed)
        rows = await store.get_user_reservations(2)
        summary = await store.get_user_reservations_summary(2)
        assert len(rows) == 2
        assert (summary.total_active_reservations, summary.total_distinct_items) == (2, 1)
    finally:
        await store.dispose()
    # Simulate legacy inconsistent storage: normal foreign keys cascade item deletion.
    with sqlite3.connect(path) as conn:
        conn.execute("DELETE FROM wl_items WHERE id = ?", (item_id,))
    store = WishlistStore(url)
    try:
        assert await store.get_user_reservations(2) == []
        summary = await store.get_user_reservations_summary(2)
        assert (summary.total_active_reservations, summary.total_distinct_items) == (2, 1)
    finally:
        await store.dispose()
