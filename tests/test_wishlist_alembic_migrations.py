"""Failing upgrade-path reproduction for WISHENKA-111."""

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import text

from wishenka.config import Settings
from wishenka.web.app import create_app
from wishenka.wishlists.store import WishlistStore

pytestmark = pytest.mark.timeout(10)


def _create_legacy_database(db_path: Path) -> None:
    """Create the complete normalized legacy schema with persisted records."""
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(
            """
            CREATE TABLE wl_lists (
                id INTEGER PRIMARY KEY,
                owner_id INTEGER NOT NULL,
                owner_name TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL,
                description TEXT,
                event_title TEXT,
                event_date TEXT,
                is_collaborative INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'active',
                public_token TEXT NOT NULL,
                invite_token TEXT NOT NULL,
                invite_token_expires_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX idx_wl_lists_owner ON wl_lists(owner_id);
            CREATE UNIQUE INDEX idx_wl_lists_public_token ON wl_lists(public_token);
            CREATE UNIQUE INDEX idx_wl_lists_invite_token ON wl_lists(invite_token);
            CREATE INDEX idx_wl_lists_status ON wl_lists(status);
            CREATE TABLE wl_members (
                id INTEGER PRIMARY KEY,
                wishlist_id INTEGER NOT NULL REFERENCES wl_lists(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL DEFAULT 'member',
                joined_at TEXT NOT NULL
            );
            CREATE UNIQUE INDEX idx_wl_members_unique ON wl_members(wishlist_id, user_id);
            CREATE INDEX idx_wl_members_user ON wl_members(user_id);
            CREATE TABLE wl_items (
                id INTEGER PRIMARY KEY,
                wishlist_id INTEGER NOT NULL REFERENCES wl_lists(id) ON DELETE CASCADE,
                recipient_user_id INTEGER,
                recipient_name TEXT,
                title TEXT NOT NULL,
                description TEXT,
                link TEXT,
                price INTEGER,
                currency TEXT NOT NULL DEFAULT 'RUB',
                quantity INTEGER NOT NULL DEFAULT 1,
                received_quantity INTEGER NOT NULL DEFAULT 0,
                image_url TEXT,
                store_name TEXT,
                store_icon_url TEXT,
                priority TEXT NOT NULL DEFAULT 'medium',
                category TEXT,
                is_archived INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX idx_wl_items_wishlist ON wl_items(wishlist_id);
            CREATE INDEX idx_wl_items_recipient ON wl_items(recipient_user_id);
            CREATE TABLE wl_reservations (
                id INTEGER PRIMARY KEY,
                wish_item_id INTEGER NOT NULL REFERENCES wl_items(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX idx_wl_reservations_item ON wl_reservations(wish_item_id);
            CREATE INDEX idx_wl_reservations_user ON wl_reservations(user_id);
            CREATE INDEX idx_wl_reservations_status ON wl_reservations(status);
            CREATE TABLE wl_favorites (
                user_id INTEGER NOT NULL,
                wishlist_id INTEGER NOT NULL REFERENCES wl_lists(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                PRIMARY KEY (user_id, wishlist_id)
            );
            CREATE INDEX idx_wl_favorites_user ON wl_favorites(user_id);
            CREATE TABLE wl_view_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                wishlist_id INTEGER NOT NULL REFERENCES wl_lists(id) ON DELETE CASCADE,
                viewed_at TEXT NOT NULL
            );
            CREATE UNIQUE INDEX wl_view_history_user_wl
                ON wl_view_history(user_id, wishlist_id);
            CREATE INDEX idx_wl_view_history_user_time
                ON wl_view_history(user_id, viewed_at DESC);
            CREATE TABLE wl_tokens (
                token TEXT PRIMARY KEY,
                wishlist_id INTEGER NOT NULL,
                active INTEGER NOT NULL DEFAULT 1
            );
            CREATE INDEX idx_wl_tokens_wishlist ON wl_tokens(wishlist_id, active);
            CREATE TABLE wl_invite_tokens (token TEXT PRIMARY KEY);
            CREATE TABLE wl_counters (name TEXT PRIMARY KEY, value INTEGER NOT NULL);
            """
        )
        connection.execute(
            """
            INSERT INTO wl_lists (
                id, owner_id, title, public_token, invite_token, created_at, updated_at
            ) VALUES (1, 101, 'Legacy wishes', 'public-token', 'invite-token', 'now', 'now')
            """
        )
        connection.execute(
            """
            INSERT INTO wl_items (id, wishlist_id, title, created_at, updated_at)
            VALUES (7, 1, 'Seeded legacy wish', 'now', 'now')
            """
        )
        connection.commit()
    finally:
        connection.close()


@pytest.mark.asyncio
async def test_legacy_database_is_adopted_at_alembic_head_without_losing_rows(
    tmp_path: Path,
) -> None:
    """A supported legacy file must be versioned, upgraded, and retain seeded rows."""
    db_path = tmp_path / "legacy-wishlist.db"
    _create_legacy_database(db_path)
    store = WishlistStore(f"sqlite+aiosqlite:///{db_path}")

    try:
        await store.initialize()

        async with store.engine.connect() as connection:
            version = (
                await connection.execute(text("SELECT version_num FROM alembic_version"))
            ).scalar_one()
            list_columns = {
                row[1]
                for row in (
                    await connection.execute(text("PRAGMA table_info(wl_lists)"))
                ).fetchall()
            }
            item_columns = {
                row[1]
                for row in (
                    await connection.execute(text("PRAGMA table_info(wl_items)"))
                ).fetchall()
            }
            order_index = (
                await connection.execute(
                    text(
                        "SELECT name FROM sqlite_master WHERE type = 'index' "
                        "AND name = 'idx_wl_items_order'"
                    )
                )
            ).scalar_one()
            persisted_rows = (
                await connection.execute(text("SELECT title FROM wl_items WHERE id = 7"))
            ).scalar_one()

        assert version
        assert "warn_on_delete_reserved" in list_columns
        assert "display_order" in item_columns
        assert order_index == "idx_wl_items_order"
        assert persisted_rows == "Seeded legacy wish"
    finally:
        await store.dispose()


@pytest.mark.asyncio
async def test_fresh_and_memory_stores_reach_the_same_alembic_head(tmp_path: Path) -> None:
    """All supported bootstrap paths use the same recorded current schema."""
    stores = (
        WishlistStore(f"sqlite+aiosqlite:///{tmp_path / 'fresh-wishlist.db'}"),
        WishlistStore("sqlite+aiosqlite:///:memory:"),
    )
    try:
        versions: list[str] = []
        for store in stores:
            await store.initialize()
            async with store.engine.connect() as connection:
                versions.append(
                    (
                        await connection.execute(text("SELECT version_num FROM alembic_version"))
                    ).scalar_one()
                )
        assert versions[0] == versions[1]
    finally:
        for store in stores:
            await store.dispose()


@pytest.mark.asyncio
async def test_memory_store_dispose_removes_its_temporary_database() -> None:
    """The compatibility file behind a memory URL belongs only to this store."""
    store = WishlistStore("sqlite+aiosqlite:///:memory:")
    temporary_path = store._temporary_database_path

    assert temporary_path is not None
    assert temporary_path.exists()

    await store.initialize()
    await store.dispose()

    assert not temporary_path.exists()


@pytest.mark.asyncio
async def test_app_lifespan_disposes_its_memory_wishlist_store() -> None:
    """App shutdown releases the temporary database created for a memory URL."""
    app = create_app(
        Settings(
            database_url="sqlite+aiosqlite:///:memory:",
            background_cleanup_enabled=False,
        )
    )
    temporary_path = app.state.wishlist_store._temporary_database_path

    assert temporary_path is not None
    assert temporary_path.exists()

    async with app.router.lifespan_context(app):
        assert temporary_path.exists()

    assert not temporary_path.exists()


@pytest.mark.asyncio
async def test_legacy_schema_with_ascending_history_index_is_not_adopted(tmp_path: Path) -> None:
    """Adoption rejects an index whose ordering differs from the baseline."""
    db_path = tmp_path / "ascending-history-index.db"
    _create_legacy_database(db_path)
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("DROP INDEX idx_wl_view_history_user_time")
        connection.execute(
            "CREATE INDEX idx_wl_view_history_user_time ON wl_view_history(user_id, viewed_at ASC)"
        )
        connection.commit()
    finally:
        connection.close()

    store = WishlistStore(f"sqlite+aiosqlite:///{db_path}")
    try:
        with pytest.raises(RuntimeError, match="Unable to initialize wishlist storage"):
            await store.initialize()
    finally:
        await store.dispose()

    connection = sqlite3.connect(db_path)
    try:
        assert (
            connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'alembic_version'"
            ).fetchone()
            is None
        )
    finally:
        connection.close()


@pytest.mark.asyncio
async def test_legacy_schema_with_malformed_display_order_marker_is_not_adopted(
    tmp_path: Path,
) -> None:
    """A present migration marker must still have the exact revision shape."""
    db_path = tmp_path / "malformed-display-order.db"
    _create_legacy_database(db_path)
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            "ALTER TABLE wl_lists ADD COLUMN warn_on_delete_reserved INTEGER NOT NULL DEFAULT 1"
        )
        connection.execute("ALTER TABLE wl_items ADD COLUMN display_order TEXT")
        connection.commit()
    finally:
        connection.close()

    store = WishlistStore(f"sqlite+aiosqlite:///{db_path}")
    try:
        with pytest.raises(RuntimeError, match="Unable to initialize wishlist storage"):
            await store.initialize()
    finally:
        await store.dispose()

    connection = sqlite3.connect(db_path)
    try:
        assert (
            connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'alembic_version'"
            ).fetchone()
            is None
        )
    finally:
        connection.close()
