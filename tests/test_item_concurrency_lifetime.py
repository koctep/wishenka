"""Verify the lifetime of inactive per-item coordination resources."""

import asyncio
import gc

import pytest

from wishenka.wishlists.concurrency import ItemConcurrencyCoordinator

pytestmark = pytest.mark.timeout(30)


def test_inactive_item_locks_are_reclaimed_after_many_distinct_items() -> None:
    """Completed operations must not retain one lock per historical item."""
    coordinator = ItemConcurrencyCoordinator()

    async def visit_items() -> None:
        for item_id in range(1000):
            async with coordinator.acquire(item_id):
                pass

    asyncio.run(visit_items())
    gc.collect()

    assert len(coordinator._locks) == 0


def test_waiters_keep_the_same_lock_during_handoff_and_cancellation() -> None:
    """A cancelled waiter cannot split later work across two locks."""

    async def scenario() -> None:
        coordinator = ItemConcurrencyCoordinator()
        queued = [asyncio.Event() for _ in range(3)]
        entered = [asyncio.Event() for _ in range(3)]
        release_waiter = asyncio.Event()
        active = 0
        peak = 0

        async def waiter(index: int) -> None:
            nonlocal active, peak
            queued[index].set()
            async with coordinator.acquire(7):
                active += 1
                peak = max(peak, active)
                entered[index].set()
                if index == 1:
                    await asyncio.wait_for(release_waiter.wait(), 2)
                active -= 1

        async with coordinator.acquire(7):
            original = coordinator._locks[7]
            cancelled = asyncio.create_task(waiter(0))
            first = asyncio.create_task(waiter(1))
            await asyncio.wait_for(queued[0].wait(), 2)
            await asyncio.wait_for(queued[1].wait(), 2)
            cancelled.cancel()
            with pytest.raises(asyncio.CancelledError):
                await cancelled
            gc.collect()
            assert coordinator._locks[7] is original
            assert not entered[1].is_set()

        await asyncio.wait_for(entered[1].wait(), 2)
        third = asyncio.create_task(waiter(2))
        await asyncio.wait_for(queued[2].wait(), 2)
        gc.collect()
        assert coordinator._locks[7] is original
        assert not entered[2].is_set()
        release_waiter.set()
        await asyncio.wait_for(asyncio.gather(first, third), 2)
        assert entered[2].is_set()
        assert peak == 1

    asyncio.run(scenario())


def test_independent_items_and_exception_release() -> None:
    """Other keys proceed, and an exception releases and eventually reclaims a lock."""

    async def scenario() -> None:
        coordinator = ItemConcurrencyCoordinator()
        independent_entered = asyncio.Event()

        async def independent() -> None:
            async with coordinator.acquire(2):
                independent_entered.set()

        with pytest.raises(ValueError, match="failure"):
            async with coordinator.acquire(1):
                task = asyncio.create_task(independent())
                await asyncio.wait_for(independent_entered.wait(), 2)
                await asyncio.wait_for(task, 2)
                raise ValueError("failure")

        gc.collect()
        assert 1 not in coordinator._locks
        async with coordinator.acquire(1):
            assert coordinator._locks[1].locked()
        gc.collect()
        assert 1 not in coordinator._locks

    asyncio.run(scenario())


def test_cancelled_holder_releases_lock_for_waiter_and_new_arrival() -> None:
    """Cancelling a holder preserves serialization through the subsequent handoff."""

    async def scenario() -> None:
        coordinator = ItemConcurrencyCoordinator()
        holder_entered = asyncio.Event()
        waiter_queued = asyncio.Event()
        waiter_entered = asyncio.Event()
        waiter_release = asyncio.Event()
        newcomer_queued = asyncio.Event()
        newcomer_entered = asyncio.Event()
        hold_forever = asyncio.Event()

        async def holder() -> None:
            async with coordinator.acquire(9):
                holder_entered.set()
                await asyncio.wait_for(hold_forever.wait(), 2)

        async def waiter() -> None:
            waiter_queued.set()
            async with coordinator.acquire(9):
                waiter_entered.set()
                await asyncio.wait_for(waiter_release.wait(), 2)

        async def newcomer() -> None:
            newcomer_queued.set()
            async with coordinator.acquire(9):
                newcomer_entered.set()

        holder_task = asyncio.create_task(holder())
        await asyncio.wait_for(holder_entered.wait(), 2)
        waiter_task = asyncio.create_task(waiter())
        await asyncio.wait_for(waiter_queued.wait(), 2)
        holder_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await holder_task
        await asyncio.wait_for(waiter_entered.wait(), 2)
        newcomer_task = asyncio.create_task(newcomer())
        await asyncio.wait_for(newcomer_queued.wait(), 2)
        assert not newcomer_entered.is_set()
        waiter_release.set()
        await asyncio.wait_for(asyncio.gather(waiter_task, newcomer_task), 2)
        assert newcomer_entered.is_set()

    asyncio.run(scenario())
