"""Regression for validation precedence on reservation creation (WISHENKA-122)."""

import asyncio
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from wishenka.auth.models import AuthenticatedUser
from wishenka.auth.session import SessionTokenService
from wishenka.config import Settings
from wishenka.web.app import create_app

pytestmark = pytest.mark.timeout(30)


@pytest.mark.parametrize("quantity", [0, -1])
def test_invalid_quantity_precedes_missing_wish_lookup(tmp_path: Path, quantity: int) -> None:
    """Invalid create requests have the same 400 for present and absent wishes."""
    database = tmp_path / "reservations.db"
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{database}",
        secret_key="reservation-invalid-quantity-repro-secret",
    )
    app = create_app(settings)
    sessions = SessionTokenService(settings.secret_key)
    headers = {"Authorization": f"Bearer {sessions.create_token(202, 'Bob')}"}
    owner = AuthenticatedUser(telegram_id=101, first_name="Alice", auth_method="session_token")

    with TestClient(app) as client:

        async def seed() -> tuple[int, int]:
            service = app.state.domain_service
            wishlist = await service.create_wishlist(owner=owner, title="Birthday")
            item = await service.add_wish_item(
                wishlist_id=wishlist.id, actor=owner, title="Gift", quantity=1
            )
            return wishlist.id, item.id

        wishlist_id, item_id = asyncio.run(seed())
        existing_url = f"/api/wishlists/{wishlist_id}/items/{item_id}/reservations"
        missing_url = f"/api/wishlists/{wishlist_id}/items/{item_id + 10000}/reservations"
        existing = client.post(existing_url, json={"quantity": quantity}, headers=headers)
        assert existing.status_code == 400
        assert existing.json()["detail"] == "Reservation quantity must be at least 1"
        positive_missing = client.post(missing_url, json={"quantity": 1}, headers=headers)
        assert positive_missing.status_code == 404
        invalid_missing = client.post(missing_url, json={"quantity": quantity}, headers=headers)
        with sqlite3.connect(database) as conn:
            assert conn.execute("SELECT COUNT(*) FROM wl_reservations").fetchone() == (0,)
        assert invalid_missing.status_code == 400
        assert invalid_missing.json()["detail"] == "Reservation quantity must be at least 1"


def test_invalid_create_skips_storage_and_injected_service_and_logs_safely(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Both backing modes reject invalid input before invoking their service."""
    from unittest.mock import AsyncMock

    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'boundary.db'}",
        secret_key="reservation-invalid-quantity-boundary-secret",
    )
    app = create_app(settings)
    token = SessionTokenService(settings.secret_key).create_token(987654, "Bob")
    headers = {"Authorization": f"Bearer {token}"}
    url = "/api/wishlists/4/items/7/reservations"

    with TestClient(app) as client:
        store_call = AsyncMock(side_effect=AssertionError("unexpected store lookup"))
        app.state.wishlist_store.execute_wish = store_call
        with caplog.at_level("WARNING", logger="wishenka.web.reservations"):
            response = client.post(url, json={"quantity": 0}, headers=headers)
        assert response.status_code == 400
        store_call.assert_not_awaited()
        records = [
            r for r in caplog.records if getattr(r, "event", None) == "reservation_validation_error"
        ]
        assert len(records) == 1
        assert records[0].__dict__["operation"] == "create_reservation"
        assert records[0].__dict__["item_id"] == 7
        assert "987654" not in str(records[0].__dict__)
        assert "gifter_id" not in records[0].__dict__

        service = AsyncMock()
        app.state.wishlist_service = service
        injected = client.post(url, json={"quantity": -1}, headers=headers)
        assert injected.status_code == 400
        assert injected.json() == response.json()
        service.create_reservation.assert_not_awaited()
        unauthenticated = client.post(url, json={"quantity": 0})
        assert unauthenticated.status_code == 401
