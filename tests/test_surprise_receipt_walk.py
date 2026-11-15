"""Surprise walks for gift receipt (WISHENKA-23, R-8, DoD 10).

``tests/test_surprise_role_context.py`` is edited by plan steps 9 and 29 and is not touched
here. These tests carry the same two checks as new tests: the replacement of its absence
assertion (section 12, items 1 to 3) and the second walk (a receipt on a wish with another
user's open promise, then the gifted read).
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.receipt_support import (
    OWNER,
    OWNER_ID,
    RECEIPT_COLUMNS,
    AppEnv,
    app_env,
    bearer,
    db_path_of,
    make_user,
    new_symbol,
    outbox_rows,
    seed_wish,
    sql_rows,
)

pytestmark = pytest.mark.timeout(30)

_GIFTER_ID = 88001122
_GIFTER_NAME = "Greta"
_GIFTER_USERNAME = "greta_gift"
_GIFTER = make_user(_GIFTER_ID, _GIFTER_NAME)
_W2_QUANTITY = 80
_W2_BOOKED = 37
_W2_RECEIVE = 2
_W2_REMAINDER = _W2_QUANTITY - _W2_RECEIVE - _W2_BOOKED
_PURCHASE_MARKS = ("purchased", "Куплено", "bought")
_NOTICE_MARKS = ("notification", "outbox", "push")
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
# Only these log extras can carry a booking quantity. Counts, ids, paths and timings such as
# ``reservations_count`` or ``duration_ms`` are operator fields: scanning their names or values
# would trip the "reservation" and whole-number checks without any booking fact in them.
_QUANTITY_KEYS = (
    "quantity",
    "received_quantity",
    "total_quantity",
    "remaining_quantity",
    "available_quantity",
    "reserved_quantity",
    "my_reserved_quantity",
)
_LOG_FIELDS = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


@pytest.fixture
def test_app(tmp_path: Path) -> Iterator[AppEnv]:
    """Open create_app with the default bot token, so no notice worker runs."""
    with app_env(tmp_path, "walk.db") as env:
        yield env


def _gifter_marks() -> tuple[str, ...]:
    return (_GIFTER_NAME, _GIFTER_USERNAME, str(_GIFTER_ID))


def _has_whole_number(text: str, number: int) -> bool:
    return re.search(rf"(?<!\d){number}(?!\d)", text) is not None


def _walk2_leaks(text: str) -> list[str]:
    """Booking facts in one surface, after removing timestamps and clock times."""
    cleaned = re.sub(r"\d{4}-\d{2}-\d{2}T[\d:.+Z-]+", "", text)
    cleaned = re.sub(r"\d{1,2}:\d{2}(:\d{2})?", "", cleaned)
    folded = cleaned.casefold()
    leaks = [
        mark
        for mark in (*_gifter_marks(), *_PURCHASE_MARKS, "reservation", *_GIVER_FIELDS)
        if mark.casefold() in folded
    ]
    leaks.extend(
        str(number) for number in (_W2_BOOKED, _W2_REMAINDER) if _has_whole_number(cleaned, number)
    )
    return leaks


def _record_text(record: logging.LogRecord) -> str:
    extras = {key: value for key, value in record.__dict__.items() if key not in _LOG_FIELDS}
    return f"{record.getMessage()} {extras}"


def _walk2_log_scan_text(record: logging.LogRecord) -> str:
    """Event, message without the middleware duration, and values of the quantity keys."""
    message = re.sub(r"duration=\S*?ms", "", record.getMessage())
    values = " ".join(str(record.__dict__[key]) for key in _QUANTITY_KEYS if key in record.__dict__)
    return f"{record.__dict__.get('event', '')} {message} {values}"


def test_recipient_walk_creates_no_notice_for_owner(test_app: AppEnv) -> None:
    """R-8.3 (replacement of the absence assertion): the table may exist, but stays empty."""
    client, sessions, app = test_app
    service = app.state.domain_service

    async def seed() -> tuple[int, int]:
        wishlist_id, item_id = await seed_wish(service, quantity=8, recipient_name="Sam")
        await service.record_item_fulfillment(item_id, OWNER, 1)
        reservation = await service.create_reservation(item_id=item_id, user=_GIFTER, quantity=3)
        await service.mark_reservation_purchased(reservation_id=reservation.id, user=_GIFTER)
        return wishlist_id, item_id

    wishlist_id, item_id = asyncio.run(seed())
    response = client.get(
        f"/api/wishlists/{wishlist_id}/items/{item_id}", headers=bearer(sessions, OWNER_ID)
    )
    assert response.status_code == 200, response.text

    db = db_path_of(app)
    rows = outbox_rows(db)
    assert rows == []
    assert [r for r in rows if r["giver_user_id"] == OWNER_ID] == []
    columns = sql_rows(db, "PRAGMA table_info(wl_receipts)")
    assert {column["name"] for column in columns} <= RECEIPT_COLUMNS
    assert columns, "wl_receipts does not exist yet"


def test_second_walk_receipt_and_gifted_read_hide_the_booking(
    test_app: AppEnv, caplog: pytest.LogCaptureFixture
) -> None:
    """R-8.1, R-8.2: receipt on a promised wish and the gifted read reveal no booking fact."""
    client, sessions, app = test_app
    service = app.state.domain_service

    async def seed() -> tuple[int, int]:
        wishlist_id, item_id = await seed_wish(service, quantity=_W2_QUANTITY, recipient_name="Sam")
        await service.create_reservation(item_id=item_id, user=_GIFTER, quantity=_W2_BOOKED)
        return wishlist_id, item_id

    wishlist_id, item_id = asyncio.run(seed())
    headers = bearer(sessions, OWNER_ID)
    gifted_fields = set(new_symbol("wishenka.wishlists.schemas", "GiftedItemDTO").model_fields)
    caplog.clear()
    with caplog.at_level(logging.INFO):
        posted = client.post(
            f"/api/wishlists/{wishlist_id}/items/{item_id}/receipts",
            json={"quantity": _W2_RECEIVE},
            headers=headers,
        )
        read = client.get(f"/api/wishlists/{wishlist_id}/gifted", headers=headers)

    assert posted.status_code == 201, posted.text
    assert read.status_code == 200, read.text
    assert posted.json()["remaining_quantity"] == _W2_QUANTITY - _W2_RECEIVE
    for response in (posted, read):
        leaks = _walk2_leaks(response.text)
        for name, value in response.headers.items():
            if name not in {"date", "content-length"}:
                leaks.extend(_walk2_leaks(f"{name}: {value}"))
        assert leaks == []
    entries = read.json()
    assert entries
    assert all(set(entry) <= gifted_fields for entry in entries)
    assert caplog.records, "the two requests must log"
    for record in caplog.records:
        full = _record_text(record)
        for mark in _gifter_marks():
            assert mark not in full
        assert _walk2_leaks(_walk2_log_scan_text(record)) == []
        notice_text = f"{getattr(record, 'event', '')} {record.getMessage()}".casefold()
        for mark in _NOTICE_MARKS:
            assert mark not in notice_text

    rows = outbox_rows(db_path_of(app))
    assert [(r["giver_user_id"], r["status"]) for r in rows] == [(_GIFTER_ID, "pending")]
