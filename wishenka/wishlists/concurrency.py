"""Concurrency control for wish items and reservation balances."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


class ItemConcurrencyCoordinator:
    """Coordinates per-item critical sections using keyed asyncio.Lock instances."""

    def __init__(self) -> None:
        self._locks: dict[int, asyncio.Lock] = {}
        self._master_lock = asyncio.Lock()

    @asynccontextmanager
    async def acquire(self, item_id: int) -> AsyncIterator[None]:
        """Acquire the lock for a specific item_id."""
        async with self._master_lock:
            if item_id not in self._locks:
                self._locks[item_id] = asyncio.Lock()
            lock = self._locks[item_id]

        async with lock:
            yield
