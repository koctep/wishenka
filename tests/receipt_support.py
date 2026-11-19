"""Shared helpers for the WISHENKA-23 gift receipt tests.

Production symbols that do not exist yet are reached through ``new_symbol`` or ``attr_of``
inside the test body, so a missing component is one red test with a readable reason and never
a collection error of the whole suite.
"""

from __future__ import annotations

import importlib
import sqlite3
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from wishenka.auth.models import AuthenticatedUser
from wishenka.auth.session import SessionTokenService
from wishenka.config import Settings
from wishenka.web.app import create_app
from wishenka.wishlists.models import WishItem
from wishenka.wishlists.service import WishlistService
from wishenka.wishlists.store import WishlistStore

SQLITE_PREFIX = "sqlite+aiosqlite:///"
OWNER_ID = 101
CO_AUTHOR_ID = 111
GIFTER_ID = 202
OTHER_GIFTER_ID = 303
THIRD_GIFTER_ID = 404
STRANGER_ID = 505
TEST_BOT_TOKEN = "123456789:ABCdefGHIjklMNOpqrsTUVwxyz1234567"
RECEIPT_COLUMNS = {"id", "wish_item_id", "quantity", "received_at", "is_approximate"}
_MISSING = object()

AppEnv = tuple[TestClient, SessionTokenService, FastAPI]


def make_user(telegram_id: int, first_name: str = "User") -> AuthenticatedUser:
    """Create a bearer test user."""
    return AuthenticatedUser(
        telegram_id=telegram_id,
        first_name=first_name,
        auth_method="session_token",
    )


OWNER = make_user(OWNER_ID, "Alice")
CO_AUTHOR = make_user(CO_AUTHOR_ID, "Carl")
GIFTER = make_user(GIFTER_ID, "Greta")
OTHER_GIFTER = make_user(OTHER_GIFTER_ID, "Oleg")
THIRD_GIFTER = make_user(THIRD_GIFTER_ID, "Tina")
STRANGER = make_user(STRANGER_ID, "Sven")


def new_symbol(module: str, name: str) -> Any:
    """Import an intended new production symbol or fail with a readable assertion."""
    try:
        loaded = importlib.import_module(module)
    except ImportError as exc:
        raise AssertionError(f"{module} does not exist yet ({exc})") from None
    symbol = getattr(loaded, name, _MISSING)
    assert symbol is not _MISSING, f"{module}.{name} does not exist yet"
    return symbol


def exc_class(name: str) -> type[Exception]:
    """Return a refusal class that the design adds to ``wishlists.exceptions``."""
    symbol = new_symbol("wishenka.wishlists.exceptions", name)
    assert isinstance(symbol, type) and issubclass(symbol, Exception)
    return symbol


def attr_of(obj: object, name: str) -> Any:
    """Read an attribute the design adds, failing with a readable assertion when absent."""
    value = getattr(obj, name, _MISSING)
    assert value is not _MISSING, f"{type(obj).__name__}.{name} does not exist yet"
    return value


def receipts_of(item: WishItem) -> list[Any]:
    """Return the receipt records of a wish."""
    return list(attr_of(item, "receipts"))


def item_of(service: WishlistService, item_id: int) -> WishItem:
    """Return the live wish of an in-memory service."""
    return service._items[item_id]


async def seed_wish(
    service: WishlistService,
    *,
    quantity: int | None = None,
    title: str = "Kettle",
    list_title: str = "Alice Birthday",
    recipient_name: str | None = None,
) -> tuple[int, int]:
    """Create the owner's list and one wish. ``quantity=None`` keeps the default of one unit."""
    wishlist = await service.create_wishlist(owner=OWNER, title=list_title)
    if quantity is None:
        item = await service.add_wish_item(
            wishlist_id=wishlist.id,
            actor=OWNER,
            title=title,
            recipient_name=recipient_name,
        )
    else:
        item = await service.add_wish_item(
            wishlist_id=wishlist.id,
            actor=OWNER,
            title=title,
            quantity=quantity,
            recipient_name=recipient_name,
        )
    return wishlist.id, item.id


def db_path_of(app: FastAPI) -> str:
    """Return the SQLite file of an app created by ``app_env``."""
    return str(app.state.settings.database_url).removeprefix(SQLITE_PREFIX)


def sql_rows(db: str | Path, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    """Run a read query and return rows as dictionaries."""
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute(sql, params).fetchall()]


def sql_exec(db: str | Path, sql: str, params: tuple[Any, ...] = ()) -> None:
    """Run one write statement (tests only)."""
    with sqlite3.connect(db) as conn:
        conn.execute(sql, params)


def seed_users(db: str | Path, *user_ids: int) -> None:
    """Ensure ``users`` rows exist for test user IDs when FK constraints are enforced."""
    now = "2026-01-01T00:00:00+00:00"
    with sqlite3.connect(db) as conn:
        for user_id in user_ids:
            conn.execute(
                "INSERT OR IGNORE INTO users(telegram_id, first_name, created_at, updated_at) "
                "VALUES (?, ?, ?, ?)",
                (user_id, f"User{user_id}", now, now),
            )
        conn.commit()


def table_names(db: str | Path) -> set[str]:
    """Return the names of all tables."""
    rows = sql_rows(db, "SELECT name FROM sqlite_master WHERE type = 'table'")
    return {str(row["name"]) for row in rows}


def require_table(db: str | Path, name: str) -> None:
    """Fail with a readable assertion when a table the design adds is absent."""
    assert name in table_names(db), f"table {name} does not exist yet"


def table_rows(db: str | Path, name: str, order: str = "id") -> list[dict[str, Any]]:
    """Return all rows of a table the design adds (readable failure when absent)."""
    require_table(db, name)
    return sql_rows(db, f"SELECT * FROM {name} ORDER BY {order}")


def outbox_rows(db: str | Path) -> list[dict[str, Any]]:
    """Return the notice queue rows."""
    return table_rows(db, "notification_outbox")


def receipt_rows(db: str | Path) -> list[dict[str, Any]]:
    """Return the receipt history rows."""
    return table_rows(db, "wl_receipts")


def item_received(db: str | Path, item_id: int) -> int:
    """Return the stored received counter of a wish."""
    rows = sql_rows(db, "SELECT received_quantity FROM wl_items WHERE id = ?", (item_id,))
    return int(rows[0]["received_quantity"])


@contextmanager
def app_env(tmp_path: Path, name: str = "receipt.db", **overrides: Any) -> Iterator[AppEnv]:
    """Open ``create_app`` on an isolated SQLite file with bearer sessions."""
    notice_sender = overrides.pop("notice_sender", None)
    settings = Settings(
        database_url=f"{SQLITE_PREFIX}{tmp_path / name}",
        secret_key="gift-receipt-test-secret",
        **overrides,
    )
    factory: Any = create_app  # ``notice_sender`` is a parameter the design adds
    app: FastAPI = (
        factory(settings)
        if notice_sender is None
        else factory(settings, notice_sender=notice_sender)
    )
    sessions = SessionTokenService(settings.secret_key)
    with TestClient(app) as client:
        yield client, sessions, app


def bearer(sessions: SessionTokenService, user_id: int, name: str = "User") -> dict[str, str]:
    """Build a bearer Authorization header."""
    return {"Authorization": f"Bearer {sessions.create_token(user_id, name)}"}


@asynccontextmanager
async def open_store(path: Path) -> AsyncIterator[WishlistStore]:
    """Initialise a migrated store on a file; engines are disposed on exit."""
    store = WishlistStore(f"{SQLITE_PREFIX}{path}")
    await store.initialize()
    try:
        yield store
    finally:
        await store.engine.dispose()
