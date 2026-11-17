"""Owner-scoped private birthday reminder management."""

from __future__ import annotations

import calendar
import time
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from wishenka.bot.entry import _language
from wishenka.bot.i18n import _private_bot_user
from wishenka.i18n import DEFAULT_LOCALE, SupportedLocale, t
from wishenka.users.models import UserRecord


def create_birthday_router(dependencies: Any) -> Router:
    """Build a private router with durable, owner-scoped input sessions."""
    router = Router()
    store = dependencies.wishlist_store
    users = dependencies.user_store

    async def principal(
        user: Any,
        chat: int,
        user_record: UserRecord | None = None,
    ) -> int | None:
        if user is None or chat != user.id:
            return None
        record = user_record
        if record is None:
            token = _private_bot_user.set(True)
            try:
                record = await users.upsert_from_bot(user)
            finally:
                _private_bot_user.reset(token)
        async with users.engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO bot_destinations(user_id,chat_id,active) VALUES (:id,:chat,1) "
                    "ON CONFLICT(user_id) DO UPDATE SET chat_id=:chat,active=1"
                ),
                {"id": record.id, "chat": chat},
            )
        return int(record.id)

    async def listing(message: Message, owner: int, lang: SupportedLocale) -> None:
        async with store.engine.connect() as conn:
            rows = (
                (
                    await conn.execute(
                        text(
                            "SELECT id, label, month, day, revision FROM birthday_entries "
                            "WHERE owner_id=:owner AND deleted=0 ORDER BY id LIMIT 20"
                        ),
                        {"owner": owner},
                    )
                )
                .mappings()
                .all()
            )
        add = t("bot.birthdays.btn_add", lang)
        edit = t("bot.birthdays.btn_edit", lang)
        delete = t("bot.birthdays.btn_delete", lang)
        keyboard = [[InlineKeyboardButton(text=add, callback_data="birthday:add")]]
        lines = [t("bot.birthdays.heading", lang)]
        for row in rows:
            lines.append(f"{row['label']}: {row['month']:02d}-{row['day']:02d}")
            key = f"{row['id']}:{row['revision']}"
            keyboard.append(
                [
                    InlineKeyboardButton(
                        text=f"{edit} {row['label']}", callback_data=f"birthday:e:{key}"
                    ),
                    InlineKeyboardButton(
                        text=f"{delete} {row['label']}", callback_data=f"birthday:d:{key}"
                    ),
                ]
            )
        await message.answer(
            "\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )

    @router.message(Command("birthdays"), F.chat.type == "private")
    async def birthdays(
        message: Message,
        locale: SupportedLocale = DEFAULT_LOCALE,
        user_record: UserRecord | None = None,
    ) -> None:
        owner = await principal(message.from_user, message.chat.id, user_record)
        if owner is not None:
            from wishenka.bot.support import clear_support_session

            await clear_support_session(store, owner, message.chat.id)
            lang = await _language(message.from_user, dependencies, locale)
            await listing(message, owner, lang)

    @router.message(Command("cancel"), F.chat.type == "private")
    async def cancel(
        message: Message,
        locale: SupportedLocale = DEFAULT_LOCALE,
        user_record: UserRecord | None = None,
    ) -> None:
        owner = await principal(message.from_user, message.chat.id, user_record)
        if owner is None:
            return

        async def clear(conn: AsyncConnection) -> None:
            await conn.execute(
                text("DELETE FROM birthday_input WHERE owner_id=:owner AND chat_id=:chat"),
                {"owner": owner, "chat": message.chat.id},
            )

        await store.transaction(clear)
        lang = await _language(message.from_user, dependencies, locale)
        await message.answer(t("bot.birthdays.cancelled", lang))

    @router.callback_query(F.data.startswith("birthday:"), F.message.chat.type == "private")
    async def action(
        callback: CallbackQuery,
        locale: SupportedLocale = DEFAULT_LOCALE,
        user_record: UserRecord | None = None,
    ) -> None:
        if not isinstance(callback.message, Message):
            return
        chat_id = callback.message.chat.id
        owner = await principal(callback.from_user, callback.message.chat.id, user_record)
        if owner is None:
            await callback.answer()
            return
        from wishenka.bot.support import clear_support_session

        await clear_support_session(store, owner, chat_id)
        lang = await _language(callback.from_user, dependencies, locale)
        parts = (callback.data or "").split(":")
        if parts == ["birthday", "open"]:
            await listing(callback.message, owner, lang)
            await callback.answer()
            return

        async def change(conn: AsyncConnection) -> str:
            if parts == ["birthday", "add"]:
                await conn.execute(
                    text(
                        "INSERT OR REPLACE INTO birthday_input VALUES (:owner,:chat,NULL,NULL,"
                        "'label',NULL,:expires)"
                    ),
                    {
                        "owner": owner,
                        "chat": chat_id,
                        "expires": int(time.time()) + 3600,
                    },
                )
                return "prompt"
            if len(parts) != 4 or parts[1] not in ("e", "d"):
                return "invalid"
            try:
                ident, revision = int(parts[2]), int(parts[3])
            except ValueError:
                return "invalid"
            row = (
                await conn.execute(
                    text(
                        "SELECT id FROM birthday_entries WHERE id=:id AND owner_id=:owner "
                        "AND revision=:revision AND deleted=0"
                    ),
                    {"id": ident, "owner": owner, "revision": revision},
                )
            ).first()
            if row is None:
                return "invalid"
            if parts[1] == "d":
                await conn.execute(
                    text("UPDATE birthday_entries SET deleted=1, revision=revision+1 WHERE id=:id"),
                    {"id": ident},
                )
                await conn.execute(
                    text("DELETE FROM birthday_input WHERE owner_id=:owner AND entry_id=:id"),
                    {"owner": owner, "id": ident},
                )
                return "deleted"
            await conn.execute(
                text(
                    "INSERT OR REPLACE INTO birthday_input VALUES (:owner,:chat,:id,:revision,"
                    "'label',NULL,:expires)"
                ),
                {
                    "owner": owner,
                    "chat": chat_id,
                    "id": ident,
                    "revision": revision,
                    "expires": int(time.time()) + 3600,
                },
            )
            return "prompt"

        outcome = await store.transaction(change)
        if outcome == "prompt":
            await callback.message.answer(t("bot.birthdays.enter_name", lang))
        elif outcome == "deleted":
            await listing(callback.message, owner, lang)
        else:
            await callback.message.answer(t("bot.birthdays.action_unavailable", lang))
        await callback.answer()

    @router.message(F.chat.type == "private", F.text, ~F.text.startswith("/"))
    async def input_message(
        message: Message,
        locale: SupportedLocale = DEFAULT_LOCALE,
        user_record: UserRecord | None = None,
    ) -> Any:
        from aiogram.dispatcher.event.bases import SkipHandler

        user = message.from_user
        if user is None or message.chat.id != user.id:
            raise SkipHandler
        record = user_record or await users.get_by_telegram_id(user.id)
        if record is None:
            raise SkipHandler
        lang = await _language(user, dependencies, locale)
        value = (message.text or "").strip()

        async def apply(conn: AsyncConnection) -> str:
            pending = (
                (
                    await conn.execute(
                        text(
                            "SELECT * FROM birthday_input WHERE owner_id=:owner AND chat_id=:chat "
                            "AND expires_at>:now"
                        ),
                        {"owner": record.id, "chat": message.chat.id, "now": int(time.time())},
                    )
                )
                .mappings()
                .first()
            )
            if pending is None:
                return "skip"
            if pending["stage"] == "label":
                if not 1 <= len(value) <= 80:
                    return "invalid_label"
                await conn.execute(
                    text(
                        "UPDATE birthday_input SET stage='date',label=:label WHERE owner_id=:owner "
                        "AND chat_id=:chat"
                    ),
                    {"label": value, "owner": record.id, "chat": message.chat.id},
                )
                return "date"
            try:
                month, day = (int(part) for part in value.split("-"))
                if not (1 <= month <= 12 and 1 <= day <= calendar.monthrange(2000, month)[1]):
                    raise ValueError
            except (ValueError, TypeError):
                return "invalid_date"
            if pending["entry_id"] is None:
                count = await conn.scalar(
                    text(
                        "SELECT COUNT(*) FROM birthday_entries WHERE owner_id=:owner AND deleted=0"
                    ),
                    {"owner": record.id},
                )
                if count is not None and count >= 20:
                    return "limit"
                await conn.execute(
                    text(
                        "INSERT INTO birthday_entries(owner_id,label,month,day) "
                        "VALUES (:owner,:label,:month,:day)"
                    ),
                    {"owner": record.id, "label": pending["label"], "month": month, "day": day},
                )
            else:
                result = await conn.execute(
                    text(
                        "UPDATE birthday_entries SET revision=revision+CASE "
                        "WHEN label!=:label OR month!=:month OR day!=:day THEN 1 ELSE 0 END, "
                        "label=:label,month=:month,day=:day "
                        "WHERE id=:id AND owner_id=:owner AND revision=:revision AND deleted=0"
                    ),
                    {
                        "owner": record.id,
                        "id": pending["entry_id"],
                        "revision": pending["revision"],
                        "label": pending["label"],
                        "month": month,
                        "day": day,
                    },
                )
                if not result.rowcount:
                    return "stale"
            await conn.execute(
                text("DELETE FROM birthday_input WHERE owner_id=:owner AND chat_id=:chat"),
                {"owner": record.id, "chat": message.chat.id},
            )
            return "saved"

        result = await store.transaction(apply)
        if result == "skip":
            raise SkipHandler
        prompt_keys = {
            "date": "bot.birthdays.enter_date",
            "invalid_label": "bot.birthdays.invalid_label",
            "invalid_date": "bot.birthdays.invalid_date",
            "stale": "bot.birthdays.stale",
            "limit": "bot.birthdays.limit",
            "saved": "bot.birthdays.saved",
        }
        await message.answer(t(prompt_keys[result], lang))

    return router
