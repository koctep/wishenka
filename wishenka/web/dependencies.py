"""FastAPI dependencies for targeted wishlist repository access."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.exc import SQLAlchemyError

from wishenka.sqlite import is_sqlite_busy
from wishenka.wishlists.exceptions import InventoryBusyError
from wishenka.wishlists.repository import WishlistRepository
from wishenka.wishlists.store import WishlistStore

logger = logging.getLogger(__name__)


def get_wishlist_store(request: Request) -> WishlistStore:
    """Retrieve the configured WishlistStore from application state."""
    store = getattr(request.app.state, "wishlist_store", None)
    if not isinstance(store, WishlistStore):
        logger.error(
            "WishlistStore is not initialized on app.state",
            extra={"event": "wishlist_store_uninitialized"},
        )
        raise RuntimeError("WishlistStore is not initialized on app.state")
    return store


async def get_wishlist_repository(
    store: Annotated[WishlistStore, Depends(get_wishlist_store)],
) -> AsyncIterator[WishlistRepository]:
    """Yield a transaction-scoped WishlistRepository bound to an AsyncConnection."""
    storage_failed = False
    busy_exc: SQLAlchemyError | None = None
    async with store.engine.connect() as conn:
        repo: WishlistRepository | None = None
        try:
            await conn.begin()
            repo = WishlistRepository(conn)
            yield repo
            if conn.in_transaction():
                await conn.commit()
            repo.flush_commit_logs()
        except SQLAlchemyError as exc:
            if repo is not None:
                repo.clear_commit_logs()
            if conn.in_transaction():
                await conn.rollback()
            if is_sqlite_busy(exc):
                busy_exc = exc
            else:
                logger.error(
                    "Wishlist storage operation failed due to database error",
                    extra={"event": "wishlist_store_error", "error_type": type(exc).__name__},
                )
                storage_failed = True
        except BaseException:
            if repo is not None:
                repo.clear_commit_logs()
            if conn.in_transaction():
                await conn.rollback()
            raise
    if busy_exc is not None:
        logger.warning(
            "Wishlist inventory change rolled back because the database was busy",
            extra={"event": "wishlist_inventory_busy"},
        )
        raise InventoryBusyError() from busy_exc
    if storage_failed:
        raise RuntimeError("Wishlist storage operation failed")


async def get_wishlist_read_repository(
    store: Annotated[WishlistStore, Depends(get_wishlist_store)],
) -> AsyncIterator[WishlistRepository]:
    """Yield a WishlistRepository inside the store's read-only transaction.

    The transaction is plain ``BEGIN`` with ``query_only``. This dependency does not
    commit, flush commit logs, or map a busy error. ``InventoryBusyError`` raised by
    ``read_transaction`` propagates to the request.
    """
    async with store.read_transaction() as conn:
        repo = WishlistRepository(conn)
        try:
            yield repo
        finally:
            repo.clear_commit_logs()


WishlistRepo = Annotated[WishlistRepository, Depends(get_wishlist_repository)]
WishlistReadRepo = Annotated[WishlistRepository, Depends(get_wishlist_read_repository)]
