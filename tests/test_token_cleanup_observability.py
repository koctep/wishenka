"""Structured logging observability tests for token TTL and background cleanup."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text

from wishenka.config import Settings
from wishenka.logging import JsonFormatter
from wishenka.web.app import create_app
from wishenka.wishlists.cleanup import background_cleanup_worker, run_cleanup_cycle
from wishenka.wishlists.store import WishlistStore

pytestmark = pytest.mark.timeout(10)


@pytest.mark.asyncio
async def test_background_cleanup_completed_logging(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Verify background_cleanup_completed log event and its structured fields."""
    db_path = tmp_path / "obs_cleanup_completed.db"
    store = WishlistStore(f"sqlite+aiosqlite:///{db_path}")
    await store.initialize()

    now = datetime(2026, 11, 11, 12, 0, 0, tzinfo=UTC)
    expired_dt = (now - timedelta(hours=2)).isoformat()
    old_deleted_dt = (now - timedelta(days=45)).isoformat()
    now_iso = now.isoformat()

    try:
        async with store.engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO wl_lists (id, owner_id, title, status, public_token, "
                    "invite_token, invite_token_expires_at, created_at, updated_at) "
                    "VALUES (10, 1, 'Expired List', 'active', 'pub_10', 'tok_10', "
                    ":exp, :now, :now)"
                ),
                {"exp": expired_dt, "now": now_iso},
            )
            await conn.execute(text("INSERT INTO wl_invite_tokens (token) VALUES ('tok_10')"))
            await conn.execute(
                text(
                    "INSERT INTO wl_lists (id, owner_id, title, status, public_token, "
                    "invite_token, created_at, updated_at) "
                    "VALUES (20, 2, 'Old Deleted', 'deleted', 'pub_20', 'tok_20', "
                    ":old, :old)"
                ),
                {"old": old_deleted_dt},
            )

        settings = Settings(
            database_url=f"sqlite+aiosqlite:///{db_path}",
            wishlist_retention_days=30,
        )

        with caplog.at_level(logging.INFO, logger="wishenka.wishlists.cleanup"):
            stats = await run_cleanup_cycle(store, settings, now=now)

        assert stats.expired_tokens_cleaned == 1
        assert stats.wishlists_purged == 1

        records = [
            r for r in caplog.records if getattr(r, "event", None) == "background_cleanup_completed"
        ]
        assert len(records) == 1, "Expected exactly 1 background_cleanup_completed event"
        rec = records[0]
        assert rec.levelno == logging.INFO
        assert getattr(rec, "expired_tokens_cleaned", None) == 1
        assert getattr(rec, "wishlists_purged", None) == 1
        assert isinstance(getattr(rec, "duration_ms", None), float)
        assert getattr(rec, "duration_ms", -1.0) >= 0.0

        formatter = JsonFormatter()
        json_output = formatter.format(rec)
        parsed = json.loads(json_output)
        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "wishenka.wishlists.cleanup"
        assert parsed["extra"]["event"] == "background_cleanup_completed"
        assert parsed["extra"]["expired_tokens_cleaned"] == 1
        assert parsed["extra"]["wishlists_purged"] == 1
        assert "duration_ms" in parsed["extra"]
    finally:
        await store.engine.dispose()


@pytest.mark.asyncio
async def test_background_cleanup_failed_logging(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify background_cleanup_failed log event and error details when store fails."""
    mock_store = AsyncMock()
    mock_store.cleanup_expired_tokens.side_effect = RuntimeError("Disk I/O error")
    settings = Settings()

    with caplog.at_level(logging.ERROR, logger="wishenka.wishlists.cleanup"):
        stats = await run_cleanup_cycle(mock_store, settings)

    assert stats.expired_tokens_cleaned == 0
    assert stats.wishlists_purged == 0

    records = [
        r for r in caplog.records if getattr(r, "event", None) == "background_cleanup_failed"
    ]
    assert len(records) == 1, "Expected exactly 1 background_cleanup_failed event"
    rec = records[0]
    assert rec.levelno == logging.ERROR
    assert getattr(rec, "error", None) == "Disk I/O error"
    assert isinstance(getattr(rec, "duration_ms", None), float)
    assert rec.exc_info is not None

    formatter = JsonFormatter()
    json_output = formatter.format(rec)
    parsed = json.loads(json_output)
    assert parsed["level"] == "ERROR"
    assert parsed["logger"] == "wishenka.wishlists.cleanup"
    assert parsed["extra"]["event"] == "background_cleanup_failed"
    assert parsed["extra"]["error"] == "Disk I/O error"
    assert "exception" in parsed


@pytest.mark.asyncio
async def test_background_worker_started_and_stopped_logging(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Verify background_worker_started and background_worker_stopped log events."""
    db_path = tmp_path / "obs_worker_lifecycle.db"
    store = WishlistStore(f"sqlite+aiosqlite:///{db_path}")
    await store.initialize()

    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{db_path}",
        background_cleanup_interval_seconds=1800,
    )
    stop_event = asyncio.Event()
    stop_event.set()

    try:
        with caplog.at_level(logging.INFO, logger="wishenka.wishlists.cleanup"):
            await background_cleanup_worker(store, settings, stop_event=stop_event)

        start_records = [
            r for r in caplog.records if getattr(r, "event", None) == "background_worker_started"
        ]
        stop_records = [
            r for r in caplog.records if getattr(r, "event", None) == "background_worker_stopped"
        ]

        assert len(start_records) == 1, "Expected 1 background_worker_started event"
        assert len(stop_records) == 1, "Expected 1 background_worker_stopped event"

        start_rec = start_records[0]
        assert start_rec.levelno == logging.INFO
        assert getattr(start_rec, "interval_seconds", None) == 1800

        stop_rec = stop_records[0]
        assert stop_rec.levelno == logging.INFO

        formatter = JsonFormatter()
        start_json = json.loads(formatter.format(start_rec))
        assert start_json["extra"]["event"] == "background_worker_started"
        assert start_json["extra"]["interval_seconds"] == 1800

        stop_json = json.loads(formatter.format(stop_rec))
        assert stop_json["extra"]["event"] == "background_worker_stopped"
    finally:
        await store.engine.dispose()


@pytest.mark.asyncio
async def test_lifespan_worker_observability(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Verify worker start and stop structured logs during FastAPI application lifespan."""
    db_path = tmp_path / "obs_lifespan.db"
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{db_path}",
        background_cleanup_enabled=True,
        background_cleanup_interval_seconds=2400,
    )

    app = create_app(settings)
    with caplog.at_level(logging.INFO, logger="wishenka.wishlists.cleanup"):
        async with app.router.lifespan_context(app):
            # Allow event loop to run background task startup
            await asyncio.sleep(0.01)
            start_records = [
                r
                for r in caplog.records
                if getattr(r, "event", None) == "background_worker_started"
            ]
            assert len(start_records) == 1
            assert getattr(start_records[0], "interval_seconds", None) == 2400

    stop_records = [
        r for r in caplog.records if getattr(r, "event", None) == "background_worker_stopped"
    ]
    assert len(stop_records) == 1


@pytest.mark.asyncio
async def test_wishlist_repo_mutation_cleanup_expired_logging(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Verify wishlist_repo_mutation event with entity='invite_token'
    and operation='cleanup_expired'.
    """
    db_path = tmp_path / "obs_repo_cleanup.db"
    store = WishlistStore(f"sqlite+aiosqlite:///{db_path}")
    await store.initialize()

    now = datetime(2026, 11, 11, 12, 0, 0, tzinfo=UTC)
    expired_dt = (now - timedelta(minutes=5)).isoformat()
    now_iso = now.isoformat()

    try:
        async with store.engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO wl_lists (id, owner_id, title, status, public_token, "
                    "invite_token, invite_token_expires_at, created_at, updated_at) "
                    "VALUES (100, 1, 'Expired List', 'active', 'pub_100', 'inv_100', "
                    ":exp, :now, :now)"
                ),
                {"exp": expired_dt, "now": now_iso},
            )
            await conn.execute(text("INSERT INTO wl_invite_tokens (token) VALUES ('inv_100')"))

        with caplog.at_level(logging.INFO, logger="wishenka.wishlists.repository"):
            count = await store.cleanup_expired_tokens(now)

        assert count == 1
        mutation_records = [
            r
            for r in caplog.records
            if getattr(r, "event", None) == "wishlist_repo_mutation"
            and getattr(r, "entity", None) == "invite_token"
        ]
        assert len(mutation_records) == 1
        rec = mutation_records[0]
        assert rec.levelno == logging.INFO
        assert getattr(rec, "entity", None) == "invite_token"
        assert getattr(rec, "operation", None) == "cleanup_expired"
        assert getattr(rec, "count", None) == 1

        formatter = JsonFormatter()
        json_output = json.loads(formatter.format(rec))
        assert json_output["extra"]["event"] == "wishlist_repo_mutation"
        assert json_output["extra"]["entity"] == "invite_token"
        assert json_output["extra"]["operation"] == "cleanup_expired"
        assert json_output["extra"]["count"] == 1
    finally:
        await store.engine.dispose()


@pytest.mark.asyncio
async def test_wishlist_repo_mutation_purge_archived_logging(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Verify wishlist_repo_mutation event with entity='wishlist' and operation='purge_archived'."""
    db_path = tmp_path / "obs_repo_purge.db"
    store = WishlistStore(f"sqlite+aiosqlite:///{db_path}")
    await store.initialize()

    now = datetime(2026, 11, 11, 12, 0, 0, tzinfo=UTC)
    threshold = now - timedelta(days=30)
    old_deleted_dt = (now - timedelta(days=40)).isoformat()

    try:
        async with store.engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO wl_lists (id, owner_id, title, status, public_token, "
                    "invite_token, created_at, updated_at) "
                    "VALUES (200, 2, 'Deleted List', 'deleted', 'pub_200', 'inv_200', "
                    ":old, :old)"
                ),
                {"old": old_deleted_dt},
            )

        with caplog.at_level(logging.INFO, logger="wishenka.wishlists.repository"):
            count = await store.purge_archived_wishlists(threshold)

        assert count == 1
        mutation_records = [
            r
            for r in caplog.records
            if getattr(r, "event", None) == "wishlist_repo_mutation"
            and getattr(r, "entity", None) == "wishlist"
        ]
        assert len(mutation_records) == 1
        rec = mutation_records[0]
        assert rec.levelno == logging.INFO
        assert getattr(rec, "entity", None) == "wishlist"
        assert getattr(rec, "operation", None) == "purge_archived"
        assert getattr(rec, "count", None) == 1
        assert "threshold" in rec.__dict__

        formatter = JsonFormatter()
        json_output = json.loads(formatter.format(rec))
        assert json_output["extra"]["event"] == "wishlist_repo_mutation"
        assert json_output["extra"]["entity"] == "wishlist"
        assert json_output["extra"]["operation"] == "purge_archived"
        assert json_output["extra"]["count"] == 1
    finally:
        await store.engine.dispose()


@pytest.mark.asyncio
async def test_cleanup_logs_zero_token_leakage(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Verify that actual capability tokens are never leaked into cleanup log messages or extras."""
    db_path = tmp_path / "obs_zero_leakage.db"
    store = WishlistStore(f"sqlite+aiosqlite:///{db_path}")
    await store.initialize()

    sensitive_token = "secret_capability_token_xyz987"
    now = datetime(2026, 11, 11, 12, 0, 0, tzinfo=UTC)
    expired_dt = (now - timedelta(hours=1)).isoformat()
    now_iso = now.isoformat()

    try:
        async with store.engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO wl_lists (id, owner_id, title, status, public_token, "
                    "invite_token, invite_token_expires_at, created_at, updated_at) "
                    "VALUES (300, 3, 'Secret List', 'active', 'pub_300', :tok, "
                    ":exp, :now, :now)"
                ),
                {"tok": sensitive_token, "exp": expired_dt, "now": now_iso},
            )
            await conn.execute(
                text("INSERT INTO wl_invite_tokens (token) VALUES (:tok)"),
                {"tok": sensitive_token},
            )

        settings = Settings(database_url=f"sqlite+aiosqlite:///{db_path}")
        with caplog.at_level(logging.DEBUG):
            await run_cleanup_cycle(store, settings, now=now)

        for record in caplog.records:
            assert sensitive_token not in record.getMessage()
            for key, val in record.__dict__.items():
                if isinstance(val, str):
                    assert sensitive_token not in val, f"Leaked in record field {key}"
    finally:
        await store.engine.dispose()
