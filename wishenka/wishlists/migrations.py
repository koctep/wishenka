"""Product migration history and safe adoption of known legacy SQLite schemas.

Applying a history lives in ``wishenka.db.migrations``. This module owns the
wishlist Alembic tree, older-wishlist recognition, and compatibility wrappers
for existing imports.
"""

from __future__ import annotations

import importlib
import logging
import sqlite3
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from wishenka.db.migrations import (
    MigrationHistory,
    apply_history,
    apply_history_sync,
    configured,
)
from wishenka.db.migrations import migration_lock_path as migration_lock_path

logger = logging.getLogger(__name__)

_REVISIONS = {
    (False, False, False): "base_normalized",
    (True, False, False): "add_warn_on_delete_reserved",
    (True, True, False): "add_display_order",
    (True, True, True): "add_item_order_index",
}
_TABLES = {
    "wl_lists",
    "wl_members",
    "wl_items",
    "wl_reservations",
    "wl_favorites",
    "wl_view_history",
    "wl_tokens",
    "wl_invite_tokens",
    "wl_counters",
}


def _database_path(database_url: str) -> Path | None:
    prefix = "sqlite+aiosqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError("Wishlist migrations support only SQLite URLs")
    value = database_url[len(prefix) :]
    return None if value == ":memory:" else Path(value)


def _configured(database_url: str) -> Config:
    return configured(database_url, script_location=PRODUCT_HISTORY.script_location)


def head_revision(database_url: str = "sqlite+aiosqlite:///:memory:") -> str:
    """Return the single head revision id of the Alembic script directory.

    The URL is only needed to build the configuration; it is never opened.
    """
    head = ScriptDirectory.from_config(_configured(database_url)).get_current_head()
    if head is None:
        raise RuntimeError("Wishlist migrations have no head revision")
    return head


def _schema_signature(connection: sqlite3.Connection, table: str) -> tuple[Any, Any, Any]:
    """Return the SQLite structural contract that is safe to stamp."""
    columns = tuple(tuple(row[1:]) for row in connection.execute(f"PRAGMA table_info({table})"))
    foreign_keys = tuple(
        tuple(row[2:]) for row in connection.execute(f"PRAGMA foreign_key_list({table})")
    )
    indexes: list[tuple[object, ...]] = []
    for row in connection.execute(f"PRAGMA index_list({table})"):
        name, unique, origin = row[1], row[2], row[3]
        if name.startswith("sqlite_autoindex"):
            continue
        # ``index_xinfo`` exposes the key-column direction in its ``desc``
        # field.  Keep it in the contract: an ascending index is not
        # interchangeable with the descending history lookup index.
        details = tuple(
            (part[2], part[3], part[4])
            for part in connection.execute(f"PRAGMA index_xinfo({name})")
            if part[5]
        )
        indexes.append((name, unique, origin, details))
    return columns, foreign_keys, tuple(sorted(indexes))


def _baseline_signatures() -> dict[str, tuple[Any, Any, Any]]:
    """Build the immutable baseline contract from the initial revision DDL."""
    module = importlib.import_module("wishenka.wishlists.alembic.versions.base_normalized")
    reference = sqlite3.connect(":memory:")
    try:
        for statement in module.DDL:
            reference.execute(statement)
        return {table: _schema_signature(reference, table) for table in _TABLES}
    finally:
        reference.close()


def _marker_signatures() -> tuple[tuple[Any, ...], tuple[Any, ...], tuple[object, ...]]:
    """Return the exact structural signatures introduced by later revisions."""
    module = importlib.import_module("wishenka.wishlists.alembic.versions.base_normalized")
    reference = sqlite3.connect(":memory:")
    try:
        for statement in module.DDL:
            reference.execute(statement)
        reference.execute(
            "ALTER TABLE wl_lists ADD COLUMN warn_on_delete_reserved INTEGER NOT NULL DEFAULT 1"
        )
        reference.execute(
            "ALTER TABLE wl_items ADD COLUMN display_order INTEGER NOT NULL DEFAULT 0"
        )
        reference.execute("CREATE INDEX idx_wl_items_order ON wl_items(wishlist_id, display_order)")
        list_column = next(
            column
            for column in _schema_signature(reference, "wl_lists")[0]
            if column[0] == "warn_on_delete_reserved"
        )
        item_column = next(
            column
            for column in _schema_signature(reference, "wl_items")[0]
            if column[0] == "display_order"
        )
        order_index = next(
            index
            for index in _schema_signature(reference, "wl_items")[2]
            if index[0] == "idx_wl_items_order"
        )
        return list_column, item_column, order_index
    finally:
        reference.close()


def _adopt_known_schema(database_url: str) -> None:
    path = _database_path(database_url)
    if path is None or not path.exists():
        return
    connection = sqlite3.connect(path)
    try:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if "alembic_version" in tables or not (tables & _TABLES):
            return
        user_tables = tables - {"sqlite_sequence"}
        if user_tables != _TABLES:
            raise RuntimeError("Unsupported wishlist database schema: tables do not match baseline")
        list_columns = {row[1] for row in connection.execute("PRAGMA table_info(wl_lists)")}
        item_columns = {row[1] for row in connection.execute("PRAGMA table_info(wl_items)")}
        flags = (
            "warn_on_delete_reserved" in list_columns,
            "display_order" in item_columns,
            connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='index' AND name='idx_wl_items_order'"
            ).fetchone()
            is not None,
        )
        revision = _REVISIONS.get(flags)
        if revision is None:
            raise RuntimeError(
                "Unsupported wishlist database schema: incompatible migration markers"
            )
        expected = _baseline_signatures()
        warn_column, display_order_column, order_index = _marker_signatures()
        for table in _TABLES:
            actual_signature = _schema_signature(connection, table)
            if table == "wl_lists" and flags[0]:
                if warn_column not in actual_signature[0]:
                    raise RuntimeError(
                        "Unsupported wishlist database schema: invalid warn-on-delete marker"
                    )
                # Compare the declared schema, excluding the one historically-added column.
                actual_columns = tuple(
                    column
                    for column in actual_signature[0]
                    if column[0] != "warn_on_delete_reserved"
                )
                actual_signature = (actual_columns, *actual_signature[1:])
            if table == "wl_items" and flags[1]:
                if display_order_column not in actual_signature[0]:
                    raise RuntimeError(
                        "Unsupported wishlist database schema: invalid display-order marker"
                    )
                if flags[2] and order_index not in actual_signature[2]:
                    raise RuntimeError(
                        "Unsupported wishlist database schema: invalid item-order index marker"
                    )
                actual_columns = tuple(
                    column for column in actual_signature[0] if column[0] != "display_order"
                )
                indexes = tuple(
                    index for index in actual_signature[2] if index[0] != "idx_wl_items_order"
                )
                actual_signature = (actual_columns, actual_signature[1], indexes)
            if actual_signature != expected[table]:
                raise RuntimeError(
                    f"Unsupported wishlist database schema: {table} does not match baseline"
                )
    finally:
        connection.close()
    command.stamp(_configured(database_url), revision)
    logger.info(
        "Adopted recognized legacy wishlist schema at revision %s",
        revision,
        extra={"event": "wishlist_migration_legacy_schema_adopted", "revision": revision},
    )


PRODUCT_HISTORY = MigrationHistory(
    script_location=Path(__file__).with_name("alembic"),
    adopt=_adopt_known_schema,
    log=logger,
    unsupported_url_message="Wishlist migrations support only SQLite URLs",
    lock_timeout_message="Timed out waiting for another process to finish wishlist migration",
    started_event="wishlist_migration_started",
    started_message="Starting wishlist database migration",
    failed_event="wishlist_migration_failed",
    failed_message="Wishlist database migration failed",
    completed_event="wishlist_migration_completed",
    completed_message="Wishlist database migration completed in %d ms",
)


def upgrade_to_head_sync(database_url: str) -> None:
    """Adopt a recognized legacy database, then apply ordered Alembic revisions."""
    apply_history_sync(database_url, PRODUCT_HISTORY)


async def upgrade_to_head(database_url: str) -> None:
    """Run the synchronous Alembic API without blocking the async application loop."""
    await apply_history(database_url, PRODUCT_HISTORY)
