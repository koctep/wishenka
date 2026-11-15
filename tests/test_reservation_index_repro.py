"""Reproduce table-wide reservation reads for the giver's cabinet."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from wishenka.auth.models import AuthenticatedUser
from wishenka.auth.session import SessionTokenService
from wishenka.config import Settings
from wishenka.web.app import create_app
from wishenka.wishlists.models import Reservation
from wishenka.wishlists.service import WishlistService

pytestmark = pytest.mark.timeout(30)


def _user(user_id: int) -> AuthenticatedUser:
    return AuthenticatedUser(
        telegram_id=user_id, first_name=f"User {user_id}", auth_method="session_token"
    )


async def _seed(service: WishlistService) -> int:
    owner, giver, other = _user(101), _user(202), _user(303)
    wishlist = await service.create_wishlist(owner=owner, title="Birthday")
    item = await service.add_wish_item(
        wishlist_id=wishlist.id, actor=owner, title="Indexed book", quantity=3
    )
    reservation = await service.create_reservation(item_id=item.id, user=giver, quantity=1)
    await service.create_reservation(item_id=item.id, user=other, quantity=1)
    return reservation.id


class _CountScans(dict[int, Reservation]):
    """Count requests to traverse the primary reservation collection."""

    scans = 0

    def values(self) -> Any:
        self.scans += 1
        return super().values()


@pytest.mark.parametrize("method", ["list", "summary"])
def test_memory_cabinet_does_not_scan_all_users(method: str) -> None:
    service = WishlistService()
    reservation_id = asyncio.run(_seed(service))
    tracked = _CountScans(service._reservations)
    service._reservations = tracked
    if method == "list":
        result = asyncio.run(service.get_user_reservations(202))
        assert [row.reservation_id for row in result] == [reservation_id]
    else:
        summary = asyncio.run(service.get_user_reservations_summary(202))
        assert summary.total_active_reservations == 1
        assert summary.total_distinct_items == 1
    assert tracked.scans == 0, "cabinet scanned the full reservation mapping"


@pytest.mark.parametrize("path", ["/web/reservations/list", "/web/reservations/card"])
def test_sqlite_cabinet_does_not_load_all_reservations(tmp_path: Path, path: str) -> None:
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'cabinet.db'}",
        secret_key="test-reservation-index-secret",
    )
    app = create_app(settings)
    sessions = SessionTokenService(settings.secret_key)
    with TestClient(app) as client:
        asyncio.run(app.state.wishlist_store.execute(_seed))
        statements: list[str] = []

        def capture(
            conn: Any, cursor: Any, statement: str, params: Any, context: Any, many: bool
        ) -> None:
            statements.append(" ".join(statement.lower().split()))

        engine = app.state.wishlist_store.engine.sync_engine
        event.listen(engine, "before_cursor_execute", capture)
        try:
            token = sessions.create_token(202, "User 202")
            response = client.get(path, headers={"Authorization": f"Bearer {token}"})
        finally:
            event.remove(engine, "before_cursor_execute", capture)
        assert response.status_code == 200
        if path.endswith("/list"):
            assert "Indexed book" in response.text
        else:
            assert re.search(r"\b1\b", response.text)
        full_reads = [
            sql for sql in statements if re.search(r"\bfrom wl_reservations\s+order by\b", sql)
        ]
        assert not full_reads, f"cabinet loaded all reservations: {full_reads}"
