"""FastAPI dependencies for targeted wishlist repository access."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.exc import SQLAlchemyError

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
    async with store.engine.connect() as conn:
        await conn.begin()
        try:
            yield WishlistRepository(conn)
            if conn.in_transaction():
                await conn.commit()
        except SQLAlchemyError as exc:
            if conn.in_transaction():
                await conn.rollback()
            logger.error(
                "Wishlist storage operation failed due to database error",
                extra={"event": "wishlist_store_error", "error_type": type(exc).__name__},
            )
            storage_failed = True
        except BaseException:
            if conn.in_transaction():
                await conn.rollback()
            raise
    if storage_failed:
        raise RuntimeError("Wishlist storage operation failed")


WishlistRepo = Annotated[WishlistRepository, Depends(get_wishlist_repository)]
