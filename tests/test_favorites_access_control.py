"""Automated failing repro tests for WISHENKA-302: Favorites access control.

Asserts desired access control behavior:
1. An authenticated stranger (non-owner, non-member, no share-link visit) cannot add a
   private wishlist to Favorites (HTTP 404 matching non-existent wishlist) or see it in
   GET /api/favorites.
2. A legacy unauthorized row in wl_favorites is not returned by GET /api/favorites.
3. After a giver opens the wishlist via its active share link, POST /api/favorites/{id}
   succeeds (200) and GET /api/favorites returns the wishlist with role == "favorite".
4. Rotating the share link revokes the giver's Favorites access (removed from
   GET /api/favorites, and POST /api/favorites/{id} returns 404 again).
"""

import asyncio
import json
import logging
import sqlite3
from collections.abc import Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from fastapi import FastAPI
from fastapi.testclient import TestClient

from wishenka.auth.models import AuthenticatedUser, TelegramUser
from wishenka.auth.session import SessionTokenService
from wishenka.config import Settings
from wishenka.logging import JsonFormatter, TextFormatter
from wishenka.web.app import create_app
from wishenka.web.dependencies import get_wishlist_repository
from wishenka.wishlists.exceptions import WishlistNotFoundError
from wishenka.wishlists.migrations import _configured
from wishenka.wishlists.models import ShareAccessGrant, WishlistRole
from wishenka.wishlists.repo_ops import RepoWishlistOps
from wishenka.wishlists.service import WishlistService

pytestmark = pytest.mark.timeout(30)


def _bearer(sessions: SessionTokenService, user_id: int) -> dict[str, str]:
    """Build Authorization header for a test user."""
    return {"Authorization": f"Bearer {sessions.create_token(user_id, 'User')}"}


@pytest.fixture
def favorites_app(
    tmp_path: Path,
) -> Iterator[tuple[TestClient, SessionTokenService, FastAPI, Path]]:
    """Initialize TestClient, SessionTokenService, app, and DB path."""
    db_path = tmp_path / "favorites_acl.db"
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{db_path}",
        secret_key="favorites-acl-test-secret",
    )
    app = create_app(settings)
    sessions = SessionTokenService(settings.secret_key)
    with TestClient(app) as client:

        async def seed_users() -> None:
            await app.state.user_store.upsert_user(TelegramUser(id=101, first_name="Owner"))
            await app.state.user_store.upsert_user(TelegramUser(id=202, first_name="Stranger"))
            await app.state.user_store.upsert_user(TelegramUser(id=303, first_name="Giver"))

        asyncio.run(seed_users())
        yield client, sessions, app, db_path


def test_stranger_cannot_add_or_list_private_wishlist_in_favorites(
    favorites_app: tuple[TestClient, SessionTokenService, FastAPI, Path],
) -> None:
    """Stranger without membership or share-link access gets 404 and empty favorites."""
    client, sessions, app, _ = favorites_app
    service: WishlistService = app.state.domain_service
    owner = AuthenticatedUser(telegram_id=101, first_name="Owner", auth_method="session_token")

    async def seed_wishlist() -> int:
        wl = await service.create_wishlist(
            owner,
            title="Secret Birthday Plan",
            description="Private notes",
            event_title="Birthday",
        )
        return wl.id

    wl_id = asyncio.run(seed_wishlist())
    stranger_headers = _bearer(sessions, 202)

    missing_resp = client.post("/api/favorites/999999", headers=stranger_headers)
    assert missing_resp.status_code == 404

    stranger_resp = client.post(f"/api/favorites/{wl_id}", headers=stranger_headers)
    assert stranger_resp.status_code == 404
    assert stranger_resp.json() == missing_resp.json()

    list_resp = client.get("/api/favorites", headers=stranger_headers)
    assert list_resp.status_code == 200
    assert list_resp.json() == []


def test_legacy_unauthorized_favorite_row_is_not_listed(
    favorites_app: tuple[TestClient, SessionTokenService, FastAPI, Path],
) -> None:
    """A pre-existing unauthorized row in wl_favorites must not disclose wishlist metadata."""
    client, sessions, app, db_path = favorites_app
    service: WishlistService = app.state.domain_service
    owner = AuthenticatedUser(telegram_id=101, first_name="Owner", auth_method="session_token")

    async def seed_wishlist() -> int:
        wl = await service.create_wishlist(owner, title="Private Legacy List")
        return wl.id

    wl_id = asyncio.run(seed_wishlist())

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO wl_favorites (user_id, wishlist_id, created_at) VALUES (?, ?, ?)",
            (202, wl_id, datetime.now(UTC).isoformat()),
        )
        conn.commit()

    stranger_headers = _bearer(sessions, 202)
    list_resp = client.get("/api/favorites", headers=stranger_headers)
    assert list_resp.status_code == 200
    assert list_resp.json() == []


def test_giver_share_link_access_and_revocation_on_token_rotation(
    favorites_app: tuple[TestClient, SessionTokenService, FastAPI, Path],
) -> None:
    """Giver can favorite after share-link visit and loses access when share link rotates."""
    client, sessions, app, _ = favorites_app
    service: WishlistService = app.state.domain_service
    owner = AuthenticatedUser(telegram_id=101, first_name="Owner", auth_method="session_token")

    async def seed_wishlist() -> tuple[int, str]:
        wl = await service.create_wishlist(owner, title="Shared Gift List")
        return wl.id, wl.public_token

    wl_id, public_token = asyncio.run(seed_wishlist())
    owner_headers = _bearer(sessions, 101)
    giver_headers = _bearer(sessions, 303)

    # 1. Giver opens wishlist via active share link
    view_resp = client.get(f"/api/public/wishlists/{public_token}/view", headers=giver_headers)
    assert view_resp.status_code == 200

    # 2. Giver can now add and list it in Favorites with role == "favorite"
    add_resp = client.post(f"/api/favorites/{wl_id}", headers=giver_headers)
    assert add_resp.status_code == 200
    assert add_resp.json().get("status") == "favorited"

    list_resp = client.get("/api/favorites", headers=giver_headers)
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert len(items) == 1
    assert items[0]["id"] == wl_id
    assert items[0]["role"] == "favorite"
    assert items[0]["is_favorite"] is True

    # 3. Owner rotates share link -> giver loses Favorites access
    reset_resp = client.post(f"/api/wishlists/{wl_id}/share/reset", headers=owner_headers)
    assert reset_resp.status_code == 200

    after_reset_list = client.get("/api/favorites", headers=giver_headers)
    assert after_reset_list.status_code == 200
    assert after_reset_list.json() == []

    after_reset_add = client.post(f"/api/favorites/{wl_id}", headers=giver_headers)
    assert after_reset_add.status_code == 404


def test_participant_can_favorite_and_removal_revokes_when_no_share_access(
    favorites_app: tuple[TestClient, SessionTokenService, FastAPI, Path],
) -> None:
    """Participant can favorite without share link; removal revokes unless share access exists."""
    client, sessions, app, _ = favorites_app
    service: WishlistService = app.state.domain_service
    owner = AuthenticatedUser(telegram_id=101, first_name="Owner", auth_method="session_token")

    async def seed_collab() -> tuple[int, str]:
        wl = await service.create_wishlist(owner, title="Collab List")
        await service.add_member(wl.id, owner, 202, WishlistRole.MEMBER)
        await service.add_member(wl.id, owner, 303, WishlistRole.MEMBER)
        return wl.id, wl.public_token

    wl_id, public_token = asyncio.run(seed_collab())
    owner_headers = _bearer(sessions, 101)
    member_headers = _bearer(sessions, 202)
    admin_headers = _bearer(sessions, 303)

    # Both member and admin can favorite without opening share link
    assert client.post(f"/api/favorites/{wl_id}", headers=member_headers).status_code == 200
    assert client.post(f"/api/favorites/{wl_id}", headers=admin_headers).status_code == 200

    # Admin also opens the active share link
    assert (
        client.get(f"/api/public/wishlists/{public_token}/view", headers=admin_headers).status_code
        == 200
    )

    # Remove both members
    assert (
        client.delete(f"/api/wishlists/{wl_id}/members/202", headers=owner_headers).status_code
        == 200
    )
    assert (
        client.delete(f"/api/wishlists/{wl_id}/members/303", headers=owner_headers).status_code
        == 200
    )

    # Member without share-link access loses favorite and cannot re-add
    assert client.get("/api/favorites", headers=member_headers).json() == []
    assert client.post(f"/api/favorites/{wl_id}", headers=member_headers).status_code == 404

    # Former admin with active share-link access retains favorite with role == "favorite"
    admin_favs = client.get("/api/favorites", headers=admin_headers).json()
    assert len(admin_favs) == 1
    assert admin_favs[0]["id"] == wl_id
    assert admin_favs[0]["role"] == "favorite"


@pytest.mark.parametrize("idempotency_key", ["res-share-access-1", None])
def test_reservation_grants_scoped_share_access_and_restore_revokes_it(
    favorites_app: tuple[TestClient, SessionTokenService, FastAPI, Path],
    idempotency_key: str | None,
) -> None:
    """Reservation via execute_wish and execute_wish_idempotent persists access; restore revokes."""
    client, sessions, app, db_path = favorites_app
    service: WishlistService = app.state.domain_service
    owner = AuthenticatedUser(telegram_id=101, first_name="Owner", auth_method="session_token")

    async def seed_with_item() -> tuple[int, str, int]:
        wl = await service.create_wishlist(owner, title="Scoped Reservation List")
        item = await service.add_wish_item(wl.id, actor=owner, title="Board Game", quantity=2)
        return wl.id, wl.public_token, item.id

    wl_id, public_token, item_id = asyncio.run(seed_with_item())
    owner_headers = _bearer(sessions, 101)
    giver_headers = _bearer(sessions, 303)

    # Giver reserves directly via public link (uses execute_wish / execute_wish_idempotent)
    req_headers = (
        {**giver_headers, "Idempotency-Key": idempotency_key}
        if idempotency_key is not None
        else giver_headers
    )
    res_resp = client.post(
        f"/api/public/wishlists/{public_token}/items/{item_id}/reservations",
        json={"quantity": 1},
        headers=req_headers,
    )
    assert res_resp.status_code == 201

    # Giver can now favorite the wishlist and see it in GET /api/favorites
    assert client.post(f"/api/favorites/{wl_id}", headers=giver_headers).status_code == 200
    assert [f["id"] for f in client.get("/api/favorites", headers=giver_headers).json()] == [wl_id]

    # Soft-delete and restore wishlist -> rotates public_token & purges non-member favorites/access
    assert client.delete(f"/api/wishlists/{wl_id}", headers=owner_headers).status_code == 200
    assert (
        client.post(f"/api/wishlists/{wl_id}/restore-deleted", headers=owner_headers).status_code
        == 200
    )

    assert client.get("/api/favorites", headers=giver_headers).json() == []
    assert client.post(f"/api/favorites/{wl_id}", headers=giver_headers).status_code == 404
    with sqlite3.connect(db_path) as conn:
        sa_row = conn.execute(
            "SELECT COUNT(*) FROM wl_share_access WHERE wishlist_id = ?", (wl_id,)
        ).fetchone()
        fav_row = conn.execute(
            "SELECT COUNT(*) FROM wl_favorites WHERE wishlist_id = ?", (wl_id,)
        ).fetchone()
    assert sa_row == (0,)
    assert fav_row == (0,)


@pytest.mark.asyncio
async def test_transfer_ownership_clears_new_owner_and_giver_favorites_and_rotates_token() -> None:
    """Transferring ownership rotates public_token and revokes new owner and giver access."""
    service = WishlistService.in_memory()
    owner = AuthenticatedUser(telegram_id=101, first_name="Owner", auth_method="session_token")
    new_owner = AuthenticatedUser(
        telegram_id=202, first_name="NewOwner", auth_method="session_token"
    )
    giver = AuthenticatedUser(telegram_id=303, first_name="Giver", auth_method="session_token")
    wl = await service.create_wishlist(owner, title="Transferable List")
    old_public_token = wl.public_token
    await service.add_member(wl.id, owner, new_owner.telegram_id, WishlistRole.ADMIN)
    await service.add_favorite(new_owner, wl.id)
    await service.get_wishlist_by_public_token(old_public_token, current_user=giver)
    await service.add_favorite(giver, wl.id)
    assert [w.id for w in await service.list_favorites(new_owner)] == [wl.id]
    assert [w.id for w in await service.list_favorites(giver)] == [wl.id]

    transferred = await service.transfer_ownership(wl.id, owner, new_owner.telegram_id)
    assert transferred.public_token != old_public_token
    assert await service.list_favorites(new_owner) == []
    with pytest.raises(ValueError, match="Cannot favorite own wishlist"):
        await service.add_favorite(new_owner, wl.id)

    assert await service.list_favorites(giver) == []
    with pytest.raises(WishlistNotFoundError):
        await service.add_favorite(giver, wl.id)
    with pytest.raises(WishlistNotFoundError):
        await service.get_wishlist_by_public_token(old_public_token, current_user=giver)


def test_migration_upgrade_purges_non_member_favorites_and_downgrade_drops_table(
    tmp_path: Path,
) -> None:
    """Upgrade creates wl_share_access and purges non-member favorites; downgrade drops table."""
    db_path = tmp_path / "migration_favorites.db"
    cfg = _configured(f"sqlite+aiosqlite:///{db_path}")

    command.upgrade(cfg, "unify_user_keys_and_cascades")
    with sqlite3.connect(db_path) as conn:
        now = datetime.now(UTC).isoformat()
        for uid in (101, 202, 303):
            conn.execute(
                "INSERT INTO users (telegram_id, first_name, created_at, updated_at) "
                "VALUES (?, ?, ?, ?)",
                (uid, f"User{uid}", now, now),
            )
        conn.execute(
            "INSERT INTO wl_lists "
            "(id, owner_id, owner_name, title, is_collaborative, status, public_token, "
            "invite_token, created_at, updated_at) "
            "VALUES (1, 101, 'Owner', 'Private', 1, 'active', 'pub-1', 'inv-1', ?, ?)",
            (now, now),
        )
        conn.execute(
            "INSERT INTO wl_members (id, wishlist_id, user_id, role, joined_at) "
            "VALUES (1, 1, 202, 'member', ?)",
            (now,),
        )
        # 202 is a member; 303 is a non-member (legacy unauthorized favorite)
        conn.execute(
            "INSERT INTO wl_favorites (user_id, wishlist_id, created_at) VALUES (202, 1, ?)",
            (now,),
        )
        conn.execute(
            "INSERT INTO wl_favorites (user_id, wishlist_id, created_at) VALUES (303, 1, ?)",
            (now,),
        )
        conn.commit()

    command.upgrade(cfg, "head")
    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert "wl_share_access" in tables
        remaining = conn.execute(
            "SELECT user_id FROM wl_favorites WHERE wishlist_id = 1 ORDER BY user_id"
        ).fetchall()
        assert remaining == [(202,)]

    command.downgrade(cfg, "unify_user_keys_and_cascades")
    with sqlite3.connect(db_path) as conn:
        tables_after = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert "wl_share_access" not in tables_after


def _assert_no_token_in_records(records: list[logging.LogRecord], secret_tokens: list[str]) -> None:
    """Ensure none of the secret public_token values appear in wishenka log messages or extras."""
    for rec in records:
        if not rec.name.startswith("wishenka"):
            continue
        msg = rec.getMessage()
        for tok in secret_tokens:
            assert tok not in msg
            for val in rec.__dict__.values():
                if isinstance(val, str):
                    assert tok not in val


def test_favorites_access_control_observability_events(
    favorites_app: tuple[TestClient, SessionTokenService, FastAPI, Path],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify structured logs for grant, denial, and revocations without token/PII leaks."""
    client, sessions, app, _ = favorites_app
    service: WishlistService = app.state.domain_service
    owner = AuthenticatedUser(telegram_id=101, first_name="Owner", auth_method="session_token")

    async def seed() -> tuple[int, str, str]:
        wl = await service.create_wishlist(owner, title="Secret Observability List")
        await service.add_member(wl.id, owner, user_id=202, role=WishlistRole.MEMBER)
        return wl.id, wl.public_token, wl.title

    wl_id, public_token, secret_title = asyncio.run(seed())
    tokens_seen = [public_token]

    # 1. Denied favorite attempt by stranger -> single WARNING favorite_access_denied, no PII/title
    stranger_headers = _bearer(sessions, 303)
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        resp = client.post(f"/api/favorites/{wl_id}", headers=stranger_headers)
        assert resp.status_code == 404
    denied_records = [
        r for r in caplog.records if getattr(r, "event", None) == "favorite_access_denied"
    ]
    assert len(denied_records) == 1
    assert denied_records[0].levelname == "WARNING"
    assert getattr(denied_records[0], "wishlist_id", None) == wl_id
    assert getattr(denied_records[0], "user_id", None) == 303
    assert secret_title not in denied_records[0].getMessage()
    _assert_no_token_in_records(caplog.records, tokens_seen)

    # 2. Share-link visit by giver -> single INFO share_access_granted, no public_token
    caplog.clear()
    with caplog.at_level(logging.INFO):
        resp = client.get(f"/api/public/wishlists/{public_token}/view", headers=stranger_headers)
        assert resp.status_code == 200
    grant_records = [
        r for r in caplog.records if getattr(r, "event", None) == "share_access_granted"
    ]
    assert len(grant_records) == 1
    assert grant_records[0].levelname == "INFO"
    assert getattr(grant_records[0], "wishlist_id", None) == wl_id
    assert getattr(grant_records[0], "user_id", None) == 303
    _assert_no_token_in_records(caplog.records, tokens_seen)

    # Giver favorites the wishlist
    assert client.post(f"/api/favorites/{wl_id}", headers=stranger_headers).status_code == 200

    # 3. Share token reset -> single INFO share_access_revoked (reason=public_token_rotated)
    owner_headers = _bearer(sessions, 101)
    caplog.clear()
    with caplog.at_level(logging.INFO):
        resp = client.post(f"/api/wishlists/{wl_id}/share/reset", headers=owner_headers)
        assert resp.status_code == 200
        tokens_seen.append(resp.json()["share_token"])
    revoked_records = [
        r for r in caplog.records if getattr(r, "event", None) == "share_access_revoked"
    ]
    assert len(revoked_records) == 1
    assert getattr(revoked_records[0], "reason", None) == "public_token_rotated"
    assert getattr(revoked_records[0], "revoked_grants", None) == 1
    assert getattr(revoked_records[0], "revoked_favorites", None) == 1
    _assert_no_token_in_records(caplog.records, tokens_seen)

    # 4. Member removal -> single INFO favorite_access_revoked (reason=member_removed)
    member_headers = _bearer(sessions, 202)
    assert client.post(f"/api/favorites/{wl_id}", headers=member_headers).status_code == 200
    caplog.clear()
    with caplog.at_level(logging.INFO):
        resp = client.delete(f"/api/wishlists/{wl_id}/members/202", headers=owner_headers)
        assert resp.status_code == 200
    member_revoked_records = [
        r for r in caplog.records if getattr(r, "event", None) == "favorite_access_revoked"
    ]
    assert len(member_revoked_records) == 1
    assert getattr(member_revoked_records[0], "reason", None) == "member_removed"
    assert getattr(member_revoked_records[0], "user_id", None) == 202
    _assert_no_token_in_records(caplog.records, tokens_seen)


@pytest.mark.asyncio
async def test_service_revocation_observability_on_restore_and_transfer(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify WishlistService logs share_access_revoked on restore and ownership transfer."""
    service = WishlistService.in_memory()
    owner = AuthenticatedUser(telegram_id=101, first_name="Owner", auth_method="session_token")
    member = AuthenticatedUser(telegram_id=202, first_name="Member", auth_method="session_token")
    giver = AuthenticatedUser(telegram_id=303, first_name="Giver", auth_method="session_token")

    wl = await service.create_wishlist(owner, title="Service Obs List")
    await service.add_member(wl.id, owner, user_id=member.telegram_id, role=WishlistRole.ADMIN)
    tokens_seen = [wl.public_token]

    await service.get_wishlist_by_public_token(wl.public_token, current_user=giver)
    await service.add_favorite(giver, wl.id)

    # Ownership transfer revokes share access and non-member favorites
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="wishenka.wishlists"):
        await service.transfer_ownership(wl.id, owner, member.telegram_id)
    tokens_seen.append(wl.public_token)
    transfer_revoked = [
        r for r in caplog.records if getattr(r, "event", None) == "share_access_revoked"
    ]
    assert len(transfer_revoked) == 1
    assert getattr(transfer_revoked[0], "reason", None) == "ownership_transferred"
    _assert_no_token_in_records(caplog.records, tokens_seen)

    # Re-grant and favorite, then delete + restore
    await service.get_wishlist_by_public_token(wl.public_token, current_user=giver)
    await service.add_favorite(giver, wl.id)
    await service.delete_wishlist(wl.id, member)

    caplog.clear()
    with caplog.at_level(logging.INFO, logger="wishenka.wishlists"):
        restored = await service.restore_deleted_wishlist(wl.id, member)
    tokens_seen.append(restored.public_token)
    restore_revoked = [
        r for r in caplog.records if getattr(r, "event", None) == "share_access_revoked"
    ]
    assert len(restore_revoked) == 1
    assert getattr(restore_revoked[0], "reason", None) == "wishlist_restored"
    _assert_no_token_in_records(caplog.records, tokens_seen)


def test_favorites_access_control_formatted_log_output(
    favorites_app: tuple[TestClient, SessionTokenService, FastAPI, Path],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify TextFormatter and JsonFormatter preserve structured fields without leaks."""
    client, sessions, app, _ = favorites_app
    service: WishlistService = app.state.domain_service
    owner = AuthenticatedUser(telegram_id=101, first_name="Owner", auth_method="session_token")
    secret_title = "Formatted Obs Secret Title"

    async def seed() -> tuple[int, str]:
        wl = await service.create_wishlist(owner, title=secret_title)
        await service.add_member(wl.id, owner, user_id=202, role=WishlistRole.MEMBER)
        return wl.id, wl.public_token

    wl_id, public_token = asyncio.run(seed())
    tokens_seen = [public_token]
    stranger_headers = _bearer(sessions, 303)
    owner_headers = _bearer(sessions, 101)
    member_headers = _bearer(sessions, 202)

    with caplog.at_level(logging.INFO, logger="wishenka.wishlists"):
        assert client.post(f"/api/favorites/{wl_id}", headers=stranger_headers).status_code == 404
        assert (
            client.get(
                f"/api/public/wishlists/{public_token}/view", headers=stranger_headers
            ).status_code
            == 200
        )
        assert client.post(f"/api/favorites/{wl_id}", headers=stranger_headers).status_code == 200
        reset_resp = client.post(f"/api/wishlists/{wl_id}/share/reset", headers=owner_headers)
        assert reset_resp.status_code == 200
        tokens_seen.append(reset_resp.json()["share_token"])
        assert client.post(f"/api/favorites/{wl_id}", headers=member_headers).status_code == 200
        assert (
            client.delete(f"/api/wishlists/{wl_id}/members/202", headers=owner_headers).status_code
            == 200
        )

    text_formatter = TextFormatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    json_formatter = JsonFormatter()

    target_records = [
        r
        for r in caplog.records
        if getattr(r, "event", None)
        in {
            "favorite_access_denied",
            "share_access_granted",
            "share_access_revoked",
            "favorite_access_revoked",
        }
    ]
    assert {getattr(r, "event", None) for r in target_records} == {
        "favorite_access_denied",
        "share_access_granted",
        "share_access_revoked",
        "favorite_access_revoked",
    }

    text_lines = [text_formatter.format(r) for r in target_records]
    json_payloads = [json.loads(json_formatter.format(r)) for r in target_records]

    for line, payload in zip(text_lines, json_payloads, strict=True):
        assert secret_title not in line
        assert secret_title not in json.dumps(payload)
        for tok in tokens_seen:
            assert tok not in line
            assert tok not in json.dumps(payload)

    denied_text = next(line for line in text_lines if "event=favorite_access_denied" in line)
    assert f"wishlist_id={wl_id}" in denied_text
    assert "user_id=303" in denied_text

    revoked_text = next(line for line in text_lines if "event=share_access_revoked" in line)
    assert "reason=public_token_rotated" in revoked_text
    assert f"wishlist_id={wl_id}" in revoked_text
    assert "actor_id=101" in revoked_text
    assert "revoked_grants=1" in revoked_text
    assert "revoked_favorites=1" in revoked_text

    member_revoked_text = next(
        line for line in text_lines if "event=favorite_access_revoked" in line
    )
    assert "reason=member_removed" in member_revoked_text
    assert f"wishlist_id={wl_id}" in member_revoked_text
    assert "user_id=202" in member_revoked_text
    assert "actor_id=101" in member_revoked_text

    revoked_json = next(
        p for p in json_payloads if p.get("extra", {}).get("event") == "share_access_revoked"
    )
    assert revoked_json["extra"]["reason"] == "public_token_rotated"
    assert revoked_json["extra"]["wishlist_id"] == wl_id
    assert revoked_json["extra"]["actor_id"] == 101
    assert revoked_json["extra"]["revoked_grants"] == 1
    assert revoked_json["extra"]["revoked_favorites"] == 1


def test_csrf_rejected_public_reservation_does_not_leak_token(
    favorites_app: tuple[TestClient, SessionTokenService, FastAPI, Path],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify CSRF-rejected public reservation requests redact public_token in all logs."""
    client, sessions, app, _ = favorites_app
    service: WishlistService = app.state.domain_service
    owner = AuthenticatedUser(telegram_id=101, first_name="Owner", auth_method="session_token")

    async def seed() -> str:
        wl = await service.create_wishlist(owner, title="CSRF Token Redaction List")
        return wl.public_token

    public_token = asyncio.run(seed())
    session_token = sessions.create_token(303, "Giver")
    client.cookies.set(app.state.settings.session_cookie_name, session_token)
    reservation_url = f"/api/public/wishlists/{public_token}/items/1/reservations"

    caplog.clear()
    with caplog.at_level(logging.WARNING):
        origin_resp = client.post(
            reservation_url,
            headers={"Origin": "https://evil.example"},
        )
        assert origin_resp.status_code == 403
        token_resp = client.post(
            reservation_url,
            headers={
                "Origin": app.state.settings.application_origin,
                "X-CSRF-Token": "invalid-csrf-token",
            },
        )
        assert token_resp.status_code == 403

    csrf_records = [
        r
        for r in caplog.records
        if r.name == "wishenka.web.security"
        and getattr(r, "event", None) in {"csrf_origin_mismatch", "csrf_token_invalid"}
    ]
    assert {getattr(r, "event", None) for r in csrf_records} == {
        "csrf_origin_mismatch",
        "csrf_token_invalid",
    }
    for rec in csrf_records:
        assert getattr(rec, "path", None) == "/api/public/wishlists/{token}"

    _assert_no_token_in_records(caplog.records, [public_token])

    text_formatter = TextFormatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    json_formatter = JsonFormatter()

    for rec in caplog.records:
        if not rec.name.startswith("wishenka"):
            continue
        text_line = text_formatter.format(rec)
        json_line = json_formatter.format(rec)
        assert public_token not in text_line
        assert public_token not in json_line
        payload = json.loads(json_line)
        assert public_token not in json.dumps(payload)
        if rec in csrf_records:
            assert "/api/public/wishlists/{token}" in text_line
            assert payload["extra"]["path"] == "/api/public/wishlists/{token}"


def test_access_control_events_not_emitted_on_transaction_rollback(
    favorites_app: tuple[TestClient, SessionTokenService, FastAPI, Path],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify share_access_granted and share_access_revoked are not emitted on rollback."""
    client, sessions, app, _ = favorites_app
    service: WishlistService = app.state.domain_service
    store = app.state.wishlist_store
    owner = AuthenticatedUser(telegram_id=101, first_name="Owner", auth_method="session_token")
    giver = AuthenticatedUser(telegram_id=303, first_name="Giver", auth_method="session_token")

    async def seed() -> tuple[int, str]:
        wl = await service.create_wishlist(owner, title="Rollback Obs List")
        return wl.id, wl.public_token

    wl_id, public_token = asyncio.run(seed())

    async def run_rollbacks() -> None:
        # 1. RepoWishlistOps rollback on share_access_granted
        with pytest.raises(RuntimeError, match="forced_grant_rollback"):
            async with asynccontextmanager(get_wishlist_repository)(store) as repo:
                ops = RepoWishlistOps(repo)
                await ops.get_wishlist_by_public_token(public_token, current_user=giver)
                raise RuntimeError("forced_grant_rollback")

        # 2. WishlistStore rollback on share_access_granted
        async def failing_store_grant(svc: WishlistService) -> None:
            await svc.get_wishlist_by_public_token(public_token, current_user=giver)
            raise RuntimeError("forced_store_grant_rollback")

        with pytest.raises(RuntimeError, match="forced_store_grant_rollback"):
            await store.execute(failing_store_grant, wishlist_id=wl_id)

    caplog.clear()
    with caplog.at_level(logging.INFO, logger="wishenka.wishlists"):
        asyncio.run(run_rollbacks())

    assert not [r for r in caplog.records if getattr(r, "event", None) == "share_access_granted"]

    # Now actually grant + favorite via HTTP so revocation has rows to revoke
    giver_headers = _bearer(sessions, 303)
    view_resp = client.get(f"/api/public/wishlists/{public_token}/view", headers=giver_headers)
    assert view_resp.status_code == 200
    assert client.post(f"/api/favorites/{wl_id}", headers=giver_headers).status_code == 200

    async def run_revoke_rollbacks() -> None:
        # 3. RepoWishlistOps rollback on share_access_revoked
        with pytest.raises(RuntimeError, match="forced_revoke_rollback"):
            async with asynccontextmanager(get_wishlist_repository)(store) as repo:
                ops = RepoWishlistOps(repo)
                await ops.regenerate_public_token(wl_id, owner)
                raise RuntimeError("forced_revoke_rollback")

        # 4. WishlistStore rollback on share_access_revoked
        async def failing_store_revoke(svc: WishlistService) -> None:
            await svc.regenerate_public_token(wl_id, owner)
            raise RuntimeError("forced_store_revoke_rollback")

        with pytest.raises(RuntimeError, match="forced_store_revoke_rollback"):
            await store.execute(failing_store_revoke, wishlist_id=wl_id)

    caplog.clear()
    with caplog.at_level(logging.INFO, logger="wishenka.wishlists"):
        asyncio.run(run_revoke_rollbacks())

    assert not [r for r in caplog.records if getattr(r, "event", None) == "share_access_revoked"]


def test_share_access_granted_not_emitted_when_user_missing_in_users(
    favorites_app: tuple[TestClient, SessionTokenService, FastAPI, Path],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify share_access_granted is suppressed when upsert_share_access writes 0 rows."""
    client, sessions, app, _ = favorites_app
    service: WishlistService = app.state.domain_service
    store = app.state.wishlist_store
    owner = AuthenticatedUser(telegram_id=101, first_name="Owner", auth_method="session_token")
    missing_user = AuthenticatedUser(
        telegram_id=999999, first_name="Ghost", auth_method="session_token"
    )

    async def seed() -> tuple[int, str]:
        wl = await service.create_wishlist(owner, title="Missing User Grant List")
        return wl.id, wl.public_token

    wl_id, public_token = asyncio.run(seed())

    async def verify_repo_return_value() -> tuple[bool, bool]:
        async with asynccontextmanager(get_wishlist_repository)(store) as repo:
            missing_persisted = await repo.upsert_share_access(
                ShareAccessGrant(
                    user_id=missing_user.telegram_id,
                    wishlist_id=wl_id,
                    public_token=public_token,
                )
            )
            existing_persisted = await repo.upsert_share_access(
                ShareAccessGrant(
                    user_id=303,
                    wishlist_id=wl_id,
                    public_token=public_token,
                )
            )
            return missing_persisted, existing_persisted

    missing_persisted, existing_persisted = asyncio.run(verify_repo_return_value())
    assert missing_persisted is False
    assert existing_persisted is True

    # HTTP route (RepoWishlistOps) with missing user must not emit share_access_granted
    missing_headers = _bearer(sessions, missing_user.telegram_id)
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="wishenka.wishlists"):
        resp = client.get(f"/api/public/wishlists/{public_token}/view", headers=missing_headers)
        assert resp.status_code == 200
        # WishlistService (WishlistStore) with missing user must also not emit share_access_granted
        asyncio.run(service.get_wishlist_by_public_token(public_token, current_user=missing_user))

    assert not [r for r in caplog.records if getattr(r, "event", None) == "share_access_granted"]
