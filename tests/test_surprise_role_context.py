"""Surprise walk and share-link visit checks (WISHENKA-38).

The product already hides a booking from the recipient and already treats a
share link as a read. These checks lock that behavior. They do not add a
notification sender.
"""

from __future__ import annotations

import asyncio
import logging
import re
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
from wishenka.wishlists.schemas import WishItemRecipientViewDTO
from wishenka.wishlists.service import WishlistService

pytestmark = pytest.mark.timeout(30)

_OWNER_ID = 101
_GIFTER_ID = 88001122
_GIFTER_NAME = "Greta"
_GIFTER_USERNAME = "greta_gift"
_QUANTITY = 8
_RECEIVED = 1
_BOOKED = 3
_REMAINDER = 4
_SQLITE_PREFIX = "sqlite+aiosqlite:///"
_RECIPIENT_FIELDS = set(WishItemRecipientViewDTO.model_fields)
_GIVER_FIELDS = (
    "available_quantity",
    "is_fully_reserved",
    "is_reserved_by_me",
    "my_reserved_quantity",
    "my_reservation_status",
    "my_reservation_id",
    "my_latest_reservation_quantity",
    "my_occupying_reservation_count",
)
_PURCHASE_MARKS = ("purchased", "Куплено", "bought")
_NOTICE_MARKS = ("notification", "outbox", "push")
_LOG_FIELDS = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}
_RECEIPT_COLUMNS = {"id", "wish_item_id", "quantity", "received_at", "is_approximate"}


def make_user(
    telegram_id: int,
    first_name: str,
    username: str | None = None,
) -> AuthenticatedUser:
    """Create a bearer test user."""
    return AuthenticatedUser(
        telegram_id=telegram_id,
        first_name=first_name,
        username=username,
        auth_method="session_token",
    )


@pytest.fixture
def test_app(tmp_path: Path) -> Iterator[tuple[TestClient, SessionTokenService, FastAPI]]:
    """Open create_app on an isolated SQLite file."""
    database = tmp_path / "surprise_role_context.db"
    settings = Settings(
        database_url=f"{_SQLITE_PREFIX}{database}",
        secret_key="surprise-role-context-test-secret",
    )
    app = create_app(settings)
    sessions = SessionTokenService(settings.secret_key)
    with TestClient(app) as client:
        yield client, sessions, app


def _db_path(app: FastAPI) -> str:
    """Return the temporary SQLite file for this app."""
    return str(app.state.settings.database_url).removeprefix(_SQLITE_PREFIX)


def user_count(app: FastAPI) -> int:
    """Return the number of account rows."""
    with sqlite3.connect(_db_path(app)) as conn:
        row = conn.execute("SELECT COUNT(*) FROM users").fetchone()
    assert row is not None
    return int(row[0])


def notice_rows(app: FastAPI) -> list[sqlite3.Row]:
    """Return every row of the notice queue (the table exists since the outbox revision)."""
    with sqlite3.connect(_db_path(app)) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute("SELECT * FROM notification_outbox").fetchall()


def receipt_columns(app: FastAPI) -> set[str]:
    """Return the column names of the receipt history table."""
    with sqlite3.connect(_db_path(app)) as conn:
        return {str(row[1]) for row in conn.execute("PRAGMA table_info(wl_receipts)")}


def _gifter_marks() -> tuple[str, ...]:
    """Return the gifter name, username, and Telegram id."""
    return (_GIFTER_NAME, _GIFTER_USERNAME, str(_GIFTER_ID))


def _has_whole_number(text: str, number: int) -> bool:
    """Return whether ``number`` appears outside a longer digit run."""
    return re.search(rf"(?<!\d){number}(?!\d)", text) is not None


def _booking_leaks(text: str) -> list[str]:
    """Return booking facts found in one response surface."""
    folded = text.casefold()
    leaks: list[str] = []
    for mark in (*_gifter_marks(), *_PURCHASE_MARKS, "reservation", *_GIVER_FIELDS):
        if mark.casefold() in folded:
            leaks.append(mark)
    for number in (_BOOKED, _REMAINDER):
        if _has_whole_number(text, number):
            leaks.append(str(number))
    return leaks


def _record_text(record: logging.LogRecord) -> str:
    """Return one log message plus its extras."""
    extras = {key: value for key, value in record.__dict__.items() if key not in _LOG_FIELDS}
    return f"{record.getMessage()} {extras}"


def test_recipient_walk_hides_booking_in_response_log_and_notice(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """One owner read hides the booking in the answer, its log, and any notice."""
    client, sessions, app = test_app
    service: WishlistService = app.state.domain_service
    owner = make_user(_OWNER_ID, "Alice")
    gifter = make_user(_GIFTER_ID, _GIFTER_NAME, _GIFTER_USERNAME)

    async def seed() -> tuple[int, int]:
        wishlist = await service.create_wishlist(owner=owner, title="Alice Birthday")
        item = await service.add_wish_item(
            wishlist_id=wishlist.id,
            actor=owner,
            title="Kettle",
            quantity=_QUANTITY,
            recipient_name="Sam",
        )
        await service.record_item_fulfillment(
            item_id=item.id,
            actor=owner,
            received_quantity=_RECEIVED,
        )
        reservation = await service.create_reservation(
            item_id=item.id,
            user=gifter,
            quantity=_BOOKED,
        )
        await service.mark_reservation_purchased(reservation_id=reservation.id, user=gifter)
        return wishlist.id, item.id

    wishlist_id, item_id = asyncio.run(seed())
    token = sessions.create_token(_OWNER_ID, "Alice")
    caplog.clear()
    with caplog.at_level(logging.INFO):
        response = client.get(
            f"/api/wishlists/{wishlist_id}/items/{item_id}",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) <= _RECIPIENT_FIELDS
    assert body["quantity"] == _QUANTITY
    assert body["received_quantity"] == _RECEIVED
    leaks = _booking_leaks(response.text)
    for name, value in response.headers.items():
        leaks.extend(_booking_leaks(f"{name}: {value}"))
    assert leaks == []
    for record in caplog.records:
        text = _record_text(record)
        for mark in _gifter_marks():
            assert mark not in text
        notice_text = f"{getattr(record, 'event', '')} {record.getMessage()}".casefold()
        for mark in _NOTICE_MARKS:
            assert mark not in notice_text
    # The receipt was recorded before any booking existed: nobody is a giver, so any row (above
    # all one for the owner, who is the recipient) would be a leak (R-8.3).
    rows = notice_rows(app)
    assert rows == []
    assert all(row["giver_user_id"] != _OWNER_ID for row in rows)
    assert receipt_columns(app) <= _RECEIPT_COLUMNS


def test_share_link_visit_creates_no_account(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An unidentified share visit adds no account and shows the free remainder."""
    client, _sessions, app = test_app
    service: WishlistService = app.state.domain_service
    owner = make_user(_OWNER_ID, "Alice")

    async def seed() -> str:
        wishlist = await service.create_wishlist(owner=owner, title="Open List")
        await service.add_wish_item(
            wishlist_id=wishlist.id,
            actor=owner,
            title="Mug",
            quantity=2,
        )
        return str(wishlist.public_token)

    public_token = asyncio.run(seed())
    before = user_count(app)
    caplog.clear()
    with caplog.at_level(logging.INFO):
        response = client.get(f"/share/{public_token}", headers={"Accept-Language": "ru"})

    assert response.status_code == 200, response.text
    assert response.request.url.path != "/healthz"
    assert user_count(app) == before
    created = [
        record for record in caplog.records if getattr(record, "event", None) == "user_created"
    ]
    assert created == []
    assert "Доступно:" in response.text
    assert "Забронировать" not in response.text
