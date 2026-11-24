"""Failing repro tests for WISHENKA-176: batched cabinet reads and non-blocking snapshots."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest
from sqlalchemy import event, text

from wishenka.auth.models import AuthenticatedUser
from wishenka.wishlists.models import Reservation
from wishenka.wishlists.repository import WishlistRepository
from wishenka.wishlists.service import WishlistService
from wishenka.wishlists.store import WishlistStore

pytestmark = pytest.mark.timeout(60)


def _user(uid: int) -> AuthenticatedUser:
    return AuthenticatedUser(telegram_id=uid, first_name=f"User {uid}", auth_method="session_token")


async def test_cabinet_read_uses_bounded_batched_queries(tmp_path: Path) -> None:
    """get_user_reservations must hydrate K=15 items across L=5 wishlists in <= 5 SELECTs."""
    url = f"sqlite+aiosqlite:///{tmp_path / 'cabinet_batch.db'}"
    store = WishlistStore(url)
    await store.initialize()
    owner = _user(101)
    giver = _user(202)

    try:

        async def seed(service: WishlistService) -> None:
            for wl_idx in range(5):
                wishlist = await service.create_wishlist(owner=owner, title=f"Wishlist {wl_idx}")
                for item_idx in range(3):
                    item = await service.add_wish_item(
                        wishlist_id=wishlist.id,
                        actor=owner,
                        title=f"Gift {wl_idx}-{item_idx}",
                        quantity=2,
                    )
                    await service.create_reservation(item_id=item.id, user=giver, quantity=1)

        await store.execute(seed)

        select_statements: list[str] = []

        def count_selects(
            _conn: object,
            _cursor: object,
            statement: str,
            _parameters: object,
            _context: object,
            _executemany: object,
        ) -> None:
            if statement.lstrip().upper().startswith("SELECT"):
                select_statements.append(statement)

        event.listen(store.engine.sync_engine, "before_cursor_execute", count_selects)
        try:
            rows = await store.get_user_reservations(giver.telegram_id)
        finally:
            event.remove(store.engine.sync_engine, "before_cursor_execute", count_selects)

        assert len(rows) == 15
        assert len(select_statements) <= 5, (
            f"Expected batched cabinet read (<= 5 SELECTs), got {len(select_statements)}"
        )
    finally:
        await store.engine.dispose()


async def test_cabinet_read_does_not_block_concurrent_writer_and_keeps_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cabinet read uses a deferred WAL snapshot so concurrent writes do not block."""
    url = f"sqlite+aiosqlite:///{tmp_path / 'cabinet_snapshot.db'}"
    store = WishlistStore(url)
    await store.initialize()
    owner = _user(11)
    giver = _user(22)

    try:

        async def seed(service: WishlistService) -> int:
            wishlist = await service.create_wishlist(owner=owner, title="Snapshot List")
            item = await service.add_wish_item(
                wishlist_id=wishlist.id, actor=owner, title="Camera", quantity=5
            )
            res = await service.create_reservation(item_id=item.id, user=giver, quantity=1)
            return res.id

        reservation_id = await store.execute(seed)

        read_pinned = asyncio.Event()
        release_read = asyncio.Event()
        orig_list_user_reservations = WishlistRepository.list_user_reservations

        async def paused_list_user_reservations(
            self: WishlistRepository, user_id: int
        ) -> list[Reservation]:
            rows = await orig_list_user_reservations(self, user_id)
            if not read_pinned.is_set():
                read_pinned.set()
                await asyncio.wait_for(release_read.wait(), timeout=5.0)
            return rows

        monkeypatch.setattr(
            WishlistRepository,
            "list_user_reservations",
            paused_list_user_reservations,
        )

        read_task = asyncio.create_task(store.get_user_reservations(giver.telegram_id))
        try:
            await asyncio.wait_for(read_pinned.wait(), timeout=5.0)

            async def update_qty(service: WishlistService) -> None:
                await service.update_reservation_quantity(reservation_id, giver, 2)

            # Must complete while the cabinet read is still paused mid-transaction.
            await asyncio.wait_for(store.execute(update_qty), timeout=2.0)
        finally:
            release_read.set()
            if not read_task.done():
                await asyncio.gather(read_task, return_exceptions=True)

        snapshot_rows = read_task.result()
        assert [
            (r.reservation_id, r.reserved_quantity, r.change_ceiling) for r in snapshot_rows
        ] == [(reservation_id, 1, 5)]

        fresh_rows = await store.get_user_reservations(giver.telegram_id)
        assert [(r.reservation_id, r.reserved_quantity, r.change_ceiling) for r in fresh_rows] == [
            (reservation_id, 2, 5)
        ]
    finally:
        await store.engine.dispose()


async def test_cabinet_response_parity_with_in_memory_service(tmp_path: Path) -> None:
    """Batched SQLite cabinet read and summary match WishlistService.in_memory() identically."""
    url = f"sqlite+aiosqlite:///{tmp_path / 'cabinet_parity.db'}"
    store = WishlistStore(url)
    await store.initialize()
    owner_a, owner_b, giver, other = _user(10), _user(11), _user(20), _user(30)

    try:

        async def seed(service: WishlistService) -> None:
            wl1 = await service.create_wishlist(owner=owner_a, title="Birthday")
            wl2 = await service.create_wishlist(owner=owner_b, title="Housewarming")
            item1 = await service.add_wish_item(
                wishlist_id=wl1.id, actor=owner_a, title="Kettle", quantity=4
            )
            item2 = await service.add_wish_item(
                wishlist_id=wl1.id, actor=owner_a, title="Mug", quantity=2
            )
            item3 = await service.add_wish_item(
                wishlist_id=wl2.id, actor=owner_b, title="Lamp", quantity=3
            )
            r1 = await service.create_reservation(item_id=item1.id, user=giver, quantity=1)
            await service.create_reservation(item_id=item1.id, user=other, quantity=1)
            r2 = await service.create_reservation(item_id=item2.id, user=giver, quantity=2)
            await service.mark_reservation_purchased(r2.id, giver)
            r3 = await service.create_reservation(item_id=item3.id, user=giver, quantity=1)
            await service.cancel_reservation(r3.id, giver)
            await service.update_reservation_quantity(r1.id, giver, 2)

        await store.execute(seed)

        expected_rows = await store.execute(lambda s: s.get_user_reservations(giver.telegram_id))
        expected_summary = await store.execute(
            lambda s: s.get_user_reservations_summary(giver.telegram_id)
        )
        expected_empty_rows = await store.execute(lambda s: s.get_user_reservations(9999))
        expected_empty_summary = await store.execute(
            lambda s: s.get_user_reservations_summary(9999)
        )

        assert await store.get_user_reservations(giver.telegram_id) == expected_rows
        assert await store.get_user_reservations_summary(giver.telegram_id) == expected_summary
        assert await store.get_user_reservations(9999) == expected_empty_rows
        assert await store.get_user_reservations_summary(9999) == expected_empty_summary
    finally:
        await store.engine.dispose()


async def test_cabinet_queries_explain_query_plan_uses_indexes(tmp_path: Path) -> None:
    """All cabinet batch queries use indexes or primary keys without full-table scans."""
    url = f"sqlite+aiosqlite:///{tmp_path / 'cabinet_plan.db'}"
    store = WishlistStore(url)
    await store.initialize()

    try:
        queries_and_expected = [
            (
                "EXPLAIN QUERY PLAN "
                "SELECT id, wish_item_id, user_id, quantity, status, created_at, updated_at "
                "FROM wl_reservations WHERE user_id = :uid AND status IN ('active', 'purchased') "
                "ORDER BY id ASC",
                {"uid": 1},
                "idx_wl_reservations_user",
            ),
            (
                "EXPLAIN QUERY PLAN "
                "SELECT id, wishlist_id, title FROM wl_items WHERE id IN (:i0, :i1)",
                {"i0": 1, "i1": 2},
                "PRIMARY KEY",
            ),
            (
                "EXPLAIN QUERY PLAN "
                "SELECT id, wish_item_id, user_id, quantity, status, created_at, updated_at "
                "FROM wl_reservations WHERE wish_item_id IN (:i0, :i1) ORDER BY id ASC",
                {"i0": 1, "i1": 2},
                "idx_wl_reservations_item",
            ),
            (
                "EXPLAIN QUERY PLAN SELECT id, title FROM wl_lists WHERE id IN (:w0, :w1)",
                {"w0": 1, "w1": 2},
                "PRIMARY KEY",
            ),
        ]

        async with store.engine.connect() as conn:
            for sql, params, expected_index in queries_and_expected:
                rows = (await conn.execute(text(sql), params)).all()
                details = " | ".join(str(row[-1]) for row in rows)
                assert "SCAN " not in details, f"Unexpected table scan in plan: {details}"
                assert expected_index in details, f"Expected {expected_index} in plan: {details}"
    finally:
        await store.engine.dispose()


async def test_cabinet_representative_volume_latency_and_chunking(tmp_path: Path) -> None:
    """Cabinet read stays fast at representative volume and batch methods chunk >500 IDs."""
    url = f"sqlite+aiosqlite:///{tmp_path / 'cabinet_volume.db'}"
    store = WishlistStore(url)
    await store.initialize()
    owner = _user(100)
    giver = _user(200)

    try:

        async def seed(service: WishlistService) -> tuple[int, int]:
            first_item_id = 0
            first_wl_id = 0
            for wl_idx in range(10):
                wl = await service.create_wishlist(owner=owner, title=f"List {wl_idx}")
                if first_wl_id == 0:
                    first_wl_id = wl.id
                for item_idx in range(6):
                    item = await service.add_wish_item(
                        wishlist_id=wl.id,
                        actor=owner,
                        title=f"Item {wl_idx}-{item_idx}",
                        quantity=3,
                    )
                    if first_item_id == 0:
                        first_item_id = item.id
                    await service.create_reservation(item_id=item.id, user=giver, quantity=1)
            return first_item_id, first_wl_id

        first_item_id, first_wl_id = await store.execute(seed)

        started = time.perf_counter()
        rows = await store.get_user_reservations(giver.telegram_id)
        elapsed = time.perf_counter() - started
        assert len(rows) == 60
        assert elapsed < 1.0, f"Cabinet read took too long: {elapsed:.3f}s"

        async def check_chunking(conn: object) -> None:
            from sqlalchemy.ext.asyncio import AsyncConnection

            assert isinstance(conn, AsyncConnection)
            repo = WishlistRepository(conn)
            many_item_ids = [first_item_id, *range(10_000, 10_520)]
            many_wl_ids = [first_wl_id, *range(20_000, 20_520)]
            items = await repo.get_items_by_ids(many_item_ids)
            headers = await repo.get_wishlist_headers_by_ids(many_wl_ids)
            assert list(items.keys()) == [first_item_id]
            assert list(headers.keys()) == [first_wl_id]

        await store.execute_read(check_chunking)
    finally:
        await store.engine.dispose()


async def test_cabinet_and_batch_read_logging_omits_pii_and_tokens(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Cabinet and batch-read DEBUG logs emit counts without PII or capability tokens."""
    import logging

    url = f"sqlite+aiosqlite:///{tmp_path / 'cabinet_obs.db'}"
    store = WishlistStore(url)
    await store.initialize()
    owner = _user(777001)
    giver = _user(888002)

    try:

        async def seed(service: WishlistService) -> tuple[str, str]:
            wl = await service.create_wishlist(owner=owner, title="SecretBirthdayList")
            item = await service.add_wish_item(
                wishlist_id=wl.id, actor=owner, title="SecretGiftItem", quantity=2
            )
            await service.create_reservation(item_id=item.id, user=giver, quantity=1)
            return wl.public_token, wl.invite_token

        public_token, invite_token = await store.execute(seed)
        caplog.clear()

        with (
            caplog.at_level(logging.DEBUG, logger="wishenka.wishlists.store"),
            caplog.at_level(logging.DEBUG, logger="wishenka.wishlists.repository"),
        ):
            rows = await store.get_user_reservations(giver.telegram_id)
            summary = await store.get_user_reservations_summary(giver.telegram_id)

        assert len(rows) == 1
        assert summary.total_distinct_items == 1

        cabinet_logs = [
            r for r in caplog.records if getattr(r, "event", None) == "reservation_cabinet_read"
        ]
        batch_logs = [
            r for r in caplog.records if getattr(r, "event", None) == "wishlist_repo_batch_read"
        ]
        assert len(cabinet_logs) == 2
        assert len(batch_logs) == 2

        list_log, summary_log = cabinet_logs
        assert getattr(list_log, "include_items", None) is True
        assert getattr(list_log, "reservations_count", None) == 1
        assert getattr(list_log, "items_count", None) == 1
        assert getattr(list_log, "wishlists_count", None) == 1

        assert getattr(summary_log, "include_items", None) is False
        assert getattr(summary_log, "reservations_count", None) == 1
        assert getattr(summary_log, "items_count", None) == 0
        assert getattr(summary_log, "wishlists_count", None) == 0

        for record in [*cabinet_logs, *batch_logs]:
            msg = record.getMessage()
            for forbidden in (
                str(owner.telegram_id),
                str(giver.telegram_id),
                "SecretBirthdayList",
                "SecretGiftItem",
                public_token,
                invite_token,
            ):
                assert forbidden not in msg
                assert forbidden not in str(record.__dict__)
    finally:
        await store.engine.dispose()
