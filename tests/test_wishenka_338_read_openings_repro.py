"""Failing reproduction for WISHENKA-338: one-wishlist openings still take the save lock.

A second connection holds ``BEGIN IMMEDIATE`` and an uncommitted title. The seven
openings, and the pure-read GETs that perform them, must return the committed
snapshot within 2 seconds. A save must still be waiting at that bound.
"""

from __future__ import annotations

import asyncio
import sqlite3
import threading
from collections.abc import Awaitable
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from wishenka.auth.models import AuthenticatedUser, TelegramUser
from wishenka.auth.session import SessionTokenService
from wishenka.config import Settings
from wishenka.users.store import UserStore
from wishenka.web.app import create_app
from wishenka.wishlists.exceptions import (
    ItemNotFoundError,
    PermissionDeniedError,
    WishlistDeletedError,
    WishlistNotFoundError,
)
from wishenka.wishlists.models import Wishlist, WishlistMember
from wishenka.wishlists.schemas import (
    GiftedItemDTO,
    WishItemGifterViewDTO,
    WishItemRecipientViewDTO,
    WishlistDetailViewDTO,
)
from wishenka.wishlists.service import WishlistService
from wishenka.wishlists.store import WishlistStore

pytestmark = pytest.mark.timeout(30)

_ORIGINAL_TITLE = "Original Title"
_PENDING_TITLE = "Uncommitted Title"
_ALPHA = "Alpha Wish"
_BETA = "Beta Wish"
_GAMMA = "Gamma Wish"
_MISSING_ID = 9_999_999
_READ_BOUND_SECONDS = 2.0
_OWNER_ID = 33801
_MEMBER_ID = 33802
_STRANGER_ID = 33803

_OWNER = AuthenticatedUser(telegram_id=_OWNER_ID, first_name="Owner")
_MEMBER = AuthenticatedUser(telegram_id=_MEMBER_ID, first_name="Member")
_STRANGER = AuthenticatedUser(telegram_id=_STRANGER_ID, first_name="Stranger")


@dataclass(frozen=True)
class _Seed:
    wishlist_id: int
    deleted_id: int
    alpha_id: int
    gamma_id: int


@dataclass(frozen=True)
class _HttpCase:
    path: str
    headers: dict[str, str]


def _database_url(path: Path) -> str:
    return f"sqlite+aiosqlite:///{path}"


def _settings(path: Path) -> Settings:
    return Settings(
        database_url=_database_url(path),
        secret_key="wishenka-338-repro",
        background_cleanup_enabled=False,
        receipt_notice_worker_enabled=False,
    )


async def _seed(store: WishlistStore, users: UserStore) -> _Seed:
    """Commit one wishlist, its member, wishes, receipt, and favorite mark."""
    for user in (_OWNER, _MEMBER, _STRANGER):
        await users.upsert_user(TelegramUser(id=user.telegram_id, first_name=user.first_name))
    service = WishlistService(store)
    wishlist = await service.create_wishlist(owner=_OWNER, title=_ORIGINAL_TITLE)
    await service.add_member(wishlist.id, _OWNER, _MEMBER_ID)
    alpha = await service.add_wish_item(wishlist.id, _OWNER, _ALPHA)
    await service.add_wish_item(wishlist.id, _OWNER, _BETA)
    gamma = await service.add_wish_item(wishlist.id, _OWNER, _GAMMA, quantity=2)
    await service.record_item_fulfillment(gamma.id, _OWNER, 1, wishlist_id=wishlist.id)
    await service.add_favorite(_MEMBER, wishlist.id)
    deleted = await service.create_wishlist(owner=_OWNER, title="Deleted Title")
    await service.delete_wishlist(deleted.id, _OWNER)
    return _Seed(
        wishlist_id=wishlist.id,
        deleted_id=deleted.id,
        alpha_id=alpha.id,
        gamma_id=gamma.id,
    )


def _hold_immediate(
    path: Path,
    wishlist_id: int,
    started: threading.Event,
    release: threading.Event,
) -> None:
    """Keep one connection in ``BEGIN IMMEDIATE`` until ``release`` is set, then roll back."""
    connection = sqlite3.connect(path, timeout=5)
    try:
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("BEGIN IMMEDIATE")
        cursor = connection.execute(
            "UPDATE wl_lists SET title = ? WHERE id = ?",
            (_PENDING_TITLE, wishlist_id),
        )
        if cursor.rowcount != 1:
            raise RuntimeError(f"writer updated {cursor.rowcount} wishlist rows")
        started.set()
        if not release.wait(timeout=8):
            raise TimeoutError("writer hold outlived its bound")
        connection.rollback()
    finally:
        connection.close()


@asynccontextmanager
async def _uncommitted_title(path: Path, wishlist_id: int) -> Any:
    """Hold ``BEGIN IMMEDIATE`` with a title change that is rolled back on exit."""
    started = threading.Event()
    release = threading.Event()
    errors: list[BaseException] = []

    def run() -> None:
        try:
            _hold_immediate(path, wishlist_id, started, release)
        except BaseException as exc:
            errors.append(exc)
            started.set()

    worker = threading.Thread(target=run, name="wishlist-write-hold")
    worker.start()
    try:
        if not await asyncio.to_thread(started.wait, 2):
            raise TimeoutError("writer did not acquire BEGIN IMMEDIATE")
        if errors:
            raise errors[0]
        yield
    finally:
        release.set()
        await asyncio.to_thread(worker.join, 5)
        if worker.is_alive():
            raise TimeoutError("writer did not roll back BEGIN IMMEDIATE")
        if errors:
            raise errors[0]


def _committed_title(path: Path, wishlist_id: int) -> str:
    """Read the title on a connection that is not the held writer."""
    connection = sqlite3.connect(path)
    try:
        row = connection.execute(
            "SELECT title FROM wl_lists WHERE id = ?",
            (wishlist_id,),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        raise AssertionError(f"wishlist {wishlist_id} is missing")
    return str(row[0])


async def _finish(awaitable: Awaitable[Any]) -> None:
    """Let a blocked call finish after the writer rolls back. Do not cancel it."""
    with suppress(Exception):
        await asyncio.wait_for(awaitable, timeout=8)


async def _raises(awaitable: Awaitable[object], exc_type: type[BaseException]) -> None:
    with pytest.raises(exc_type):
        await awaitable


async def _open_one_wishlist(service: WishlistService, seed: _Seed) -> None:
    """The seven openings return the committed snapshot and the same refusals."""
    opened = await asyncio.gather(
        service.get_wishlist_by_id(seed.wishlist_id),
        service.get_wishlist_view(seed.wishlist_id, _MEMBER),
        service.get_members(seed.wishlist_id, _OWNER),
        service.get_wish_item(seed.wishlist_id, seed.alpha_id, _OWNER),
        service.list_wish_items(seed.wishlist_id, _OWNER),
        service.list_gifted_items(seed.wishlist_id, _OWNER),
        service.is_favorite(_MEMBER, seed.wishlist_id),
        service.is_favorite(None, seed.wishlist_id),
    )
    wishlist = cast(Wishlist, opened[0])
    view = cast(WishlistDetailViewDTO, opened[1])
    members = cast(list[WishlistMember], opened[2])
    item = cast(WishItemRecipientViewDTO | WishItemGifterViewDTO, opened[3])
    items = cast(list[WishItemRecipientViewDTO | WishItemGifterViewDTO], opened[4])
    gifted = cast(list[GiftedItemDTO], opened[5])
    favorite = cast(bool, opened[6])
    signed_out = cast(bool, opened[7])
    assert wishlist.title == _ORIGINAL_TITLE
    assert view.title == _ORIGINAL_TITLE
    assert [row.title for row in view.items] == [_ALPHA, _BETA, _GAMMA]
    assert [member.user_id for member in members] == [_MEMBER_ID]
    assert item.title == _ALPHA
    assert [row.title for row in items] == [_ALPHA, _BETA, _GAMMA]
    assert [row.title for row in gifted] == [_GAMMA]
    assert gifted[0].received_quantity == 1
    assert len(gifted[0].receipts) == 1
    assert gifted[0].receipts[0].quantity == 1
    assert favorite is True
    assert signed_out is False

    await asyncio.gather(
        _raises(service.get_wishlist_by_id(_MISSING_ID), WishlistNotFoundError),
        _raises(service.get_wishlist_by_id(seed.deleted_id), WishlistDeletedError),
        _raises(
            service.get_wish_item(seed.wishlist_id, _MISSING_ID, _OWNER),
            ItemNotFoundError,
        ),
        _raises(service.get_members(seed.wishlist_id, _STRANGER), PermissionDeniedError),
        _raises(
            service.list_gifted_items(seed.wishlist_id, _STRANGER),
            PermissionDeniedError,
        ),
    )


@pytest.mark.asyncio
async def test_one_wishlist_openings_see_committed_snapshot_while_save_holds_lock(
    tmp_path: Path,
) -> None:
    """Seven openings return the pre-write snapshot within 2 seconds and commit nothing."""
    database = tmp_path / "openings.db"
    store = WishlistStore(_database_url(database))
    users = UserStore(store.database_url)
    read: asyncio.Task[None] | None = None
    try:
        await store.initialize()
        seed = await _seed(store, users)
        service = WishlistService(store)
        try:
            async with _uncommitted_title(database, seed.wishlist_id):
                read = asyncio.create_task(_open_one_wishlist(service, seed))
                await asyncio.wait_for(asyncio.shield(read), timeout=_READ_BOUND_SECONDS)
            assert _committed_title(database, seed.wishlist_id) == _ORIGINAL_TITLE
        finally:
            if read is not None:
                await _finish(read)
    finally:
        await users.engine.dispose()
        await store.engine.dispose()


def _bearer(secret: str, user: AuthenticatedUser) -> dict[str, str]:
    token = SessionTokenService(secret).create_token(user.telegram_id, user.first_name)
    return {"Authorization": f"Bearer {token}"}


def _http_cases(seed: _Seed, secret: str) -> list[_HttpCase]:
    owner = _bearer(secret, _OWNER)
    member = _bearer(secret, _MEMBER)
    stranger = _bearer(secret, _STRANGER)
    wishlist = f"/api/wishlists/{seed.wishlist_id}"
    return [
        _HttpCase(wishlist, member),
        _HttpCase(f"{wishlist}/items", owner),
        _HttpCase(f"{wishlist}/members", owner),
        _HttpCase(f"{wishlist}/items/{seed.alpha_id}", owner),
        _HttpCase(f"{wishlist}/gifted", owner),
        _HttpCase(f"/api/wishlists/{_MISSING_ID}", owner),
        _HttpCase(f"/api/wishlists/{seed.deleted_id}", owner),
        _HttpCase(f"{wishlist}/items/{_MISSING_ID}", owner),
        _HttpCase(f"{wishlist}/members", stranger),
        _HttpCase(f"{wishlist}/gifted", stranger),
    ]


def _get(client: TestClient, case: _HttpCase) -> tuple[int, Any]:
    response = client.get(case.path, headers=case.headers)
    return response.status_code, response.json()


def _assert_unlocked_bodies(seed: _Seed, bodies: list[tuple[int, Any]]) -> None:
    """The bodies these routes return when no save is in progress."""
    (
        wishlist,
        items,
        members,
        item,
        gifted,
        missing,
        deleted,
        missing_item,
        stranger_members,
        stranger_gifted,
    ) = bodies
    assert wishlist[0] == 200
    assert wishlist[1]["name"] == _ORIGINAL_TITLE
    assert wishlist[1]["is_favorite"] is True
    assert items[0] == 200
    assert [row["title"] for row in items[1]] == [_ALPHA, _BETA, _GAMMA]
    assert members[0] == 200
    assert [row["user_id"] for row in members[1]] == [_OWNER_ID, _MEMBER_ID]
    assert item[0] == 200
    assert item[1]["title"] == _ALPHA
    assert gifted[0] == 200
    assert [row["title"] for row in gifted[1]] == [_GAMMA]
    assert gifted[1][0]["receipts"]
    assert missing[0] == 404
    assert deleted[0] == 404
    assert missing_item[0] == 404
    assert stranger_members[0] == 404
    assert stranger_gifted[0] == 403
    assert seed.wishlist_id == wishlist[1]["id"]


@pytest.mark.asyncio
async def test_pure_read_gets_match_unlocked_bodies_while_save_holds_lock(
    tmp_path: Path,
) -> None:
    """Pure-read GETs return the same status and body within 2 seconds per request."""
    database = tmp_path / "http.db"
    app = create_app(_settings(database))
    secret = app.state.settings.secret_key
    pending: list[asyncio.Future[tuple[int, Any]]] = []
    with TestClient(app) as client:
        portal = client.portal
        assert portal is not None
        seed = await asyncio.to_thread(
            portal.call,
            _seed,
            app.state.wishlist_store,
            app.state.user_store,
        )
        cases = _http_cases(seed, secret)
        baseline = await asyncio.to_thread(
            lambda: [_get(client, case) for case in cases],
        )
        _assert_unlocked_bodies(seed, baseline)
        try:
            async with _uncommitted_title(database, seed.wishlist_id):
                locked: list[tuple[int, Any]] = []
                loop = asyncio.get_running_loop()
                for case in cases:
                    future = loop.run_in_executor(None, _get, client, case)
                    pending.append(future)
                    observed = await asyncio.wait_for(
                        asyncio.shield(future),
                        timeout=_READ_BOUND_SECONDS,
                    )
                    locked.append(observed)
                assert locked == baseline
            assert _committed_title(database, seed.wishlist_id) == _ORIGINAL_TITLE
        finally:
            if pending:
                await _finish(asyncio.gather(*pending, return_exceptions=True))


@pytest.mark.asyncio
async def test_save_does_not_finish_while_another_immediate_transaction_holds_lock(
    tmp_path: Path,
) -> None:
    """A settings save still waits on ``BEGIN IMMEDIATE`` and does not finish within 2 seconds."""
    database = tmp_path / "save.db"
    store = WishlistStore(_database_url(database))
    users = UserStore(store.database_url)
    save: asyncio.Task[Any] | None = None
    try:
        await store.initialize()
        seed = await _seed(store, users)
        service = WishlistService(store)
        try:
            async with _uncommitted_title(database, seed.wishlist_id):
                save = asyncio.create_task(
                    service.update_wishlist_settings(
                        wishlist_id=seed.wishlist_id,
                        actor=_OWNER,
                        title="Saved During Lock",
                    )
                )
                with pytest.raises(TimeoutError):
                    await asyncio.wait_for(asyncio.shield(save), timeout=_READ_BOUND_SECONDS)
                assert not save.done()
        finally:
            if save is not None:
                await _finish(save)
    finally:
        await users.engine.dispose()
        await store.engine.dispose()
