"""Private bot entry and safe Mini App navigation."""

from __future__ import annotations

import logging
import re
from typing import Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (
    CallbackQuery,
    ErrorEvent,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    User,
    WebAppInfo,
)
from sqlalchemy import text

from wishenka.bot.i18n import LocaleMiddleware, _private_bot_user, sync_user_bot_commands
from wishenka.i18n import (
    DEFAULT_LOCALE,
    SupportedLocale,
    resolve_telegram_locale,
    t,
)
from wishenka.notices.destinations import upsert_bot_destination
from wishenka.users.models import UserRecord
from wishenka.users.store import UserStore

logger = logging.getLogger("wishenka.bot.entry")


class EntryDependencies(Protocol):
    """Configuration needed by the bot entry router."""

    mini_app_url: str


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


async def _language(
    user: User | None,
    dependencies: EntryDependencies,
    resolved_locale: str | None = None,
) -> SupportedLocale:
    """Resolve user locale, preferring pre-resolved middleware locale when supplied."""
    if resolved_locale == "ru":
        return "ru"
    if resolved_locale == "en":
        return "en"
    store: UserStore | None = getattr(dependencies, "user_store", None)
    if store is not None and user is not None:
        record = await store.get_by_telegram_id(user.id)
        if record is not None:
            return record.locale
    return resolve_telegram_locale(user.language_code if user else None)


def _keyboard(base: str, lang: SupportedLocale, target: str | None = None) -> InlineKeyboardMarkup:
    rows = []
    if target:
        rows.append(
            [
                InlineKeyboardButton(
                    text=t("bot.entry.btn_public", lang),
                    web_app=WebAppInfo(url=_url(base, target)),
                )
            ]
        )
    for intent, key in (
        ("create", "bot.entry.btn_create"),
        ("collection", "bot.entry.btn_collection"),
    ):
        rows.append(
            [InlineKeyboardButton(text=t(key, lang), web_app=WebAppInfo(url=_url(base, intent)))]
        )
    rows.append(
        [InlineKeyboardButton(text=t("bot.entry.btn_help", lang), callback_data="entry:help")]
    )
    rows.append(
        [InlineKeyboardButton(text=t("bot.entry.btn_support", lang), callback_data="support:open")]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=t("bot.entry.btn_birthdays", lang), callback_data="birthday:open"
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=t("bot.entry.btn_home", lang),
                web_app=WebAppInfo(url=_url(base, "home")),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _ensure_private_destination(
    dependencies: EntryDependencies,
    message: Message,
    user_record: UserRecord | None,
) -> UserRecord | None:
    """Persist verified bot destination and clear superseded support input."""
    users: UserStore | None = getattr(dependencies, "user_store", None)
    if users is None or not message.from_user or message.chat.id != message.from_user.id:
        return None
    record = user_record
    if record is None:
        token = _private_bot_user.set(True)
        try:
            record = await users.upsert_from_bot(message.from_user)
        finally:
            _private_bot_user.reset(token)
    async with users.engine.begin() as conn:
        await upsert_bot_destination(conn, int(record.id), message.chat.id)
    store = getattr(dependencies, "wishlist_store", None)
    if store is not None:
        from wishenka.bot.support import clear_support_session

        await clear_support_session(store, int(record.id), message.chat.id)
    return record


def create_router(dependencies: EntryDependencies) -> Router:
    """Create an isolated receiver, without starting polling or modifying user data."""
    _url(dependencies.mini_app_url, "home")
    router = Router()

    middleware = LocaleMiddleware(dependencies)
    router.message.outer_middleware(middleware)
    router.callback_query.outer_middleware(middleware)

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
    async def start(
        message: Message,
        command: CommandObject,
        locale: SupportedLocale = DEFAULT_LOCALE,
        user_record: UserRecord | None = None,
    ) -> None:
        record = await _ensure_private_destination(dependencies, message, user_record)
        payload = command.args
        valid = bool(
            payload and len(payload) <= 64 and re.fullmatch(r"p_[A-Za-z0-9_-]{1,62}", payload)
        )
        outcome = "invalid_link" if payload and not valid else "public_link" if valid else "menu"
        lang = await _language(message.from_user, dependencies, locale)
        key = "bot.entry.unavailable" if payload and not valid else "bot.entry.welcome"
        await message.answer(
            t(key, lang),
            reply_markup=_keyboard(dependencies.mini_app_url, lang, payload if valid else None),
        )
        if (
            message.bot is not None
            and message.from_user
            and message.chat.id == message.from_user.id
        ):
            await sync_user_bot_commands(
                message.bot,
                message.chat.id,
                lang,
                user_id=record.id if record is not None else None,
            )
        logger.info("Bot entry handled", extra={"event": "bot_start_handled", "outcome": outcome})

    @router.message(Command("help"), F.chat.type == "private")
    async def help_command(
        message: Message,
        locale: SupportedLocale = DEFAULT_LOCALE,
        user_record: UserRecord | None = None,
    ) -> None:
        await _ensure_private_destination(dependencies, message, user_record)
        lang = await _language(message.from_user, dependencies, locale)
        await message.answer(
            t("bot.entry.help", lang),
            reply_markup=_keyboard(dependencies.mini_app_url, lang),
        )

    @router.callback_query(F.data == "entry:help", F.message.chat.type == "private")
    async def help_callback(
        callback: CallbackQuery,
        locale: SupportedLocale = DEFAULT_LOCALE,
        user_record: UserRecord | None = None,
    ) -> None:
        if isinstance(callback.message, Message):
            users: UserStore | None = getattr(dependencies, "user_store", None)
            store = getattr(dependencies, "wishlist_store", None)
            if users is not None and store is not None and callback.from_user:
                record = user_record or await users.get_by_telegram_id(callback.from_user.id)
                if record is not None:
                    from wishenka.bot.support import clear_support_session

                    await clear_support_session(store, int(record.id), callback.message.chat.id)
            lang = await _language(callback.from_user, dependencies, locale)
            await callback.message.answer(
                t("bot.entry.help", lang),
                reply_markup=_keyboard(dependencies.mini_app_url, lang),
            )
        await callback.answer()

    @router.message(Command("reservation_confirmations"), F.chat.type == "private")
    async def reservation_confirmations(
        message: Message,
        command: CommandObject,
        locale: SupportedLocale = DEFAULT_LOCALE,
        user_record: UserRecord | None = None,
    ) -> None:
        """Let a user explicitly opt in or out of their own action confirmations."""
        user = message.from_user
        users: UserStore | None = getattr(dependencies, "user_store", None)
        if user is None or users is None or message.chat.id != user.id:
            return
        lang = await _language(user, dependencies, locale)
        value = (command.args or "").strip().lower()
        if value not in {"on", "off"}:
            await message.answer(t("bot.entry.confirmations_usage", lang))
            return
        record = user_record or await users.get_by_telegram_id(user.id)
        if record is None:
            await message.answer(t("bot.entry.start_first", lang))
            return
        store = getattr(dependencies, "wishlist_store", None)
        if store is not None:
            from wishenka.bot.support import clear_support_session

            await clear_support_session(store, int(record.id), message.chat.id)
        async with users.engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO user_notification_settings(user_id,event_type,enabled,updated_at) "
                    "VALUES (:user,'reservation_changes',:enabled,CURRENT_TIMESTAMP) "
                    "ON CONFLICT(user_id,event_type) DO UPDATE SET enabled=:enabled, "
                    "updated_at=CURRENT_TIMESTAMP"
                ),
                {"user": user.id, "enabled": int(value == "on")},
            )
        key = "bot.entry.confirmations_on" if value == "on" else "bot.entry.confirmations_off"
        await message.answer(t(key, lang))

    if getattr(dependencies, "wishlist_store", None) is not None:
        from wishenka.bot.birthdays import create_birthday_router
        from wishenka.bot.capture import create_capture_router
        from wishenka.bot.support import create_support_router

        router.include_router(create_support_router(dependencies))
        router.include_router(create_birthday_router(dependencies))
        router.include_router(create_capture_router(dependencies))
    return router
