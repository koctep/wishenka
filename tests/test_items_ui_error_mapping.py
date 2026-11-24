"""Characterization of externally visible behaviour of the wishlist items UI routes.

Written for WISHENKA-112 (a behaviour-preserving refactoring of ``items_ui.py``) and green
both before and after it. Pins the HTTP error mapping (409 archived, 404 not found / not a
member, 400 invalid order), the "no write for an unchanged order" rule and the structured
INFO/WARNING events of the reorder and move routes.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from wishenka.auth.models import AuthenticatedUser
from wishenka.auth.session import SessionTokenService
from wishenka.config import Settings
from wishenka.web.app import create_app
from wishenka.wishlists.service import WishlistService

pytestmark = pytest.mark.timeout(30)

_LOGGER = "wishenka.web.items_ui"
_MISSING_ID = 987654
_Env = tuple[TestClient, SessionTokenService, FastAPI]
_Send = Callable[[TestClient, int, int, dict[str, str]], Any]


def make_user(
    telegram_id: int,
    first_name: str,
    username: str | None = None,
) -> AuthenticatedUser:
    """Create a test AuthenticatedUser instance."""
    return AuthenticatedUser(
        telegram_id=telegram_id,
        first_name=first_name,
        username=username,
        auth_method="session_token",
    )


def auth_header(
    sessions: SessionTokenService,
    user_id: int,
    name: str = "User",
) -> dict[str, str]:
    """Generate Authorization header with valid session bearer token."""
    return {"Authorization": f"Bearer {sessions.create_token(user_id, name)}"}


@pytest.fixture
def test_app(tmp_path: Path) -> Iterator[_Env]:
    """Initialize TestClient and SessionTokenService with an isolated SQLite database."""
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'items_ui_error_mapping.db'}",
        secret_key="items-ui-error-mapping-test-secret",
    )
    app = create_app(settings)
    sessions = SessionTokenService(settings.secret_key)
    with TestClient(app) as client:
        yield client, sessions, app


def _reorder(client: TestClient, wl: int, item: int, headers: dict[str, str]) -> Any:
    return client.post(
        f"/web/wishlists/{wl}/items/reorder",
        data={"item_ids": [str(item)]},
        headers=headers,
    )


def _move(client: TestClient, wl: int, item: int, headers: dict[str, str]) -> Any:
    return client.post(f"/web/wishlists/{wl}/items/{item}/move?direction=up", headers=headers)


def _archive_confirm(client: TestClient, wl: int, item: int, headers: dict[str, str]) -> Any:
    return client.get(f"/web/wishlists/{wl}/items/{item}/archive-confirm", headers=headers)


def _archive(client: TestClient, wl: int, item: int, headers: dict[str, str]) -> Any:
    return client.post(f"/web/wishlists/{wl}/items/{item}/archive", headers=headers)


def _restore(client: TestClient, wl: int, item: int, headers: dict[str, str]) -> Any:
    return client.post(f"/web/wishlists/{wl}/items/{item}/restore", headers=headers)


_ROUTES = [
    pytest.param(_reorder, id="reorder"),
    pytest.param(_move, id="move"),
    pytest.param(_archive_confirm, id="archive-confirm"),
    pytest.param(_archive, id="archive"),
    pytest.param(_restore, id="restore"),
]
# Routes where an unknown *item* id (path parameter) is a domain "not found".
_ITEM_ROUTES = [r for r in _ROUTES if r.id != "reorder"]


def _seed(app: FastAPI, owner: AuthenticatedUser, count: int = 3) -> tuple[int, list[int]]:
    service: WishlistService = app.state.domain_service

    async def run() -> tuple[int, list[int]]:
        wl = await service.create_wishlist(owner=owner, title="Mapping Wishlist")
        ids = [
            (await service.add_wish_item(wishlist_id=wl.id, actor=owner, title=f"Item {n}")).id
            for n in range(count)
        ]
        return wl.id, ids

    return asyncio.run(run())


def _order(app: FastAPI, owner: AuthenticatedUser, wl: int) -> list[int]:
    items = asyncio.run(app.state.domain_service.list_wish_items(wishlist_id=wl, actor=owner))
    return [it.id for it in items]


def _events(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [getattr(r, "event", "") for r in caplog.records if r.name == _LOGGER]


@pytest.mark.parametrize("send", _ROUTES)
def test_archived_wishlist_gives_409(test_app: _Env, send: _Send) -> None:
    """Archived wishlist -> 409 with the fixed detail on every mapped route."""
    client, sessions, app = test_app
    owner = make_user(101, "Alice")
    wl, ids = _seed(app, owner)
    asyncio.run(app.state.domain_service.archive_wishlist(wishlist_id=wl, actor=owner))

    resp = send(client, wl, ids[0], auth_header(sessions, 101))

    assert resp.status_code == 409
    assert resp.json()["detail"] == "Wishlist is archived"


@pytest.mark.parametrize("send", _ROUTES)
def test_unknown_wishlist_gives_404(test_app: _Env, send: _Send) -> None:
    """Unknown wishlist id -> 404 with the generic detail."""
    client, sessions, app = test_app
    owner = make_user(101, "Alice")
    _wl, ids = _seed(app, owner)

    resp = send(client, _MISSING_ID, ids[0], auth_header(sessions, 101))

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Resource not found"


@pytest.mark.parametrize("send", _ROUTES)
def test_non_member_gives_404(test_app: _Env, send: _Send) -> None:
    """Authenticated non-member -> 404, indistinguishable from a missing resource."""
    client, sessions, app = test_app
    owner = make_user(101, "Alice")
    wl, ids = _seed(app, owner)

    resp = send(client, wl, ids[0], auth_header(sessions, 999, "Stranger"))

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Resource not found"


@pytest.mark.parametrize("send", _ITEM_ROUTES)
def test_unknown_item_gives_404(test_app: _Env, send: _Send) -> None:
    """Unknown item id for move / archive-confirm / archive / restore -> 404."""
    client, sessions, app = test_app
    owner = make_user(101, "Alice")
    wl, _ids = _seed(app, owner)

    resp = send(client, wl, _MISSING_ID, auth_header(sessions, 101))

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Resource not found"


def test_invalid_permutation_gives_400_event_and_keeps_order(
    test_app: _Env, caplog: pytest.LogCaptureFixture
) -> None:
    """Wrong item set on reorder -> exactly 400, rejected event, order kept, no success event."""
    client, sessions, app = test_app
    owner = make_user(101, "Alice")
    wl, ids = _seed(app, owner)
    before = _order(app, owner, wl)

    with caplog.at_level(logging.INFO, logger=_LOGGER):
        short = client.post(
            f"/web/wishlists/{wl}/items/reorder",
            data={"item_ids": [str(ids[1]), str(ids[0])]},
            headers=auth_header(sessions, 101),
        )
        unknown = client.post(
            f"/web/wishlists/{wl}/items/reorder",
            data={"item_ids": [str(ids[0]), str(ids[1]), str(_MISSING_ID)]},
            headers=auth_header(sessions, 101),
        )

    for resp in (short, unknown):
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Invalid item order"
    assert _order(app, owner, wl) == before
    rejected = [r for r in caplog.records if getattr(r, "event", "") == "ui_items_reorder_rejected"]
    assert len(rejected) == 2
    assert all(r.name == _LOGGER and r.levelno == logging.WARNING for r in rejected)
    assert all(getattr(r, "reason", None) == "invalid_permutation" for r in rejected)
    assert "ui_items_reordered" not in _events(caplog)


@pytest.fixture
def reorder_spy(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Count real ``WishlistService.reorder_wish_items`` calls while still delegating."""
    from wishenka.wishlists.repo_ops import RepoWishlistOps

    calls: list[dict[str, Any]] = []
    original = WishlistService.reorder_wish_items
    original_repo = RepoWishlistOps.reorder_wish_items

    async def spy(self: WishlistService, *args: Any, **kwargs: Any) -> Any:
        calls.append(kwargs)
        return await original(self, *args, **kwargs)

    async def repo_spy(self: RepoWishlistOps, *args: Any, **kwargs: Any) -> Any:
        calls.append(kwargs)
        return await original_repo(self, *args, **kwargs)

    monkeypatch.setattr(WishlistService, "reorder_wish_items", spy)
    monkeypatch.setattr(RepoWishlistOps, "reorder_wish_items", repo_spy)
    return calls


def test_unchanged_order_performs_no_write(
    test_app: _Env, reorder_spy: list[dict[str, Any]], caplog: pytest.LogCaptureFixture
) -> None:
    """Same-order reorder, first-up and last-down moves are no-ops without a write."""
    client, sessions, app = test_app
    owner = make_user(101, "Alice")
    wl, ids = _seed(app, owner)
    headers = auth_header(sessions, 101)

    with caplog.at_level(logging.INFO, logger=_LOGGER):
        same = client.post(
            f"/web/wishlists/{wl}/items/reorder",
            data={"item_ids": [str(i) for i in ids]},
            headers=headers,
        )
        first_up = client.post(
            f"/web/wishlists/{wl}/items/{ids[0]}/move?direction=up", headers=headers
        )
        last_down = client.post(
            f"/web/wishlists/{wl}/items/{ids[-1]}/move?direction=down", headers=headers
        )

    assert [same.status_code, first_up.status_code, last_down.status_code] == [200, 200, 200]
    assert reorder_spy == []
    assert _order(app, owner, wl) == ids
    assert _events(caplog).count("ui_items_reordered") == 1
    assert _events(caplog).count("ui_item_moved") == 2


def test_real_move_writes_once_and_logs_events(
    test_app: _Env, reorder_spy: list[dict[str, Any]], caplog: pytest.LogCaptureFixture
) -> None:
    """A real move and a real reorder each write once and emit their INFO events."""
    client, sessions, app = test_app
    owner = make_user(101, "Alice")
    wl, ids = _seed(app, owner)
    headers = auth_header(sessions, 101)

    with caplog.at_level(logging.INFO, logger=_LOGGER):
        moved = client.post(
            f"/web/wishlists/{wl}/items/{ids[2]}/move?direction=up", headers=headers
        )
    assert moved.status_code == 200
    assert len(reorder_spy) == 1
    assert _order(app, owner, wl) == [ids[0], ids[2], ids[1]]
    move_events = [r for r in caplog.records if getattr(r, "event", "") == "ui_item_moved"]
    assert len(move_events) == 1
    assert move_events[0].levelno == logging.INFO
    assert getattr(move_events[0], "direction", None) == "up"
    assert getattr(move_events[0], "item_id", None) == ids[2]

    caplog.clear()
    with caplog.at_level(logging.INFO, logger=_LOGGER):
        reordered = client.post(
            f"/web/wishlists/{wl}/items/reorder",
            data={"item_ids": [str(i) for i in reversed(ids)]},
            headers=headers,
        )
    assert reordered.status_code == 200
    assert len(reorder_spy) == 2
    assert _order(app, owner, wl) == list(reversed(ids))
    done = [r for r in caplog.records if getattr(r, "event", "") == "ui_items_reordered"]
    assert len(done) == 1
    assert done[0].levelno == logging.INFO
    assert getattr(done[0], "item_count", None) == 3


@pytest.mark.parametrize("send", [_reorder, _move])
def test_error_paths_emit_no_success_events(
    test_app: _Env, send: _Send, caplog: pytest.LogCaptureFixture
) -> None:
    """409 and 404 on reorder / move never log the success events."""
    client, sessions, app = test_app
    owner = make_user(101, "Alice")
    wl, ids = _seed(app, owner)

    with caplog.at_level(logging.INFO, logger=_LOGGER):
        missing = send(client, _MISSING_ID, ids[0], auth_header(sessions, 101))
        stranger = send(client, wl, ids[0], auth_header(sessions, 999, "Stranger"))
        asyncio.run(app.state.domain_service.archive_wishlist(wishlist_id=wl, actor=owner))
        archived = send(client, wl, ids[0], auth_header(sessions, 101))

    assert [missing.status_code, stranger.status_code, archived.status_code] == [404, 404, 409]
    assert not {"ui_items_reordered", "ui_item_moved"} & set(_events(caplog))
