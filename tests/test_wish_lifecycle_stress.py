"""Stress and concurrency tests for wish lifecycle operations (WISHENKA-102).

Covers concurrent ``reorder_wish_items``, ``add_wish_item``, and ``archive_wish_item``
over SQLite WAL + ``BEGIN IMMEDIATE`` across single-store and multi-store contention.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from sqlalchemy import text

from wishenka.auth.models import AuthenticatedUser
from wishenka.wishlists.models import WishlistRole
from wishenka.wishlists.service import WishlistService
from wishenka.wishlists.store import WishlistStore

pytestmark = pytest.mark.timeout(120)

_BARRIER_TIMEOUT_SECONDS = 15.0
_BATCH_TIMEOUT_SECONDS = 45.0


def _actor(user_id: int, name: str) -> AuthenticatedUser:
    return AuthenticatedUser(
        telegram_id=user_id,
        first_name=name,
        auth_method="session_token",
    )


@asynccontextmanager
async def _open_wal_store(db_path: Path) -> AsyncIterator[WishlistStore]:
    """Initialize a SQLite WAL WishlistStore, verify pragmas, and dispose on exit."""
    store = WishlistStore(f"sqlite+aiosqlite:///{db_path}")
    try:
        await store.initialize()
        async with store.engine.connect() as conn:
            journal_mode = (await conn.execute(text("PRAGMA journal_mode"))).scalar_one()
            foreign_keys = (await conn.execute(text("PRAGMA foreign_keys"))).scalar_one()
            busy_timeout = (await conn.execute(text("PRAGMA busy_timeout"))).scalar_one()
        assert str(journal_mode).lower() == "wal"
        assert int(foreign_keys) == 1
        assert int(busy_timeout) == 5000
        yield store
    finally:
        await store.dispose()


async def _run_barrier_tasks[T](
    factories: Sequence[Callable[[], Awaitable[T]]],
    *,
    barrier_timeout: float = _BARRIER_TIMEOUT_SECONDS,
    batch_timeout: float = _BATCH_TIMEOUT_SECONDS,
) -> list[T]:
    """Start all coroutines at a shared barrier and await them with bounded timeouts."""
    total = len(factories)
    if total == 0:
        return []

    ready = asyncio.Event()
    gate = asyncio.Event()
    ready_count = 0

    async def runner(factory: Callable[[], Awaitable[T]]) -> T:
        nonlocal ready_count
        ready_count += 1
        if ready_count == total:
            ready.set()
        await asyncio.wait_for(gate.wait(), timeout=barrier_timeout)
        return await factory()

    tasks = [asyncio.create_task(runner(factory)) for factory in factories]
    try:
        await asyncio.wait_for(ready.wait(), timeout=barrier_timeout)
        gate.set()
        return list(await asyncio.wait_for(asyncio.gather(*tasks), timeout=batch_timeout))
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def _seed_wishlist_with_items(
    store: WishlistStore,
    *,
    owner: AuthenticatedUser,
    co_authors: Sequence[tuple[AuthenticatedUser, WishlistRole]],
    item_count: int,
    title: str = "Stress Wishlist",
) -> tuple[int, list[int]]:
    """Create a wishlist with co-authors and initial active items."""
    service = WishlistService(store=store)
    async with store.engine.begin() as conn:
        for member, _ in co_authors:
            await conn.execute(
                text(
                    "INSERT OR IGNORE INTO users (telegram_id, first_name, created_at, updated_at) "
                    "VALUES (:uid, :name, '2026-01-01', '2026-01-01')"
                ),
                {"uid": member.telegram_id, "name": member.first_name},
            )
    wishlist = await service.create_wishlist(owner=owner, title=title)
    for member, role in co_authors:
        await service.add_member(
            wishlist_id=wishlist.id,
            actor=owner,
            user_id=member.telegram_id,
            role=role,
        )

    item_ids: list[int] = []
    for idx in range(item_count):
        item = await service.add_wish_item(
            wishlist_id=wishlist.id,
            actor=owner,
            title=f"{title} Item {idx}",
        )
        item_ids.append(item.id)
    return wishlist.id, item_ids


async def _assert_wishlist_invariants(
    store: WishlistStore,
    *,
    wishlist_id: int,
    actor: AuthenticatedUser,
    expected_active_ids: set[int],
    expected_archived_ids: set[int],
    require_contiguous_order: bool = False,
) -> list[int]:
    """Verify wishlist item sets, display_order uniqueness, and service/SQL agreement."""
    async with store.engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT id, display_order, is_archived "
                    "FROM wl_items WHERE wishlist_id = :wid "
                    "ORDER BY display_order ASC, id ASC"
                ),
                {"wid": wishlist_id},
            )
        ).fetchall()

    sql_active = [(int(r[0]), int(r[1])) for r in rows if int(r[2]) == 0]
    sql_archived = {int(r[0]) for r in rows if int(r[2]) == 1}

    sql_active_ids = [item_id for item_id, _ in sql_active]
    sql_active_orders = [order for _, order in sql_active]

    assert set(sql_active_ids) == expected_active_ids
    assert len(sql_active_ids) == len(expected_active_ids)
    assert sql_archived == expected_archived_ids
    assert expected_active_ids.isdisjoint(expected_archived_ids)
    assert len(sql_active_orders) == len(set(sql_active_orders))
    if require_contiguous_order:
        assert sorted(sql_active_orders) == list(range(len(expected_active_ids)))

    service = WishlistService(store=store)
    view = await service.get_wishlist_view(wishlist_id=wishlist_id, current_user=actor)
    view_active_ids = [item.id for item in view.items]
    view_archived_ids = {item.id for item in view.archived_items}

    assert view_active_ids == sql_active_ids
    assert view_archived_ids == expected_archived_ids
    return view_active_ids


async def test_concurrent_reorders_single_store_preserve_permutation(tmp_path: Path) -> None:
    """Twenty-four concurrent reorders on one store produce a valid 0..N-1 permutation."""
    db_path = tmp_path / "reorder_single.db"
    owner = _actor(1001, "Owner")
    member = _actor(1002, "Member")
    admin = _actor(1003, "Admin")

    async with _open_wal_store(db_path) as store:
        wishlist_id, item_ids = await _seed_wishlist_with_items(
            store,
            owner=owner,
            co_authors=[(member, WishlistRole.MEMBER), (admin, WishlistRole.ADMIN)],
            item_count=8,
        )
        actors = [owner, member, admin]
        service = WishlistService(store=store)

        def make_reorder(idx: int) -> Callable[[], Awaitable[list[int]]]:
            actor = actors[idx % len(actors)]
            shift = idx % len(item_ids)
            candidate = item_ids[shift:] + item_ids[:shift]
            if idx % 2 == 1:
                candidate = list(reversed(candidate))

            async def call() -> list[int]:
                result = await service.reorder_wish_items(
                    wishlist_id=wishlist_id,
                    actor=actor,
                    item_ids=candidate,
                )
                return [item.id for item in result]

            return call

        outcomes = await _run_barrier_tasks([make_reorder(i) for i in range(24)])
        for returned_ids in outcomes:
            assert set(returned_ids) == set(item_ids)
            assert len(returned_ids) == len(item_ids)

        await _assert_wishlist_invariants(
            store,
            wishlist_id=wishlist_id,
            actor=owner,
            expected_active_ids=set(item_ids),
            expected_archived_ids=set(),
            require_contiguous_order=True,
        )


async def test_concurrent_reorders_multiple_stores_preserve_permutation(tmp_path: Path) -> None:
    """Concurrent reorders across four separate WishlistStore instances stay consistent."""
    db_path = tmp_path / "reorder_multi.db"
    owner = _actor(2001, "Owner")
    co_author = _actor(2002, "CoAuthor")

    async with _open_wal_store(db_path) as seed_store:
        wishlist_id, item_ids = await _seed_wishlist_with_items(
            seed_store,
            owner=owner,
            co_authors=[(co_author, WishlistRole.MEMBER)],
            item_count=7,
        )

    stores = [WishlistStore(f"sqlite+aiosqlite:///{db_path}") for _ in range(4)]
    try:
        services = [WishlistService(store=store) for store in stores]
        actors = [owner, co_author]

        def make_reorder(idx: int) -> Callable[[], Awaitable[list[int]]]:
            service = services[idx % len(services)]
            actor = actors[idx % len(actors)]
            shift = idx % len(item_ids)
            candidate = item_ids[shift:] + item_ids[:shift]
            if idx % 3 == 0:
                candidate = list(reversed(candidate))

            async def call() -> list[int]:
                result = await service.reorder_wish_items(
                    wishlist_id=wishlist_id,
                    actor=actor,
                    item_ids=candidate,
                )
                return [item.id for item in result]

            return call

        outcomes = await _run_barrier_tasks([make_reorder(i) for i in range(20)])
        for returned_ids in outcomes:
            assert set(returned_ids) == set(item_ids)
            assert len(returned_ids) == len(item_ids)

        await _assert_wishlist_invariants(
            stores[0],
            wishlist_id=wishlist_id,
            actor=owner,
            expected_active_ids=set(item_ids),
            expected_archived_ids=set(),
            require_contiguous_order=True,
        )
    finally:
        for store in stores:
            await store.dispose()


async def test_concurrent_add_and_reorder_preserve_all_items(tmp_path: Path) -> None:
    """Parallel add and reorder preserve all items and reject stale snapshots."""
    db_path = tmp_path / "add_reorder.db"
    owner = _actor(3001, "Owner")
    co_author = _actor(3002, "CoAuthor")

    async with _open_wal_store(db_path) as store:
        wishlist_id, initial_ids = await _seed_wishlist_with_items(
            store,
            owner=owner,
            co_authors=[(co_author, WishlistRole.ADMIN)],
            item_count=5,
        )
        service = WishlistService(store=store)
        actors = [owner, co_author]

        def make_add(idx: int) -> Callable[[], Awaitable[tuple[str, int]]]:
            actor = actors[idx % len(actors)]

            async def call() -> tuple[str, int]:
                item = await service.add_wish_item(
                    wishlist_id=wishlist_id,
                    actor=actor,
                    title=f"Concurrent Added {idx}",
                )
                return ("added", item.id)

            return call

        def make_reorder(idx: int) -> Callable[[], Awaitable[tuple[str, int]]]:
            actor = actors[idx % len(actors)]
            shift = idx % len(initial_ids)
            candidate = initial_ids[shift:] + initial_ids[:shift]

            async def call() -> tuple[str, int]:
                try:
                    result = await service.reorder_wish_items(
                        wishlist_id=wishlist_id,
                        actor=actor,
                        item_ids=candidate,
                    )
                except ValueError:
                    return ("stale_rejected", idx)
                assert [item.id for item in result] == candidate
                return ("reordered", idx)

            return call

        factories: list[Callable[[], Awaitable[tuple[str, int]]]] = [
            *[make_add(i) for i in range(8)],
            *[make_reorder(i) for i in range(10)],
        ]
        outcomes = await _run_barrier_tasks(factories)

        added_ids = {value for kind, value in outcomes if kind == "added"}
        assert len(added_ids) == 8
        assert all(kind in {"added", "reordered", "stale_rejected"} for kind, _ in outcomes)

        expected_active = set(initial_ids) | added_ids
        active_ids = await _assert_wishlist_invariants(
            store,
            wishlist_id=wishlist_id,
            actor=owner,
            expected_active_ids=expected_active,
            expected_archived_ids=set(),
        )

        # Follow-up reorder on the full active set restores contiguous 0..N-1 order.
        await service.reorder_wish_items(
            wishlist_id=wishlist_id,
            actor=owner,
            item_ids=list(reversed(active_ids)),
        )
        await _assert_wishlist_invariants(
            store,
            wishlist_id=wishlist_id,
            actor=owner,
            expected_active_ids=expected_active,
            expected_archived_ids=set(),
            require_contiguous_order=True,
        )


async def test_concurrent_archive_and_reorder_exclude_archived_items(tmp_path: Path) -> None:
    """Parallel archive, add, and reorder never leave archived items in active order."""
    db_path = tmp_path / "archive_reorder.db"
    owner = _actor(4001, "Owner")
    co_author = _actor(4002, "CoAuthor")

    async with _open_wal_store(db_path) as store:
        wishlist_id, initial_ids = await _seed_wishlist_with_items(
            store,
            owner=owner,
            co_authors=[(co_author, WishlistRole.MEMBER)],
            item_count=8,
        )
        service = WishlistService(store=store)
        archive_targets = [initial_ids[0], initial_ids[3], initial_ids[6]]
        actors = [owner, co_author]

        def make_archive(item_id: int, idx: int) -> Callable[[], Awaitable[tuple[str, int]]]:
            actor = actors[idx % len(actors)]

            async def call() -> tuple[str, int]:
                await service.archive_wish_item(
                    wishlist_id=wishlist_id,
                    item_id=item_id,
                    actor=actor,
                )
                return ("archived", item_id)

            return call

        def make_add(idx: int) -> Callable[[], Awaitable[tuple[str, int]]]:
            actor = actors[idx % len(actors)]

            async def call() -> tuple[str, int]:
                item = await service.add_wish_item(
                    wishlist_id=wishlist_id,
                    actor=actor,
                    title=f"Added During Archive {idx}",
                )
                return ("added", item.id)

            return call

        def make_reorder(idx: int) -> Callable[[], Awaitable[tuple[str, int]]]:
            actor = actors[idx % len(actors)]
            candidate = list(reversed(initial_ids)) if idx % 2 == 0 else list(initial_ids)

            async def call() -> tuple[str, int]:
                try:
                    await service.reorder_wish_items(
                        wishlist_id=wishlist_id,
                        actor=actor,
                        item_ids=candidate,
                    )
                except ValueError:
                    return ("stale_rejected", idx)
                return ("reordered", idx)

            return call

        factories: list[Callable[[], Awaitable[tuple[str, int]]]] = [
            *[make_archive(item_id, idx) for idx, item_id in enumerate(archive_targets)],
            *[make_add(i) for i in range(4)],
            *[make_reorder(i) for i in range(8)],
        ]
        outcomes = await _run_barrier_tasks(factories)

        archived_ids = {value for kind, value in outcomes if kind == "archived"}
        added_ids = {value for kind, value in outcomes if kind == "added"}
        assert archived_ids == set(archive_targets)
        assert len(added_ids) == 4

        expected_active = (set(initial_ids) - archived_ids) | added_ids
        await _assert_wishlist_invariants(
            store,
            wishlist_id=wishlist_id,
            actor=owner,
            expected_active_ids=expected_active,
            expected_archived_ids=archived_ids,
        )


async def test_mixed_lifecycle_waves_owner_and_coauthors(tmp_path: Path) -> None:
    """Multi-wave mixed operations across two stores keep active/archived state consistent."""
    db_path = tmp_path / "mixed_waves.db"
    owner = _actor(5001, "Owner")
    admin = _actor(5002, "Admin")
    member = _actor(5003, "Member")

    async with _open_wal_store(db_path) as seed_store:
        wishlist_id, initial_ids = await _seed_wishlist_with_items(
            seed_store,
            owner=owner,
            co_authors=[(admin, WishlistRole.ADMIN), (member, WishlistRole.MEMBER)],
            item_count=6,
        )

    stores = [WishlistStore(f"sqlite+aiosqlite:///{db_path}") for _ in range(2)]
    try:
        services = [WishlistService(store=s) for s in stores]
        actors = [owner, admin, member]
        expected_active = set(initial_ids)
        expected_archived: set[int] = set()

        for wave in range(3):
            snapshot_active = sorted(expected_active)
            archive_target = snapshot_active[0]

            def make_add(
                idx: int, wave_idx: int = wave
            ) -> Callable[[], Awaitable[tuple[str, int]]]:
                svc = services[idx % len(services)]
                actor = actors[idx % len(actors)]

                async def call() -> tuple[str, int]:
                    item = await svc.add_wish_item(
                        wishlist_id=wishlist_id,
                        actor=actor,
                        title=f"Wave {wave_idx} Item {idx}",
                    )
                    return ("added", item.id)

                return call

            def make_archive(
                target_id: int = archive_target,
                wave_idx: int = wave,
            ) -> Callable[[], Awaitable[tuple[str, int]]]:
                svc = services[wave_idx % len(services)]
                actor = actors[wave_idx % len(actors)]

                async def call() -> tuple[str, int]:
                    await svc.archive_wish_item(
                        wishlist_id=wishlist_id,
                        item_id=target_id,
                        actor=actor,
                    )
                    return ("archived", target_id)

                return call

            def make_reorder(
                idx: int,
                snap: list[int] = snapshot_active,
            ) -> Callable[[], Awaitable[tuple[str, int]]]:
                svc = services[(idx + 1) % len(services)]
                actor = actors[(idx + 1) % len(actors)]
                candidate = list(reversed(snap)) if idx % 2 == 0 else snap[1:] + snap[:1]

                async def call() -> tuple[str, int]:
                    try:
                        await svc.reorder_wish_items(
                            wishlist_id=wishlist_id,
                            actor=actor,
                            item_ids=candidate,
                        )
                    except ValueError:
                        return ("stale_rejected", idx)
                    return ("reordered", idx)

                return call

            factories: list[Callable[[], Awaitable[tuple[str, int]]]] = [
                *[make_add(i) for i in range(4)],
                make_archive(),
                *[make_reorder(i) for i in range(6)],
            ]
            outcomes = await _run_barrier_tasks(factories)

            wave_added = {val for kind, val in outcomes if kind == "added"}
            wave_archived = {val for kind, val in outcomes if kind == "archived"}
            assert len(wave_added) == 4
            assert wave_archived == {archive_target}

            expected_active = (expected_active - wave_archived) | wave_added
            expected_archived |= wave_archived

            active_ids = await _assert_wishlist_invariants(
                stores[0],
                wishlist_id=wishlist_id,
                actor=owner,
                expected_active_ids=expected_active,
                expected_archived_ids=expected_archived,
            )

        await services[0].reorder_wish_items(
            wishlist_id=wishlist_id,
            actor=owner,
            item_ids=list(reversed(active_ids)),
        )
        await _assert_wishlist_invariants(
            stores[1],
            wishlist_id=wishlist_id,
            actor=owner,
            expected_active_ids=expected_active,
            expected_archived_ids=expected_archived,
            require_contiguous_order=True,
        )
    finally:
        for store in stores:
            await store.dispose()


async def test_concurrent_lifecycle_isolation_across_wishlists(tmp_path: Path) -> None:
    """Concurrent mutations on three independent wishlists never cross-contaminate."""
    db_path = tmp_path / "isolation.db"
    owners = [_actor(6001 + i, f"Owner{i}") for i in range(3)]

    async with _open_wal_store(db_path) as store:
        seeded: list[tuple[int, AuthenticatedUser, list[int]]] = []
        for idx, owner in enumerate(owners):
            wl_id, item_ids = await _seed_wishlist_with_items(
                store,
                owner=owner,
                co_authors=[],
                item_count=5,
                title=f"Isolated {idx}",
            )
            seeded.append((wl_id, owner, item_ids))

        service = WishlistService(store=store)
        factories: list[Callable[[], Awaitable[tuple[int, str, int]]]] = []

        for wl_idx, (wl_id, owner, item_ids) in enumerate(seeded):
            archive_id = item_ids[0]

            def make_add(
                w_idx: int = wl_idx,
                wid: int = wl_id,
                act: AuthenticatedUser = owner,
                add_idx: int = 0,
            ) -> Callable[[], Awaitable[tuple[int, str, int]]]:
                async def call() -> tuple[int, str, int]:
                    item = await service.add_wish_item(
                        wishlist_id=wid,
                        actor=act,
                        title=f"WL{w_idx} New {add_idx}",
                    )
                    return (wid, "added", item.id)

                return call

            def make_archive(
                wid: int = wl_id,
                act: AuthenticatedUser = owner,
                target: int = archive_id,
            ) -> Callable[[], Awaitable[tuple[int, str, int]]]:
                async def call() -> tuple[int, str, int]:
                    await service.archive_wish_item(
                        wishlist_id=wid,
                        item_id=target,
                        actor=act,
                    )
                    return (wid, "archived", target)

                return call

            def make_reorder(
                wid: int = wl_id,
                act: AuthenticatedUser = owner,
                snap: list[int] = item_ids,
                r_idx: int = 0,
            ) -> Callable[[], Awaitable[tuple[int, str, int]]]:
                candidate = list(reversed(snap)) if r_idx % 2 == 0 else snap[1:] + snap[:1]

                async def call() -> tuple[int, str, int]:
                    try:
                        await service.reorder_wish_items(
                            wishlist_id=wid,
                            actor=act,
                            item_ids=candidate,
                        )
                    except ValueError:
                        return (wid, "stale_rejected", r_idx)
                    return (wid, "reordered", r_idx)

                return call

            for add_i in range(3):
                factories.append(make_add(add_idx=add_i))
            factories.append(make_archive())
            for r_i in range(4):
                factories.append(make_reorder(r_idx=r_i))

        outcomes = await _run_barrier_tasks(factories)

        for wl_id, owner, initial_ids in seeded:
            added = {val for wid, kind, val in outcomes if wid == wl_id and kind == "added"}
            archived = {val for wid, kind, val in outcomes if wid == wl_id and kind == "archived"}
            assert len(added) == 3
            assert archived == {initial_ids[0]}
            expected_active = (set(initial_ids) - archived) | added
            await _assert_wishlist_invariants(
                store,
                wishlist_id=wl_id,
                actor=owner,
                expected_active_ids=expected_active,
                expected_archived_ids=archived,
            )
