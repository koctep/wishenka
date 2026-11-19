"""Client promise routes for WISHENKA-18.

Create, quantity change, cancel, purchase, and undo use the existing
reservation methods. Recipient answers stay silent. Archive and delete keep
the rules already in force.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from wishenka.auth.models import AuthenticatedUser, TelegramUser
from wishenka.auth.session import SessionTokenService
from wishenka.config import Settings
from wishenka.web.app import create_app
from wishenka.wishlists.exceptions import InventoryBusyError, PermissionDeniedError
from wishenka.wishlists.service import WishlistService

pytestmark = pytest.mark.timeout(30)

_RECIPIENT_ID = 101
_GIFTER_ID = 202
_OTHER_GIFTER_ID = 303
_SQLITE_PREFIX = "sqlite+aiosqlite:///"
_BOOKING_KEYS = (
    "available_quantity",
    "is_fully_reserved",
    "is_reserved_by_me",
    "my_reserved_quantity",
    "my_reservation_status",
    "my_reservation_id",
)
_PROMISE_KEYS = {
    "reservation_id",
    "wish_item_id",
    "quantity",
    "status",
    "available_quantity",
    "item",
}
_ROUTE_LOGGER = "wishenka.web.reservations"
_IDENTITY_FIELDS = (
    "gifter_id",
    "user_id",
    "actor_id",
    "telegram_id",
    "first_name",
    "recipient_user_id",
    "token",
)
_LOG_RECORD_FIELDS = set(logging.makeLogRecord({"msg": "x"}).__dict__) | {
    "message",
    "asctime",
}


def make_user(telegram_id: int, first_name: str) -> AuthenticatedUser:
    """Create a test user identified by a Telegram id."""
    return AuthenticatedUser(
        telegram_id=telegram_id,
        first_name=first_name,
        auth_method="session_token",
    )


def auth_header(sessions: SessionTokenService, user_id: int, name: str) -> dict[str, str]:
    """Build a bearer Authorization header for a session token."""
    token = sessions.create_token(user_id, name)
    return {"Authorization": f"Bearer {token}"}


def reservations_url(wishlist_id: int, item_id: int) -> str:
    """Return the promise-action prefix for one wish."""
    return f"/api/wishlists/{wishlist_id}/items/{item_id}/reservations"


def reservation_count(app: FastAPI) -> int:
    """Count promise rows in the app's temporary SQLite file."""
    database_url = str(app.state.settings.database_url)
    db_path = database_url.removeprefix(_SQLITE_PREFIX)
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) FROM wl_reservations").fetchone()
    assert row is not None
    return int(row[0])


@pytest.fixture
def test_app(tmp_path: Path) -> Iterator[tuple[TestClient, SessionTokenService, FastAPI]]:
    """Open create_app on a temporary SQLite file with bearer sessions."""
    settings = Settings(
        database_url=f"{_SQLITE_PREFIX}{tmp_path / 'reservation_actions.db'}",
        secret_key="reservation-actions-test-secret",
    )
    app = create_app(settings)
    sessions = SessionTokenService(settings.secret_key)
    with TestClient(app) as client:
        yield client, sessions, app


def reservation_fields(app: FastAPI, reservation_id: int) -> tuple[int, str, int]:
    """Return quantity, status, and gifter id for one stored promise."""
    database_url = str(app.state.settings.database_url)
    db_path = database_url.removeprefix(_SQLITE_PREFIX)
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT quantity, status, user_id FROM wl_reservations WHERE id = ?",
            (reservation_id,),
        ).fetchone()
    assert row is not None
    return int(row[0]), str(row[1]), int(row[2])


def open_active_wish(
    client: TestClient,
    sessions: SessionTokenService,
    *,
    quantity: int = 2,
) -> tuple[int, int, dict[str, str], dict[str, str]]:
    """Create a personal list and one active wish. The owner is the recipient."""
    recipient_headers = auth_header(sessions, _RECIPIENT_ID, "Alice")
    gifter_headers = auth_header(sessions, _GIFTER_ID, "Bob")
    created = client.post(
        "/api/wishlists",
        json={"name": "Alice Birthday"},
        headers=recipient_headers,
    )
    assert created.status_code == 201, created.text
    wishlist_id = int(created.json()["id"])
    item = client.post(
        f"/api/wishlists/{wishlist_id}/items",
        json={"title": "Headphones", "quantity": quantity},
        headers=recipient_headers,
    )
    assert item.status_code == 201, item.text
    return wishlist_id, int(item.json()["id"]), recipient_headers, gifter_headers


def create_promise(
    client: TestClient,
    wishlist_id: int,
    item_id: int,
    headers: dict[str, str],
    quantity: int = 1,
) -> dict[str, Any]:
    """Create a promise and return the action body."""
    response = client.post(
        reservations_url(wishlist_id, item_id),
        json={"quantity": quantity},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert isinstance(body, dict)
    return body


def route_events(caplog: pytest.LogCaptureFixture, event: str) -> list[logging.LogRecord]:
    """Return promise-route records for one structured event."""
    return [
        record
        for record in caplog.records
        if record.name == _ROUTE_LOGGER and getattr(record, "event", None) == event
    ]


def route_extra(record: logging.LogRecord) -> dict[str, object]:
    """Structured fields added to one promise-route record."""
    return {key: value for key, value in record.__dict__.items() if key not in _LOG_RECORD_FIELDS}


def assert_route_record_hides_identity(record: logging.LogRecord, *secrets: str) -> None:
    """The HTTP promise log has no gifter id, name, token, or wish graph."""
    for field in _IDENTITY_FIELDS:
        assert field not in record.__dict__
    assert "item" not in record.__dict__
    extras = route_extra(record)
    rendered = f"{record.getMessage()} {extras}"
    for secret in secrets:
        assert secret not in rendered
    for identity in (_RECIPIENT_ID, _GIFTER_ID, _OTHER_GIFTER_ID):
        assert identity not in extras.values()
        assert str(identity) not in record.getMessage()


def assert_no_reservation_list(payload: Any) -> None:
    """Collection answers do not carry a reservation list."""
    if isinstance(payload, dict):
        assert "reservations" not in payload
        for value in payload.values():
            assert_no_reservation_list(value)
    elif isinstance(payload, list):
        for value in payload:
            assert_no_reservation_list(value)


def test_unauthenticated_create_is_rejected(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """A create with no Authorization header is 401 and stores no promise."""
    client, sessions, app = test_app
    wishlist_id, item_id, _, _ = open_active_wish(client, sessions)

    response = client.post(reservations_url(wishlist_id, item_id), json={"quantity": 1})

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}
    assert reservation_count(app) == 0


def test_gifter_create_returns_the_new_promise(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """An identified gifter who is not the recipient receives the new promise."""
    client, sessions, _app = test_app
    wishlist_id, item_id, _, gifter_headers = open_active_wish(client, sessions)

    response = client.post(
        reservations_url(wishlist_id, item_id),
        json={"quantity": 1},
        headers=gifter_headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert isinstance(body["reservation_id"], int)
    assert body["wish_item_id"] == item_id
    assert body["quantity"] == 1
    assert body["status"] == "active"
    assert body["available_quantity"] == 1
    assert "user_id" not in body


def test_recipient_cancel_does_not_reveal_the_promise(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """A recipient mutation of a real promise is only 'Resource not found'."""
    client, sessions, app = test_app
    wishlist_id, item_id, recipient_headers, _ = open_active_wish(client, sessions)
    service: WishlistService = app.state.domain_service
    reservation = asyncio.run(
        service.create_reservation(
            item_id=item_id,
            user=make_user(_GIFTER_ID, "Bob"),
            quantity=1,
        )
    )
    assert reservation.id > 0
    assert reservation_count(app) == 1

    response = client.post(
        f"{reservations_url(wishlist_id, item_id)}/{reservation.id}/cancel",
        headers=recipient_headers,
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Resource not found"}


def test_non_positive_quantity_is_rejected(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """Quantity below 1 is a validation refusal and does not allocate a promise."""
    client, sessions, app = test_app
    wishlist_id, item_id, recipient_headers, gifter_headers = open_active_wish(client, sessions)
    url = reservations_url(wishlist_id, item_id)

    for headers in (recipient_headers, gifter_headers):
        for quantity in (0, -1):
            response = client.post(url, json={"quantity": quantity}, headers=headers)
            assert response.status_code == 400
            assert response.json() == {"detail": "Reservation quantity must be at least 1"}
    assert reservation_count(app) == 0

    created = create_promise(client, wishlist_id, item_id, gifter_headers, quantity=1)
    reservation_id = int(created["reservation_id"])
    for quantity in (0, -2):
        response = client.patch(
            f"{url}/{reservation_id}",
            json={"quantity": quantity},
            headers=gifter_headers,
        )
        assert response.status_code == 400
        assert response.json() == {"detail": "Reservation quantity must be at least 1"}
        assert reservation_fields(app, reservation_id) == (1, "active", _GIFTER_ID)


def test_unauthenticated_mutation_is_rejected(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """A missing session is 401 on every mutation and leaves the promise unchanged."""
    client, sessions, app = test_app
    wishlist_id, item_id, _, gifter_headers = open_active_wish(client, sessions)
    created = create_promise(client, wishlist_id, item_id, gifter_headers)
    reservation_id = int(created["reservation_id"])
    prefix = f"{reservations_url(wishlist_id, item_id)}/{reservation_id}"

    responses = [
        client.patch(prefix, json={"quantity": 2}),
        client.post(f"{prefix}/cancel"),
        client.post(f"{prefix}/purchase"),
        client.post(f"{prefix}/undo-purchase"),
    ]
    for response in responses:
        assert response.status_code == 401
        assert response.json() == {"detail": "Authentication required"}
    assert reservation_fields(app, reservation_id) == (1, "active", _GIFTER_ID)


def test_ownerless_create_does_not_store_user_zero(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """A missing user raises before a promise id is stored."""
    client, sessions, app = test_app
    _wishlist_id, item_id, _, gifter_headers = open_active_wish(client, sessions)
    service: WishlistService = app.state.domain_service

    with pytest.raises(PermissionDeniedError):
        asyncio.run(service.create_reservation(item_id=item_id, user=None, quantity=1))

    assert reservation_count(app) == 0
    created = create_promise(client, _wishlist_id, item_id, gifter_headers)
    _quantity, _status, user_id = reservation_fields(app, int(created["reservation_id"]))
    assert user_id == _GIFTER_ID


def test_second_promise_is_not_merged(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """An action returns the changed row. The wish view keeps the combined quantity."""
    client, sessions, app = test_app
    wishlist_id, item_id, _, gifter_headers = open_active_wish(client, sessions, quantity=4)
    older = create_promise(client, wishlist_id, item_id, gifter_headers, quantity=2)
    newer = create_promise(client, wishlist_id, item_id, gifter_headers, quantity=1)
    older_id = int(older["reservation_id"])
    newer_id = int(newer["reservation_id"])
    assert older_id != newer_id
    assert reservation_count(app) == 2

    purchased = client.post(
        f"{reservations_url(wishlist_id, item_id)}/{newer_id}/purchase",
        headers=gifter_headers,
    )
    assert purchased.status_code == 200
    assert purchased.json()["reservation_id"] == newer_id
    assert purchased.json()["status"] == "purchased"
    assert purchased.json()["quantity"] == 1

    lowered = client.patch(
        f"{reservations_url(wishlist_id, item_id)}/{older_id}",
        json={"quantity": 1},
        headers=gifter_headers,
    )
    assert lowered.status_code == 200
    body = lowered.json()
    assert set(body) == _PROMISE_KEYS
    assert body["reservation_id"] == older_id
    assert body["quantity"] == 1
    assert body["status"] == "active"
    assert body["available_quantity"] == 2
    assert "user_id" not in body
    assert body["item"]["my_reserved_quantity"] == 2
    assert body["item"]["my_reservation_id"] == newer_id
    assert body["item"]["my_reservation_status"] == "purchased"
    assert reservation_fields(app, older_id) == (1, "active", _GIFTER_ID)
    assert reservation_fields(app, newer_id) == (1, "purchased", _GIFTER_ID)

    wish = client.get(f"/api/wishlists/{wishlist_id}/items/{item_id}", headers=gifter_headers)
    assert wish.status_code == 200
    view = wish.json()
    assert view["my_reserved_quantity"] == 2
    assert view["my_reservation_id"] == newer_id
    assert view["my_reservation_status"] == "purchased"


def test_holder_can_resize_purchase_undo_and_cancel(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """The holder changes one promise. Lowering a purchase keeps the purchase mark."""
    client, sessions, app = test_app
    wishlist_id, item_id, _, gifter_headers = open_active_wish(client, sessions, quantity=4)
    created = create_promise(client, wishlist_id, item_id, gifter_headers, quantity=3)
    reservation_id = int(created["reservation_id"])
    prefix = f"{reservations_url(wishlist_id, item_id)}/{reservation_id}"
    assert created["available_quantity"] == 1
    assert "user_id" not in created["item"]

    resized = client.patch(prefix, json={"quantity": 2}, headers=gifter_headers)
    assert resized.status_code == 200
    assert resized.json()["quantity"] == 2
    assert resized.json()["status"] == "active"
    assert resized.json()["available_quantity"] == 2

    purchased = client.post(f"{prefix}/purchase", headers=gifter_headers)
    assert purchased.status_code == 200
    assert purchased.json()["status"] == "purchased"
    assert purchased.json()["quantity"] == 2
    assert purchased.json()["available_quantity"] == 2

    lowered = client.patch(prefix, json={"quantity": 1}, headers=gifter_headers)
    assert lowered.status_code == 200
    assert lowered.json()["status"] == "purchased"
    assert lowered.json()["quantity"] == 1
    assert lowered.json()["available_quantity"] == 3

    undone = client.post(f"{prefix}/undo-purchase", headers=gifter_headers)
    assert undone.status_code == 200
    assert undone.json()["status"] == "active"
    assert undone.json()["quantity"] == 1
    assert undone.json()["reservation_id"] == reservation_id

    cancelled = client.post(f"{prefix}/cancel", headers=gifter_headers)
    assert cancelled.status_code == 200
    cancelled_body = cancelled.json()
    assert cancelled_body["status"] == "cancelled"
    assert cancelled_body["reservation_id"] == reservation_id
    assert cancelled_body["available_quantity"] == 4
    assert cancelled_body["item"]["my_reserved_quantity"] == 0
    assert cancelled_body["item"]["my_reservation_id"] is None
    assert reservation_fields(app, reservation_id) == (1, "cancelled", _GIFTER_ID)


def test_non_holder_receives_forbidden(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """Another gifter is refused without the holder's name or id."""
    client, sessions, app = test_app
    wishlist_id, item_id, _, gifter_headers = open_active_wish(client, sessions)
    created = create_promise(client, wishlist_id, item_id, gifter_headers)
    reservation_id = int(created["reservation_id"])
    prefix = f"{reservations_url(wishlist_id, item_id)}/{reservation_id}"
    other_headers = auth_header(sessions, _OTHER_GIFTER_ID, "Cara")

    responses = [
        client.patch(prefix, json={"quantity": 2}, headers=other_headers),
        client.post(f"{prefix}/purchase", headers=other_headers),
        client.post(f"{prefix}/undo-purchase", headers=other_headers),
        client.post(f"{prefix}/cancel", headers=other_headers),
    ]
    for response in responses:
        assert response.status_code == 403
        assert response.json() == {"detail": "Forbidden"}
        assert "Bob" not in response.text
        assert str(_GIFTER_ID) not in response.text
    assert reservation_fields(app, reservation_id) == (1, "active", _GIFTER_ID)


def test_shortage_names_the_free_remainder(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """A shortage states the free remainder and does not name the holder."""
    client, sessions, app = test_app
    wishlist_id, item_id, _, gifter_headers = open_active_wish(client, sessions, quantity=1)
    created = create_promise(client, wishlist_id, item_id, gifter_headers, quantity=1)
    reservation_id = int(created["reservation_id"])
    other_headers = auth_header(sessions, _OTHER_GIFTER_ID, "Cara")

    response = client.post(
        reservations_url(wishlist_id, item_id),
        json={"quantity": 1},
        headers=other_headers,
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Cannot reserve 1 units, available: 0"
    assert "Bob" not in response.text
    assert str(_GIFTER_ID) not in response.text
    assert reservation_count(app) == 1
    assert reservation_fields(app, reservation_id) == (1, "active", _GIFTER_ID)


def test_mismatched_path_does_not_change_the_promise(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """A promise id on the wrong wish or list is the same not-found body."""
    client, sessions, app = test_app
    wishlist_id, item_id, _, gifter_headers = open_active_wish(client, sessions)
    created = create_promise(client, wishlist_id, item_id, gifter_headers)
    reservation_id = int(created["reservation_id"])

    wrong_item = client.post(
        f"{reservations_url(wishlist_id, item_id + 1)}/{reservation_id}/cancel",
        headers=gifter_headers,
    )
    wrong_list = client.post(
        f"{reservations_url(wishlist_id + 1, item_id)}/{reservation_id}/cancel",
        headers=gifter_headers,
    )
    missing = client.post(
        f"{reservations_url(wishlist_id, item_id)}/999999/cancel",
        headers=gifter_headers,
    )

    for response in (wrong_item, wrong_list, missing):
        assert response.status_code == 404
        assert response.json() == {"detail": "Resource not found"}
    assert reservation_fields(app, reservation_id) == (1, "active", _GIFTER_ID)


def test_archived_list_refuses_every_action(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """An archived list refuses a new promise and every change to an existing one."""
    client, sessions, app = test_app
    wishlist_id, item_id, recipient_headers, gifter_headers = open_active_wish(client, sessions)
    created = create_promise(client, wishlist_id, item_id, gifter_headers)
    reservation_id = int(created["reservation_id"])
    archived = client.post(f"/api/wishlists/{wishlist_id}/archive", headers=recipient_headers)
    assert archived.status_code == 200
    prefix = f"{reservations_url(wishlist_id, item_id)}/{reservation_id}"

    responses = [
        client.post(
            reservations_url(wishlist_id, item_id),
            json={"quantity": 1},
            headers=gifter_headers,
        ),
        client.patch(prefix, json={"quantity": 2}, headers=gifter_headers),
        client.post(f"{prefix}/cancel", headers=gifter_headers),
        client.post(f"{prefix}/purchase", headers=gifter_headers),
        client.post(f"{prefix}/undo-purchase", headers=gifter_headers),
    ]
    for response in responses:
        assert response.status_code == 409
        assert "archived" in response.json()["detail"]
        assert "Bob" not in response.text
        assert str(_GIFTER_ID) not in response.text
    assert reservation_count(app) == 1
    assert reservation_fields(app, reservation_id) == (1, "active", _GIFTER_ID)


def test_deleted_list_refuses_every_action_and_keeps_the_cancellation(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """Deleting a list still cancels the promise. Later actions are not found."""
    client, sessions, app = test_app
    wishlist_id, item_id, _, gifter_headers = open_active_wish(client, sessions)
    created = create_promise(client, wishlist_id, item_id, gifter_headers)
    reservation_id = int(created["reservation_id"])
    service: WishlistService = app.state.domain_service

    asyncio.run(
        app.state.user_store.upsert_user(TelegramUser(id=_OTHER_GIFTER_ID, first_name="Cara"))
    )
    asyncio.run(
        app.state.user_store.upsert_user(
            TelegramUser(id=_OTHER_GIFTER_ID, first_name="Cara", language_code="ru")
        )
    )
    asyncio.run(
        service.delete_wishlist(wishlist_id=wishlist_id, actor=make_user(_RECIPIENT_ID, "Alice"))
    )
    assert reservation_fields(app, reservation_id) == (1, "cancelled", _GIFTER_ID)
    prefix = f"{reservations_url(wishlist_id, item_id)}/{reservation_id}"

    responses = [
        client.post(
            reservations_url(wishlist_id, item_id),
            json={"quantity": 1},
            headers=gifter_headers,
        ),
        client.patch(prefix, json={"quantity": 2}, headers=gifter_headers),
        client.post(f"{prefix}/cancel", headers=gifter_headers),
        client.post(f"{prefix}/purchase", headers=gifter_headers),
        client.post(f"{prefix}/undo-purchase", headers=gifter_headers),
    ]
    for response in responses:
        assert response.status_code == 404
        assert response.json() == {"detail": "Resource not found"}
    assert reservation_fields(app, reservation_id) == (1, "cancelled", _GIFTER_ID)


def test_archived_wish_refuses_only_a_new_promise(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """An archived wish on an active list blocks a new promise and still allows changes."""
    client, sessions, app = test_app
    wishlist_id, item_id, recipient_headers, gifter_headers = open_active_wish(
        client, sessions, quantity=3
    )
    created = create_promise(client, wishlist_id, item_id, gifter_headers, quantity=1)
    reservation_id = int(created["reservation_id"])
    archived = client.post(
        f"/api/wishlists/{wishlist_id}/items/{item_id}/archive",
        headers=recipient_headers,
    )
    assert archived.status_code == 200
    prefix = f"{reservations_url(wishlist_id, item_id)}/{reservation_id}"

    refused = client.post(
        reservations_url(wishlist_id, item_id),
        json={"quantity": 1},
        headers=gifter_headers,
    )
    assert refused.status_code == 409
    assert "archived" in refused.json()["detail"]
    assert reservation_count(app) == 1

    resized = client.patch(prefix, json={"quantity": 2}, headers=gifter_headers)
    assert resized.status_code == 200
    assert resized.json()["quantity"] == 2
    assert resized.json()["status"] == "active"
    purchased = client.post(f"{prefix}/purchase", headers=gifter_headers)
    assert purchased.status_code == 200
    assert purchased.json()["status"] == "purchased"
    undone = client.post(f"{prefix}/undo-purchase", headers=gifter_headers)
    assert undone.status_code == 200
    assert undone.json()["status"] == "active"
    cancelled = client.post(f"{prefix}/cancel", headers=gifter_headers)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["reservation_id"] == reservation_id
    assert reservation_fields(app, reservation_id) == (2, "cancelled", _GIFTER_ID)


def test_recipient_create_and_wish_reads_stay_silent(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """The recipient cannot promise a wish, and reads omit booking facts."""
    client, sessions, app = test_app
    wishlist_id, item_id, recipient_headers, gifter_headers = open_active_wish(
        client, sessions, quantity=2
    )

    empty = client.post(
        reservations_url(wishlist_id, item_id),
        json={"quantity": 1},
        headers=recipient_headers,
    )
    assert empty.status_code == 403
    assert empty.json() == {"detail": "Cannot promise this wish"}
    assert reservation_count(app) == 0

    create_promise(client, wishlist_id, item_id, gifter_headers, quantity=2)
    full = client.post(
        reservations_url(wishlist_id, item_id),
        json={"quantity": 1},
        headers=recipient_headers,
    )
    assert full.status_code == 403
    assert full.json() == {"detail": "Cannot promise this wish"}
    assert reservation_count(app) == 1

    recipient_item = client.get(
        f"/api/wishlists/{wishlist_id}/items/{item_id}",
        headers=recipient_headers,
    )
    assert recipient_item.status_code == 200
    recipient_body = recipient_item.json()
    assert recipient_body["quantity"] == 2
    assert "received_quantity" in recipient_body
    for key in _BOOKING_KEYS:
        assert key not in recipient_body

    recipient_list = client.get(f"/api/wishlists/{wishlist_id}/items", headers=recipient_headers)
    assert recipient_list.status_code == 200
    own_wish = next(item for item in recipient_list.json() if item["id"] == item_id)
    for key in _BOOKING_KEYS:
        assert key not in own_wish

    service: WishlistService = app.state.domain_service

    asyncio.run(
        app.state.user_store.upsert_user(TelegramUser(id=_OTHER_GIFTER_ID, first_name="Cara"))
    )
    asyncio.run(
        app.state.user_store.upsert_user(
            TelegramUser(id=_OTHER_GIFTER_ID, first_name="Cara", language_code="ru")
        )
    )
    asyncio.run(
        service.add_member(
            wishlist_id=wishlist_id,
            actor=make_user(_RECIPIENT_ID, "Alice"),
            user_id=_OTHER_GIFTER_ID,
        )
    )
    addressed = client.post(
        f"/api/wishlists/{wishlist_id}/items",
        json={"title": "Kettle", "quantity": 2, "recipient_user_id": _OTHER_GIFTER_ID},
        headers=recipient_headers,
    )
    assert addressed.status_code == 201, addressed.text
    addressed_id = int(addressed.json()["id"])
    bob_headers = auth_header(sessions, _OTHER_GIFTER_ID, "Cara")

    coauthor = client.post(
        reservations_url(wishlist_id, addressed_id),
        json={"quantity": 1},
        headers=recipient_headers,
    )
    assert coauthor.status_code == 201
    assert coauthor.json()["status"] == "active"
    assert "user_id" not in coauthor.json()
    designated = client.post(
        reservations_url(wishlist_id, addressed_id),
        json={"quantity": 1},
        headers=bob_headers,
    )
    assert designated.status_code == 403
    assert designated.json() == {"detail": "Cannot promise this wish"}

    designated_item = client.get(
        f"/api/wishlists/{wishlist_id}/items/{addressed_id}",
        headers=bob_headers,
    )
    assert designated_item.status_code == 200
    for key in _BOOKING_KEYS:
        assert key not in designated_item.json()

    coauthor_item = client.get(
        f"/api/wishlists/{wishlist_id}/items/{addressed_id}",
        headers=recipient_headers,
    )
    assert coauthor_item.status_code == 200
    assert coauthor_item.json()["available_quantity"] == 1
    assert coauthor_item.json()["my_reserved_quantity"] == 1

    collection = client.get("/api/wishlists", headers=recipient_headers)
    assert collection.status_code == 200
    assert_no_reservation_list(collection.json())
    detail = client.get(f"/api/wishlists/{wishlist_id}", headers=bob_headers)
    assert detail.status_code == 200
    assert_no_reservation_list(detail.json())


def test_completed_promise_log_omits_the_gifter(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A successful action logs the promise status and not the gifter."""
    client, sessions, _app = test_app
    wishlist_id, item_id, _, gifter_headers = open_active_wish(client, sessions)
    token = gifter_headers["Authorization"]
    url = reservations_url(wishlist_id, item_id)

    with caplog.at_level(logging.INFO, logger=_ROUTE_LOGGER):
        created = create_promise(client, wishlist_id, item_id, gifter_headers)
        purchased = client.post(
            f"{url}/{created['reservation_id']}/purchase",
            headers=gifter_headers,
        )

    assert purchased.status_code == 200
    completed = route_events(caplog, "reservation_action_completed")
    observed = [
        (
            route_extra(record)["operation"],
            route_extra(record)["item_id"],
            route_extra(record)["reservation_id"],
            route_extra(record)["status"],
        )
        for record in completed
    ]
    assert observed == [
        ("create_reservation", item_id, created["reservation_id"], "active"),
        ("purchase_reservation", item_id, created["reservation_id"], "purchased"),
    ]
    for record in completed:
        assert record.levelno == logging.INFO
        assert_route_record_hides_identity(
            record,
            token,
            "Alice",
            "Bob",
            "Headphones",
            "Alice Birthday",
        )
        assert "quantity" not in record.__dict__


def test_recipient_create_refusal_hides_whether_a_promise_exists(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Create 403 is the same record when the wish has a promise and when it does not."""
    client, sessions, _app = test_app
    wishlist_id, item_id, recipient_headers, gifter_headers = open_active_wish(client, sessions)
    token = recipient_headers["Authorization"]
    url = reservations_url(wishlist_id, item_id)

    with caplog.at_level(logging.WARNING, logger=_ROUTE_LOGGER):
        empty = client.post(url, json={"quantity": 1}, headers=recipient_headers)
        created = create_promise(client, wishlist_id, item_id, gifter_headers, quantity=1)
        occupied = client.post(url, json={"quantity": 1}, headers=recipient_headers)

    assert empty.status_code == 403
    assert occupied.status_code == 403
    assert empty.json() == occupied.json() == {"detail": "Cannot promise this wish"}
    refused = route_events(caplog, "reservation_action_refused")
    assert int(created["reservation_id"]) > 0
    assert len(refused) == 2
    assert refused[0].getMessage() == refused[1].getMessage()
    assert route_extra(refused[0]) == route_extra(refused[1])
    for record in refused:
        fields = route_extra(record)
        assert record.levelno == logging.WARNING
        assert fields["http_status"] == 403
        assert fields["operation"] == "create_reservation"
        assert fields["item_id"] == item_id
        assert "reservation_id" not in fields
        assert_route_record_hides_identity(record, token, "Alice", "Bob")


def test_recipient_mutation_refusal_matches_a_missing_promise(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Mutation 404 does not say the promise existed, and it names no gifter."""
    client, sessions, _app = test_app
    wishlist_id, item_id, recipient_headers, gifter_headers = open_active_wish(client, sessions)
    token = recipient_headers["Authorization"]
    created = create_promise(client, wishlist_id, item_id, gifter_headers)
    real_id = int(created["reservation_id"])
    missing_id = real_id + 1000
    prefix = reservations_url(wishlist_id, item_id)

    with caplog.at_level(logging.WARNING, logger=_ROUTE_LOGGER):
        recipient = client.post(f"{prefix}/{real_id}/cancel", headers=recipient_headers)
        missing = client.post(f"{prefix}/{missing_id}/cancel", headers=recipient_headers)

    assert recipient.status_code == 404
    assert missing.status_code == 404
    assert recipient.json() == missing.json() == {"detail": "Resource not found"}
    refused = route_events(caplog, "reservation_action_refused")
    assert len(refused) == 2
    recipient_log, missing_log = refused
    recipient_fields = route_extra(recipient_log)
    missing_fields = route_extra(missing_log)
    assert recipient_log.getMessage() == missing_log.getMessage()
    assert recipient_log.levelno == missing_log.levelno == logging.WARNING
    assert recipient_fields["http_status"] == missing_fields["http_status"] == 404
    assert recipient_fields["operation"] == "cancel_reservation"
    assert missing_fields["operation"] == "cancel_reservation"
    assert recipient_fields["item_id"] == missing_fields["item_id"] == item_id
    assert recipient_fields["reservation_id"] == real_id
    assert missing_fields["reservation_id"] == missing_id
    assert set(recipient_fields) == set(missing_fields)
    for record in refused:
        assert_route_record_hides_identity(record, token, "Alice", "Bob", "Headphones")


def test_busy_promise_logs_warning_without_gifter(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A busy wish is WARNING 503 and the route log has no gifter."""
    client, sessions, app = test_app
    wishlist_id, item_id, _, gifter_headers = open_active_wish(client, sessions)
    token = gifter_headers["Authorization"]

    async def busy(*_args: object, **_kwargs: object) -> None:
        raise InventoryBusyError()

    monkeypatch.setattr(app.state.wishlist_store, "execute_wish", busy)
    with caplog.at_level(logging.WARNING, logger=_ROUTE_LOGGER):
        response = client.post(
            reservations_url(wishlist_id, item_id),
            json={"quantity": 1},
            headers=gifter_headers,
        )

    assert response.status_code == 503
    busy_logs = route_events(caplog, "reservation_inventory_busy")
    assert len(busy_logs) == 1
    record = busy_logs[0]
    fields = route_extra(record)
    assert record.levelno == logging.WARNING
    assert fields["operation"] == "create_reservation"
    assert fields["item_id"] == item_id
    assert "reservation_id" not in fields
    assert route_events(caplog, "reservation_action_completed") == []
    assert_route_record_hides_identity(record, token, "Alice", "Bob", "Headphones")
