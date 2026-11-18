"""Red tests for the web access to gift receipt (WISHENKA-23, R-5, R-7, R-8.1).

Today the receipt and gifted routes do not exist (HTTP 404), the DTOs lack the new fields and
archive/restore never answers with the closed ``nothing_remaining`` reason.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI

from tests.receipt_support import (
    GIFTER,
    GIFTER_ID,
    OWNER,
    OWNER_ID,
    AppEnv,
    app_env,
    attr_of,
    bearer,
    db_path_of,
    item_received,
    new_symbol,
    seed_wish,
    sql_exec,
)
from wishenka.wishlists.exceptions import InventoryBusyError
from wishenka.wishlists.models import ReservationStatus
from wishenka.wishlists.schemas import (
    MyReservationItemDTO,
    WishItemGifterViewDTO,
    WishItemRecipientViewDTO,
)
from wishenka.wishlists.service import WishlistService

pytestmark = pytest.mark.timeout(30)

_ORIGIN = "http://testserver"
_RESULT_KEYS = {
    "item",
    "received_now",
    "received_quantity",
    "remaining_quantity",
    "is_fully_received",
}
_REASONS: dict[str, tuple[int, str, str, bool]] = {
    "quantity_invalid": (
        400,
        "quantity_invalid",
        "Quantity must be a whole number of at least 1",
        False,
    ),
    "above_remaining": (
        409,
        "quantity_above_remaining",
        "Quantity is above the remaining quantity",
        True,
    ),
    "wish_archived": (409, "wish_archived", "The wish is archived", False),
    "list_archived": (409, "wishlist_not_active", "The wishlist is not active", False),
    "list_deleted": (404, "wishlist_not_active", "The wishlist is not active", False),
    "nothing_remaining": (409, "nothing_remaining", "Nothing remains to receive", True),
    "forbidden": (403, "forbidden", "Forbidden", False),
    "not_found": (404, "not_found", "Resource not found", False),
}


@pytest.fixture
def test_app(tmp_path: Path) -> Iterator[AppEnv]:
    """Open create_app on an isolated SQLite file."""
    with app_env(tmp_path) as env:
        yield env


def _domain(app: FastAPI) -> WishlistService:
    service: WishlistService = app.state.domain_service
    return service


def _seed(app: FastAPI, quantity: int = 5, *, promised: int = 0) -> tuple[int, int]:
    service = _domain(app)

    async def run() -> tuple[int, int]:
        wishlist_id, item_id = await seed_wish(service, quantity=quantity)
        if promised:
            await service.create_reservation(item_id=item_id, user=GIFTER, quantity=promised)
        return wishlist_id, item_id

    return asyncio.run(run())


def _url(wishlist_id: int, item_id: int) -> str:
    return f"/api/wishlists/{wishlist_id}/items/{item_id}/receipts"


def test_receipt_route_success_shape(test_app: AppEnv) -> None:
    """R-1.5, R-7.1, R-8.1: 201 with the recipient-safe result, no promise or giver."""
    client, sessions, app = test_app
    wishlist_id, item_id = _seed(app, 5, promised=2)

    response = client.post(
        _url(wishlist_id, item_id), json={"quantity": 2}, headers=bearer(sessions, OWNER_ID)
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body) == _RESULT_KEYS
    assert (body["received_now"], body["received_quantity"], body["remaining_quantity"]) == (
        2,
        2,
        3,
    )
    assert body["is_fully_received"] is False
    assert set(body["item"]) <= set(WishItemRecipientViewDTO.model_fields)
    for mark in ("reserv", "available", "giver", "my_", "Greta", str(GIFTER_ID)):
        assert mark not in response.text


@pytest.mark.parametrize("case", sorted(_REASONS))
def test_receipt_route_reason_table(test_app: AppEnv, case: str) -> None:
    """R-7.2: closed reasons, fixed wording, ``remaining_quantity`` only for two of them."""
    client, sessions, app = test_app
    status, reason, message, has_remaining = _REASONS[case]
    wishlist_id, item_id = _seed(app, 5, promised=2)
    service = _domain(app)
    headers = bearer(sessions, OWNER_ID)
    quantity = 1
    target_item = item_id
    if case == "quantity_invalid":
        quantity = 0
    elif case == "above_remaining":
        quantity = 9
    elif case == "wish_archived":
        asyncio.run(service.archive_wish_item(wishlist_id, item_id, OWNER))
    elif case == "list_archived":
        asyncio.run(service.archive_wishlist(wishlist_id, OWNER))
    elif case == "list_deleted":
        asyncio.run(service.delete_wishlist(wishlist_id, OWNER))
    elif case == "nothing_remaining":
        asyncio.run(service.record_item_fulfillment(item_id, OWNER, 5))
    elif case == "forbidden":
        headers = bearer(sessions, GIFTER_ID, "Greta")
    else:
        target_item = item_id + 1000

    response = client.post(
        _url(wishlist_id, target_item), json={"quantity": quantity}, headers=headers
    )

    assert response.status_code == status, response.text
    detail = response.json()["detail"]
    assert isinstance(detail, dict), response.text
    assert detail["reason"] == reason
    assert detail["message"] == message
    # The fixed minimum "at least 1" (design 6) is no booked or received count.
    assert re.search(r"\d", detail["message"].replace("at least 1", "")) is None
    assert ("remaining_quantity" in detail) is has_remaining
    if case == "above_remaining":
        assert detail["remaining_quantity"] == 5
    if case == "nothing_remaining":
        assert detail["remaining_quantity"] == 0


def test_receipt_route_auth_and_csrf(test_app: AppEnv) -> None:
    """R-7.1: 401 anonymous, CSRF on cookie sessions, success with a valid token."""
    client, sessions, app = test_app
    wishlist_id, item_id = _seed(app, 5, promised=1)
    url = _url(wishlist_id, item_id)

    assert client.post(url, json={"quantity": 1}).status_code == 401

    client.cookies.set("session_id", sessions.create_token(OWNER_ID, "Alice"))
    no_token = client.post(url, json={"quantity": 1}, headers={"Origin": _ORIGIN})
    assert no_token.status_code == 403
    assert item_received(db_path_of(app), item_id) == 0
    csrf = client.get("/api/auth/csrf").json()["csrf_token"]
    accepted = client.post(
        url, json={"quantity": 1}, headers={"Origin": _ORIGIN, "X-CSRF-Token": csrf}
    )
    assert accepted.status_code == 201, accepted.text


@pytest.mark.parametrize("extra", [{"giver": 5}, {"confirm": True}])
def test_receipt_route_unknown_field_422(test_app: AppEnv, extra: dict[str, Any]) -> None:
    """R-1.5: no giver and no confirmation field; the counter stays."""
    client, sessions, app = test_app
    wishlist_id, item_id = _seed(app, 5)

    response = client.post(
        _url(wishlist_id, item_id),
        json={"quantity": 1, **extra},
        headers=bearer(sessions, OWNER_ID),
    )

    assert response.status_code == 422, response.text
    assert item_received(db_path_of(app), item_id) == 0


def test_receipt_route_non_integer_quantity_422(test_app: AppEnv) -> None:
    """Design 6: a body type error is rejected before the service runs; the counter stays."""
    client, sessions, app = test_app
    wishlist_id, item_id = _seed(app, 5, promised=1)

    response = client.post(
        _url(wishlist_id, item_id), json={"quantity": "abc"}, headers=bearer(sessions, OWNER_ID)
    )

    assert response.status_code == 422, response.text
    assert item_received(db_path_of(app), item_id) == 0


def test_receipt_route_busy_503(test_app: AppEnv, monkeypatch: pytest.MonkeyPatch) -> None:
    """R-7.2: a busy wish gives the retryable 503 with the promise route's sentence."""
    client, sessions, app = test_app
    wishlist_id, item_id = _seed(app, 5, promised=1)

    async def busy(*_args: object, **_kwargs: object) -> None:
        raise InventoryBusyError()

    monkeypatch.setattr(app.state.wishlist_store, "execute_wish", busy)
    promise = client.post(
        f"/api/wishlists/{wishlist_id}/items/{item_id}/reservations",
        json={"quantity": 1},
        headers=bearer(sessions, GIFTER_ID, "Greta"),
    )
    assert promise.status_code == 503
    response = client.post(
        _url(wishlist_id, item_id), json={"quantity": 1}, headers=bearer(sessions, OWNER_ID)
    )

    assert response.status_code == 503, response.text
    detail = response.json()["detail"]
    assert isinstance(detail, dict), response.text
    assert detail["reason"] == "busy"
    assert detail["message"] == promise.json()["detail"]


def test_new_dto_fields_have_defaults() -> None:
    """R-5.1, R-5.4: old constructions stay valid and derive the new fields."""
    recipient = WishItemRecipientViewDTO(id=1, title="t", quantity=5, received_quantity=2)
    assert attr_of(recipient, "remaining_quantity") == 3
    assert "is_fully_received" not in WishItemRecipientViewDTO.model_fields
    explicit = WishItemRecipientViewDTO(
        id=1, title="t", quantity=5, received_quantity=2, remaining_quantity=1
    )
    assert attr_of(explicit, "remaining_quantity") == 1

    giver_args: dict[str, Any] = {
        "id": 1,
        "title": "t",
        "quantity": 5,
        "received_quantity": 5,
        "available_quantity": 0,
        "is_fully_reserved": True,
        "is_reserved_by_me": False,
        "my_reserved_quantity": 0,
    }
    giver = WishItemGifterViewDTO(**giver_args)
    assert attr_of(giver, "remaining_quantity") == 0
    assert attr_of(giver, "is_fully_received") is True
    partly = WishItemGifterViewDTO(**{**giver_args, "received_quantity": 1})
    assert attr_of(partly, "is_fully_received") is False

    cabinet = MyReservationItemDTO(
        reservation_id=1,
        wish_item_id=2,
        wishlist_id=3,
        wishlist_title="l",
        recipient_name="r",
        item_title="t",
        reserved_quantity=1,
        status=ReservationStatus.ACTIVE,
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
        updated_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    assert attr_of(cabinet, "is_fully_received") is False
    assert "remaining_quantity" not in MyReservationItemDTO.model_fields


def test_gifted_route_and_read_data(test_app: AppEnv) -> None:
    """R-5.1 to R-5.4: gifted shape, giver flag, cabinet row marker."""
    from wishenka.web.routes.reservations_ui import _row

    client, sessions, app = test_app
    wishlist_id, item_id = _seed(app, 2, promised=2)
    service = _domain(app)
    asyncio.run(service.record_item_fulfillment(item_id, OWNER, 2))
    gifted_url = f"/api/wishlists/{wishlist_id}/gifted"
    gifted_dto = new_symbol("wishenka.wishlists.schemas", "GiftedItemDTO")

    response = client.get(gifted_url, headers=bearer(sessions, OWNER_ID))
    assert response.status_code == 200, response.text
    entries = response.json()
    assert [entry["id"] for entry in entries] == [item_id]
    assert set(entries[0]) == set(gifted_dto.model_fields)
    assert set(entries[0]["receipts"][0]) == {"id", "received_at", "quantity", "is_approximate"}
    assert client.get(gifted_url, headers=bearer(sessions, GIFTER_ID, "Greta")).status_code == 403
    assert client.get(gifted_url).status_code == 401

    giver_view = client.get(
        f"/api/wishlists/{wishlist_id}/items/{item_id}", headers=bearer(sessions, GIFTER_ID)
    ).json()
    assert giver_view["remaining_quantity"] == 0
    assert giver_view["is_fully_received"] is True
    owner_view = client.get(
        f"/api/wishlists/{wishlist_id}/items/{item_id}", headers=bearer(sessions, OWNER_ID)
    ).json()
    assert owner_view["remaining_quantity"] == 0
    assert "is_fully_received" not in owner_view

    cabinet = asyncio.run(service.get_user_reservations(GIFTER_ID))
    row = _row(cabinet[0])
    assert attr_of(row, "wish_received") is True
    assert row.offer_actions is True


def test_archive_restore_routes_nothing_remaining(test_app: AppEnv) -> None:
    """R-4.4, R-7.2: JSON and HTMX archive and restore answer 409 for a received wish."""
    client, sessions, app = test_app
    wishlist_id, item_id = _seed(app, 2)
    asyncio.run(_domain(app).record_item_fulfillment(item_id, OWNER, 2))
    headers = bearer(sessions, OWNER_ID)
    htmx = headers | {"HX-Request": "true"}
    api = f"/api/wishlists/{wishlist_id}/items/{item_id}"
    web = f"/web/wishlists/{wishlist_id}/items/{item_id}"

    archive = client.post(f"{api}/archive", headers=headers)
    assert archive.status_code == 409, archive.text
    assert re.search(r"\d", str(archive.json()["detail"])) is None
    assert client.post(f"{web}/archive", headers=htmx).status_code == 409

    sql_exec(db_path_of(app), "UPDATE wl_items SET is_archived = 1 WHERE id = ?", (item_id,))
    restore = client.post(f"{api}/restore", headers=headers)
    assert restore.status_code == 409, restore.text
    assert re.search(r"\d", str(restore.json()["detail"])) is None
    assert client.post(f"{web}/restore", headers=htmx).status_code == 409
