"""Failing repro tests for WISHENKA-121 (Step 3, red before Step 4)."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import sqlite3
import time
import urllib.parse
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncConnection

import wishenka.users as users_pkg
from wishenka.auth.models import TelegramUser
from wishenka.config import Settings
from wishenka.users.store import UserStore, UserStoreBusyError
from wishenka.web.app import create_app
from wishenka.wishlists.store import WishlistStore

pytestmark = pytest.mark.timeout(60)


def _db_url(db_path: Path) -> str:
    return f"sqlite+aiosqlite:///{db_path}"


@pytest.mark.parametrize("operation", ["upsert_user", "set_locale"])
async def test_user_write_serializes_with_concurrent_wishlist_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    """UserStore writes must use BEGIN IMMEDIATE so concurrent WishlistStore commits serialize."""
    db_path = tmp_path / "shared.sqlite"
    url = _db_url(db_path)
    wishlist_store = WishlistStore(url)
    user_store = UserStore(url)

    try:
        await wishlist_store.initialize()
        await user_store.initialize()
        # Warm up WishlistStore's connection pool so the concurrent write starts immediately.
        await wishlist_store.execute_read(lambda conn: conn.execute(text("SELECT 1")))

        if operation == "set_locale":
            await user_store.upsert_user(
                TelegramUser(id=1001, first_name="Alice", language_code="en")
            )

        select_done = asyncio.Event()
        allow_write = asyncio.Event()
        hooked = False
        orig_execute = AsyncConnection.execute

        async def paused_execute(
            self_conn: AsyncConnection,
            statement: Any,
            *args: Any,
            **kwargs: Any,
        ) -> Any:
            nonlocal hooked
            result = await orig_execute(self_conn, statement, *args, **kwargs)
            sql_text = str(statement)
            if (
                not hooked
                and self_conn.engine is user_store.engine
                and "SELECT" in sql_text
                and "FROM users" in sql_text
            ):
                hooked = True
                select_done.set()
                await asyncio.wait_for(allow_write.wait(), timeout=5.0)
            return result

        monkeypatch.setattr(AsyncConnection, "execute", paused_execute)

        if operation == "upsert_user":
            user_task = asyncio.create_task(
                user_store.upsert_user(
                    TelegramUser(id=1001, first_name="Alice", language_code="ru")
                )
            )
        else:
            user_task = asyncio.create_task(user_store.set_locale(1001, "ru"))

        await asyncio.wait_for(select_done.wait(), timeout=5.0)

        async def wishlist_write(conn: AsyncConnection) -> int:
            row = (
                await conn.execute(
                    text(
                        "INSERT OR REPLACE INTO wl_counters (name, value) "
                        "VALUES ('repro', 1) RETURNING value"
                    )
                )
            ).one()
            return int(row[0])

        wishlist_committed = asyncio.Event()

        async def run_wishlist_write() -> int:
            wid = await wishlist_store.transaction(wishlist_write)
            wishlist_committed.set()
            return wid

        wishlist_task = asyncio.create_task(run_wishlist_write())
        await asyncio.sleep(0.25)
        try:
            assert not wishlist_committed.is_set(), (
                "WishlistStore committed while UserStore was mid-transaction; "
                "UserStore did not acquire BEGIN IMMEDIATE"
            )
        finally:
            allow_write.set()

        record, wishlist_id = await asyncio.wait_for(
            asyncio.gather(user_task, wishlist_task),
            timeout=15.0,
        )
        assert record.telegram_id == 1001
        assert record.locale == "ru"
        assert wishlist_id > 0

        persisted = await user_store.get_by_telegram_id(1001)
        assert persisted is not None
        assert persisted.locale == "ru"
    finally:
        await user_store.dispose()
        await wishlist_store.dispose()


@pytest.mark.parametrize(
    "operation",
    ["upsert_user", "set_locale", "set_birthdate", "clear_birthdate"],
)
async def test_user_write_busy_lock_maps_to_user_store_busy_error(
    tmp_path: Path,
    operation: str,
) -> None:
    """Timed-out write locks must roll back cleanly and raise UserStoreBusyError."""
    busy_error_cls = getattr(users_pkg, "UserStoreBusyError", None)
    assert busy_error_cls is not None, "wishenka.users.UserStoreBusyError is not defined"

    db_path = tmp_path / "shared.sqlite"
    url = _db_url(db_path)
    user_store = UserStore(url)
    ext_conn: sqlite3.Connection | None = None

    try:
        await user_store.initialize()
        await user_store.upsert_user(TelegramUser(id=2002, first_name="Bob", language_code="en"))
        await user_store.set_locale(2002, "en")
        await user_store.set_birthdate(2002, day=15, month=6, year=1992)

        ext_conn = sqlite3.connect(db_path, isolation_level=None)
        ext_conn.execute("BEGIN IMMEDIATE")

        with pytest.raises(busy_error_cls):
            if operation == "upsert_user":
                await user_store.upsert_user(
                    TelegramUser(id=2002, first_name="Bobby", language_code="ru")
                )
            elif operation == "set_locale":
                await user_store.set_locale(2002, "ru")
            elif operation == "set_birthdate":
                await user_store.set_birthdate(2002, day=1, month=1, year=2000)
            else:
                await user_store.clear_birthdate(2002)

        ext_conn.rollback()
        ext_conn.close()
        ext_conn = None

        persisted = await user_store.get_by_telegram_id(2002)
        assert persisted is not None
        assert persisted.first_name == "Bob"
        assert persisted.locale == "en"
        assert persisted.birth_day == 15
        assert persisted.birth_month == 6
        assert persisted.birth_year == 1992
    finally:
        if ext_conn is not None:
            ext_conn.rollback()
            ext_conn.close()
        await user_store.dispose()


async def test_user_read_lookups_do_not_block_on_external_write_lock(tmp_path: Path) -> None:
    """Read-only UserStore lookups must succeed immediately while a write lock is held."""
    db_path = tmp_path / "shared.sqlite"
    url = _db_url(db_path)
    user_store = UserStore(url)
    ext_conn: sqlite3.Connection | None = None

    try:
        await user_store.initialize()
        seeded = await user_store.upsert_user(
            TelegramUser(id=3003, first_name="Carol", language_code="en")
        )

        ext_conn = sqlite3.connect(db_path, isolation_level=None)
        ext_conn.execute("BEGIN IMMEDIATE")

        by_tg = await asyncio.wait_for(user_store.get_by_telegram_id(3003), timeout=1.0)
        by_id = await asyncio.wait_for(user_store.get_by_id(seeded.id), timeout=1.0)

        assert by_tg is not None
        assert by_tg.id == seeded.id
        assert by_id is not None
        assert by_id.telegram_id == 3003
    finally:
        if ext_conn is not None:
            ext_conn.rollback()
            ext_conn.close()
        await user_store.dispose()


def _signed_init_data(bot_token: str, user_data: dict[str, Any]) -> str:
    params: dict[str, str] = {
        "auth_date": str(int(time.time())),
        "user": json.dumps(user_data, separators=(",", ":")),
    }
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    params["hash"] = hmac.new(
        secret_key, data_check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return urllib.parse.urlencode(params)


def test_user_store_busy_maps_to_http_503(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """UserStoreBusyError on auth/profile write routes must return HTTP 503."""
    bot_token = "123456789:ABCdefGHIjklMNOpqrsTUVwxyz1234567"
    settings = Settings(
        bot_token=bot_token,
        database_url=_db_url(tmp_path / "web.sqlite"),
        secret_key="test-secret-key",
        receipt_notice_worker_enabled=False,
        background_cleanup_enabled=False,
    )
    app = create_app(settings)
    init_data = _signed_init_data(
        bot_token,
        {"id": 4004, "first_name": "Dana", "language_code": "en"},
    )

    with TestClient(app) as client:
        origin_headers = {"Origin": "http://testserver"}
        auth_ok = client.post(
            "/api/auth/telegram",
            json={"init_data": init_data},
            headers=origin_headers,
        )
        assert auth_ok.status_code == 200
        token = auth_ok.json()["token"]
        headers = {"Authorization": f"Bearer {token}", "Origin": "http://testserver"}

        async def raise_busy(*_args: Any, **_kwargs: Any) -> Any:
            raise UserStoreBusyError("User service is temporarily busy; please retry")

        monkeypatch.setattr(UserStore, "upsert_user", raise_busy)
        auth_busy = client.post(
            "/api/auth/telegram",
            json={"init_data": init_data},
            headers=origin_headers,
        )
        assert auth_busy.status_code == 503

        monkeypatch.setattr(UserStore, "set_locale", raise_busy)
        locale_busy = client.patch(
            "/api/profile/locale",
            json={"locale": "ru"},
            headers=headers,
        )
        assert locale_busy.status_code == 503

        monkeypatch.setattr(UserStore, "set_birthdate", raise_busy)
        birthdate_busy = client.patch(
            "/api/profile/birthdate",
            json={"day": 10, "month": 5, "year": 1995},
            headers=headers,
        )
        assert birthdate_busy.status_code == 503


async def test_user_store_observability_logs_busy_and_error_without_pii(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """UserStore logs user_store_busy and user_store_error without PII or driver text."""
    db_path = tmp_path / "obs.sqlite"
    user_store = UserStore(_db_url(db_path))
    ext_conn: sqlite3.Connection | None = None

    try:
        await user_store.initialize()
        ext_conn = sqlite3.connect(db_path, isolation_level=None)
        ext_conn.execute("BEGIN IMMEDIATE")

        with (
            caplog.at_level(logging.WARNING, logger="wishenka.users"),
            pytest.raises(UserStoreBusyError),
        ):
            await user_store.upsert_user(
                TelegramUser(id=5005, first_name="SecretFirst", username="secretuser")
            )

        busy_records = [
            rec for rec in caplog.records if getattr(rec, "event", None) == "user_store_busy"
        ]
        assert len(busy_records) == 1
        assert getattr(busy_records[0], "operation", None) == "upsert_user"
        assert "SecretFirst" not in busy_records[0].getMessage()
        assert "secretuser" not in busy_records[0].getMessage()
        assert "5005" not in busy_records[0].getMessage()

        ext_conn.rollback()
        ext_conn.close()
        ext_conn = None

        async def raise_db_error(*_args: Any, **_kwargs: Any) -> Any:
            raise OperationalError("SELECT 1", {}, Exception("disk I/O error"))

        monkeypatch.setattr(AsyncConnection, "execute", raise_db_error)
        caplog.clear()
        with (
            caplog.at_level(logging.ERROR, logger="wishenka.users"),
            pytest.raises(RuntimeError, match="User storage operation failed"),
        ):
            await user_store.set_locale(5005, "ru")

        error_records = [
            rec for rec in caplog.records if getattr(rec, "event", None) == "user_store_error"
        ]
        assert len(error_records) == 1
        assert getattr(error_records[0], "operation", None) == "set_locale"
        assert "disk I/O error" not in error_records[0].getMessage()

        caplog.clear()
        monkeypatch.setattr(AsyncConnection, "exec_driver_sql", raise_db_error)
        with (
            caplog.at_level(logging.ERROR, logger="wishenka.users"),
            pytest.raises(RuntimeError, match="User storage operation failed"),
        ):
            await user_store.initialize()

        init_error_records = [
            rec for rec in caplog.records if getattr(rec, "event", None) == "user_store_error"
        ]
        assert len(init_error_records) == 1
        assert getattr(init_error_records[0], "operation", None) == "initialize"
    finally:
        if ext_conn is not None:
            ext_conn.rollback()
            ext_conn.close()
        await user_store.dispose()


def test_http_503_routes_log_structured_busy_events_without_pii(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Auth and profile 503 handlers log structured busy events with status_code=503."""
    bot_token = "123456789:ABCdefGHIjklMNOpqrsTUVwxyz1234567"
    settings = Settings(
        bot_token=bot_token,
        database_url=_db_url(tmp_path / "web_obs.sqlite"),
        secret_key="test-secret-key",
        receipt_notice_worker_enabled=False,
        background_cleanup_enabled=False,
    )
    app = create_app(settings)
    init_data = _signed_init_data(
        bot_token,
        {"id": 6006, "first_name": "HiddenName", "username": "hiddenhandle", "language_code": "en"},
    )

    with TestClient(app) as client:
        origin_headers = {"Origin": "http://testserver"}
        auth_ok = client.post(
            "/api/auth/telegram",
            json={"init_data": init_data},
            headers=origin_headers,
        )
        assert auth_ok.status_code == 200
        token = auth_ok.json()["token"]
        headers = {"Authorization": f"Bearer {token}", "Origin": "http://testserver"}

        async def raise_busy(*_args: Any, **_kwargs: Any) -> Any:
            raise UserStoreBusyError("User service is temporarily busy; please retry")

        caplog.clear()
        monkeypatch.setattr(UserStore, "upsert_user", raise_busy)
        with caplog.at_level(logging.WARNING, logger="wishenka.auth"):
            res_auth = client.post(
                "/api/auth/telegram",
                json={"init_data": init_data},
                headers=origin_headers,
            )
        assert res_auth.status_code == 503
        auth_events = [
            r for r in caplog.records if getattr(r, "event", None) == "auth_user_store_busy"
        ]
        assert len(auth_events) == 1
        assert getattr(auth_events[0], "status_code", None) == 503
        assert "HiddenName" not in auth_events[0].getMessage()
        assert token not in auth_events[0].getMessage()

        caplog.clear()
        monkeypatch.setattr(UserStore, "set_locale", raise_busy)
        with caplog.at_level(logging.WARNING, logger="wishenka.web.profile"):
            res_locale = client.patch(
                "/api/profile/locale",
                json={"locale": "ru"},
                headers=headers,
            )
        assert res_locale.status_code == 503
        locale_events = [
            r for r in caplog.records if getattr(r, "event", None) == "locale_user_store_busy"
        ]
        assert len(locale_events) == 1
        assert getattr(locale_events[0], "status_code", None) == 503

        caplog.clear()
        monkeypatch.setattr(UserStore, "set_birthdate", raise_busy)
        with caplog.at_level(logging.WARNING, logger="wishenka.web.profile"):
            res_bday = client.patch(
                "/api/profile/birthdate",
                json={"day": 10, "month": 5, "year": 1995},
                headers=headers,
            )
        assert res_bday.status_code == 503
        bday_events = [
            r for r in caplog.records if getattr(r, "event", None) == "birthdate_user_store_busy"
        ]
        assert len(bday_events) == 1
        assert getattr(bday_events[0], "status_code", None) == 503
