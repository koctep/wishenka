"""Failing reproduction tests for WISHENKA-254: WishlistStore.execute_read hardening."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from wishenka.auth.models import AuthenticatedUser
from wishenka.wishlists.exceptions import InventoryBusyError
from wishenka.wishlists.service import WishlistService
from wishenka.wishlists.store import WishlistStore

pytestmark = pytest.mark.timeout(30)


class _ReadProbeError(RuntimeError):
    """Sentinel exception for testing execute_read cleanup on user errors."""


@pytest.mark.asyncio
async def test_execute_read_rejects_write_with_readonly_error(tmp_path: Path) -> None:
    """execute_read must reject SQL writes immediately with OperationalError (readonly)."""
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'execute_read_readonly.db'}"
    store = WishlistStore(db_url)
    owner = AuthenticatedUser(telegram_id=101, first_name="ReadonlyOwner")
    try:
        await store.initialize()

        async def seed(service: WishlistService) -> int:
            wishlist = await service.create_wishlist(owner=owner, title="Original")
            return wishlist.id

        wishlist_id = await store.execute(seed)

        async def mutate_in_read(conn: Any) -> None:
            await conn.execute(
                text("UPDATE wl_lists SET title = :title WHERE id = :id"),
                {"title": "Mutated", "id": wishlist_id},
            )

        with pytest.raises(OperationalError, match="readonly"):
            await store.execute_read(mutate_in_read)

        async def read_title(conn: Any) -> str:
            row = (
                await conn.execute(
                    text("SELECT title FROM wl_lists WHERE id = :id"),
                    {"id": wishlist_id},
                )
            ).one()
            return str(row.title)

        assert await store.execute_read(read_title) == "Original"
    finally:
        await store.engine.dispose()


@pytest.mark.asyncio
async def test_execute_read_resets_query_only_before_pool_return(tmp_path: Path) -> None:
    """execute_read must reset PRAGMA query_only=0 before returning connection to pool."""
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'execute_read_pool_reset.db'}"
    store = WishlistStore(db_url)
    owner = AuthenticatedUser(telegram_id=102, first_name="PoolOwner")
    try:
        await store.initialize()

        async def seed(service: WishlistService) -> int:
            wishlist = await service.create_wishlist(owner=owner, title="Initial")
            return wishlist.id

        wishlist_id = await store.execute(seed)

        async def ok_read(conn: Any) -> str:
            row = (
                await conn.execute(
                    text("SELECT title FROM wl_lists WHERE id = :id"),
                    {"id": wishlist_id},
                )
            ).one()
            return str(row.title)

        assert await store.execute_read(ok_read) == "Initial"

        async def failing_write(conn: Any) -> None:
            await conn.execute(
                text("UPDATE wl_lists SET title = :title WHERE id = :id"),
                {"title": "Blocked", "id": wishlist_id},
            )

        with contextlib.suppress(OperationalError):
            await store.execute_read(failing_write)

        async def failing_user_error(conn: Any) -> None:
            await conn.execute(text("SELECT 1"))
            raise _ReadProbeError("boom")

        with pytest.raises(_ReadProbeError, match="boom"):
            await store.execute_read(failing_user_error)

        async def check_query_only(conn: Any) -> int:
            row = (await conn.execute(text("PRAGMA query_only"))).one()
            return int(row[0])

        assert await store.transaction(check_query_only) == 0

        async def update_title(service: WishlistService) -> str:
            updated = await service.update_wishlist_settings(
                wishlist_id=wishlist_id,
                actor=owner,
                title="UpdatedAfterReads",
            )
            return updated.title

        assert await store.execute(update_title) == "UpdatedAfterReads"
    finally:
        await store.engine.dispose()


@pytest.mark.asyncio
async def test_execute_read_maps_sqlite_busy_to_inventory_busy_error(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """execute_read must map SQLITE_BUSY OperationalError to InventoryBusyError and log warning."""
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'execute_read_busy.db'}"
    store = WishlistStore(db_url)
    try:
        await store.initialize()

        async def busy_read(conn: Any) -> None:
            await conn.execute(text("SELECT 1"))
            raise OperationalError(
                "SELECT 1",
                {},
                sqlite3.OperationalError("database is locked"),
            )

        caplog.clear()
        with (
            caplog.at_level(logging.WARNING, logger="wishenka.wishlists.store"),
            pytest.raises(InventoryBusyError),
        ):
            await store.execute_read(busy_read)

        busy_logs = [
            rec
            for rec in caplog.records
            if rec.name == "wishenka.wishlists.store"
            and getattr(rec, "event", None) == "wishlist_read_busy"
        ]
        assert len(busy_logs) == 1
        assert busy_logs[0].levelno == logging.WARNING
    finally:
        await store.engine.dispose()


@pytest.mark.asyncio
async def test_execute_read_logs_warning_and_invalidates_on_query_only_reset_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """execute_read must log a warning and invalidate the connection if query_only reset fails."""
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'execute_read_reset_fail.db'}"
    store = WishlistStore(db_url)
    try:
        await store.initialize()
        invalidated = False
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
                nonlocal invalidated
                invalidated = True
                await self._inner.invalidate()

        def fake_connect(engine_self: Any) -> Any:
            conn_cm = orig_connect(engine_self)
            if engine_self is store.engine:
                return _WrappedRawConn(conn_cm)
            return conn_cm

        monkeypatch.setattr(type(store.engine), "connect", fake_connect)

        async def ok_read(conn: Any) -> int:
            row = (await conn.execute(text("SELECT 1"))).one()
            return int(row[0])

        caplog.clear()
        with (
            caplog.at_level(logging.WARNING, logger="wishenka.wishlists.store"),
            pytest.raises(RuntimeError, match="autocommit reset failed"),
        ):
            await store.execute_read(ok_read)

        assert invalidated is True
        reset_logs = [
            rec
            for rec in caplog.records
            if rec.name == "wishenka.wishlists.store"
            and getattr(rec, "event", None) == "wishlist_read_query_only_reset_failed"
        ]
        assert len(reset_logs) == 1
        assert reset_logs[0].levelno == logging.WARNING
        assert getattr(reset_logs[0], "error_type", None) == "RuntimeError"
    finally:
        await store.engine.dispose()


@pytest.mark.asyncio
async def test_execute_read_preserves_non_blocking_wal_reads(tmp_path: Path) -> None:
    """execute_read must complete without waiting on an active BEGIN IMMEDIATE writer."""
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'execute_read_wal.db'}"
    writer = WishlistStore(db_url)
    reader = WishlistStore(db_url)
    owner = AuthenticatedUser(telegram_id=103, first_name="WalReader")
    write_locked = asyncio.Event()
    release_write = asyncio.Event()
    writer_task: asyncio.Task[None] | None = None
    try:
        await writer.initialize()

        async def seed(service: WishlistService) -> int:
            wishlist = await service.create_wishlist(owner=owner, title="Before")
            return wishlist.id

        wishlist_id = await writer.execute(seed)

        async def hold_write(conn: Any) -> None:
            await conn.execute(
                text("UPDATE wl_lists SET title = :title WHERE id = :id"),
                {"title": "During", "id": wishlist_id},
            )
            write_locked.set()
            await asyncio.wait_for(release_write.wait(), timeout=5.0)

        async def read_title(conn: Any) -> str:
            row = (
                await conn.execute(
                    text("SELECT title FROM wl_lists WHERE id = :id"),
                    {"id": wishlist_id},
                )
            ).one()
            return str(row.title)

        writer_task = asyncio.create_task(writer.transaction(hold_write))
        await asyncio.wait_for(write_locked.wait(), timeout=2.0)

        observed_during_write = await asyncio.wait_for(reader.execute_read(read_title), timeout=2.0)
        assert observed_during_write == "Before"

        release_write.set()
        await asyncio.wait_for(writer_task, timeout=5.0)

        observed_after_commit = await asyncio.wait_for(reader.execute_read(read_title), timeout=2.0)
        assert observed_after_commit == "During"
    finally:
        if writer_task is not None and not writer_task.done():
            release_write.set()
            writer_task.cancel()
            await asyncio.gather(writer_task, return_exceptions=True)
        await reader.engine.dispose()
        await writer.engine.dispose()
