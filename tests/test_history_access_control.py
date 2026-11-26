"""Automated failing repro tests for WISHENKA-303: Viewing History access control.

Asserts desired access control behavior:
1. An authenticated stranger (non-owner, non-member, no share-link visit) calling
   POST /api/history/{wishlist_id} receives HTTP 404 with the same error template as a
   non-existent wishlist ID, and GET /api/history returns [].
2. A legacy unverified non-member row in wl_view_history is not returned by
   GET /api/history.
3. An authenticated giver opening GET /api/public/wishlists/{token}/view automatically
   records the wishlist in Viewing History (GET /api/history includes it without a
   separate POST /api/history/{wishlist_id}), anonymous visits do not record history,
   and after POST /api/wishlists/{wishlist_id}/share/reset, GET /api/history returns []
   and POST /api/history/{wishlist_id} returns 404.
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

from tests.receipt_support import open_service
from wishenka.auth.models import AuthenticatedUser, TelegramUser
from wishenka.auth.session import SessionTokenService
from wishenka.config import Settings
from wishenka.logging import JsonFormatter, TextFormatter
from wishenka.web.app import create_app
from wishenka.web.dependencies import get_wishlist_repository
from wishenka.wishlists.exceptions import WishlistNotFoundError
from wishenka.wishlists.migrations import _configured
from wishenka.wishlists.models import WishlistRole
from wishenka.wishlists.repo_ops import RepoWishlistOps
from wishenka.wishlists.service import WishlistService

pytestmark = pytest.mark.timeout(30)


def _bearer(sessions: SessionTokenService, user_id: int) -> dict[str, str]:
    """Build Authorization header for a test user."""
    return {"Authorization": f"Bearer {sessions.create_token(user_id, 'User')}"}


@pytest.fixture
def history_app(
    tmp_path: Path,
) -> Iterator[tuple[TestClient, SessionTokenService, FastAPI, Path]]:
    """Initialize TestClient, SessionTokenService, app, and DB path."""
    db_path = tmp_path / "history_acl.db"
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{db_path}",
        secret_key="history-acl-test-secret",
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


def test_stranger_cannot_record_or_list_private_wishlist_in_history(
    history_app: tuple[TestClient, SessionTokenService, FastAPI, Path],
) -> None:
    """Stranger without membership or share-link access gets 404 and empty history."""
    client, sessions, app, _ = history_app
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

    missing_id = 999999
    missing_resp = client.post(f"/api/history/{missing_id}", headers=stranger_headers)
    assert missing_resp.status_code == 404

    stranger_resp = client.post(f"/api/history/{wl_id}", headers=stranger_headers)
    assert stranger_resp.status_code == 404
    assert stranger_resp.json()["detail"].replace(str(wl_id), "<id>") == (
        missing_resp.json()["detail"].replace(str(missing_id), "<id>")
    )

    list_resp = client.get("/api/history", headers=stranger_headers)
    assert list_resp.status_code == 200
    assert list_resp.json() == []


def test_legacy_unauthorized_history_row_is_not_listed(
    history_app: tuple[TestClient, SessionTokenService, FastAPI, Path],
) -> None:
    """A pre-existing unauthorized row in wl_view_history must not disclose metadata."""
    client, sessions, app, db_path = history_app
    service: WishlistService = app.state.domain_service
    owner = AuthenticatedUser(telegram_id=101, first_name="Owner", auth_method="session_token")

    async def seed_wishlist() -> int:
        wl = await service.create_wishlist(owner, title="Private Legacy List")
        return wl.id

    wl_id = asyncio.run(seed_wishlist())

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO wl_view_history (user_id, wishlist_id, viewed_at) VALUES (?, ?, ?)",
            (202, wl_id, datetime.now(UTC).isoformat()),
        )
        conn.commit()

    stranger_headers = _bearer(sessions, 202)
    list_resp = client.get("/api/history", headers=stranger_headers)
    assert list_resp.status_code == 200
    assert list_resp.json() == []


def test_giver_share_link_auto_records_history_and_revokes_on_token_rotation(
    history_app: tuple[TestClient, SessionTokenService, FastAPI, Path],
) -> None:
    """Authenticated share-link view auto-records history; token reset revokes it."""
    client, sessions, app, db_path = history_app
    service: WishlistService = app.state.domain_service
    owner = AuthenticatedUser(telegram_id=101, first_name="Owner", auth_method="session_token")

    async def seed_wishlist() -> tuple[int, str]:
        wl = await service.create_wishlist(owner, title="Shared Gift List")
        return wl.id, wl.public_token

    wl_id, public_token = asyncio.run(seed_wishlist())
    owner_headers = _bearer(sessions, 101)
    giver_headers = _bearer(sessions, 303)

    # 1. Anonymous share-link visit does not record history
    anon_view_resp = client.get(f"/api/public/wishlists/{public_token}/view")
    assert anon_view_resp.status_code == 200
    with sqlite3.connect(db_path) as conn:
        row_count = conn.execute(
            "SELECT COUNT(*) FROM wl_view_history WHERE wishlist_id = ?",
            (wl_id,),
        ).fetchone()[0]
    assert row_count == 0

    # 2. Authenticated giver opens wishlist via active share link -> auto-recorded in history
    view_resp = client.get(f"/api/public/wishlists/{public_token}/view", headers=giver_headers)
    assert view_resp.status_code == 200

    list_resp = client.get("/api/history", headers=giver_headers)
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert len(items) == 1
    assert items[0]["id"] == wl_id

    # Explicit POST /api/history/{wl_id} also succeeds while share-link access is valid
    record_resp = client.post(f"/api/history/{wl_id}", headers=giver_headers)
    assert record_resp.status_code == 200
    assert record_resp.json() == {"status": "recorded", "wishlist_id": wl_id}

    # 3. Owner rotates share link -> giver loses Viewing History access
    reset_resp = client.post(f"/api/wishlists/{wl_id}/share/reset", headers=owner_headers)
    assert reset_resp.status_code == 200

    after_reset_list = client.get("/api/history", headers=giver_headers)
    assert after_reset_list.status_code == 200
    assert after_reset_list.json() == []

    after_reset_record = client.post(f"/api/history/{wl_id}", headers=giver_headers)
    assert after_reset_record.status_code == 404


def test_owner_can_record_and_list_own_wishlist_in_history(
    history_app: tuple[TestClient, SessionTokenService, FastAPI, Path],
) -> None:
    """Owner is allowed to record views of their own non-deleted wishlist."""
    client, sessions, app, _ = history_app
    service: WishlistService = app.state.domain_service
    owner = AuthenticatedUser(telegram_id=101, first_name="Owner", auth_method="session_token")

    async def seed_wishlist() -> int:
        wl = await service.create_wishlist(owner, title="Owner Self-View List")
        return wl.id

    wl_id = asyncio.run(seed_wishlist())
    owner_headers = _bearer(sessions, 101)

    rec = client.post(f"/api/history/{wl_id}", headers=owner_headers)
    assert rec.status_code == 200
    assert rec.json() == {"status": "recorded", "wishlist_id": wl_id}

    hist = client.get("/api/history", headers=owner_headers)
    assert hist.status_code == 200
    items = hist.json()
    assert len(items) == 1
    assert items[0]["id"] == wl_id
    assert items[0]["role"] == "owner"


def test_html_share_route_auto_records_for_authenticated_user_only(
    history_app: tuple[TestClient, SessionTokenService, FastAPI, Path],
) -> None:
    """GET /share/{public_token} records history when authenticated, not when anonymous."""
    client, sessions, app, db_path = history_app
    service: WishlistService = app.state.domain_service
    owner = AuthenticatedUser(telegram_id=101, first_name="Owner", auth_method="session_token")

    async def seed_wishlist() -> tuple[int, str]:
        wl = await service.create_wishlist(owner, title="HTML Share List")
        return wl.id, wl.public_token

    wl_id, public_token = asyncio.run(seed_wishlist())

    anon_resp = client.get(f"/share/{public_token}")
    assert anon_resp.status_code == 200
    with sqlite3.connect(db_path) as conn:
        cnt = conn.execute(
            "SELECT COUNT(*) FROM wl_view_history WHERE wishlist_id = ?", (wl_id,)
        ).fetchone()[0]
    assert cnt == 0

    giver_headers = _bearer(sessions, 303)
    auth_resp = client.get(f"/share/{public_token}", headers=giver_headers)
    assert auth_resp.status_code == 200

    hist = client.get("/api/history", headers=giver_headers)
    assert hist.status_code == 200
    assert [item["id"] for item in hist.json()] == [wl_id]


def test_participant_history_and_removal_revocation_vs_retained_share_access(
    history_app: tuple[TestClient, SessionTokenService, FastAPI, Path],
) -> None:
    """Participant can record history; removal revokes unless share-link access is held."""
    client, sessions, app, _ = history_app
    service: WishlistService = app.state.domain_service
    owner = AuthenticatedUser(telegram_id=101, first_name="Owner", auth_method="session_token")

    async def seed_collab() -> tuple[int, str]:
        wl = await service.create_wishlist(owner, title="Collab History List")
        await service.add_member(wl.id, owner, user_id=202, role=WishlistRole.MEMBER)
        await service.add_member(wl.id, owner, user_id=303, role=WishlistRole.MEMBER)
        return wl.id, wl.public_token

    wl_id, public_token = asyncio.run(seed_collab())
    owner_headers = _bearer(sessions, 101)
    member_no_share_headers = _bearer(sessions, 202)
    member_with_share_headers = _bearer(sessions, 303)

    # Both members can record without opening share link
    assert client.post(f"/api/history/{wl_id}", headers=member_no_share_headers).status_code == 200
    # Member 303 also opens the active share link
    assert (
        client.get(
            f"/api/public/wishlists/{public_token}/view", headers=member_with_share_headers
        ).status_code
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

    # Member 202 (no share access) loses history and gets 404 on new record
    assert client.get("/api/history", headers=member_no_share_headers).json() == []
    assert client.post(f"/api/history/{wl_id}", headers=member_no_share_headers).status_code == 404

    # Member 303 (retained active share-link access) keeps history until token reset
    assert [
        i["id"] for i in client.get("/api/history", headers=member_with_share_headers).json()
    ] == [wl_id]
    assert (
        client.post(f"/api/history/{wl_id}", headers=member_with_share_headers).status_code == 200
    )


@pytest.mark.parametrize("idempotency_key", ["res-history-access-1", None])
def test_reservation_grants_share_access_for_history_and_reset_revokes_it(
    history_app: tuple[TestClient, SessionTokenService, FastAPI, Path],
    idempotency_key: str | None,
) -> None:
    """Reservation via execute_wish_idempotent / execute_wish grants history access until reset."""
    client, sessions, app, db_path = history_app
    service: WishlistService = app.state.domain_service
    owner = AuthenticatedUser(telegram_id=101, first_name="Owner", auth_method="session_token")

    async def seed_with_item() -> tuple[int, str, int]:
        wl = await service.create_wishlist(owner, title="Reservation History List")
        item = await service.add_wish_item(wl.id, actor=owner, title="Board Game", quantity=2)
        return wl.id, wl.public_token, item.id

    wl_id, public_token, item_id = asyncio.run(seed_with_item())
    owner_headers = _bearer(sessions, 101)
    giver_headers = _bearer(sessions, 303)

    # Giver reserves directly via public link (covers execute_wish_idempotent and execute_wish)
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

    with sqlite3.connect(db_path) as conn:
        sa_count = conn.execute(
            "SELECT COUNT(*) FROM wl_share_access WHERE user_id = 303 AND wishlist_id = ?",
            (wl_id,),
        ).fetchone()[0]
    assert sa_count == 1

    # Persisted wl_share_access grant allows POST /api/history/{wl_id} and GET /api/history
    rec_resp = client.post(f"/api/history/{wl_id}", headers=giver_headers)
    assert rec_resp.status_code == 200
    assert rec_resp.json() == {"status": "recorded", "wishlist_id": wl_id}

    hist_resp = client.get("/api/history", headers=giver_headers)
    assert hist_resp.status_code == 200
    assert [item["id"] for item in hist_resp.json()] == [wl_id]

    # Rotating/revoking the share link revokes history access
    reset_resp = client.post(f"/api/wishlists/{wl_id}/share/reset", headers=owner_headers)
    assert reset_resp.status_code == 200

    after_reset_hist = client.get("/api/history", headers=giver_headers)
    assert after_reset_hist.status_code == 200
    assert after_reset_hist.json() == []

    after_reset_rec = client.post(f"/api/history/{wl_id}", headers=giver_headers)
    assert after_reset_rec.status_code == 404


def test_restore_deleted_wishlist_revokes_non_member_history(
    history_app: tuple[TestClient, SessionTokenService, FastAPI, Path],
) -> None:
    """Soft-deleting and restoring a wishlist rotates token and revokes non-member history."""
    client, sessions, app, db_path = history_app
    service: WishlistService = app.state.domain_service
    owner = AuthenticatedUser(telegram_id=101, first_name="Owner", auth_method="session_token")

    async def seed_wishlist() -> tuple[int, str]:
        wl = await service.create_wishlist(owner, title="Restorable History List")
        return wl.id, wl.public_token

    wl_id, public_token = asyncio.run(seed_wishlist())
    owner_headers = _bearer(sessions, 101)
    giver_headers = _bearer(sessions, 303)

    assert (
        client.get(f"/api/public/wishlists/{public_token}/view", headers=giver_headers).status_code
        == 200
    )
    assert [i["id"] for i in client.get("/api/history", headers=giver_headers).json()] == [wl_id]

    assert client.delete(f"/api/wishlists/{wl_id}", headers=owner_headers).status_code == 200
    # Deleted wishlist is hidden from history
    assert client.get("/api/history", headers=giver_headers).json() == []
    assert client.post(f"/api/history/{wl_id}", headers=giver_headers).status_code == 404

    assert (
        client.post(f"/api/wishlists/{wl_id}/restore-deleted", headers=owner_headers).status_code
        == 200
    )
    # After restore, giver's history remains revoked
    assert client.get("/api/history", headers=giver_headers).json() == []
    assert client.post(f"/api/history/{wl_id}", headers=giver_headers).status_code == 404
    with sqlite3.connect(db_path) as conn:
        cnt = conn.execute(
            "SELECT COUNT(*) FROM wl_view_history WHERE wishlist_id = ? AND user_id = 303",
            (wl_id,),
        ).fetchone()[0]
    assert cnt == 0


@pytest.mark.asyncio
async def test_transfer_ownership_preserves_members_and_revokes_non_member_history(
    tmp_path: Path,
) -> None:
    """Transferring ownership keeps new & old owner history while purging non-member viewers."""
    owner = AuthenticatedUser(telegram_id=101, first_name="Owner", auth_method="session_token")
    new_owner = AuthenticatedUser(
        telegram_id=202, first_name="NewOwner", auth_method="session_token"
    )
    giver = AuthenticatedUser(telegram_id=303, first_name="Giver", auth_method="session_token")
    async with open_service(tmp_path / "hist-transfer.db", owner, new_owner, giver) as service:
        await _transfer_keeps_member_history(service, owner, new_owner, giver)


async def _transfer_keeps_member_history(
    service: WishlistService,
    owner: AuthenticatedUser,
    new_owner: AuthenticatedUser,
    giver: AuthenticatedUser,
) -> None:
    wl = await service.create_wishlist(owner, title="Transfer History List")
    old_public_token = wl.public_token
    await service.add_member(wl.id, owner, new_owner.telegram_id, WishlistRole.ADMIN)

    await service.record_view(owner, wl.id)
    await service.record_view(new_owner, wl.id)
    await service.get_wishlist_by_public_token(old_public_token, current_user=giver)
    await service.record_view(giver, wl.id)

    transferred = await service.transfer_ownership(wl.id, owner, new_owner.telegram_id)
    assert transferred.public_token != old_public_token

    # Both new owner and demoted old owner (now ADMIN member) retain history
    assert [w.id for w, _ in await service.get_history(new_owner)] == [wl.id]
    assert [w.id for w, _ in await service.get_history(owner)] == [wl.id]

    # Non-member giver loses history and cannot record again
    assert await service.get_history(giver) == []
    with pytest.raises(WishlistNotFoundError):
        await service.record_view(giver, wl.id)


def test_migration_upgrade_purges_unverified_history_and_downgrade_refuses(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Upgrade purges unverified non-member wl_view_history; one-way downgrade refuses."""
    db_path = tmp_path / "migration_history.db"
    cfg = _configured(f"sqlite+aiosqlite:///{db_path}")

    command.upgrade(cfg, "add_share_access_and_purge_favorites")
    with sqlite3.connect(db_path) as conn:
        now = datetime.now(UTC).isoformat()
        for uid in (101, 202, 303, 404, 505):
            conn.execute(
                "INSERT INTO users (telegram_id, first_name, created_at, updated_at) "
                "VALUES (?, ?, ?, ?)",
                (uid, f"User{uid}", now, now),
            )
        conn.execute(
            "INSERT INTO wl_lists "
            "(id, owner_id, owner_name, title, is_collaborative, status, public_token, "
            "invite_token, created_at, updated_at) "
            "VALUES (1, 101, 'Owner', 'Private', 1, 'active', 'pub-active', 'inv-1', ?, ?)",
            (now, now),
        )
        conn.execute(
            "INSERT INTO wl_members (id, wishlist_id, user_id, role, joined_at) "
            "VALUES (1, 1, 202, 'member', ?)",
            (now,),
        )
        # 303 has active share access; 404 has stale token; 505 has no share access
        conn.execute(
            "INSERT INTO wl_share_access (user_id, wishlist_id, public_token, granted_at) "
            "VALUES (303, 1, 'pub-active', ?)",
            (now,),
        )
        conn.execute(
            "INSERT INTO wl_share_access (user_id, wishlist_id, public_token, granted_at) "
            "VALUES (404, 1, 'pub-stale', ?)",
            (now,),
        )
        for uid in (101, 202, 303, 404, 505):
            conn.execute(
                "INSERT INTO wl_view_history (user_id, wishlist_id, viewed_at) VALUES (?, 1, ?)",
                (uid, now),
            )
        conn.commit()

    command.upgrade(cfg, "head")
    with sqlite3.connect(db_path) as conn:
        remaining = conn.execute(
            "SELECT user_id FROM wl_view_history WHERE wishlist_id = 1 ORDER BY user_id"
        ).fetchall()
        assert remaining == [(101,), (202,), (303,)]

    with (
        caplog.at_level(logging.WARNING, logger="wishenka.wishlists.migrations"),
        pytest.raises(NotImplementedError, match="(?i)backup"),
    ):
        command.downgrade(cfg, "add_share_access_and_purge_favorites")

    assert any(
        getattr(r, "event", None) == "wishlist_migration_downgrade_refused"
        and getattr(r, "revision", None) == "purge_legacy_non_member_view_history"
        and r.levelno == logging.WARNING
        for r in caplog.records
    )


def test_history_access_control_formatted_log_output(
    history_app: tuple[TestClient, SessionTokenService, FastAPI, Path],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify TextFormatter and JsonFormatter output for history access-control events."""
    client, sessions, app, _ = history_app
    service: WishlistService = app.state.domain_service
    owner = AuthenticatedUser(telegram_id=101, first_name="Owner", auth_method="session_token")
    secret_title = "Secret History Observability Title"

    async def seed() -> tuple[int, str, int, str]:
        wl = await service.create_wishlist(owner, title=secret_title)
        await service.add_member(wl.id, owner, 202, WishlistRole.MEMBER)
        del_wl = await service.create_wishlist(owner, title="Secret Deleted History Title")
        await service.delete_wishlist(del_wl.id, actor=owner)
        return wl.id, wl.public_token, del_wl.id, del_wl.public_token

    wl_id, public_token, deleted_wl_id, deleted_public_token = asyncio.run(seed())
    owner_headers = _bearer(sessions, 101)
    member_headers = _bearer(sessions, 202)
    stranger_headers = _bearer(sessions, 303)
    tokens_seen = [public_token, deleted_public_token]

    caplog.clear()
    with caplog.at_level(logging.INFO, logger="wishenka.wishlists"):
        assert client.post(f"/api/history/{wl_id}", headers=stranger_headers).status_code == 404
        assert (
            client.post(f"/api/history/{deleted_wl_id}", headers=stranger_headers).status_code
            == 404
        )
        assert (
            client.get(
                f"/api/public/wishlists/{public_token}/view", headers=stranger_headers
            ).status_code
            == 200
        )
        reset_resp = client.post(f"/api/wishlists/{wl_id}/share/reset", headers=owner_headers)
        assert reset_resp.status_code == 200
        tokens_seen.append(reset_resp.json()["share_token"])
        assert client.post(f"/api/history/{wl_id}", headers=member_headers).status_code == 200
        assert (
            client.delete(f"/api/wishlists/{wl_id}/members/202", headers=owner_headers).status_code
            == 200
        )

    text_formatter = TextFormatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    json_formatter = JsonFormatter()

    expected_events = {
        "view_history_access_denied",
        "view_history_deleted_wishlist_denied",
        "share_access_granted",
        "share_access_revoked",
        "view_history_access_revoked",
    }
    target_records = [r for r in caplog.records if getattr(r, "event", None) in expected_events]
    assert {getattr(r, "event", None) for r in target_records} == expected_events

    text_lines = [text_formatter.format(r) for r in target_records]
    json_payloads = [json.loads(json_formatter.format(r)) for r in target_records]

    for line, payload in zip(text_lines, json_payloads, strict=True):
        assert secret_title not in line
        assert secret_title not in json.dumps(payload)
        assert "Secret Deleted History Title" not in line
        assert "Secret Deleted History Title" not in json.dumps(payload)
        for tok in tokens_seen:
            assert tok not in line
            assert tok not in json.dumps(payload)

    denied_text = next(line for line in text_lines if "event=view_history_access_denied" in line)
    assert f"wishlist_id={wl_id}" in denied_text
    assert "user_id=303" in denied_text

    deleted_denied_text = next(
        line for line in text_lines if "event=view_history_deleted_wishlist_denied" in line
    )
    assert f"wishlist_id={deleted_wl_id}" in deleted_denied_text
    assert "user_id=303" in deleted_denied_text

    deleted_denied_json = next(
        p
        for p in json_payloads
        if p.get("extra", {}).get("event") == "view_history_deleted_wishlist_denied"
    )
    assert deleted_denied_json["extra"]["wishlist_id"] == deleted_wl_id
    assert deleted_denied_json["extra"]["user_id"] == 303

    revoked_text = next(line for line in text_lines if "event=share_access_revoked" in line)
    assert "reason=public_token_rotated" in revoked_text
    assert f"wishlist_id={wl_id}" in revoked_text
    assert "actor_id=101" in revoked_text
    assert "revoked_grants=1" in revoked_text
    assert "revoked_history=1" in revoked_text

    member_revoked_text = next(
        line for line in text_lines if "event=view_history_access_revoked" in line
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
    assert revoked_json["extra"]["revoked_history"] == 1

    member_revoked_json = next(
        p for p in json_payloads if p.get("extra", {}).get("event") == "view_history_access_revoked"
    )
    assert member_revoked_json["extra"]["reason"] == "member_removed"
    assert member_revoked_json["extra"]["wishlist_id"] == wl_id
    assert member_revoked_json["extra"]["user_id"] == 202
    assert member_revoked_json["extra"]["actor_id"] == 101


def test_history_access_control_events_not_emitted_on_transaction_rollback(
    history_app: tuple[TestClient, SessionTokenService, FastAPI, Path],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify share_access_revoked and view_history_access_revoked are suppressed on rollback."""
    client, sessions, app, _ = history_app
    service: WishlistService = app.state.domain_service
    store = app.state.wishlist_store
    owner = AuthenticatedUser(telegram_id=101, first_name="Owner", auth_method="session_token")

    async def seed() -> tuple[int, str]:
        wl = await service.create_wishlist(owner, title="Rollback History Obs List")
        await service.add_member(wl.id, owner, 202, WishlistRole.MEMBER)
        return wl.id, wl.public_token

    wl_id, public_token = asyncio.run(seed())
    member_headers = _bearer(sessions, 202)
    giver_headers = _bearer(sessions, 303)

    # Seed active share-link history (303) and member history (202)
    assert (
        client.get(f"/api/public/wishlists/{public_token}/view", headers=giver_headers).status_code
        == 200
    )
    assert client.post(f"/api/history/{wl_id}", headers=member_headers).status_code == 200

    async def run_revoke_rollbacks() -> None:
        # 1. RepoWishlistOps rollback on share_access_revoked (token rotation)
        with pytest.raises(RuntimeError, match="forced_share_revoke_rollback"):
            async with asynccontextmanager(get_wishlist_repository)(store) as repo:
                ops = RepoWishlistOps(repo)
                await ops.regenerate_public_token(wl_id, owner)
                raise RuntimeError("forced_share_revoke_rollback")

        # 2. WishlistStore rollback on share_access_revoked (token rotation)
        async def failing_store_share_revoke(svc: WishlistService) -> None:
            await svc.regenerate_public_token(wl_id, owner)

        with pytest.raises(WishlistNotFoundError, match="repository path"):
            await store.execute(failing_store_share_revoke, wishlist_id=wl_id)

        # 3. RepoWishlistOps rollback on view_history_access_revoked (member removal)
        with pytest.raises(RuntimeError, match="forced_member_history_rollback"):
            async with asynccontextmanager(get_wishlist_repository)(store) as repo:
                ops = RepoWishlistOps(repo)
                await ops.remove_member(wl_id, owner, 202)
                raise RuntimeError("forced_member_history_rollback")

        # 4. WishlistStore rollback on view_history_access_revoked (member removal)
        async def failing_store_member_revoke(svc: WishlistService) -> None:
            await svc.remove_member(wl_id, owner, 202)

        with pytest.raises(WishlistNotFoundError, match="repository path"):
            await store.execute(failing_store_member_revoke, wishlist_id=wl_id)

    caplog.clear()
    with caplog.at_level(logging.INFO, logger="wishenka.wishlists"):
        asyncio.run(run_revoke_rollbacks())

    assert not [
        r
        for r in caplog.records
        if getattr(r, "event", None) in {"share_access_revoked", "view_history_access_revoked"}
    ]


def test_injected_in_memory_service_records_share_view_without_db_user_row(
    history_app: tuple[TestClient, SessionTokenService, FastAPI, Path],
) -> None:
    """The repository share path records a view for a persisted viewer."""
    client, sessions, app, _ = history_app
    owner = AuthenticatedUser(telegram_id=101, first_name="Owner", auth_method="session_token")

    async def seed() -> tuple[int, str]:
        await app.state.user_store.upsert_user(TelegramUser(id=101, first_name="Owner"))
        await app.state.user_store.upsert_user(TelegramUser(id=777777, first_name="Viewer"))
        await app.state.user_store.upsert_user(TelegramUser(id=888888, first_name="Other"))
        wl = await app.state.domain_service.create_wishlist(owner, title="Shared List")
        return int(wl.id), str(wl.public_token)

    portal = client.portal
    assert portal is not None
    wl_id, public_token = portal.call(seed)
    unregistered_headers = _bearer(sessions, 777777)
    share_resp = client.get(f"/share/{public_token}", headers=unregistered_headers)
    assert share_resp.status_code == 200

    history_resp = client.get("/api/history", headers=unregistered_headers)
    assert history_resp.status_code == 200
    assert [item["id"] for item in history_resp.json()] == [wl_id]

    other_headers = _bearer(sessions, 888888)
    api_resp = client.get(f"/api/public/wishlists/{public_token}/view", headers=other_headers)
    assert api_resp.status_code == 200

    other_history = client.get("/api/history", headers=other_headers)
    assert other_history.status_code == 200
    assert [item["id"] for item in other_history.json()] == [wl_id]
