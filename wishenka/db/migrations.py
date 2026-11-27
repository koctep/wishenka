"""Apply one database history to one SQLite URL.

The procedure is history-agnostic: lock, optional adopt hook, Alembic
``upgrade head``, and WAL on a file database. The product history lives in
``wishenka.wishlists.migrations`` and is loaded only when the product binding
runs, so the two modules can import in either order.
"""

from __future__ import annotations

import asyncio
import contextlib
import fcntl
import logging
import os
import sqlite3
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

from alembic import command
from alembic.config import Config

_LOCK_SUFFIX = ".migrate.lock"
_LOCK_TIMEOUT_SECONDS = 60.0
_LOCK_POLL_SECONDS = 0.05


@dataclass(frozen=True)
class MigrationHistory:
    """One database's Alembic tree and the words used while applying it."""

    script_location: Path
    adopt: Callable[[str], None] | None
    log: logging.Logger
    unsupported_url_message: str
    lock_timeout_message: str
    started_event: str
    started_message: str
    failed_event: str
    failed_message: str
    completed_event: str
    completed_message: str


def migration_lock_path(path: Path) -> Path:
    """Return the sidecar lock file that serializes migrations of ``path``."""
    return path.with_name(path.name + _LOCK_SUFFIX)


def _sqlite_url(database_url: str) -> str:
    """Convert the async application URL to Alembic's synchronous SQLite URL."""
    return database_url.replace("sqlite+aiosqlite://", "sqlite://", 1)


def _database_path(database_url: str, unsupported_url_message: str) -> Path | None:
    prefix = "sqlite+aiosqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError(unsupported_url_message)
    value = database_url[len(prefix) :]
    return None if value == ":memory:" else Path(value)


def configured(database_url: str, *, script_location: Path) -> Config:
    """Load repository ``alembic.ini`` for one history and one database URL."""
    # This module sits in ``wishenka/db/``, so the repository root is two parents up.
    config = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    config.set_main_option("script_location", str(script_location))
    config.set_main_option("sqlalchemy.url", _sqlite_url(database_url))
    return config


@contextlib.contextmanager
def _migration_lock(path: Path | None, timeout_message: str) -> Iterator[None]:
    """Serialize adoption, upgrade and WAL selection across processes (bounded wait)."""
    if path is None:
        yield
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(migration_lock_path(path), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        deadline = time.monotonic() + _LOCK_TIMEOUT_SECONDS
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(timeout_message) from None
                time.sleep(_LOCK_POLL_SECONDS)
        try:
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


def _product_history() -> MigrationHistory:
    # Imported here so this module and the wishlist history can load in either order.
    from wishenka.wishlists.migrations import PRODUCT_HISTORY

    return PRODUCT_HISTORY


def apply_history_sync(database_url: str, history: MigrationHistory) -> None:
    """Bring one SQLite database to the head of ``history``."""
    start = time.perf_counter()
    history.log.info(
        history.started_message,
        extra={"event": history.started_event},
    )
    try:
        path = _database_path(database_url, history.unsupported_url_message)
        # The lock is held for the whole sequence; state is re-read after acquiring it,
        # so a late process sees alembic_version and ``upgrade head`` is a no-op.
        with _migration_lock(path, history.lock_timeout_message):
            if history.adopt is not None:
                history.adopt(database_url)
            config = configured(database_url, script_location=history.script_location)
            command.upgrade(config, "head")
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
        history.log.exception(
            history.failed_message,
            extra={"event": history.failed_event},
        )
        raise
    else:
        duration_ms = round((time.perf_counter() - start) * 1000)
        history.log.info(
            history.completed_message,
            duration_ms,
            extra={"event": history.completed_event, "duration_ms": duration_ms},
        )


async def apply_history(database_url: str, history: MigrationHistory) -> None:
    """Run :func:`apply_history_sync` without blocking the async application loop."""
    await asyncio.to_thread(apply_history_sync, database_url, history)


def upgrade_to_head_sync(database_url: str) -> None:
    """Apply the product history to ``database_url``."""
    apply_history_sync(database_url, _product_history())


async def upgrade_to_head(database_url: str) -> None:
    """Run the product history upgrade without blocking the async application loop."""
    await asyncio.to_thread(upgrade_to_head_sync, database_url)
