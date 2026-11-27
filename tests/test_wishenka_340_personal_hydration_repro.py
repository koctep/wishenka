"""Personal openings read headers, not the full wishlist (WISHENKA-340).

Favorites, recently deleted lists, the bot list offer, and recording a visit
already start from the signed-in person. On current code each chosen list is
then opened through ``get_wishlist``, which reads ``wl_items`` and
``wl_reservations``. The screen and the permission check need list headers,
plus this person's membership only where the role or the permission uses it.

History listing and clearing are not part of this repro. Seeding stays
outside the SQL listener.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncConnection

from wishenka.auth.models import AuthenticatedUser, TelegramUser
from wishenka.bot.capture import _allowed
from wishenka.users.store import UserStore
from wishenka.wishlists.exceptions import WishlistNotFoundError
from wishenka.wishlists.models import Wishlist, WishlistRole, WishlistStatus
from wishenka.wishlists.policy import WishlistAccessPolicy
from wishenka.wishlists.repository import WishlistRepository
from wishenka.wishlists.retention import (
    DEFAULT_WISHLIST_RETENTION_DAYS,
    days_remaining,
    deletion_moment,
)
from wishenka.wishlists.service import WishlistService
from wishenka.wishlists.store import WishlistStore

pytestmark = pytest.mark.timeout(30)

_PERSON_ID = 34001
_HOST_ID = 34002
_OTHER_ID = 34003
_GHOST_ID = 34004
_NOW = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)
_IN_WINDOW_AT = _NOW - timedelta(days=3)
_EXPIRED_AT = _NOW - timedelta(days=31)
_COLLAB_BOOKMARK_AT = datetime(2026, 5, 1, tzinfo=UTC)
_SHARE_BOOKMARK_AT = datetime(2026, 5, 2, tzinfo=UTC)
_TABLES = ("wl_items", "wl_reservations", "wl_members")


@dataclass(frozen=True)
class _OpenedList:
    """Header fields a personal screen must keep for one seeded list."""

    wishlist_id: int
    title: str
    description: str
    occasion: str
    event_date: datetime


@dataclass(frozen=True)
class _World:
    """Lists the signed-in person can favorite, restore, offer, or record."""

    person: AuthenticatedUser
    ghost: AuthenticatedUser
    collab: _OpenedList
    share: _OpenedList
    own: _OpenedList
    bookmarked_deleted: _OpenedList
    in_window: _OpenedList
    expired: _OpenedList
    hidden: _OpenedList
    ghost_list: _OpenedList


def _user(telegram_id: int, first_name: str) -> AuthenticatedUser:
    return AuthenticatedUser(
        telegram_id=telegram_id,
        first_name=first_name,
        auth_method="session_token",
    )


def _compact(statement: str) -> str:
    return " ".join(statement.split())


def _ints_from_params(parameters: object) -> set[int]:
    found: set[int] = set()

    def walk(value: object) -> None:
        if isinstance(value, bool):
            return
        if isinstance(value, int):
            found.add(value)
            return
        if isinstance(value, dict):
            for item in value.values():
                walk(item)
            return
        if isinstance(value, (list, tuple)):
            for item in value:
                walk(item)

    walk(parameters)
    return found


def _table_reads(captured: list[tuple[str, object]]) -> dict[str, int]:
    counts = dict.fromkeys(_TABLES, 0)
    for statement, _parameters in captured:
        compact = _compact(statement)
        for table in _TABLES:
            if table in compact:
                counts[table] += 1
    return counts


def _named_reads(
    name: str,
    captured: list[tuple[str, object]],
    *,
    members: bool,
) -> dict[str, int]:
    counts = _table_reads(captured)
    named = {
        f"{name}_wl_items": counts["wl_items"],
        f"{name}_wl_reservations": counts["wl_reservations"],
    }
    if members:
        named[f"{name}_wl_members"] = counts["wl_members"]
    return named


def _saw_user_exists(captured: list[tuple[str, object]], user_id: int) -> bool:
    for statement, parameters in captured:
        compact = _compact(statement)
        if "FROM users" in compact and user_id in _ints_from_params(parameters):
            return True
    return False


def _favorite_card(user: AuthenticatedUser, wishlist: Wishlist) -> tuple[object, ...]:
    ctx = WishlistAccessPolicy.resolve_context(user, wishlist)
    role = ctx.role.value if ctx.role else "favorite"
    return (
        wishlist.id,
        wishlist.title,
        wishlist.description,
        wishlist.event_title,
        wishlist.event_date,
        wishlist.status,
        role,
    )


def _expected_card(spec: _OpenedList, role: str) -> tuple[object, ...]:
    return (
        spec.wishlist_id,
        spec.title,
        spec.description,
        spec.occasion,
        spec.event_date,
        WishlistStatus.ACTIVE,
        role,
    )


@contextmanager
def _capture_sql(store: WishlistStore) -> Iterator[list[tuple[str, object]]]:
    """Record compiled statements on the wishlist engine only."""
    captured: list[tuple[str, object]] = []

    def capture(
        _conn: object,
        _cursor: object,
        statement: str,
        parameters: object,
        _context: object,
        _executemany: object,
    ) -> None:
        captured.append((statement, parameters))

    event.listen(store.engine.sync_engine, "before_cursor_execute", capture)
    try:
        yield captured
    finally:
        event.remove(store.engine.sync_engine, "before_cursor_execute", capture)


async def _open_stores(tmp_path: Path) -> tuple[WishlistStore, UserStore]:
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'wishenka_340_personal_hydration.db'}"
    store = WishlistStore(db_url)
    await store.initialize()
    return store, UserStore(db_url)


async def _sql(
    store: WishlistStore,
    statement: str,
    parameters: dict[str, object],
) -> None:
    async def work(conn: AsyncConnection) -> None:
        await conn.execute(text(statement), parameters)

    await store.transaction(work)


async def _scalar(
    store: WishlistStore,
    statement: str,
    parameters: dict[str, object],
) -> object:
    async def read(conn: AsyncConnection) -> object:
        result = await conn.execute(text(statement), parameters)
        return result.scalar_one_or_none()

    return await store.execute_read(read)


async def _id_set(
    store: WishlistStore,
    statement: str,
    parameters: dict[str, object],
) -> set[int]:
    async def read(conn: AsyncConnection) -> set[int]:
        rows = (await conn.execute(text(statement), parameters)).all()
        return {int(row[0]) for row in rows}

    return await store.execute_read(read)


async def _create(
    service: WishlistService,
    owner: AuthenticatedUser,
    title: str,
    day: int,
) -> _OpenedList:
    description = f"{title} description"
    occasion = f"{title} occasion"
    event_date = datetime(2026, 8, day, tzinfo=UTC)
    wishlist = await service.create_wishlist(
        owner=owner,
        title=title,
        description=description,
        event_title=occasion,
        event_date=event_date,
    )
    return _OpenedList(wishlist.id, title, description, occasion, event_date)


async def _seed(store: WishlistStore, users: UserStore) -> _World:
    await users.upsert_user(TelegramUser(id=_PERSON_ID, first_name="Person"))
    await users.upsert_user(TelegramUser(id=_HOST_ID, first_name="Host"))
    await users.upsert_user(TelegramUser(id=_OTHER_ID, first_name="Other"))
    person = _user(_PERSON_ID, "Person")
    host = _user(_HOST_ID, "Host")
    other = _user(_OTHER_ID, "Other")
    ghost = _user(_GHOST_ID, "Ghost")
    service = WishlistService(store=store)

    collab = await _create(service, host, "Collab", 1)
    await service.add_member(collab.wishlist_id, host, person.telegram_id, WishlistRole.MEMBER)
    collab_item = await service.add_wish_item(collab.wishlist_id, host, title="Collab Wish")
    await service.create_reservation(item_id=collab_item.id, user=other, quantity=1)
    await service.add_favorite(person, collab.wishlist_id)

    share = await _create(service, other, "Share", 2)
    share_wl = await service.get_wishlist_by_id(share.wishlist_id)
    await service.get_wishlist_by_public_token(share_wl.public_token, current_user=person)
    await service.add_wish_item(share.wishlist_id, other, title="Share Wish")
    await service.add_favorite(person, share.wishlist_id)

    own = await _create(service, person, "Own", 3)
    await service.add_wish_item(own.wishlist_id, person, title="Own Wish")

    bookmarked_deleted = await _create(service, host, "Bookmarked Deleted", 4)
    await service.add_member(
        bookmarked_deleted.wishlist_id, host, person.telegram_id, WishlistRole.MEMBER
    )
    await service.add_favorite(person, bookmarked_deleted.wishlist_id)
    await service.delete_wishlist(bookmarked_deleted.wishlist_id, host)

    in_window = await _create(service, person, "In Window", 5)
    await service.add_wish_item(in_window.wishlist_id, person, title="In Window Wish")
    await service.delete_wishlist(in_window.wishlist_id, person)

    expired = await _create(service, person, "Expired", 6)
    await service.add_wish_item(expired.wishlist_id, person, title="Expired Wish")
    await service.delete_wishlist(expired.wishlist_id, person)

    hidden = await _create(service, other, "Hidden", 7)
    await service.add_wish_item(hidden.wishlist_id, other, title="Hidden Wish")

    ghost_list = await _create(service, ghost, "Ghost", 8)
    await service.add_wish_item(ghost_list.wishlist_id, ghost, title="Ghost Wish")

    await _sql(
        store,
        "UPDATE wl_favorites SET created_at = :ts WHERE user_id = :uid AND wishlist_id = :wid",
        {"ts": _COLLAB_BOOKMARK_AT.isoformat(), "uid": _PERSON_ID, "wid": collab.wishlist_id},
    )
    await _sql(
        store,
        "UPDATE wl_favorites SET created_at = :ts WHERE user_id = :uid AND wishlist_id = :wid",
        {"ts": _SHARE_BOOKMARK_AT.isoformat(), "uid": _PERSON_ID, "wid": share.wishlist_id},
    )
    await _sql(
        store,
        "UPDATE wl_lists SET updated_at = :ts WHERE id = :id",
        {"ts": _IN_WINDOW_AT.isoformat(), "id": in_window.wishlist_id},
    )
    await _sql(
        store,
        "UPDATE wl_lists SET updated_at = :ts WHERE id = :id",
        {"ts": _EXPIRED_AT.isoformat(), "id": expired.wishlist_id},
    )
    return _World(
        person=person,
        ghost=ghost,
        collab=collab,
        share=share,
        own=own,
        bookmarked_deleted=bookmarked_deleted,
        in_window=in_window,
        expired=expired,
        hidden=hidden,
        ghost_list=ghost_list,
    )


async def _assert_seed(store: WishlistStore, world: _World) -> None:
    """The rows that make a full-list read visible are present before the calls."""
    person_id = world.person.telegram_id
    favorites = await _id_set(
        store,
        "SELECT wishlist_id FROM wl_favorites WHERE user_id = :uid",
        {"uid": person_id},
    )
    assert favorites == {
        world.collab.wishlist_id,
        world.share.wishlist_id,
        world.bookmarked_deleted.wishlist_id,
    }
    wished = (
        world.collab,
        world.share,
        world.own,
        world.in_window,
        world.expired,
        world.hidden,
        world.ghost_list,
    )
    for spec in wished:
        count = await _scalar(
            store,
            "SELECT COUNT(*) FROM wl_items WHERE wishlist_id = :id",
            {"id": spec.wishlist_id},
        )
        assert count == 1
    reservations = await _scalar(
        store,
        "SELECT COUNT(*) FROM wl_reservations r "
        "JOIN wl_items i ON i.id = r.wish_item_id WHERE i.wishlist_id = :id",
        {"id": world.collab.wishlist_id},
    )
    assert reservations == 1
    assert (
        await _scalar(
            store,
            "SELECT 1 FROM users WHERE telegram_id = :uid",
            {"uid": world.ghost.telegram_id},
        )
        is None
    )
    assert (
        await _scalar(
            store,
            "SELECT status FROM wl_lists WHERE id = :id",
            {"id": world.ghost_list.wishlist_id},
        )
        == "active"
    )


@pytest.mark.asyncio
async def test_personal_openings_load_headers_without_full_lists(tmp_path: Path) -> None:
    """Chosen lists keep their screen fields and do not open wishes or reservations."""
    store, users = await _open_stores(tmp_path)
    try:
        world = await _seed(store, users)
        await _assert_seed(store, world)
        service = WishlistService(store=store)
        person = world.person

        with _capture_sql(store) as favorite_sql:
            favorites = await service.list_favorites(person)
        with _capture_sql(store) as deleted_sql:
            deleted = await service.list_deleted_wishlists(
                person,
                retention_days=DEFAULT_WISHLIST_RETENTION_DAYS,
                now=_NOW,
            )
        with _capture_sql(store) as bot_sql:

            async def load_offer(repo: WishlistRepository) -> list[Wishlist]:
                return await _allowed(repo, person)

            offered = await store.run_repository(load_offer)
        with _capture_sql(store) as success_sql:
            recorded = await service.record_view(person, world.own.wishlist_id)
        with _capture_sql(store) as record_deleted_sql, pytest.raises(WishlistNotFoundError):
            await service.record_view(person, world.in_window.wishlist_id)
        with _capture_sql(store) as hidden_sql, pytest.raises(WishlistNotFoundError):
            await service.record_view(person, world.hidden.wishlist_id)
        with _capture_sql(store) as missing_sql, pytest.raises(WishlistNotFoundError):
            await service.record_view(world.ghost, world.ghost_list.wishlist_id)

        assert [_favorite_card(person, wishlist) for wishlist in favorites] == [
            _expected_card(world.share, "favorite"),
            _expected_card(world.collab, "member"),
        ]
        assert world.own.wishlist_id not in {wishlist.id for wishlist in favorites}
        assert world.bookmarked_deleted.wishlist_id not in {wishlist.id for wishlist in favorites}

        assert len(deleted) == 1
        restored, expires_at, days_left = deleted[0]
        assert restored.id == world.in_window.wishlist_id
        assert restored.title == world.in_window.title
        assert restored.description == world.in_window.description
        assert restored.event_title == world.in_window.occasion
        assert restored.updated_at == _IN_WINDOW_AT
        assert expires_at == deletion_moment(_IN_WINDOW_AT) + timedelta(
            days=DEFAULT_WISHLIST_RETENTION_DAYS
        )
        assert days_left == days_remaining(_IN_WINDOW_AT, DEFAULT_WISHLIST_RETENTION_DAYS, _NOW)
        assert world.expired.wishlist_id not in {wishlist.id for wishlist, _, _ in deleted}

        editable = sorted(
            (
                (world.collab.wishlist_id, world.collab.title),
                (world.own.wishlist_id, world.own.title),
            ),
            key=lambda pair: pair[0],
        )
        assert [(wishlist.id, wishlist.title) for wishlist in offered] == editable
        refused = {
            world.share.wishlist_id,
            world.hidden.wishlist_id,
            world.bookmarked_deleted.wishlist_id,
            world.in_window.wishlist_id,
            world.expired.wishlist_id,
            world.ghost_list.wishlist_id,
        }
        assert refused.isdisjoint({wishlist.id for wishlist in offered})

        assert recorded.user_id == person.telegram_id
        assert recorded.wishlist_id == world.own.wishlist_id
        assert await _id_set(
            store,
            "SELECT wishlist_id FROM wl_view_history WHERE user_id = :uid",
            {"uid": person.telegram_id},
        ) == {world.own.wishlist_id}
        assert (
            await _id_set(
                store,
                "SELECT wishlist_id FROM wl_view_history WHERE user_id = :uid",
                {"uid": world.ghost.telegram_id},
            )
            == set()
        )
        assert _saw_user_exists(missing_sql, world.ghost.telegram_id) is True

        observed = {
            **_named_reads("favorites", favorite_sql, members=False),
            **_named_reads("deleted", deleted_sql, members=True),
            **_named_reads("bot", bot_sql, members=False),
            **_named_reads("record_success", success_sql, members=False),
            **_named_reads("record_deleted", record_deleted_sql, members=True),
            **_named_reads("record_hidden", hidden_sql, members=False),
            **_named_reads("record_missing_user", missing_sql, members=False),
        }
        assert observed == dict.fromkeys(observed, 0)

        for wishlist in favorites:
            assert wishlist.items == []
        for wishlist, _expires_at, _days_left in deleted:
            assert wishlist.items == []
            assert wishlist.members == []
        for wishlist in offered:
            assert wishlist.items == []
    finally:
        await users.engine.dispose()
        await store.engine.dispose()
