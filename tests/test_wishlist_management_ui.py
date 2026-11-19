"""Integration regressions for Mini App wishlist management and invitations."""

import asyncio
import hashlib
import hmac
import json
import logging
import time
import urllib.parse
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from wishenka.auth.models import AuthenticatedUser, TelegramUser
from wishenka.auth.session import SessionTokenService
from wishenka.config import Settings
from wishenka.web.app import create_app
from wishenka.wishlists.models import WishlistRole

pytestmark = pytest.mark.timeout(30)

ORIGIN = "http://testserver"
Setup = tuple[TestClient, SessionTokenService, int, str, str, str]


@pytest.fixture
def setup_app(tmp_path: Path) -> Iterator[Setup]:
    """Provide a real transactional store with owner, admin and ordinary member."""
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'management.db'}",
        secret_key="management-test-secret",
    )
    app = create_app(settings)
    owner = AuthenticatedUser(telegram_id=101, first_name="Owner", auth_method="session_token")
    sessions = SessionTokenService(settings.secret_key)
    with TestClient(app) as client:

        async def seed() -> tuple[int, str, str, str]:
            for uid, name in ((101, "Owner"), (202, "Admin"), (303, "Member"), (404, "Joiner")):
                await app.state.user_store.upsert_user(TelegramUser(id=uid, first_name=name))
            service = app.state.domain_service
            user_store = app.state.user_store
            await user_store.upsert_user(TelegramUser(id=101, first_name="Owner"))
            await user_store.upsert_user(TelegramUser(id=202, first_name="Admin"))
            await user_store.upsert_user(TelegramUser(id=303, first_name="Member"))
            await user_store.upsert_user(TelegramUser(id=404, first_name="Guest"))
            wishlist = await service.create_wishlist(owner, title="Party")
            await service.add_member(wishlist.id, owner, 202, WishlistRole.ADMIN)
            await service.add_member(wishlist.id, owner, 303, WishlistRole.MEMBER)
            expired = await service.create_wishlist(
                owner, title="Expired", invite_token_expires_in=timedelta(seconds=-10)
            )
            return (
                int(wishlist.id),
                str(wishlist.invite_token),
                str(wishlist.public_token),
                str(expired.invite_token),
            )

        wishlist_id, invite, public, expired = asyncio.run(seed())
        yield client, sessions, wishlist_id, invite, public, expired


def bearer(sessions: SessionTokenService, user_id: int) -> dict[str, str]:
    """Authenticate as a known seeded user without contacting Telegram."""
    return {"Authorization": f"Bearer {sessions.create_token(user_id, 'User')}"}


def test_mini_app_shell_and_empty_wishlist_creation(setup_app: Setup) -> None:
    """A user can reach the Mini App and create a list without supplying fields."""
    client, sessions, _, _, _, _ = setup_app
    shell = client.get("/")
    assert shell.status_code == 200
    assert "text/html" in shell.headers["content-type"]
    created = client.post("/api/wishlists", json={}, headers=bearer(sessions, 101))
    assert created.status_code == 201
    assert created.json()["id"]


def test_member_controls_cannot_be_forged_by_non_owner(setup_app: Setup) -> None:
    """Owner sees roles; an admin cannot modify or remove another administrator."""
    client, sessions, wishlist_id, _, _, _ = setup_app
    path = f"/api/wishlists/{wishlist_id}/members"
    owner_headers = bearer(sessions, 101)
    admin_headers = bearer(sessions, 202)
    listed = client.get(path, headers=owner_headers)
    assert listed.status_code == 200
    assert any(member["user_id"] == 202 and member["role"] == "admin" for member in listed.json())
    assert (
        client.patch(path + "/303/role", json={"role": "admin"}, headers=admin_headers).status_code
        == 404
    )
    assert client.delete(path + "/202", headers=admin_headers).status_code == 404
    assert client.delete(path + "/101", headers=admin_headers).status_code == 404
    after = client.get(path, headers=owner_headers).json()
    assert any(member["user_id"] == 303 and member["role"] == "member" for member in after)
    assert any(member["user_id"] == 202 and member["role"] == "admin" for member in after)


def test_invitation_preview_is_read_only_and_confirmed_join_preserves_roles(
    setup_app: Setup,
) -> None:
    """Preview grants nothing; explicit acceptance joins and never demotes existing users."""
    client, sessions, wishlist_id, invite, _, _ = setup_app
    invitation = {"X-Invite-Token": invite}
    before = client.get(f"/api/wishlists/{wishlist_id}", headers=bearer(sessions, 404))
    assert before.status_code == 404
    preview = client.get("/api/invitations/preview", headers=invitation)
    assert preview.status_code == 200
    assert preview.json() == {"name": "Party", "access": "member"}
    assert (
        client.get(f"/api/wishlists/{wishlist_id}", headers=bearer(sessions, 404)).status_code
        == 404
    )
    for user_id, role in ((404, "member"), (101, "owner"), (202, "admin")):
        headers = invitation | bearer(sessions, user_id)
        accepted = client.post("/api/invitations/accept", json={}, headers=headers)
        assert accepted.status_code == 200
        assert accepted.json() == {"wishlist_id": wishlist_id, "role": role}


def test_invitation_validity_reset_and_secret_redaction(
    setup_app: Setup, caplog: pytest.LogCaptureFixture
) -> None:
    """Expired, stale, public and invalid capabilities cannot be used as invitations."""
    client, sessions, wishlist_id, invite, public, expired = setup_app
    with caplog.at_level(logging.DEBUG):
        valid = client.get("/api/invitations/preview", headers={"X-Invite-Token": invite})
        assert valid.status_code == 200
        for invalid in (expired, public, "unknown-secret-capability"):
            response = client.get("/api/invitations/preview", headers={"X-Invite-Token": invalid})
            assert response.status_code == 404
            assert invalid not in response.text
        reset = client.post(
            f"/api/wishlists/{wishlist_id}/invite/reset", headers=bearer(sessions, 101)
        )
        assert reset.status_code == 200
        assert (
            client.get("/api/invitations/preview", headers={"X-Invite-Token": invite}).status_code
            == 404
        )
        stale_headers = bearer(sessions, 404) | {"X-Invite-Token": invite}
        assert (
            client.post("/api/invitations/accept", json={}, headers=stale_headers).status_code
            == 404
        )
    for secret in (invite, public, expired, "unknown-secret-capability"):
        assert secret not in caplog.text


def test_cookie_mutations_require_session_bound_csrf_and_origin(setup_app: Setup) -> None:
    """Missing, incorrect and old-session CSRF values cannot authorize a cookie request."""
    client, sessions, wishlist_id, _, _, _ = setup_app
    owner_cookie = sessions.create_token(101, "Owner")
    client.cookies.set("session_id", owner_cookie)
    csrf_response = client.get("/api/auth/csrf")
    assert csrf_response.status_code == 200
    assert "no-store" in csrf_response.headers.get("cache-control", "")
    csrf = csrf_response.json()["csrf_token"]
    path = f"/api/wishlists/{wishlist_id}/invite/reset"
    assert client.post(path, headers={"Origin": ORIGIN}).status_code == 403
    assert (
        client.post(path, headers={"Origin": ORIGIN, "X-CSRF-Token": "incorrect"}).status_code
        == 403
    )
    assert (
        client.post(
            path, headers={"Origin": "https://evil.example", "X-CSRF-Token": csrf}
        ).status_code
        == 403
    )
    client.cookies.set("session_id", sessions.create_token(202, "Admin"))
    assert client.post(path, headers={"Origin": ORIGIN, "X-CSRF-Token": csrf}).status_code == 403
    current_csrf = client.get("/api/auth/csrf").json()["csrf_token"]
    assert (
        client.post(path, headers={"Origin": ORIGIN, "X-CSRF-Token": current_csrf}).status_code
        == 200
    )


def test_archived_list_rejects_stale_member_actions(setup_app: Setup) -> None:
    """A stale manager cannot modify membership or issue invitations after archive."""
    client, sessions, wishlist_id, _, _, _ = setup_app
    headers = bearer(sessions, 101)
    path = f"/api/wishlists/{wishlist_id}"
    assert client.get(path + "/members", headers=headers).status_code == 200
    assert client.post(path + "/archive", headers=headers).status_code == 200
    assert client.delete(path + "/members/303", headers=headers).status_code == 409
    assert client.post(path + "/invite/reset", headers=headers).status_code == 409


def test_anonymous_public_display_ignores_stale_session_and_hides_reservation(
    setup_app: Setup,
) -> None:
    """A public recipient can open the list without onboarding or reservation disclosure."""
    client, _, wishlist_id, _, public, _ = setup_app
    owner = AuthenticatedUser(telegram_id=101, first_name="Owner", auth_method="session_token")
    giver = AuthenticatedUser(telegram_id=505, first_name="Giver", auth_method="session_token")
    service = cast(FastAPI, client.app).state.domain_service

    async def reserve() -> None:
        item = await service.add_wish_item(wishlist_id=wishlist_id, actor=owner, title="Book")
        await service.create_reservation(item_id=item.id, user=giver, quantity=1)

    asyncio.run(reserve())
    client.cookies.set("session_id", "expired-or-invalid")
    response = client.get(f"/api/public/wishlists/{public}")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["title"] == "Book"
    assert {
        "available_quantity",
        "reserved_quantity",
        "is_fully_reserved",
        "reservations",
        "giver",
        "comments",
    }.isdisjoint(items[0])


def test_telegram_bootstrap_enforces_origin_before_setting_session(setup_app: Setup) -> None:
    """A valid signed Telegram payload cannot set a session from a foreign origin."""
    client, _, _, _, _, _ = setup_app
    user = json.dumps({"id": 101, "first_name": "Owner"}, separators=(",", ":"))
    fields = {"auth_date": str(int(time.time())), "user": user}
    check = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", b"dummy_bot_token", hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    payload = {"init_data": urllib.parse.urlencode(fields)}
    rejected = client.post(
        "/api/auth/telegram", json=payload, headers={"Origin": "https://evil.example"}
    )
    assert rejected.status_code == 403
    assert "session_id" not in rejected.cookies
    allowed = client.post("/api/auth/telegram", json=payload, headers={"Origin": ORIGIN})
    assert allowed.status_code == 200
    assert "session_id" in allowed.cookies
    assert client.get("/api/auth/me").status_code == 200
