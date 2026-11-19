"""Regression coverage for explicit completion of fully received purchased promises."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI

from tests.receipt_support import (
    GIFTER,
    GIFTER_ID,
    OTHER_GIFTER,
    OTHER_GIFTER_ID,
    OWNER,
    OWNER_ID,
    AppEnv,
    app_env,
    bearer,
    db_path_of,
    seed_wish,
    sql_rows,
)
from wishenka.wishlists.service import WishlistService

pytestmark = pytest.mark.timeout(30)


@pytest.fixture
def env(tmp_path: Path) -> Iterator[AppEnv]:
    """Use an isolated SQLite database and local HTTP client."""
    with app_env(tmp_path, name="wishenka_219.db") as test_env:
        yield test_env


def _seed(app: FastAPI, *, purchased: bool = True, received: int = 3) -> tuple[int, int, int, int]:
    service: WishlistService = app.state.domain_service

    async def setup() -> tuple[int, int, int, int]:
        wishlist_id, item_id = await seed_wish(service, quantity=3)
        first = await service.create_reservation(item_id=item_id, user=GIFTER, quantity=1)
        second = await service.create_reservation(item_id=item_id, user=OTHER_GIFTER, quantity=1)
        if purchased:
            await service.mark_reservation_purchased(first.id, GIFTER)
        if received:
            await service.record_item_fulfillment(item_id, OWNER, received)
        return wishlist_id, item_id, first.id, second.id

    return asyncio.run(setup())


def _complete_url(wishlist_id: int, item_id: int, reservation_id: int) -> str:
    return f"/api/wishlists/{wishlist_id}/items/{item_id}/reservations/{reservation_id}/complete"


def test_purchased_completion_preserves_receipts_and_other_promise(env: AppEnv) -> None:
    """A giver closes only their purchased promise and releases its occupied unit."""
    client, sessions, app = env
    wishlist_id, item_id, reservation_id, other_id = _seed(app)
    database = db_path_of(app)
    before_receipts = sql_rows(database, "SELECT * FROM wl_receipts ORDER BY id")
    before = sql_rows(
        database,
        "SELECT id, quantity, status FROM wl_reservations WHERE wish_item_id = ? ORDER BY id",
        (item_id,),
    )
    assert [(row["id"], row["status"]) for row in before] == [
        (reservation_id, "purchased"),
        (other_id, "active"),
    ]
    headers = bearer(sessions, GIFTER_ID)
    cabinet = client.get("/web/reservations/list", headers=headers)
    assert cabinet.status_code == 200
    assert f'data-reservation-id="{reservation_id}"' in cabinet.text

    response = client.post(_complete_url(wishlist_id, item_id, reservation_id), headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "completed"
    after = sql_rows(
        database,
        "SELECT id, quantity, status FROM wl_reservations WHERE wish_item_id = ? ORDER BY id",
        (item_id,),
    )
    assert after == [
        {"id": reservation_id, "quantity": 1, "status": "completed"},
        {"id": other_id, "quantity": 1, "status": "active"},
    ]
    assert sql_rows(database, "SELECT * FROM wl_receipts ORDER BY id") == before_receipts
    assert sum(row["quantity"] for row in after if row["status"] in {"active", "purchased"}) == 1
    assert (
        f'data-reservation-id="{reservation_id}"'
        not in client.get("/web/reservations/list", headers=headers).text
    )
    summary = asyncio.run(app.state.domain_service.get_user_reservations_summary(GIFTER_ID))
    assert summary.total_distinct_items == 0
    assert (
        client.post(
            _complete_url(wishlist_id, item_id, reservation_id), headers=headers
        ).status_code
        == 409
    )


def test_cabinet_offers_completion_only_to_eligible_giver(env: AppEnv) -> None:
    """The explicit action is visible for a purchased, fully received promise."""
    client, sessions, app = env
    wishlist_id, item_id, reservation_id, _ = _seed(app)
    response = client.get("/web/reservations/list", headers=bearer(sessions, GIFTER_ID))
    assert response.status_code == 200
    assert _complete_url(wishlist_id, item_id, reservation_id) in response.text
    other = client.get("/web/reservations/list", headers=bearer(sessions, OTHER_GIFTER.telegram_id))
    assert other.status_code == 200
    assert _complete_url(wishlist_id, item_id, reservation_id) not in other.text


@pytest.mark.parametrize("purchased,received", [(False, 3), (True, 1)])
def test_ineligible_owner_cannot_complete(env: AppEnv, purchased: bool, received: int) -> None:
    """Intended promises and promises on partially received wishes remain open."""
    client, sessions, app = env
    wishlist_id, item_id, reservation_id, _ = _seed(app, purchased=purchased, received=received)
    response = client.post(
        _complete_url(wishlist_id, item_id, reservation_id), headers=bearer(sessions, GIFTER_ID)
    )
    assert response.status_code == 409, response.text
    rows = sql_rows(
        db_path_of(app), "SELECT status FROM wl_reservations WHERE id = ?", (reservation_id,)
    )
    assert rows == [{"status": "purchased" if purchased else "active"}]


def test_foreign_user_cannot_complete_a_promise(env: AppEnv) -> None:
    """An author receives the same non-disclosing refusal as for a missing promise."""
    client, sessions, app = env
    wishlist_id, item_id, reservation_id, _ = _seed(app)
    control_list, control_item, control_reservation, _ = _seed(app)
    owner_response = client.post(
        _complete_url(control_list, control_item, control_reservation),
        headers=bearer(sessions, GIFTER_ID),
    )
    assert owner_response.status_code == 200, owner_response.text
    headers = bearer(sessions, OWNER_ID)
    foreign = client.post(_complete_url(wishlist_id, item_id, reservation_id), headers=headers)
    missing = client.post(_complete_url(wishlist_id, item_id, 999999), headers=headers)
    assert foreign.status_code in {403, 404}
    assert (foreign.status_code, foreign.json()) == (missing.status_code, missing.json())
    rows = sql_rows(
        db_path_of(app), "SELECT status FROM wl_reservations WHERE id = ?", (reservation_id,)
    )
    assert rows == [{"status": "purchased"}]


def test_concurrent_completion_releases_units_only_once(env: AppEnv) -> None:
    """Competing requests yield one success and one refusal without duplicate mutation."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    client, sessions, app = env
    wishlist_id, item_id, reservation_id, other_id = _seed(app)
    url = _complete_url(wishlist_id, item_id, reservation_id)
    headers = bearer(sessions, GIFTER_ID)
    ready = Barrier(2, timeout=5)

    def attempt() -> int:
        ready.wait(timeout=5)
        return int(client.post(url, headers=headers).status_code)

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = sorted(executor.map(lambda _: attempt(), range(2)))
    assert statuses[0] == 200
    assert statuses[1] in {409, 503}
    rows = sql_rows(
        db_path_of(app),
        "SELECT id, status FROM wl_reservations WHERE wish_item_id = ? ORDER BY id",
        (item_id,),
    )
    assert rows == [
        {"id": reservation_id, "status": "completed"},
        {"id": other_id, "status": "active"},
    ]


async def test_queued_gift_notice_is_not_sent_for_completed_promise(tmp_path: Path) -> None:
    """The receipt worker must recheck entitlement after an already queued notice."""
    from tests.notice_support import FakeNoticeSender
    from tests.receipt_support import sql_exec
    from tests.test_receipt_notices import _base, _store_env

    async with _store_env(tmp_path) as notice_env:
        await notice_env.seed(2, ((GIFTER, 1),))
        await notice_env.receive(2)
        rows = notice_env.rows_for(GIFTER_ID)
        assert len(rows) == 1
        assert rows[0]["status"] == "pending"
        # Isolate the delivery authorization rule from the missing completion endpoint.
        sql_exec(
            notice_env.db,
            "UPDATE wl_reservations SET status = 'completed' WHERE user_id = ?",
            (GIFTER_ID,),
        )
        sender = FakeNoticeSender()
        await notice_env.worker(sender).run_once(_base())
        assert sender.calls == []


async def test_queued_undo_notice_is_not_sent_for_completed_promise(tmp_path: Path) -> None:
    """The service-reminder queue also rechecks entitlement at delivery time."""
    from tests.notice_support import FakeNoticeSender
    from tests.receipt_support import receipt_rows, sql_exec
    from tests.test_receipt_notices import _base, _store_env

    async with _store_env(tmp_path) as notice_env:
        await notice_env.seed(2, ((GIFTER, 1), (OTHER_GIFTER, 1)))
        await notice_env.receive(2)
        receipt_id = receipt_rows(notice_env.db)[-1]["id"]

        async def correct(service: WishlistService) -> None:
            await service.correct_item_receipt(
                notice_env.item_id,
                receipt_id,
                OWNER,
                1,
                wishlist_id=notice_env.wishlist_id,
            )

        await notice_env.store.execute_wish(correct, item_id=notice_env.item_id)
        rows = sql_rows(
            notice_env.db,
            "SELECT user_id, status FROM reminder_outbox WHERE kind = 'receipt_reverted' "
            "AND user_id IN (?, ?) ORDER BY user_id",
            (GIFTER_ID, OTHER_GIFTER_ID),
        )
        assert rows == [
            {"user_id": GIFTER_ID, "status": "pending"},
            {"user_id": OTHER_GIFTER_ID, "status": "pending"},
        ]
        sql_exec(notice_env.db, "DELETE FROM notification_outbox")
        sql_exec(
            notice_env.db,
            "UPDATE wl_reservations SET status = 'completed' WHERE user_id = ?",
            (GIFTER_ID,),
        )
        sender = FakeNoticeSender()
        await notice_env.worker(sender).run_once(_base())
        rows = sql_rows(
            notice_env.db,
            "SELECT user_id, status FROM reminder_outbox WHERE kind = 'receipt_reverted' "
            "AND user_id IN (?, ?) ORDER BY user_id",
            (GIFTER_ID, OTHER_GIFTER_ID),
        )
        assert rows == [
            {"user_id": GIFTER_ID, "status": "skipped"},
            {"user_id": OTHER_GIFTER_ID, "status": "sent"},
        ]
        assert len(sender.calls) == 1
        assert sender.calls[0][0] == OTHER_GIFTER_ID
