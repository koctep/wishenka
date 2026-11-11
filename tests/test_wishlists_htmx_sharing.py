"""Failing repro test suite for WISHENKA-51.

Tests FastAPI endpoints and HTMX views for wishlist sharing, collaborator invitations,
member management, and share modal regeneration with strict Surprise Invariant enforcement.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from wishenka.auth.models import AuthenticatedUser
from wishenka.auth.session import SessionTokenService
from wishenka.config import Settings
from wishenka.web.app import create_app
from wishenka.wishlists.models import WishlistRole
from wishenka.wishlists.service import WishlistService

pytestmark = pytest.mark.timeout(10)


def make_user(telegram_id: int, first_name: str, username: str | None = None) -> AuthenticatedUser:
    """Create test AuthenticatedUser instance."""
    return AuthenticatedUser(
        telegram_id=telegram_id,
        first_name=first_name,
        username=username,
        auth_method="session_token",
    )


def bearer(sessions: SessionTokenService, user_id: int) -> dict[str, str]:
    """Authenticate as a test user via Bearer token."""
    return {"Authorization": f"Bearer {sessions.create_token(user_id, 'User')}"}


@pytest.fixture
def test_app(tmp_path: Path) -> Iterator[tuple[TestClient, SessionTokenService, FastAPI]]:
    """Initialize test client and session token service with isolated database."""
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'htmx_sharing.db'}",
        secret_key="htmx-sharing-test-secret",
    )
    app = create_app(settings)
    sessions = SessionTokenService(settings.secret_key)
    with TestClient(app) as client:
        yield client, sessions, app


def test_public_share_view_guest_sees_reservations_and_items(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """Public share view renders wishlist HTML with item cards and reservation availability."""
    client, sessions, app = test_app
    service: WishlistService = app.state.domain_service
    owner = make_user(101, "Alice")
    gifter = make_user(202, "Bob")

    async def seed() -> tuple[int, str, str, int, int]:
        wl = await service.create_wishlist(owner=owner, title="Alice's Birthday")
        item1 = await service.add_wish_item(
            wishlist_id=wl.id,
            actor=owner,
            title="Board Game",
            quantity=2,
        )
        item2 = await service.add_wish_item(
            wishlist_id=wl.id,
            actor=owner,
            title="Wireless Headphones",
            quantity=1,
        )
        await service.create_reservation(item_id=item2.id, user=gifter, quantity=1)
        return wl.id, str(wl.public_token), str(wl.invite_token), item1.id, item2.id

    wl_id, public_token, invite_token, item1_id, item2_id = asyncio.run(seed())

    # Guest requests public view
    response = client.get(f"/share/{public_token}")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    html = response.text
    assert "Alice's Birthday" in html
    assert "Board Game" in html
    assert "Wireless Headphones" in html
    # Invite token must never be leaked on public share page
    assert invite_token not in html

    # Gifter views wishlist and sees items
    gifter_headers = bearer(sessions, 202)
    gifter_resp = client.get(f"/share/{public_token}", headers=gifter_headers)
    assert gifter_resp.status_code == 200
    assert "Wireless Headphones" in gifter_resp.text

    # HTMX partial card endpoint
    card_resp = client.get(
        f"/wishlists/{wl_id}/items/{item2_id}/card",
        headers={"HX-Request": "true"} | gifter_headers,
    )
    assert card_resp.status_code == 200
    assert "text/html" in card_resp.headers["content-type"]
    assert "Wireless Headphones" in card_resp.text


def test_public_share_view_owner_surprise_invariant(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """When owner/recipient views their wishlist, reservations and buyers are stripped."""
    client, sessions, app = test_app
    service: WishlistService = app.state.domain_service
    owner = make_user(101, "Alice")
    gifter = make_user(202, "Bob")

    async def seed() -> tuple[int, str, int]:
        wl = await service.create_wishlist(owner=owner, title="Surprise Wishlist")
        item = await service.add_wish_item(
            wishlist_id=wl.id,
            actor=owner,
            title="Mystery Watch",
            quantity=1,
        )
        await service.create_reservation(item_id=item.id, user=gifter, quantity=1)
        return wl.id, str(wl.public_token), item.id

    wl_id, public_token, item_id = asyncio.run(seed())

    # Owner views their wishlist via public link with auth header
    owner_headers = bearer(sessions, 101)
    response = client.get(f"/share/{public_token}", headers=owner_headers)
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    html = response.text
    assert "Mystery Watch" in html

    # Strictly verify Surprise Invariant in rendered HTML:
    # 1. Gifter's name or ID must NOT appear anywhere in the page
    assert "Bob" not in html
    assert "202" not in html
    # 2. Reservation indicators must NOT be rendered for recipient/owner
    lower_html = html.lower()
    assert "забронировано" not in lower_html
    assert "reserved" not in lower_html

    # Also test HTMX partial card endpoint for owner
    card_resp = client.get(
        f"/wishlists/{wl_id}/items/{item_id}/card",
        headers={"HX-Request": "true"} | owner_headers,
    )
    assert card_resp.status_code == 200
    card_html = card_resp.text
    assert "Mystery Watch" in card_html
    assert "Bob" not in card_html
    assert "202" not in card_html
    assert "забронировано" not in card_html.lower()
    assert "reserved" not in card_html.lower()


def test_invite_preview_page(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """Invite preview page renders preview card with title, owner name, and join action."""
    client, sessions, app = test_app
    service: WishlistService = app.state.domain_service
    owner = make_user(101, "Alice")

    async def seed() -> tuple[int, str]:
        wl = await service.create_wishlist(owner=owner, title="Trip to Altai")
        return wl.id, str(wl.invite_token)

    wl_id, invite_token = asyncio.run(seed())

    response = client.get(f"/invite/{invite_token}")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    html = response.text
    assert "Trip to Altai" in html
    assert "Alice" in html
    assert f"/invite/{invite_token}/join" in html


def test_invite_join_htmx_success(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """Joining via HTMX POST adds user as member and returns updated UI fragment or redirect."""
    client, sessions, app = test_app
    service: WishlistService = app.state.domain_service
    owner = make_user(101, "Alice")

    async def seed() -> tuple[int, str, str]:
        wl = await service.create_wishlist(owner=owner, title="Shared Project")
        return wl.id, str(wl.invite_token), str(wl.public_token)

    wl_id, invite_token, public_token = asyncio.run(seed())

    # User Charlie accepts invite via HTMX POST
    joiner_headers = bearer(sessions, 303) | {"HX-Request": "true"}
    response = client.post(
        f"/invite/{invite_token}/join",
        headers=joiner_headers,
    )
    assert response.status_code in (200, 303)
    if response.status_code == 200:
        assert (
            "text/html" in response.headers.get("content-type", "")
            or "HX-Redirect" in response.headers
        )

    # Verify Charlie is now a member with role MEMBER
    async def verify_member() -> bool:
        members = await service.get_members(wl_id, actor=owner)
        return any(m.user_id == 303 and m.role == WishlistRole.MEMBER for m in members)

    assert asyncio.run(verify_member()) is True


def test_invite_expired_or_invalid_error_card(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """Expired or invalid invite token renders a friendly error card rather than raw JSON."""
    client, sessions, app = test_app
    service: WishlistService = app.state.domain_service
    owner = make_user(101, "Alice")

    async def seed() -> str:
        wl = await service.create_wishlist(
            owner=owner,
            title="Old Wishlist",
            invite_token_expires_in=timedelta(seconds=-10),
        )
        return str(wl.invite_token)

    expired_token = asyncio.run(seed())

    # 1. Expired invite token
    resp_expired = client.get(f"/invite/{expired_token}")
    assert resp_expired.status_code in (200, 404)
    assert "text/html" in resp_expired.headers["content-type"]
    text_expired = resp_expired.text.lower()
    assert any(term in text_expired for term in ("истек", "недействительн", "expired"))

    # 2. Completely invalid/unknown token
    resp_invalid = client.get("/invite/non-existent-token-12345")
    assert resp_invalid.status_code in (200, 404)
    assert "text/html" in resp_invalid.headers["content-type"]
    text_invalid = resp_invalid.text.lower()
    assert any(term in text_invalid for term in ("недействительн", "не найден", "истек", "invalid"))


def test_members_partial_view_and_management(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """Members partial renders member list with roles; deletion revokes member."""
    client, sessions, app = test_app
    service: WishlistService = app.state.domain_service
    owner = make_user(101, "Alice")

    async def seed() -> int:
        wl = await service.create_wishlist(owner=owner, title="Collab Wishlist")
        await service.add_member(wl.id, owner, 202, WishlistRole.MEMBER)
        await service.add_member(wl.id, owner, 303, WishlistRole.ADMIN)
        return wl.id

    wl_id = asyncio.run(seed())
    owner_headers = bearer(sessions, 101)

    # 1. Owner requests members partial
    resp = client.get(f"/wishlists/{wl_id}/members/partial", headers=owner_headers)
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    html = resp.text
    assert any(r in html.lower() for r in ("владелец", "owner"))
    assert any(r in html.lower() for r in ("администратор", "admin"))
    assert any(r in html.lower() for r in ("участник", "member"))
    assert f"/wishlists/{wl_id}/members/202/partial" in html

    # 2. Owner removes member 202
    del_resp = client.delete(
        f"/wishlists/{wl_id}/members/202/partial",
        headers=owner_headers | {"HX-Request": "true"},
    )
    assert del_resp.status_code == 200
    assert "text/html" in del_resp.headers["content-type"]
    assert f"/wishlists/{wl_id}/members/202/partial" not in del_resp.text

    # Verify in service that 202 is removed
    async def verify_removed() -> bool:
        members = await service.get_members(wl_id, actor=owner)
        return all(m.user_id != 202 for m in members)

    assert asyncio.run(verify_removed()) is True

    # 3. Unauthorized removal: stranger cannot delete members
    stranger_headers = bearer(sessions, 999)
    unauth_resp = client.delete(
        f"/wishlists/{wl_id}/members/303/partial",
        headers=stranger_headers,
    )
    assert unauth_resp.status_code in (401, 403, 404)


def test_share_modal_partial_and_regeneration(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """Share modal renders tokens and allows regenerating invite link via HTMX."""
    client, sessions, app = test_app
    service: WishlistService = app.state.domain_service
    owner = make_user(101, "Alice")

    async def seed() -> tuple[int, str, str]:
        wl = await service.create_wishlist(owner=owner, title="Sharing Modal Test")
        return wl.id, str(wl.public_token), str(wl.invite_token)

    wl_id, public_token, old_invite = asyncio.run(seed())
    owner_headers = bearer(sessions, 101)

    # 1. Owner requests share modal partial
    modal_resp = client.get(f"/wishlists/{wl_id}/share-modal", headers=owner_headers)
    assert modal_resp.status_code == 200
    assert "text/html" in modal_resp.headers["content-type"]
    modal_html = modal_resp.text
    assert public_token in modal_html
    assert old_invite in modal_html
    assert f"/wishlists/{wl_id}/invite/regenerate" in modal_html

    # 2. Owner regenerates invite token via HTMX POST
    regen_resp = client.post(
        f"/wishlists/{wl_id}/invite/regenerate",
        headers=owner_headers | {"HX-Request": "true"},
    )
    assert regen_resp.status_code == 200
    assert "text/html" in regen_resp.headers["content-type"]
    regen_html = regen_resp.text
    assert old_invite not in regen_html

    # Old invite token cannot be used anymore
    old_invite_resp = client.get(f"/invite/{old_invite}")
    assert old_invite_resp.status_code in (200, 404)
    assert any(
        term in old_invite_resp.text.lower() for term in ("истек", "недействительн", "expired")
    )

    # 3. Non-owner cannot access share modal
    stranger_headers = bearer(sessions, 999)
    stranger_resp = client.get(f"/wishlists/{wl_id}/share-modal", headers=stranger_headers)
    assert stranger_resp.status_code in (401, 403, 404)
