"""Failing reproduction tests for WISHENKA-33 bilingual i18n synchronization (RU/EN)."""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
import time
import urllib.parse
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot, Dispatcher
from aiogram.methods import SendMessage, SetMyCommands
from aiogram.types import BotCommandScopeChat, Update
from aiogram.types import User as AiogramUser
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from tests.notice_support import FakeNoticeSender
from wishenka.bot.entry import create_router
from wishenka.config import Settings
from wishenka.items.schemas import ItemPreviewDTO
from wishenka.notices.scheduler import ReminderScheduler
from wishenka.notices.worker import NoticeWorker
from wishenka.web.app import create_app

pytestmark = pytest.mark.timeout(20)

TEST_BOT_TOKEN = "123456789:ABCdefGHIjklMNOpqrsTUVwxyz1234567"


def _create_init_data(
    user_data: dict[str, Any],
    bot_token: str = TEST_BOT_TOKEN,
    auth_date: int | None = None,
) -> str:
    """Build signed Telegram WebApp initData query string."""
    if auth_date is None:
        auth_date = int(time.time())
    params: dict[str, str] = {
        "auth_date": str(auth_date),
        "user": json.dumps(user_data, separators=(",", ":")),
    }
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    params["hash"] = hmac.new(
        secret_key, data_check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return urllib.parse.urlencode(params)


def _make_settings(db_path: Path) -> Settings:
    """Create isolated test settings with background workers disabled."""
    return Settings(
        bot_token=TEST_BOT_TOKEN,
        database_url=f"sqlite+aiosqlite:///{db_path}",
        secret_key="i18n-sync-test-secret",
        receipt_notice_worker_enabled=False,
        background_cleanup_enabled=False,
    )


def _has_cyrillic(text: str) -> bool:
    """Return True when text contains any Cyrillic letters."""
    return any("а" <= ch.lower() <= "я" or ch.lower() == "ё" for ch in text)


def _html_lang(html_text: str) -> str | None:
    """Extract the root <html lang=...> attribute from rendered HTML."""
    soup = BeautifulSoup(html_text, "html.parser")
    html_tag = soup.find("html")
    if html_tag is None:
        return None
    lang = html_tag.get("lang")
    return str(lang) if isinstance(lang, str) else None


def _bot_deps(app: Any) -> SimpleNamespace:
    """Build bot router dependencies backed by the app's stores."""
    preview = AsyncMock()
    preview.preview = AsyncMock(return_value=ItemPreviewDTO(title="Parsed Lamp"))
    return SimpleNamespace(
        mini_app_url="https://example.test/miniapp",
        user_store=app.state.user_store,
        wishlist_store=app.state.wishlist_store,
        preview_service=preview,
        support_chat_id=None,
        support_admin_ids=(),
        support_session_ttl_seconds=3600,
        support_max_message_length=2000,
        support_rate_limit_window_seconds=3600,
        support_rate_limit_max_tickets=3,
    )


class _BotHarness:
    """Drive aiogram updates in-process against the intercepted transport."""

    def __init__(self, app: Any, calls: list[Any]) -> None:
        self.dispatcher = Dispatcher()
        self.dispatcher.include_router(create_router(_bot_deps(app)))
        self.bot = Bot(TEST_BOT_TOKEN)
        self.calls = calls
        self.sequence = 0

    async def send_command(
        self,
        command_text: str,
        *,
        user_id: int,
        first_name: str,
        language_code: str | None,
    ) -> SendMessage:
        """Feed a private bot command and return the resulting reply SendMessage."""
        self.sequence += 1
        from_user: dict[str, Any] = {
            "id": user_id,
            "is_bot": False,
            "first_name": first_name,
        }
        if language_code is not None:
            from_user["language_code"] = language_code
        command_word = command_text.split()[0]
        update = Update.model_validate(
            {
                "update_id": self.sequence,
                "message": {
                    "message_id": self.sequence,
                    "date": 1700000000 + self.sequence,
                    "chat": {"id": user_id, "type": "private"},
                    "from": from_user,
                    "text": command_text,
                    "entities": [{"type": "bot_command", "offset": 0, "length": len(command_word)}],
                },
            }
        )
        start_idx = len(self.calls)
        await self.dispatcher.feed_update(self.bot, update)
        sent_messages = [
            call
            for call in self.calls[start_idx:]
            if isinstance(call, SendMessage) and call.chat_id == user_id
        ]
        assert sent_messages, f"Expected SendMessage reply for {command_text}"
        return sent_messages[-1]

    async def close(self) -> None:
        """Close the underlying bot aiohttp session."""
        await self.bot.session.close()


@pytest.mark.timeout(15)
def test_first_login_locale_mapping_ru_en_and_fallback(tmp_path: Path) -> None:
    """First Telegram auth maps ru* -> ru and en*/unsupported/None -> en with source=auto."""
    settings = _make_settings(tmp_path / "first_login.db")
    cases = [
        (1001, "Ivan", "Petrov", "ru-RU", "ru", "Ivan Petrov"),
        (1002, "Alice", None, "en-US", "en", "Alice"),
        (1003, "Hans", "Mueller", "de", "en", "Hans Mueller"),
        (1004, "NoLang", None, None, "en", "NoLang"),
    ]

    app = create_app(settings)
    with TestClient(app) as client:
        assert client.portal is not None
        for tg_id, first_name, last_name, language_code, _, _ in cases:
            payload: dict[str, Any] = {"id": tg_id, "first_name": first_name}
            if last_name is not None:
                payload["last_name"] = last_name
            if language_code is not None:
                payload["language_code"] = language_code
            resp = client.post(
                "/api/auth/telegram",
                json={"init_data": _create_init_data(payload)},
                headers={"Origin": settings.application_origin},
            )
            assert resp.status_code == 200

        async def verify_records() -> None:
            for tg_id, _, _, _, expected_locale, expected_display_name in cases:
                record = await app.state.user_store.get_by_telegram_id(tg_id)
                assert record is not None
                assert getattr(record, "locale", None) == expected_locale
                assert getattr(record, "locale_source", None) == "auto"
                assert getattr(record, "display_name", None) == expected_display_name

        client.portal.call(verify_records)


@pytest.mark.timeout(15)
def test_auto_locale_tracks_telegram_client_until_explicit_switch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Auto locale tracks client language across Mini App & Bot until explicit switch."""
    bot_calls: list[Any] = []

    async def transport(_bot: Bot, method: Any, request_timeout: float | None = None) -> bool:
        bot_calls.append(method)
        return True

    monkeypatch.setattr(Bot, "__call__", transport)

    settings = _make_settings(tmp_path / "auto_to_explicit.db")
    tg_id = 2001
    app = create_app(settings)

    with TestClient(app) as client:
        assert client.portal is not None
        portal = client.portal

        async def get_record() -> Any:
            return await app.state.user_store.get_by_telegram_id(tg_id)

        # 1. First login with ru -> auto 'ru'
        auth_ru = client.post(
            "/api/auth/telegram",
            json={
                "init_data": _create_init_data(
                    {"id": tg_id, "first_name": "Boris", "language_code": "ru"}
                )
            },
            headers={"Origin": settings.application_origin},
        )
        assert auth_ru.status_code == 200
        rec = portal.call(get_record)
        assert rec is not None
        assert getattr(rec, "locale", None) == "ru"
        assert getattr(rec, "locale_source", None) == "auto"

        # 2. Re-login with en-GB -> auto 'en'
        auth_en = client.post(
            "/api/auth/telegram",
            json={
                "init_data": _create_init_data(
                    {"id": tg_id, "first_name": "Boris", "language_code": "en-GB"}
                )
            },
            headers={"Origin": settings.application_origin},
        )
        assert auth_en.status_code == 200
        rec = portal.call(get_record)
        assert rec is not None
        assert rec.language_code == "en-GB"
        assert getattr(rec, "locale", None) == "en"
        assert getattr(rec, "locale_source", None) == "auto"

        # 3. Bot upsert_from_bot with ru-BY -> auto 'ru'
        async def bot_upsert() -> Any:
            upsert_from_bot = getattr(app.state.user_store, "upsert_from_bot", None)
            assert callable(upsert_from_bot), "UserStore.upsert_from_bot must exist"
            tg_user = AiogramUser(id=tg_id, is_bot=False, first_name="Boris", language_code="ru-BY")
            return await upsert_from_bot(tg_user)

        rec = portal.call(bot_upsert)
        assert rec.language_code == "ru-BY"
        assert getattr(rec, "locale", None) == "ru"
        assert getattr(rec, "locale_source", None) == "auto"

        # 4. Explicit switch via PATCH /api/profile/locale with CSRF cookie
        csrf_resp = client.get("/api/auth/csrf")
        assert csrf_resp.status_code == 200
        csrf_headers = {
            "Origin": settings.application_origin,
            "X-CSRF-Token": csrf_resp.json()["csrf_token"],
        }
        patch_resp = client.patch(
            "/api/profile/locale", json={"locale": "en"}, headers=csrf_headers
        )
        assert patch_resp.status_code == 200
        assert patch_resp.headers.get("hx-refresh") == "true"
        patch_body = patch_resp.json()
        assert patch_body.get("locale") == "en"
        assert patch_body.get("locale_source") == "explicit"

        rec = portal.call(get_record)
        assert getattr(rec, "locale", None) == "en"
        assert getattr(rec, "locale_source", None) == "explicit"

        # 5. Subsequent Mini App login and Bot /start with language_code='ru' preserve explicit 'en'
        auth_ru_again = client.post(
            "/api/auth/telegram",
            json={
                "init_data": _create_init_data(
                    {"id": tg_id, "first_name": "Boris", "language_code": "ru"}
                )
            },
            headers={"Origin": settings.application_origin},
        )
        assert auth_ru_again.status_code == 200

        async def bot_start_ru() -> SendMessage:
            harness = _BotHarness(app, bot_calls)
            try:
                return await harness.send_command(
                    "/start", user_id=tg_id, first_name="Boris", language_code="ru"
                )
            finally:
                await harness.close()

        start_reply = portal.call(bot_start_ru)
        assert start_reply.text is not None
        assert not _has_cyrillic(start_reply.text)

        rec = portal.call(get_record)
        assert rec.language_code == "ru"
        assert getattr(rec, "locale", None) == "en"
        assert getattr(rec, "locale_source", None) == "explicit"

        # 6. Unsupported locale returns 422/400 without mutating DB
        refreshed_csrf = client.get("/api/auth/csrf")
        assert refreshed_csrf.status_code == 200
        csrf_headers["X-CSRF-Token"] = refreshed_csrf.json()["csrf_token"]
        bad_resp = client.patch("/api/profile/locale", json={"locale": "de"}, headers=csrf_headers)
        assert bad_resp.status_code in (400, 422)
        rec = portal.call(get_record)
        assert getattr(rec, "locale", None) == "en"
        assert getattr(rec, "locale_source", None) == "explicit"

        # 7. Unauthenticated PATCH returns 401
        client.cookies.clear()
        anon_resp = client.patch(
            "/api/profile/locale",
            json={"locale": "ru"},
            headers={"Origin": settings.application_origin},
        )
        assert anon_resp.status_code == 401


@pytest.mark.timeout(25)
def test_miniapp_switch_immediately_updates_ssr_bot_and_pending_notices(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Switching locale in Mini App syncs SSR pages, Bot responses/menu, and queued outboxes."""
    bot_calls: list[Any] = []
    fail_set_commands = False

    async def transport(_bot: Bot, method: Any, request_timeout: float | None = None) -> bool:
        bot_calls.append(method)
        if fail_set_commands and isinstance(method, SetMyCommands):
            raise RuntimeError("Simulated Telegram setMyCommands failure")
        return True

    monkeypatch.setattr(Bot, "__call__", transport)

    db_path = tmp_path / "e2e_sync.db"
    settings = _make_settings(db_path)
    owner_id = 3001
    giver_id = 3002
    app = create_app(settings)

    with TestClient(app) as client:
        assert client.portal is not None
        portal = client.portal

        # 1. Authenticate owner (Bearer) and giver (cookie + CSRF, initially ru-RU)
        owner_auth = client.post(
            "/api/auth/telegram",
            json={
                "init_data": _create_init_data(
                    {"id": owner_id, "first_name": "Olga", "language_code": "en-US"}
                )
            },
            headers={"Origin": settings.application_origin},
        )
        assert owner_auth.status_code == 200
        owner_headers = {
            "Authorization": f"Bearer {owner_auth.json()['token']}",
            "Origin": settings.application_origin,
        }
        client.cookies.clear()

        giver_auth = client.post(
            "/api/auth/telegram",
            json={
                "init_data": _create_init_data(
                    {"id": giver_id, "first_name": "Dmitry", "language_code": "ru-RU"}
                )
            },
            headers={"Origin": settings.application_origin},
        )
        assert giver_auth.status_code == 200
        csrf_resp = client.get("/api/auth/csrf")
        assert csrf_resp.status_code == 200
        giver_csrf_headers = {
            "Origin": settings.application_origin,
            "X-CSRF-Token": csrf_resp.json()["csrf_token"],
        }

        # Verify Mini App shell initially renders in Russian for ru-RU user
        home_ru = client.get("/")
        assert home_ru.status_code == 200
        assert _html_lang(home_ru.text) == "ru"
        assert "Загрузка" in home_ru.text

        # 2. Giver starts the bot -> creates verified bot_destinations
        async def bot_initial_start() -> SendMessage:
            harness = _BotHarness(app, bot_calls)
            try:
                return await harness.send_command(
                    "/start", user_id=giver_id, first_name="Dmitry", language_code="ru-RU"
                )
            finally:
                await harness.close()

        initial_start_msg = portal.call(bot_initial_start)
        assert initial_start_msg.text is not None

        # 3. Create wishlist, item, favorite, reservation, receipt, and reminder while on ru
        event_date = (datetime.now(UTC) + timedelta(days=3)).isoformat()
        wl_resp = client.post(
            "/api/wishlists",
            json={"name": "Holiday List", "event_date": event_date},
            headers=owner_headers,
        )
        assert wl_resp.status_code == 201
        wl_data = wl_resp.json()
        wishlist_id = int(wl_data["id"])
        public_token = str(wl_data["share_token"])

        item_resp = client.post(
            f"/api/wishlists/{wishlist_id}/items",
            json={"title": "Espresso Machine", "quantity": 2},
            headers=owner_headers,
        )
        assert item_resp.status_code == 201
        item_id = int(item_resp.json()["id"])

        fav_resp = client.post(f"/api/favorites/{wishlist_id}", headers=giver_csrf_headers)
        assert fav_resp.status_code == 200

        reserve_resp = client.post(
            f"/api/public/wishlists/{public_token}/items/{item_id}/reservations",
            json={"quantity": 1},
            headers=giver_csrf_headers,
        )
        assert reserve_resp.status_code == 201

        receipt_resp = client.post(
            f"/api/wishlists/{wishlist_id}/items/{item_id}/receipts",
            json={"quantity": 1},
            headers=owner_headers,
        )
        assert receipt_resp.status_code == 201

        base_now = int(time.time()) + 10

        async def schedule_pending_reminder() -> None:
            await ReminderScheduler(app.state.wishlist_store, settings).run_once(base_now)

        portal.call(schedule_pending_reminder)

        with sqlite3.connect(db_path) as conn:
            pending_notices = conn.execute(
                "SELECT status FROM notification_outbox WHERE giver_user_id = ?",
                (giver_id,),
            ).fetchall()
            pending_reminders = conn.execute(
                "SELECT status FROM reminder_outbox WHERE user_id = ? AND kind = 'list'",
                (giver_id,),
            ).fetchall()
        assert pending_notices == [("pending",)]
        assert pending_reminders == [("pending",)]

        # 4. Switch giver locale to 'en' via Mini App PATCH /api/profile/locale
        bot_calls.clear()
        switch_en = client.patch(
            "/api/profile/locale", json={"locale": "en"}, headers=giver_csrf_headers
        )
        assert switch_en.status_code == 200
        assert switch_en.headers.get("hx-refresh") == "true"
        assert switch_en.json().get("locale") == "en"
        assert switch_en.json().get("locale_source") == "explicit"

        cmd_calls = [call for call in bot_calls if isinstance(call, SetMyCommands)]
        assert cmd_calls, "Switching locale must sync SetMyCommands for active bot destination"
        last_cmd = cmd_calls[-1]
        assert isinstance(last_cmd.scope, BotCommandScopeChat)
        assert last_cmd.scope.chat_id == giver_id
        descriptions = " ".join(cmd.description for cmd in last_cmd.commands)
        assert descriptions and not _has_cyrillic(descriptions)

        # Verify best-effort resilience when set_my_commands fails (HTTP stays 200, no rollback)
        fail_set_commands = True
        switch_ru_resilient = client.patch(
            "/api/profile/locale", json={"locale": "ru"}, headers=giver_csrf_headers
        )
        assert switch_ru_resilient.status_code == 200
        assert switch_ru_resilient.json().get("locale") == "ru"

        fail_set_commands = False
        switch_en_final = client.patch(
            "/api/profile/locale", json={"locale": "en"}, headers=giver_csrf_headers
        )
        assert switch_en_final.status_code == 200
        assert switch_en_final.json().get("locale") == "en"
        assert switch_en_final.json().get("locale_source") == "explicit"

        # 5a. Mini App & SSR HTML responses reflect 'en', and anonymous /share obeys query/header
        settings_page = client.get("/settings")
        assert settings_page.status_code == 200
        assert _html_lang(settings_page.text) == "en"
        assert "/api/profile/locale" in settings_page.text
        assert "English" in settings_page.text
        assert "Settings" in settings_page.text or "Language" in settings_page.text
        assert "Настройки" not in settings_page.text

        home_en = client.get("/")
        assert home_en.status_code == 200
        assert _html_lang(home_en.text) == "en"
        assert "Loading" in home_en.text
        assert "Загрузка" not in home_en.text

        reservations_page = client.get("/web/reservations")
        assert reservations_page.status_code == 200
        assert _html_lang(reservations_page.text) == "en"
        res_soup = BeautifulSoup(reservations_page.text, "html.parser")
        settings_link = res_soup.find("a", href="/settings")
        assert settings_link is not None
        assert "settings" in settings_link.get_text(strip=True).casefold()

        saved_cookies = dict(client.cookies)
        client.cookies.clear()
        try:
            with sqlite3.connect(db_path) as conn:
                users_before = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

            anon_default = client.get(f"/share/{public_token}")
            assert anon_default.status_code == 200
            assert _html_lang(anon_default.text) == "en"

            anon_query_ru = client.get(f"/share/{public_token}?lang=ru")
            assert anon_query_ru.status_code == 200
            assert _html_lang(anon_query_ru.text) == "ru"

            anon_header_ru = client.get(
                f"/share/{public_token}",
                headers={"Accept-Language": "ru-RU,ru;q=0.9"},
            )
            assert anon_header_ru.status_code == 200
            assert _html_lang(anon_header_ru.text) == "ru"

            anon_unsupported = client.get(
                f"/share/{public_token}",
                headers={"Accept-Language": "fr-FR,de;q=0.8"},
            )
            assert anon_unsupported.status_code == 200
            assert _html_lang(anon_unsupported.text) == "en"

            with sqlite3.connect(db_path) as conn:
                users_after = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            assert users_after == users_before
        finally:
            client.cookies.update(saved_cookies)

        # 5b. Bot commands reply in English even when client language_code is 'ru'
        bot_calls.clear()

        async def exercise_bot_commands() -> tuple[
            SendMessage, SendMessage, SendMessage, SendMessage
        ]:
            harness = _BotHarness(app, bot_calls)
            try:
                start_msg = await harness.send_command(
                    "/start", user_id=giver_id, first_name="Dmitry", language_code="ru"
                )
                help_msg = await harness.send_command(
                    "/help", user_id=giver_id, first_name="Dmitry", language_code="ru"
                )
                bday_msg = await harness.send_command(
                    "/birthdays", user_id=giver_id, first_name="Dmitry", language_code="ru"
                )
                support_msg = await harness.send_command(
                    "/support", user_id=giver_id, first_name="Dmitry", language_code="ru"
                )
                return start_msg, help_msg, bday_msg, support_msg
            finally:
                await harness.close()

        start_msg, help_msg, bday_msg, support_msg = portal.call(exercise_bot_commands)

        assert start_msg.text is not None and not _has_cyrillic(start_msg.text)
        assert "Create wishlist" in str(start_msg.reply_markup)
        bot_cmd_syncs = [call for call in bot_calls if isinstance(call, SetMyCommands)]
        assert bot_cmd_syncs
        assert isinstance(bot_cmd_syncs[-1].scope, BotCommandScopeChat)
        assert bot_cmd_syncs[-1].scope.chat_id == giver_id
        assert not _has_cyrillic(" ".join(c.description for c in bot_cmd_syncs[-1].commands))

        assert help_msg.text is not None and not _has_cyrillic(help_msg.text)
        assert "wishlist" in help_msg.text.casefold()
        assert "support" in help_msg.text.casefold()

        assert bday_msg.text is not None and not _has_cyrillic(bday_msg.text)
        assert "Birthdays:" in bday_msg.text
        assert "Add" in str(bday_msg.reply_markup)

        assert support_msg.text is not None and not _has_cyrillic(support_msg.text)
        assert "Cancel" in str(support_msg.reply_markup)
        assert "Отмена" not in str(support_msg.reply_markup)

        # 5c. Previously queued pending notice & reminder deliver in English (surprise preserved)
        sender = FakeNoticeSender()

        async def deliver_pending() -> None:
            worker = NoticeWorker(app.state.notice_store, sender, settings)
            await worker.run_once(base_now + 1)
            await worker.run_once(base_now + 3)

        portal.call(deliver_pending)

        assert len(sender.calls) == 2
        assert all(chat_id == giver_id for chat_id, _ in sender.calls)

        gift_notices = [text for _, text in sender.calls if "Espresso Machine" in text]
        list_reminders = [
            text
            for _, text in sender.calls
            if "Holiday List" in text and "Espresso Machine" not in text
        ]
        assert len(gift_notices) == 1
        assert len(list_reminders) == 1

        assert "Holiday List" in gift_notices[0]
        assert "received" in gift_notices[0].casefold()
        assert not _has_cyrillic(gift_notices[0])

        assert (
            "upcoming" in list_reminders[0].casefold() or "occasion" in list_reminders[0].casefold()
        )
        assert not _has_cyrillic(list_reminders[0])
        assert "reservation" not in list_reminders[0].casefold()
        assert "брон" not in list_reminders[0].casefold()
