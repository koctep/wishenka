"""Red repro for WISHENKA-328: read locks and bot busy saves.

Desired behavior, which current call sites do not implement:

- The birthday list read and the active private-chat lookup open with plain
  ``BEGIN`` and do not emit ``BEGIN IMMEDIATE``.
- A ``SQLITE_BUSY`` / ``database is locked`` failure while recording the
  private chat, or while saving reservation confirmations, raises
  ``UserStoreBusyError``.
"""

from __future__ import annotations

import inspect
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from aiogram.filters import CommandObject
from aiogram.types import Message
from sqlalchemy import event, text
from starlette.requests import Request

from wishenka.bot.birthdays import create_birthday_router
from wishenka.bot.entry import create_router
from wishenka.bot.principal import ensure_private_bot_user
from wishenka.users.store import UserStore, UserStoreBusyError
from wishenka.web.routes.profile import _find_active_chat_id
from wishenka.wishlists.store import WishlistStore

pytestmark = pytest.mark.timeout(30)

_BUSY_MESSAGE = "User service is temporarily busy; please retry"


@dataclass
class _Seen:
    sql: str
    immediate: bool
    tx_id: int | None
    opener: str | None


class _StatementLog:
    """Record listener text from ``before_cursor_execute``.

    Named binds such as ``:owner`` and ``:uid`` are compiled to positional
    placeholders before this event, so queries are identified by table name.
    """

    def __init__(self) -> None:
        self.rows: list[_Seen] = []
        self._tx_seq = 0
        self._tx_id: int | None = None
        self._opener: str | None = None
        self._immediate = False

    def on_execute(
        self,
        _conn: Any,
        _cursor: Any,
        statement: str,
        _parameters: Any,
        _context: Any,
        _executemany: bool,
    ) -> None:
        sql = " ".join(str(statement).split())
        upper = sql.upper()
        if upper.startswith("BEGIN IMMEDIATE"):
            self._tx_seq += 1
            self._tx_id = self._tx_seq
            self._opener = "BEGIN IMMEDIATE"
            self._immediate = True
        elif upper == "BEGIN":
            self._tx_seq += 1
            self._tx_id = self._tx_seq
            self._opener = "BEGIN"
            self._immediate = False
        elif upper in {"COMMIT", "ROLLBACK"}:
            self._tx_id = None
            self._opener = None
            self._immediate = False
            return
        self.rows.append(_Seen(sql, self._immediate, self._tx_id, self._opener))


def _listen(engine: Any, log: _StatementLog) -> None:
    event.listen(engine.sync_engine, "before_cursor_execute", log.on_execute)


def _unlisten(engine: Any, log: _StatementLog) -> None:
    event.remove(engine.sync_engine, "before_cursor_execute", log.on_execute)


def _db_url(db_path: Path) -> str:
    return f"sqlite+aiosqlite:///{db_path}"


async def _open_stores(tmp_path: Path, name: str) -> tuple[Path, WishlistStore, UserStore]:
    db_path = tmp_path / name
    url = _db_url(db_path)
    store = WishlistStore(url)
    users = UserStore(url)
    await store.initialize()
    await users.initialize()
    return db_path, store, users


def _tg_user(user_id: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        first_name="Dana",
        last_name=None,
        username="dana",
        language_code="en",
        is_premium=False,
    )


def _private_message(user_id: int, text_value: str) -> Message:
    return Message.model_validate(
        {
            "message_id": 1,
            "date": 1700000000,
            "chat": {"id": user_id, "type": "private"},
            "from": {"id": user_id, "is_bot": False, "first_name": "Dana"},
            "text": text_value,
        }
    )


def _handler(router: Any, name: str) -> Any:
    for handler in router.message.handlers:
        callback = inspect.unwrap(handler.callback)
        if getattr(callback, "__name__", "") == name:
            return callback
    raise AssertionError(f"{name} is not registered on the router")


def _hold_immediate(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.execute("BEGIN IMMEDIATE")
    return conn


def _release(conn: sqlite3.Connection | None) -> None:
    if conn is None:
        return
    conn.rollback()
    conn.close()


def _rows_mentioning(log: _StatementLog, table: str, *, exclude: str | None = None) -> list[_Seen]:
    needle = table.upper()
    blocked = exclude.upper() if exclude is not None else None
    matched: list[_Seen] = []
    for row in log.rows:
        upper = row.sql.upper()
        if needle not in upper:
            continue
        if blocked is not None and blocked in upper:
            continue
        if "SELECT" not in upper:
            continue
        matched.append(row)
    return matched


def _assert_shared_plain_begin(log: _StatementLog, label: str, groups: list[list[_Seen]]) -> None:
    """The grouped reads share one plain ``BEGIN`` and no ``BEGIN IMMEDIATE``."""
    for group in groups:
        assert group, f"{label} did not execute every expected query"
    selects = [row for group in groups for row in group]
    tx_ids = {row.tx_id for row in selects}
    assert len(tx_ids) == 1, f"{label} used more than one transaction: {tx_ids}"
    opener = selects[0].opener
    assert opener == "BEGIN", (
        f"{label} ran under {opener!r}; expected BEGIN and not BEGIN IMMEDIATE"
    )
    tx_id = next(iter(tx_ids))
    tx_sql = [row.sql.upper() for row in log.rows if row.tx_id == tx_id]
    assert any(sql == "BEGIN" for sql in tx_sql), tx_sql
    assert all(not sql.startswith("BEGIN IMMEDIATE") for sql in tx_sql), tx_sql
    assert all(not row.immediate for row in selects)


async def _answer(self: Message, *_args: Any, **_kwargs: Any) -> None:
    return None


async def test_birthday_list_read_uses_plain_begin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The birthday_entries list read must use BEGIN, not BEGIN IMMEDIATE."""
    _db_path, store, users = await _open_stores(tmp_path, "birthdays.sqlite")
    monkeypatch.setattr(Message, "answer", _answer)
    user_id = 8801
    record = await users.upsert_from_bot(_tg_user(user_id))
    deps = SimpleNamespace(wishlist_store=store, user_store=users, clock=lambda: 1_700_000_000)
    birthdays = _handler(create_birthday_router(deps), "birthdays")
    log = _StatementLog()
    _listen(store.engine, log)
    try:
        await birthdays(
            _private_message(user_id, "/birthdays"),
            locale="en",
            user_record=record,
        )
        selects = _rows_mentioning(log, "birthday_entries")
        _assert_shared_plain_begin(log, "birthday list", [selects])
    finally:
        _unlisten(store.engine, log)
        await users.dispose()
        await store.dispose()


async def test_active_private_chat_lookup_uses_plain_begin(tmp_path: Path) -> None:
    """sqlite_master and bot_destinations share one BEGIN on either engine."""
    _db_path, store, users = await _open_stores(tmp_path, "chat-lookup.sqlite")
    telegram_id = 5150
    failures: list[str] = []
    cases = (
        (
            "wishlist engine",
            cast(
                Request,
                SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(wishlist_store=store))),
            ),
            store.engine,
        ),
        (
            "user engine",
            cast(Request, SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))),
            users.engine,
        ),
    )
    try:
        for label, request, engine in cases:
            log = _StatementLog()
            _listen(engine, log)
            try:
                found = await _find_active_chat_id(request, users, telegram_id)
            finally:
                _unlisten(engine, log)
            if found is not None:
                failures.append(f"{label}: missing row returned {found!r}")
                continue
            probes = _rows_mentioning(log, "sqlite_master")
            chats = _rows_mentioning(log, "bot_destinations", exclude="sqlite_master")
            try:
                _assert_shared_plain_begin(log, label, [probes, chats])
            except AssertionError as exc:
                failures.append(f"{label}: {exc}")
    finally:
        await users.dispose()
        await store.dispose()
    assert not failures, "; ".join(failures)


async def _destination(users: UserStore, user_id: int) -> tuple[int, int, int, int] | None:
    async with users.engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT user_id, chat_id, active, updated_at "
                    "FROM bot_destinations WHERE user_id = :id"
                ),
                {"id": user_id},
            )
        ).first()
    if row is None:
        return None
    return (int(row[0]), int(row[1]), int(row[2]), int(row[3]))


async def test_private_chat_save_busy_raises_user_store_busy_error(tmp_path: Path) -> None:
    """A locked private-chat save raises UserStoreBusyError and keeps the row."""
    db_path, store, users = await _open_stores(tmp_path, "private-chat.sqlite")
    ext: sqlite3.Connection | None = None
    user_id = 404
    try:
        record = await users.upsert_from_bot(_tg_user(user_id))
        deps = SimpleNamespace(user_store=users, clock=lambda: 1000)
        await ensure_private_bot_user(
            deps, _tg_user(user_id), user_id, user_record=record, now=1000
        )
        before = await _destination(users, user_id)
        assert before == (user_id, user_id, 1, 1000)

        ext = _hold_immediate(db_path)
        with pytest.raises(UserStoreBusyError, match=_BUSY_MESSAGE):
            await ensure_private_bot_user(
                deps,
                _tg_user(user_id),
                user_id,
                user_record=record,
                now=2000,
            )
        _release(ext)
        ext = None

        assert await _destination(users, user_id) == before
        persisted = await users.get_by_telegram_id(user_id)
        assert persisted is not None
        assert persisted.first_name == record.first_name
        assert persisted.telegram_id == record.telegram_id
    finally:
        _release(ext)
        await users.dispose()
        await store.dispose()


async def _confirmation_enabled(users: UserStore, user_id: int) -> int | None:
    async with users.engine.connect() as conn:
        value = await conn.scalar(
            text(
                "SELECT enabled FROM user_notification_settings "
                "WHERE user_id = :user AND event_type = 'reservation_changes'"
            ),
            {"user": user_id},
        )
    return None if value is None else int(value)


async def test_reservation_confirmations_busy_raises_user_store_busy_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A locked confirmation save raises UserStoreBusyError and keeps enabled."""
    db_path, store, users = await _open_stores(tmp_path, "confirmations.sqlite")
    monkeypatch.setattr(Message, "answer", _answer)
    ext: sqlite3.Connection | None = None
    user_id = 606
    try:
        record = await users.upsert_from_bot(_tg_user(user_id))
        async with users.engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO user_notification_settings"
                    "(user_id, event_type, enabled, updated_at) "
                    "VALUES (:user, 'reservation_changes', 1, CURRENT_TIMESTAMP)"
                ),
                {"user": user_id},
            )
        assert await _confirmation_enabled(users, user_id) == 1

        deps = SimpleNamespace(mini_app_url="https://example.test/app", user_store=users)
        confirm = _handler(create_router(deps), "reservation_confirmations")
        message = _private_message(user_id, "/reservation_confirmations off")
        command = CommandObject(prefix="/", command="reservation_confirmations", args="off")

        ext = _hold_immediate(db_path)
        with pytest.raises(UserStoreBusyError, match=_BUSY_MESSAGE):
            await confirm(message, command, locale="en", user_record=record)
        _release(ext)
        ext = None

        assert await _confirmation_enabled(users, user_id) == 1
    finally:
        _release(ext)
        await users.dispose()
        await store.dispose()
