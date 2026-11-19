"""Observability verification tests for wishlist sharing, invites, and members (WISHENKA-51).

Validates structured logging schema, event attributes, and zero token leakage.
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from wishenka.auth.models import AuthenticatedUser, TelegramUser
from wishenka.auth.session import SessionTokenService
from wishenka.config import Settings
from wishenka.web.app import ShareTokenAccessFilter, create_app
from wishenka.wishlists.service import WishlistService

pytestmark = pytest.mark.timeout(10)


@pytest.fixture(autouse=True)
def silence_httpx_logging() -> Iterator[None]:
    """Silence httpx client request logging to isolate server-side records."""
    httpx_logger = logging.getLogger("httpx")
    old_level = httpx_logger.level
    httpx_logger.setLevel(logging.WARNING)
    yield
    httpx_logger.setLevel(old_level)


def make_user(
    telegram_id: int,
    first_name: str,
    username: str | None = None,
) -> AuthenticatedUser:
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
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'htmx_obs.db'}",
        secret_key="htmx-observability-secret-key",
    )
    app = create_app(settings)
    sessions = SessionTokenService(settings.secret_key)
    with TestClient(app) as client:

        async def _seed_users() -> None:
            for uid, name in ((101, "Alice"), (202, "Bob"), (303, "Charlie")):
                await app.state.user_store.upsert_user(TelegramUser(id=uid, first_name=name))

        asyncio.run(_seed_users())
        yield client, sessions, app


def test_wishlist_shared_view_observability(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Structured log wishlist_shared_view emitted with correct fields and zero token leak."""
    client, sessions, app = test_app
    service: WishlistService = app.state.domain_service
    owner = make_user(101, "Alice")

    async def seed() -> tuple[int, str]:
        wl = await service.create_wishlist(owner=owner, title="Alice Birthday")
        await service.add_wish_item(wishlist_id=wl.id, actor=owner, title="Book", quantity=1)
        return wl.id, str(wl.public_token)

    wl_id, public_token = asyncio.run(seed())

    # 1. Guest views public share page
    with caplog.at_level(logging.INFO, logger="wishenka.web.sharing"):
        caplog.clear()
        resp = client.get(f"/share/{public_token}")
        assert resp.status_code == 200

        records = [r for r in caplog.records if getattr(r, "event", None) == "wishlist_shared_view"]
        assert len(records) == 1
        rec = records[0]
        assert getattr(rec, "wishlist_id", None) == wl_id
        assert getattr(rec, "is_recipient", None) is False
        assert getattr(rec, "is_collaborative", None) is False
        assert public_token not in caplog.text

    # 2. Owner views public share page (is_recipient = True for personal wishlist)
    with caplog.at_level(logging.INFO, logger="wishenka.web.sharing"):
        caplog.clear()
        resp = client.get(f"/share/{public_token}", headers=bearer(sessions, 101))
        assert resp.status_code == 200

        records = [r for r in caplog.records if getattr(r, "event", None) == "wishlist_shared_view"]
        assert len(records) == 1
        rec = records[0]
        assert getattr(rec, "wishlist_id", None) == wl_id
        assert getattr(rec, "is_recipient", None) is True
        assert getattr(rec, "is_collaborative", None) is False
        assert public_token not in caplog.text

    # 3. Gifter views public share page (is_recipient = False)
    with caplog.at_level(logging.INFO, logger="wishenka.web.sharing"):
        caplog.clear()
        resp = client.get(f"/share/{public_token}", headers=bearer(sessions, 202))
        assert resp.status_code == 200

        records = [r for r in caplog.records if getattr(r, "event", None) == "wishlist_shared_view"]
        assert len(records) == 1
        rec = records[0]
        assert getattr(rec, "wishlist_id", None) == wl_id
        assert getattr(rec, "is_recipient", None) is False
        assert getattr(rec, "is_collaborative", None) is False
        assert public_token not in caplog.text


def test_invite_preview_accessed_observability(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Structured log invite_preview_accessed emitted for valid, expired, and not_found tokens."""
    client, _, app = test_app
    service: WishlistService = app.state.domain_service
    owner = make_user(101, "Alice")

    async def seed() -> tuple[int, str, int, str]:
        wl_valid = await service.create_wishlist(owner=owner, title="Valid Invite List")
        wl_exp = await service.create_wishlist(
            owner=owner,
            title="Expired Invite List",
            invite_token_expires_in=timedelta(seconds=-60),
        )
        return (
            wl_valid.id,
            str(wl_valid.invite_token),
            wl_exp.id,
            str(wl_exp.invite_token),
        )

    valid_id, valid_token, exp_id, exp_token = asyncio.run(seed())
    not_found_token = "non-existent-secret-token-xyz"

    with caplog.at_level(logging.INFO, logger="wishenka.web.sharing"):
        # 1. Valid token
        caplog.clear()
        resp = client.get(f"/invite/{valid_token}")
        assert resp.status_code == 200
        records = [
            r for r in caplog.records if getattr(r, "event", None) == "invite_preview_accessed"
        ]
        assert len(records) == 1
        assert getattr(records[0], "wishlist_id", None) == valid_id
        assert getattr(records[0], "status", None) == "valid"
        assert valid_token not in caplog.text

        # 2. Expired token
        caplog.clear()
        resp = client.get(f"/invite/{exp_token}")
        assert resp.status_code == 200
        records = [
            r for r in caplog.records if getattr(r, "event", None) == "invite_preview_accessed"
        ]
        assert len(records) == 1
        assert getattr(records[0], "wishlist_id", None) == exp_id
        assert getattr(records[0], "status", None) == "expired"
        assert exp_token not in caplog.text

        # 3. Not found token
        caplog.clear()
        resp = client.get(f"/invite/{not_found_token}")
        assert resp.status_code == 200
        records = [
            r for r in caplog.records if getattr(r, "event", None) == "invite_preview_accessed"
        ]
        assert len(records) == 1
        assert getattr(records[0], "wishlist_id", None) is None
        assert getattr(records[0], "status", None) == "not_found"
        assert not_found_token not in caplog.text


def test_invite_joined_observability(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Structured log invite_joined emitted with wishlist_id, user_id, and role."""
    client, sessions, app = test_app
    service: WishlistService = app.state.domain_service
    owner = make_user(101, "Alice")

    async def seed() -> tuple[int, str]:
        wl = await service.create_wishlist(owner=owner, title="Collaboration")
        return wl.id, str(wl.invite_token)

    wl_id, invite_token = asyncio.run(seed())

    with caplog.at_level(logging.INFO, logger="wishenka.web.sharing"):
        caplog.clear()
        joiner_headers = bearer(sessions, 303) | {"HX-Request": "true"}
        resp = client.post(f"/invite/{invite_token}/join", headers=joiner_headers)
        assert resp.status_code == 200

        records = [r for r in caplog.records if getattr(r, "event", None) == "invite_joined"]
        assert len(records) == 1
        rec = records[0]
        assert getattr(rec, "wishlist_id", None) == wl_id
        assert getattr(rec, "user_id", None) == 303
        assert getattr(rec, "role", None) == "member"
        assert invite_token not in caplog.text


def test_member_removed_observability(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Structured log member_removed emitted with wishlist_id, removed_user_id, and removed_by."""
    client, sessions, app = test_app
    service: WishlistService = app.state.domain_service
    owner = make_user(101, "Alice")
    member = make_user(303, "Charlie")

    async def seed() -> tuple[int, str]:
        wl = await service.create_wishlist(owner=owner, title="Team Wishlist")
        await service.join_by_invite(str(wl.invite_token), member)
        return wl.id, str(wl.invite_token)

    wl_id, _ = asyncio.run(seed())

    with caplog.at_level(logging.INFO, logger="wishenka.web.sharing"):
        caplog.clear()
        owner_headers = bearer(sessions, 101) | {"HX-Request": "true"}
        resp = client.delete(f"/wishlists/{wl_id}/members/303/partial", headers=owner_headers)
        assert resp.status_code == 200

        records = [
            r
            for r in caplog.records
            if getattr(r, "event", None) == "member_removed" and r.name == "wishenka.web.sharing"
        ]
        assert len(records) == 1
        rec = records[0]
        assert getattr(rec, "wishlist_id", None) == wl_id
        assert getattr(rec, "removed_user_id", None) == 303
        assert getattr(rec, "removed_by", None) == 101


def test_invite_regenerated_observability(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Structured log invite_regenerated emitted with zero leakage of old or new tokens."""
    client, sessions, app = test_app
    service: WishlistService = app.state.domain_service
    owner = make_user(101, "Alice")

    async def seed() -> tuple[int, str]:
        wl = await service.create_wishlist(owner=owner, title="Secret Project")
        return wl.id, str(wl.invite_token)

    wl_id, old_invite_token = asyncio.run(seed())

    with caplog.at_level(logging.INFO, logger="wishenka.web.sharing"):
        caplog.clear()
        owner_headers = bearer(sessions, 101) | {"HX-Request": "true"}
        resp = client.post(f"/wishlists/{wl_id}/invite/regenerate", headers=owner_headers)
        assert resp.status_code == 200

        records = [r for r in caplog.records if getattr(r, "event", None) == "invite_regenerated"]
        assert len(records) == 1
        rec = records[0]
        assert getattr(rec, "wishlist_id", None) == wl_id
        assert getattr(rec, "user_id", None) == 101

        # Retrieve new token to verify it was not leaked either
        async def get_new_token() -> str:
            wl = await service.get_wishlist_by_id(wl_id)
            return str(wl.invite_token)

        new_token = asyncio.run(get_new_token())
        assert new_token != old_invite_token
        assert old_invite_token not in caplog.text
        assert new_token not in caplog.text


def test_share_token_access_filter_redaction() -> None:
    """Uvicorn access log filter sanitizes capability tokens from path strings."""
    filter_ = ShareTokenAccessFilter()

    # 1. Share token
    rec1 = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        0,
        '%s - "%s %s HTTP/%s" %s',
        ("client", "GET", "/share/secret-public-token-12345", "1.1", 200),
        None,
    )
    assert filter_.filter(rec1) is True
    assert "secret-public-token-12345" not in rec1.getMessage()
    assert "/share/{token}" in rec1.getMessage()

    # 2. Invite token
    rec2 = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        0,
        '%s - "%s %s HTTP/%s" %s',
        ("client", "GET", "/invite/secret-invite-token-67890", "1.1", 200),
        None,
    )
    assert filter_.filter(rec2) is True
    assert "secret-invite-token-67890" not in rec2.getMessage()
    assert "/invite/{token}" in rec2.getMessage()

    # 3. Invite join token
    rec3 = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        0,
        '%s - "%s %s HTTP/%s" %s',
        ("client", "POST", "/invite/secret-invite-token-67890/join", "1.1", 200),
        None,
    )
    assert filter_.filter(rec3) is True
    assert "secret-invite-token-67890" not in rec3.getMessage()
    assert "/invite/{token}/join" in rec3.getMessage()

    # 4. Token with query parameters
    rec4 = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        0,
        '%s - "%s %s HTTP/%s" %s',
        ("client", "GET", "/share/secret-public-token-12345?ref=telegram", "1.1", 200),
        None,
    )
    assert filter_.filter(rec4) is True
    assert "secret-public-token-12345" not in rec4.getMessage()
    assert "/share/{token}" in rec4.getMessage()


@pytest.mark.timeout(30)
def test_uvicorn_access_log_redacts_public_view_token(tmp_path: Path) -> None:
    """Exercise the actual server access formatter and application startup filter."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = os.environ.copy()
    env["WISHENKA_DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_path / 'access.db'}"
    env["WISHENKA_BACKGROUND_CLEANUP_ENABLED"] = "false"
    env["WISHENKA_RECEIPT_NOTICE_WORKER_ENABLED"] = "false"
    log_path = tmp_path / "server.log"
    token = "private-access-capability"
    url = f"http://127.0.0.1:{port}/api/public/wishlists/{token}/view?credential=secret"
    with log_path.open("w+") as output:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "wishenka.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            stdout=output,
            stderr=subprocess.STDOUT,
            env=env,
        )
        try:
            deadline = time.monotonic() + 15
            while True:
                try:
                    with urllib.request.urlopen(url, timeout=1):
                        pass
                except urllib.error.HTTPError as exc:
                    assert exc.code == 404
                    break
                except urllib.error.URLError:
                    assert process.poll() is None and time.monotonic() < deadline
                    time.sleep(0.1)
            process.terminate()
            process.wait(timeout=5)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
        output.seek(0)
        logs = output.read()
    assert "/api/public/wishlists/{token}" in logs
    assert token not in logs
    assert "credential=secret" not in logs
