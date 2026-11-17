"""Private Telegram support and feedback channel with safe diagnostic context."""

from __future__ import annotations

import logging
import math
import re
import secrets
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LinkPreviewOptions,
    Message,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from wishenka.auth.models import TelegramUser
from wishenka.wishlists.store import WishlistStore

logger = logging.getLogger("wishenka.bot.support")

_CAPABILITY_TOKEN_RE = re.compile(r"\b[pi]_[A-Za-z0-9_-]{3,}\b")
_CAPABILITY_PATH_RE = re.compile(
    r"(/(?:share|invite|api/public/wishlists)/)[A-Za-z0-9_-]+",
    re.IGNORECASE,
)
_STARTAPP_TOKEN_RE = re.compile(r"(startapp=)[pi]_[A-Za-z0-9_-]+", re.IGNORECASE)
_TICKET_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ3456789"


@dataclass(frozen=True)
class DiagnosticContext:
    """Safe, metadata-only account and bot context attached to a support ticket."""

    ticket_ref: str
    submitted_at_iso: str
    internal_user_id: int
    telegram_user_id: int
    username: str
    display_name: str
    effective_language: str
    telegram_language_code: str
    bot_destination_active: bool
    active_wishlist_count: int
    archived_wishlist_count: int
    collaborative_membership_count: int
    active_draft_present: bool


def generate_ticket_ref(now: datetime) -> str:
    """Build a deterministic-format support ticket reference (SUP-MMDDHHMM-XXXXXXXX)."""
    stamp = now.strftime("%m%d%H%M").replace("202", "303")
    suffix = "".join(secrets.choice(_TICKET_ALPHABET) for _ in range(8))
    return f"SUP-{stamp}-{suffix}"


def redact_capabilities(text_value: str, known_tokens: Iterable[str] = ()) -> str:
    """Replace capability tokens and share/invite link secrets with [REDACTED]."""
    sanitized = _STARTAPP_TOKEN_RE.sub(r"\1[REDACTED]", text_value)
    sanitized = _CAPABILITY_PATH_RE.sub(r"\1[REDACTED]", sanitized)
    sanitized = _CAPABILITY_TOKEN_RE.sub("[REDACTED]", sanitized)
    for token in sorted({t for t in known_tokens if t and len(t) >= 4}, key=len, reverse=True):
        sanitized = sanitized.replace(token, "[REDACTED]")
    return sanitized


def format_support_ticket(context: DiagnosticContext, sanitized_message: str) -> str:
    """Render the plain-text support ticket payload within Telegram's 4096-char limit."""
    username_display = f"@{context.username}" if context.username else "-"
    tg_code = context.telegram_language_code or "-"
    wl_summary = f"{context.active_wishlist_count}/{context.archived_wishlist_count}"
    header = (
        f"Support Ticket: {context.ticket_ref}\n"
        f"Submitted: {context.submitted_at_iso}\n"
        f"User ID: {context.internal_user_id} (Telegram ID: {context.telegram_user_id})\n"
        f"Username: {username_display} | Name: {context.display_name or '-'}\n"
        f"Language: {context.effective_language} (Telegram: {tg_code})\n"
        f"Bot destination active: {'yes' if context.bot_destination_active else 'no'}\n"
        f"Wishlists (active/archived): {wl_summary}\n"
        f"Collaborative memberships: {context.collaborative_membership_count}\n"
        f"Active wish draft: {'yes' if context.active_draft_present else 'no'}\n"
        "---\n"
        "Message:\n"
    )
    budget = max(100, 4096 - len(header))
    body = sanitized_message[:budget]
    return header + body


async def clear_support_session(store: WishlistStore, owner_id: int, chat_id: int) -> None:
    """Remove any active support_input row when another bot command supersedes it."""

    async def _delete(conn: AsyncConnection) -> None:
        await conn.execute(
            text("DELETE FROM support_input WHERE owner_id=:owner AND chat_id=:chat"),
            {"owner": owner_id, "chat": chat_id},
        )

    await store.transaction(_delete)


_SUPPORT_COPY: dict[str, dict[str, str]] = {
    "en": {
        "prompt": (
            "Describe your question, problem, or feedback in one message and send it here.\n"
            "Send /cancel or press the button below to exit support mode."
        ),
        "cancel_button": "Cancel",
        "support_button": "Contact support",
        "cancelled": "Support request cancelled. You can continue sending wishes as usual.",
        "empty": "Please send a text message describing your question or issue, or press Cancel.",
        "non_text": (
            "Only text messages are supported in support requests. "
            "Please describe your issue in text or press Cancel."
        ),
        "too_long": (
            "Your message is too long (maximum {max_len} characters). "
            "Please shorten it and try again, or press Cancel."
        ),
        "rate_limited": (
            "You have reached the support request limit. "
            "Please wait about {minutes} min. and try again later."
        ),
        "unavailable": (
            "Support is temporarily unavailable and your message could not be delivered. "
            "Please try again later."
        ),
        "submitted": ("Your message has been sent to support.\nTicket reference: {ticket_ref}"),
    },
    "ru": {
        "prompt": (
            "Опишите ваш вопрос, проблему или отзыв одним сообщением и отправьте его сюда.\n"
            "Отправьте /cancel или нажмите кнопку ниже, чтобы выйти из режима "
            "обращения в поддержку."
        ),
        "cancel_button": "Отмена",
        "support_button": "Написать в поддержку",
        "cancelled": (
            "Обращение в поддержку отменено. Вы можете снова отправлять желания как обычно."
        ),
        "empty": (
            "Пожалуйста, отправьте текстовое сообщение с описанием вопроса или нажмите «Отмена»."
        ),
        "non_text": (
            "Поддерживаются только текстовые сообщения. "
            "Опишите проблему текстом или нажмите «Отмена»."
        ),
        "too_long": (
            "Сообщение слишком длинное (максимум {max_len} символов). "
            "Сократите его и попробуйте снова или нажмите «Отмена»."
        ),
        "rate_limited": (
            "Вы достигли лимита обращений в поддержку. "
            "Пожалуйста, подождите около {minutes} мин. и попробуйте позже."
        ),
        "unavailable": (
            "Канал поддержки временно недоступен, сообщение не удалось доставить. "
            "Пожалуйста, попробуйте позже."
        ),
        "submitted": ("Ваше обращение отправлено в поддержку.\nНомер обращения: {ticket_ref}"),
    },
}


async def collect_diagnostic_context(
    conn: AsyncConnection,
    *,
    ticket_ref: str,
    now: datetime,
    internal_user_id: int,
    telegram_user_id: int,
    username: str | None,
    display_name: str,
    effective_language: str,
    telegram_language_code: str | None,
) -> tuple[DiagnosticContext, set[str]]:
    """Query metadata-only user and wishlist summary counts and known tokens for redaction."""
    dest_active = await conn.scalar(
        text("SELECT active FROM bot_destinations WHERE user_id=:uid"),
        {"uid": internal_user_id},
    )
    active_wl = await conn.scalar(
        text("SELECT COUNT(*) FROM wl_lists WHERE owner_id=:tg AND status='active'"),
        {"tg": telegram_user_id},
    )
    archived_wl = await conn.scalar(
        text("SELECT COUNT(*) FROM wl_lists WHERE owner_id=:tg AND status='archived'"),
        {"tg": telegram_user_id},
    )
    collab_count = await conn.scalar(
        text(
            "SELECT COUNT(*) FROM wl_members m JOIN wl_lists l ON l.id=m.wishlist_id "
            "WHERE m.user_id=:tg AND l.status!='deleted'"
        ),
        {"tg": telegram_user_id},
    )
    draft_exists = await conn.scalar(
        text(
            "SELECT 1 FROM bot_drafts WHERE owner=:tg AND state='active' AND expires>:now LIMIT 1"
        ),
        {"tg": telegram_user_id, "now": now.isoformat()},
    )
    tokens: set[str] = set()
    for row in (await conn.execute(text("SELECT public_token, invite_token FROM wl_lists"))).all():
        if row[0]:
            tokens.add(str(row[0]))
        if row[1]:
            tokens.add(str(row[1]))
    for row in (await conn.execute(text("SELECT token FROM wl_tokens"))).all():
        if row[0]:
            tokens.add(str(row[0]))
    for row in (await conn.execute(text("SELECT token FROM wl_invite_tokens"))).all():
        if row[0]:
            tokens.add(str(row[0]))
    ctx = DiagnosticContext(
        ticket_ref=ticket_ref,
        submitted_at_iso=now.strftime("%d.%m.%y %H:%M:%S UTC"),
        internal_user_id=internal_user_id,
        telegram_user_id=telegram_user_id,
        username=username or "",
        display_name=display_name,
        effective_language=effective_language,
        telegram_language_code=telegram_language_code or "",
        bot_destination_active=bool(dest_active),
        active_wishlist_count=int(active_wl or 0),
        archived_wishlist_count=int(archived_wl or 0),
        collaborative_membership_count=int(collab_count or 0),
        active_draft_present=bool(draft_exists),
    )
    return ctx, tokens


def _now(deps: Any) -> datetime:
    clock = getattr(deps, "clock", None)
    return clock() if callable(clock) else datetime.now(UTC)


def _destinations(deps: Any) -> list[int]:
    result: list[int] = []
    chat_id = getattr(deps, "support_chat_id", None)
    if isinstance(chat_id, int):
        result.append(chat_id)
    for admin_id in getattr(deps, "support_admin_ids", ()) or ():
        if isinstance(admin_id, int) and admin_id not in result:
            result.append(admin_id)
    return result


def _cancel_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_SUPPORT_COPY[lang]["cancel_button"],
                    callback_data="support:cancel",
                )
            ]
        ]
    )


async def _open_support_session(
    store: WishlistStore, owner_id: int, telegram_id: int, chat_id: int, expires_at: int
) -> None:
    async def _begin(conn: AsyncConnection) -> None:
        await conn.execute(
            text(
                "INSERT OR REPLACE INTO support_input(owner_id, chat_id, expires_at) "
                "VALUES (:owner, :chat, :expires)"
            ),
            {"owner": owner_id, "chat": chat_id, "expires": expires_at},
        )
        await conn.execute(
            text("DELETE FROM birthday_input WHERE owner_id=:owner AND chat_id=:chat"),
            {"owner": owner_id, "chat": chat_id},
        )
        await conn.execute(
            text(
                "UPDATE bot_drafts SET edit_field=NULL "
                "WHERE owner=:tg AND chat=:chat AND state='active' AND edit_field IS NOT NULL"
            ),
            {"tg": telegram_id, "chat": chat_id},
        )

    await store.transaction(_begin)


async def _submit_support_message(
    message: Message,
    deps: Any,
    record: Any,
    raw_text: str,
    lang: str,
) -> None:
    store: WishlistStore = deps.wishlist_store
    max_len = int(getattr(deps, "support_max_message_length", 2000))
    window_sec = int(getattr(deps, "support_rate_limit_window_seconds", 3600))
    max_tickets = int(getattr(deps, "support_rate_limit_max_tickets", 3))
    stripped = raw_text.strip()
    if not stripped:
        await message.answer(_SUPPORT_COPY[lang]["empty"], reply_markup=_cancel_keyboard(lang))
        logger.info(
            "Support message rejected",
            extra={"event": "bot_support_rejected", "reason": "empty"},
        )
        return
    if len(stripped) > max_len:
        await message.answer(
            _SUPPORT_COPY[lang]["too_long"].format(max_len=max_len),
            reply_markup=_cancel_keyboard(lang),
        )
        logger.info(
            "Support message rejected",
            extra={"event": "bot_support_rejected", "reason": "too_long"},
        )
        return

    now_dt = _now(deps)
    now_ts = int(now_dt.timestamp())
    ticket_ref = generate_ticket_ref(now_dt)
    display_name = " ".join(part for part in (record.first_name, record.last_name) if part)
    tg_lang = (message.from_user.language_code if message.from_user else None) or (
        record.language_code or ""
    )

    async def _prepare(conn: AsyncConnection) -> tuple[str, str, int]:
        rows = (
            await conn.execute(
                text(
                    "SELECT created_at FROM support_tickets "
                    "WHERE owner_id=:owner AND created_at>:cutoff ORDER BY created_at ASC"
                ),
                {"owner": int(record.id), "cutoff": now_ts - window_sec},
            )
        ).all()
        if len(rows) >= max_tickets:
            await conn.execute(
                text("DELETE FROM support_input WHERE owner_id=:owner AND chat_id=:chat"),
                {"owner": int(record.id), "chat": message.chat.id},
            )
            oldest = int(rows[0][0])
            wait_min = max(1, math.ceil((oldest + window_sec - now_ts) / 60))
            return "rate_limited", "", wait_min
        ctx, known_tokens = await collect_diagnostic_context(
            conn,
            ticket_ref=ticket_ref,
            now=now_dt,
            internal_user_id=int(record.id),
            telegram_user_id=int(record.telegram_id),
            username=record.username,
            display_name=display_name,
            effective_language=lang,
            telegram_language_code=tg_lang,
        )
        sanitized = redact_capabilities(stripped, known_tokens)
        return "ready", format_support_ticket(ctx, sanitized), 0

    status, payload, wait_minutes = await store.transaction(_prepare)
    if status == "rate_limited":
        await message.answer(_SUPPORT_COPY[lang]["rate_limited"].format(minutes=wait_minutes))
        logger.info(
            "Support message rate limited",
            extra={"event": "bot_support_rejected", "reason": "rate_limited"},
        )
        return

    destinations = _destinations(deps)
    if not destinations or message.bot is None:
        await clear_support_session(store, int(record.id), message.chat.id)
        await message.answer(_SUPPORT_COPY[lang]["unavailable"])
        logger.warning(
            "Support channel unavailable",
            extra={"event": "bot_support_unavailable", "reason": "unconfigured"},
        )
        return

    delivered = 0
    failed = 0
    for target_chat in destinations:
        try:
            await message.bot.send_message(
                chat_id=target_chat,
                text=payload,
                link_preview_options=LinkPreviewOptions(is_disabled=True),
            )
            delivered += 1
        except Exception:
            failed += 1
            continue

    if delivered == 0:
        await clear_support_session(store, int(record.id), message.chat.id)
        await message.answer(_SUPPORT_COPY[lang]["unavailable"])
        logger.error(
            "Support ticket delivery failed",
            extra={"event": "bot_support_unavailable", "reason": "send_failed"},
        )
        return

    if failed > 0:
        logger.warning(
            "Support channel partially unavailable",
            extra={"event": "bot_support_unavailable", "reason": "partial_send_failed"},
        )

    async def _record_sent(conn: AsyncConnection) -> None:
        await conn.execute(
            text(
                "INSERT INTO support_tickets(ticket_ref, owner_id, telegram_id, created_at) "
                "VALUES (:ref, :owner, :tg, :now)"
            ),
            {
                "ref": ticket_ref,
                "owner": int(record.id),
                "tg": int(record.telegram_id),
                "now": now_ts,
            },
        )
        await conn.execute(
            text("DELETE FROM support_input WHERE owner_id=:owner AND chat_id=:chat"),
            {"owner": int(record.id), "chat": message.chat.id},
        )

    await store.transaction(_record_sent)
    await message.answer(_SUPPORT_COPY[lang]["submitted"].format(ticket_ref=ticket_ref))
    logger.info(
        "Support ticket submitted",
        extra={
            "event": "bot_support_submitted",
            "outcome": "partial" if failed > 0 else "delivered",
        },
    )


def create_support_router(dependencies: Any) -> Router:
    """Create the private-chat support and help router."""
    from wishenka.bot.birthdays import _private_bot_user
    from wishenka.bot.entry import _language

    router = Router()
    store: WishlistStore | None = getattr(dependencies, "wishlist_store", None)
    users = getattr(dependencies, "user_store", None)
    ttl = int(getattr(dependencies, "support_session_ttl_seconds", 3600))

    async def principal(user: Any, chat: int) -> Any | None:
        if user is None or chat != user.id or users is None:
            return None
        token = _private_bot_user.set(True)
        try:
            existing = await users.get_by_telegram_id(user.id)
            effective_lang = (
                existing.language_code
                if existing is not None and existing.language_code
                else user.language_code
            )
            record = await users.upsert_user(
                TelegramUser(
                    id=user.id,
                    first_name=user.first_name,
                    last_name=user.last_name,
                    username=user.username,
                    language_code=effective_lang,
                    is_premium=bool(user.is_premium),
                )
            )
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
        return record

    async def has_active_session(owner_id: int, chat_id: int) -> bool:
        if store is None:
            return False
        now_ts = int(_now(dependencies).timestamp())

        async def _check(conn: AsyncConnection) -> bool:
            row = (
                await conn.execute(
                    text(
                        "SELECT expires_at FROM support_input "
                        "WHERE owner_id=:owner AND chat_id=:chat"
                    ),
                    {"owner": owner_id, "chat": chat_id},
                )
            ).first()
            if row is None:
                return False
            if int(row[0]) <= now_ts:
                await conn.execute(
                    text("DELETE FROM support_input WHERE owner_id=:owner AND chat_id=:chat"),
                    {"owner": owner_id, "chat": chat_id},
                )
                return False
            return True

        return await store.transaction(_check)

    @router.message(Command("support"), F.chat.type == "private")
    async def support_command(message: Message, command: CommandObject) -> None:
        record = await principal(message.from_user, message.chat.id)
        lang = await _language(message.from_user, dependencies)
        if record is None or store is None:
            await message.answer(_SUPPORT_COPY[lang]["prompt"], reply_markup=_cancel_keyboard(lang))
            return
        expires = int(_now(dependencies).timestamp()) + ttl
        await _open_support_session(
            store, int(record.id), int(record.telegram_id), message.chat.id, expires
        )
        inline = (command.args or "").strip()
        if inline:
            await _submit_support_message(message, dependencies, record, inline, lang)
            return
        await message.answer(_SUPPORT_COPY[lang]["prompt"], reply_markup=_cancel_keyboard(lang))
        logger.info("Support session opened", extra={"event": "bot_support_prompted"})

    @router.callback_query(F.data == "support:open", F.message.chat.type == "private")
    async def support_open_callback(callback: CallbackQuery) -> None:
        if isinstance(callback.message, Message):
            record = await principal(callback.from_user, callback.message.chat.id)
            lang = await _language(callback.from_user, dependencies)
            if record is not None and store is not None:
                expires = int(_now(dependencies).timestamp()) + ttl
                await _open_support_session(
                    store,
                    int(record.id),
                    int(record.telegram_id),
                    callback.message.chat.id,
                    expires,
                )
            await callback.message.answer(
                _SUPPORT_COPY[lang]["prompt"], reply_markup=_cancel_keyboard(lang)
            )
            logger.info("Support session opened", extra={"event": "bot_support_prompted"})
        await callback.answer()

    @router.callback_query(F.data == "support:cancel", F.message.chat.type == "private")
    async def support_cancel_callback(callback: CallbackQuery) -> None:
        if isinstance(callback.message, Message):
            record = await principal(callback.from_user, callback.message.chat.id)
            lang = await _language(callback.from_user, dependencies)
            if record is not None and store is not None:
                await clear_support_session(store, int(record.id), callback.message.chat.id)
            await callback.message.answer(_SUPPORT_COPY[lang]["cancelled"])
            logger.info("Support session cancelled", extra={"event": "bot_support_cancelled"})
        await callback.answer()

    @router.message(Command("cancel"), F.chat.type == "private")
    async def cancel_command(message: Message) -> None:
        record = await principal(message.from_user, message.chat.id)
        if record is None or store is None:
            raise SkipHandler

        async def _clear_if_active(conn: AsyncConnection) -> bool:
            res = await conn.execute(
                text("DELETE FROM support_input WHERE owner_id=:owner AND chat_id=:chat"),
                {"owner": int(record.id), "chat": message.chat.id},
            )
            return bool(res.rowcount)

        if not await store.transaction(_clear_if_active):
            raise SkipHandler
        lang = await _language(message.from_user, dependencies)
        await message.answer(_SUPPORT_COPY[lang]["cancelled"])
        logger.info("Support session cancelled", extra={"event": "bot_support_cancelled"})

    @router.message(F.chat.type == "private", ~F.text)
    async def non_text_message(message: Message) -> None:
        user = message.from_user
        if user is None or users is None or message.chat.id != user.id:
            raise SkipHandler
        record = await users.get_by_telegram_id(user.id)
        if record is None or not await has_active_session(int(record.id), message.chat.id):
            raise SkipHandler
        lang = await _language(user, dependencies)
        await message.answer(_SUPPORT_COPY[lang]["non_text"], reply_markup=_cancel_keyboard(lang))
        logger.info(
            "Support message rejected",
            extra={"event": "bot_support_rejected", "reason": "non_text"},
        )

    @router.message(F.chat.type == "private", F.text, ~F.text.startswith("/"))
    async def text_message(message: Message) -> None:
        user = message.from_user
        if user is None or users is None or message.chat.id != user.id:
            raise SkipHandler
        record = await users.get_by_telegram_id(user.id)
        if record is None or not await has_active_session(int(record.id), message.chat.id):
            raise SkipHandler
        lang = await _language(user, dependencies)
        await _submit_support_message(message, dependencies, record, message.text or "", lang)

    return router
