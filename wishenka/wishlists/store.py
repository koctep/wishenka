"""Transactional storage for the wishlist domain service."""

import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import fields
from datetime import datetime
from pathlib import Path
from typing import Any, TypeVar

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from wishenka.items.models import ItemPriority
from wishenka.wishlists.models import (
    Reservation,
    ReservationStatus,
    WishItem,
    Wishlist,
    WishlistMember,
    WishlistRole,
    WishlistStatus,
)
from wishenka.wishlists.service import WishlistService

T = TypeVar("T")

# aiosqlite DEBUG logs include SQL bound parameters, including capabilities.
logging.getLogger("aiosqlite").setLevel(logging.WARNING)


def _dump(obj: Any, excluded: set[str]) -> str:
    values = {f.name: getattr(obj, f.name) for f in fields(obj) if f.name not in excluded}
    return json.dumps(values, default=lambda v: v.isoformat(), ensure_ascii=False)


def _load[T](model: type[T], payload: str) -> T:
    values = json.loads(payload)
    for name in ("created_at", "updated_at", "joined_at", "event_date", "invite_token_expires_at"):
        if values.get(name):
            values[name] = datetime.fromisoformat(values[name])
    enum_fields = {
        (Wishlist, "status"): WishlistStatus,
        (WishlistMember, "role"): WishlistRole,
        (WishItem, "priority"): ItemPriority,
        (Reservation, "status"): ReservationStatus,
    }
    for (cls, name), enum_type in enum_fields.items():
        if model is cls and name in values:
            values[name] = enum_type(values[name])
    return model(**values)


class TokenCollision(Exception):
    """A generated capability was previously used for either access purpose."""


class WishlistStore:
    """Load domain objects afresh inside a SQLite transaction for every operation."""

    def __init__(self, database_url: str) -> None:
        prefix = "sqlite+aiosqlite:///"
        if not database_url.startswith(prefix):
            raise ValueError("Wishlist storage requires SQLite")
        path = database_url[len(prefix) :]
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_async_engine(
            database_url, connect_args={"timeout": 5}, hide_parameters=True
        )

    async def initialize(self) -> None:
        """Create the schema without modifying existing records."""
        try:
            await self._initialize()
        except SQLAlchemyError:
            pass
        else:
            return
        raise RuntimeError("Unable to initialize wishlist storage")

    async def _initialize(self) -> None:
        async with self.engine.begin() as conn:
            await conn.exec_driver_sql("PRAGMA journal_mode=WAL")
            for statement in (
                "CREATE TABLE IF NOT EXISTS wl_lists "
                "(id INTEGER PRIMARY KEY, payload TEXT NOT NULL)",
                "CREATE TABLE IF NOT EXISTS wl_members (id INTEGER PRIMARY KEY, "
                "wishlist_id INTEGER NOT NULL REFERENCES wl_lists(id), payload TEXT NOT NULL)",
                "CREATE TABLE IF NOT EXISTS wl_items (id INTEGER PRIMARY KEY, "
                "wishlist_id INTEGER NOT NULL REFERENCES wl_lists(id), payload TEXT NOT NULL)",
                "CREATE TABLE IF NOT EXISTS wl_reservations (id INTEGER PRIMARY KEY, "
                "item_id INTEGER NOT NULL REFERENCES wl_items(id), payload TEXT NOT NULL)",
                "CREATE TABLE IF NOT EXISTS wl_tokens (token TEXT PRIMARY KEY, "
                "wishlist_id INTEGER NOT NULL, active INTEGER NOT NULL)",
                "CREATE TABLE IF NOT EXISTS wl_invite_tokens (token TEXT PRIMARY KEY)",
                "CREATE TABLE IF NOT EXISTS wl_counters "
                "(name TEXT PRIMARY KEY, value INTEGER NOT NULL)",
                "CREATE UNIQUE INDEX IF NOT EXISTS wl_member_identity "
                "ON wl_members(wishlist_id, json_extract(payload, '$.user_id'))",
            ):
                await conn.exec_driver_sql(statement)

    async def _read(self, conn: AsyncConnection) -> WishlistService:
        service = WishlistService()
        for table, model in (
            ("wl_lists", Wishlist),
            ("wl_members", WishlistMember),
            ("wl_items", WishItem),
            ("wl_reservations", Reservation),
        ):
            rows = (await conn.execute(text(f"SELECT payload FROM {table}"))).scalars().all()
            for payload in rows:
                obj = _load(model, payload)
                if isinstance(obj, Wishlist):
                    service._wishlists[obj.id] = obj
                elif isinstance(obj, WishlistMember):
                    obj.wishlist = service._wishlists[obj.wishlist_id]
                    obj.wishlist.members.append(obj)
                elif isinstance(obj, WishItem):
                    service._items[obj.id] = obj
                    obj.wishlist = service._wishlists[obj.wishlist_id]
                    obj.wishlist.items.append(obj)
                elif isinstance(obj, Reservation):
                    service._reservations[obj.id] = obj
                    obj.wish_item = service._items[obj.wish_item_id]
                    obj.wish_item.reservations.append(obj)
        counters: dict[str, int] = dict(
            (await conn.execute(text("SELECT name, value FROM wl_counters"))).all()
        )
        for name in ("wishlist", "member", "item", "reservation"):
            setattr(service, f"_next_{name}_id", counters.get(name, 0))
        return service

    async def _write(self, conn: AsyncConnection, service: WishlistService) -> None:
        for table in ("wl_reservations", "wl_items", "wl_members", "wl_lists"):
            await conn.execute(text(f"DELETE FROM {table}"))
        for wl in service._wishlists.values():
            await conn.execute(
                text("INSERT INTO wl_lists VALUES (:id, :payload)"),
                {"id": wl.id, "payload": _dump(wl, {"members", "items"})},
            )
            for member in wl.members:
                await conn.execute(
                    text("INSERT INTO wl_members VALUES (:id, :parent, :payload)"),
                    {"id": member.id, "parent": wl.id, "payload": _dump(member, {"wishlist"})},
                )
            for item in wl.items:
                await conn.execute(
                    text("INSERT INTO wl_items VALUES (:id, :parent, :payload)"),
                    {
                        "id": item.id,
                        "parent": wl.id,
                        "payload": _dump(item, {"wishlist", "reservations"}),
                    },
                )
                for reservation in item.reservations:
                    await conn.execute(
                        text("INSERT INTO wl_reservations VALUES (:id, :parent, :payload)"),
                        {
                            "id": reservation.id,
                            "parent": item.id,
                            "payload": _dump(reservation, {"wish_item"}),
                        },
                    )
        for name in ("wishlist", "member", "item", "reservation"):
            await conn.execute(
                text("INSERT OR REPLACE INTO wl_counters VALUES (:name, :value)"),
                {"name": name, "value": getattr(service, f"_next_{name}_id")},
            )

    async def execute(self, operation: Callable[[WishlistService], Awaitable[T]]) -> T:
        """Serialize reads and writes across workers and commit the whole aggregate atomically."""
        for attempt in range(5):
            try:
                return await self._execute_once(operation)
            except TokenCollision:
                if attempt < 4:
                    continue
                message = "Unable to allocate a unique capability"
            except IntegrityError as exc:
                if not any(
                    name in str(exc.orig) for name in ("wl_tokens.token", "wl_invite_tokens.token")
                ):
                    message = "Wishlist storage operation failed"
                elif attempt < 4:
                    continue
                else:
                    message = "Unable to allocate a unique public token"
            except SQLAlchemyError:
                message = "Wishlist storage operation failed"
            # Raise outside the handler: middleware may otherwise re-chain __context__ even
            # when exception chaining was explicitly suppressed with ``from None``.
            raise RuntimeError(message)
        raise RuntimeError("Unable to allocate a unique public token")

    async def _execute_once(self, operation: Callable[[WishlistService], Awaitable[T]]) -> T:
        async with self.engine.connect() as conn:
            await conn.exec_driver_sql("PRAGMA foreign_keys=ON")
            await conn.exec_driver_sql("PRAGMA busy_timeout=5000")
            await conn.commit()
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                service = await self._read(conn)
                previous = {wl.id: wl.public_token for wl in service._wishlists.values()}
                prior_invites = {wl.id: wl.invite_token for wl in service._wishlists.values()}
                for token in prior_invites.values():
                    await conn.execute(
                        text("INSERT OR IGNORE INTO wl_invite_tokens VALUES (:token)"),
                        {"token": token},
                    )
                result = await operation(service)
                for wl in service._wishlists.values():
                    if prior_invites.get(wl.id) != wl.invite_token:
                        matching_public = await conn.scalar(
                            text("SELECT 1 FROM wl_tokens WHERE token=:token"),
                            {"token": wl.invite_token},
                        )
                        if matching_public or wl.invite_token == wl.public_token:
                            raise TokenCollision
                        await conn.execute(
                            text("INSERT INTO wl_invite_tokens VALUES (:token)"),
                            {"token": wl.invite_token},
                        )
                    old = previous.get(wl.id)
                    if old != wl.public_token:
                        matching_invite = await conn.scalar(
                            text("SELECT 1 FROM wl_invite_tokens WHERE token=:token"),
                            {"token": wl.public_token},
                        )
                        if matching_invite:
                            raise TokenCollision
                        await conn.execute(
                            text("UPDATE wl_tokens SET active=0 WHERE wishlist_id=:id"),
                            {"id": wl.id},
                        )
                        await conn.execute(
                            text("INSERT INTO wl_tokens VALUES (:token, :id, 1)"),
                            {"token": wl.public_token, "id": wl.id},
                        )
                await self._write(conn, service)
                await conn.commit()
                return result
            except BaseException:
                await conn.rollback()
                raise
