"""Controlled Alembic upgrades and safe adoption of known legacy SQLite schemas."""

from __future__ import annotations

import asyncio
import contextlib
import fcntl
import importlib
import logging
import os
import sqlite3
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config

logger = logging.getLogger(__name__)

_LOCK_SUFFIX = ".migrate.lock"
_LOCK_TIMEOUT_SECONDS = 60.0
_LOCK_POLL_SECONDS = 0.05

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


def _sqlite_url(database_url: str) -> str:
    """Convert the async application URL to Alembic's synchronous SQLite URL."""
    return database_url.replace("sqlite+aiosqlite://", "sqlite://", 1)


def _database_path(database_url: str) -> Path | None:
    prefix = "sqlite+aiosqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError("Wishlist migrations support only SQLite URLs")
    value = database_url[len(prefix) :]
    return None if value == ":memory:" else Path(value)


def _configured(database_url: str) -> Config:
    config = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).with_name("alembic")))
    config.set_main_option("sqlalchemy.url", _sqlite_url(database_url))
    return config


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


def migration_lock_path(path: Path) -> Path:
    """Return the sidecar lock file that serializes migrations of ``path``."""
    return path.with_name(path.name + _LOCK_SUFFIX)


@contextlib.contextmanager
def _migration_lock(path: Path | None, timeout: float = _LOCK_TIMEOUT_SECONDS) -> Iterator[None]:
    """Serialize adoption, upgrade and WAL selection across processes (bounded wait)."""
    if path is None:
        yield
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(migration_lock_path(path), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        "Timed out waiting for another process to finish wishlist migration"
                    ) from None
                time.sleep(_LOCK_POLL_SECONDS)
        try:
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


def upgrade_to_head_sync(database_url: str) -> None:
    """Adopt a recognized legacy database, then apply ordered Alembic revisions."""
    start = time.perf_counter()
    logger.info(
        "Starting wishlist database migration",
        extra={"event": "wishlist_migration_started"},
    )
    try:
        path = _database_path(database_url)
        # The lock is held for the whole sequence; state is re-read after acquiring it,
        # so a late process sees alembic_version and ``upgrade head`` is a no-op.
        with _migration_lock(path):
            _adopt_known_schema(database_url)
            command.upgrade(_configured(database_url), "head")
            if path is not None:
                # Journal mode is persistent database state.  Set it once while startup
                # owns schema migration, rather than on every pooled connection where
                # two workers can contend for SQLite's exclusive mode-change lock.
                connection = sqlite3.connect(path)
                try:
                    connection.execute("PRAGMA journal_mode=WAL")
                finally:
                    connection.close()
    except Exception:
        logger.exception(
            "Wishlist database migration failed",
            extra={"event": "wishlist_migration_failed"},
        )
        raise
    else:
        duration_ms = round((time.perf_counter() - start) * 1000)
        logger.info(
            "Wishlist database migration completed in %d ms",
            duration_ms,
            extra={"event": "wishlist_migration_completed", "duration_ms": duration_ms},
        )


async def upgrade_to_head(database_url: str) -> None:
    """Run the synchronous Alembic API without blocking the async application loop."""
    await asyncio.to_thread(upgrade_to_head_sync, database_url)
