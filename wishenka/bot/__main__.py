"""Run a single Telegram polling receiver independently from the web workers."""

import asyncio
import logging
from dataclasses import dataclass

from aiogram import Bot, Dispatcher

from wishenka.bot.capture import cleanup_drafts
from wishenka.bot.entry import create_router
from wishenka.config import Settings
from wishenka.items.service import ItemPreviewService
from wishenka.logging import configure_logging
from wishenka.users.store import UserStore
from wishenka.wishlists.store import WishlistStore

logger = logging.getLogger("wishenka.bot.cleanup")


@dataclass
class Dependencies:
    """Shared bot dependencies."""

    mini_app_url: str
    user_store: UserStore
    wishlist_store: WishlistStore
    preview_service: ItemPreviewService
    support_chat_id: int | None = None
    support_admin_ids: tuple[int, ...] = ()
    support_session_ttl_seconds: int = 3600
    support_max_message_length: int = 2000
    support_rate_limit_window_seconds: int = 3600
    support_rate_limit_max_tickets: int = 3


async def cleanup_loop(
    store: WishlistStore,
    *,
    interval: float = 3600,
    retry_interval: float = 60,
    order_retention_days: int | None = None,
) -> None:
    """Retry periodic cleanup after transient failures without exposing exception details."""
    while True:
        try:
            if order_retention_days is None:
                await cleanup_drafts(store)
            else:
                await cleanup_drafts(store, order_retention_days=order_retention_days)
        except Exception:
            logger.error(
                "bot_draft_cleanup_failed",
                extra={
                    "event": "bot_draft_cleanup_failed",
                    "order_retention_days": order_retention_days,
                },
            )
            await asyncio.sleep(retry_interval)
        else:
            await asyncio.sleep(interval)


async def run() -> None:
    """Start polling and close resources on shutdown."""
    settings = Settings()
    configure_logging(log_level=settings.log_level, json_logs=settings.log_json)
    store = UserStore(settings.database_url)
    wishlist_store = WishlistStore(settings.database_url)
    await wishlist_store.initialize()
    order_retention_days = (
        None
        if settings.bot_capture_order_retention_days == 30
        else settings.bot_capture_order_retention_days
    )
    cleanup_task = asyncio.create_task(
        cleanup_loop(wishlist_store, order_retention_days=order_retention_days)
    )
    dispatcher = Dispatcher()
    dispatcher.include_router(
        create_router(
            Dependencies(
                settings.mini_app_url,
                store,
                wishlist_store,
                ItemPreviewService(settings=settings),
                support_chat_id=settings.support_chat_id,
                support_admin_ids=settings.support_admin_ids,
                support_session_ttl_seconds=settings.support_session_ttl_seconds,
                support_max_message_length=settings.support_max_message_length,
                support_rate_limit_window_seconds=settings.support_rate_limit_window_seconds,
                support_rate_limit_max_tickets=settings.support_rate_limit_max_tickets,
            )
        )
    )
    bot = Bot(settings.bot_token)
    try:
        await dispatcher.start_polling(bot, close_bot_session=False)
    finally:
        cleanup_task.cancel()
        await asyncio.gather(cleanup_task, return_exceptions=True)
        await bot.session.close()
        await store.engine.dispose()
        await wishlist_store.dispose()


if __name__ == "__main__":
    asyncio.run(run())
