"""Add foreign keys from wishlist user links to users(telegram_id) with cascade delete."""

import logging
from typing import NamedTuple

from alembic import op
from sqlalchemy import text

logger = logging.getLogger("wishenka.wishlists.migrations")

revision = "add_user_fk_cascades"
down_revision = "add_notice_retention_columns"
branch_labels = None
depends_on = None

_ENSURE_USERS_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL UNIQUE,
    first_name TEXT NOT NULL,
    last_name TEXT,
    username TEXT,
    language_code TEXT,
    locale TEXT NOT NULL DEFAULT 'en' CHECK (locale IN ('ru', 'en')),
    locale_source TEXT NOT NULL DEFAULT 'auto' CHECK (locale_source IN ('auto', 'explicit')),
    is_premium INTEGER NOT NULL DEFAULT 0 CHECK (is_premium IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""


class _TableSpec(NamedTuple):
    name: str
    columns: str
    upgrade_ddl: str
    downgrade_ddl: str
    indexes: tuple[str, ...]
    index_names: tuple[str, ...]


_SPECS: tuple[_TableSpec, ...] = (
    _TableSpec(
        name="wl_members",
        columns="id, wishlist_id, user_id, role, joined_at",
        upgrade_ddl="""
            CREATE TABLE wl_members (
                id INTEGER PRIMARY KEY,
                wishlist_id INTEGER NOT NULL REFERENCES wl_lists(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
                role TEXT NOT NULL DEFAULT 'member',
                joined_at TEXT NOT NULL
            )
        """,
        downgrade_ddl="""
            CREATE TABLE wl_members (
                id INTEGER PRIMARY KEY,
                wishlist_id INTEGER NOT NULL REFERENCES wl_lists(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL DEFAULT 'member',
                joined_at TEXT NOT NULL
            )
        """,
        indexes=(
            "CREATE UNIQUE INDEX idx_wl_members_unique ON wl_members(wishlist_id, user_id)",
            "CREATE INDEX idx_wl_members_user ON wl_members(user_id)",
        ),
        index_names=("idx_wl_members_unique", "idx_wl_members_user"),
    ),
    _TableSpec(
        name="wl_favorites",
        columns="user_id, wishlist_id, created_at",
        upgrade_ddl="""
            CREATE TABLE wl_favorites (
                user_id INTEGER NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
                wishlist_id INTEGER NOT NULL REFERENCES wl_lists(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                PRIMARY KEY (user_id, wishlist_id)
            )
        """,
        downgrade_ddl="""
            CREATE TABLE wl_favorites (
                user_id INTEGER NOT NULL,
                wishlist_id INTEGER NOT NULL REFERENCES wl_lists(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                PRIMARY KEY (user_id, wishlist_id)
            )
        """,
        indexes=("CREATE INDEX idx_wl_favorites_user ON wl_favorites(user_id)",),
        index_names=("idx_wl_favorites_user",),
    ),
    _TableSpec(
        name="wl_view_history",
        columns="id, user_id, wishlist_id, viewed_at",
        upgrade_ddl="""
            CREATE TABLE wl_view_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
                wishlist_id INTEGER NOT NULL REFERENCES wl_lists(id) ON DELETE CASCADE,
                viewed_at TEXT NOT NULL
            )
        """,
        downgrade_ddl="""
            CREATE TABLE wl_view_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                wishlist_id INTEGER NOT NULL REFERENCES wl_lists(id) ON DELETE CASCADE,
                viewed_at TEXT NOT NULL
            )
        """,
        indexes=(
            "CREATE UNIQUE INDEX wl_view_history_user_wl ON wl_view_history(user_id, wishlist_id)",
            "CREATE INDEX idx_wl_view_history_user_time "
            "ON wl_view_history(user_id, viewed_at DESC)",
        ),
        index_names=("wl_view_history_user_wl", "idx_wl_view_history_user_time"),
    ),
)


def _rebuild_table(spec: _TableSpec, *, with_fk: bool) -> int:
    """Rebuild ``spec.name`` with or without user_id FK, log counts, and recreate indexes."""
    legacy_name = f"{spec.name}_legacy"
    for index_name in spec.index_names:
        op.execute(f"DROP INDEX IF EXISTS {index_name}")
    op.execute(f"ALTER TABLE {spec.name} RENAME TO {legacy_name}")
    op.execute(spec.upgrade_ddl if with_fk else spec.downgrade_ddl)
    where_clause = (
        " WHERE user_id IN (SELECT telegram_id FROM users) "
        "AND wishlist_id IN (SELECT id FROM wl_lists)"
        if with_fk
        else ""
    )
    connection = op.get_bind()
    total_rows = int(connection.execute(text(f"SELECT COUNT(*) FROM {legacy_name}")).scalar_one())
    inserted = connection.execute(
        text(
            f"INSERT INTO {spec.name} ({spec.columns}) "
            f"SELECT {spec.columns} FROM {legacy_name}{where_clause}"
        )
    )
    kept_rows = max(0, int(inserted.rowcount or 0))
    removed_orphans = max(0, total_rows - kept_rows)
    op.execute(f"DROP TABLE {legacy_name}")
    for index_sql in spec.indexes:
        op.execute(index_sql)

    if with_fk and removed_orphans > 0:
        logger.warning(
            "Cleaned orphaned user/wishlist link rows during FK migration",
            extra={
                "event": "user_fk_migration_orphans_cleaned",
                "table": spec.name,
                "rows_removed": removed_orphans,
                "rows_kept": kept_rows,
            },
        )
    elif with_fk:
        logger.info(
            "Rebuilt table with user_id cascade FK",
            extra={
                "event": "user_fk_migration_table_rebuilt",
                "table": spec.name,
                "rows_kept": kept_rows,
            },
        )
    else:
        logger.info(
            "Rebuilt table without user_id FK",
            extra={
                "event": "user_fk_downgrade_table_rebuilt",
                "table": spec.name,
                "rows_kept": kept_rows,
            },
        )
    return removed_orphans


def upgrade() -> None:
    """Rebuild wl_members, wl_favorites, and wl_view_history with user_id CASCADE FKs."""
    op.execute(_ENSURE_USERS_SQL)
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id)")
    total_orphans = sum(_rebuild_table(spec, with_fk=True) for spec in _SPECS)
    logger.info(
        "Applied user_id cascade FK migration",
        extra={
            "event": "user_fk_migration_completed",
            "tables": len(_SPECS),
            "total_orphans_removed": total_orphans,
        },
    )


def downgrade() -> None:
    """Rebuild wl_members, wl_favorites, and wl_view_history without user_id FKs."""
    for spec in reversed(_SPECS):
        _rebuild_table(spec, with_fk=False)
    logger.info(
        "Reverted user_id cascade FK migration",
        extra={
            "event": "user_fk_downgrade_completed",
            "tables": len(_SPECS),
        },
    )
