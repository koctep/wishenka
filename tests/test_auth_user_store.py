"""Failing reproduction tests for WISHENKA-44 TelegramUser database persistence."""

import asyncio
import hashlib
import hmac
import json
import time
import urllib.parse
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from wishenka.auth import TelegramUser
from wishenka.config import Settings
from wishenka.users import UserRecord, UserStore
from wishenka.web.app import create_app

pytestmark = pytest.mark.timeout(10)

TEST_BOT_TOKEN = "123456789:ABCdefGHIjklMNOpqrsTUVwxyz1234567"


def create_test_init_data(
    user_data: dict[str, Any],
    bot_token: str = TEST_BOT_TOKEN,
    auth_date: int | None = None,
    tampered: bool = False,
) -> str:
    """Generate a Telegram WebApp initData query string with HMAC-SHA256 signature."""
    if auth_date is None:
        auth_date = int(time.time())

    params: dict[str, str] = {
        "auth_date": str(auth_date),
        "user": json.dumps(user_data, separators=(",", ":")),
    }
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    computed_hash = hmac.new(
        secret_key, data_check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    if tampered:
        altered = "0" if computed_hash[-1] != "0" else "1"
        computed_hash = computed_hash[:-1] + altered

    params["hash"] = computed_hash
    return urllib.parse.urlencode(params)


def test_auth_telegram_persists_user_to_db(tmp_path: Path) -> None:
    """Authenticating a new user via POST /api/auth/telegram persists user record in db."""
    db_path = tmp_path / "user_persist.db"
    settings = Settings(
        bot_token=TEST_BOT_TOKEN,
        database_url=f"sqlite+aiosqlite:///{db_path}",
    )
    user_payload = {
        "id": 11223344,
        "first_name": "Alexander",
        "last_name": "Pushkin",
        "username": "pushkin",
        "language_code": "ru",
        "is_premium": True,
    }
    init_data = create_test_init_data(user_payload, bot_token=TEST_BOT_TOKEN)

    app = create_app(settings)
    with TestClient(app) as client:
        resp = client.post(
            "/api/auth/telegram",
            json={"init_data": init_data},
            headers={"Origin": "http://testserver"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "user_id" in data
        assert isinstance(data["user_id"], int)
        assert data["user_id"] > 0

        # Verify user record in database
        store = getattr(app.state, "user_store", None)
        assert store is not None, "app.state.user_store must be initialized"

        async def check_db() -> None:
            user = await store.get_by_telegram_id(11223344)
            assert user is not None
            assert user.id == data["user_id"]
            assert user.telegram_id == 11223344
            assert user.first_name == "Alexander"
            assert user.last_name == "Pushkin"
            assert user.username == "pushkin"
            assert user.language_code == "ru"
            assert user.is_premium is True
            assert user.created_at is not None
            assert user.updated_at is not None

        asyncio.run(check_db())


def test_auth_telegram_upserts_user_on_profile_change(tmp_path: Path) -> None:
    """Returning user profile changes are synchronized while preserving user_id."""
    db_path = tmp_path / "user_upsert.db"
    settings = Settings(
        bot_token=TEST_BOT_TOKEN,
        database_url=f"sqlite+aiosqlite:///{db_path}",
    )
    telegram_id = 55667788
    initial_payload = {
        "id": telegram_id,
        "first_name": "OldName",
        "last_name": "OldLast",
        "username": "oldhandle",
        "language_code": "en",
        "is_premium": False,
    }
    updated_payload = {
        "id": telegram_id,
        "first_name": "NewName",
        "last_name": None,
        "username": "newhandle",
        "language_code": "ru",
        "is_premium": True,
    }

    app = create_app(settings)
    with TestClient(app) as client:
        # First login
        init_data_1 = create_test_init_data(initial_payload, bot_token=TEST_BOT_TOKEN)
        resp1 = client.post(
            "/api/auth/telegram",
            json={"init_data": init_data_1},
            headers={"Origin": "http://testserver"},
        )
        assert resp1.status_code == 200
        first_user_id = resp1.json()["user_id"]

        # Second login with updated profile
        init_data_2 = create_test_init_data(updated_payload, bot_token=TEST_BOT_TOKEN)
        resp2 = client.post(
            "/api/auth/telegram",
            json={"init_data": init_data_2},
            headers={"Origin": "http://testserver"},
        )
        assert resp2.status_code == 200
        second_user_id = resp2.json()["user_id"]
        assert second_user_id == first_user_id

        store = getattr(app.state, "user_store", None)
        assert store is not None, "app.state.user_store must be initialized"

        async def check_db() -> None:
            user = await store.get_by_telegram_id(telegram_id)
            assert user is not None
            assert user.id == first_user_id
            assert user.first_name == "NewName"
            assert user.last_name is None
            assert user.username == "newhandle"
            assert user.language_code == "ru"
            assert user.is_premium is True

        asyncio.run(check_db())


@pytest.mark.asyncio
async def test_user_store_upsert_and_retrieval(tmp_path: Path) -> None:
    """Direct UserStore upsert and retrieval operations operate accurately."""
    db_path = tmp_path / "user_store_direct.db"
    store = UserStore(f"sqlite+aiosqlite:///{db_path}")
    await store.initialize()
    try:
        user_input = TelegramUser(
            id=77889900,
            first_name="Lev",
            last_name="Tolstoy",
            username="tolstoy",
            language_code="ru",
            is_premium=False,
        )
        record = await store.upsert_user(user_input)
        assert isinstance(record, UserRecord)
        assert record.id > 0
        assert record.telegram_id == 77889900
        assert record.first_name == "Lev"
        assert record.last_name == "Tolstoy"
        assert record.username == "tolstoy"
        assert record.language_code == "ru"
        assert record.is_premium is False
        assert record.created_at is not None
        assert record.updated_at is not None

        # Upsert update
        updated_input = TelegramUser(
            id=77889900,
            first_name="Leo",
            last_name="Tolstoy",
            username="leo_tolstoy",
            language_code="en",
            is_premium=True,
        )
        updated_record = await store.upsert_user(updated_input)
        assert updated_record.id == record.id
        assert updated_record.telegram_id == 77889900
        assert updated_record.first_name == "Leo"
        assert updated_record.username == "leo_tolstoy"
        assert updated_record.language_code == "en"
        assert updated_record.is_premium is True
    finally:
        await store.dispose()


@pytest.mark.asyncio
async def test_user_store_get_by_id_and_telegram_id(tmp_path: Path) -> None:
    """UserStore retrieves by primary key id and alternate key telegram_id."""
    db_path = tmp_path / "user_store_queries.db"
    store = UserStore(f"sqlite+aiosqlite:///{db_path}")
    await store.initialize()
    try:
        user_input = TelegramUser(
            id=12312312,
            first_name="Anton",
            last_name="Chekhov",
            username="chekhov",
        )
        created = await store.upsert_user(user_input)

        by_id = await store.get_by_id(created.id)
        assert by_id is not None
        assert by_id.id == created.id
        assert by_id.telegram_id == 12312312
        assert by_id.first_name == "Anton"

        by_tg = await store.get_by_telegram_id(12312312)
        assert by_tg is not None
        assert by_tg.id == created.id
        assert by_tg.username == "chekhov"

        # Non-existent lookups return None
        assert await store.get_by_id(9999999) is None
        assert await store.get_by_telegram_id(9999999) is None
    finally:
        await store.dispose()


def test_auth_telegram_session_user_id_linkage(tmp_path: Path) -> None:
    """Session issued on /telegram contains user_id and /me endpoint exposes user_id."""
    db_path = tmp_path / "session_linkage.db"
    settings = Settings(
        bot_token=TEST_BOT_TOKEN,
        database_url=f"sqlite+aiosqlite:///{db_path}",
    )
    user_payload = {
        "id": 99887766,
        "first_name": "Fyodor",
        "username": "dostoevsky",
    }
    init_data = create_test_init_data(user_payload, bot_token=TEST_BOT_TOKEN)

    app = create_app(settings)
    with TestClient(app) as client:
        auth_resp = client.post(
            "/api/auth/telegram",
            json={"init_data": init_data},
            headers={"Origin": "http://testserver"},
        )
        assert auth_resp.status_code == 200
        auth_data = auth_resp.json()
        user_id = auth_data.get("user_id")
        assert isinstance(user_id, int)
        token = auth_data["token"]

        # GET /api/auth/me using session cookie
        cookie_client = TestClient(app, cookies={settings.session_cookie_name: token})
        me_resp = cookie_client.get("/api/auth/me")
        assert me_resp.status_code == 200
        me_data = me_resp.json()
        assert me_data["telegram_id"] == 99887766
        assert me_data.get("user_id") == user_id


def test_auth_telegram_invalid_init_data_does_not_persist_user(tmp_path: Path) -> None:
    """Tampered or invalid init_data returns 401 and does not persist any user in db."""
    db_path = tmp_path / "invalid_auth.db"
    settings = Settings(
        bot_token=TEST_BOT_TOKEN,
        database_url=f"sqlite+aiosqlite:///{db_path}",
    )
    tampered_payload = {
        "id": 44332211,
        "first_name": "Hacker",
        "username": "hacker",
    }
    tampered_init_data = create_test_init_data(
        tampered_payload, bot_token=TEST_BOT_TOKEN, tampered=True
    )

    app = create_app(settings)
    with TestClient(app) as client:
        resp = client.post(
            "/api/auth/telegram",
            json={"init_data": tampered_init_data},
            headers={"Origin": "http://testserver"},
        )
        assert resp.status_code == 401

        store = getattr(app.state, "user_store", None)
        if store is not None:

            async def check_db() -> None:
                user = await store.get_by_telegram_id(44332211)
                assert user is None

            asyncio.run(check_db())


def test_guest_request_does_not_create_user(tmp_path: Path) -> None:
    """Anonymous visitors do not trigger user creation in database."""
    db_path = tmp_path / "guest_isolation.db"
    settings = Settings(
        bot_token=TEST_BOT_TOKEN,
        database_url=f"sqlite+aiosqlite:///{db_path}",
    )
    app = create_app(settings)
    with TestClient(app) as client:
        # Access healthcheck without credentials
        resp = client.get("/healthz")
        assert resp.status_code == 200

        store = getattr(app.state, "user_store", None)
        if store is not None:

            async def check_db() -> None:
                assert await store.get_by_id(1) is None

            asyncio.run(check_db())
