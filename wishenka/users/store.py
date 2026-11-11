"""Async transactional SQLite storage for user entities."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import Row, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from wishenka.users.models import UserRecord

if TYPE_CHECKING:
    from wishenka.auth.models import TelegramUser

logger = logging.getLogger("wishenka.users")


class UserStore:
    """Async transactional SQLite storage for user entities."""

    def __init__(self, database_url: str) -> None:
        prefix = "sqlite+aiosqlite:///"
        if not database_url.startswith(prefix):
            raise ValueError("UserStore requires SQLite database URL")
        path = database_url[len(prefix) :]
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.engine: AsyncEngine = create_async_engine(
            database_url,
            connect_args={"timeout": 5},
            hide_parameters=True,
        )
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize table schema and WAL mode idempotently."""
        async with self.engine.begin() as conn:
            await conn.exec_driver_sql("PRAGMA journal_mode=WAL")
            await conn.exec_driver_sql("PRAGMA foreign_keys=ON")
            await conn.exec_driver_sql("PRAGMA busy_timeout=5000")
            await conn.exec_driver_sql(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER NOT NULL UNIQUE,
                    first_name TEXT NOT NULL,
                    last_name TEXT,
                    username TEXT,
                    language_code TEXT,
                    is_premium INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            await conn.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id)"
            )
            await conn.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)"
            )
        self._initialized = True

    async def _ensure_initialized(self) -> None:
        """Ensure schema is initialized if lifespan startup was bypassed."""
        if not self._initialized:
            await self.initialize()

    @staticmethod
    def _row_to_record(row: Row[Any]) -> UserRecord:
        """Convert a database row into a UserRecord."""
        created_val = row.created_at
        updated_val = row.updated_at
        created_dt = (
            datetime.fromisoformat(created_val) if isinstance(created_val, str) else created_val
        )
        updated_dt = (
            datetime.fromisoformat(updated_val) if isinstance(updated_val, str) else updated_val
        )
        return UserRecord(
            id=int(row.id),
            telegram_id=int(row.telegram_id),
            first_name=str(row.first_name),
            last_name=str(row.last_name) if row.last_name is not None else None,
            username=str(row.username) if row.username is not None else None,
            language_code=str(row.language_code) if row.language_code is not None else None,
            is_premium=bool(row.is_premium),
            created_at=created_dt,
            updated_at=updated_dt,
        )

    async def upsert_user(self, user: TelegramUser) -> UserRecord:
        """Insert new user or update mutable attributes if already exists."""
        await self._ensure_initialized()
        now_iso = datetime.now(UTC).isoformat()
        stmt = text(
            """
            INSERT INTO users (
                telegram_id, first_name, last_name, username,
                language_code, is_premium, created_at, updated_at
            ) VALUES (
                :telegram_id, :first_name, :last_name, :username,
                :language_code, :is_premium, :created_at, :updated_at
            )
            ON CONFLICT(telegram_id) DO UPDATE SET
                first_name = excluded.first_name,
                last_name = excluded.last_name,
                username = excluded.username,
                language_code = excluded.language_code,
                is_premium = excluded.is_premium,
                updated_at = excluded.updated_at
            RETURNING id, telegram_id, first_name, last_name,
                      username, language_code, is_premium,
                      created_at, updated_at
            """
        )
        params = {
            "telegram_id": user.id,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "username": user.username,
            "language_code": user.language_code,
            "is_premium": 1 if user.is_premium else 0,
            "created_at": now_iso,
            "updated_at": now_iso,
        }
        async with self.engine.begin() as conn:
            existing = await conn.execute(
                text("SELECT id FROM users WHERE telegram_id = :telegram_id"),
                {"telegram_id": user.id},
            )
            is_new = existing.first() is None
            result = await conn.execute(stmt, params)
            row = result.one()
            record = self._row_to_record(row)
            if is_new:
                logger.info(
                    "User %s created with telegram_id %s",
                    record.id,
                    record.telegram_id,
                    extra={
                        "event": "user_created",
                        "user_id": record.id,
                        "telegram_id": record.telegram_id,
                    },
                )
            else:
                logger.info(
                    "User %s updated with telegram_id %s",
                    record.id,
                    record.telegram_id,
                    extra={
                        "event": "user_updated",
                        "user_id": record.id,
                        "telegram_id": record.telegram_id,
                    },
                )
            return record

    async def get_by_telegram_id(self, telegram_id: int) -> UserRecord | None:
        """Find user by numeric Telegram ID."""
        await self._ensure_initialized()
        stmt = text(
            """
            SELECT id, telegram_id, first_name, last_name,
                   username, language_code, is_premium,
                   created_at, updated_at
            FROM users WHERE telegram_id = :telegram_id
            """
        )
        async with self.engine.connect() as conn:
            result = await conn.execute(stmt, {"telegram_id": telegram_id})
            row = result.first()
            return self._row_to_record(row) if row is not None else None

    async def get_by_id(self, user_id: int) -> UserRecord | None:
        """Find user by internal database primary key."""
        await self._ensure_initialized()
        stmt = text(
            """
            SELECT id, telegram_id, first_name, last_name,
                   username, language_code, is_premium,
                   created_at, updated_at
            FROM users WHERE id = :id
            """
        )
        async with self.engine.connect() as conn:
            result = await conn.execute(stmt, {"id": user_id})
            row = result.first()
            return self._row_to_record(row) if row is not None else None

    async def dispose(self) -> None:
        """Cleanly close connection pools."""
        await self.engine.dispose()
