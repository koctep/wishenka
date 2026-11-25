"""Automated observability tests for WISHENKA-9 (Wishlist sections, favorites, and view history).

Verifies structured logging:
- INFO: favorite_added, favorite_removed, favorites_listed, view_history_recorded,
        view_history_listed, view_history_cleared.
- WARNING: unauthorized attempts, self-favoriting attempt (favorite_own_wishlist_denied),
           deleted wishlist access (favorite_deleted_wishlist_denied).
- Redaction: Zero leak of tokens, session secrets, reservation details, or large payloads.
"""

import asyncio
import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from wishenka.auth.models import AuthenticatedUser, TelegramUser
from wishenka.auth.session import SessionTokenService
from wishenka.config import Settings
from wishenka.web.app import create_app
from wishenka.wishlists.exceptions import WishlistNotFoundError
from wishenka.wishlists.service import WishlistService

pytestmark = pytest.mark.timeout(30)


@pytest.fixture
def obs_app(tmp_path: Path) -> Iterator[tuple[TestClient, SessionTokenService, FastAPI]]:
    """Initialize isolated test client and session token service with database."""
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'obs_sections.db'}",
        secret_key="sections-obs-secret-token",
    )
    app = create_app(settings)
    sessions = SessionTokenService(settings.secret_key)
    with TestClient(app) as client:
        yield client, sessions, app


def bearer(sessions: SessionTokenService, user_id: int) -> dict[str, str]:
    """Generate Authorization header with Bearer token."""
    return {"Authorization": f"Bearer {sessions.create_token(user_id, f'User{user_id}')}"}


def test_favorites_lifecycle_observability(
    obs_app: tuple[TestClient, SessionTokenService, FastAPI],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify structured INFO logging for favorite_added, favorites_listed, and favorite_removed."""
    client, sessions, app = obs_app
    service: WishlistService = app.state.domain_service

    owner = AuthenticatedUser(telegram_id=101, first_name="Owner", auth_method="session_token")
    headers = bearer(sessions, 202)

    async def seed() -> tuple[int, str]:
        await app.state.user_store.upsert_user(TelegramUser(id=202, first_name="User"))
        wl = await service.create_wishlist(owner, title="Observability Wishlist")
        return wl.id, wl.public_token

    wl_id, public_token = asyncio.run(seed())
    assert (
        client.get(f"/api/public/wishlists/{public_token}/view", headers=headers).status_code == 200
    )

    # 1. Add favorite -> favorite_added
    with caplog.at_level(logging.INFO, logger="wishenka.web.wishlists"):
        resp = client.post(f"/api/favorites/{wl_id}", headers=headers)
        assert resp.status_code == 200

    add_records = [
        r
        for r in caplog.records
        if r.name == "wishenka.web.wishlists"
        and r.levelname == "INFO"
        and getattr(r, "event", None) == "favorite_added"
    ]
    assert len(add_records) >= 1
    assert getattr(add_records[0], "wishlist_id", None) == wl_id
    assert getattr(add_records[0], "user_id", None) == 202

    # 2. List favorites -> favorites_listed
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="wishenka.web.wishlists"):
        resp = client.get("/api/favorites", headers=headers)
        assert resp.status_code == 200

    list_records = [
        r
        for r in caplog.records
        if r.name == "wishenka.web.wishlists"
        and r.levelname == "INFO"
        and getattr(r, "event", None) == "favorites_listed"
    ]
    assert len(list_records) >= 1
    assert getattr(list_records[0], "user_id", None) == 202
    assert getattr(list_records[0], "count", None) == 1

    # 3. Remove favorite -> favorite_removed
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="wishenka.web.wishlists"):
        resp = client.delete(f"/api/favorites/{wl_id}", headers=headers)
        assert resp.status_code == 200

    remove_records = [
        r
        for r in caplog.records
        if r.name == "wishenka.web.wishlists"
        and r.levelname == "INFO"
        and getattr(r, "event", None) == "favorite_removed"
    ]
    assert len(remove_records) >= 1
    assert getattr(remove_records[0], "wishlist_id", None) == wl_id
    assert getattr(remove_records[0], "user_id", None) == 202


def test_view_history_lifecycle_observability(
    obs_app: tuple[TestClient, SessionTokenService, FastAPI],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify structured INFO logging for view history operations."""
    client, sessions, app = obs_app
    service: WishlistService = app.state.domain_service

    owner = AuthenticatedUser(telegram_id=101, first_name="Owner", auth_method="session_token")
    headers = bearer(sessions, 202)

    async def seed() -> int:
        await app.state.user_store.upsert_user(TelegramUser(id=202, first_name="User"))
        wl = await service.create_wishlist(owner, title="History Obs Wishlist")
        return wl.id

    wl_id = asyncio.run(seed())

    # 1. Record view -> view_history_recorded
    with caplog.at_level(logging.INFO, logger="wishenka.web.wishlists"):
        resp = client.post(f"/api/history/{wl_id}", headers=headers)
        assert resp.status_code == 200

    rec_records = [
        r
        for r in caplog.records
        if r.name == "wishenka.web.wishlists"
        and r.levelname == "INFO"
        and getattr(r, "event", None) == "view_history_recorded"
    ]
    assert len(rec_records) >= 1
    assert getattr(rec_records[0], "wishlist_id", None) == wl_id
    assert getattr(rec_records[0], "user_id", None) == 202

    # 2. List history -> view_history_listed
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="wishenka.web.wishlists"):
        resp = client.get("/api/history", headers=headers)
        assert resp.status_code == 200

    hist_records = [
        r
        for r in caplog.records
        if r.name == "wishenka.web.wishlists"
        and r.levelname == "INFO"
        and getattr(r, "event", None) == "view_history_listed"
    ]
    assert len(hist_records) >= 1
    assert getattr(hist_records[0], "user_id", None) == 202
    assert getattr(hist_records[0], "count", None) == 1

    # 3. Clear history -> view_history_cleared
    caplog.clear()
    with (
        caplog.at_level(logging.INFO, logger="wishenka.web.wishlists"),
        caplog.at_level(logging.INFO, logger="wishenka.wishlists"),
    ):
        resp = client.delete("/api/history", headers=headers)
        assert resp.status_code == 200

    cleared = [r for r in caplog.records if getattr(r, "event", None) == "view_history_cleared"]
    assert len(cleared) == 1
    assert getattr(cleared[0], "user_id", None) == 202
    assert getattr(cleared[0], "removed_count", None) == 1
    assert "History Obs Wishlist" not in cleared[0].getMessage()


def test_warning_on_self_favoriting_and_deleted_wishlists(
    obs_app: tuple[TestClient, SessionTokenService, FastAPI],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify WARNING logs for favorite_own_wishlist_denied and favorite_deleted_wishlist_denied."""
    client, sessions, app = obs_app
    service: WishlistService = app.state.domain_service

    alice = AuthenticatedUser(telegram_id=101, first_name="Alice", auth_method="session_token")
    alice_headers = bearer(sessions, 101)
    bob_headers = bearer(sessions, 202)

    async def seed() -> tuple[int, int]:
        wl_alice = await service.create_wishlist(alice, title="Alice Active List")
        wl_deleted = await service.create_wishlist(alice, title="Alice Deleted List")
        await service.delete_wishlist(wl_deleted.id, actor=alice)
        return wl_alice.id, wl_deleted.id

    alice_wl_id, deleted_wl_id = asyncio.run(seed())

    # 1. Alice tries to favorite her own wishlist -> WARNING favorite_own_wishlist_denied
    with caplog.at_level(logging.WARNING, logger="wishenka.wishlists"):
        resp = client.post(f"/api/favorites/{alice_wl_id}", headers=alice_headers)
        assert resp.status_code == 400

    own_warn = [
        r
        for r in caplog.records
        if r.name == "wishenka.wishlists"
        and r.levelname == "WARNING"
        and getattr(r, "event", None) == "favorite_own_wishlist_denied"
    ]
    assert len(own_warn) >= 1
    assert getattr(own_warn[0], "wishlist_id", None) == alice_wl_id
    assert getattr(own_warn[0], "user_id", None) == 101

    # 2. Bob tries to favorite deleted wishlist -> WARNING favorite_deleted_wishlist_denied
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="wishenka.wishlists"):
        resp_del = client.post(f"/api/favorites/{deleted_wl_id}", headers=bob_headers)
        assert resp_del.status_code == 404

    del_warn = [
        r
        for r in caplog.records
        if r.name == "wishenka.wishlists"
        and r.levelname == "WARNING"
        and getattr(r, "event", None) == "favorite_deleted_wishlist_denied"
    ]
    assert len(del_warn) >= 1
    assert getattr(del_warn[0], "wishlist_id", None) == deleted_wl_id

    # 3. Bob tries to record view for deleted wishlist -> WARNING favorite_deleted_wishlist_denied
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="wishenka.web.wishlists"):
        resp_view_del = client.post(f"/api/history/{deleted_wl_id}", headers=bob_headers)
        assert resp_view_del.status_code == 404

    view_del_warn = [
        r
        for r in caplog.records
        if r.name == "wishenka.web.wishlists"
        and r.levelname == "WARNING"
        and getattr(r, "event", None) == "favorite_deleted_wishlist_denied"
    ]
    assert len(view_del_warn) >= 1
    assert getattr(view_del_warn[0], "wishlist_id", None) == deleted_wl_id


def test_unauthorized_attempts_warning_logs(
    obs_app: tuple[TestClient, SessionTokenService, FastAPI],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify unauthorized attempts to favorites or history trigger WARNING logs."""
    client, _, _ = obs_app

    with caplog.at_level(logging.WARNING, logger="wishenka.auth"):
        # Without any authorization headers
        resp_fav = client.get("/api/favorites")
        assert resp_fav.status_code == 401

        resp_hist = client.get("/api/history")
        assert resp_hist.status_code == 401

        resp_post_fav = client.post("/api/favorites/123")
        assert resp_post_fav.status_code == 401

    auth_warns = [
        r
        for r in caplog.records
        if r.name == "wishenka.auth"
        and r.levelname == "WARNING"
        and getattr(r, "event", None) == "auth_failure"
    ]
    assert len(auth_warns) == 3


def test_redaction_zero_leak_in_observability(
    obs_app: tuple[TestClient, SessionTokenService, FastAPI],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Ensure zero leak of secrets, sharing tokens, reservation details, or large payloads."""
    client, sessions, app = obs_app
    service: WishlistService = app.state.domain_service

    owner = AuthenticatedUser(telegram_id=101, first_name="Owner", auth_method="session_token")
    gifter = AuthenticatedUser(telegram_id=202, first_name="Gifter", auth_method="session_token")
    gifter_headers = bearer(sessions, 202)

    async def seed() -> tuple[int, str, str]:
        await app.state.user_store.upsert_user(TelegramUser(id=202, first_name="Gifter"))
        wl = await service.create_wishlist(owner, title="Secret Redaction Wishlist")
        item = await service.add_wish_item(
            wishlist_id=wl.id, actor=owner, title="Secret PlayStation 5", quantity=1
        )
        # Gifter reserves item
        await service.create_reservation(item.id, gifter, quantity=1)
        return wl.id, wl.invite_token, wl.public_token

    wl_id, invite_token, public_token = asyncio.run(seed())

    # Grant share-link access before capturing debug logs so httpx request URL is not in caplog
    assert (
        client.get(f"/api/public/wishlists/{public_token}/view", headers=gifter_headers).status_code
        == 200
    )
    caplog.clear()

    with caplog.at_level(logging.DEBUG):
        # Favorite the list
        client.post(f"/api/favorites/{wl_id}", headers=gifter_headers)
        client.get("/api/favorites", headers=gifter_headers)
        client.post(f"/api/history/{wl_id}", headers=gifter_headers)
        client.get("/api/history", headers=gifter_headers)
        client.delete(f"/api/favorites/{wl_id}", headers=gifter_headers)
        client.delete("/api/history", headers=gifter_headers)

    full_log = caplog.text

    # Zero leak assertion
    assert invite_token not in full_log, "Invite token leaked in logs!"
    assert public_token not in full_log, "Public token leaked in logs!"
    assert "PlayStation" not in full_log, "Item title leaked in logs!"
    assert "is_reserved_by_me" not in full_log, "Reservation details leaked in logs!"
    assert "reserved_quantity" not in full_log, "Reservation quantities leaked in logs!"


@pytest.mark.asyncio
async def test_domain_service_favorites_and_history_logging(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Validate WishlistService direct logging for all favorites and history events."""
    service = WishlistService.in_memory()
    owner = AuthenticatedUser(telegram_id=1001, first_name="Owner", auth_method="session_token")
    user = AuthenticatedUser(telegram_id=2002, first_name="User", auth_method="session_token")

    wl = await service.create_wishlist(owner=owner, title="Domain List")
    await service.get_wishlist_by_public_token(wl.public_token, user)

    with caplog.at_level(logging.INFO, logger="wishenka.wishlists"):
        await service.add_favorite(user, wl.id)
        await service.list_favorites(user)
        await service.record_view(user, wl.id)
        await service.get_history(user)
        await service.remove_favorite(user, wl.id)
        await service.clear_history(user)

    events = [getattr(r, "event", None) for r in caplog.records if r.name == "wishenka.wishlists"]
    assert "favorite_added" in events
    assert "favorites_listed" in events
    assert "view_history_recorded" in events
    assert "view_history_listed" in events
    assert "favorite_removed" in events
    assert "view_history_cleared" in events


@pytest.mark.asyncio
async def test_domain_service_warnings_on_violations(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Validate WishlistService warnings on self-favoriting and deleted wishlist access."""
    service = WishlistService.in_memory()
    owner = AuthenticatedUser(telegram_id=1001, first_name="Owner", auth_method="session_token")
    user = AuthenticatedUser(telegram_id=2002, first_name="User", auth_method="session_token")

    wl = await service.create_wishlist(owner=owner, title="Domain List")
    await service.get_wishlist_by_public_token(wl.public_token, user)
    del_wl = await service.create_wishlist(owner=owner, title="Deleted List")
    await service.delete_wishlist(del_wl.id, actor=owner)

    with caplog.at_level(logging.WARNING, logger="wishenka.wishlists"):
        with pytest.raises(ValueError):
            await service.add_favorite(owner, wl.id)
        with pytest.raises(WishlistNotFoundError):
            await service.add_favorite(user, del_wl.id)
        with pytest.raises(WishlistNotFoundError):
            await service.record_view(user, del_wl.id)

    events = [getattr(r, "event", None) for r in caplog.records if r.name == "wishenka.wishlists"]
    assert "favorite_own_wishlist_denied" in events
    assert events.count("favorite_deleted_wishlist_denied") == 2
