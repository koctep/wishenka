"""End-to-end verification of Telegram bot menu transitions to the Mini App (WISHENKA-177)."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from collections.abc import Callable
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import pytest
from aiogram import Bot, Dispatcher
from aiogram.methods import SendMessage
from aiogram.types import InlineKeyboardMarkup, Update

from tests.browser_cdp import CdpBrowser, CdpPage
from tests.browser_helpers import Seeded
from tests.conftest import OWNER_TELEGRAM_ID, BrowserServer
from wishenka.bot.entry import create_router
from wishenka.i18n import SupportedLocale, t

pytestmark = [pytest.mark.timeout(45), pytest.mark.browser]


async def _extract_bot_menu_queries(
    monkeypatch: pytest.MonkeyPatch, language: SupportedLocale
) -> dict[str, str]:
    """Dispatch /start in-process and extract validated query strings for menu Mini App buttons."""
    sent: list[object] = []

    async def transport(_bot: Bot, method: object, request_timeout: float | None = None) -> bool:
        sent.append(method)
        return True

    monkeypatch.setattr(Bot, "__call__", transport)
    service = SimpleNamespace(create_wishlist=AsyncMock())
    dependencies = SimpleNamespace(
        mini_app_url="https://example.test/miniapp",
        wishlist_service=service,
    )
    dispatcher = Dispatcher()
    dispatcher.include_router(create_router(dependencies))
    update = Update.model_validate(
        {
            "update_id": 1,
            "message": {
                "message_id": 1,
                "date": 1700000000,
                "chat": {"id": OWNER_TELEGRAM_ID, "type": "private"},
                "from": {
                    "id": OWNER_TELEGRAM_ID,
                    "is_bot": False,
                    "first_name": "Owner",
                    "language_code": language,
                },
                "text": "/start",
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
    assert messages, "The bot must reply to a private /start command"
    reply = messages[-1]
    assert isinstance(reply.reply_markup, InlineKeyboardMarkup)

    buttons = [button for row in reply.reply_markup.inline_keyboard for button in row]
    by_label = {button.text: button for button in buttons}

    expected_buttons = {
        "create": t("bot.entry.btn_create", language),
        "collection": t("bot.entry.btn_collection", language),
        "home": t("bot.entry.btn_home", language),
    }
    queries: dict[str, str] = {}
    for intent, label in expected_buttons.items():
        button = by_label.get(label)
        assert button is not None, f"Missing bot menu button {label!r} for locale {language!r}"
        assert button.web_app is not None, f"Button {label!r} must open a Mini App"
        parts = urlsplit(button.web_app.url)
        assert parts.scheme == "https"
        assert parse_qs(parts.query).get("startapp") == [intent]
        queries[intent] = parts.query
    return queries


def _build_telegram_init_data(telegram_id: int, first_name: str, language: SupportedLocale) -> str:
    """Create a valid signed Telegram WebApp initData string using the default test bot token."""
    from wishenka.config import Settings

    user = json.dumps(
        {"id": telegram_id, "first_name": first_name, "language_code": language},
        separators=(",", ":"),
    )
    fields = {"auth_date": str(int(time.time())), "user": user}
    check = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", Settings().bot_token.encode("utf-8"), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode("utf-8"), hashlib.sha256).hexdigest()
    return urlencode(fields)


def _set_owner_locale_and_count(
    server: BrowserServer, owner_token: str, language: SupportedLocale
) -> int:
    """Ensure the owner profile exists, persist their locale, and return wishlist count."""
    init_data = _build_telegram_init_data(OWNER_TELEGRAM_ID, "Owner", language)
    headers = {"Authorization": f"Bearer {owner_token}"}
    with httpx.Client(base_url=server.base_url, headers=headers, timeout=10) as api:
        auth_resp = api.post(
            "/api/auth/telegram",
            json={"init_data": init_data},
            headers={"Origin": server.base_url},
        )
        auth_resp.raise_for_status()
        locale_resp = api.patch("/api/profile/locale", json={"locale": language})
        locale_resp.raise_for_status()
        wishlists_resp = api.get("/api/wishlists")
        wishlists_resp.raise_for_status()
        return len(wishlists_resp.json())


def _get_owner_wishlist_count(server: BrowserServer, owner_token: str) -> int:
    """Return the owner's current wishlist count via the REST API."""
    headers = {"Authorization": f"Bearer {owner_token}"}
    with httpx.Client(base_url=server.base_url, headers=headers, timeout=10) as api:
        resp = api.get("/api/wishlists")
        resp.raise_for_status()
        return len(resp.json())


def _open_session_page(
    browser: CdpBrowser,
    pages: list[CdpPage],
    server: BrowserServer,
    token: str,
    query: str,
) -> CdpPage:
    """Open a Mini App URL with an authenticated session_id cookie."""
    browser.ensure_alive()
    page = browser.new_page((412, 800))
    pages.append(page)
    page.set_cookie("session_id", token, server.base_url)
    page.navigate(f"{server.base_url}/?{query}")
    return page


@pytest.mark.parametrize("language", ["en", "ru"])
@pytest.mark.parametrize("intent", ["create", "collection", "home"])
async def test_bot_menu_transition_opens_expected_miniapp_screen_without_creating_wishlist(
    monkeypatch: pytest.MonkeyPatch,
    seed_wishlist: Callable[..., Seeded],
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
    language: SupportedLocale,
    intent: str,
) -> None:
    """Following create, collection, or home from the bot menu opens the localized screen safely."""
    seeded = seed_wishlist(["Birthday camera"])
    before_count = _set_owner_locale_and_count(wishlist_server, seeded.owner_token, language)
    queries = await _extract_bot_menu_queries(monkeypatch, language)

    page = _open_session_page(
        chromium_browser,
        _browser_pages,
        wishlist_server,
        seeded.owner_token,
        queries[intent],
    )

    expected_title = json.dumps(t("miniapp.home.title", language))
    expected_my_wishlists = json.dumps(t("miniapp.home.my_wishlists", language))
    page.wait_for(
        f"Mini App home settled for {intent} ({language})",
        f"document.querySelector('#app h1')?.innerText === {expected_title} "
        "&& document.getElementById('status')?.innerText === '' "
        f"&& document.body.innerText.includes({expected_my_wishlists})",
    )

    body_text = page.evaluate("document.body.innerText")
    assert "Browser wishlist" in body_text

    if intent == "create":
        expected_create_btn = json.dumps(t("miniapp.home.create_wishlist", language))
        page.wait_for(
            "create wishlist button focused",
            "document.activeElement?.tagName === 'BUTTON' "
            f"&& document.activeElement?.innerText === {expected_create_btn}",
        )

    assert _get_owner_wishlist_count(wishlist_server, seeded.owner_token) == before_count


@pytest.mark.parametrize("language", ["en", "ru"])
@pytest.mark.parametrize("invalid_param", ["unknown_action", "bad!param", "x_not_a_token"])
def test_invalid_startapp_recovers_safely_without_leaking_data_or_creating_wishlist(
    seed_wishlist: Callable[..., Seeded],
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
    language: SupportedLocale,
    invalid_param: str,
) -> None:
    """An invalid startapp parameter renders localized recovery without leaking or creating data."""
    seeded = seed_wishlist(["Secret surprise gift"])
    before_count = _set_owner_locale_and_count(wishlist_server, seeded.owner_token, language)

    page = _open_session_page(
        chromium_browser,
        _browser_pages,
        wishlist_server,
        seeded.owner_token,
        f"startapp={invalid_param}",
    )

    expected_unavailable_title = json.dumps(t("miniapp.unavailable.title", language))
    expected_unavailable_desc = json.dumps(t("miniapp.unavailable.description", language))
    expected_home_btn = json.dumps(t("miniapp.unavailable.home_menu", language))
    page.wait_for(
        f"unavailable recovery screen ({language})",
        f"document.querySelector('#app h1')?.innerText === {expected_unavailable_title} "
        f"&& document.body.innerText.includes({expected_unavailable_desc})",
    )

    body_text = page.evaluate("document.body.innerText")
    assert t("miniapp.unavailable.home_menu", language) in body_text
    assert "Browser wishlist" not in body_text
    assert "Secret surprise gift" not in body_text

    page.evaluate(
        "[...document.querySelectorAll('#app button')]"
        f".find(b => b.innerText === {expected_home_btn}).click()"
    )
    expected_home_title = json.dumps(t("miniapp.home.title", language))
    page.wait_for(
        f"recovered to home screen ({language})",
        f"document.querySelector('#app h1')?.innerText === {expected_home_title} "
        "&& document.getElementById('status')?.innerText === '' "
        "&& document.body.innerText.includes('Browser wishlist')",
    )

    assert _get_owner_wishlist_count(wishlist_server, seeded.owner_token) == before_count
