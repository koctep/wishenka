"""Failing repro tests for WISHENKA-86 (Step 3, red before Step 4)."""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from wishenka.auth.models import AuthenticatedUser
from wishenka.auth.session import SessionTokenService
from wishenka.config import Settings
from wishenka.i18n.catalog import miniapp_catalog
from wishenka.logging import JsonFormatter
from wishenka.web.app import create_app
from wishenka.wishlists.models import ReservationStatus, WishlistStatus
from wishenka.wishlists.service import WishlistService

pytestmark = pytest.mark.timeout(30)

OWNER_ID = 101
ADMIN_ID = 102
MEMBER_ID = 103
GIFTER_ID = 202
STRANGER_ID = 303


def _make_settings(db_path: Path, retention_days: int = 30) -> Settings:
    return Settings(
        database_url=f"sqlite+aiosqlite:///{db_path}",
        sqlite_db_path=str(db_path),
        secret_key="test-secret-key",
        wishlist_retention_days=retention_days,
    )


def _auth_headers(sessions: SessionTokenService, user_id: int, name: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {sessions.create_token(user_id, name)}"}


def test_deleted_wishlist_restore_flow_permissions_tokens_and_reservations(
    tmp_path: Path,
) -> None:
    """Owner lists/restores deleted wishlist; tokens rotate and reservations stay cancelled."""
    db_path = tmp_path / "restore-flow.db"
    settings = _make_settings(db_path, retention_days=30)
    sessions = SessionTokenService(settings.secret_key)
    owner_headers = _auth_headers(sessions, OWNER_ID, "Owner")
    admin_headers = _auth_headers(sessions, ADMIN_ID, "Admin")
    member_headers = _auth_headers(sessions, MEMBER_ID, "Member")
    stranger_headers = _auth_headers(sessions, STRANGER_ID, "Stranger")

    owner_user = AuthenticatedUser(
        telegram_id=OWNER_ID, first_name="Owner", auth_method="session_token"
    )
    gifter_user = AuthenticatedUser(
        telegram_id=GIFTER_ID, first_name="Giver", auth_method="session_token"
    )

    app = create_app(settings)
    with TestClient(app) as client:
        # 1. Owner creates wishlist, adds wish item, invites admin & member
        created = client.post(
            "/api/wishlists",
            json={"name": "Birthday", "description": "My gifts"},
            headers=owner_headers,
        )
        assert created.status_code == 201
        wl_data = created.json()
        wishlist_id = wl_data["id"]
        old_share_token = wl_data["share_token"]
        old_invite_token = wl_data["invite_token"]

        item_resp = client.post(
            f"/api/wishlists/{wishlist_id}/items",
            json={"title": "Espresso Machine", "quantity": 3},
            headers=owner_headers,
        )
        assert item_resp.status_code == 201
        item_id = item_resp.json()["id"]

        assert (
            client.post(
                "/api/invitations/accept",
                headers={**admin_headers, "x-invite-token": old_invite_token},
            ).status_code
            == 200
        )
        assert (
            client.patch(
                f"/api/wishlists/{wishlist_id}/members/{ADMIN_ID}/role",
                json={"role": "admin"},
                headers=owner_headers,
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/api/invitations/accept",
                headers={**member_headers, "x-invite-token": old_invite_token},
            ).status_code
            == 200
        )

        # Record fulfillment (gift receipt history), create reservation, then soft-delete
        async def seed_and_delete(service: WishlistService) -> int:
            await service.record_item_fulfillment(item_id, owner_user, 1)
            reservation = await service.create_reservation(item_id, gifter_user, quantity=1)
            await service.delete_wishlist(wishlist_id, owner_user)
            return reservation.id

        assert client.portal is not None
        reservation_id = client.portal.call(app.state.wishlist_store.execute, seed_and_delete)

        # 2. GET /api/wishlists/deleted visible ONLY to owner
        owner_deleted = client.get("/api/wishlists/deleted", headers=owner_headers)
        assert owner_deleted.status_code == 200
        deleted_list = owner_deleted.json()
        assert len(deleted_list) == 1
        assert deleted_list[0]["id"] == wishlist_id
        assert deleted_list[0]["name"] == "Birthday"
        assert "deleted_at" in deleted_list[0]
        assert "expires_at" in deleted_list[0]
        assert 1 <= deleted_list[0]["days_remaining"] <= 30

        for non_owner_headers in (admin_headers, member_headers, stranger_headers):
            resp = client.get("/api/wishlists/deleted", headers=non_owner_headers)
            assert resp.status_code == 200
            assert resp.json() == []

        # 3. Non-owners get 404 on restore-deleted
        for non_owner_headers in (admin_headers, member_headers, stranger_headers):
            resp = client.post(
                f"/api/wishlists/{wishlist_id}/restore-deleted",
                headers=non_owner_headers,
            )
            assert resp.status_code == 404

        # Owner restores within retention window -> 200 OK, status=active, tokens rotated
        restore_resp = client.post(
            f"/api/wishlists/{wishlist_id}/restore-deleted",
            headers=owner_headers,
        )
        assert restore_resp.status_code == 200
        restored = restore_resp.json()
        assert restored["id"] == wishlist_id
        assert restored["status"] == "active"
        assert restored["share_token"] != old_share_token
        assert restored["invite_token"] != old_invite_token
        assert len(restored["items"]) == 1
        assert restored["items"][0]["received_quantity"] == 1
        # Surprise Invariant: no reservation data leaked to recipient projection
        assert "reservations" not in restored["items"][0]
        assert "reserved_quantity" not in restored["items"][0]

        # Restored wishlist appears in GET /api/wishlists and disappears from /deleted
        active_lists = client.get("/api/wishlists", headers=owner_headers)
        assert active_lists.status_code == 200
        assert [wl["id"] for wl in active_lists.json()] == [wishlist_id]

        assert client.get("/api/wishlists/deleted", headers=owner_headers).json() == []

        # Old public_token and invite_token are rejected with 404
        assert client.get(f"/api/public/wishlists/{old_share_token}").status_code == 404
        assert (
            client.get(
                "/api/invitations/preview",
                headers={"x-invite-token": old_invite_token},
            ).status_code
            == 404
        )

        # Cancelled reservation stays CANCELLED
        async def check_reservation(service: WishlistService) -> ReservationStatus:
            return service._reservations[reservation_id].status

        assert client.portal is not None
        res_status = client.portal.call(app.state.wishlist_store.execute, check_reservation)
        assert res_status == ReservationStatus.CANCELLED

        # 4. Idempotent second restore-deleted -> 200 OK without duplicates
        second_restore = client.post(
            f"/api/wishlists/{wishlist_id}/restore-deleted",
            headers=owner_headers,
        )
        assert second_restore.status_code == 200
        assert second_restore.json()["id"] == wishlist_id
        assert second_restore.json()["status"] == "active"
        assert len(client.get("/api/wishlists", headers=owner_headers).json()) == 1


def test_deleted_wishlist_retention_expired_returns_410_and_hides_from_list(
    tmp_path: Path,
) -> None:
    """Expired deleted wishlist is hidden from /deleted and returns 410 Gone on restore-deleted."""
    db_path = tmp_path / "restore-expired.db"
    settings = _make_settings(db_path, retention_days=30)
    sessions = SessionTokenService(settings.secret_key)
    owner_headers = _auth_headers(sessions, OWNER_ID, "Owner")
    owner_user = AuthenticatedUser(
        telegram_id=OWNER_ID, first_name="Owner", auth_method="session_token"
    )

    app = create_app(settings)
    with TestClient(app) as client:
        created = client.post("/api/wishlists", json={"name": "Old List"}, headers=owner_headers)
        assert created.status_code == 201
        wishlist_id = created.json()["id"]

        async def soft_delete(service: WishlistService) -> None:
            await service.delete_wishlist(wishlist_id, owner_user)

        assert client.portal is not None
        client.portal.call(app.state.wishlist_store.execute, soft_delete)

    # Shift updated_at past the 30-day retention window before background purge runs
    expired_at = (datetime.now(UTC) - timedelta(days=31)).isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE wl_lists SET updated_at = ? WHERE id = ?",
            (expired_at, wishlist_id),
        )
        conn.commit()

    reloaded_app = create_app(settings)
    with TestClient(reloaded_app) as client:
        deleted_resp = client.get("/api/wishlists/deleted", headers=owner_headers)
        assert deleted_resp.status_code == 200
        assert deleted_resp.json() == []

        restore_resp = client.post(
            f"/api/wishlists/{wishlist_id}/restore-deleted",
            headers=owner_headers,
        )
        assert restore_resp.status_code == 410


def test_restore_deleted_archived_returns_409_and_missing_returns_404(tmp_path: Path) -> None:
    """Archived wishlists return 409 Conflict and non-existent wishlists return 404 Not Found."""
    db_path = tmp_path / "restore-edge.db"
    settings = _make_settings(db_path, retention_days=30)
    sessions = SessionTokenService(settings.secret_key)
    owner_headers = _auth_headers(sessions, OWNER_ID, "Owner")
    owner_user = AuthenticatedUser(
        telegram_id=OWNER_ID, first_name="Owner", auth_method="session_token"
    )

    app = create_app(settings)
    with TestClient(app) as client:
        created = client.post(
            "/api/wishlists", json={"name": "Archived List"}, headers=owner_headers
        )
        assert created.status_code == 201
        wishlist_id = created.json()["id"]

        async def archive_it(service: WishlistService) -> None:
            await service.archive_wishlist(wishlist_id, owner_user)

        assert client.portal is not None
        client.portal.call(app.state.wishlist_store.execute, archive_it)

        archived_resp = client.post(
            f"/api/wishlists/{wishlist_id}/restore-deleted",
            headers=owner_headers,
        )
        assert archived_resp.status_code == 409

        missing_resp = client.post(
            "/api/wishlists/999999/restore-deleted",
            headers=owner_headers,
        )
        assert missing_resp.status_code == 404


def test_service_list_deleted_wishlists_sorting_and_days_remaining(tmp_path: Path) -> None:
    """list_deleted_wishlists sorts newest-first and rounds days_remaining up to at least 1."""
    db_path = tmp_path / "restore-sort.db"
    settings = _make_settings(db_path, retention_days=30)
    sessions = SessionTokenService(settings.secret_key)
    owner_headers = _auth_headers(sessions, OWNER_ID, "Owner")
    owner_user = AuthenticatedUser(
        telegram_id=OWNER_ID, first_name="Owner", auth_method="session_token"
    )

    app = create_app(settings)
    with TestClient(app) as client:
        older_id = client.post(
            "/api/wishlists", json={"name": "Older Deleted"}, headers=owner_headers
        ).json()["id"]
        newer_id = client.post(
            "/api/wishlists", json={"name": "Newer Deleted"}, headers=owner_headers
        ).json()["id"]

        now = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)

        async def setup_and_list(service: WishlistService) -> list[tuple[int, int, WishlistStatus]]:
            await service.delete_wishlist(older_id, owner_user)
            await service.delete_wishlist(newer_id, owner_user)
            service._wishlists[older_id].updated_at = now - timedelta(days=29, hours=23)
            service._wishlists[newer_id].updated_at = now - timedelta(days=10)
            entries = await service.list_deleted_wishlists(owner_user, retention_days=30, now=now)
            return [(wl.id, days, wl.status) for wl, _exp, days in entries]

        assert client.portal is not None
        rows = client.portal.call(app.state.wishlist_store.execute, setup_and_list)
        assert rows == [
            (newer_id, 20, WishlistStatus.DELETED),
            (older_id, 1, WishlistStatus.DELETED),
        ]


def test_deleted_i18n_keys_and_miniapp_ui_wiring() -> None:
    """RU and EN catalogs define miniapp.deleted.* keys and miniapp.js wires the UI."""
    catalog = miniapp_catalog()
    expected_keys = {
        "miniapp.deleted.heading",
        "miniapp.deleted.days_left",
        "miniapp.deleted.restore",
        "miniapp.deleted.restoring",
        "miniapp.deleted.restored",
        "miniapp.deleted.expired",
        "miniapp.deleted.restore_failed",
    }
    for locale in ("en", "ru"):
        for key in expected_keys:
            assert key in catalog[locale]
            assert catalog[locale][key].strip()

    miniapp_js = Path("wishenka/web/static/miniapp.js").read_text(encoding="utf-8")
    assert "/api/wishlists/deleted" in miniapp_js
    assert "/restore-deleted" in miniapp_js
    for key in expected_keys:
        assert key in miniapp_js


def test_deleted_restore_observability_logs(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Deleted list, restore, and retention-expired emit structured logs without PII or tokens."""
    db_path = tmp_path / "restore-obs.db"
    settings = _make_settings(db_path, retention_days=30)
    sessions = SessionTokenService(settings.secret_key)
    owner_headers = _auth_headers(sessions, OWNER_ID, "Owner")
    app = create_app(settings)
    formatter = JsonFormatter()

    with TestClient(app) as client:
        wl_ok = client.post(
            "/api/wishlists",
            json={"name": "SecretBirthdayTitle"},
            headers=owner_headers,
        ).json()
        ok_id = wl_ok["id"]
        wl_exp = client.post(
            "/api/wishlists",
            json={"name": "ExpiredSecretTitle"},
            headers=owner_headers,
        ).json()
        exp_id = wl_exp["id"]

        owner_user = AuthenticatedUser(
            telegram_id=OWNER_ID, first_name="Owner", auth_method="session_token"
        )

        async def _delete_both(service: WishlistService) -> None:
            await service.delete_wishlist(ok_id, owner_user)
            await service.delete_wishlist(exp_id, owner_user)
            service._wishlists[exp_id].updated_at = datetime.now(UTC) - timedelta(days=31)

        assert client.portal is not None
        client.portal.call(app.state.wishlist_store.execute, _delete_both)

        with caplog.at_level(logging.INFO, logger="wishenka"):
            list_resp = client.get("/api/wishlists/deleted", headers=owner_headers)
            assert list_resp.status_code == 200
            restore_resp = client.post(
                f"/api/wishlists/{ok_id}/restore-deleted", headers=owner_headers
            )
            assert restore_resp.status_code == 200
            expired_resp = client.post(
                f"/api/wishlists/{exp_id}/restore-deleted", headers=owner_headers
            )
            assert expired_resp.status_code == 410

    restored_data = restore_resp.json()
    new_share_token = restored_data["share_token"]
    new_invite_token = restored_data["invite_token"]

    events = [
        (r.name, r.levelname, getattr(r, "event", None), r)
        for r in caplog.records
        if getattr(r, "event", None)
        in {
            "wishlist_deleted_listed",
            "wishlist_restored_from_deleted",
            "wishlist_restore_retention_expired",
        }
    ]
    assert ("wishenka.wishlists", "INFO", "wishlist_deleted_listed") in [e[:3] for e in events]
    assert ("wishenka.web.wishlists", "INFO", "wishlist_deleted_listed") in [e[:3] for e in events]
    assert ("wishenka.wishlists", "INFO", "wishlist_restored_from_deleted") in [
        e[:3] for e in events
    ]
    assert ("wishenka.web.wishlists", "INFO", "wishlist_restored_from_deleted") in [
        e[:3] for e in events
    ]
    assert ("wishenka.wishlists", "WARNING", "wishlist_restore_retention_expired") in [
        e[:3] for e in events
    ]

    for _, _, _, record in events:
        payload = json.loads(formatter.format(record))
        rendered = json.dumps(payload)
        assert "SecretBirthdayTitle" not in rendered
        assert "ExpiredSecretTitle" not in rendered
        assert new_share_token not in rendered
        assert new_invite_token not in rendered
        for val in payload.get("extra", {}).values():
            assert isinstance(val, (str, int, float, bool)) or val is None
