"""Failing repro tests for WISHENKA-132: WishlistStore resource cleanup on initialize() failure.

Verifies that ``WishlistStore.initialize()`` disposes its SQLAlchemy engine and
cleans up owned temporary database files (for ``:memory:`` stores) when
``upgrade_to_head`` raises an exception, without deleting persistent file-backed
databases, and that a subsequent ``dispose()`` call remains idempotent.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from wishenka.wishlists import store as store_module
from wishenka.wishlists.migrations import migration_lock_path
from wishenka.wishlists.store import WishlistStore

pytestmark = pytest.mark.timeout(10)


def _spy_engine_dispose(store: WishlistStore, monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Wrap ``AsyncEngine.dispose`` to count calls for ``store.engine``."""
    calls: list[int] = []
    engine_cls = type(store.engine)
    original_dispose = engine_cls.dispose

    async def tracked_dispose(self_engine: Any, close: bool = True) -> None:
        if self_engine is store.engine:
            calls.append(1)
        await original_dispose(self_engine, close=close)

    monkeypatch.setattr(engine_cls, "dispose", tracked_dispose)
    return calls


async def test_memory_store_initialize_failure_disposes_and_removes_temp_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Failed initialize() on :memory: store must dispose engine and remove temp files."""
    store = WishlistStore("sqlite+aiosqlite:///:memory:")
    temp_path = store._temporary_database_path
    assert temp_path is not None
    assert temp_path.exists()
    lock_path = migration_lock_path(temp_path)
    dispose_calls = _spy_engine_dispose(store, monkeypatch)

    async def failing_upgrade_to_head(_database_url: str) -> None:
        lock_path.touch()
        raise RuntimeError("simulated migration failure")

    monkeypatch.setattr(store_module, "upgrade_to_head", failing_upgrade_to_head)

    try:
        with pytest.raises(RuntimeError, match="Unable to initialize wishlist storage"):
            await store.initialize()

        assert len(dispose_calls) == 1
        assert not temp_path.exists()
        assert not lock_path.exists()
        assert store._temporary_database_path is None
    finally:
        await store.dispose()


async def test_file_store_initialize_failure_disposes_and_keeps_persistent_db(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Failed initialize() on file-backed store must dispose engine but keep DB file."""
    db_path = tmp_path / "persistent.sqlite"
    db_path.touch()
    store = WishlistStore(f"sqlite+aiosqlite:///{db_path}")
    dispose_calls = _spy_engine_dispose(store, monkeypatch)

    async def failing_upgrade_to_head(_database_url: str) -> None:
        raise RuntimeError("simulated migration failure")

    monkeypatch.setattr(store_module, "upgrade_to_head", failing_upgrade_to_head)

    try:
        with pytest.raises(RuntimeError, match="Unable to initialize wishlist storage"):
            await store.initialize()

        assert len(dispose_calls) == 1
        assert db_path.exists()
        assert store._temporary_database_path is None
    finally:
        await store.dispose()


async def test_dispose_after_failed_initialize_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Calling dispose() after a failed initialize() must succeed without error."""
    store = WishlistStore("sqlite+aiosqlite:///:memory:")
    dispose_calls = _spy_engine_dispose(store, monkeypatch)

    async def failing_upgrade_to_head(_database_url: str) -> None:
        raise RuntimeError("simulated migration failure")

    monkeypatch.setattr(store_module, "upgrade_to_head", failing_upgrade_to_head)

    with pytest.raises(RuntimeError, match="Unable to initialize wishlist storage"):
        await store.initialize()

    assert len(dispose_calls) == 1
    await store.dispose()
    assert len(dispose_calls) == 2
    assert store._temporary_database_path is None


async def test_memory_store_initialize_unmapped_exception_still_disposes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unmapped exceptions during initialize() must still dispose resources and propagate."""

    class UnexpectedMigrationError(Exception):
        pass

    store = WishlistStore("sqlite+aiosqlite:///:memory:")
    temp_path = store._temporary_database_path
    assert temp_path is not None
    dispose_calls = _spy_engine_dispose(store, monkeypatch)

    async def failing_upgrade_to_head(_database_url: str) -> None:
        raise UnexpectedMigrationError("unexpected failure")

    monkeypatch.setattr(store_module, "upgrade_to_head", failing_upgrade_to_head)

    try:
        with pytest.raises(UnexpectedMigrationError, match="unexpected failure"):
            await store.initialize()

        assert len(dispose_calls) == 1
        assert not temp_path.exists()
        assert store._temporary_database_path is None
    finally:
        await store.dispose()


async def test_initialize_failure_logs_structured_cleanup_events(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Failed initialize() emits structured warning and debug temp-db removal logs."""
    store = WishlistStore("sqlite+aiosqlite:///:memory:")

    async def failing_upgrade_to_head(_database_url: str) -> None:
        raise RuntimeError("simulated migration failure")

    monkeypatch.setattr(store_module, "upgrade_to_head", failing_upgrade_to_head)

    with (
        caplog.at_level(logging.DEBUG, logger="wishenka.wishlists.store"),
        pytest.raises(RuntimeError, match="Unable to initialize wishlist storage"),
    ):
        await store.initialize()

    init_failed_records = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "wishlist_store_init_failed"
    ]
    assert len(init_failed_records) == 1
    assert init_failed_records[0].levelno == logging.WARNING
    assert getattr(init_failed_records[0], "error_type", None) == "RuntimeError"
    assert getattr(init_failed_records[0], "has_temporary_db", None) is True

    temp_removed_records = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "wishlist_store_temp_db_removed"
    ]
    assert len(temp_removed_records) == 1
    assert temp_removed_records[0].levelno == logging.DEBUG
