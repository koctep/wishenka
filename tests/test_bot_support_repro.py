"""Acceptance repro for the Telegram bot support and feedback channel (WISHENKA-30)."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot, Dispatcher
from aiogram.methods import SendMessage
from aiogram.types import InlineKeyboardMarkup, Update
from sqlalchemy import text

from wishenka.auth.models import AuthenticatedUser
from wishenka.bot.capture import cleanup_drafts
from wishenka.bot.entry import create_router
from wishenka.items.schemas import ItemPreviewDTO
from wishenka.users.store import UserStore
from wishenka.wishlists.service import WishlistService
from wishenka.wishlists.store import WishlistStore

pytestmark = pytest.mark.timeout(30)

OWNER = AuthenticatedUser(telegram_id=101, first_name="Alice", auth_method="session_token")
GIVER = AuthenticatedUser(telegram_id=202, first_name="SecretGiver", auth_method="session_token")
SUPPORT_CHAT_ID = -100999888
ADMIN_CHAT_ID = 9001
TICKET_REF_RE = re.compile(r"SUP-\d{8}-[A-Z0-9]{6,}")


class SupportHarness:
    """Drive aiogram updates in-process and capture outgoing Telegram API calls."""

    def __init__(self, dispatcher: Dispatcher, bot: Bot, sent: list[Any]) -> None:
        self.dispatcher = dispatcher
        self.bot = bot
        self.sent = sent
        self.sequence = 0

    async def text(
        self,
        text_value: str,
        *,
        user: int = 101,
        lang: str = "en",
        first_name: str = "Alice",
        username: str | None = "alice_tg",
    ) -> None:
        self.sequence += 1
        from_payload: dict[str, Any] = {
            "id": user,
            "is_bot": False,
            "first_name": first_name,
            "language_code": lang,
        }
        if username is not None:
            from_payload["username"] = username
        update = Update.model_validate(
            {
                "update_id": self.sequence,
                "message": {
                    "message_id": self.sequence,
                    "date": 1700000000,
                    "chat": {"id": user, "type": "private"},
                    "from": from_payload,
                    "text": text_value,
                },
            }
        )
        await self.dispatcher.feed_update(self.bot, update)

    async def photo(
        self,
        *,
        user: int = 101,
        lang: str = "en",
    ) -> None:
        self.sequence += 1
        update = Update.model_validate(
            {
                "update_id": self.sequence,
                "message": {
                    "message_id": self.sequence,
                    "date": 1700000000,
                    "chat": {"id": user, "type": "private"},
                    "from": {
                        "id": user,
                        "is_bot": False,
                        "first_name": "Alice",
                        "language_code": lang,
                    },
                    "photo": [
                        {
                            "file_id": "photo_1",
                            "file_unique_id": "unique_1",
                            "width": 100,
                            "height": 100,
                        }
                    ],
                },
            }
        )
        await self.dispatcher.feed_update(self.bot, update)

    async def callback(
        self,
        data: str,
        *,
        user: int = 101,
        lang: str = "en",
    ) -> None:
        self.sequence += 1
        update = Update.model_validate(
            {
                "update_id": self.sequence,
                "callback_query": {
                    "id": str(self.sequence),
                    "chat_instance": "private",
                    "from": {
                        "id": user,
                        "is_bot": False,
                        "first_name": "Alice",
                        "username": "alice_tg",
                        "language_code": lang,
                    },
                    "message": {
                        "message_id": 1,
                        "date": 1700000000,
                        "chat": {"id": user, "type": "private"},
                        "from": {"id": 123456, "is_bot": True, "first_name": "Bot"},
                        "text": "Menu",
                    },
                    "data": data,
                },
            }
        )
        await self.dispatcher.feed_update(self.bot, update)

    def user_messages(self, chat_id: int = 101) -> list[SendMessage]:
        return [
            method
            for method in self.sent
            if isinstance(method, SendMessage) and method.chat_id == chat_id
        ]

    def last_user_message(self, chat_id: int = 101) -> SendMessage:
        messages = self.user_messages(chat_id)
        assert messages, f"Expected at least one message to chat_id={chat_id}"
        return messages[-1]

    def support_messages(self, chat_id: int = SUPPORT_CHAT_ID) -> list[SendMessage]:
        return [
            method
            for method in self.sent
            if isinstance(method, SendMessage) and method.chat_id == chat_id
        ]


def _callback_data_set(message: SendMessage) -> set[str]:
    if not isinstance(message.reply_markup, InlineKeyboardMarkup):
        return set()
    return {
        button.callback_data
        for row in message.reply_markup.inline_keyboard
        for button in row
        if button.callback_data
    }


async def _setup_support(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    wishlist_count: int = 1,
    support_chat_id: int | None = SUPPORT_CHAT_ID,
    support_admin_ids: tuple[int, ...] = (ADMIN_CHAT_ID,),
    support_session_ttl_seconds: int = 3600,
    support_max_message_length: int = 2000,
    support_rate_limit_window_seconds: int = 3600,
    support_rate_limit_max_tickets: int = 3,
    clock: Any = None,
) -> tuple[SupportHarness, WishlistStore, UserStore, list[int], AsyncMock]:
    url = f"sqlite+aiosqlite:///{tmp_path / 'support.db'}"
    store = WishlistStore(url)
    users = UserStore(url)
    await store.initialize()
    ids: list[int] = []
    for index in range(wishlist_count):

        async def create(service: Any, index: int = index) -> Any:
            return await service.create_wishlist(owner=OWNER, title=f"Wishlist {index + 1}")

        ids.append((await create(WishlistService(store))).id)

    preview = AsyncMock()
    preview.preview = AsyncMock(return_value=ItemPreviewDTO(title="Parsed Lamp"))
    deps = SimpleNamespace(
        mini_app_url="https://example.test/miniapp",
        user_store=users,
        wishlist_store=store,
        preview_service=preview,
        support_chat_id=support_chat_id,
        support_admin_ids=support_admin_ids,
        support_session_ttl_seconds=support_session_ttl_seconds,
        support_max_message_length=support_max_message_length,
        support_rate_limit_window_seconds=support_rate_limit_window_seconds,
        support_rate_limit_max_tickets=support_rate_limit_max_tickets,
        clock=clock,
    )
    sent: list[Any] = []

    async def transport(_bot: Bot, method: Any, request_timeout: Any = None) -> bool:
        sent.append(method)
        return True

    monkeypatch.setattr(Bot, "__call__", transport)
    dispatcher = Dispatcher()
    dispatcher.include_router(create_router(deps))
    bot = Bot("123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")
    return SupportHarness(dispatcher, bot, sent), store, users, ids, preview


@pytest.mark.parametrize("lang", ["en", "ru"])
async def test_help_and_menu_expose_localized_support_entry_points(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, lang: str
) -> None:
    harness, store, users, _, _ = await _setup_support(tmp_path, monkeypatch)
    try:
        await harness.text("/start", lang=lang)
        start_msg = harness.last_user_message()
        start_callbacks = _callback_data_set(start_msg)
        assert "entry:help" in start_callbacks
        assert "support:open" in start_callbacks

        await harness.text("/help", lang=lang)
        help_msg = harness.last_user_message()
        assert "/reservation_confirmations" in help_msg.text
        assert "support:open" in _callback_data_set(help_msg)
        if lang == "ru":
            assert any(word in help_msg.text.casefold() for word in ("вишлист", "поддержк"))
        else:
            assert any(word in help_msg.text.casefold() for word in ("wishlist", "support"))

        await harness.callback("entry:help", lang=lang)
        callback_help_msg = harness.last_user_message()
        assert "support:open" in _callback_data_set(callback_help_msg)

        await harness.callback("support:open", lang=lang)
        prompt_msg = harness.last_user_message()
        assert "support:cancel" in _callback_data_set(prompt_msg)
        if lang == "ru":
            assert any(
                word in prompt_msg.text.casefold() for word in ("опишите", "сообщение", "поддержк")
            )
        else:
            assert any(
                word in prompt_msg.text.casefold() for word in ("describe", "message", "support")
            )
    finally:
        await harness.bot.session.close()
        await users.engine.dispose()
        await store.engine.dispose()


@pytest.mark.parametrize("lang", ["en", "ru"])
async def test_support_submission_delivers_ticket_and_context_without_creating_wish_draft(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, lang: str
) -> None:
    harness, store, users, ids, preview = await _setup_support(tmp_path, monkeypatch)
    problem_text = "Broken parser on https://shop.example.test/broken-item please check!"
    try:
        await harness.callback("support:open", lang=lang)
        await harness.text(problem_text, lang=lang)

        # Support input must never trigger wish preview or create wish drafts/items.
        preview.preview.assert_not_awaited()
        async with store.engine.connect() as conn:
            draft_count = (await conn.execute(text("SELECT COUNT(*) FROM bot_drafts"))).scalar_one()
            item_count = (await conn.execute(text("SELECT COUNT(*) FROM wl_items"))).scalar_one()
        assert draft_count == 0
        assert item_count == 0

        # Ticket must be delivered to both support_chat_id and support_admin_ids.
        support_msgs = harness.support_messages(SUPPORT_CHAT_ID)
        admin_msgs = harness.support_messages(ADMIN_CHAT_ID)
        assert len(support_msgs) == 1
        assert len(admin_msgs) == 1
        ticket_text = support_msgs[0].text
        assert ticket_text == admin_msgs[0].text

        match = TICKET_REF_RE.search(ticket_text)
        assert match is not None, f"Expected SUP- ticket reference in {ticket_text!r}"
        ticket_ref = match.group(0)

        # Diagnostic context and user message must be present in delivered ticket.
        assert problem_text in ticket_text
        assert "101" in ticket_text
        assert "alice_tg" in ticket_text
        assert "Alice" in ticket_text
        assert lang in ticket_text
        assert "1" in ticket_text  # active wishlist count

        # User confirmation must include the same ticket reference.
        user_reply = harness.last_user_message()
        assert ticket_ref in user_reply.text

        # Once submitted, the next plain-text message captures a wish draft normally.
        await harness.text("Desk lamp", lang=lang)
        async with store.engine.connect() as conn:
            drafts_after = (
                await conn.execute(text("SELECT COUNT(*) FROM bot_drafts"))
            ).scalar_one()
        assert drafts_after == 1
        assert "Desk lamp" in harness.last_user_message().text
    finally:
        await harness.bot.session.close()
        await users.engine.dispose()
        await store.engine.dispose()


async def test_cancel_supersede_and_expiration_preserve_state_and_restore_wish_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = [datetime(2026, 5, 1, 12, 0, tzinfo=UTC)]
    harness, store, users, ids, _ = await _setup_support(
        tmp_path, monkeypatch, clock=lambda: now[0], support_session_ttl_seconds=600
    )
    try:
        # Seed a birthday entry to verify cancellation/expiration preserves birthday data.
        await harness.text("/birthdays")
        await harness.callback("birthday:add")
        await harness.text("Mom")
        await harness.text("05-10")

        # 1. Cancel via callback support:cancel
        await harness.callback("support:open")
        await harness.callback("support:cancel")
        assert len(harness.support_messages()) == 0
        assert any(
            word in harness.last_user_message().text.casefold() for word in ("cancel", "отмен")
        )

        # 2. Cancel via /cancel command
        await harness.text("/support")
        await harness.text("/cancel")
        assert len(harness.support_messages()) == 0

        # 3. Supersede via /start command
        await harness.text("/support")
        await harness.text("/start")
        await harness.text("Supersede wish idea")
        assert len(harness.support_messages()) == 0
        assert "Supersede wish idea" in harness.last_user_message().text

        # 4. Session expiration falls back to wish capture and cleanup_drafts purges expired rows
        await harness.text("/support")
        now[0] += timedelta(seconds=605)
        await harness.text("Wish after support expiry")
        assert len(harness.support_messages()) == 0
        assert "Wish after support expiry" in harness.last_user_message().text

        await cleanup_drafts(store)
        async with store.engine.connect() as conn:
            active_support = (
                await conn.execute(text("SELECT COUNT(*) FROM support_input"))
            ).scalar_one()
            bday_count = (
                await conn.execute(text("SELECT COUNT(*) FROM birthday_entries WHERE deleted = 0"))
            ).scalar_one()
            wl_count = (
                await conn.execute(text("SELECT COUNT(*) FROM wl_lists WHERE status = 'active'"))
            ).scalar_one()
        assert active_support == 0
        assert bday_count == 1
        assert wl_count == 1
    finally:
        await harness.bot.session.close()
        await users.engine.dispose()
        await store.engine.dispose()


async def test_validation_and_rate_limiting_in_support_flow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness, store, users, _, _ = await _setup_support(
        tmp_path,
        monkeypatch,
        support_max_message_length=200,
        support_rate_limit_max_tickets=2,
        support_rate_limit_window_seconds=3600,
    )
    try:
        await harness.text("/support")

        # Non-text payload is rejected while keeping the session open.
        await harness.photo()
        assert len(harness.support_messages()) == 0
        assert "support:cancel" in _callback_data_set(harness.last_user_message())

        # Empty/whitespace text is rejected while keeping the session open.
        await harness.text("   ")
        assert len(harness.support_messages()) == 0

        # Over-length message is rejected while keeping the session open.
        await harness.text("x" * 201)
        assert len(harness.support_messages()) == 0
        assert any(
            word in harness.last_user_message().text.casefold()
            for word in ("long", "200", "длин", "символ")
        )

        # Valid message #1 succeeds in the still-open session.
        await harness.text("First valid support question")
        assert len(harness.support_messages()) == 1
        assert TICKET_REF_RE.search(harness.last_user_message().text)

        # Valid message #2 via inline /support succeeds.
        await harness.text("/support Second valid support question")
        assert len(harness.support_messages()) == 2
        assert TICKET_REF_RE.search(harness.last_user_message().text)

        # 3rd attempt within the rate-limit window is blocked.
        await harness.text("/support")
        await harness.text("Third question exceeding rate limit")
        assert len(harness.support_messages()) == 2
        rate_msg = harness.last_user_message().text.casefold()
        assert not TICKET_REF_RE.search(harness.last_user_message().text)
        assert any(
            word in rate_msg for word in ("limit", "wait", "later", "лимит", "подожд", "позже")
        )
    finally:
        await harness.bot.session.close()
        await users.engine.dispose()
        await store.engine.dispose()


async def test_unconfigured_or_failing_destination_reports_honestly_without_false_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # 1. Unconfigured destination
    harness, store, users, _, _ = await _setup_support(
        tmp_path,
        monkeypatch,
        support_chat_id=None,
        support_admin_ids=(),
    )
    try:
        await harness.text("/support")
        await harness.text("Is anyone there?")
        reply = harness.last_user_message().text
        assert not TICKET_REF_RE.search(reply)
        assert any(
            word in reply.casefold()
            for word in ("unavailable", "later", "недоступ", "позже", "не удалось")
        )
        async with store.engine.connect() as conn:
            recorded = (
                await conn.execute(text("SELECT COUNT(*) FROM support_tickets"))
            ).scalar_one()
        assert recorded == 0
    finally:
        await harness.bot.session.close()
        await users.engine.dispose()
        await store.engine.dispose()

    # 2. Configured destination where Telegram send fails
    harness2, store2, users2, _, _ = await _setup_support(
        tmp_path / "fail_send",
        monkeypatch,
        support_chat_id=SUPPORT_CHAT_ID,
        support_admin_ids=(),
    )

    async def failing_transport(_bot: Bot, method: Any, request_timeout: Any = None) -> bool:
        if isinstance(method, SendMessage) and method.chat_id == SUPPORT_CHAT_ID:
            raise RuntimeError("Telegram destination unreachable")
        harness2.sent.append(method)
        return True

    monkeypatch.setattr(Bot, "__call__", failing_transport)
    try:
        with caplog.at_level(logging.ERROR, logger="wishenka.bot.support"):
            await harness2.text("/support")
            await harness2.text("Message when destination fails")
        assert any("Support ticket delivery failed" in r.message for r in caplog.records)
        reply2 = harness2.last_user_message().text
        assert not TICKET_REF_RE.search(reply2)
        assert any(
            word in reply2.casefold()
            for word in ("unavailable", "later", "could not", "недоступ", "позже", "не удалось")
        )
        async with store2.engine.connect() as conn:
            recorded2 = (
                await conn.execute(text("SELECT COUNT(*) FROM support_tickets"))
            ).scalar_one()
        assert recorded2 == 0
    finally:
        await harness2.bot.session.close()
        await users2.engine.dispose()
        await store2.engine.dispose()


async def test_privacy_surprise_protection_and_capability_redaction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    harness, store, users, ids, _ = await _setup_support(tmp_path, monkeypatch)
    secret_wish_title = "Top Secret Surprise Pony"
    secret_message_marker = "my-private-feedback-body-98765"
    try:
        # Seed a wish, a giver reservation, a purchase, and a receipt.
        async def seed_surprise(service: Any) -> tuple[str, str]:
            wl = await service.get_wishlist_by_id(ids[0])
            item = await service.add_wish_item(wl.id, OWNER, title=secret_wish_title, quantity=2)
            res = await service.create_reservation(item.id, GIVER, quantity=1, wishlist_id=wl.id)
            await service.mark_reservation_purchased(
                res.id, GIVER, wishlist_id=wl.id, item_id=item.id
            )
            await service.record_item_fulfillment(item.id, OWNER, 1, wishlist_id=wl.id)
            return str(wl.public_token), str(wl.invite_token)

        public_token, invite_token = await seed_surprise(WishlistService(store))
        caplog.clear()

        with caplog.at_level(logging.DEBUG):
            await harness.text("/support")
            await harness.text(
                f"{secret_message_marker} check p_{public_token} and i_{invite_token} "
                f"and https://example.test/share/{public_token} "
                f"and https://example.test/invite/{invite_token} "
                f"and https://example.test/api/public/wishlists/{public_token}/view"
            )

        support_msgs = harness.support_messages(SUPPORT_CHAT_ID)
        assert len(support_msgs) == 1
        ticket_text = support_msgs[0].text
        user_reply = harness.last_user_message().text

        # Capability tokens must be redacted from the delivered ticket.
        assert "[REDACTED]" in ticket_text
        assert public_token not in ticket_text
        assert invite_token not in ticket_text
        assert public_token not in user_reply
        assert invite_token not in user_reply

        # Surprise-protected data and private wish titles must never appear in tickets or replies.
        for forbidden in (
            secret_wish_title,
            "SecretGiver",
            "202",
            "PURCHASED",
        ):
            assert forbidden not in ticket_text
            assert forbidden not in user_reply

        # Operational logs must never contain message bodies, tokens, wish titles, or user PII.
        for forbidden_log in (
            secret_message_marker,
            public_token,
            invite_token,
            secret_wish_title,
            "SecretGiver",
            "alice_tg",
            "101",
        ):
            assert forbidden_log not in caplog.text
            assert all(forbidden_log not in str(record.__dict__) for record in caplog.records)
    finally:
        await harness.bot.session.close()
        await users.engine.dispose()
        await store.engine.dispose()
