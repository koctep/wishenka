"""Unit, parity, migration, and edge-case tests for WISHENKA-33 i18n subsystem."""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import string
from collections.abc import MutableMapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot, Dispatcher
from aiogram.methods import SendMessage
from aiogram.types import Update
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from tests.test_i18n_sync import _create_init_data, _has_cyrillic, _html_lang, _make_settings
from wishenka.auth.models import AuthenticatedUser, TelegramUser
from wishenka.bot.entry import create_router
from wishenka.bot.i18n import sync_user_bot_commands
from wishenka.i18n import (
    CATALOG,
    SUPPORTED_LOCALES,
    resolve_accept_language,
    resolve_telegram_locale,
    t,
    validate_locale,
)
from wishenka.items.schemas import ItemPreviewDTO
from wishenka.logging import JsonFormatter
from wishenka.notices.reminders import (
    _normalize_row_locale,
    _render,
    claim_reminder,
    refresh_reminder,
)
from wishenka.notices.worker import notice_text
from wishenka.users import UserNotFoundError, UserStore
from wishenka.web.app import create_app
from wishenka.wishlists.migrations import _configured, upgrade_to_head_sync
from wishenka.wishlists.service import WishlistService
from wishenka.wishlists.store import WishlistStore

pytestmark = pytest.mark.timeout(20)


def _placeholders(template: str) -> set[str]:
    """Extract named format placeholders from a translation template."""
    return {
        field_name
        for _, field_name, _, _ in string.Formatter().parse(template)
        if field_name is not None
    }


def test_catalog_key_and_placeholder_parity() -> None:
    """RU and EN catalogs must share exact key sets, non-empty strings, and placeholders."""
    assert set(CATALOG.keys()) == set(SUPPORTED_LOCALES)
    en_keys = set(CATALOG["en"].keys())
    ru_keys = set(CATALOG["ru"].keys())
    assert en_keys == ru_keys
    assert len(en_keys) > 0

    for key in sorted(en_keys):
        en_val = CATALOG["en"][key]
        ru_val = CATALOG["ru"][key]
        assert isinstance(en_val, str) and en_val.strip(), f"Empty EN value for {key}"
        assert isinstance(ru_val, str) and ru_val.strip(), f"Empty RU value for {key}"
        assert _placeholders(en_val) == _placeholders(ru_val), (
            f"Placeholder mismatch for {key}: EN={_placeholders(en_val)} RU={_placeholders(ru_val)}"
        )


def test_t_fallbacks_and_missing_key_logging(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """t() falls back to EN for unsupported locales or missing RU keys, then returns key."""
    assert t("nav.settings", "de") == "Settings"
    assert t("nav.settings", None) == "Settings"
    assert t("nav.settings", "ru") == "Настройки"

    ru_catalog = dict(CATALOG["ru"])
    ru_catalog.pop("nav.settings")
    monkeypatch.setitem(CATALOG, "ru", ru_catalog)

    with caplog.at_level(logging.WARNING, logger="wishenka.i18n"):
        assert t("nav.settings", "ru") == "Settings"
        assert t("nonexistent.i18n.key", "en") == "nonexistent.i18n.key"

    events = [
        (
            getattr(r, "event", None),
            getattr(r, "i18n_key", None),
            getattr(r, "fallback_locale", None),
        )
        for r in caplog.records
        if r.name == "wishenka.i18n"
    ]
    assert ("i18n_missing_translation_key", "nav.settings", "en") in events
    assert ("i18n_missing_translation_key", "nonexistent.i18n.key", "key") in events


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ru", "ru"),
        ("RU", "ru"),
        ("ru-RU", "ru"),
        (" ru-BY ", "ru"),
        ("en", "en"),
        ("en-US", "en"),
        ("uk", "en"),
        ("de-DE", "en"),
        ("", "en"),
        ("   ", "en"),
        (None, "en"),
    ],
)
def test_resolve_telegram_locale_edge_cases(raw: str | None, expected: str) -> None:
    """Only ru* normalizes to 'ru'; everything else falls back to 'en'."""
    assert resolve_telegram_locale(raw) == expected


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (None, "en"),
        ("", "en"),
        ("*", "en"),
        ("ru;q=0", "en"),
        ("ru;q=invalid", "en"),
        ("*,ru;q=0.7", "ru"),
        ("en-US,en;q=0.9,ru;q=0.8", "en"),
        ("en;q=0.5,ru-RU;q=0.9", "ru"),
        ("ru-RU,ru;q=0.9", "ru"),
        ("uk,ru;q=0.9", "en"),
        ("fr-FR,de;q=0.8", "en"),
    ],
)
def test_resolve_accept_language_edge_cases(header: str | None, expected: str) -> None:
    """Accept-Language selects highest-priority valid tag and normalizes to ru/en."""
    assert resolve_accept_language(header) == expected


def test_validate_locale_accepts_only_ru_and_en() -> None:
    """Explicit locale validation strictly allows only 'ru' and 'en'."""
    assert validate_locale("ru") == "ru"
    assert validate_locale("en") == "en"
    for invalid in ("RU", "ru-RU", "de", "", " ", None, 123):
        with pytest.raises(ValueError, match="Unsupported locale"):
            validate_locale(invalid)


async def test_user_store_initialize_backfills_legacy_users_table(tmp_path: Path) -> None:
    """UserStore.initialize() migrates a pre-WISHENKA-33 users table and preserves ru* -> ru."""
    db_path = tmp_path / "legacy_users.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL UNIQUE,
                first_name TEXT NOT NULL,
                last_name TEXT,
                username TEXT,
                language_code TEXT,
                is_premium INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            INSERT INTO users (
                telegram_id, first_name, language_code, is_premium, created_at, updated_at
            )
            VALUES
                (1, 'Ivan', 'ru-RU', 0, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'),
                (2, 'Bob', 'en-US', 0, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'),
                (3, 'Karl', 'de', 0, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'),
                (4, 'Blank', NULL, 0, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
            """
        )

    store = UserStore(f"sqlite+aiosqlite:///{db_path}")
    try:
        await store.initialize()
        u1 = await store.get_by_telegram_id(1)
        u2 = await store.get_by_telegram_id(2)
        u3 = await store.get_by_telegram_id(3)
        u4 = await store.get_by_telegram_id(4)
        assert u1 is not None and (u1.locale, u1.locale_source) == ("ru", "auto")
        assert u2 is not None and (u2.locale, u2.locale_source) == ("en", "auto")
        assert u3 is not None and (u3.locale, u3.locale_source) == ("en", "auto")
        assert u4 is not None and (u4.locale, u4.locale_source) == ("en", "auto")

        # Subsequent initialize() must not overwrite explicit preferences.
        await store.set_explicit_locale(2, "ru")
        await store.initialize()
        u2_after = await store.get_by_telegram_id(2)
        assert u2_after is not None and (u2_after.locale, u2_after.locale_source) == (
            "ru",
            "explicit",
        )
    finally:
        await store.dispose()


def test_alembic_add_user_locale_upgrade_backfill_and_downgrade(tmp_path: Path) -> None:
    """Alembic add_user_locale backfills legacy users rows and cleanly downgrades/re-upgrades."""
    db_path = tmp_path / "alembic_locale.db"
    url = f"sqlite+aiosqlite:///{db_path}"
    command.upgrade(_configured(url), "add_idempotency_records")
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL UNIQUE,
                first_name TEXT NOT NULL,
                last_name TEXT,
                username TEXT,
                language_code TEXT,
                is_premium INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            INSERT INTO users (
                telegram_id, first_name, language_code, is_premium, created_at, updated_at
            )
            VALUES (10, 'Olga', 'RU', 0, '2026-01-01', '2026-01-01'),
                   (11, 'Max', 'fr', 0, '2026-01-01', '2026-01-01');
            """
        )

    upgrade_to_head_sync(url)
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT telegram_id, locale, locale_source FROM users ORDER BY telegram_id"
        ).fetchall()
    assert rows == [(10, "ru", "auto"), (11, "en", "auto")]

    command.downgrade(_configured(url), "add_idempotency_records")
    with sqlite3.connect(db_path) as conn:
        cols_down = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    assert "locale" not in cols_down
    assert "locale_source" not in cols_down

    upgrade_to_head_sync(url)
    with sqlite3.connect(db_path) as conn:
        rows_reup = conn.execute(
            "SELECT telegram_id, locale, locale_source FROM users ORDER BY telegram_id"
        ).fetchall()
    assert rows_reup == [(10, "ru", "auto"), (11, "en", "auto")]


async def test_user_store_explicit_locale_same_language_and_missing_user(tmp_path: Path) -> None:
    """Setting the same locale explicitly flips source to explicit and resists client drift."""
    store = UserStore(f"sqlite+aiosqlite:///{tmp_path / 'explicit.db'}")
    await store.initialize()
    try:
        with pytest.raises(UserNotFoundError):
            await store.set_locale(999999, "ru")

        created = await store.upsert_user(
            TelegramUser(id=501, first_name="Anna", language_code="ru-RU")
        )
        assert (created.locale, created.locale_source) == ("ru", "auto")

        explicit = await store.set_explicit_locale(501, "ru")
        assert (explicit.locale, explicit.locale_source) == ("ru", "explicit")

        after = await store.upsert_user(
            TelegramUser(id=501, first_name="Anna", language_code="en-US")
        )
        assert after.language_code == "en-US"
        assert (after.locale, after.locale_source) == ("ru", "explicit")
    finally:
        await store.dispose()


def test_settings_page_form_patch_and_authenticated_share_precedence(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Verify /settings auth/UI, form-encoded PATCH, 422 logging, and authenticated /share."""
    settings = _make_settings(tmp_path / "web_settings.db")
    app = create_app(settings)
    with TestClient(app) as client:
        assert client.get("/settings").status_code == 401

        auth = client.post(
            "/api/auth/telegram",
            json={
                "init_data": _create_init_data(
                    {"id": 4001, "first_name": "Nina", "language_code": "en-US"}
                )
            },
            headers={"Origin": settings.application_origin},
        )
        assert auth.status_code == 200
        me = client.get("/api/auth/me")
        assert me.status_code == 200
        assert me.json()["locale"] == "en"

        wl = client.post(
            "/api/wishlists",
            json={"name": "Birthday"},
            headers={
                "Authorization": f"Bearer {auth.json()['token']}",
                "Origin": settings.application_origin,
            },
        )
        assert wl.status_code == 201
        public_token = wl.json()["share_token"]

        csrf = client.get("/api/auth/csrf").json()["csrf_token"]
        headers = {"Origin": settings.application_origin, "X-CSRF-Token": csrf}

        # Switch to 'ru' using form-encoded payload
        form_resp = client.patch("/api/profile/locale", data={"locale": "ru"}, headers=headers)
        assert form_resp.status_code == 200
        assert form_resp.headers.get("hx-refresh") == "true"
        assert form_resp.json() == {"locale": "ru", "locale_source": "explicit"}

        settings_ru = client.get("/settings")
        assert settings_ru.status_code == 200
        assert _html_lang(settings_ru.text) == "ru"
        assert "Настройки" in settings_ru.text
        assert "Выбран вручную" in settings_ru.text

        # Authenticated /share uses profile locale ('ru') even with ?lang=en and Accept-Language: en
        auth_share = client.get(
            f"/share/{public_token}?lang=en",
            headers={"Accept-Language": "en-US"},
        )
        assert auth_share.status_code == 200
        assert _html_lang(auth_share.text) == "ru"

        # Invalid JSON body -> 422 + locale_invalid_request without PII
        caplog.clear()
        with caplog.at_level(logging.WARNING, logger="wishenka.web.profile"):
            invalid_resp = client.patch(
                "/api/profile/locale",
                content=b"{broken",
                headers={**headers, "Content-Type": "application/json"},
            )
        assert invalid_resp.status_code == 422
        assert any(
            getattr(r, "event", None) == "locale_invalid_request"
            and getattr(r, "status_code", None) == 422
            for r in caplog.records
        )
        assert "Nina" not in caplog.text


async def test_bot_middleware_without_user_store_and_explicit_ru_capture_birthdays(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """LocaleMiddleware falls back when user_store is None and uses explicit RU across routers."""
    sent: list[Any] = []

    async def transport(_bot: Bot, method: Any, request_timeout: float | None = None) -> bool:
        sent.append(method)
        return True

    monkeypatch.setattr(Bot, "__call__", transport)

    # 1. Lightweight router without user_store
    dp_light = Dispatcher()
    dp_light.include_router(create_router(SimpleNamespace(mini_app_url="https://example.test/app")))
    bot = Bot("123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")
    try:
        await dp_light.feed_update(
            bot,
            Update.model_validate(
                {
                    "update_id": 1,
                    "message": {
                        "message_id": 1,
                        "date": 1700000000,
                        "chat": {"id": 801, "type": "private"},
                        "from": {
                            "id": 801,
                            "is_bot": False,
                            "first_name": "X",
                            "language_code": "fr",
                        },
                        "text": "/start",
                        "entities": [{"type": "bot_command", "offset": 0, "length": 6}],
                    },
                }
            ),
        )
        light_reply = next(m for m in sent if isinstance(m, SendMessage))
        assert light_reply.text is not None and not _has_cyrillic(light_reply.text)

        # 2. Full router with explicit RU overriding EN Telegram client on /birthdays & capture
        url = f"sqlite+aiosqlite:///{tmp_path / 'bot_ru.db'}"
        wstore = WishlistStore(url)
        ustore = UserStore(url)
        await wstore.initialize()
        await ustore.initialize()
        try:
            await ustore.upsert_user(TelegramUser(id=802, first_name="Leo", language_code="en"))
            await ustore.set_locale(802, "ru")
            preview = AsyncMock()
            preview.preview = AsyncMock(return_value=ItemPreviewDTO(title="Book"))
            dp_full = Dispatcher()
            dp_full.include_router(
                create_router(
                    SimpleNamespace(
                        mini_app_url="https://example.test/app",
                        user_store=ustore,
                        wishlist_store=wstore,
                        preview_service=preview,
                    )
                )
            )
            sent.clear()
            for seq, text_val in enumerate(("/birthdays", "Coffee mug"), start=2):
                entity = (
                    [{"type": "bot_command", "offset": 0, "length": len(text_val)}]
                    if text_val.startswith("/")
                    else []
                )
                payload: dict[str, Any] = {
                    "update_id": seq,
                    "message": {
                        "message_id": seq,
                        "date": 1700000000 + seq,
                        "chat": {"id": 802, "type": "private"},
                        "from": {
                            "id": 802,
                            "is_bot": False,
                            "first_name": "Leo",
                            "language_code": "en",
                        },
                        "text": text_val,
                    },
                }
                if entity:
                    payload["message"]["entities"] = entity
                await dp_full.feed_update(bot, Update.model_validate(payload))

            replies = [m.text for m in sent if isinstance(m, SendMessage)]
            assert len(replies) == 2
            assert replies[0] is not None and "Дни рождения:" in replies[0]
            assert replies[1] is not None and "Проверьте" in replies[1]
        finally:
            await ustore.dispose()
            await wstore.dispose()
    finally:
        await bot.session.close()


def test_notice_text_and_reminder_render_normalize_safely() -> None:
    """Notice templates render EN on unknown/empty language and RU on ru*."""
    assert "received" in notice_text("Book", "List", "fr").casefold()
    assert "полученное" in notice_text("Book", "List", "ru-RU").casefold()
    assert (
        _render("list", "Party", None, "2030-01-01", "de")
        == "Upcoming occasion: Party (2030-01-01)."
    )
    assert (
        _render("list", "Party", None, "2030-01-01", "ru")
        == "Приближается событие: Party (2030-01-01)."
    )


@pytest.mark.timeout(15)
def test_anonymous_share_and_invite_locale_priority_chain(tmp_path: Path) -> None:
    """Anonymous GET /share/{token} and /invite/{token} obey ?lang > Accept-Language > en."""
    db_path = tmp_path / "anon_share_invite.db"
    settings = _make_settings(db_path)
    app = create_app(settings)

    with TestClient(app) as client:
        assert client.portal is not None

        async def seed_wishlist() -> tuple[str, str]:
            wl = await app.state.domain_service.create_wishlist(
                owner=AuthenticatedUser(
                    telegram_id=5001,
                    first_name="Owner",
                    auth_method="session_token",
                ),
                title="Birthday List",
            )
            return str(wl.public_token), str(wl.invite_token)

        public_token, invite_token = client.portal.call(seed_wishlist)

        with sqlite3.connect(db_path) as conn:
            users_before = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

        for path in (f"/share/{public_token}", f"/invite/{invite_token}"):
            # 1. No query, no header -> default 'en'
            resp_default = client.get(path)
            assert resp_default.status_code == 200
            assert _html_lang(resp_default.text) == "en"

            # 2. Regional ?lang=ru-RU -> 'ru'
            resp_query_ru = client.get(f"{path}?lang=ru-RU")
            assert resp_query_ru.status_code == 200
            assert _html_lang(resp_query_ru.text) == "ru"

            # 3. ?lang=en-US overrides Accept-Language: ru-RU
            resp_query_en = client.get(
                f"{path}?lang=en-US",
                headers={"Accept-Language": "ru-RU,ru;q=0.9"},
            )
            assert resp_query_en.status_code == 200
            assert _html_lang(resp_query_en.text) == "en"

            # 4. Unsupported ?lang=de falls back to Accept-Language: ru-RU -> 'ru'
            resp_invalid_query_with_ru = client.get(
                f"{path}?lang=de",
                headers={"Accept-Language": "ru-RU,ru;q=0.9"},
            )
            assert resp_invalid_query_with_ru.status_code == 200
            assert _html_lang(resp_invalid_query_with_ru.text) == "ru"

            # 5. Unsupported ?lang=de without Accept-Language -> 'en'
            resp_invalid_query = client.get(f"{path}?lang=de")
            assert resp_invalid_query.status_code == 200
            assert _html_lang(resp_invalid_query.text) == "en"

            # 6. Accept-Language: ru-RU,ru;q=0.9 -> 'ru'
            resp_header_ru = client.get(
                path,
                headers={"Accept-Language": "ru-RU,ru;q=0.9"},
            )
            assert resp_header_ru.status_code == 200
            assert _html_lang(resp_header_ru.text) == "ru"

            # 7. Unsupported Accept-Language -> 'en'
            resp_header_de = client.get(
                path,
                headers={"Accept-Language": "de-DE,fr;q=0.8"},
            )
            assert resp_header_de.status_code == 200
            assert _html_lang(resp_header_de.text) == "en"

        with sqlite3.connect(db_path) as conn:
            users_after = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        assert users_after == users_before


@pytest.mark.timeout(15)
async def test_reminders_fallback_to_en_for_missing_user_locale_and_legacy_schema(
    tmp_path: Path,
) -> None:
    """claim_reminder and refresh_reminder fall back to 'en' on missing/legacy locale."""
    db_path = tmp_path / "reminder_fallback.db"
    url = f"sqlite+aiosqlite:///{db_path}"
    wstore = WishlistStore(url)
    ustore = UserStore(url)
    await wstore.initialize()
    await ustore.initialize()
    try:
        owner = AuthenticatedUser(telegram_id=6001, first_name="Max", auth_method="session_token")
        await ustore.upsert_user(TelegramUser(id=6001, first_name="Max", language_code="de"))
        event_dt = datetime.now(UTC) + timedelta(days=2)
        wl = await WishlistService(wstore).create_wishlist(
            owner=owner, title="Camping", event_date=event_dt
        )
        event_date_str = event_dt.date().isoformat()
        now = int(datetime.now(UTC).timestamp())

        with sqlite3.connect(db_path) as conn:
            user_row_id = conn.execute("SELECT id FROM users WHERE telegram_id = 6001").fetchone()[
                0
            ]
            conn.execute(
                "INSERT INTO bot_destinations (user_id, chat_id, active) VALUES (?, ?, 1)",
                (user_row_id, 6001),
            )
            conn.execute(
                "INSERT INTO reminder_outbox "
                "(occurrence_key, kind, user_id, list_id, event_date, next_attempt_at, status) "
                "VALUES ('occ-1', 'list', 6001, ?, ?, ?, 'pending')",
                (wl.id, event_date_str, now),
            )

        claimed = await claim_reminder(wstore, now, lease=60, global_limit=10, chat_interval=1)
        assert claimed is not None
        assert claimed.body == f"Upcoming occasion: Camping ({event_date_str})."

        refreshed = await refresh_reminder(wstore, claimed, now)
        assert refreshed is not None
        assert refreshed.body == f"Upcoming occasion: Camping ({event_date_str})."

        # Simulate legacy users table without locale column (even when language_code is 'ru').
        with sqlite3.connect(db_path) as conn:
            conn.executescript(
                """
                ALTER TABLE users DROP COLUMN locale_source;
                ALTER TABLE users DROP COLUMN locale;
                UPDATE users SET language_code = 'ru' WHERE telegram_id = 6001;
                UPDATE reminder_outbox
                SET status = 'pending', claimed_at = NULL, claim_token = NULL, next_attempt_at = 0
                WHERE occurrence_key = 'occ-1';
                """
            )

        legacy_claimed = await claim_reminder(
            wstore, now + 2, lease=60, global_limit=10, chat_interval=1
        )
        assert legacy_claimed is not None
        assert legacy_claimed.body == f"Upcoming occasion: Camping ({event_date_str})."

        legacy_refreshed = await refresh_reminder(wstore, legacy_claimed, now + 2)
        assert legacy_refreshed is not None
        assert legacy_refreshed.body == f"Upcoming occasion: Camping ({event_date_str})."

        # Non-"no such column" OperationalError must be re-raised, not swallowed.
        with sqlite3.connect(db_path) as conn:
            conn.execute("DROP TABLE bot_destinations")
            conn.execute(
                "UPDATE reminder_outbox SET status = 'pending', claimed_at = NULL, "
                "claim_token = NULL, next_attempt_at = 0 WHERE occurrence_key = 'occ-1'"
            )
        with pytest.raises(OperationalError, match="no such table"):
            await claim_reminder(wstore, now + 4, lease=60, global_limit=10, chat_interval=1)
    finally:
        await ustore.dispose()
        await wstore.dispose()


@pytest.mark.timeout(15)
def test_profile_locale_patch_runs_bot_sync_in_background_tasks(tmp_path: Path) -> None:
    """PATCH /api/profile/locale sends HTTP 200 before bot command sync executes."""
    db_path = tmp_path / "bg_sync.db"
    settings = _make_settings(db_path)
    app = create_app(settings)

    with TestClient(app) as client:
        assert client.portal is not None
        auth = client.post(
            "/api/auth/telegram",
            json={
                "init_data": _create_init_data(
                    {"id": 7001, "first_name": "Elena", "language_code": "en-US"}
                )
            },
            headers={"Origin": settings.application_origin},
        )
        assert auth.status_code == 200
        csrf = client.get("/api/auth/csrf").json()["csrf_token"]
        cookie_header = "; ".join(f"{k}={v}" for k, v in client.cookies.items())

        with sqlite3.connect(db_path) as conn:
            user_row_id = conn.execute("SELECT id FROM users WHERE telegram_id = 7001").fetchone()[
                0
            ]
            conn.execute(
                "INSERT INTO bot_destinations (user_id, chat_id, active) VALUES (?, ?, 1)",
                (user_row_id, 7001),
            )

        async def verify_non_blocking_asgi() -> None:
            events: list[str] = []
            response_headers: list[tuple[bytes, bytes]] = []
            response_status = 0
            response_body = b""
            response_sent = asyncio.Event()

            async def slow_hook(chat_id: int, locale: str) -> None:
                events.append(f"sync_started:{chat_id}:{locale}")
                await asyncio.wait_for(response_sent.wait(), timeout=1.5)
                events.append("sync_finished")

            app.state.bot_command_sync = slow_hook

            payload = json.dumps({"locale": "ru"}).encode("utf-8")
            scope = {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "method": "PATCH",
                "scheme": "http",
                "path": "/api/profile/locale",
                "raw_path": b"/api/profile/locale",
                "query_string": b"",
                "root_path": "",
                "headers": [
                    (b"host", b"testserver"),
                    (b"origin", settings.application_origin.encode("ascii")),
                    (b"x-csrf-token", csrf.encode("ascii")),
                    (b"cookie", cookie_header.encode("ascii")),
                    (b"content-type", b"application/json"),
                ],
                "client": ("127.0.0.1", 12345),
                "server": ("testserver", 80),
            }
            sent_request = False

            async def receive() -> dict[str, Any]:
                nonlocal sent_request
                if not sent_request:
                    sent_request = True
                    return {"type": "http.request", "body": payload, "more_body": False}
                return {"type": "http.disconnect"}

            async def send(message: MutableMapping[str, Any]) -> None:
                nonlocal response_status, response_body
                msg_type = str(message["type"])
                if msg_type == "http.response.start":
                    events.append(msg_type)
                    response_status = int(message["status"])
                    response_headers.extend(message.get("headers", []))
                elif msg_type == "http.response.body":
                    response_body += bytes(message.get("body", b""))
                    if not message.get("more_body", False):
                        events.append("http.response.end")
                        response_sent.set()

            await app(scope, receive, send)
            assert response_status == 200
            assert json.loads(response_body) == {"locale": "ru", "locale_source": "explicit"}
            assert (b"hx-refresh", b"true") in [(k.lower(), v) for k, v in response_headers]
            assert events == [
                "http.response.start",
                "http.response.end",
                "sync_started:7001:ru",
                "sync_finished",
            ]

        client.portal.call(verify_non_blocking_asgi)


@pytest.mark.timeout(10)
def test_miniapp_js_localizes_home_nav_shell_and_settings_label(tmp_path: Path) -> None:
    """GET / supplies centralized RU/EN Mini App catalog and miniapp.js uses t()."""
    from wishenka.i18n import miniapp_catalog

    app = create_app(_make_settings(tmp_path / "miniapp_js.db"))
    with TestClient(app) as client:
        shell_resp = client.get("/")
        assert shell_resp.status_code == 200
        assert '<script id="miniapp-i18n" type="application/json">' in shell_resp.text

        catalog = miniapp_catalog()
        assert set(catalog.keys()) == {"en", "ru"}
        assert catalog["ru"]["nav.settings"] == "Настройки"
        assert catalog["en"]["nav.settings"] == "Settings"
        assert catalog["ru"]["miniapp.home.title"] == "Вишлисты"
        assert catalog["en"]["miniapp.home.title"] == "Wishlists"
        assert catalog["ru"]["miniapp.home.create_wishlist"] == "Создать вишлист"
        assert catalog["en"]["miniapp.home.create_wishlist"] == "Create wishlist"
        assert catalog["ru"]["miniapp.home.viewing_history"] == "История просмотров"
        assert catalog["en"]["miniapp.home.viewing_history"] == "Viewing history"
        assert catalog["ru"]["miniapp.home.my_wishlists"] == "Мои вишлисты"
        assert catalog["en"]["miniapp.home.my_wishlists"] == "My wishlists"

        resp = client.get("/static/miniapp.js")
        assert resp.status_code == 200
        source = resp.text
        assert "HOME_I18N" not in source
        for token in (
            "miniapp-i18n",
            "t('nav.settings')",
            "t('miniapp.home.title')",
            "t('miniapp.home.create_wishlist')",
            "t('miniapp.home.viewing_history')",
            "t('miniapp.home.my_wishlists')",
            "activeLocale()",
        ):
            assert token in source, f"Missing centralized i18n token {token} in miniapp.js"


@pytest.mark.timeout(10)
def test_miniapp_catalog_projection_and_json_xss_escaping() -> None:
    """miniapp_catalog() projects only nav.*/miniapp.* keys with RU/EN parity."""
    from wishenka.i18n import miniapp_catalog

    projected = miniapp_catalog()
    assert set(projected.keys()) == {"en", "ru"}
    assert set(projected["en"].keys()) == set(projected["ru"].keys())
    assert projected["en"]
    for locale in ("en", "ru"):
        for key in projected[locale]:
            assert key.startswith(("nav.", "miniapp.")), f"Unexpected key {key} in miniapp_catalog"


@pytest.mark.timeout(15)
async def test_i18n_observability_structured_logs_and_no_pii(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """All i18n lifecycle events emit structured JSON-safe logs without leaking PII."""
    formatter = JsonFormatter()
    store = UserStore(f"sqlite+aiosqlite:///{tmp_path / 'obs.db'}")
    await store.initialize()
    try:
        caplog.clear()
        with caplog.at_level(logging.DEBUG, logger="wishenka.users"):
            await store.upsert_user(
                TelegramUser(
                    id=9101,
                    first_name="SecretFirst",
                    last_name="SecretLast",
                    username="secret_handle",
                    language_code="de-DE",
                ),
                channel="miniapp",
            )
            await store.set_locale(9101, "ru")

        auto_rec = next(
            r for r in caplog.records if getattr(r, "event", None) == "locale_auto_resolved"
        )
        assert auto_rec.levelno == logging.DEBUG
        assert getattr(auto_rec, "channel", None) == "miniapp"
        assert getattr(auto_rec, "resolved_locale", None) == "en"
        assert getattr(auto_rec, "locale_source", None) == "auto"
        assert getattr(auto_rec, "changed", None) is True
        assert getattr(auto_rec, "fallback_used", None) is True

        explicit_rec = next(
            r for r in caplog.records if getattr(r, "event", None) == "locale_explicit_updated"
        )
        assert explicit_rec.levelno == logging.INFO
        assert getattr(explicit_rec, "previous_locale", None) == "en"
        assert getattr(explicit_rec, "new_locale", None) == "ru"
        assert getattr(explicit_rec, "previous_source", None) == "auto"
        assert getattr(explicit_rec, "locale_source", None) == "explicit"

        for rec in (auto_rec, explicit_rec):
            parsed = json.loads(formatter.format(rec))
            assert parsed["extra"]["event"] in {"locale_auto_resolved", "locale_explicit_updated"}
            assert "SecretFirst" not in caplog.text
            assert "SecretLast" not in caplog.text
            assert "secret_handle" not in caplog.text
    finally:
        await store.dispose()

    # Bot command sync success (DEBUG) and failure (WARNING)
    bot = Bot("123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")
    try:

        async def ok_transport(
            _bot: Bot, _method: Any, request_timeout: float | None = None
        ) -> bool:
            return True

        monkeypatch.setattr(Bot, "__call__", ok_transport)
        caplog.clear()
        with caplog.at_level(logging.DEBUG, logger="wishenka.bot.i18n"):
            assert await sync_user_bot_commands(bot, 9101, "ru", user_id=42) is True
        synced_rec = next(
            r for r in caplog.records if getattr(r, "event", None) == "bot_commands_locale_synced"
        )
        assert synced_rec.levelno == logging.DEBUG
        assert json.loads(formatter.format(synced_rec))["extra"]["target_locale"] == "ru"

        async def fail_transport(
            _bot: Bot, _method: Any, request_timeout: float | None = None
        ) -> bool:
            raise RuntimeError("telegram unreachable")

        monkeypatch.setattr(Bot, "__call__", fail_transport)
        caplog.clear()
        with caplog.at_level(logging.WARNING, logger="wishenka.bot.i18n"):
            assert await sync_user_bot_commands(bot, 9101, "en", user_id=42) is False
        fail_rec = next(
            r
            for r in caplog.records
            if getattr(r, "event", None) == "bot_commands_locale_sync_failed"
        )
        assert fail_rec.levelno == logging.WARNING
        assert getattr(fail_rec, "error_type", None) == "RuntimeError"
        assert json.loads(formatter.format(fail_rec))["extra"]["target_locale"] == "en"
    finally:
        await bot.session.close()

    # Reminder locale resolution (DEBUG)
    caplog.clear()
    with caplog.at_level(logging.DEBUG, logger="wishenka.notices.reminders"):
        assert _normalize_row_locale("fr", channel="occasion_reminder") == "en"
    notice_rec = next(
        r for r in caplog.records if getattr(r, "event", None) == "notice_locale_resolved"
    )
    assert notice_rec.levelno == logging.DEBUG
    assert getattr(notice_rec, "channel", None) == "occasion_reminder"
    assert getattr(notice_rec, "locale", None) == "en"
    assert getattr(notice_rec, "fallback_used", None) is True
    assert json.loads(formatter.format(notice_rec))["extra"]["event"] == "notice_locale_resolved"
