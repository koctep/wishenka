"""Failing repro for WISHENKA-326 shared-repository lock mapping.

A busy ``SQLAlchemyError`` on ``get_wishlist_repository``, including one
raised from ``conn.begin()``, must surface ``InventoryBusyError``.
``wishlists.execute`` must let that busy error reach the dependency. Any
other ``SQLAlchemyError`` stays ``RuntimeError`` (``Wishlist storage
operation failed``).
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection
from starlette.requests import Request

from wishenka.sqlite import is_sqlite_busy
from wishenka.web.dependencies import get_wishlist_repository
from wishenka.web.routes.wishlists import execute
from wishenka.wishlists.exceptions import InventoryBusyError
from wishenka.wishlists.repository import WishlistRepository
from wishenka.wishlists.store import WishlistStore

pytestmark = pytest.mark.timeout(30)

_DEP_LOGGER = "wishenka.web.dependencies"
_ROUTE_LOGGER = "wishenka.web.wishlists"
_BUSY_MESSAGE = "The wish was busy and the attempt changed nothing"
_BUSY_LOG = "Wishlist inventory change rolled back because the database was busy"
_GENERIC_FAILURE = "Wishlist storage operation failed"
_DEFERRED_EVENT = "wishenka_326_deferred_probe"
_PROBE_COUNTER = "wishenka_326_busy_probe"


@dataclass
class _Trace:
    """Commit, rollback, and deferred-log calls during one repository use."""

    commits: int = 0
    rollbacks: int = 0
    flushes: int = 0
    clears: int = 0
    cleared_pending: int = 0


def _operational(driver_message: str) -> OperationalError:
    return OperationalError("SELECT 1", {}, sqlite3.OperationalError(driver_message))


def _busy_error() -> OperationalError:
    return _operational("database is locked")


def _plain_error() -> OperationalError:
    return _operational("no such table: wishenka_326_missing")


def _route_request() -> Request:
    """Request whose endpoint name is a wishlist mutation."""

    async def update_wishlist() -> None:
        return None

    scope: dict[str, Any] = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/wishlists/1",
        "raw_path": b"/api/wishlists/1",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 123),
        "server": ("test", 80),
    }
    request = Request(scope)
    request.scope["endpoint"] = update_wishlist
    return request


def _install_trace(monkeypatch: pytest.MonkeyPatch) -> _Trace:
    trace = _Trace()
    original_commit = AsyncConnection.commit
    original_rollback = AsyncConnection.rollback
    original_flush = WishlistRepository.flush_commit_logs
    original_clear = WishlistRepository.clear_commit_logs

    async def commit(self: AsyncConnection) -> None:
        trace.commits += 1
        await original_commit(self)

    async def rollback(self: AsyncConnection) -> None:
        trace.rollbacks += 1
        await original_rollback(self)

    def flush(self: WishlistRepository) -> None:
        trace.flushes += 1
        original_flush(self)

    def clear(self: WishlistRepository) -> None:
        trace.clears += 1
        trace.cleared_pending += len(self._pending_commit_logs)
        original_clear(self)

    monkeypatch.setattr(AsyncConnection, "commit", commit)
    monkeypatch.setattr(AsyncConnection, "rollback", rollback)
    monkeypatch.setattr(WishlistRepository, "flush_commit_logs", flush)
    monkeypatch.setattr(WishlistRepository, "clear_commit_logs", clear)
    return trace


async def _open_store(tmp_path: Path) -> WishlistStore:
    store = WishlistStore(f"sqlite+aiosqlite:///{tmp_path / 'wishenka_326.db'}")
    await store.initialize()
    return store


async def _probe_value(store: WishlistStore) -> int | None:
    async with store.engine.connect() as conn:
        value = await conn.scalar(
            text("SELECT value FROM wl_counters WHERE name = :name"),
            {"name": _PROBE_COUNTER},
        )
    if value is None:
        return None
    return int(value)


async def _raise_during_request(
    store: WishlistStore,
    error: SQLAlchemyError,
    *,
    through_execute: bool,
) -> BaseException:
    """Use the shared repository and raise ``error`` from that request."""
    try:
        async with asynccontextmanager(get_wishlist_repository)(store) as repo:
            await repo.conn.execute(
                text("INSERT INTO wl_counters (name, value) VALUES (:name, :value)"),
                {"name": _PROBE_COUNTER, "value": 326},
            )
            repo.defer_commit_log(
                logging.INFO,
                "deferred probe must not flush",
                extra={"event": _DEFERRED_EVENT},
            )
            if through_execute:

                async def action(_ops: Any) -> None:
                    raise error

                await execute(_route_request(), action, repo=repo)
            else:
                raise error
    except BaseException as exc:
        return exc
    raise AssertionError("shared repository returned without an error")


async def _raise_from_begin(
    store: WishlistStore,
    error: SQLAlchemyError,
    monkeypatch: pytest.MonkeyPatch,
) -> BaseException:
    """Enter the shared repository while ``conn.begin()`` raises ``error``."""

    def begin(_conn: AsyncConnection) -> None:
        raise error

    monkeypatch.setattr(AsyncConnection, "begin", begin)
    try:
        async with asynccontextmanager(get_wishlist_repository)(store):
            raise AssertionError("repository yielded after begin failed")
    except BaseException as exc:
        return exc
    raise AssertionError("shared repository returned without an error")


def _require_inventory_busy(caught: BaseException, *, path: str) -> InventoryBusyError:
    if isinstance(caught, InventoryBusyError):
        assert str(caught) == _BUSY_MESSAGE
        return caught
    actual = f"{type(caught).__name__}: {caught}"
    raise AssertionError(f"{path}: expected InventoryBusyError ({_BUSY_MESSAGE}), got {actual}")


def _assert_busy_outcome(
    caught: BaseException,
    error: OperationalError,
    trace: _Trace,
    caplog: pytest.LogCaptureFixture,
    *,
    path: str,
) -> None:
    busy = _require_inventory_busy(caught, path=path)
    assert busy.__cause__ is error
    records = [
        rec
        for rec in caplog.records
        if rec.name == _DEP_LOGGER and getattr(rec, "event", None) == "wishlist_inventory_busy"
    ]
    assert len(records) == 1
    record = records[0]
    assert record.levelno == logging.WARNING
    assert record.getMessage() == _BUSY_LOG
    assert getattr(record, "error_type", None) is None
    assert record.exc_info is None
    assert "database is locked" not in record.getMessage()
    assert not any(getattr(rec, "event", None) == "wishlist_store_error" for rec in caplog.records)
    assert not any(getattr(rec, "event", None) == _DEFERRED_EVENT for rec in caplog.records)
    assert trace.flushes == 0
    assert trace.cleared_pending == 1
    assert trace.commits == 0
    assert trace.rollbacks >= 1


async def test_shared_repository_busy_error_surfaces_inventory_busy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """get_wishlist_repository maps a busy SQLAlchemyError to InventoryBusyError."""
    error = _busy_error()
    assert is_sqlite_busy(error)
    store = await _open_store(tmp_path)
    trace = _install_trace(monkeypatch)
    try:
        caplog.clear()
        with caplog.at_level(logging.WARNING, logger=_DEP_LOGGER):
            caught = await _raise_during_request(store, error, through_execute=False)
        _assert_busy_outcome(
            caught,
            error,
            trace,
            caplog,
            path="get_wishlist_repository",
        )
        assert await _probe_value(store) is None
    finally:
        await store.dispose()


async def test_wishlist_execute_busy_error_surfaces_inventory_busy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A wishlist execute request lets the dependency map the busy error."""
    error = _busy_error()
    assert is_sqlite_busy(error)
    store = await _open_store(tmp_path)
    trace = _install_trace(monkeypatch)
    try:
        caplog.clear()
        with (
            caplog.at_level(logging.WARNING, logger=_DEP_LOGGER),
            caplog.at_level(logging.WARNING, logger=_ROUTE_LOGGER),
        ):
            caught = await _raise_during_request(store, error, through_execute=True)
        _assert_busy_outcome(
            caught,
            error,
            trace,
            caplog,
            path="wishlists.execute",
        )
        route_store_errors = [
            rec
            for rec in caplog.records
            if rec.name == _ROUTE_LOGGER and getattr(rec, "event", None) == "wishlist_store_error"
        ]
        assert route_store_errors == []
        assert await _probe_value(store) is None
    finally:
        await store.dispose()


async def test_shared_repository_non_busy_error_stays_storage_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A non-busy SQLAlchemyError stays the generic storage failure."""
    error = _plain_error()
    assert is_sqlite_busy(error) is False
    store = await _open_store(tmp_path)
    trace = _install_trace(monkeypatch)
    try:
        caplog.clear()
        with caplog.at_level(logging.ERROR, logger=_DEP_LOGGER):
            caught = await _raise_during_request(store, error, through_execute=False)
        assert type(caught) is RuntimeError
        assert str(caught) == _GENERIC_FAILURE
        assert caught.__cause__ is None
        errors = [
            rec
            for rec in caplog.records
            if rec.name == _DEP_LOGGER and getattr(rec, "event", None) == "wishlist_store_error"
        ]
        assert len(errors) == 1
        assert errors[0].levelno == logging.ERROR
        assert getattr(errors[0], "error_type", None) == "OperationalError"
        assert not any(
            getattr(rec, "event", None) == "wishlist_inventory_busy" for rec in caplog.records
        )
        assert trace.flushes == 0
        assert trace.cleared_pending == 1
        assert trace.commits == 0
        assert trace.rollbacks >= 1
        assert await _probe_value(store) is None
    finally:
        await store.dispose()


async def test_shared_repository_begin_busy_error_surfaces_inventory_busy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A busy SQLAlchemyError from conn.begin() becomes InventoryBusyError."""
    error = _busy_error()
    assert is_sqlite_busy(error)
    store = await _open_store(tmp_path)
    trace = _install_trace(monkeypatch)
    try:
        caplog.clear()
        with caplog.at_level(logging.WARNING, logger=_DEP_LOGGER):
            caught = await _raise_from_begin(store, error, monkeypatch)
        busy = _require_inventory_busy(caught, path="conn.begin")
        assert busy.__cause__ is error
        records = [
            rec
            for rec in caplog.records
            if rec.name == _DEP_LOGGER and getattr(rec, "event", None) == "wishlist_inventory_busy"
        ]
        assert len(records) == 1
        record = records[0]
        assert record.levelno == logging.WARNING
        assert record.getMessage() == _BUSY_LOG
        assert getattr(record, "error_type", None) is None
        assert record.exc_info is None
        assert "database is locked" not in record.getMessage()
        assert not any(
            getattr(rec, "event", None) == "wishlist_store_error" for rec in caplog.records
        )
        assert trace.flushes == 0
        assert trace.clears == 0
        assert trace.commits == 0
        assert trace.rollbacks == 0
        assert await _probe_value(store) is None
    finally:
        await store.dispose()


async def test_shared_repository_begin_non_busy_error_stays_storage_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A non-busy SQLAlchemyError from conn.begin() stays the storage failure."""
    error = _plain_error()
    assert is_sqlite_busy(error) is False
    store = await _open_store(tmp_path)
    trace = _install_trace(monkeypatch)
    try:
        caplog.clear()
        with caplog.at_level(logging.WARNING, logger=_DEP_LOGGER):
            caught = await _raise_from_begin(store, error, monkeypatch)
        assert type(caught) is RuntimeError
        assert str(caught) == _GENERIC_FAILURE
        assert caught.__cause__ is None
        errors = [
            rec
            for rec in caplog.records
            if rec.name == _DEP_LOGGER and getattr(rec, "event", None) == "wishlist_store_error"
        ]
        assert len(errors) == 1
        assert errors[0].levelno == logging.ERROR
        assert getattr(errors[0], "error_type", None) == "OperationalError"
        assert not any(
            getattr(rec, "event", None) == "wishlist_inventory_busy" for rec in caplog.records
        )
        assert trace.flushes == 0
        assert trace.clears == 0
        assert trace.commits == 0
        assert trace.rollbacks == 0
        assert await _probe_value(store) is None
    finally:
        await store.dispose()
