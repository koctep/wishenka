"""Failing repro for WISHENKA-304: equal view times follow recording order.

A repeated view keeps its row and becomes the newest recording. The tie-break is
that recording sequence, newest first, on the session list and the stored list,
including which equal-time rows stay inside the existing limit of 20. The row id
is not the tie-break. Record A, then B, then C, then A again, and the order is
A, C, B.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from wishenka.auth.models import AuthenticatedUser, TelegramUser
from wishenka.users.store import UserStore
from wishenka.wishlists.models import Wishlist
from wishenka.wishlists.repo_ops import RepoWishlistOps
from wishenka.wishlists.repository import WishlistRepository
from wishenka.wishlists.service import WishlistService
from wishenka.wishlists.store import WishlistStore

pytestmark = pytest.mark.timeout(30)

_FROZEN = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
_LATER = datetime(2026, 6, 1, 13, 0, tzinfo=UTC)
_VIEWER_ID = 30401
_OTHER_ID = 30402
_HISTORY_LIMIT = 20


def _user(telegram_id: int, first_name: str) -> AuthenticatedUser:
    return AuthenticatedUser(
        telegram_id=telegram_id,
        first_name=first_name,
        auth_method="session_token",
    )


def _history_wishlist_ids(history: list[tuple[Wishlist, datetime]]) -> list[int]:
    return [wishlist.id for wishlist, _ in history]


def _expected_limit_order(created_ids: list[int]) -> list[int]:
    """L1..L20, repeat L1, then L21: twenty ids, newest recording first."""
    repeated = created_ids[0]
    newest = created_ids[-1]
    kept_after_repeat = list(reversed(created_ids[2:-1]))
    return [newest, repeated, *kept_after_repeat]


@contextmanager
def _frozen_recording_clock(moment: datetime) -> Iterator[tuple[MagicMock, MagicMock]]:
    """Freeze view timestamps in both record paths. Wishlists are created outside."""
    with (
        patch("wishenka.wishlists.service.datetime") as service_clock,
        patch("wishenka.wishlists.repo_ops.datetime") as repo_clock,
    ):
        service_clock.now.return_value = moment
        repo_clock.now.return_value = moment
        yield service_clock, repo_clock


async def _create_owned(
    service: WishlistService,
    owner: AuthenticatedUser,
    titles: list[str],
) -> list[int]:
    created: list[int] = []
    for title in titles:
        wishlist = await service.create_wishlist(owner=owner, title=title)
        created.append(wishlist.id)
    return created


async def _open_stores(tmp_path: Path, name: str) -> tuple[WishlistStore, UserStore]:
    db_url = f"sqlite+aiosqlite:///{tmp_path / name}"
    store = WishlistStore(db_url)
    await store.initialize()
    return store, UserStore(db_url)


async def _seed_viewers(users: UserStore) -> tuple[AuthenticatedUser, AuthenticatedUser]:
    await users.upsert_user(TelegramUser(id=_VIEWER_ID, first_name="Viewer"))
    await users.upsert_user(TelegramUser(id=_OTHER_ID, first_name="Other"))
    return _user(_VIEWER_ID, "Viewer"), _user(_OTHER_ID, "Other")


async def _reload_history_ids(store: WishlistStore, viewer: AuthenticatedUser) -> list[int]:
    history = await WishlistService(store=store).get_history(viewer, limit=_HISTORY_LIMIT)
    return _history_wishlist_ids(history)


async def _stored_history_ids(store: WishlistStore, viewer: AuthenticatedUser) -> list[int]:
    async def read(conn: AsyncConnection) -> list[int]:
        entries = await WishlistRepository(conn).list_view_history(
            viewer.telegram_id,
            limit=_HISTORY_LIMIT,
        )
        return [entry.wishlist_id for entry in entries]

    return await store.execute_read(read)


@pytest.mark.asyncio
async def test_stored_equal_times_follow_recording_sequence_after_reload(tmp_path: Path) -> None:
    """A flushed A, B, C, A sequence reloads as A, C, B from the service and SQL."""
    store, users = await _open_stores(tmp_path, "wishenka_304_order.db")
    try:
        viewer, _other = await _seed_viewers(users)
        service = WishlistService(store=store)
        created = await _create_owned(service, viewer, ["A", "B", "C"])
        wishlist_a, wishlist_b, wishlist_c = created
        expected = [wishlist_a, wishlist_c, wishlist_b]

        with _frozen_recording_clock(_FROZEN):
            await service.record_view(viewer, wishlist_a)
            await service.record_view(viewer, wishlist_b)
            await service.record_view(viewer, wishlist_c)
            await service.record_view(viewer, wishlist_a)

        reloaded = await _reload_history_ids(store, viewer)
        listed = await _stored_history_ids(store, viewer)
        assert [reloaded, listed] == [expected, expected]
    finally:
        await users.engine.dispose()
        await store.engine.dispose()


@pytest.mark.asyncio
async def test_stored_equal_time_limit_keeps_newer_recordings(tmp_path: Path) -> None:
    """SQL LIMIT keeps the newer equal-time rows; another viewer does not reorder them."""
    store, users = await _open_stores(tmp_path, "wishenka_304_limit.db")
    try:
        viewer, other = await _seed_viewers(users)
        service = WishlistService(store=store)
        created = await _create_owned(service, viewer, [f"L{index}" for index in range(1, 22)])
        other_lists = await _create_owned(service, other, ["Other-1", "Other-2"])
        expected = _expected_limit_order(created)

        async def record_without_deleting_older_rows(conn: AsyncConnection) -> None:
            ops = RepoWishlistOps(WishlistRepository(conn))
            for wishlist_id in created[:_HISTORY_LIMIT]:
                await ops.record_view(viewer, wishlist_id)
            for wishlist_id in other_lists:
                await ops.record_view(other, wishlist_id)
            await ops.record_view(viewer, created[0])
            await ops.record_view(viewer, created[-1])

        with _frozen_recording_clock(_FROZEN):
            await store.transaction(record_without_deleting_older_rows)

        listed = await _stored_history_ids(store, viewer)
        listed_again = await _stored_history_ids(store, viewer)
        assert [listed, listed_again] == [expected, expected]
        assert created[1] not in listed
    finally:
        await users.engine.dispose()
        await store.engine.dispose()


@pytest.mark.asyncio
async def test_later_view_time_ranks_before_earlier_view_time(tmp_path: Path) -> None:
    """Different view times stay most-recent-first after reload."""
    store, users = await _open_stores(tmp_path, "wishenka_304_times.db")
    try:
        stored_viewer, _other = await _seed_viewers(users)
        stored = WishlistService(store=store)
        stored_earlier, stored_later = await _create_owned(
            stored,
            stored_viewer,
            ["Earlier", "Later"],
        )
        with _frozen_recording_clock(_FROZEN) as (service_clock, repo_clock):
            await stored.record_view(stored_viewer, stored_earlier)
            service_clock.now.return_value = _LATER
            repo_clock.now.return_value = _LATER
            await stored.record_view(stored_viewer, stored_later)

        expected = [stored_later, stored_earlier]
        assert await _reload_history_ids(store, stored_viewer) == expected
        assert await _stored_history_ids(store, stored_viewer) == expected
    finally:
        await users.engine.dispose()
        await store.engine.dispose()
