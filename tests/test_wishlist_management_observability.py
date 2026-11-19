"""Automated tests for wishlist management and Mini App observability."""

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest
from fastapi.testclient import TestClient

from wishenka.auth.models import AuthenticatedUser, TelegramUser
from wishenka.auth.session import SessionTokenService
from wishenka.config import Settings
from wishenka.logging import JsonFormatter
from wishenka.web.app import create_app
from wishenka.wishlists.service import WishlistService

pytestmark = pytest.mark.timeout(30)

ORIGIN = "http://testserver"
Setup = tuple[TestClient, SessionTokenService, int, str, str]


@pytest.fixture
def setup_app(tmp_path: Path) -> Iterator[Setup]:
    """Provide a real transactional application with seeded owner and wishlist."""
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'obs_management.db'}",
        secret_key="obs-test-secret",
    )
    app = create_app(settings)
    sessions = SessionTokenService(settings.secret_key)
    owner = AuthenticatedUser(telegram_id=101, first_name="Owner", auth_method="session_token")

    with TestClient(app) as client:
        import asyncio

        async def _seed_users() -> None:
            for uid, name in (
                (101, "Owner"),
                (202, "User202"),
                (303, "User303"),
                (505, "User505"),
                (999, "User999"),
            ):
                await app.state.user_store.upsert_user(TelegramUser(id=uid, first_name=name))

        asyncio.run(_seed_users())
        service = cast(WishlistService, getattr(app.state, "wishlist_service", None))
        if service is None:
            store = app.state.wishlist_store
            import asyncio

            async def init_data(srv: WishlistService) -> tuple[int, str, str]:
                wl = await srv.create_wishlist(owner=owner, title="Birthday Wishlist")
                return wl.id, wl.invite_token, wl.public_token

            wishlist_id, invite_token, public_token = asyncio.run(store.execute(init_data))
        else:
            import asyncio

            async def init_data(srv: WishlistService) -> tuple[int, str, str]:
                wl = await srv.create_wishlist(owner=owner, title="Birthday Wishlist")
                return wl.id, wl.invite_token, wl.public_token

            wishlist_id, invite_token, public_token = asyncio.run(init_data(service))

        yield client, sessions, wishlist_id, invite_token, public_token


def bearer(sessions: SessionTokenService, user_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {sessions.create_token(user_id, f'User{user_id}')}"}


def test_public_entry_logs_safe_outcomes(
    setup_app: Setup, caplog: pytest.LogCaptureFixture
) -> None:
    """Entry logs distinguish outcomes without including capability tokens or wishlist data."""
    client, _, _, _, token = setup_app
    invalid = "nonexistent-sensitive-capability"
    with caplog.at_level(logging.INFO, logger="wishenka.web.wishlists"):
        assert client.get(f"/api/public/wishlists/{token}/view").status_code == 200
        assert client.get(f"/api/public/wishlists/{invalid}/view").status_code == 404
    records = [
        record
        for record in caplog.records
        if getattr(record, "event", None) in {"public_entry_viewed", "public_entry_unavailable"}
    ]
    assert [getattr(record, "event", None) for record in records] == [
        "public_entry_viewed",
        "public_entry_unavailable",
    ]
    assert getattr(records[0], "identified", None) is False
    rendered = " ".join(JsonFormatter().format(record) for record in records)
    assert token not in rendered
    assert invalid not in rendered
    assert "Birthday Wishlist" not in rendered


def test_miniapp_shell_requested_log(setup_app: Setup, caplog: pytest.LogCaptureFixture) -> None:
    """GET / must emit structured INFO log for miniapp_shell_requested."""
    client, _, _, _, _ = setup_app
    with caplog.at_level(logging.INFO, logger="wishenka.web.miniapp"):
        response = client.get("/")
    assert response.status_code == 200
    records = [
        r
        for r in caplog.records
        if r.name == "wishenka.web.miniapp"
        and getattr(r, "event", None) == "miniapp_shell_requested"
    ]
    assert len(records) == 1
    assert records[0].levelname == "INFO"


def test_miniapp_catalog_embedded_debug_log(
    setup_app: Setup, caplog: pytest.LogCaptureFixture
) -> None:
    """GET / must emit structured DEBUG log for miniapp_catalog_embedded with scalar fields."""
    client, _, _, _, _ = setup_app
    with caplog.at_level(logging.DEBUG, logger="wishenka.web.miniapp"):
        response = client.get("/")
    assert response.status_code == 200
    records = [
        r
        for r in caplog.records
        if r.name == "wishenka.web.miniapp"
        and getattr(r, "event", None) == "miniapp_catalog_embedded"
    ]
    assert len(records) == 1
    assert records[0].levelname == "DEBUG"
    assert getattr(records[0], "locale", None) in {"en", "ru"}
    assert isinstance(getattr(records[0], "key_count", None), int)
    assert getattr(records[0], "key_count", 0) > 0


def test_wishlist_lifecycle_observability_events(
    setup_app: Setup, caplog: pytest.LogCaptureFixture
) -> None:
    """Wishlist creation, update, and status change emit structured INFO logs."""
    client, sessions, wishlist_id, _, _ = setup_app
    owner_headers = bearer(sessions, 101)

    with caplog.at_level(logging.INFO, logger="wishenka.web.wishlists"):
        # Update wishlist
        upd = client.patch(
            f"/api/wishlists/{wishlist_id}",
            json={"name": "Updated Title", "description": "New Desc"},
            headers=owner_headers,
        )
        assert upd.status_code == 200

        # Archive wishlist
        arch = client.post(f"/api/wishlists/{wishlist_id}/archive", headers=owner_headers)
        assert arch.status_code == 200

    upd_events = [
        r
        for r in caplog.records
        if r.name == "wishenka.web.wishlists" and getattr(r, "event", None) == "wishlist_updated"
    ]
    assert len(upd_events) == 1
    assert getattr(upd_events[0], "wishlist_id", None) == wishlist_id
    assert getattr(upd_events[0], "user_id", None) == 101

    status_events = [
        r
        for r in caplog.records
        if r.name == "wishenka.web.wishlists"
        and getattr(r, "event", None) == "wishlist_status_changed"
    ]
    assert len(status_events) == 1
    assert getattr(status_events[0], "wishlist_id", None) == wishlist_id
    assert getattr(status_events[0], "new_status", None) == "archived"


def test_access_violation_warning_logs(setup_app: Setup, caplog: pytest.LogCaptureFixture) -> None:
    """Unauthorized access attempts must emit structured WARNING logs."""
    client, sessions, wishlist_id, _, _ = setup_app
    stranger_headers = bearer(sessions, 999)

    with caplog.at_level(logging.WARNING, logger="wishenka.web.wishlists"):
        resp = client.get(f"/api/wishlists/{wishlist_id}", headers=stranger_headers)
        assert resp.status_code == 404

    records = [
        r
        for r in caplog.records
        if r.name == "wishenka.web.wishlists"
        and r.levelname == "WARNING"
        and getattr(r, "event", None) == "wishlist_access_denied"
    ]
    assert len(records) >= 1
    assert getattr(records[0], "user_id", None) == 999
    assert getattr(records[0], "wishlist_id", None) == wishlist_id


def test_member_management_observability_events(
    setup_app: Setup, caplog: pytest.LogCaptureFixture
) -> None:
    """Member role changes and removals emit structured INFO logs and WARNING on violation."""
    client, sessions, wishlist_id, invite_token, _ = setup_app
    owner_headers = bearer(sessions, 101)
    member_headers = bearer(sessions, 202)
    stranger_headers = bearer(sessions, 303)

    # 1. Member joins via invite
    client.post(
        "/api/invitations/accept",
        json={},
        headers=member_headers | {"X-Invite-Token": invite_token},
    )

    with caplog.at_level(logging.DEBUG, logger="wishenka.web.wishlists"):
        # Stranger attempts role change -> WARNING
        bad_role = client.patch(
            f"/api/wishlists/{wishlist_id}/members/202/role",
            json={"role": "admin"},
            headers=stranger_headers,
        )
        assert bad_role.status_code == 404

        # Owner changes member role -> INFO
        good_role = client.patch(
            f"/api/wishlists/{wishlist_id}/members/202/role",
            json={"role": "admin"},
            headers=owner_headers,
        )
        assert good_role.status_code == 200

    warn_records = [
        r
        for r in caplog.records
        if r.name == "wishenka.web.wishlists"
        and r.levelname == "WARNING"
        and getattr(r, "event", None) in {"wishlist_access_denied", "role_change_denied"}
    ]
    assert len(warn_records) >= 1

    info_role = [
        r
        for r in caplog.records
        if r.name == "wishenka.web.wishlists"
        and r.levelname == "INFO"
        and getattr(r, "event", None) == "member_role_updated"
    ]
    assert len(info_role) == 1
    assert getattr(info_role[0], "new_role", None) == "admin"
    assert getattr(info_role[0], "target_user_id", None) == 202


def test_invitation_preview_accept_and_token_issues_observability(
    setup_app: Setup, caplog: pytest.LogCaptureFixture
) -> None:
    """Invitation operations emit INFO and invalid token attempts emit WARNING with zero leak."""
    client, sessions, wishlist_id, invite_token, _ = setup_app
    member_headers = bearer(sessions, 505)

    with caplog.at_level(logging.DEBUG, logger="wishenka.web.wishlists"):
        # Malformed / unknown invite token -> WARNING
        resp_bad = client.get(
            "/api/invitations/preview",
            headers={"X-Invite-Token": "non-existent-secret-token"},
        )
        assert resp_bad.status_code == 404

        # Valid preview -> INFO
        resp_preview = client.get(
            "/api/invitations/preview",
            headers={"X-Invite-Token": invite_token},
        )
        assert resp_preview.status_code == 200

        # Valid accept -> INFO
        resp_accept = client.post(
            "/api/invitations/accept",
            json={},
            headers=member_headers | {"X-Invite-Token": invite_token},
        )
        assert resp_accept.status_code == 200

    warn_records = [
        r
        for r in caplog.records
        if r.name == "wishenka.web.wishlists"
        and r.levelname == "WARNING"
        and getattr(r, "event", None) == "invitation_token_invalid_or_expired"
    ]
    assert len(warn_records) == 1

    preview_records = [
        r
        for r in caplog.records
        if r.name == "wishenka.web.wishlists"
        and r.levelname == "INFO"
        and getattr(r, "event", None) == "invitation_previewed"
    ]
    assert len(preview_records) == 1

    accept_records = [
        r
        for r in caplog.records
        if r.name == "wishenka.web.wishlists"
        and r.levelname == "INFO"
        and getattr(r, "event", None) == "invitation_accepted"
    ]
    assert len(accept_records) == 1

    # Zero secret leak verification
    assert "non-existent-secret-token" not in caplog.text
    assert invite_token not in caplog.text


def test_csrf_and_origin_security_observability(
    setup_app: Setup, caplog: pytest.LogCaptureFixture
) -> None:
    """CSRF and origin validation failures emit structured WARNING logs."""
    client, sessions, wishlist_id, _, _ = setup_app
    cookie = sessions.create_token(101, "Owner")
    client.cookies.set("session_id", cookie)

    with caplog.at_level(logging.WARNING, logger="wishenka.web.security"):
        # Mutation with wrong origin -> WARNING
        bad_origin = client.post(
            f"/api/wishlists/{wishlist_id}/invite/reset",
            headers={"Origin": "https://evil.attacker.com"},
        )
        assert bad_origin.status_code == 403

        # Mutation with right origin but invalid CSRF token -> WARNING
        bad_csrf = client.post(
            f"/api/wishlists/{wishlist_id}/invite/reset",
            headers={"Origin": ORIGIN, "X-CSRF-Token": "bad-token-value"},
        )
        assert bad_csrf.status_code == 403

    origin_warns = [
        r
        for r in caplog.records
        if r.name == "wishenka.web.security" and getattr(r, "event", None) == "csrf_origin_mismatch"
    ]
    assert len(origin_warns) == 1

    csrf_warns = [
        r
        for r in caplog.records
        if r.name == "wishenka.web.security" and getattr(r, "event", None) == "csrf_token_invalid"
    ]
    assert len(csrf_warns) == 1

    # Verify no secret leak
    assert cookie not in caplog.text
    assert "bad-token-value" not in caplog.text


def test_csrf_endpoint_observability(setup_app: Setup, caplog: pytest.LogCaptureFixture) -> None:
    """CSRF token issuance emits INFO and missing session emits WARNING."""
    client, sessions, _, _, _ = setup_app

    with caplog.at_level(logging.DEBUG, logger="wishenka.auth"):
        # Call without cookie -> WARNING
        bearer_token = sessions.create_token(101, "Owner")
        resp_unauth = client.get(
            "/api/auth/csrf", headers={"Authorization": f"Bearer {bearer_token}"}
        )
        assert resp_unauth.status_code == 401

        # Call with cookie -> INFO
        client.cookies.set("session_id", bearer_token)
        resp_auth = client.get("/api/auth/csrf")
        assert resp_auth.status_code == 200

    warn_records = [
        r
        for r in caplog.records
        if r.name == "wishenka.auth"
        and r.levelname == "WARNING"
        and getattr(r, "event", None) == "csrf_cookie_missing"
    ]
    assert len(warn_records) == 1

    info_records = [
        r
        for r in caplog.records
        if r.name == "wishenka.auth"
        and r.levelname == "INFO"
        and getattr(r, "event", None) == "csrf_token_issued"
    ]
    assert len(info_records) == 1
    assert getattr(info_records[0], "telegram_id", None) == 101

    # Verify CSRF token itself is not logged
    csrf_token = resp_auth.json()["csrf_token"]
    assert csrf_token not in caplog.text
