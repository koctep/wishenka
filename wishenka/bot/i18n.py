"""Aiogram v3 localization middleware and per-chat command menu sync."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

from aiogram import BaseMiddleware, Bot
from aiogram.types import BotCommand, BotCommandScopeChat, CallbackQuery, Message, TelegramObject
from aiogram.types import User as AiogramUser

from wishenka.i18n import SupportedLocale, resolve_telegram_locale, t
from wishenka.notices.sender import PLACEHOLDER_TOKEN

if TYPE_CHECKING:
    from wishenka.users.store import UserStore

logger = logging.getLogger("wishenka.bot.i18n")

_private_bot_user: ContextVar[bool] = ContextVar("private_bot_user", default=False)


class _PrivateUserLogFilter(logging.Filter):
    """Suppress wishenka.users identifier logs during private bot interactions."""

    def filter(self, record: logging.LogRecord) -> bool:
        return not _private_bot_user.get()


_user_logger = logging.getLogger("wishenka.users")
if not any(isinstance(item, _PrivateUserLogFilter) for item in _user_logger.filters):
    _user_logger.addFilter(_PrivateUserLogFilter())

_COMMAND_KEYS: tuple[tuple[str, str], ...] = (
    ("start", "bot.commands.start"),
    ("help", "bot.commands.help"),
    ("birthdays", "bot.commands.birthdays"),
    ("support", "bot.commands.support"),
    ("reservation_confirmations", "bot.commands.reservation_confirmations"),
    ("cancel", "bot.commands.cancel"),
)


def bot_commands_for_locale(locale: SupportedLocale) -> list[BotCommand]:
    """Build localized Telegram bot command menu entries for the given locale."""
    return [BotCommand(command=cmd, description=t(key, locale)) for cmd, key in _COMMAND_KEYS]


async def sync_user_bot_commands(
    bot: Bot,
    chat_id: int,
    locale: SupportedLocale,
    *,
    user_id: int | None = None,
    timeout_seconds: float = 2.0,
) -> bool:
    """Best-effort, timeout-bounded update of per-chat Telegram bot command menu."""
    if not bot.token or bot.token == PLACEHOLDER_TOKEN:
        return False
    try:
        await asyncio.wait_for(
            bot.set_my_commands(
                commands=bot_commands_for_locale(locale),
                scope=BotCommandScopeChat(chat_id=chat_id),
            ),
            timeout=timeout_seconds,
        )
        logger.debug(
            "Synced bot commands for locale %s",
            locale,
            extra={
                "event": "bot_commands_locale_synced",
                "user_id": user_id,
                "target_locale": locale,
            },
        )
        return True
    except Exception as err:
        logger.warning(
            "Failed to sync bot commands for locale %s",
            locale,
            extra={
                "event": "bot_commands_locale_sync_failed",
                "user_id": user_id,
                "target_locale": locale,
                "error_type": type(err).__name__,
            },
        )
        return False


class LocaleMiddleware(BaseMiddleware):
    """Outer middleware resolving and injecting active profile locale on bot updates."""

    def __init__(self, dependencies: Any) -> None:
        self._dependencies = dependencies

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        from_user: AiogramUser | None = getattr(event, "from_user", None)
        chat_id: int | None = None
        chat_type: str | None = None
        if isinstance(event, Message):
            chat_id = event.chat.id
            chat_type = event.chat.type
        elif isinstance(event, CallbackQuery) and isinstance(event.message, Message):
            chat_id = event.message.chat.id
            chat_type = event.message.chat.type

        user_store: UserStore | None = getattr(self._dependencies, "user_store", None)
        locale: SupportedLocale = resolve_telegram_locale(
            from_user.language_code if from_user is not None else None
        )
        if (
            user_store is not None
            and from_user is not None
            and chat_type == "private"
            and chat_id == from_user.id
        ):
            token = _private_bot_user.set(True)
            try:
                record = await user_store.upsert_from_bot(from_user)
            finally:
                _private_bot_user.reset(token)
            locale = record.locale
            data["user_record"] = record

        data["locale"] = locale
        data["t"] = lambda key, **kw: t(key, locale, **kw)
        return await handler(event, data)
