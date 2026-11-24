"""Shared SQLite transaction configuration and busy-error detection helpers."""

from __future__ import annotations

import sqlite3
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import Connection as SyncConnection
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError


def configure_immediate_transactions(sync_engine: Engine, *, busy_timeout_ms: int = 5000) -> None:
    """Take the SQLite reserved lock with BEGIN IMMEDIATE on Connection.begin()."""
    timeout_pragma = f"PRAGMA busy_timeout={int(busy_timeout_ms)}"

    @event.listens_for(sync_engine, "connect")
    def _sqlite_connect(dbapi_connection: Any, _connection_record: Any) -> None:
        # isolation_level None stops sqlite3 from emitting its own BEGIN.
        dbapi_connection.isolation_level = None
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute(timeout_pragma)
        finally:
            cursor.close()

    @event.listens_for(sync_engine, "begin")
    def _sqlite_begin_immediate(conn: SyncConnection) -> None:
        if conn.get_execution_options().get("isolation_level") == "AUTOCOMMIT":
            return
        # busy_timeout is applied before BEGIN IMMEDIATE, while __in_begin
        # prevents SQLAlchemy from opening a second transaction for the pragma.
        conn.exec_driver_sql(timeout_pragma)
        if conn.get_execution_options().get("read_only"):
            conn.exec_driver_sql("BEGIN")
        else:
            conn.exec_driver_sql("BEGIN IMMEDIATE")


def _sqlite_error_is_busy(exc: BaseException) -> bool:
    if isinstance(exc, sqlite3.Error):
        code = getattr(exc, "sqlite_errorcode", None)
        if isinstance(code, int) and (code & 0xFF) == sqlite3.SQLITE_BUSY:
            return True
    if isinstance(exc, sqlite3.Error | SQLAlchemyError):
        message = str(exc).casefold()
        return "database is locked" in message or "database is busy" in message
    return False


def is_sqlite_busy(exc: BaseException) -> bool:
    """Return True when exc or its driver/cause chain represents SQLITE_BUSY."""
    pending: list[BaseException] = [exc]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        marker = id(current)
        if marker in seen:
            continue
        seen.add(marker)
        if _sqlite_error_is_busy(current):
            return True
        orig = getattr(current, "orig", None)
        if isinstance(orig, BaseException):
            pending.append(orig)
        cause = current.__cause__
        if isinstance(cause, BaseException):
            pending.append(cause)
    return False
