"""Observability and structured logging tests for user persistence and authentication."""

import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.test_auth_user_store import TEST_BOT_TOKEN, create_test_init_data
from wishenka.auth.models import TelegramUser
from wishenka.config import Settings
from wishenka.users.store import UserStore
from wishenka.web.app import create_app

pytestmark = pytest.mark.timeout(10)


def test_auth_telegram_emits_user_created_on_first_authentication(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """First authentication emits user_created structured log without sensitive data."""
    db_path = tmp_path / "obs_first_auth.db"
    settings = Settings(
        bot_token=TEST_BOT_TOKEN,
        database_url=f"sqlite+aiosqlite:///{db_path}",
    )
    user_payload = {
        "id": 1001001,
        "first_name": "Mikhail",
        "last_name": "Lermontov",
        "username": "lermontov",
        "language_code": "ru",
        "is_premium": False,
    }
    init_data = create_test_init_data(user_payload, bot_token=TEST_BOT_TOKEN)

    app = create_app(settings)
    with caplog.at_level(logging.DEBUG), TestClient(app) as client:
        resp = client.post(
            "/api/auth/telegram",
            json={"init_data": init_data},
            headers={"Origin": "http://testserver"},
        )
        assert resp.status_code == 200
        data = resp.json()
        user_id = data["user_id"]
        token = data["token"]

    # Verify user_created structured log event
    created_events = [
        rec for rec in caplog.records if getattr(rec, "event", None) == "user_created"
    ]
    assert len(created_events) == 1
    event_rec = created_events[0]
    assert event_rec.levelname == "INFO"
    assert getattr(event_rec, "user_id", None) == user_id
    assert getattr(event_rec, "telegram_id", None) == 1001001

    # Verify auth_success structured log event
    auth_success_events = [
        rec for rec in caplog.records if getattr(rec, "event", None) == "auth_success"
    ]
    assert len(auth_success_events) == 1
    auth_rec = auth_success_events[0]
    assert getattr(auth_rec, "user_id", None) == user_id
    assert getattr(auth_rec, "telegram_id", None) == 1001001

    # Security check: verify no secrets leaked in logs
    hmac_hash = dict(urllib_parse_qsl(init_data))["hash"]
    for rec in caplog.records:
        message = rec.getMessage()
        record_repr = str(rec.__dict__)
        assert token not in message
        assert token not in record_repr
        assert TEST_BOT_TOKEN not in message
        assert TEST_BOT_TOKEN not in record_repr
        assert hmac_hash not in message
        assert hmac_hash not in record_repr


def test_auth_telegram_emits_user_updated_on_profile_change(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Subsequent authentication with profile change emits user_updated log."""
    db_path = tmp_path / "obs_profile_update.db"
    settings = Settings(
        bot_token=TEST_BOT_TOKEN,
        database_url=f"sqlite+aiosqlite:///{db_path}",
    )
    initial_payload = {
        "id": 2002002,
        "first_name": "Nikolai",
        "last_name": "Gogol",
        "username": "gogol",
    }
    updated_payload = {
        "id": 2002002,
        "first_name": "Nikolay",
        "last_name": "Gogol-Yanovsky",
        "username": "nikolay_gogol",
    }

    app = create_app(settings)
    with TestClient(app) as client:
        # Initial login
        init_data_1 = create_test_init_data(initial_payload, bot_token=TEST_BOT_TOKEN)
        resp1 = client.post(
            "/api/auth/telegram",
            json={"init_data": init_data_1},
            headers={"Origin": "http://testserver"},
        )
        assert resp1.status_code == 200
        user_id_1 = resp1.json()["user_id"]

        # Capture logs during second login
        caplog.clear()
        with caplog.at_level(logging.DEBUG):
            init_data_2 = create_test_init_data(updated_payload, bot_token=TEST_BOT_TOKEN)
            resp2 = client.post(
                "/api/auth/telegram",
                json={"init_data": init_data_2},
                headers={"Origin": "http://testserver"},
            )
            assert resp2.status_code == 200
            token_2 = resp2.json()["token"]
            assert resp2.json()["user_id"] == user_id_1

    # Verify user_updated structured log event
    updated_events = [
        rec for rec in caplog.records if getattr(rec, "event", None) == "user_updated"
    ]
    assert len(updated_events) == 1
    event_rec = updated_events[0]
    assert event_rec.levelname == "INFO"
    assert getattr(event_rec, "user_id", None) == user_id_1
    assert getattr(event_rec, "telegram_id", None) == 2002002

    # Verify user_created was NOT emitted on second login
    created_events = [
        rec for rec in caplog.records if getattr(rec, "event", None) == "user_created"
    ]
    assert len(created_events) == 0

    # Security check: verify no secrets leaked in logs
    hmac_hash_2 = dict(urllib_parse_qsl(init_data_2))["hash"]
    for rec in caplog.records:
        message = rec.getMessage()
        record_repr = str(rec.__dict__)
        assert token_2 not in message
        assert token_2 not in record_repr
        assert TEST_BOT_TOKEN not in message
        assert TEST_BOT_TOKEN not in record_repr
        assert hmac_hash_2 not in message
        assert hmac_hash_2 not in record_repr


@pytest.mark.asyncio
async def test_user_store_direct_upsert_logging(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Direct UserStore upsert operations emit user_created and user_updated logs."""
    db_path = tmp_path / "obs_store_direct.db"
    store = UserStore(f"sqlite+aiosqlite:///{db_path}")
    await store.initialize()

    try:
        user_1 = TelegramUser(
            id=3003003,
            first_name="Ivan",
            last_name="Turgenev",
            username="turgenev",
        )
        with caplog.at_level(logging.DEBUG):
            record_1 = await store.upsert_user(user_1)

        created_events = [
            rec for rec in caplog.records if getattr(rec, "event", None) == "user_created"
        ]
        assert len(created_events) == 1
        assert getattr(created_events[0], "user_id", None) == record_1.id
        assert getattr(created_events[0], "telegram_id", None) == 3003003

        # Update profile
        caplog.clear()
        user_updated = TelegramUser(
            id=3003003,
            first_name="Ivan",
            last_name="Turgenev",
            username="ivan_turgenev",
            is_premium=True,
        )
        with caplog.at_level(logging.DEBUG):
            record_updated = await store.upsert_user(user_updated)

        assert record_updated.id == record_1.id
        updated_events = [
            rec for rec in caplog.records if getattr(rec, "event", None) == "user_updated"
        ]
        assert len(updated_events) == 1
        assert getattr(updated_events[0], "user_id", None) == record_1.id
        assert getattr(updated_events[0], "telegram_id", None) == 3003003
    finally:
        await store.dispose()


def test_failed_auth_does_not_log_sensitive_data(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Tampered initData validation failure does not leak secret token or hashes."""
    db_path = tmp_path / "obs_failed_auth.db"
    settings = Settings(
        bot_token=TEST_BOT_TOKEN,
        database_url=f"sqlite+aiosqlite:///{db_path}",
    )
    tampered_payload = {"id": 999999, "first_name": "Tampered"}
    tampered_init_data = create_test_init_data(
        tampered_payload, bot_token=TEST_BOT_TOKEN, tampered=True
    )

    app = create_app(settings)
    with caplog.at_level(logging.DEBUG), TestClient(app) as client:
        resp = client.post(
            "/api/auth/telegram",
            json={"init_data": tampered_init_data},
            headers={"Origin": "http://testserver"},
        )
        assert resp.status_code == 401

    # Verify auth_failure log exists
    failure_events = [
        rec for rec in caplog.records if getattr(rec, "event", None) == "auth_failure"
    ]
    assert len(failure_events) >= 1

    # Verify user_created was NOT emitted
    assert not any(getattr(r, "event", None) == "user_created" for r in caplog.records)

    # Verify no secrets leaked
    tampered_hash = dict(urllib_parse_qsl(tampered_init_data))["hash"]
    for rec in caplog.records:
        message = rec.getMessage()
        record_repr = str(rec.__dict__)
        assert TEST_BOT_TOKEN not in message
        assert TEST_BOT_TOKEN not in record_repr
        assert tampered_hash not in message
        assert tampered_hash not in record_repr


def urllib_parse_qsl(raw_query: str) -> list[tuple[str, str]]:
    """Helper to parse query string into key-value pairs."""
    import urllib.parse

    return urllib.parse.parse_qsl(raw_query, keep_blank_values=True)
