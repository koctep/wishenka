"""Extended unit, integration, migration, and concurrency tests for WISHENKA-61."""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.test_booking_idempotency import (
    _GIFTER_ID,
    _OWNER_ID,
    _SQLITE_PREFIX,
    _auth_header,
    _make_user,
    _row_count,
    _seed_wishlist_and_item,
)
from wishenka.auth.session import SessionTokenService
from wishenka.config import Settings
from wishenka.web.app import create_app
from wishenka.web.idempotency import compute_request_hash
from wishenka.wishlists.cleanup import run_cleanup_cycle
from wishenka.wishlists.service import WishlistService
from wishenka.wishlists.store import WishlistStore

pytestmark = pytest.mark.timeout(20)


@pytest.fixture
def isolated_app(tmp_path: Path) -> Iterator[tuple[TestClient, SessionTokenService, FastAPI]]:
    """Create an isolated FastAPI TestClient backed by a temporary SQLite database."""
    settings = Settings(
        database_url=f"{_SQLITE_PREFIX}{tmp_path / 'idempotency_ext.db'}",
        secret_key="idempotency-ext-test-secret",
    )
    app = create_app(settings)
    sessions = SessionTokenService(settings.secret_key)
    with TestClient(app) as client:
        yield client, sessions, app


def test_update_cancel_and_undo_purchase_idempotent_replay(
    isolated_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """PATCH quantity, POST cancel, and POST undo-purchase all replay safely."""
    client, sessions, app = isolated_app
    wishlist_id, item_id, _ = _seed_wishlist_and_item(app, quantity=3)

    create_resp = client.post(
        f"/api/wishlists/{wishlist_id}/items/{item_id}/reservations",
        json={"quantity": 1},
        headers=_auth_header(sessions, _GIFTER_ID, "Gifter"),
    )
    assert create_resp.status_code == 201
    res_id = create_resp.json()["reservation_id"]
    base_url = f"/api/wishlists/{wishlist_id}/items/{item_id}/reservations/{res_id}"

    # 1. PATCH quantity replay
    patch_headers = _auth_header(
        sessions,
        _GIFTER_ID,
        "Gifter",
        idempotency_key="patch-qty-1",
    )
    p1 = client.patch(base_url, json={"quantity": 2}, headers=patch_headers)
    p2 = client.patch(base_url, json={"quantity": 2}, headers=patch_headers)
    assert p1.status_code == 200 and p2.status_code == 200
    assert p1.json() == p2.json()
    assert p2.json()["quantity"] == 2

    # 2. Purchase then undo-purchase replay
    assert (
        client.post(
            f"{base_url}/purchase",
            headers=_auth_header(sessions, _GIFTER_ID, "Gifter"),
        ).status_code
        == 200
    )
    undo_headers = _auth_header(
        sessions,
        _GIFTER_ID,
        "Gifter",
        idempotency_key="undo-1",
    )
    u1 = client.post(f"{base_url}/undo-purchase", headers=undo_headers)
    u2 = client.post(f"{base_url}/undo-purchase", headers=undo_headers)
    assert u1.status_code == 200 and u2.status_code == 200
    assert u1.json() == u2.json()
    assert u2.json()["status"] == "active"

    # 3. Cancel replay
    cancel_headers = _auth_header(
        sessions,
        _GIFTER_ID,
        "Gifter",
        idempotency_key="cancel-1",
    )
    c1 = client.post(f"{base_url}/cancel", headers=cancel_headers)
    c2 = client.post(f"{base_url}/cancel", headers=cancel_headers)
    assert c1.status_code == 200 and c2.status_code == 200
    assert c1.json() == c2.json()
    assert c2.json()["status"] == "cancelled"


def test_receipt_ui_htmx_idempotent_replay(
    isolated_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """Duplicate POST /web/.../receipt with the same Idempotency-Key replays HTML once."""
    client, sessions, app = isolated_app
    wishlist_id, item_id, _ = _seed_wishlist_and_item(app, quantity=2)
    url = f"/web/wishlists/{wishlist_id}/items/{item_id}/receipt"
    headers = _auth_header(
        sessions,
        _OWNER_ID,
        "Owner",
        idempotency_key="ui-receipt-1",
    )

    first = client.post(url, data={"quantity": "1"}, headers=headers)
    second = client.post(url, data={"quantity": "1"}, headers=headers)

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert "text/html" in second.headers["content-type"]
    assert second.text == first.text
    assert _row_count(app, "wl_receipts") == 1


def test_cross_operation_key_reuse_returns_409(
    isolated_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """Reusing an Idempotency-Key from create_reservation on purchase returns 409."""
    client, sessions, app = isolated_app
    wishlist_id, item_id, _ = _seed_wishlist_and_item(app, quantity=2)
    headers = _auth_header(
        sessions,
        _GIFTER_ID,
        "Gifter",
        idempotency_key="cross-op-1",
    )

    created = client.post(
        f"/api/wishlists/{wishlist_id}/items/{item_id}/reservations",
        json={"quantity": 1},
        headers=headers,
    )
    assert created.status_code == 201
    res_id = created.json()["reservation_id"]

    reused = client.post(
        f"/api/wishlists/{wishlist_id}/items/{item_id}/reservations/{res_id}/purchase",
        headers=headers,
    )
    assert reused.status_code == 409, reused.text


def test_failed_domain_refusal_does_not_block_retry(
    isolated_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """A 409 domain refusal must not persist an idempotency record that blocks later retries."""
    client, sessions, app = isolated_app
    wishlist_id, item_id, _ = _seed_wishlist_and_item(app, quantity=1)
    url = f"/api/wishlists/{wishlist_id}/items/{item_id}/reservations"
    headers = _auth_header(
        sessions,
        _GIFTER_ID,
        "Gifter",
        idempotency_key="retry-after-409",
    )

    # Requesting 2 units when only 1 is available -> 409
    first = client.post(url, json={"quantity": 2}, headers=headers)
    assert first.status_code == 409

    # Owner increases quantity to 2, retry with same key & payload now succeeds
    service: WishlistService = app.state.domain_service
    asyncio.run(
        service.update_wish_item(item_id=item_id, actor=_make_user(_OWNER_ID, "Owner"), quantity=2)
    )

    second = client.post(url, json={"quantity": 2}, headers=headers)
    assert second.status_code == 201, second.text
    assert _row_count(app, "wl_reservations") == 1


def test_cleanup_cycle_purges_expired_idempotency_records(tmp_path: Path) -> None:
    """run_cleanup_cycle deletes expired idempotency records and keeps active ones."""
    db_file = tmp_path / "cleanup_idem.db"
    store = WishlistStore(f"{_SQLITE_PREFIX}{db_file}")
    settings = Settings(database_url=f"{_SQLITE_PREFIX}{db_file}", idempotency_retention_hours=24)

    async def _run() -> None:
        await store.initialize()
        owner = _make_user(_OWNER_ID, "Owner")
        wl = await WishlistService(store).create_wishlist(owner=owner, title="List")
        item = await WishlistService(store).add_wish_item(
            wishlist_id=wl.id, actor=owner, title="Item", quantity=5
        )
        t0 = datetime(2026, 11, 17, 12, 0, tzinfo=UTC)

        async def _reserve_one(svc: WishlistService) -> tuple[int, str, str]:
            await svc.create_reservation(item.id, _make_user(_GIFTER_ID, "G"), 1, wishlist_id=wl.id)
            return 201, "application/json", '{"ok":true}'

        await store.execute_wish_idempotent(
            _reserve_one,
            actor_id=_GIFTER_ID,
            idempotency_key="old-key",
            request_hash=compute_request_hash("op", {"item_id": item.id}),
            retention_hours=24,
            item_id=item.id,
            now=t0,
        )
        await store.execute_wish_idempotent(
            _reserve_one,
            actor_id=_GIFTER_ID,
            idempotency_key="fresh-key",
            request_hash=compute_request_hash("op", {"item_id": item.id}),
            retention_hours=24,
            item_id=item.id,
            now=t0 + timedelta(hours=20),
        )

        stats = await run_cleanup_cycle(store, settings, now=t0 + timedelta(hours=25))
        assert stats.idempotency_records_cleaned == 1

    asyncio.run(_run())

    with sqlite3.connect(str(db_file)) as conn:
        rows = conn.execute("SELECT idempotency_key FROM wl_idempotency_records").fetchall()
        keys = [r[0] for r in rows]
    assert keys == ["fresh-key"]


def test_concurrent_duplicate_idempotent_requests_execute_once(tmp_path: Path) -> None:
    """Concurrent callers with the same Idempotency-Key serialize and mutate at most once."""
    db_file = tmp_path / "concurrent_idem.db"
    store = WishlistStore(f"{_SQLITE_PREFIX}{db_file}")

    async def _run() -> None:
        await store.initialize()
        owner = _make_user(_OWNER_ID, "Owner")
        wl = await WishlistService(store).create_wishlist(owner=owner, title="List")
        item = await WishlistService(store).add_wish_item(
            wishlist_id=wl.id, actor=owner, title="Item", quantity=2
        )
        req_hash = compute_request_hash("create_reservation", {"item_id": item.id}, {"quantity": 1})

        async def _op(svc: WishlistService) -> tuple[int, str, str]:
            res = await svc.create_reservation(
                item.id, _make_user(_GIFTER_ID, "G"), 1, wishlist_id=wl.id
            )
            return 201, "application/json", f'{{"reservation_id":{res.id}}}'

        r1, r2 = await asyncio.gather(
            store.execute_wish_idempotent(
                _op,
                actor_id=_GIFTER_ID,
                idempotency_key="concurrent-k1",
                request_hash=req_hash,
                item_id=item.id,
            ),
            store.execute_wish_idempotent(
                _op,
                actor_id=_GIFTER_ID,
                idempotency_key="concurrent-k1",
                request_hash=req_hash,
                item_id=item.id,
            ),
        )
        assert r1.body == r2.body
        assert sorted([r1.replayed, r2.replayed]) == [False, True]

    asyncio.run(_run())

    with sqlite3.connect(str(db_file)) as conn:
        count = conn.execute("SELECT COUNT(*) FROM wl_reservations").fetchone()
    assert count is not None and count[0] == 1


def test_alembic_migration_upgrade_and_downgrade(tmp_path: Path) -> None:
    """Alembic add_idempotency_records cleanly creates and drops wl_idempotency_records."""
    db_file = tmp_path / "alembic_idem.db"
    cfg = Config()
    cfg.set_main_option("script_location", "wishenka/wishlists/alembic")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_file}")

    command.upgrade(cfg, "add_idempotency_records")
    with sqlite3.connect(str(db_file)) as conn:
        tables = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        indexes = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
        }
    assert "wl_idempotency_records" in tables
    assert "idx_wl_idempotency_expires_at" in indexes

    command.downgrade(cfg, "add_support_channel")
    with sqlite3.connect(str(db_file)) as conn:
        tables_after = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
    assert "wl_idempotency_records" not in tables_after
