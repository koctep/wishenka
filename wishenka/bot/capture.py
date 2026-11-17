"""Private, durable wish capture for Telegram conversations."""

from __future__ import annotations

import json
import logging
import re
import secrets
import time
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from wishenka.auth.models import AuthenticatedUser, TelegramUser
from wishenka.bot.entry import _language, _url
from wishenka.items.classifier import UniversalInputClassifier
from wishenka.items.schemas import CreateItemDTO
from wishenka.wishlists.policy import WishlistAccessPolicy
from wishenka.wishlists.store import WishlistStore

_preview_active: ContextVar[bool] = ContextVar("bot_private_preview", default=False)
logger = logging.getLogger("wishenka.bot.capture")


class _PrivatePreviewFilter(logging.Filter):
    """Suppress third-party preview logs only in this task's asynchronous context."""

    def filter(self, record: logging.LogRecord) -> bool:
        return not _preview_active.get()


for _logger_name in (
    "wishenka.items",
    "httpx",
    "httpcore",
    "httpcore.connection",
    "httpcore.http11",
    "httpcore.http2",
    "httpcore.proxy",
    "wishenka.users",
    "wishenka.wishlists",
    "wishenka.wishlists.store",
    "wishenka.wishlists.notices",
):
    _logger = logging.getLogger(_logger_name)
    if not any(isinstance(item, _PrivatePreviewFilter) for item in _logger.filters):
        _logger.addFilter(_PrivatePreviewFilter())


_FIELDS = (
    "title",
    "description",
    "link",
    "image_url",
    "price",
    "currency",
    "quantity",
    "priority",
    "category",
    "recipient_user_id",
    "recipient_name",
)
_LABELS = {
    "title": "Title",
    "description": "Description",
    "link": "Link",
    "image_url": "Image URL",
    "price": "Price",
    "currency": "Currency",
    "quantity": "Quantity",
    "priority": "Priority",
    "category": "Category",
    "recipient_user_id": "Recipient ID",
    "recipient_name": "Recipient name",
}

_RU_LABELS = {
    "title": "Название",
    "description": "Описание",
    "link": "Ссылка",
    "image_url": "Ссылка на изображение",
    "price": "Цена",
    "currency": "Валюта",
    "quantity": "Количество",
    "priority": "Приоритет",
    "category": "Категория",
    "recipient_user_id": "ID получателя",
    "recipient_name": "Имя получателя",
}


def _label(field: str, lang: str) -> str:
    return (_RU_LABELS if lang == "ru" else _LABELS)[field]


def _safe_web_url(value: Any) -> bool:
    """Allow only absolute HTTP(S) URLs before persisting clickable references."""
    if value is None or value == "":
        return True
    if not isinstance(value, str) or any(ord(char) <= 32 or char == "\\" for char in value):
        return False
    try:
        parsed = urlsplit(value)
        return parsed.scheme.lower() in ("http", "https") and bool(parsed.hostname)
    except ValueError:
        return False


def _actor(user_id: int) -> AuthenticatedUser:
    return AuthenticatedUser(
        telegram_id=user_id, first_name="Telegram user", auth_method="telegram"
    )


def _now(deps: Any) -> datetime:
    clock = getattr(deps, "clock", None)
    return clock() if callable(clock) else datetime.now(UTC)


def _allowed(service: Any, actor: AuthenticatedUser) -> list[Any]:
    return [
        wl
        for wl in service._wishlists.values()
        if WishlistAccessPolicy.can_add_or_edit_item(
            WishlistAccessPolicy.resolve_context(actor, wl), wl
        )
    ]


def _keyboard(
    draft: Any,
    lists: list[Any],
    lang: str,
    fields: bool = False,
    page: int = 0,
    base_url: str | None = None,
) -> InlineKeyboardMarkup:
    ident, rev = draft["id"], draft["revision"]

    def callback(action: str) -> str:
        return f"cap:{ident}:{rev}:{action}"

    rows: list[list[InlineKeyboardButton]] = []
    ru = lang == "ru"
    if fields:
        for field in _FIELDS:
            row = [
                InlineKeyboardButton(text=_label(field, lang), callback_data=callback("e_" + field))
            ]
            if field != "title":
                row.append(
                    InlineKeyboardButton(
                        text="Очистить" if ru else "Clear", callback_data=callback("c_" + field)
                    )
                )
            rows.append(row)
    else:
        if len(lists) > 1 or draft["list_id"] is None:
            page = max(0, min(page, max(0, (len(lists) - 1) // 8)))
            for wl in lists[page * 8 : page * 8 + 8]:
                rows.append(
                    [InlineKeyboardButton(text=wl.title, callback_data=callback(f"l_{wl.id}"))]
                )
            nav = []
            if page > 0:
                nav.append(InlineKeyboardButton(text="‹", callback_data=callback(f"p_{page - 1}")))
            if (page + 1) * 8 < len(lists):
                nav.append(InlineKeyboardButton(text="›", callback_data=callback(f"p_{page + 1}")))
            if nav:
                rows.append(nav)
        rows.append(
            [
                InlineKeyboardButton(
                    text="Редактировать" if ru else "Edit", callback_data=callback("edit")
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text="Посмотреть полностью" if ru else "View full values",
                    callback_data=callback("view"),
                )
            ]
        )
        if draft["list_id"] is not None:
            rows.append(
                [
                    InlineKeyboardButton(
                        text="Сохранить" if ru else "Save", callback_data=callback("save")
                    )
                ]
            )
    if not lists and base_url:
        rows.append(
            [
                InlineKeyboardButton(
                    text="Создать вишлист" if ru else "Create wishlist",
                    web_app=WebAppInfo(url=_url(base_url, "create")),
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="Отмена" if ru else "Cancel", callback_data=callback("cancel"))]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _review(draft: Any, lists: list[Any], replaced: bool = False, lang: str = "en") -> str:
    values = json.loads(draft["data"])
    destination = next((wl.title for wl in lists if wl.id == draft["list_id"]), None)
    truncated = False

    def display(value: Any) -> str:
        nonlocal truncated
        rendered = str(value)
        if len(rendered) <= 100:
            return rendered
        truncated = True
        return rendered[:99] + "…"

    lines = [
        ("Предыдущий черновик удалён." if lang == "ru" else "Previous draft discarded.")
        if replaced
        else ("Проверьте" if lang == "ru" else "Review")
    ]
    if values.get("_preview_fallback"):
        lines.append(
            "Не удалось извлечь все данные. Проверьте и заполните поля вручную."
            if lang == "ru"
            else "Could not extract all details. Review and enter missing fields manually."
        )
        missing = [
            _label(field, lang)
            for field in ("title", "description", "image_url", "price")
            if values.get(field) is None or values.get(field) == ""
        ]
        if missing:
            prefix = "Не заполнено: " if lang == "ru" else "Missing: "
            lines.append(prefix + ", ".join(missing))
    if not values.get("title"):
        lines.append("Необходимо название." if lang == "ru" else "Title is required.")
    lines.extend(
        f"{_label(key, lang)}: {display(value)}"
        for key, value in values.items()
        if key in _FIELDS and value is not None and value != ""
    )
    lines.append(
        (f"Список: {display(destination)}" if lang == "ru" else f"List: {display(destination)}")
        if destination
        else ("Выберите список" if lang == "ru" else "Choose a list")
    )
    if not lists:
        lines.append(
            "Нет доступных списков. Создайте список или запросите приглашение."
            if lang == "ru"
            else "No available list. Create a wishlist or request an invitation."
        )
    if truncated:
        lines.append(
            "Длинные значения сокращены только в обзоре; сохраняются полностью. "
            "Нажмите «Посмотреть полностью»."
            if lang == "ru"
            else "Long values are shortened only in this review; they are saved in full. "
            "Select View full values."
        )
    return "\n".join(lines)


async def _row(conn: AsyncConnection, ident: str) -> Any:
    result = await conn.execute(text("SELECT * FROM bot_drafts WHERE id=:id"), {"id": ident})
    return result.mappings().one_or_none()


def create_capture_router(deps: Any) -> Router:
    """Create handlers backed by the same SQLite transactions as wishlist operations."""
    router = Router()
    store: WishlistStore = deps.wishlist_store

    async def lists_for(actor: AuthenticatedUser) -> list[Any]:
        async def work(service: Any) -> list[Any]:
            return _allowed(service, actor)

        return await store.execute(work)

    @router.message(F.chat.type == "private", F.text, ~F.text.startswith("/"))
    async def capture(message: Message) -> None:
        if not message.from_user or message.text is None:
            return
        actor = _actor(message.from_user.id)
        lang = await _language(message.from_user, deps)
        users = getattr(deps, "user_store", None)
        if users is not None and message.chat.id == message.from_user.id:
            record = await users.get_by_telegram_id(message.from_user.id)
            if record is None:
                private_context = _preview_active.set(True)
                try:
                    record = await users.upsert_user(
                        TelegramUser(
                            id=message.from_user.id,
                            first_name=message.from_user.first_name,
                            last_name=message.from_user.last_name,
                            username=message.from_user.username,
                            language_code=message.from_user.language_code,
                            is_premium=bool(message.from_user.is_premium),
                        )
                    )
                finally:
                    _preview_active.reset(private_context)
            async with users.engine.begin() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO bot_destinations(user_id,chat_id,active) VALUES (:id,:chat,1) "
                        "ON CONFLICT(user_id) DO UPDATE SET chat_id=:chat,active=1"
                    ),
                    {"id": record.id, "chat": message.chat.id},
                )
        now = _now(deps)
        chat = message.chat.id
        raw = message.text.strip()

        async def pending(conn: AsyncConnection) -> Any:
            result = await conn.execute(
                text(
                    "SELECT d.*, o.message_id AS capture_message_id FROM bot_drafts d "
                    "JOIN bot_capture_order o ON d.owner=o.owner AND d.chat=o.chat "
                    "WHERE d.owner=:owner AND d.chat=:chat AND d.state='active' "
                    "AND d.edit_field IS NOT NULL AND d.expires>:now "
                    "ORDER BY d.rowid DESC LIMIT 1"
                ),
                {"owner": actor.telegram_id, "chat": chat, "now": now.isoformat()},
            )
            return result.mappings().one_or_none()

        editing = await store.transaction(pending)
        if editing and message.message_id <= editing["capture_message_id"]:
            return
        if editing:
            field = editing["edit_field"]
            values = json.loads(editing["data"])
            try:
                value: Any = raw or None
                if field in ("price", "quantity", "recipient_user_id") and value is not None:
                    value = int(value)
                # Validate this field independently of incomplete extracted values.
                check = {"title": "placeholder", field: value}
                validated = CreateItemDTO.model_validate(check)
                candidate = {**values, field: getattr(validated, field)}
            except (ValueError, ValidationError):
                await message.answer(
                    f"Неверное значение: {_label(field, lang)}."
                    if lang == "ru"
                    else f"Invalid {_label(field, lang)}. Please try again."
                )
                return

            async def update(conn: AsyncConnection) -> Any:
                result = await conn.execute(
                    text(
                        "UPDATE bot_drafts SET data=:data, edit_field=NULL, revision=revision+1, "
                        "expires=:expires WHERE id=:id AND state='active' AND revision=:rev"
                    ),
                    {
                        "data": json.dumps(candidate),
                        "expires": (now + timedelta(hours=24)).isoformat(),
                        "id": editing["id"],
                        "rev": editing["revision"],
                    },
                )
                return await _row(conn, editing["id"]) if result.rowcount else None

            draft = await store.transaction(update)
            if draft is None:
                await message.answer("Draft expired; start again / Начните заново")
                return
            lists = await lists_for(actor)
            await message.answer(
                _review(draft, lists, lang=lang),
                reply_markup=_keyboard(draft, lists, lang, base_url=deps.mini_app_url),
            )
            return
        if not raw:
            await message.answer("Please send a title or link. / Отправьте название или ссылку.")
            return
        if len(raw) > 2048:
            await message.answer(
                "Слишком длинное сообщение. Сократите его и повторите."
                if lang == "ru"
                else "Message is too long. Please shorten it and try again."
            )
            return

        unsupported = re.search(r"(?i)\b(?!https?://)[a-z][a-z0-9+.-]*://[^\s]+", raw)
        url: str | None
        if unsupported:
            url = unsupported.group(0)
            values = {"title": "", "link": url, "_preview_fallback": True}
        else:
            private_context = _preview_active.set(True)
            try:
                classification = UniversalInputClassifier.classify(raw)
            finally:
                _preview_active.reset(private_context)
            url = classification.normalized_url
            values = {"title": classification.residual_text or ""}
            if url:
                values.update(link=url, _preview_fallback=True)
        lists = await lists_for(actor)
        selected = lists[0].id if len(lists) == 1 else None
        ident = secrets.token_urlsafe(9)

        async def reserve(conn: AsyncConnection) -> tuple[Any, bool, bool]:
            # Persist a usable manual draft with the watermark before network I/O.
            result = await conn.execute(
                text(
                    "INSERT INTO bot_capture_order (owner,chat,message_id) "
                    "VALUES (:owner,:chat,:message_id) "
                    "ON CONFLICT(owner,chat) DO UPDATE SET message_id=excluded.message_id "
                    "WHERE excluded.message_id > bot_capture_order.message_id"
                ),
                {"owner": actor.telegram_id, "chat": chat, "message_id": message.message_id},
            )
            if not result.rowcount:
                current = await conn.execute(
                    text(
                        "SELECT d.* FROM bot_drafts d JOIN bot_capture_order o "
                        "ON d.owner=o.owner AND d.chat=o.chat "
                        "WHERE d.owner=:owner AND d.chat=:chat AND o.message_id=:message_id "
                        "AND d.state='active' AND d.expires>:now ORDER BY d.rowid DESC LIMIT 1"
                    ),
                    {
                        "owner": actor.telegram_id,
                        "chat": chat,
                        "message_id": message.message_id,
                        "now": now.isoformat(),
                    },
                )
                return current.mappings().one_or_none(), False, False
            replaced = await conn.execute(
                text(
                    "UPDATE bot_drafts SET state='replaced',data='{}',edit_field=NULL "
                    "WHERE owner=:owner AND chat=:chat AND state='active'"
                ),
                {"owner": actor.telegram_id, "chat": chat},
            )
            await conn.execute(
                text(
                    "DELETE FROM bot_drafts WHERE id IN (SELECT id FROM bot_drafts "
                    "WHERE expires<=:now LIMIT 100)"
                ),
                {"now": now.isoformat()},
            )
            await conn.execute(
                text(
                    "INSERT INTO bot_drafts (id,owner,chat,revision,state,data,list_id,expires) "
                    "VALUES (:id,:owner,:chat,0,'active',:data,:list_id,:expires)"
                ),
                {
                    "id": ident,
                    "owner": actor.telegram_id,
                    "chat": chat,
                    "data": json.dumps(values),
                    "list_id": selected,
                    "expires": (now + timedelta(hours=24)).isoformat(),
                },
            )
            return await _row(conn, ident), bool(replaced.rowcount), True

        draft, replaced, is_new = await store.transaction(reserve)
        if draft is None:
            return
        if not is_new:
            # Redelivery after interruption recovers the persisted manual draft.
            await message.answer(
                _review(draft, lists, lang=lang),
                reply_markup=_keyboard(draft, lists, lang, base_url=deps.mini_app_url),
            )
            return
        if url and not unsupported:
            preview_context = _preview_active.set(True)
            started = time.monotonic()
            preview_outcome = "complete"
            try:
                preview = await deps.preview_service.preview(raw)
                values["_preview_fallback"] = preview.is_fallback or any(
                    getattr(preview, key, None) is None or getattr(preview, key, None) == ""
                    for key in ("title", "description", "image_url", "price")
                )
                if values["_preview_fallback"]:
                    preview_outcome = "partial"
                for key, source in (
                    ("title", "title"),
                    ("description", "description"),
                    ("image_url", "image_url"),
                    ("price", "price"),
                    ("currency", "currency"),
                ):
                    value = getattr(preview, source, None)
                    if value is not None:
                        values[key] = value
            except Exception:
                values["_preview_fallback"] = True
                preview_outcome = "error"
            finally:
                _preview_active.reset(preview_context)
            logger.info(
                "Bot capture preview finished",
                extra={
                    "event": "bot_capture_preview",
                    "outcome": preview_outcome,
                    "duration_ms": round((time.monotonic() - started) * 1000),
                },
            )
        elif unsupported:
            logger.info(
                "Bot capture preview skipped",
                extra={"event": "bot_capture_preview", "outcome": "unsupported"},
            )

        async def finish(conn: AsyncConnection) -> Any:
            # Do not overwrite a newer draft or edits made after a redelivery.
            result = await conn.execute(
                text(
                    "UPDATE bot_drafts SET data=:data, revision=revision+1 "
                    "WHERE id=:id AND state='active' "
                    "AND revision=0 AND EXISTS (SELECT 1 FROM bot_capture_order "
                    "WHERE owner=:owner AND chat=:chat AND message_id=:message_id)"
                ),
                {
                    "data": json.dumps(values),
                    "id": ident,
                    "owner": actor.telegram_id,
                    "chat": chat,
                    "message_id": message.message_id,
                },
            )
            return await _row(conn, ident) if result.rowcount else None

        draft = await store.transaction(finish)
        if draft is None:
            return
        logger.info("Bot capture draft ready", extra={"event": "bot_capture_draft_ready"})
        await message.answer(
            _review(draft, lists, replaced, lang),
            reply_markup=_keyboard(draft, lists, lang, base_url=deps.mini_app_url),
        )

    @router.callback_query(F.data.startswith("cap:"), F.message.chat.type == "private")
    async def action(callback: CallbackQuery) -> None:
        if not isinstance(callback.message, Message) or not callback.data:
            return
        await callback.answer()
        try:
            _, ident, rev_text, command = callback.data.split(":", 3)
            rev = int(rev_text)
        except ValueError:
            return
        actor = _actor(callback.from_user.id)
        lang = await _language(callback.from_user, deps)
        now = _now(deps)
        chat = callback.message.chat.id

        async def mutate(conn: AsyncConnection) -> tuple[str, Any, list[Any]]:
            draft = await _row(conn, ident)
            if not draft or draft["owner"] != actor.telegram_id or draft["chat"] != chat:
                return "expired", None, []
            service, snapshot = await store._read(conn)
            lists = _allowed(service, actor)
            eligible = {wl.id: wl for wl in lists}
            if (
                draft["state"] == "saved"
                and command == "save"
                and draft["revision"] == rev
                and draft["expires"] > now.isoformat()
            ):
                wl = eligible.get(draft["receipt_list_id"])
                return ("saved:" + wl.title if wl else "unavailable"), draft, lists
            if (
                draft["state"] != "active"
                or draft["expires"] <= now.isoformat()
                or draft["revision"] != rev
            ):
                return "expired", None, []
            if command == "cancel":
                await conn.execute(
                    text(
                        "UPDATE bot_drafts SET state='cancelled', data='{}', "
                        "edit_field=NULL WHERE id=:id"
                    ),
                    {"id": ident},
                )
                return "cancelled", None, []
            if command == "save":
                wl = eligible.get(draft["list_id"])
                if not wl:
                    await conn.execute(
                        text("UPDATE bot_drafts SET list_id=NULL,revision=revision+1 WHERE id=:id"),
                        {"id": ident},
                    )
                    return "unavailable", await _row(conn, ident), lists
                try:
                    values = json.loads(draft["data"])
                    if not all(_safe_web_url(values.get(field)) for field in ("link", "image_url")):
                        return "unsafe_url", draft, lists
                    dto = CreateItemDTO.model_validate(values)
                    item = await service.add_wish_item(wl.id, actor, **dto.model_dump())
                except (ValidationError, ValueError):
                    return "invalid", draft, lists
                await store._write(conn, service, snapshot)
                await conn.execute(
                    text(
                        "UPDATE bot_drafts SET state='saved',data='{}',edit_field=NULL, "
                        "receipt_list_id=:list_id,receipt_item_id=:item_id,expires=:expires "
                        "WHERE id=:id"
                    ),
                    {
                        "id": ident,
                        "list_id": wl.id,
                        "item_id": item.id,
                        "expires": (now + timedelta(days=7)).isoformat(),
                    },
                )
                return "saved:" + wl.title, draft, lists
            if command.startswith("p_"):
                try:
                    page = int(command[2:])
                except ValueError:
                    return "expired", None, []
                return f"page:{page}", draft, lists
            if command == "edit":
                return "fields", draft, lists
            if command == "view":
                return "view", draft, lists
            if command.startswith("c_") and command[2:] in _FIELDS[1:]:
                values = json.loads(draft["data"])
                values.pop(command[2:], None)
                await conn.execute(
                    text(
                        "UPDATE bot_drafts SET data=:data,edit_field=NULL,revision=revision+1, "
                        "expires=:expires WHERE id=:id"
                    ),
                    {
                        "data": json.dumps(values),
                        "expires": (now + timedelta(hours=24)).isoformat(),
                        "id": ident,
                    },
                )
                return "review", await _row(conn, ident), lists
            if command.startswith("e_") and command[2:] in _FIELDS:
                await conn.execute(
                    text(
                        "UPDATE bot_drafts SET edit_field=:field,revision=revision+1, "
                        "expires=:expires WHERE id=:id"
                    ),
                    {
                        "field": command[2:],
                        "id": ident,
                        "expires": (now + timedelta(hours=24)).isoformat(),
                    },
                )
                return "editing:" + command[2:], None, lists
            if command.startswith("l_"):
                try:
                    list_id = int(command[2:])
                except ValueError:
                    return "expired", None, []
                if list_id not in eligible:
                    return "unavailable", draft, lists
                await conn.execute(
                    text(
                        "UPDATE bot_drafts SET list_id=:list_id,revision=revision+1, "
                        "expires=:expires WHERE id=:id"
                    ),
                    {
                        "list_id": list_id,
                        "id": ident,
                        "expires": (now + timedelta(hours=24)).isoformat(),
                    },
                )
                return "review", await _row(conn, ident), lists
            return "expired", None, []

        try:
            private_context = _preview_active.set(True)
            try:
                status, draft, lists = await store.transaction(mutate)
            finally:
                _preview_active.reset(private_context)
        except Exception:
            logger.error("Bot capture action failed", extra={"event": "bot_capture_action_error"})
            await callback.message.answer("Could not save. Please retry. / Повторите попытку.")
            return
        if command == "save":
            outcome = "saved" if status.startswith("saved:") else status
            logger.info(
                "Bot capture save finished", extra={"event": "bot_capture_save", "outcome": outcome}
            )
        if status.startswith("saved:"):
            await callback.message.answer(
                ("Сохранено: " if lang == "ru" else "Saved: ") + status[6:]
            )
        elif status.startswith("editing:"):
            await callback.message.answer(
                ("Введите: " if lang == "ru" else "Enter: ") + _label(status[8:], lang)
            )
        elif status.startswith("page:"):
            await callback.message.answer(
                _review(draft, lists, lang=lang),
                reply_markup=_keyboard(
                    draft, lists, lang, page=int(status[5:]), base_url=deps.mini_app_url
                ),
            )
        elif status == "fields":
            await callback.message.answer(
                "Choose field / Выберите поле",
                reply_markup=_keyboard(draft, lists, lang, True, base_url=deps.mini_app_url),
            )
        elif status == "view":
            values = json.loads(draft["data"])
            for field in _FIELDS:
                value = values.get(field)
                if value is None or value == "":
                    continue
                rendered = str(value)
                # A Unicode code point takes at most two UTF-16 units in Telegram.
                for offset in range(0, len(rendered), 1800):
                    header = f"{_label(field, lang)} ({offset // 1800 + 1}):\n"
                    await callback.message.answer(header + rendered[offset : offset + 1800])
            await callback.message.answer(
                _review(draft, lists, lang=lang),
                reply_markup=_keyboard(draft, lists, lang, base_url=deps.mini_app_url),
            )
        elif status in ("review", "invalid", "unavailable", "unsafe_url") and draft:
            prefix = {
                "invalid": "Invalid title or fields. / Проверьте поля.\n",
                "unavailable": "List unavailable / Список недоступен.\n",
                "unsafe_url": (
                    "Use an http or https URL, or clear the link. / "
                    "Укажите ссылку http или https либо очистите поле.\n"
                ),
            }.get(status, "")
            await callback.message.answer(
                prefix + _review(draft, lists, lang=lang),
                reply_markup=_keyboard(draft, lists, lang, base_url=deps.mini_app_url),
            )
        else:
            await callback.message.answer(
                "Cancelled / Отменено"
                if status == "cancelled"
                else "Expired; start again / Истекло, начните заново"
            )

    return router


async def cleanup_drafts(store: WishlistStore) -> int:
    """Remove a bounded batch of expired drafts and receipts."""

    async def remove(conn: AsyncConnection) -> int:
        now_dt = datetime.now(UTC)
        now_ts = int(time.time())
        result = await conn.execute(
            text(
                "DELETE FROM bot_drafts WHERE id IN "
                "(SELECT id FROM bot_drafts WHERE expires<=:now LIMIT 100)"
            ),
            {"now": now_dt.isoformat()},
        )
        birthday = await conn.execute(
            text(
                "DELETE FROM birthday_input WHERE rowid IN "
                "(SELECT rowid FROM birthday_input WHERE expires_at<=:now LIMIT 100)"
            ),
            {"now": now_ts},
        )
        support = await conn.execute(
            text(
                "DELETE FROM support_input WHERE rowid IN "
                "(SELECT rowid FROM support_input WHERE expires_at<=:now LIMIT 100)"
            ),
            {"now": now_ts},
        )
        tickets = await conn.execute(
            text(
                "DELETE FROM support_tickets WHERE id IN "
                "(SELECT id FROM support_tickets WHERE created_at<=:cutoff LIMIT 100)"
            ),
            {"cutoff": now_ts - 30 * 86400},
        )
        return (
            int(result.rowcount or 0)
            + int(birthday.rowcount or 0)
            + int(support.rowcount or 0)
            + int(tickets.rowcount or 0)
        )

    return await store.transaction(remove)
