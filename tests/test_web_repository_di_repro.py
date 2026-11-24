"""Reproduce full-scan WishlistStore.execute() usage and missing repository DI in web routes."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncConnection

from wishenka.auth.models import AuthenticatedUser, TelegramUser
from wishenka.auth.session import SessionTokenService
from wishenka.config import Settings
from wishenka.web.app import create_app
from wishenka.wishlists.repository import WishlistRepository
from wishenka.wishlists.store import WishlistStore

pytestmark = pytest.mark.timeout(30)


def _make_settings(db_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite+aiosqlite:///{db_path}",
        secret_key="test-web-repository-di-repro-secret",
    )


def _bearer(sessions: SessionTokenService, user_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {sessions.create_token(user_id, f'User {user_id}')}"}


def _forbid_full_scan(*_args: Any, **_kwargs: Any) -> Any:
    raise AssertionError("Full-scan WishlistStore.execute/_read must not be called")


def test_get_wishlist_repository_dependency_contract(tmp_path: Path) -> None:
    """wishenka.web.dependencies.get_wishlist_repository yields a bound WishlistRepository."""
    from wishenka.web.dependencies import WishlistRepo, get_wishlist_repository

    assert WishlistRepo is not None

    settings = _make_settings(tmp_path / "deps_contract.db")
    app = create_app(settings)

    async def _check_dependency() -> None:
        store: WishlistStore = app.state.wishlist_store
        gen = get_wishlist_repository(store)
        repo = await gen.__anext__()
        try:
            assert isinstance(repo, WishlistRepository)
            assert isinstance(repo.conn, AsyncConnection)
        finally:
            await gen.aclose()  # type: ignore[attr-defined]

    with TestClient(app):
        asyncio.run(_check_dependency())


@pytest.mark.parametrize(
    ("method", "path_template", "user_id", "payload", "expected_status"),
    [
        ("GET", "/api/wishlists", 101, None, 200),
        ("POST", "/api/wishlists", 101, {"name": "New List"}, 201),
        ("GET", "/api/wishlists/{wishlist_id}", 101, None, 200),
        ("GET", "/api/wishlists/{wishlist_id}/items", 101, None, 200),
        ("POST", "/api/wishlists/{wishlist_id}/items", 101, {"title": "New Item"}, 201),
        ("GET", "/share/{public_token}", 202, None, 200),
        ("GET", "/api/wishlists/{wishlist_id}/gifted", 101, None, 200),
        ("GET", "/web/wishlists/{wishlist_id}", 101, None, 200),
        ("GET", "/web/wishlists/{wishlist_id}/items/{item_id}/receipt", 101, None, 200),
    ],
)
def test_web_routes_do_not_call_full_scan_wishlist_store_execute(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path_template: str,
    user_id: int,
    payload: dict[str, Any] | None,
    expected_status: int,
) -> None:
    """Representative web routes must use WishlistRepository DI without WishlistStore.execute()."""
    settings = _make_settings(tmp_path / "routes_di.db")
    app = create_app(settings)
    sessions = SessionTokenService(settings.secret_key)
    owner = AuthenticatedUser(telegram_id=101, first_name="Owner", auth_method="session_token")

    with TestClient(app) as client:

        async def _seed() -> tuple[int, int, str]:
            await app.state.user_store.upsert_user(TelegramUser(id=101, first_name="Owner"))
            await app.state.user_store.upsert_user(TelegramUser(id=202, first_name="Gifter"))
            wishlist = await app.state.domain_service.create_wishlist(owner, title="Birthday")
            item = await app.state.domain_service.add_wish_item(
                wishlist_id=wishlist.id,
                actor=owner,
                title="Camera",
                quantity=2,
            )
            return int(wishlist.id), int(item.id), str(wishlist.public_token)

        wishlist_id, item_id, public_token = asyncio.run(_seed())

        monkeypatch.setattr(WishlistStore, "execute", _forbid_full_scan)
        monkeypatch.setattr(WishlistStore, "_read", _forbid_full_scan)

        path = path_template.format(
            wishlist_id=wishlist_id,
            item_id=item_id,
            public_token=public_token,
        )
        response = client.request(
            method,
            path,
            json=payload,
            headers=_bearer(sessions, user_id),
        )
        assert response.status_code == expected_status
