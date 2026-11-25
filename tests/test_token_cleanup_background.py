"""Failing reproduction test suite for WISHENKA-50: Token TTL & Background Cleanup."""

import asyncio
import importlib
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text

from wishenka.config import Settings
from wishenka.web.app import create_app
from wishenka.wishlists.repository import WishlistRepository
from wishenka.wishlists.store import WishlistStore

pytestmark = pytest.mark.timeout(10)


def _load_cleanup_module() -> Any:
    """Dynamically load cleanup domain module or fail test if not implemented."""
    try:
        return importlib.import_module("wishenka.wishlists.cleanup")
    except ImportError as err:
        pytest.fail(f"wishenka.wishlists.cleanup module is not implemented yet: {err}")


def test_config_settings_defaults_and_env_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Settings must configure token TTL, retention, and background worker parameters."""
    settings = Settings()

    assert hasattr(settings, "invite_token_ttl_seconds"), (
        "Settings must define invite_token_ttl_seconds"
    )
    assert settings.invite_token_ttl_seconds == 7 * 86400

    assert hasattr(settings, "wishlist_retention_days"), (
        "Settings must define wishlist_retention_days"
    )
    assert settings.wishlist_retention_days == 30

    assert hasattr(settings, "background_cleanup_interval_seconds"), (
        "Settings must define background_cleanup_interval_seconds"
    )
    assert settings.background_cleanup_interval_seconds == 3600

    assert hasattr(settings, "background_cleanup_enabled"), (
        "Settings must define background_cleanup_enabled"
    )
    assert settings.background_cleanup_enabled is True

    # Test environment variable overrides
    monkeypatch.setenv("WISHENKA_INVITE_TOKEN_TTL_SECONDS", "86400")
    monkeypatch.setenv("WISHENKA_WISHLIST_RETENTION_DAYS", "14")
    monkeypatch.setenv("WISHENKA_BACKGROUND_CLEANUP_INTERVAL_SECONDS", "1800")
    monkeypatch.setenv("WISHENKA_BACKGROUND_CLEANUP_ENABLED", "false")

    custom_settings = Settings()
    assert custom_settings.invite_token_ttl_seconds == 86400
    assert custom_settings.wishlist_retention_days == 14
    assert custom_settings.background_cleanup_interval_seconds == 1800
    assert custom_settings.background_cleanup_enabled is False


@pytest.mark.asyncio
async def test_cleanup_expired_tokens_repo(tmp_path: Path) -> None:
    """Repository must revoke expired invite tokens and remove from wl_invite_tokens."""
    db_path = tmp_path / "repo_expired_tokens.db"
    store = WishlistStore(f"sqlite+aiosqlite:///{db_path}")
    await store.initialize()

    now = datetime(2026, 11, 11, 12, 0, 0, tzinfo=UTC)
    active_expiry = (now + timedelta(days=2)).isoformat()
    expired_expiry = (now - timedelta(hours=1)).isoformat()
    now_iso = now.isoformat()

    try:
        async with store.engine.begin() as conn:
            # Active invite token
            await conn.execute(
                text(
                    "INSERT INTO wl_lists (id, owner_id, title, status, public_token, "
                    "invite_token, invite_token_expires_at, created_at, updated_at) "
                    "VALUES (1, 10, 'Active List', 'active', 'pub_1', 'tok_active', "
                    ":exp, :now, :now)"
                ),
                {"exp": active_expiry, "now": now_iso},
            )
            await conn.execute(
                text("INSERT INTO wl_invite_tokens (token, wishlist_id) VALUES ('tok_active', 1)")
            )

            # Expired invite token
            await conn.execute(
                text(
                    "INSERT INTO wl_lists (id, owner_id, title, status, public_token, "
                    "invite_token, invite_token_expires_at, created_at, updated_at) "
                    "VALUES (2, 20, 'Expired List', 'active', 'pub_2', 'tok_expired', "
                    ":exp, :now, :now)"
                ),
                {"exp": expired_expiry, "now": now_iso},
            )
            await conn.execute(
                text("INSERT INTO wl_invite_tokens (token, wishlist_id) VALUES ('tok_expired', 2)")
            )

        async with store.engine.begin() as conn:
            repo = WishlistRepository(conn)
            assert hasattr(repo, "cleanup_expired_tokens"), (
                "WishlistRepository must implement cleanup_expired_tokens"
            )
            cleaned_count = await repo.cleanup_expired_tokens(now)
            assert cleaned_count == 1

        async with store.engine.connect() as conn:
            # Check active token remains untouched
            row1 = (
                await conn.execute(
                    text("SELECT invite_token, invite_token_expires_at FROM wl_lists WHERE id = 1")
                )
            ).one()
            assert row1[0] == "tok_active"
            assert row1[1] == active_expiry

            tok_active_row = (
                await conn.execute(
                    text("SELECT token FROM wl_invite_tokens WHERE token = 'tok_active'")
                )
            ).one_or_none()
            assert tok_active_row is not None

            # Check expired token was revoked and removed from wl_invite_tokens
            row2 = (
                await conn.execute(
                    text("SELECT invite_token, invite_token_expires_at FROM wl_lists WHERE id = 2")
                )
            ).one()
            assert row2[0] != "tok_expired"
            assert row2[0].startswith("revoked:")
            assert row2[1] is None

            tok_expired_row = (
                await conn.execute(
                    text("SELECT token FROM wl_invite_tokens WHERE token = 'tok_expired'")
                )
            ).one_or_none()
            assert tok_expired_row is None
    finally:
        await store.engine.dispose()


@pytest.mark.asyncio
async def test_purge_archived_wishlists_repo(tmp_path: Path) -> None:
    """Repository must purge deleted wishlists older than threshold and cascade delete."""
    db_path = tmp_path / "repo_purge.db"
    store = WishlistStore(f"sqlite+aiosqlite:///{db_path}")
    await store.initialize()

    now = datetime(2026, 11, 11, 12, 0, 0, tzinfo=UTC)
    threshold = now - timedelta(days=30)
    old_date = (now - timedelta(days=40)).isoformat()
    recent_date = (now - timedelta(days=5)).isoformat()
    now_iso = now.isoformat()

    try:
        async with store.engine.begin() as conn:
            await conn.exec_driver_sql("PRAGMA foreign_keys = ON")

            # 1. Active wishlist older than threshold (MUST NOT be purged)
            await conn.execute(
                text(
                    "INSERT INTO wl_lists (id, owner_id, title, status, public_token, "
                    "invite_token, created_at, updated_at) "
                    "VALUES (10, 1, 'Active Old', 'active', 'pub_10', 'inv_10', :old, :old)"
                ),
                {"old": old_date},
            )

            # 2. Archived wishlist older than threshold (MUST NOT be purged)
            await conn.execute(
                text(
                    "INSERT INTO wl_lists (id, owner_id, title, status, public_token, "
                    "invite_token, created_at, updated_at) "
                    "VALUES (20, 2, 'Archived Old', 'archived', 'pub_20', 'inv_20', :old, :old)"
                ),
                {"old": old_date},
            )

            # 3. Soft-deleted wishlist within retention window (MUST NOT be purged)
            await conn.execute(
                text(
                    "INSERT INTO wl_lists (id, owner_id, title, status, public_token, "
                    "invite_token, created_at, updated_at) "
                    "VALUES (30, 3, 'Deleted Recent', 'deleted', 'pub_30', 'inv_30', :now, :rec)"
                ),
                {"now": now_iso, "rec": recent_date},
            )

            # 4. Soft-deleted wishlist past retention threshold (MUST be purged)
            for uid in (999, 777):
                await conn.execute(
                    text(
                        "INSERT OR IGNORE INTO users "
                        "(telegram_id, first_name, created_at, updated_at) "
                        "VALUES (:uid, 'User', :now, :now)"
                    ),
                    {"uid": uid, "now": now_iso},
                )
            await conn.execute(
                text(
                    "INSERT INTO wl_lists (id, owner_id, title, status, public_token, "
                    "invite_token, created_at, updated_at) "
                    "VALUES (40, 4, 'Deleted Old', 'deleted', 'pub_40', 'inv_40', :old, :old)"
                ),
                {"old": old_date},
            )
            await conn.execute(
                text("INSERT INTO wl_tokens (token, wishlist_id, active) VALUES ('pub_40', 40, 1)")
            )
            await conn.execute(
                text(
                    "INSERT INTO wl_members (id, wishlist_id, user_id, role, joined_at) "
                    "VALUES (401, 40, 999, 'member', :now)"
                ),
                {"now": now_iso},
            )
            await conn.execute(
                text(
                    "INSERT INTO wl_items (id, wishlist_id, title, created_at, updated_at) "
                    "VALUES (402, 40, 'Purged Item', :now, :now)"
                ),
                {"now": now_iso},
            )
            await conn.execute(
                text(
                    "INSERT INTO wl_reservations "
                    "(id, wish_item_id, user_id, created_at, updated_at) "
                    "VALUES (403, 402, 888, :now, :now)"
                ),
                {"now": now_iso},
            )
            await conn.execute(
                text(
                    "INSERT INTO wl_favorites (user_id, wishlist_id, created_at) "
                    "VALUES (777, 40, :now)"
                ),
                {"now": now_iso},
            )
            await conn.execute(
                text(
                    "INSERT INTO wl_view_history (id, user_id, wishlist_id, viewed_at) "
                    "VALUES (404, 777, 40, :now)"
                ),
                {"now": now_iso},
            )

        async with store.engine.begin() as conn:
            await conn.exec_driver_sql("PRAGMA foreign_keys = ON")
            repo = WishlistRepository(conn)
            assert hasattr(repo, "purge_archived_wishlists"), (
                "WishlistRepository must implement purge_archived_wishlists"
            )
            assert hasattr(repo, "purge_deleted_wishlists"), (
                "WishlistRepository must implement purge_deleted_wishlists alias"
            )
            purged_count = await repo.purge_archived_wishlists(threshold)
            assert purged_count == 1

        async with store.engine.connect() as conn:
            # Wishlists 10, 20, 30 must remain
            remaining_ids = {
                row[0] for row in (await conn.execute(text("SELECT id FROM wl_lists"))).fetchall()
            }
            assert remaining_ids == {10, 20, 30}

            # Wishlist 40 must be completely purged along with cascaded records
            assert (
                await conn.execute(text("SELECT COUNT(*) FROM wl_members WHERE wishlist_id = 40"))
            ).scalar() == 0
            assert (
                await conn.execute(text("SELECT COUNT(*) FROM wl_items WHERE wishlist_id = 40"))
            ).scalar() == 0
            assert (
                await conn.execute(
                    text("SELECT COUNT(*) FROM wl_reservations WHERE wish_item_id = 402")
                )
            ).scalar() == 0
            assert (
                await conn.execute(text("SELECT COUNT(*) FROM wl_favorites WHERE wishlist_id = 40"))
            ).scalar() == 0
            assert (
                await conn.execute(
                    text("SELECT COUNT(*) FROM wl_view_history WHERE wishlist_id = 40")
                )
            ).scalar() == 0
    finally:
        await store.engine.dispose()


@pytest.mark.asyncio
async def test_wishlist_store_cleanup_methods(tmp_path: Path) -> None:
    """WishlistStore must expose convenience methods delegating to repository."""
    db_path = tmp_path / "store_cleanup.db"
    store = WishlistStore(f"sqlite+aiosqlite:///{db_path}")
    await store.initialize()

    try:
        assert hasattr(store, "cleanup_expired_tokens"), (
            "WishlistStore must implement cleanup_expired_tokens"
        )
        assert hasattr(store, "purge_archived_wishlists"), (
            "WishlistStore must implement purge_archived_wishlists"
        )
        assert hasattr(store, "purge_deleted_wishlists"), (
            "WishlistStore must implement purge_deleted_wishlists"
        )

        now = datetime.now(UTC)
        threshold = now - timedelta(days=30)

        # Calling store convenience methods directly inside isolated transactions
        cleaned = await store.cleanup_expired_tokens(now)
        assert isinstance(cleaned, int)

        purged = await store.purge_archived_wishlists(threshold)
        assert isinstance(purged, int)
    finally:
        await store.engine.dispose()


@pytest.mark.asyncio
async def test_run_cleanup_cycle_domain(tmp_path: Path) -> None:
    """run_cleanup_cycle must clean expired tokens and purge old wishlists returning stats."""
    cleanup_mod = _load_cleanup_module()
    run_cleanup_cycle = getattr(cleanup_mod, "run_cleanup_cycle", None)
    CleanupStats = getattr(cleanup_mod, "CleanupStats", None)
    assert run_cleanup_cycle is not None, "cleanup module must define run_cleanup_cycle"
    assert CleanupStats is not None, "cleanup module must define CleanupStats"

    db_path = tmp_path / "domain_cleanup.db"
    store = WishlistStore(f"sqlite+aiosqlite:///{db_path}")
    await store.initialize()

    now = datetime(2026, 11, 11, 12, 0, 0, tzinfo=UTC)
    expired_expiry = (now - timedelta(hours=2)).isoformat()
    old_date = (now - timedelta(days=40)).isoformat()
    now_iso = now.isoformat()

    try:
        async with store.engine.begin() as conn:
            # Expired token on active wishlist
            await conn.execute(
                text(
                    "INSERT INTO wl_lists (id, owner_id, title, status, public_token, "
                    "invite_token, invite_token_expires_at, created_at, updated_at) "
                    "VALUES (101, 1, 'Expired List', 'active', 'pub_101', 'tok_101', "
                    ":exp, :now, :now)"
                ),
                {"exp": expired_expiry, "now": now_iso},
            )
            await conn.execute(
                text("INSERT INTO wl_invite_tokens (token, wishlist_id) VALUES ('tok_101', 101)")
            )

            # Soft-deleted wishlist past 30-day retention
            await conn.execute(
                text(
                    "INSERT INTO wl_lists (id, owner_id, title, status, public_token, "
                    "invite_token, created_at, updated_at) "
                    "VALUES (202, 2, 'Deleted List', 'deleted', 'pub_202', 'tok_202', "
                    ":old, :old)"
                ),
                {"old": old_date},
            )

        settings = Settings(
            database_url=f"sqlite+aiosqlite:///{db_path}",
            wishlist_retention_days=30,
        )

        stats = await run_cleanup_cycle(store, settings, now=now)

        assert isinstance(stats, CleanupStats)
        assert stats.expired_tokens_cleaned == 1
        assert stats.wishlists_purged == 1
        assert stats.duration_ms >= 0
        assert stats.started_at <= stats.finished_at
    finally:
        await store.engine.dispose()


@pytest.mark.asyncio
async def test_run_cleanup_cycle_error_resilience(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """run_cleanup_cycle must handle operational failures gracefully and log structured error."""
    cleanup_mod = _load_cleanup_module()
    run_cleanup_cycle = getattr(cleanup_mod, "run_cleanup_cycle", None)
    assert run_cleanup_cycle is not None, "cleanup module must define run_cleanup_cycle"

    mock_store = AsyncMock()
    mock_store.cleanup_expired_tokens.side_effect = RuntimeError("Database locked")
    settings = Settings()

    with caplog.at_level(logging.ERROR, logger="wishenka.wishlists.cleanup"):
        # Execution must not raise an unhandled exception
        stats = await run_cleanup_cycle(mock_store, settings)

    assert stats.expired_tokens_cleaned == 0
    assert stats.wishlists_purged == 0
    assert any(
        "background_cleanup_failed" in record.message
        or getattr(record, "event", None) == "background_cleanup_failed"
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_lifespan_background_worker_lifecycle(tmp_path: Path) -> None:
    """Lifespan must spawn background cleanup task when enabled and cancel on shutdown."""
    db_path = tmp_path / "lifespan_enabled.db"
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{db_path}",
        background_cleanup_enabled=True,
        background_cleanup_interval_seconds=1,
    )
    assert hasattr(settings, "background_cleanup_enabled"), (
        "Settings must define background_cleanup_enabled"
    )

    app = create_app(settings)
    async with app.router.lifespan_context(app):
        task = getattr(app.state, "cleanup_task", None) or getattr(
            app.state, "background_cleanup_task", None
        )
        assert task is not None, "Lifespan must spawn background cleanup task"
        assert isinstance(task, asyncio.Task)
        assert not task.done(), "Background cleanup task should be running during lifespan"

    # After lifespan exit, the task must be cancelled and terminated
    assert task.done() or task.cancelled()


@pytest.mark.asyncio
async def test_lifespan_background_worker_disabled_in_testing(tmp_path: Path) -> None:
    """Lifespan must NOT spawn background cleanup task when background_cleanup_enabled is False."""
    db_path = tmp_path / "lifespan_disabled.db"
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{db_path}",
        background_cleanup_enabled=False,
    )
    assert hasattr(settings, "background_cleanup_enabled"), (
        "Settings must define background_cleanup_enabled"
    )

    app = create_app(settings)
    async with app.router.lifespan_context(app):
        task = getattr(app.state, "cleanup_task", None) or getattr(
            app.state, "background_cleanup_task", None
        )
        assert task is None, "Lifespan must not spawn background task when disabled"
