"""History open batches wishlist headers (WISHENKA-325).

A 20-row open keeps the stored visit list, the cap, and access checks.
It must not compile ``FROM wl_lists WHERE id = ?`` from ``get_wishlist``
and must not read ``wl_items``. Headers arrive as one
``FROM wl_lists WHERE id IN (`` batch covering the page. The
``list_view_history`` join ``ON l.id = vh.wishlist_id`` is not that batch,
and neither is ``wishlist_id =``.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncConnection

from wishenka.auth.models import AuthenticatedUser, TelegramUser
from wishenka.users.store import UserStore
from wishenka.wishlists.models import WishlistRole
from wishenka.wishlists.policy import WishlistAccessPolicy
from wishenka.wishlists.repository import WishlistRepository
from wishenka.wishlists.service import WishlistService
from wishenka.wishlists.store import WishlistStore

pytestmark = pytest.mark.timeout(30)

_FROZEN = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
_VIEWER_ID = 32501
_HOST_ID = 32502
_OTHER_ID = 32503
_OPEN_LIMIT = 20
_STORED_VISIBLE = 21
_FILLER_COUNT = 18
_PER_ROW_LIST_LOAD = "FROM wl_lists WHERE id = ?"
_HEADER_BATCH = "FROM wl_lists WHERE id IN ("


@dataclass(frozen=True)
class _ListFacts:
    """Fields history must keep for one stored wishlist."""

    title: str
    description: str | None
    event_title: str | None
    event_date: datetime | None


def _user(telegram_id: int, first_name: str) -> AuthenticatedUser:
    return AuthenticatedUser(
        telegram_id=telegram_id,
        first_name=first_name,
        auth_method="session_token",
    )


def _facts(
    title: str,
    description: str | None = None,
    event_title: str | None = None,
    event_date: datetime | None = None,
) -> _ListFacts:
    return _ListFacts(
        title=title,
        description=description,
        event_title=event_title,
        event_date=event_date,
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


def _sql_observation(
    captured: list[tuple[str, object]],
    page_ids: set[int],
) -> dict[str, object]:
    """Count item reads, per-row list loads, and the header id batch."""
    item_reads = 0
    per_row = 0
    header_batches = 0
    header_ids: set[int] = set()
    for statement, parameters in captured:
        compact = _compact(statement)
        if "wl_items" in compact:
            item_reads += 1
        if _PER_ROW_LIST_LOAD in compact:
            per_row += 1
        if _HEADER_BATCH in compact:
            header_batches += 1
            header_ids.update(_ints_from_params(parameters))
    return {
        "wl_items_reads": item_reads,
        "per_row_list_loads": per_row,
        "header_batches": header_batches,
        "header_covers_page": header_batches == 1 and header_ids == page_ids,
    }


@contextmanager
def _frozen_recording_clock(moment: datetime) -> Iterator[None]:
    """Freeze view timestamps in both record paths."""
    with (
        patch("wishenka.wishlists.service.datetime") as service_clock,
        patch("wishenka.wishlists.repo_ops.datetime") as repo_clock,
    ):
        service_clock.now.return_value = moment
        repo_clock.now.return_value = moment
        yield


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
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'wishenka_325_history_batch.db'}"
    store = WishlistStore(db_url)
    await store.initialize()
    return store, UserStore(db_url)


async def _seed_users(
    users: UserStore,
) -> tuple[AuthenticatedUser, AuthenticatedUser, AuthenticatedUser]:
    await users.upsert_user(TelegramUser(id=_VIEWER_ID, first_name="Viewer"))
    await users.upsert_user(TelegramUser(id=_HOST_ID, first_name="Host"))
    await users.upsert_user(TelegramUser(id=_OTHER_ID, first_name="Other"))
    return _user(_VIEWER_ID, "Viewer"), _user(_HOST_ID, "Host"), _user(_OTHER_ID, "Other")


async def _create(
    service: WishlistService,
    owner: AuthenticatedUser,
    facts: _ListFacts,
) -> int:
    wishlist = await service.create_wishlist(
        owner=owner,
        title=facts.title,
        description=facts.description,
        event_title=facts.event_title,
        event_date=facts.event_date,
    )
    return wishlist.id


async def _visible_ids(
    store: WishlistStore,
    user: AuthenticatedUser,
    *,
    limit: int,
) -> list[int]:
    async def read(conn: AsyncConnection) -> list[int]:
        entries = await WishlistRepository(conn).list_view_history(user.telegram_id, limit=limit)
        return [entry.wishlist_id for entry in entries]

    return await store.execute_read(read)


async def _raw_wishlist_ids(store: WishlistStore, user_id: int) -> set[int]:
    async def read(conn: AsyncConnection) -> set[int]:
        rows = (
            await conn.execute(
                text("SELECT wishlist_id FROM wl_view_history WHERE user_id = :uid"),
                {"uid": user_id},
            )
        ).all()
        return {int(row.wishlist_id) for row in rows}

    return await store.execute_read(read)


async def _favorite_ids(store: WishlistStore, user_id: int) -> set[int]:
    async def read(conn: AsyncConnection) -> set[int]:
        return await WishlistRepository(conn).list_favorite_ids(user_id)

    return await store.execute_read(read)


@pytest.mark.asyncio
async def test_history_open_batches_headers_without_per_row_wishlist_load(
    tmp_path: Path,
) -> None:
    """A 20-row open keeps today's list and must not call get_wishlist per row."""
    store, users = await _open_stores(tmp_path)
    try:
        viewer, host, other = await _seed_users(users)
        service = WishlistService(store=store)
        alpha_facts = _facts(
            "Alpha Title",
            "Alpha description",
            "Alpha Event",
            datetime(2026, 8, 1, tzinfo=UTC),
        )
        beta_facts = _facts(
            "Beta Title",
            "Beta description",
            "Beta Event",
            datetime(2026, 8, 2, tzinfo=UTC),
        )
        collab_facts = _facts(
            "Collab Title",
            "Collab description",
            "Collab Event",
            datetime(2026, 8, 3, tzinfo=UTC),
        )
        deleted_facts = _facts("Deleted Title", "Deleted description")
        revoked_facts = _facts("Revoked Title", "Revoked description")
        other_facts = _facts("Other Title", "Other description")
        filler_facts = [_facts(f"Filler {index:02d}") for index in range(_FILLER_COUNT)]

        filler_ids: list[int] = []
        for facts in filler_facts:
            filler_ids.append(await _create(service, viewer, facts))
        alpha_id = await _create(service, viewer, alpha_facts)
        beta_id = await _create(service, viewer, beta_facts)
        collab_id = await _create(service, host, collab_facts)
        await service.add_member(collab_id, host, viewer.telegram_id, WishlistRole.MEMBER)
        await service.add_wish_item(collab_id, host, title="Collab Wish")
        await service.add_favorite(viewer, collab_id)
        await service.add_wish_item(alpha_id, viewer, title="Alpha Wish")
        await service.add_wish_item(beta_id, viewer, title="Beta Wish")
        deleted_id = await _create(service, viewer, deleted_facts)
        revoked_id = await _create(service, host, revoked_facts)
        await service.add_member(revoked_id, host, viewer.telegram_id, WishlistRole.MEMBER)
        other_id = await _create(service, other, other_facts)

        known: dict[int, _ListFacts] = {
            alpha_id: alpha_facts,
            beta_id: beta_facts,
            collab_id: collab_facts,
        }
        for wishlist_id, facts in zip(filler_ids, filler_facts, strict=True):
            known[wishlist_id] = facts

        with _frozen_recording_clock(_FROZEN):
            await service.record_view(viewer, deleted_id)
            await service.record_view(viewer, revoked_id)
            for wishlist_id in filler_ids:
                await service.record_view(viewer, wishlist_id)
            await service.record_view(viewer, alpha_id)
            await service.record_view(viewer, beta_id)
            await service.record_view(viewer, collab_id)
            await service.record_view(other, other_id)

        await service.delete_wishlist(deleted_id, viewer)
        await service.remove_member(revoked_id, host, viewer.telegram_id)

        expected_ids = [collab_id, beta_id, alpha_id, *reversed(filler_ids[1:])]
        older_id = filler_ids[0]
        assert len(expected_ids) == _OPEN_LIMIT

        with _capture_sql(store) as captured:
            history = await service.get_history(viewer, limit=_OPEN_LIMIT)

        returned_ids = [wishlist.id for wishlist, _viewed_at in history]
        assert returned_ids == expected_ids
        for wishlist, viewed_at in history:
            facts = known[wishlist.id]
            assert wishlist.title == facts.title
            assert wishlist.description == facts.description
            assert wishlist.event_title == facts.event_title
            assert wishlist.event_date == facts.event_date
            assert viewed_at == _FROZEN

        collab = next(wishlist for wishlist, _viewed_at in history if wishlist.id == collab_id)
        collab_ctx = WishlistAccessPolicy.resolve_context(viewer, collab)
        assert collab_ctx.role == WishlistRole.MEMBER
        assert collab_ctx.is_member is True
        assert collab_ctx.is_owner is False

        assert await _favorite_ids(store, viewer.telegram_id) == {collab_id}
        assert deleted_id not in returned_ids
        assert revoked_id not in returned_ids
        assert other_id not in returned_ids

        stored_ids = await _visible_ids(store, viewer, limit=_STORED_VISIBLE + 5)
        assert stored_ids == [*expected_ids, older_id]
        assert len(stored_ids) == _STORED_VISIBLE
        raw_ids = await _raw_wishlist_ids(store, viewer.telegram_id)
        assert deleted_id in raw_ids
        assert revoked_id not in raw_ids

        other_history = await service.get_history(other, limit=_OPEN_LIMIT)
        other_ids = [wishlist.id for wishlist, _viewed_at in other_history]
        assert other_ids == [other_id]
        assert set(other_ids).isdisjoint(returned_ids)

        await service.record_view(viewer, older_id)
        refreshed = await _visible_ids(store, viewer, limit=_STORED_VISIBLE + 5)
        assert refreshed[0] == older_id
        assert set(refreshed) == set(stored_ids)
        assert len(refreshed) == _STORED_VISIBLE

        await service.clear_history(viewer)
        assert await _visible_ids(store, viewer, limit=_STORED_VISIBLE + 5) == []
        assert await _raw_wishlist_ids(store, viewer.telegram_id) == set()
        assert await _visible_ids(store, other, limit=_OPEN_LIMIT) == [other_id]

        saw_history_join = any(
            "JOIN wl_lists" in _compact(statement) for statement, _parameters in captured
        )
        assert saw_history_join is True
        observed = _sql_observation(captured, set(expected_ids))
        assert observed == {
            "wl_items_reads": 0,
            "per_row_list_loads": 0,
            "header_batches": 1,
            "header_covers_page": True,
        }
    finally:
        await users.engine.dispose()
        await store.engine.dispose()
