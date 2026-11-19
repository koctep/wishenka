"""Red failing-repro tests for client idempotency keys on booking mutations (WISHENKA-61).

Covers duplicate create, public-link create, purchase, and receipt replay without
double-decrement, payload mismatch 409, invalid header 400, cross-actor isolation,
and Surprise Invariant enforcement on replay.
"""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Iterator
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

_OWNER_ID = 101
_GIFTER_ID = 202
_OTHER_GIFTER_ID = 303
_SQLITE_PREFIX = "sqlite+aiosqlite:///"


def _make_user(telegram_id: int, first_name: str) -> AuthenticatedUser:
    """Create a test user identified by a Telegram id."""
    return AuthenticatedUser(
        telegram_id=telegram_id,
        first_name=first_name,
        auth_method="session_token",
    )


def _auth_header(
    sessions: SessionTokenService,
    user_id: int,
    name: str = "User",
    *,
    idempotency_key: str | None = None,
) -> dict[str, str]:
    """Build bearer Authorization headers with an optional Idempotency-Key."""
    token = sessions.create_token(user_id, name)
    headers = {"Authorization": f"Bearer {token}"}
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    return headers


def _db_path(app: FastAPI) -> str:
    """Return the SQLite file path from app settings."""
    return str(app.state.settings.database_url).removeprefix(_SQLITE_PREFIX)


def _row_count(app: FastAPI, table: str) -> int:
    """Count rows in a SQLite table."""
    with sqlite3.connect(_db_path(app)) as conn:
        row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    assert row is not None
    return int(row[0])


def _seed_wishlist_and_item(
    app: FastAPI,
    *,
    quantity: int = 2,
) -> tuple[int, int, str]:
    """Seed an active wishlist and wish item via the app's domain service."""
    service: WishlistService = app.state.domain_service
    owner = _make_user(_OWNER_ID, "Owner")

    async def _run() -> tuple[int, int, str]:
        wishlist = await service.create_wishlist(owner=owner, title="Birthday")
        item = await service.add_wish_item(
            wishlist_id=wishlist.id,
            actor=owner,
            title="Board Game",
            quantity=quantity,
        )
        return wishlist.id, item.id, wishlist.public_token

    return asyncio.run(_run())


@pytest.fixture
def test_app(tmp_path: Path) -> Iterator[tuple[TestClient, SessionTokenService, FastAPI]]:
    """Create an isolated FastAPI TestClient backed by a temporary SQLite database."""
    settings = Settings(
        database_url=f"{_SQLITE_PREFIX}{tmp_path / 'idempotency_repro.db'}",
        secret_key="idempotency-repro-test-secret",
    )
    app = create_app(settings)
    sessions = SessionTokenService(settings.secret_key)
    with TestClient(app) as client:
        yield client, sessions, app


def test_create_reservation_idempotent_replay(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """Duplicate POST .../reservations replays without double-decrement."""
    client, sessions, app = test_app
    wishlist_id, item_id, _ = _seed_wishlist_and_item(app, quantity=2)
    url = f"/api/wishlists/{wishlist_id}/items/{item_id}/reservations"
    headers = _auth_header(sessions, _GIFTER_ID, "Gifter", idempotency_key="create-res-1")

    first = client.post(url, json={"quantity": 1}, headers=headers)
    second = client.post(url, json={"quantity": 1}, headers=headers)

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    first_body = first.json()
    second_body = second.json()
    assert second_body["reservation_id"] == first_body["reservation_id"]
    assert first_body["available_quantity"] == 1
    assert second_body["available_quantity"] == 1
    assert _row_count(app, "wl_reservations") == 1


def test_public_link_reservation_idempotent_replay(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """Duplicate POST /api/public/.../reservations with the same Idempotency-Key replays safely."""
    client, sessions, app = test_app
    _, item_id, public_token = _seed_wishlist_and_item(app, quantity=2)
    url = f"/api/public/wishlists/{public_token}/items/{item_id}/reservations"
    headers = _auth_header(sessions, _GIFTER_ID, "Gifter", idempotency_key="public-res-1")

    first = client.post(url, json={"quantity": 1}, headers=headers)
    second = client.post(url, json={"quantity": 1}, headers=headers)

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    first_body = first.json()
    second_body = second.json()
    assert second_body["reservation_id"] == first_body["reservation_id"]
    assert second_body["available_quantity"] == 1
    assert _row_count(app, "wl_reservations") == 1


def test_purchase_reservation_idempotent_replay(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """Duplicate POST .../purchase replays 200 instead of conflicting."""
    client, sessions, app = test_app
    wishlist_id, item_id, _ = _seed_wishlist_and_item(app, quantity=2)
    create_resp = client.post(
        f"/api/wishlists/{wishlist_id}/items/{item_id}/reservations",
        json={"quantity": 1},
        headers=_auth_header(sessions, _GIFTER_ID, "Gifter"),
    )
    assert create_resp.status_code == 201, create_resp.text
    reservation_id = create_resp.json()["reservation_id"]

    purchase_url = (
        f"/api/wishlists/{wishlist_id}/items/{item_id}/reservations/{reservation_id}/purchase"
    )
    headers = _auth_header(sessions, _GIFTER_ID, "Gifter", idempotency_key="purchase-res-1")

    first = client.post(purchase_url, headers=headers)
    second = client.post(purchase_url, headers=headers)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert second.json() == first.json()
    assert second.json()["status"] == "purchased"


def test_receipt_idempotent_replay(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """Duplicate POST .../receipts replays without double-recording."""
    client, sessions, app = test_app
    wishlist_id, item_id, _ = _seed_wishlist_and_item(app, quantity=2)
    url = f"/api/wishlists/{wishlist_id}/items/{item_id}/receipts"
    headers = _auth_header(sessions, _OWNER_ID, "Owner", idempotency_key="receipt-1")

    first = client.post(url, json={"quantity": 1}, headers=headers)
    second = client.post(url, json={"quantity": 1}, headers=headers)

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["received_quantity"] == 1
    assert second.json()["received_quantity"] == 1
    assert second.json()["remaining_quantity"] == 1
    assert _row_count(app, "wl_receipts") == 1


def test_idempotency_payload_mismatch_returns_409(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """Reusing an Idempotency-Key with a different payload must be rejected with 409 Conflict."""
    client, sessions, app = test_app
    wishlist_id, item_id, _ = _seed_wishlist_and_item(app, quantity=3)
    url = f"/api/wishlists/{wishlist_id}/items/{item_id}/reservations"
    headers = _auth_header(sessions, _GIFTER_ID, "Gifter", idempotency_key="mismatch-key-1")

    first = client.post(url, json={"quantity": 1}, headers=headers)
    assert first.status_code == 201, first.text

    second = client.post(url, json={"quantity": 2}, headers=headers)
    assert second.status_code == 409, second.text
    assert _row_count(app, "wl_reservations") == 1


@pytest.mark.parametrize("bad_key", ["", "   ", "invalid key with spaces", "k" * 129])
def test_invalid_idempotency_key_header_returns_400(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
    bad_key: str,
) -> None:
    """Malformed or empty Idempotency-Key headers must fail with 400 before mutating state."""
    client, sessions, app = test_app
    wishlist_id, item_id, _ = _seed_wishlist_and_item(app, quantity=2)
    url = f"/api/wishlists/{wishlist_id}/items/{item_id}/reservations"
    headers = _auth_header(sessions, _GIFTER_ID, "Gifter", idempotency_key=bad_key)

    resp = client.post(url, json={"quantity": 1}, headers=headers)

    assert resp.status_code == 400, resp.text
    assert _row_count(app, "wl_reservations") == 0


def test_cross_actor_idempotency_key_isolation(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """Different actors sending the same Idempotency-Key never share records."""
    client, sessions, app = test_app
    wishlist_id, item_id, _ = _seed_wishlist_and_item(app, quantity=2)
    url = f"/api/wishlists/{wishlist_id}/items/{item_id}/reservations"

    gifter_a_headers = _auth_header(sessions, _GIFTER_ID, "GifterA", idempotency_key="shared-key")
    gifter_b_headers = _auth_header(
        sessions, _OTHER_GIFTER_ID, "GifterB", idempotency_key="shared-key"
    )

    resp_a = client.post(url, json={"quantity": 1}, headers=gifter_a_headers)
    resp_b = client.post(url, json={"quantity": 1}, headers=gifter_b_headers)
    replay_a = client.post(url, json={"quantity": 1}, headers=gifter_a_headers)

    assert resp_a.status_code == 201, resp_a.text
    assert resp_b.status_code == 201, resp_b.text
    assert replay_a.status_code == 201, replay_a.text
    assert resp_a.json()["reservation_id"] != resp_b.json()["reservation_id"]
    assert replay_a.json()["reservation_id"] == resp_a.json()["reservation_id"]
    assert _row_count(app, "wl_reservations") == 2


def test_surprise_invariant_blocks_replay_when_actor_becomes_recipient(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """Replaying a reservation key after the actor becomes the wish recipient must return 403."""
    client, sessions, app = test_app
    wishlist_id, item_id, _ = _seed_wishlist_and_item(app, quantity=2)
    service: WishlistService = app.state.domain_service
    owner = _make_user(_OWNER_ID, "Owner")
    from wishenka.auth.models import TelegramUser

    asyncio.run(app.state.user_store.upsert_user(TelegramUser(id=_GIFTER_ID, first_name="Gifter")))
    asyncio.run(
        service.add_member(
            wishlist_id=wishlist_id,
            actor=owner,
            user_id=_GIFTER_ID,
            role=WishlistRole.MEMBER,
        )
    )

    url = f"/api/wishlists/{wishlist_id}/items/{item_id}/reservations"
    headers = _auth_header(sessions, _GIFTER_ID, "Gifter", idempotency_key="surprise-key-1")
    first = client.post(url, json={"quantity": 1}, headers=headers)
    assert first.status_code == 201, first.text

    asyncio.run(
        service.update_wish_item(
            item_id=item_id,
            actor=owner,
            recipient_user_id=_GIFTER_ID,
        )
    )

    replay = client.post(url, json={"quantity": 1}, headers=headers)
    assert replay.status_code == 403, replay.text
    assert "reservation_id" not in replay.text
