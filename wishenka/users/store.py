"""Async transactional SQLite storage for user entities."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import Row, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from wishenka.i18n.locale import (
    LocaleSource,
    SupportedLocale,
    resolve_telegram_locale,
    validate_locale,
)
from wishenka.users.models import BirthdateSource, UserRecord

if TYPE_CHECKING:
    from wishenka.auth.models import TelegramUser

logger = logging.getLogger("wishenka.users")

_USERS_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL UNIQUE,
    first_name TEXT NOT NULL,
    last_name TEXT,
    username TEXT,
    language_code TEXT,
    locale TEXT NOT NULL DEFAULT 'en' CHECK (locale IN ('ru', 'en')),
    locale_source TEXT NOT NULL DEFAULT 'auto' CHECK (locale_source IN ('auto', 'explicit')),
    birth_day INTEGER,
    birth_month INTEGER,
    birth_year INTEGER,
    birthdate_source TEXT NOT NULL DEFAULT 'auto'
        CHECK (birthdate_source IN ('auto', 'explicit')),
    is_premium INTEGER NOT NULL DEFAULT 0 CHECK (is_premium IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

_BACKFILL_ALL_SQL = """
UPDATE users
SET locale = CASE
        WHEN lower(trim(coalesce(language_code, ''))) LIKE 'ru%' THEN 'ru'
        ELSE 'en'
    END,
    locale_source = 'auto'
"""

_REPAIR_INVALID_SQL = """
UPDATE users
SET locale = CASE
        WHEN lower(trim(coalesce(language_code, ''))) LIKE 'ru%' THEN 'ru'
        ELSE 'en'
    END,
    locale_source = 'auto'
WHERE locale IS NULL
   OR locale NOT IN ('ru', 'en')
   OR locale_source IS NULL
   OR locale_source NOT IN ('auto', 'explicit')
"""

_USER_COLUMNS = (
    "id, telegram_id, first_name, last_name, username, language_code, "
    "locale, locale_source, birth_day, birth_month, birth_year, birthdate_source, "
    "is_premium, created_at, updated_at"
)


def validate_birthdate(
    day: object, month: object, year: object = None
) -> tuple[int, int, int | None]:
    """Validate calendar birthdate (day, month, optional year); allows Feb 29 without year."""
    if isinstance(day, bool) or not isinstance(day, int):
        raise ValueError("Invalid birth day")
    if isinstance(month, bool) or not isinstance(month, int):
        raise ValueError("Invalid birth month")
    if year is not None:
        if isinstance(year, bool) or not isinstance(year, int):
            raise ValueError("Invalid birth year")
        current_year = datetime.now(UTC).year
        if year < 1900 or year > current_year:
            raise ValueError("Birth year out of range")
    check_year = year if year is not None else 2000
    try:
        date(check_year, month, day)
    except ValueError as err:
        raise ValueError("Invalid calendar birthdate") from err
    return day, month, year


class UserNotFoundError(LookupError):
    """Raised when an operation targets a non-existent user record."""


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
        """Initialize table schema, locale columns, and WAL mode idempotently."""
        async with self.engine.begin() as conn:
            await conn.exec_driver_sql("PRAGMA journal_mode=WAL")
            await conn.exec_driver_sql("PRAGMA foreign_keys=ON")
            await conn.exec_driver_sql("PRAGMA busy_timeout=5000")
            await conn.exec_driver_sql(_USERS_TABLE_DDL)
            await conn.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id)"
            )
            await conn.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)"
            )
            columns_res = await conn.execute(text("PRAGMA table_info(users)"))
            columns = {str(row["name"]) for row in columns_res.mappings().all()}
            added_column = False
            if "locale" not in columns:
                await conn.exec_driver_sql(
                    "ALTER TABLE users ADD COLUMN locale TEXT NOT NULL DEFAULT 'en' "
                    "CHECK (locale IN ('ru', 'en'))"
                )
                added_column = True
            if "locale_source" not in columns:
                await conn.exec_driver_sql(
                    "ALTER TABLE users ADD COLUMN locale_source TEXT NOT NULL DEFAULT 'auto' "
                    "CHECK (locale_source IN ('auto', 'explicit'))"
                )
                added_column = True
            if added_column:
                await conn.exec_driver_sql(_BACKFILL_ALL_SQL)
            else:
                await conn.exec_driver_sql(_REPAIR_INVALID_SQL)
            if "birth_day" not in columns:
                await conn.exec_driver_sql("ALTER TABLE users ADD COLUMN birth_day INTEGER")
            if "birth_month" not in columns:
                await conn.exec_driver_sql("ALTER TABLE users ADD COLUMN birth_month INTEGER")
            if "birth_year" not in columns:
                await conn.exec_driver_sql("ALTER TABLE users ADD COLUMN birth_year INTEGER")
            if "birthdate_source" not in columns:
                await conn.exec_driver_sql(
                    "ALTER TABLE users ADD COLUMN birthdate_source TEXT NOT NULL DEFAULT 'auto' "
                    "CHECK (birthdate_source IN ('auto', 'explicit'))"
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
        raw_locale = getattr(row, "locale", "en")
        locale: SupportedLocale = "ru" if raw_locale == "ru" else "en"
        raw_source = getattr(row, "locale_source", "auto")
        locale_source: LocaleSource = "explicit" if raw_source == "explicit" else "auto"
        raw_birth_day = getattr(row, "birth_day", None)
        raw_birth_month = getattr(row, "birth_month", None)
        raw_birth_year = getattr(row, "birth_year", None)
        raw_bday_source = getattr(row, "birthdate_source", "auto")
        birthdate_source: BirthdateSource = "explicit" if raw_bday_source == "explicit" else "auto"
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
            locale=locale,
            locale_source=locale_source,
            birth_day=int(raw_birth_day) if raw_birth_day is not None else None,
            birth_month=int(raw_birth_month) if raw_birth_month is not None else None,
            birth_year=int(raw_birth_year) if raw_birth_year is not None else None,
            birthdate_source=birthdate_source,
        )

    async def upsert_user(self, user: TelegramUser, *, channel: str = "miniapp") -> UserRecord:
        """Insert new user or update mutable attributes while preserving explicit locale."""
        await self._ensure_initialized()
        now_iso = datetime.now(UTC).isoformat()
        resolved_locale = resolve_telegram_locale(user.language_code)
        normalized_raw = (user.language_code or "").strip().lower()
        fallback_used = not normalized_raw.startswith(("ru", "en"))
        stmt = text(
            f"""
            INSERT INTO users (
                telegram_id, first_name, last_name, username,
                language_code, locale, locale_source, is_premium, created_at, updated_at
            ) VALUES (
                :telegram_id, :first_name, :last_name, :username,
                :language_code, :locale, 'auto', :is_premium, :created_at, :updated_at
            )
            ON CONFLICT(telegram_id) DO UPDATE SET
                first_name = excluded.first_name,
                last_name = excluded.last_name,
                username = excluded.username,
                language_code = excluded.language_code,
                locale = CASE
                    WHEN users.locale_source = 'explicit' THEN users.locale
                    ELSE excluded.locale
                END,
                locale_source = users.locale_source,
                is_premium = excluded.is_premium,
                updated_at = excluded.updated_at
            RETURNING {_USER_COLUMNS}
            """
        )
        params = {
            "telegram_id": user.id,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "username": user.username,
            "language_code": user.language_code,
            "locale": resolved_locale,
            "is_premium": 1 if user.is_premium else 0,
            "created_at": now_iso,
            "updated_at": now_iso,
        }
        async with self.engine.begin() as conn:
            existing = (
                await conn.execute(
                    text("SELECT id, locale FROM users WHERE telegram_id = :telegram_id"),
                    {"telegram_id": user.id},
                )
            ).first()
            is_new = existing is None
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
            changed = is_new or (existing is not None and existing.locale != record.locale)
            logger.debug(
                "User locale resolved on %s: locale=%s source=%s",
                channel,
                record.locale,
                record.locale_source,
                extra={
                    "event": "locale_auto_resolved",
                    "channel": channel,
                    "resolved_locale": record.locale,
                    "locale_source": record.locale_source,
                    "changed": changed,
                    "fallback_used": fallback_used,
                },
            )
            return record

    async def upsert_from_bot(self, tg_user: Any) -> UserRecord:
        """Upsert a user profile from an aiogram User object."""
        from wishenka.auth.models import TelegramUser

        telegram_user = TelegramUser(
            id=int(tg_user.id),
            first_name=str(tg_user.first_name or "User"),
            last_name=getattr(tg_user, "last_name", None),
            username=getattr(tg_user, "username", None),
            language_code=getattr(tg_user, "language_code", None),
            is_premium=bool(getattr(tg_user, "is_premium", False)),
        )
        return await self.upsert_user(telegram_user, channel="bot")

    async def set_locale(self, telegram_id: int, locale: SupportedLocale) -> UserRecord:
        """Persist an explicit user locale choice that overrides client language auto-detection."""
        await self._ensure_initialized()
        validated = validate_locale(locale)
        now_iso = datetime.now(UTC).isoformat()
        async with self.engine.begin() as conn:
            existing = (
                await conn.execute(
                    text(
                        "SELECT id, locale, locale_source FROM users "
                        "WHERE telegram_id = :telegram_id"
                    ),
                    {"telegram_id": telegram_id},
                )
            ).first()
            if existing is None:
                raise UserNotFoundError(f"User with telegram_id {telegram_id} not found")
            result = await conn.execute(
                text(
                    f"""
                    UPDATE users
                    SET locale = :locale,
                        locale_source = 'explicit',
                        updated_at = :updated_at
                    WHERE telegram_id = :telegram_id
                    RETURNING {_USER_COLUMNS}
                    """
                ),
                {
                    "locale": validated,
                    "updated_at": now_iso,
                    "telegram_id": telegram_id,
                },
            )
            record = self._row_to_record(result.one())
            logger.info(
                "User locale explicitly updated to %s",
                record.locale,
                extra={
                    "event": "locale_explicit_updated",
                    "user_id": record.id,
                    "previous_locale": str(existing.locale),
                    "new_locale": record.locale,
                    "previous_source": str(existing.locale_source),
                    "locale_source": record.locale_source,
                },
            )
            return record

    set_explicit_locale = set_locale

    async def set_birthdate(
        self,
        telegram_id: int,
        *,
        day: int,
        month: int,
        year: int | None = None,
    ) -> UserRecord:
        """Persist an explicit user birthdate that is never overwritten by Telegram sync."""
        await self._ensure_initialized()
        valid_day, valid_month, valid_year = validate_birthdate(day, month, year)
        now_iso = datetime.now(UTC).isoformat()
        async with self.engine.begin() as conn:
            result = await conn.execute(
                text(
                    f"""
                    UPDATE users
                    SET birth_day = :birth_day,
                        birth_month = :birth_month,
                        birth_year = :birth_year,
                        birthdate_source = 'explicit',
                        updated_at = :updated_at
                    WHERE telegram_id = :telegram_id
                    RETURNING {_USER_COLUMNS}
                    """
                ),
                {
                    "birth_day": valid_day,
                    "birth_month": valid_month,
                    "birth_year": valid_year,
                    "updated_at": now_iso,
                    "telegram_id": telegram_id,
                },
            )
            row = result.first()
            if row is None:
                raise UserNotFoundError(f"User with telegram_id {telegram_id} not found")
            record = self._row_to_record(row)
            logger.info(
                "User birthdate explicitly updated",
                extra={
                    "event": "birthdate_explicit_updated",
                    "user_id": record.id,
                    "has_year": record.birth_year is not None,
                    "birthdate_source": record.birthdate_source,
                },
            )
            return record

    async def clear_birthdate(self, telegram_id: int) -> UserRecord:
        """Explicitly clear user birthdate while marking source='explicit'."""
        await self._ensure_initialized()
        now_iso = datetime.now(UTC).isoformat()
        async with self.engine.begin() as conn:
            result = await conn.execute(
                text(
                    f"""
                    UPDATE users
                    SET birth_day = NULL,
                        birth_month = NULL,
                        birth_year = NULL,
                        birthdate_source = 'explicit',
                        updated_at = :updated_at
                    WHERE telegram_id = :telegram_id
                    RETURNING {_USER_COLUMNS}
                    """
                ),
                {"updated_at": now_iso, "telegram_id": telegram_id},
            )
            row = result.first()
            if row is None:
                raise UserNotFoundError(f"User with telegram_id {telegram_id} not found")
            record = self._row_to_record(row)
            logger.info(
                "User birthdate explicitly cleared",
                extra={
                    "event": "birthdate_explicit_cleared",
                    "user_id": record.id,
                    "birthdate_source": record.birthdate_source,
                },
            )
            return record

    async def get_by_telegram_id(self, telegram_id: int) -> UserRecord | None:
        """Find user by numeric Telegram ID."""
        await self._ensure_initialized()
        stmt = text(f"SELECT {_USER_COLUMNS} FROM users WHERE telegram_id = :telegram_id")
        async with self.engine.connect() as conn:
            result = await conn.execute(stmt, {"telegram_id": telegram_id})
            row = result.first()
            return self._row_to_record(row) if row is not None else None

    async def get_by_id(self, user_id: int) -> UserRecord | None:
        """Find user by internal database primary key."""
        await self._ensure_initialized()
        stmt = text(f"SELECT {_USER_COLUMNS} FROM users WHERE id = :id")
        async with self.engine.connect() as conn:
            result = await conn.execute(stmt, {"id": user_id})
            row = result.first()
            return self._row_to_record(row) if row is not None else None

    async def dispose(self) -> None:
        """Cleanly close connection pools."""
        await self.engine.dispose()
