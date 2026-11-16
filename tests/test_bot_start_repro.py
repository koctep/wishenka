"""Bot entry acceptance checks with in-process Telegram transport (WISHENKA-27)."""

import importlib
import importlib.util
import json
import logging
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot, Dispatcher, Router
from aiogram.filters import CommandStart
from aiogram.methods import SendMessage
from aiogram.types import InlineKeyboardMarkup, Message, Update

from wishenka.logging import JsonFormatter

pytestmark = pytest.mark.timeout(30)


def _router_factory() -> Callable[[Any], Router]:
    """Use an empty receiver until the entry component exists."""
    if importlib.util.find_spec("wishenka.bot") is None:
        return lambda _dependencies: Router()
    entry = importlib.import_module("wishenka.bot.entry")
    return cast(Callable[[Any], Router], entry.create_router)


async def _start(
    monkeypatch: pytest.MonkeyPatch,
    text: str,
    language: str,
    factory: Callable[[Any], Router] | None = None,
) -> SendMessage:
    """Deliver a private update and capture all outgoing Telegram methods locally."""
    sent = []

    async def transport(_bot, method, request_timeout=None):
        sent.append(method)
        return True

    monkeypatch.setattr(Bot, "__call__", transport)
    service = SimpleNamespace(create_wishlist=AsyncMock())
    dependencies = SimpleNamespace(
        mini_app_url="https://example.test/miniapp", wishlist_service=service
    )
    dispatcher = Dispatcher()
    dispatcher.include_router((factory or _router_factory())(dependencies))
    update = Update.model_validate(
        {
            "update_id": 1,
            "message": {
                "message_id": 1,
                "date": 1700000000,
                "chat": {"id": 101, "type": "private"},
                "from": {
                    "id": 101,
                    "is_bot": False,
                    "first_name": "Test",
                    "language_code": language,
                },
                "text": text,
                "entities": [{"type": "bot_command", "offset": 0, "length": 6}],
            },
        }
    )
    bot = Bot("123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")
    try:
        await dispatcher.feed_update(bot, update)
    finally:
        await bot.session.close()
    service.create_wishlist.assert_not_awaited()
    messages = [method for method in sent if isinstance(method, SendMessage)]
    assert messages, "The bot must answer a private /start"
    return messages[-1]


async def test_fake_transport_delivers_update_and_captures_reply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def factory(_dependencies):
        router = Router()

        @router.message(CommandStart())
        async def echo(message: Message) -> None:
            await message.answer("transport works")

        return router

    message = await _start(monkeypatch, "/start", "en", factory)
    assert message.chat_id == 101
    assert message.text == "transport works"


@pytest.mark.parametrize(
    ("language", "labels"),
    [
        ("en", ("Create wishlist", "My wishlists", "How it works", "Open Mini App")),
        ("ru", ("Создать вишлист", "Мои вишлисты", "Как это работает", "Открыть Mini App")),
    ],
)
async def test_start_menu_has_localized_actions_and_distinct_destinations(
    monkeypatch: pytest.MonkeyPatch, language: str, labels: tuple[str, ...]
) -> None:
    message = await _start(monkeypatch, "/start", language)
    assert isinstance(message.reply_markup, InlineKeyboardMarkup)
    buttons = [button for row in message.reply_markup.inline_keyboard for button in row]
    by_label = {button.text: button for button in buttons}
    assert set(labels) <= set(by_label)
    targets = []
    for label in labels:
        button = by_label[label]
        target = button.web_app.url if button.web_app else button.callback_data or button.url
        assert target, f"{label} must lead to an action"
        targets.append(target)
    assert len(set(targets)) == 4


async def test_malformed_start_recovers_with_menu_without_echoing_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    greeting = await _start(monkeypatch, "/start", "en")
    message = await _start(monkeypatch, "/start p_!invalid", "en")
    assert "p_!invalid" not in message.text
    assert message.text != greeting.text
    assert isinstance(message.reply_markup, InlineKeyboardMarkup)
    buttons = [button.text for row in message.reply_markup.inline_keyboard for button in row]
    assert {"Create wishlist", "My wishlists", "How it works", "Open Mini App"} <= set(buttons)


async def test_public_start_preserves_token_in_open_button(monkeypatch: pytest.MonkeyPatch) -> None:
    message = await _start(monkeypatch, "/start p_abc-123", "en")
    assert isinstance(message.reply_markup, InlineKeyboardMarkup)
    buttons = [button for row in message.reply_markup.inline_keyboard for button in row]
    target = next(button for button in buttons if button.text == "Open wishlist")
    assert target.web_app is not None
    assert target.web_app.url == "https://example.test/miniapp?startapp=p_abc-123"


async def test_start_logs_only_safe_outcome(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    secret = "p_private_capability"
    with caplog.at_level(logging.INFO, logger="wishenka.bot.entry"):
        await _start(monkeypatch, f"/start {secret}", "en")
        await _start(monkeypatch, "/start p_!invalid-secret", "en")
    records = [r for r in caplog.records if getattr(r, "event", None) == "bot_start_handled"]
    assert [getattr(r, "outcome", None) for r in records] == ["public_link", "invalid_link"]
    serialized = " ".join(JsonFormatter().format(record) for record in records)
    assert secret not in serialized
    assert "invalid-secret" not in serialized
    assert all(json.loads(JsonFormatter().format(record))["extra"]["event"] for record in records)


async def test_start_failure_log_omits_exception_details(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def fail_language(*_args: Any) -> str:
        raise RuntimeError("private-capability-value")

    monkeypatch.setattr("wishenka.bot.entry._language", fail_language)
    dispatcher = Dispatcher()
    dispatcher.include_router(
        _router_factory()(SimpleNamespace(mini_app_url="https://example.test"))
    )
    update = Update.model_validate(
        {
            "update_id": 1,
            "message": {
                "message_id": 1,
                "date": 1700000000,
                "chat": {"id": 101, "type": "private"},
                "from": {"id": 101, "is_bot": False, "first_name": "Test"},
                "text": "/start p_secret",
                "entities": [{"type": "bot_command", "offset": 0, "length": 6}],
            },
        }
    )
    bot = Bot("123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")
    try:
        with caplog.at_level(logging.ERROR):
            assert await dispatcher._process_update(bot, update)
    finally:
        await bot.session.close()
    record = next(r for r in caplog.records if getattr(r, "event", None) == "bot_start_failed")
    serialized = " ".join(JsonFormatter().format(item) for item in caplog.records)
    assert record.exc_info is None
    assert "private-capability-value" not in serialized
    assert "p_secret" not in serialized
