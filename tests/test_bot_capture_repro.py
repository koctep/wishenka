"""Acceptance repro for capturing wishes through private Telegram updates."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from aiogram import Bot, Dispatcher, Router
from aiogram.methods import SendMessage
from aiogram.types import InlineKeyboardMarkup, Message, Update
from sqlalchemy import text

from wishenka.auth.models import AuthenticatedUser, TelegramUser
from wishenka.bot.entry import create_router
from wishenka.items.schemas import ItemPreviewDTO
from wishenka.items.service import ItemPreviewService
from wishenka.users.store import UserStore
from wishenka.wishlists.models import WishlistRole
from wishenka.wishlists.store import WishlistStore

pytestmark = pytest.mark.timeout(30)
OWNER = AuthenticatedUser(telegram_id=101, first_name="Owner", auth_method="session_token")


class Harness:
    """Deliver updates to a dispatcher and record Telegram methods without network access."""

    def __init__(self, dispatcher: Dispatcher, bot: Bot, sent: list[Any]) -> None:
        self.dispatcher, self.bot, self.sent = dispatcher, bot, sent
        self.sequence = 0

    async def text(
        self, text: str, *, user: int = 101, lang: str = "en", forwarded: bool = False
    ) -> None:
        self.sequence += 1
        message: dict[str, Any] = {
            "message_id": self.sequence,
            "date": 1700000000,
            "chat": {"id": user, "type": "private"},
            "from": {"id": user, "is_bot": False, "first_name": "Owner", "language_code": lang},
            "text": text,
        }
        if forwarded:
            message["forward_origin"] = {
                "type": "hidden_user",
                "date": 1699999999,
                "sender_user_name": "Other",
            }
        update = Update.model_validate(
            {
                "update_id": self.sequence,
                "message": message,
            }
        )
        await self.dispatcher.feed_update(self.bot, update)

    def last_message(self) -> SendMessage:
        messages = [method for method in self.sent if isinstance(method, SendMessage)]
        assert messages, "Bot must respond to a private idea with a review or guidance"
        return messages[-1]

    async def callback(self, data: str, *, user: int = 101) -> None:
        self.sequence += 1
        update = Update.model_validate(
            {
                "update_id": self.sequence,
                "callback_query": {
                    "id": str(self.sequence),
                    "chat_instance": "private",
                    "from": {"id": user, "is_bot": False, "first_name": "Owner"},
                    "message": {
                        "message_id": 1,
                        "date": 1700000000,
                        "chat": {"id": user, "type": "private"},
                        "from": {"id": 123456, "is_bot": True, "first_name": "Bot"},
                        "text": "Review",
                    },
                    "data": data,
                },
            }
        )
        await self.dispatcher.feed_update(self.bot, update)


def _action(message: SendMessage, labels: tuple[str, ...]) -> str:
    assert isinstance(message.reply_markup, InlineKeyboardMarkup), "Review must offer actions"
    for row in message.reply_markup.inline_keyboard:
        for button in row:
            if any(label in button.text.casefold() for label in labels) and button.callback_data:
                return button.callback_data
    pytest.fail(f"Missing action {labels} in review keyboard")


async def _setup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    count: int = 1,
    clock: Any = None,
    preview_service: Any = None,
) -> tuple[Harness, WishlistStore, UserStore, list[int], AsyncMock]:
    url = f"sqlite+aiosqlite:///{tmp_path / 'capture.db'}"
    store, users = WishlistStore(url), UserStore(url)
    await store.initialize()
    ids = []
    for index in range(count):

        async def create(service: Any, index: int = index) -> Any:
            return await service.create_wishlist(owner=OWNER, title=f"List {index + 1}")

        ids.append((await store.execute(create)).id)
    preview = AsyncMock()
    preview.preview = AsyncMock(return_value=ItemPreviewDTO(title="Lamp"))
    deps = SimpleNamespace(
        mini_app_url="https://example.test/miniapp",
        user_store=users,
        wishlist_store=store,
        preview_service=preview_service or preview,
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
    return Harness(dispatcher, bot, sent), store, users, ids, preview


async def _count(store: WishlistStore, wishlist_id: int) -> int:
    async def inspect(service: Any) -> int:
        return len((await service.get_wishlist_by_id(wishlist_id)).items)

    return await store.execute(inspect)


async def test_long_draft_review_is_bounded_and_preserves_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness, store, users, ids, _ = await _setup(tmp_path, monkeypatch)
    description = "🎁" * 2000
    link = "https://example.test/" + "x" * 2000

    async def limited_transport(_bot: Bot, method: Any, request_timeout: Any = None) -> bool:
        if isinstance(method, SendMessage):
            assert len(method.text.encode("utf-16-le")) // 2 <= 4096
        harness.sent.append(method)
        return True

    monkeypatch.setattr(Bot, "__call__", limited_transport)
    try:
        await harness.text("Lamp")
        for field, value in (("description", description), ("link", link)):
            await harness.callback(_action(harness.last_message(), ("edit",)))
            await harness.callback(_action(harness.last_message(), (field,)))
            await harness.text(value)
        review = harness.last_message()
        assert "shortened only in this review" in review.text
        view = _action(review, ("view full",))
        before = len(harness.sent)
        await harness.callback(view)
        messages = [m.text for m in harness.sent[before:] if isinstance(m, SendMessage)]
        description_parts = [m.split("\n", 1)[1] for m in messages if m.startswith("Description (")]
        link_parts = [m.split("\n", 1)[1] for m in messages if m.startswith("Link (")]
        assert "".join(description_parts) == description
        assert "".join(link_parts) == link
        review = harness.last_message()
        await harness.callback(_action(review, ("edit",)))
        await harness.callback(_action(harness.last_message(), ("title",)))
        await harness.text("Updated lamp")
        review = harness.last_message()
        before = len(harness.sent)
        await harness.callback(view)
        stale = [m.text for m in harness.sent[before:] if isinstance(m, SendMessage)]
        assert len(stale) == 1 and "Expired" in stale[0]
        await harness.callback(_action(review, ("save",)))
        assert "Saved: List 1" in harness.last_message().text

        async def inspect(service: Any) -> Any:
            return (await service.get_wishlist_by_id(ids[0])).items[0]

        item = await store.execute(inspect)
        assert item.description == description
        assert item.link == link
    finally:
        await harness.bot.session.close()
        await users.engine.dispose()
        await store.engine.dispose()


async def test_fake_transport_exercises_private_message(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[Any] = []

    async def transport(_bot: Bot, method: Any, request_timeout: Any = None) -> bool:
        sent.append(method)
        return True

    monkeypatch.setattr(Bot, "__call__", transport)
    router = Router()

    @router.message()
    async def echo(message: Message) -> None:
        await message.answer("transport works")

    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    bot = Bot("123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")
    try:
        harness = Harness(dispatcher, bot, sent)
        await harness.text("Hello")
        assert harness.last_message().text == "transport works"
    finally:
        await bot.session.close()


@pytest.mark.parametrize("lang", ["en", "ru"])
async def test_text_opens_review_without_creating_wish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, lang: str
) -> None:
    harness, store, users, ids, _ = await _setup(tmp_path, monkeypatch)
    try:
        await harness.text("Lamp", lang=lang)
        message = harness.last_message()
        assert "Lamp" in message.text and "List 1" in message.text
        _action(message, ("save", "сохран"))
        _action(message, ("cancel", "отмен"))
        assert await _count(store, ids[0]) == 0
    finally:
        await harness.bot.session.close()
        await users.engine.dispose()
        await store.engine.dispose()


async def test_forwarded_link_keeps_preview_and_allows_destination_choice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness, store, users, ids, preview = await _setup(tmp_path, monkeypatch, count=2)
    link = "https://shop.example.test/item"
    preview.preview.return_value = ItemPreviewDTO(title="Lamp", url=link, price=1200)
    try:
        await harness.text(link, forwarded=True)
        message = harness.last_message()
        assert link in message.text and "Lamp" in message.text
        assert isinstance(message.reply_markup, InlineKeyboardMarkup)
        texts = [button.text for row in message.reply_markup.inline_keyboard for button in row]
        assert any("List 1" in text for text in texts)
        assert any("List 2" in text for text in texts)
        assert [await _count(store, item) for item in ids] == [0, 0]
    finally:
        await harness.bot.session.close()
        await users.engine.dispose()
        await store.engine.dispose()


async def test_no_eligible_list_provides_guidance_without_saving(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness, store, users, _, _ = await _setup(tmp_path, monkeypatch, count=0)
    try:
        await harness.text("A gift")
        message = harness.last_message()
        assert message.text and any(word in message.text.casefold() for word in ("list", "спис"))
        assert message.reply_markup is not None
    finally:
        await harness.bot.session.close()
        await users.engine.dispose()
        await store.engine.dispose()


async def test_save_callback_retry_and_concurrency_create_only_one_wish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness, store, users, ids, _ = await _setup(tmp_path, monkeypatch)
    try:
        await harness.text("Lamp")
        save = _action(harness.last_message(), ("save", "сохран"))
        before_save = len(harness.sent)
        await asyncio.gather(harness.callback(save), harness.callback(save))
        confirmations = [
            method.text for method in harness.sent[before_save:] if isinstance(method, SendMessage)
        ]
        assert len(confirmations) == 2, "Each save callback must produce a fresh confirmation"
        first = confirmations[0]
        assert first and all(message == first for message in confirmations)
        assert any(word in first.casefold() for word in ("saved", "сохран"))
        assert "List 1" in first
        before_retry = len(harness.sent)
        await harness.callback(save)
        retry = [
            method.text for method in harness.sent[before_retry:] if isinstance(method, SendMessage)
        ]
        assert retry == [first], "A retry must return the same fresh success confirmation"
        assert await _count(store, ids[0]) == 1
    finally:
        await harness.bot.session.close()
        await users.engine.dispose()
        await store.engine.dispose()


async def test_cancel_and_stale_save_do_not_create_a_wish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness, store, users, ids, _ = await _setup(tmp_path, monkeypatch)
    try:
        await harness.text("Lamp")
        review = harness.last_message()
        save = _action(review, ("save", "сохран"))
        cancel = _action(review, ("cancel", "отмен"))
        await harness.callback(cancel)
        await harness.callback(save)
        assert await _count(store, ids[0]) == 0
    finally:
        await harness.bot.session.close()
        await users.engine.dispose()
        await store.engine.dispose()


async def test_other_user_cannot_save_a_private_draft(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness, store, users, ids, _ = await _setup(tmp_path, monkeypatch)
    try:
        await harness.text("Secret gift")
        save = _action(harness.last_message(), ("save", "сохран"))
        await harness.callback(save, user=202)
        assert await _count(store, ids[0]) == 0
        leaked = [str(method) for method in harness.sent if getattr(method, "chat_id", None) == 202]
        assert all("Secret gift" not in text for text in leaked)
    finally:
        await harness.bot.session.close()
        await users.engine.dispose()
        await store.engine.dispose()


@pytest.mark.parametrize("failure", [False, True])
async def test_partial_or_failed_preview_can_be_corrected_and_saved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: bool
) -> None:
    harness, store, users, ids, preview = await _setup(tmp_path, monkeypatch)
    link = "https://shop.example.test/unknown"
    if failure:
        preview.preview.side_effect = RuntimeError("preview unavailable")
    else:
        preview.preview.return_value = ItemPreviewDTO(url=link, is_fallback=True)
    try:
        await harness.text(link, forwarded=True)
        review = harness.last_message()
        assert link in review.text
        assert "manually" in review.text and "Title is required" in review.text
        await harness.callback(_action(review, ("edit", "редакт")))
        await harness.callback(_action(harness.last_message(), ("title", "назван")))
        await harness.text("Handmade lamp")
        updated = harness.last_message()
        assert "Handmade lamp" in updated.text and link in updated.text
        await harness.callback(_action(updated, ("save", "сохран")))
        assert await _count(store, ids[0]) == 1
    finally:
        await harness.bot.session.close()
        await users.engine.dispose()
        await store.engine.dispose()


async def test_incomplete_preview_allows_independent_field_corrections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness, store, users, ids, preview = await _setup(tmp_path, monkeypatch)
    preview.preview.return_value = ItemPreviewDTO(price=1_000_000_000, is_fallback=True)
    try:
        await harness.text("https://shop.example.test/item")
        await harness.callback(_action(harness.last_message(), ("edit",)))
        await harness.callback(_action(harness.last_message(), ("price",)))
        await harness.text("42")
        review = harness.last_message()
        assert "Price: 42" in review.text and "Title is required" in review.text
        await harness.callback(_action(review, ("edit",)))
        await harness.callback(_action(harness.last_message(), ("title",)))
        await harness.text("Lamp")
        await harness.callback(_action(harness.last_message(), ("save",)))
        assert await _count(store, ids[0]) == 1
    finally:
        await harness.bot.session.close()
        await users.engine.dispose()
        await store.engine.dispose()


async def test_partial_nonfallback_preview_shows_missing_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness, store, users, _, preview = await _setup(tmp_path, monkeypatch)
    preview.preview.return_value = ItemPreviewDTO(title="Lamp", is_fallback=False)
    try:
        await harness.text("https://shop.example.test/item")
        message = harness.last_message().text
        assert "Missing: Description, Image URL, Price" in message
    finally:
        await harness.bot.session.close()
        await users.engine.dispose()
        await store.engine.dispose()


async def test_clear_optional_fields_uses_defaults_on_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness, store, users, ids, preview = await _setup(tmp_path, monkeypatch)
    preview.preview.return_value = ItemPreviewDTO(title="Lamp", price=42)
    try:
        await harness.text("https://shop.example.test/item")
        await harness.callback(_action(harness.last_message(), ("edit",)))
        keyboard = harness.last_message().reply_markup
        assert isinstance(keyboard, InlineKeyboardMarkup)
        price_row = next(row for row in keyboard.inline_keyboard if row[0].text == "Price")
        assert price_row[1].text == "Clear" and price_row[1].callback_data
        await harness.callback(price_row[1].callback_data)
        assert "Price: 42" not in harness.last_message().text
        await harness.callback(_action(harness.last_message(), ("save",)))

        async def inspect(service: Any) -> Any:
            return (await service.get_wishlist_by_id(ids[0])).items[0]

        assert (await store.execute(inspect)).price is None
    finally:
        await harness.bot.session.close()
        await users.engine.dispose()
        await store.engine.dispose()


@pytest.mark.parametrize("lang, guidance", [("en", "manually"), ("ru", "вручную")])
async def test_unsupported_link_is_preserved_without_fetch_until_corrected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, lang: str, guidance: str
) -> None:
    harness, store, users, ids, preview = await _setup(tmp_path, monkeypatch)
    link = "file:///private/example"
    try:
        await harness.text(link, lang=lang)
        review = harness.last_message()
        assert link in review.text and guidance in review.text
        preview.preview.assert_not_awaited()
        await harness.callback(_action(review, ("edit", "редакт")))
        await harness.callback(_action(harness.last_message(), ("title", "назван")))
        await harness.text("Lamp", lang=lang)
        await harness.callback(_action(harness.last_message(), ("save", "сохран")))
        assert await _count(store, ids[0]) == 0
        assert link in harness.last_message().text
        assert "http" in harness.last_message().text
        await harness.callback(_action(harness.last_message(), ("edit", "редакт")))
        await harness.callback(_action(harness.last_message(), ("link", "ссылка")))
        await harness.text("https://shop.example.test/item", lang=lang)
        await harness.callback(_action(harness.last_message(), ("save", "сохран")))
        assert await _count(store, ids[0]) == 1
    finally:
        await harness.bot.session.close()
        await users.engine.dispose()
        await store.engine.dispose()


@pytest.mark.parametrize("field", ["link", "image_url"])
async def test_unsafe_edited_url_cannot_be_saved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    harness, store, users, ids, _ = await _setup(tmp_path, monkeypatch)
    unsafe = "javascript://%0Aalert(1)"
    try:
        await harness.text("Lamp")
        await harness.callback(_action(harness.last_message(), ("edit",)))
        # Image URL contains "link" in Russian but has a distinct English label.
        label = ("image url",) if field == "image_url" else ("link",)
        await harness.callback(_action(harness.last_message(), label))
        await harness.text(unsafe)
        review = harness.last_message()
        assert unsafe in review.text
        await harness.callback(_action(review, ("save",)))
        assert await _count(store, ids[0]) == 0
        assert unsafe in harness.last_message().text
        assert "http" in harness.last_message().text
    finally:
        await harness.bot.session.close()
        await users.engine.dispose()
        await store.engine.dispose()


async def test_unsafe_initial_link_cannot_be_saved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness, store, users, ids, preview = await _setup(tmp_path, monkeypatch)
    unsafe = "javascript://%0Aalert(1)"
    try:
        await harness.text(unsafe)
        preview.preview.assert_not_awaited()
        await harness.callback(_action(harness.last_message(), ("edit",)))
        await harness.callback(_action(harness.last_message(), ("title",)))
        await harness.text("Lamp")
        await harness.callback(_action(harness.last_message(), ("save",)))
        assert await _count(store, ids[0]) == 0
        assert unsafe in harness.last_message().text
        assert "http" in harness.last_message().text
    finally:
        await harness.bot.session.close()
        await users.engine.dispose()
        await store.engine.dispose()


async def test_invalid_title_keeps_draft_and_prevents_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness, store, users, ids, _ = await _setup(tmp_path, monkeypatch)
    try:
        await harness.text("Lamp")
        await harness.callback(_action(harness.last_message(), ("edit", "редакт")))
        await harness.callback(_action(harness.last_message(), ("title", "назван")))
        await harness.text(" " * 3)
        response = harness.last_message().text.casefold()
        assert any(word in response for word in ("title", "назван"))
        assert await _count(store, ids[0]) == 0
    finally:
        await harness.bot.session.close()
        await users.engine.dispose()
        await store.engine.dispose()


async def test_deleted_destination_is_rechecked_at_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness, store, users, ids, _ = await _setup(tmp_path, monkeypatch)
    try:
        await harness.text("Lamp")
        save = _action(harness.last_message(), ("save", "сохран"))

        async def delete(service: Any) -> None:
            await service.delete_wishlist(ids[0], OWNER)

        await store.execute(delete)
        await harness.callback(save)
        response = harness.last_message().text.casefold()
        assert any(word in response for word in ("unavailable", "недоступ"))
        async with store.engine.connect() as connection:
            result = await connection.execute(
                text("SELECT COUNT(*) FROM wl_items WHERE wishlist_id = :wishlist_id"),
                {"wishlist_id": ids[0]},
            )
            assert result.scalar_one() == 0
    finally:
        await harness.bot.session.close()
        await users.engine.dispose()
        await store.engine.dispose()


async def test_removed_member_cannot_save_previously_selected_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness, store, users, ids, _ = await _setup(tmp_path, monkeypatch)
    try:
        await users.upsert_user(TelegramUser(id=202, first_name="Member"))

        async def add(service: Any) -> None:
            await service.add_member(ids[0], OWNER, 202, WishlistRole.MEMBER)

        await store.execute(add)
        await harness.text("Private gift", user=202)
        save = _action(harness.last_message(), ("save", "сохран"))

        async def remove(service: Any) -> None:
            await service.remove_member(ids[0], OWNER, 202)

        await store.execute(remove)
        await harness.callback(save, user=202)
        assert await _count(store, ids[0]) == 0
        assert any(
            word in harness.last_message().text.casefold() for word in ("unavailable", "недоступ")
        )
    finally:
        await harness.bot.session.close()
        await users.engine.dispose()
        await store.engine.dispose()


async def test_replaced_draft_rejects_old_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness, store, users, ids, _ = await _setup(tmp_path, monkeypatch)
    try:
        await harness.text("First idea")
        old_save = _action(harness.last_message(), ("save", "сохран"))
        await harness.text("Second idea")
        new_review = harness.last_message()
        assert "Second idea" in new_review.text
        await harness.callback(old_save)
        assert await _count(store, ids[0]) == 0
        await harness.callback(_action(new_review, ("save", "сохран")))
        assert await _count(store, ids[0]) == 1
    finally:
        await harness.bot.session.close()
        await users.engine.dispose()
        await store.engine.dispose()


async def test_slow_older_preview_cannot_replace_newer_draft_after_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_preview(raw: str) -> ItemPreviewDTO:
        if "older" in raw:
            started.set()
            await asyncio.wait_for(release.wait(), timeout=5)
            return ItemPreviewDTO(title="Older idea")
        return ItemPreviewDTO(title="Other user's idea")

    preview = SimpleNamespace(preview=slow_preview)
    harness, store, users, ids, _ = await _setup(tmp_path, monkeypatch, preview_service=preview)
    older = asyncio.create_task(harness.text("https://example.test/older"))
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
        # A replacement dispatcher models a restart while the prior worker is delayed.
        restarted = Dispatcher()
        restarted.include_router(
            create_router(
                SimpleNamespace(
                    mini_app_url="https://example.test/miniapp",
                    user_store=users,
                    wishlist_store=store,
                    preview_service=preview,
                )
            )
        )
        harness.dispatcher = restarted
        await harness.text("Newest idea")
        newest = harness.last_message()
        assert "Newest idea" in newest.text
        save = _action(newest, ("save", "сохран"))
        await harness.text("A different user's idea", user=202)
        release.set()
        await asyncio.wait_for(older, timeout=5)
        owner_messages = [
            method
            for method in harness.sent
            if isinstance(method, SendMessage) and method.chat_id == 101
        ]
        assert len(owner_messages) == 1
        assert "Newest idea" in owner_messages[0].text
        await harness.callback(save)
        assert await _count(store, ids[0]) == 1

        async def saved_title(service: Any) -> str:
            wishlist = await service.get_wishlist_by_id(ids[0])
            return str(wishlist.items[0].title)

        assert await store.execute(saved_title) == "Newest idea"
    finally:
        release.set()
        await asyncio.gather(older, return_exceptions=True)
        await harness.bot.session.close()
        await users.engine.dispose()
        await store.engine.dispose()


async def test_interrupted_preview_recovers_durable_draft_on_redelivery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def interrupted_preview(raw: str) -> ItemPreviewDTO:
        started.set()
        await asyncio.wait_for(release.wait(), timeout=5)
        return ItemPreviewDTO(title="Extracted")

    preview = SimpleNamespace(preview=interrupted_preview)
    harness, store, users, ids, _ = await _setup(tmp_path, monkeypatch, preview_service=preview)
    pending: asyncio.Task[None] | None = None
    try:
        await harness.text("Previous idea")
        old_save = _action(harness.last_message(), ("save", "сохран"))
        pending = asyncio.create_task(harness.text("https://example.test/interrupted"))
        await asyncio.wait_for(started.wait(), timeout=5)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        await harness.callback(old_save)
        assert await _count(store, ids[0]) == 0

        restarted = Dispatcher()
        restarted.include_router(
            create_router(
                SimpleNamespace(
                    mini_app_url="https://example.test/miniapp",
                    user_store=users,
                    wishlist_store=store,
                    preview_service=preview,
                )
            )
        )
        harness.dispatcher = restarted
        # Redeliver the same message id despite the callback's later update id.
        harness.sequence = 1
        await harness.text("https://example.test/interrupted")
        review = harness.last_message()
        assert "https://example.test/interrupted" in review.text
        assert "missing" in review.text.casefold() or "required" in review.text.casefold()
        edit = _action(review, ("edit", "редакт"))
        await harness.callback(edit)
        title = _action(harness.last_message(), ("title", "название"))
        await harness.callback(title)
        await harness.text("Recovered idea")
        await harness.callback(_action(harness.last_message(), ("save", "сохран")))
        assert await _count(store, ids[0]) == 1
    finally:
        release.set()
        if pending:
            await asyncio.gather(pending, return_exceptions=True)
        await harness.bot.session.close()
        await users.engine.dispose()
        await store.engine.dispose()


async def test_redelivery_review_cannot_save_unseen_late_preview(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started, release = asyncio.Event(), asyncio.Event()

    async def delayed_preview(raw: str) -> ItemPreviewDTO:
        started.set()
        await asyncio.wait_for(release.wait(), timeout=5)
        return ItemPreviewDTO(title="Enriched idea", price=42)

    preview = SimpleNamespace(preview=delayed_preview)
    harness, store, users, ids, _ = await _setup(tmp_path, monkeypatch, preview_service=preview)
    pending = asyncio.create_task(harness.text("Original idea https://example.test/item"))
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
        harness.sequence = 0
        await harness.text("Original idea https://example.test/item")
        manual = harness.last_message()
        assert "Original idea" in manual.text
        old_save = _action(manual, ("save", "сохран"))

        release.set()
        await asyncio.wait_for(pending, timeout=5)
        enriched = harness.last_message()
        assert "Enriched idea" in enriched.text
        new_save = _action(enriched, ("save", "сохран"))
        assert old_save != new_save

        await harness.callback(old_save)
        assert await _count(store, ids[0]) == 0
        await harness.callback(new_save)
        await harness.callback(new_save)
        assert await _count(store, ids[0]) == 1

        async def saved_title(service: Any) -> str:
            wishlist = await service.get_wishlist_by_id(ids[0])
            return str(wishlist.items[0].title)

        assert await store.execute(saved_title) == "Enriched idea"
    finally:
        release.set()
        await asyncio.gather(pending, return_exceptions=True)
        await harness.bot.session.close()
        await users.engine.dispose()
        await store.engine.dispose()


async def test_expired_draft_cannot_be_saved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = [datetime(2026, 1, 1, tzinfo=UTC)]
    harness, store, users, ids, _ = await _setup(tmp_path, monkeypatch, clock=lambda: now[0])
    try:
        await harness.text("Lamp")
        save = _action(harness.last_message(), ("save", "сохран"))
        now[0] += timedelta(hours=25)
        await harness.callback(save)
        assert await _count(store, ids[0]) == 0
        response = harness.last_message().text.casefold()
        assert any(word in response for word in ("expired", "start again", "истек", "заново"))
    finally:
        await harness.bot.session.close()
        await users.engine.dispose()
        await store.engine.dispose()


async def test_draft_survives_dispatcher_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness, store, users, ids, preview = await _setup(tmp_path, monkeypatch)
    try:
        await harness.text("Lamp")
        save = _action(harness.last_message(), ("save", "сохран"))
        restarted = Dispatcher()
        restarted.include_router(
            create_router(
                SimpleNamespace(
                    mini_app_url="https://example.test/miniapp",
                    user_store=users,
                    wishlist_store=store,
                    preview_service=preview,
                )
            )
        )
        harness.dispatcher = restarted
        await harness.callback(save)
        assert await _count(store, ids[0]) == 1
        assert "List 1" in harness.last_message().text
    finally:
        await harness.bot.session.close()
        await users.engine.dispose()
        await store.engine.dispose()


@pytest.mark.parametrize("link", ["http://127.0.0.1/private", "file:///etc/passwd"])
async def test_unsafe_url_does_not_reach_preview_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, link: str
) -> None:
    requests: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(record)) as client:
        harness, store, users, ids, _ = await _setup(
            tmp_path, monkeypatch, preview_service=ItemPreviewService(client=client)
        )
        try:
            await harness.text(link)
            assert harness.last_message().text
            assert requests == []
            assert await _count(store, ids[0]) == 0
        finally:
            await harness.bot.session.close()
            await users.engine.dispose()
            await store.engine.dispose()


async def test_start_and_help_remain_available_with_active_draft(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness, store, users, ids, _ = await _setup(tmp_path, monkeypatch)
    try:
        await harness.text("Lamp")
        assert "Lamp" in harness.last_message().text
        await harness.text("/start")
        start = harness.last_message()
        assert "Welcome" in start.text
        await harness.callback(_action(start, ("how it works", "как это")))
        assert "wishlist" in harness.last_message().text.casefold()
        assert await _count(store, ids[0]) == 0
    finally:
        await harness.bot.session.close()
        await users.engine.dispose()
        await store.engine.dispose()


async def test_preview_logs_never_expose_private_link(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    import logging

    secret = "private-token-123"

    class Preview:
        async def preview(self, value: str) -> ItemPreviewDTO:
            logging.getLogger("wishenka.items").warning("Failed preview: %s", value)
            logging.getLogger("httpx").info("Request to %s", value)
            return ItemPreviewDTO(title="Lamp")

    harness, store, users, _, _ = await _setup(tmp_path, monkeypatch, preview_service=Preview())
    try:
        with caplog.at_level(logging.INFO):
            await harness.text(f"https://shop.example.test/?token={secret}")
        assert "Lamp" in harness.last_message().text
        assert secret not in caplog.text
        assert all(secret not in str(record.__dict__) for record in caplog.records)
    finally:
        await harness.bot.session.close()
        await users.engine.dispose()
        await store.engine.dispose()


async def test_capture_observability_omits_private_data_on_failure_and_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    import logging

    secret = "private-observability-marker"

    class Preview:
        async def preview(self, value: str) -> ItemPreviewDTO:
            logging.getLogger("httpcore.http11").warning("private %s", value)
            raise RuntimeError(value)

    harness, store, users, _, _ = await _setup(tmp_path, monkeypatch, preview_service=Preview())
    try:
        with caplog.at_level(logging.DEBUG):
            await harness.text(f"{secret} https://{secret}.example.test/?token={secret}")
            save = _action(harness.last_message(), ("save", "сохран"))
            original = store._write

            async def fail(*args: Any, **kwargs: Any) -> None:
                raise RuntimeError(secret)

            monkeypatch.setattr(store, "_write", fail)
            await harness.callback(save)
            monkeypatch.setattr(store, "_write", original)
            await harness.callback(save)

        events = {getattr(record, "event", ""): record for record in caplog.records}
        assert vars(events["bot_capture_preview"])["outcome"] == "error"
        assert vars(events["bot_capture_preview"])["duration_ms"] >= 0
        assert "bot_capture_action_error" in events
        assert vars(events["bot_capture_save"])["outcome"] == "saved"
        assert "user_created" not in events
        assert "item_created" not in events
        assert secret not in caplog.text
        assert all(secret not in str(record.__dict__) for record in caplog.records)
    finally:
        await harness.bot.session.close()
        await users.engine.dispose()
        await store.engine.dispose()


async def test_private_child_logger_filter_preserves_parallel_operations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    entered = asyncio.Event()
    release = asyncio.Event()
    secret = "private-child-logger-marker"

    class Preview:
        async def preview(self, value: str) -> ItemPreviewDTO:
            logging.getLogger("wishenka.wishlists.store").warning("private %s", secret)
            entered.set()
            await asyncio.wait_for(release.wait(), timeout=5)
            logging.getLogger("wishenka.wishlists.notices").warning("private %s", secret)
            return ItemPreviewDTO(title="Lamp")

    harness, store, users, _, _ = await _setup(tmp_path, monkeypatch, preview_service=Preview())
    task = None
    try:
        with caplog.at_level(logging.WARNING):
            task = asyncio.create_task(harness.text("https://shop.example.test/item"))
            await asyncio.wait_for(entered.wait(), timeout=5)
            logging.getLogger("wishenka.wishlists.store").warning("unrelated operation")
            release.set()
            await asyncio.wait_for(task, timeout=5)
        assert "unrelated operation" in caplog.text
        assert secret not in caplog.text
        assert all(secret not in str(record.__dict__) for record in caplog.records)
    finally:
        release.set()
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await harness.bot.session.close()
        await users.engine.dispose()
        await store.engine.dispose()


async def test_cleanup_loop_recovers_from_transient_failure(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from wishenka.bot import __main__ as bot_main

    completed = asyncio.Event()
    attempts = 0
    secret = "private-cleanup-exception"

    async def cleanup(store: WishlistStore) -> int:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError(secret)
        completed.set()
        return 0

    monkeypatch.setattr(bot_main, "cleanup_drafts", cleanup)
    with caplog.at_level(logging.ERROR, logger="wishenka.bot.cleanup"):
        task = asyncio.create_task(
            bot_main.cleanup_loop(None, interval=0.01, retry_interval=0.01)  # type: ignore[arg-type]
        )
        try:
            await asyncio.wait_for(completed.wait(), timeout=5)
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
    assert attempts >= 2
    assert any(
        getattr(record, "event", "") == "bot_draft_cleanup_failed" for record in caplog.records
    )
    assert secret not in caplog.text
    assert all(secret not in str(record.__dict__) for record in caplog.records)


async def test_failed_atomic_save_can_be_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness, store, users, ids, _ = await _setup(tmp_path, monkeypatch)
    try:
        await harness.text("Lamp")
        save = _action(harness.last_message(), ("save", "сохран"))
        original_write = store._write

        async def fail_after_write(*args: Any, **kwargs: Any) -> Any:
            await original_write(*args, **kwargs)
            raise RuntimeError("database failure")

        monkeypatch.setattr(store, "_write", fail_after_write)
        await harness.callback(save)
        assert "retry" in harness.last_message().text.casefold()
        monkeypatch.setattr(store, "_write", original_write)
        assert await _count(store, ids[0]) == 0
        await harness.callback(save)
        assert "saved" in harness.last_message().text.casefold()
        assert await _count(store, ids[0]) == 1
    finally:
        await harness.bot.session.close()
        await users.engine.dispose()
        await store.engine.dispose()
