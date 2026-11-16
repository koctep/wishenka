"""Run a single Telegram polling receiver independently from the web workers."""

import asyncio
from dataclasses import dataclass

from aiogram import Bot, Dispatcher

from wishenka.bot.entry import create_router
from wishenka.config import Settings
from wishenka.logging import configure_logging
from wishenka.users.store import UserStore


@dataclass
class Dependencies:
    """Shared bot dependencies."""

    mini_app_url: str
    user_store: UserStore


async def run() -> None:
    """Start polling and close resources on shutdown."""
    settings = Settings()
    configure_logging(log_level=settings.log_level, json_logs=settings.log_json)
    store = UserStore(settings.database_url)
    dispatcher = Dispatcher()
    dispatcher.include_router(create_router(Dependencies(settings.mini_app_url, store)))
    bot = Bot(settings.bot_token)
    try:
        await dispatcher.start_polling(bot, close_bot_session=False)
    finally:
        await bot.session.close()
        await store.engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
