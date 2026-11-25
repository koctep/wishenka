"""Async transactional SQLite storage for user entities."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar

from sqlalchemy import Row, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from wishenka.i18n.locale import (
    LocaleSource,
    SupportedLocale,
    resolve_telegram_locale,
    validate_locale,
)
from wishenka.sqlite import configure_immediate_transactions, is_sqlite_busy
from wishenka.users.models import BirthdateSource, UserRecord
from wishenka.wishlists.migrations import upgrade_to_head

if TYPE_CHECKING:
    from wishenka.auth.models import TelegramUser

T = TypeVar("T")
logger = logging.getLogger("wishenka.users")

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


class UserStoreBusyError(RuntimeError):
    """Retryable error raised when a user write transaction exceeds SQLite busy_timeout."""


class UserStore:
    """Async transactional SQLite storage for user entities."""

    def __init__(self, database_url: str, *, engine: AsyncEngine | None = None) -> None:
        self.database_url = database_url
        self._external_engine = engine is not None
        if engine is not None:
            self.engine: AsyncEngine = engine
        else:
            prefix = "sqlite+aiosqlite:///"
            if not database_url.startswith(prefix):
                raise ValueError("UserStore requires SQLite database URL")
            path = database_url[len(prefix) :]
            if path != ":memory:":
                Path(path).parent.mkdir(parents=True, exist_ok=True)
            self.engine = create_async_engine(
                database_url,
                connect_args={"timeout": 5},
                hide_parameters=True,
            )
            configure_immediate_transactions(self.engine.sync_engine)
        self._initialized = False

    async def _immediate(
        self,
        work: Callable[[AsyncConnection], Awaitable[T]],
        *,
        operation: str,
    ) -> T:
        """Run work inside a BEGIN IMMEDIATE transaction and map SQLite busy errors."""
        async with self.engine.connect() as conn:
            try:
                await conn.begin()
                result = await work(conn)
                await conn.commit()
                return result
            except SQLAlchemyError as exc:
                if conn.in_transaction():
                    await conn.rollback()
                if is_sqlite_busy(exc):
                    logger.warning(
                        "User store operation rolled back because the database was busy",
                        extra={"event": "user_store_busy", "operation": operation},
                    )
                    raise UserStoreBusyError(
                        "User service is temporarily busy; please retry"
                    ) from exc
                logger.error(
                    "User store operation failed due to database error",
                    extra={"event": "user_store_error", "operation": operation},
                )
                raise RuntimeError("User storage operation failed") from exc
            except BaseException:
                if conn.in_transaction():
                    await conn.rollback()
                raise

    async def _read(self, work: Callable[[AsyncConnection], Awaitable[T]]) -> T:
        """Run work in a read-only deferred transaction without BEGIN IMMEDIATE."""
        async with self.engine.connect() as raw_conn:
            conn = await raw_conn.execution_options(read_only=True)
            try:
                await conn.begin()
                return await work(conn)
            finally:
                if conn.in_transaction():
                    await conn.rollback()

    async def initialize(self) -> None:
        """Delegate schema migrations to Alembic and configure WAL mode idempotently."""
        if not self._external_engine:
            async with self.engine.connect() as raw_conn:
                autocommit_conn = await raw_conn.execution_options(isolation_level="AUTOCOMMIT")
                try:
                    await autocommit_conn.exec_driver_sql("PRAGMA journal_mode=WAL")
                    await autocommit_conn.exec_driver_sql("PRAGMA synchronous=NORMAL")
                    await autocommit_conn.exec_driver_sql("PRAGMA busy_timeout=5000")
                except SQLAlchemyError as exc:
                    if is_sqlite_busy(exc):
                        logger.warning(
                            "User store initialization busy while configuring WAL mode",
                            extra={"event": "user_store_busy", "operation": "initialize"},
                        )
                        raise UserStoreBusyError(
                            "User service is temporarily busy; please retry"
                        ) from exc
                    logger.error(
                        "User store initialization failed due to database error",
                        extra={"event": "user_store_error", "operation": "initialize"},
                    )
                    raise RuntimeError("User storage operation failed") from exc

        await upgrade_to_head(self.database_url)
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

        async def _work(conn: AsyncConnection) -> tuple[UserRecord, bool, str | None]:
            existing = (
                await conn.execute(
                    text("SELECT id, locale FROM users WHERE telegram_id = :telegram_id"),
                    {"telegram_id": user.id},
                )
            ).first()
            is_new = existing is None
            existing_locale = str(existing.locale) if existing is not None else None
            result = await conn.execute(stmt, params)
            row = result.one()
            return self._row_to_record(row), is_new, existing_locale

        record, is_new, existing_locale = await self._immediate(_work, operation="upsert_user")
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
        changed = is_new or (existing_locale is not None and existing_locale != record.locale)
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

        async def _work(conn: AsyncConnection) -> tuple[UserRecord, str, str]:
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
            return (
                self._row_to_record(result.one()),
                str(existing.locale),
                str(existing.locale_source),
            )

        record, previous_locale, previous_source = await self._immediate(
            _work, operation="set_locale"
        )
        logger.info(
            "User locale explicitly updated to %s",
            record.locale,
            extra={
                "event": "locale_explicit_updated",
                "user_id": record.id,
                "previous_locale": previous_locale,
                "new_locale": record.locale,
                "previous_source": previous_source,
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

        async def _work(conn: AsyncConnection) -> UserRecord:
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
            return self._row_to_record(row)

        record = await self._immediate(_work, operation="set_birthdate")
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

        async def _work(conn: AsyncConnection) -> UserRecord:
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
            return self._row_to_record(row)

        record = await self._immediate(_work, operation="clear_birthdate")
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

        async def _work(conn: AsyncConnection) -> UserRecord | None:
            result = await conn.execute(stmt, {"telegram_id": telegram_id})
            row = result.first()
            return self._row_to_record(row) if row is not None else None

        return await self._read(_work)

    async def get_by_id(self, user_id: int) -> UserRecord | None:
        """Find user by internal database primary key."""
        await self._ensure_initialized()
        stmt = text(f"SELECT {_USER_COLUMNS} FROM users WHERE id = :id")

        async def _work(conn: AsyncConnection) -> UserRecord | None:
            result = await conn.execute(stmt, {"id": user_id})
            row = result.first()
            return self._row_to_record(row) if row is not None else None

        return await self._read(_work)

    async def dispose(self) -> None:
        """Cleanly close connection pools."""
        await self.engine.dispose()
