"""Concurrency control for wish items and reservation balances."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from weakref import WeakValueDictionary


class ItemConcurrencyCoordinator:
    """Coordinates per-item critical sections using keyed asyncio.Lock instances."""

    def __init__(self) -> None:
        self._locks: WeakValueDictionary[int, asyncio.Lock] = WeakValueDictionary()
        self._master_lock = asyncio.Lock()

    @asynccontextmanager
    async def acquire(self, item_id: int) -> AsyncIterator[None]:
        """Acquire the lock for a specific item_id."""
        async with self._master_lock:
            lock = self._locks.get(item_id)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[item_id] = lock

        async with lock:
            yield
