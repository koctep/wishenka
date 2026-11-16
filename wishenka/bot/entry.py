"""Private bot entry and safe Mini App navigation."""

from __future__ import annotations

import logging
import re
from typing import Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import (
    CallbackQuery,
    ErrorEvent,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    User,
    WebAppInfo,
)

from wishenka.users.store import UserStore

logger = logging.getLogger("wishenka.bot.entry")


class EntryDependencies(Protocol):
    """Configuration needed by the bot entry router."""

    mini_app_url: str


_COPY = {
    "en": {
        "welcome": "Welcome to Wishenka! Create and share wishlists with friends.",
        "unavailable": "This link is unavailable. Choose an action below.",
        "help": (
            "Create and share a wishlist. Givers can reserve wishes while surprises stay secret."
        ),
        "create": "Create wishlist",
        "collection": "My wishlists",
        "help_button": "How it works",
        "home": "Open Mini App",
        "public": "Open wishlist",
    },
    "ru": {
        "welcome": "Добро пожаловать в Вишенку! Создавайте и делитесь вишлистами.",
        "unavailable": "Ссылка недоступна. Выберите действие ниже.",
        "help": "Создайте и отправьте вишлист. Дарители бронируют желания, сохраняя сюрприз.",
        "create": "Создать вишлист",
        "collection": "Мои вишлисты",
        "help_button": "Как это работает",
        "home": "Открыть Mini App",
        "public": "Открыть вишлист",
    },
}


def _url(base: str, intent: str) -> str:
    parts = urlsplit(base)
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.fragment
    ):
        raise ValueError("Mini App URL must be an HTTPS URL without credentials or fragment")
    query = [(key, value) for key, value in parse_qsl(parts.query) if key != "startapp"]
    query.append(("startapp", intent))
    return urlunsplit((parts.scheme, parts.netloc, parts.path or "/", urlencode(query), ""))


async def _language(user: User | None, dependencies: EntryDependencies) -> str:
    code = user.language_code if user else None
    store: UserStore | None = getattr(dependencies, "user_store", None)
    if store is not None and user is not None:
        record = await store.get_by_telegram_id(user.id)
        if record and record.language_code:
            code = record.language_code
    return "ru" if code and code.lower().startswith("ru") else "en"


def _keyboard(base: str, lang: str, target: str | None = None) -> InlineKeyboardMarkup:
    copy = _COPY[lang]
    rows = []
    if target:
        rows.append(
            [InlineKeyboardButton(text=copy["public"], web_app=WebAppInfo(url=_url(base, target)))]
        )
    for key in ("create", "collection"):
        rows.append([InlineKeyboardButton(text=copy[key], web_app=WebAppInfo(url=_url(base, key)))])
    rows.append([InlineKeyboardButton(text=copy["help_button"], callback_data="entry:help")])
    rows.append(
        [InlineKeyboardButton(text=copy["home"], web_app=WebAppInfo(url=_url(base, "home")))]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def create_router(dependencies: EntryDependencies) -> Router:
    """Create an isolated receiver, without starting polling or modifying user data."""
    _url(dependencies.mini_app_url, "home")
    router = Router()

    @router.errors()
    async def entry_error(_event: ErrorEvent) -> bool:
        # Aiogram otherwise logs the exception and traceback, which can contain capabilities.
        logger.error(
            "Bot entry failed (%s)",
            type(_event.exception).__name__,
            extra={"event": "bot_start_failed"},
        )
        return True

    @router.message(CommandStart(), F.chat.type == "private")
    async def start(message: Message, command: CommandObject) -> None:
        payload = command.args
        valid = bool(
            payload and len(payload) <= 64 and re.fullmatch(r"p_[A-Za-z0-9_-]{1,62}", payload)
        )
        outcome = "invalid_link" if payload and not valid else "public_link" if valid else "menu"
        lang = await _language(message.from_user, dependencies)
        text = _COPY[lang]["unavailable" if payload and not valid else "welcome"]
        await message.answer(
            text,
            reply_markup=_keyboard(dependencies.mini_app_url, lang, payload if valid else None),
        )
        logger.info("Bot entry handled", extra={"event": "bot_start_handled", "outcome": outcome})

    @router.callback_query(F.data == "entry:help", F.message.chat.type == "private")
    async def help_callback(callback: CallbackQuery) -> None:
        if isinstance(callback.message, Message):
            lang = await _language(callback.from_user, dependencies)
            await callback.message.answer(
                _COPY[lang]["help"], reply_markup=_keyboard(dependencies.mini_app_url, lang)
            )
        await callback.answer()

    if getattr(dependencies, "wishlist_store", None) is not None:
        from wishenka.bot.capture import create_capture_router

        router.include_router(create_capture_router(dependencies))
    return router
