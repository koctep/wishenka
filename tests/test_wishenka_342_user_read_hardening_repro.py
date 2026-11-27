"""Failing reproduction tests for WISHENKA-342: UserStore._read hardening.

Current ``_read`` does not set ``PRAGMA query_only`` or reset it through
``AUTOCOMMIT``, and a busy lookup stays an ordinary storage failure.
"""

from __future__ import annotations

import inspect
import logging
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncConnection

from wishenka.auth.models import TelegramUser
from wishenka.users.store import UserStore, UserStoreBusyError

pytestmark = pytest.mark.timeout(30)

_BUSY_MESSAGE = "User service is temporarily busy; please retry"
_BUSY_LOG = "User store operation rolled back because the database was busy"
_SEEDED_NAME = "Ada"
_QUERY_ONLY_SEQUENCE = (
    "query_only_on",
    "select_user",
    "autocommit",
    "query_only_off",
)


class _LookupProbeError(RuntimeError):
    """Sentinel raised from read work while the query_only reset also fails."""


def _db_url(db_path: Path) -> str:
    return f"sqlite+aiosqlite:///{db_path}"


async def _seed(store: UserStore, telegram_id: int) -> Any:
    return await store.upsert_user(
        TelegramUser(id=telegram_id, first_name=_SEEDED_NAME, language_code="en")
    )


async def _invoke_read(store: UserStore, work: Any, *, operation: str) -> Any:
    """Call ``_read``; pass ``operation`` once that keyword exists."""
    read = store._read
    if "operation" in inspect.signature(read).parameters:
        return await read(work, operation=operation)
    return await read(work)  # type: ignore[call-arg]


def _query_only_token(statement: str) -> str | None:
    upper = " ".join(str(statement).upper().split())
    if "QUERY_ONLY" not in upper:
        return None
    if upper.endswith(("= OFF", "=OFF", "= 0", "=0")):
        return "query_only_off"
    if upper.endswith(("= ON", "=ON", "= 1", "=1")):
        return "query_only_on"
    return None


def _is_user_select(statement: str) -> bool:
    upper = " ".join(str(statement).upper().split())
    return "SELECT" in upper and "FROM USERS" in upper


def _assert_query_only_sequence(events: list[str], lookup: str) -> None:
    assert tuple(events) == _QUERY_ONLY_SEQUENCE, (
        f"{lookup} must set PRAGMA query_only = ON and reset it OFF "
        f"through AUTOCOMMIT, saw {events}"
    )


def _install_reset_failure(
    monkeypatch: pytest.MonkeyPatch,
    store: UserStore,
) -> dict[str, bool]:
    """Raise when a lookup resets ``query_only`` through ``AUTOCOMMIT``."""
    state = {"invalidated": False}
    orig_connect = type(store.engine).connect

    class _WrappedRawConn:
        def __init__(self, inner: Any) -> None:
            self._inner = inner

        async def __aenter__(self) -> _WrappedRawConn:
            await self._inner.__aenter__()
            return self

        async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> Any:
            return await self._inner.__aexit__(exc_type, exc, tb)

        async def execution_options(self, **opt: Any) -> Any:
            if opt.get("isolation_level") == "AUTOCOMMIT":
                raise RuntimeError("autocommit reset failed")
            return await self._inner.execution_options(**opt)

        async def invalidate(self) -> None:
            state["invalidated"] = True
            await self._inner.invalidate()

    def fake_connect(engine_self: Any) -> Any:
        conn_cm = orig_connect(engine_self)
        if engine_self is store.engine:
            return _WrappedRawConn(conn_cm)
        return conn_cm

    monkeypatch.setattr(type(store.engine), "connect", fake_connect)
    return state


def _reset_warnings(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [
        rec
        for rec in caplog.records
        if rec.name == "wishenka.users"
        and getattr(rec, "event", None) == "user_store_query_only_reset_failed"
    ]


@pytest.mark.asyncio
async def test_person_lookups_set_query_only_and_reset_off_through_autocommit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both person lookups turn query_only on, then off in AUTOCOMMIT."""
    store = UserStore(_db_url(tmp_path / "query_only.sqlite"))
    events: list[str] = []
    original_options = AsyncConnection.execution_options

    def _on_execute(
        _conn: Any,
        _cursor: Any,
        statement: str,
        _parameters: Any,
        _context: Any,
        _executemany: bool,
    ) -> None:
        token = _query_only_token(statement)
        if token is not None:
            events.append(token)
        elif _is_user_select(statement):
            events.append("select_user")

    async def _spy_options(self: AsyncConnection, **opt: Any) -> Any:
        if opt.get("isolation_level") == "AUTOCOMMIT":
            events.append("autocommit")
        return await original_options(self, **opt)

    listening = False
    try:
        await store.initialize()
        seeded = await _seed(store, 34201)
        event.listen(store.engine.sync_engine, "before_cursor_execute", _on_execute)
        listening = True
        monkeypatch.setattr(AsyncConnection, "execution_options", _spy_options)

        by_telegram = await store.get_by_telegram_id(seeded.telegram_id)
        assert by_telegram is not None
        assert by_telegram.first_name == _SEEDED_NAME
        telegram_events = list(events)
        events.clear()

        by_id = await store.get_by_id(seeded.id)
        assert by_id is not None
        assert by_id.first_name == _SEEDED_NAME
        _assert_query_only_sequence(telegram_events, "get_by_telegram_id")
        _assert_query_only_sequence(events, "get_by_id")
    finally:
        if listening:
            event.remove(store.engine.sync_engine, "before_cursor_execute", _on_execute)
        await store.dispose()


@pytest.mark.asyncio
async def test_user_read_refuses_write_with_readonly_error(tmp_path: Path) -> None:
    """A write inside _read is refused at once; the seeded name stays."""
    store = UserStore(_db_url(tmp_path / "readonly.sqlite"))
    try:
        await store.initialize()
        seeded = await _seed(store, 34202)

        async def mutate(conn: AsyncConnection) -> None:
            await conn.execute(
                text("UPDATE users SET first_name = :name WHERE telegram_id = :telegram_id"),
                {"name": "Mutated", "telegram_id": seeded.telegram_id},
            )

        with pytest.raises(OperationalError, match="readonly"):
            await _invoke_read(store, mutate, operation="get_by_telegram_id")

        persisted = await store.get_by_telegram_id(seeded.telegram_id)
        assert persisted is not None
        assert persisted.first_name == _SEEDED_NAME
    finally:
        await store.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "lookup",
    ["get_by_telegram_id", "get_by_id"],
)
async def test_busy_person_lookup_raises_user_store_busy_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    lookup: str,
) -> None:
    """A locked person lookup uses the existing busy error and warning."""
    store = UserStore(_db_url(tmp_path / f"busy_{lookup}.sqlite"))
    original_execute = AsyncConnection.execute

    async def locked_execute(
        self: AsyncConnection,
        statement: Any,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        if _is_user_select(str(statement)):
            raise OperationalError(
                "SELECT 1",
                {},
                sqlite3.OperationalError("database is locked"),
            )
        return await original_execute(self, statement, *args, **kwargs)

    try:
        await store.initialize()
        seeded = await _seed(store, 34203)
        monkeypatch.setattr(AsyncConnection, "execute", locked_execute)
        caplog.clear()
        with (
            caplog.at_level(logging.WARNING, logger="wishenka.users"),
            pytest.raises(UserStoreBusyError, match=_BUSY_MESSAGE),
        ):
            if lookup == "get_by_telegram_id":
                await store.get_by_telegram_id(seeded.telegram_id)
            else:
                await store.get_by_id(seeded.id)

        busy_logs = [
            rec
            for rec in caplog.records
            if rec.name == "wishenka.users" and getattr(rec, "event", None) == "user_store_busy"
        ]
        assert len(busy_logs) == 1
        assert busy_logs[0].levelno == logging.WARNING
        assert busy_logs[0].getMessage() == _BUSY_LOG
        assert getattr(busy_logs[0], "operation", None) == lookup
        error_logs = [
            rec for rec in caplog.records if getattr(rec, "event", None) == "user_store_error"
        ]
        assert error_logs == []
    finally:
        await store.dispose()


@pytest.mark.asyncio
async def test_user_read_invalidates_when_query_only_reset_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failed AUTOCOMMIT reset logs, invalidates, and is the raised error."""
    store = UserStore(_db_url(tmp_path / "reset_ok_read.sqlite"))
    try:
        await store.initialize()
        state = _install_reset_failure(monkeypatch, store)

        async def ok_read(conn: AsyncConnection) -> int:
            row = (await conn.execute(text("SELECT 1"))).one()
            return int(row[0])

        caplog.clear()
        with (
            caplog.at_level(logging.WARNING, logger="wishenka.users"),
            pytest.raises(RuntimeError, match="autocommit reset failed"),
        ):
            await _invoke_read(store, ok_read, operation="get_by_telegram_id")

        assert state["invalidated"] is True
        reset_logs = _reset_warnings(caplog)
        assert len(reset_logs) == 1
        assert reset_logs[0].levelno == logging.WARNING
        assert getattr(reset_logs[0], "error_type", None) == "RuntimeError"
    finally:
        await store.dispose()


@pytest.mark.asyncio
async def test_user_read_keeps_work_error_when_query_only_reset_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When work already failed, the reset still invalidates and work wins."""
    store = UserStore(_db_url(tmp_path / "reset_work_error.sqlite"))
    try:
        await store.initialize()
        state = _install_reset_failure(monkeypatch, store)

        async def failing_read(conn: AsyncConnection) -> None:
            await conn.execute(text("SELECT 1"))
            raise _LookupProbeError("lookup failed")

        caplog.clear()
        with (
            caplog.at_level(logging.WARNING, logger="wishenka.users"),
            pytest.raises(_LookupProbeError, match="lookup failed"),
        ):
            await _invoke_read(store, failing_read, operation="get_by_id")

        assert state["invalidated"] is True
        reset_logs = _reset_warnings(caplog)
        assert len(reset_logs) == 1
        assert getattr(reset_logs[0], "error_type", None) == "RuntimeError"
    finally:
        await store.dispose()


@pytest.mark.asyncio
async def test_successful_person_lookup_adds_no_log(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A successful person lookup adds no new log record."""
    store = UserStore(_db_url(tmp_path / "quiet.sqlite"))
    try:
        await store.initialize()
        seeded = await _seed(store, 34204)
        caplog.clear()
        with caplog.at_level(logging.DEBUG, logger="wishenka.users"):
            by_telegram = await store.get_by_telegram_id(seeded.telegram_id)
            by_id = await store.get_by_id(seeded.id)
        assert by_telegram is not None
        assert by_telegram.first_name == _SEEDED_NAME
        assert by_id is not None
        assert by_id.id == seeded.id
        new_logs = [rec for rec in caplog.records if rec.name == "wishenka.users"]
        assert new_logs == []
    finally:
        await store.dispose()


@pytest.mark.asyncio
async def test_user_read_non_busy_error_stays_operational(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A non-busy storage error stays that error and is not user_store_error."""
    store = UserStore(_db_url(tmp_path / "disk_io.sqlite"))
    try:
        await store.initialize()

        async def disk_read(_conn: AsyncConnection) -> None:
            raise OperationalError(
                "SELECT 1",
                {},
                sqlite3.OperationalError("disk I/O error"),
            )

        caplog.clear()
        with (
            caplog.at_level(logging.ERROR, logger="wishenka.users"),
            pytest.raises(OperationalError, match="disk I/O error"),
        ):
            await _invoke_read(store, disk_read, operation="get_by_telegram_id")

        error_logs = [
            rec for rec in caplog.records if getattr(rec, "event", None) == "user_store_error"
        ]
        assert error_logs == []
    finally:
        await store.dispose()
