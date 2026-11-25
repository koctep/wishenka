"""Failing reproduction tests for WISHENKA-218 (FR-5 / Q12).

Verifies that wish quantity editing never exposes or enforces a floor based on
occupied giver promises, allows reductions down to ``max(1, received_quantity)``,
rejects reductions below ``received_quantity`` without leaking booking data,
preserves existing promises in the over-booked state, and queues
``item_quantity_overbooked`` notifications for open-promise givers.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from wishenka.auth.models import AuthenticatedUser, TelegramUser
from wishenka.auth.session import SessionTokenService
from wishenka.config import Settings
from wishenka.users.store import UserStore
from wishenka.web.app import create_app
from wishenka.wishlists.exceptions import (
    CannotReduceQuantityBelowReservedError,
    InsufficientQuantityError,
)
from wishenka.wishlists.models import ReservationStatus
from wishenka.wishlists.service import WishlistService
from wishenka.wishlists.store import WishlistStore

pytestmark = pytest.mark.timeout(30)


def _make_user(telegram_id: int, first_name: str, username: str | None = None) -> AuthenticatedUser:
    return AuthenticatedUser(
        telegram_id=telegram_id,
        first_name=first_name,
        username=username,
        auth_method="session_token",
    )


def _auth_headers(
    sessions: SessionTokenService,
    user_id: int,
    name: str = "User",
    *,
    lang: str = "en",
) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {sessions.create_token(user_id, name)}",
        "Accept-Language": lang,
    }


@pytest.fixture
def test_app(tmp_path: Path) -> Iterator[tuple[TestClient, SessionTokenService, FastAPI]]:
    """Initialize TestClient and SessionTokenService with an isolated SQLite DB."""
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'wishenka_218_repro.db'}",
        secret_key="wishenka-218-repro-secret",
    )
    app = create_app(settings)
    sessions = SessionTokenService(settings.secret_key)
    with TestClient(app) as client:
        yield client, sessions, app


async def _register_deliverable_users(db_url: str, users: list[AuthenticatedUser]) -> None:
    """Create user profiles and active bot_destinations rows without touching Telegram."""
    user_store = UserStore(db_url)
    try:
        for user in users:
            await user_store.upsert_user(
                TelegramUser(
                    id=user.telegram_id,
                    first_name=user.first_name,
                    language_code="en",
                )
            )
            async with user_store.engine.begin() as conn:
                await conn.execute(
                    text(
                        "INSERT OR REPLACE INTO bot_destinations "
                        "(user_id, chat_id, active) VALUES (:uid, :chat_id, 1)"
                    ),
                    {"uid": user.telegram_id, "chat_id": user.telegram_id},
                )
    finally:
        await user_store.engine.dispose()


async def _fetch_outbox_rows(db_url: str, item_id: int) -> list[tuple[str, int]]:
    """Read (kind, user_id) rows from reminder_outbox for a given item."""
    user_store = UserStore(db_url)
    try:
        async with user_store.engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT kind, user_id FROM reminder_outbox WHERE item_id = :item_id ORDER BY id"
                ),
                {"item_id": item_id},
            )
            return [(str(row[0]), int(row[1])) for row in result.fetchall()]
    finally:
        await user_store.engine.dispose()


def test_reduce_quantity_below_occupied_to_min_allowed_succeeds(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """Author can reduce quantity to max(1, received_quantity) despite open promises."""
    client, sessions, app = test_app
    service: WishlistService = app.state.domain_service
    owner = _make_user(1001, "Alice")
    gifter_a = _make_user(2001, "Bob")
    gifter_b = _make_user(2002, "Carol")

    async def setup() -> tuple[int, int, int]:
        wl = await service.create_wishlist(owner=owner, title="Birthday")
        item_zero_recv = await service.add_wish_item(
            wishlist_id=wl.id, actor=owner, title="Camera", quantity=5
        )
        res_a = await service.create_reservation(
            item_id=item_zero_recv.id, user=gifter_a, quantity=2
        )
        await service.mark_reservation_purchased(res_a.id, gifter_a)
        await service.create_reservation(item_id=item_zero_recv.id, user=gifter_b, quantity=2)

        item_with_recv = await service.add_wish_item(
            wishlist_id=wl.id, actor=owner, title="Lens", quantity=6
        )
        await service.record_item_fulfillment(item_with_recv.id, owner, 2)
        await service.create_reservation(item_id=item_with_recv.id, user=gifter_a, quantity=3)
        return wl.id, item_zero_recv.id, item_with_recv.id

    wl_id, item_zero_id, item_recv_id = asyncio.run(setup())
    headers = _auth_headers(sessions, owner.telegram_id, owner.first_name)

    resp_zero = client.patch(
        f"/api/wishlists/{wl_id}/items/{item_zero_id}",
        json={"quantity": 1},
        headers=headers,
    )
    assert resp_zero.status_code == 200, resp_zero.text
    assert resp_zero.json()["quantity"] == 1

    resp_recv = client.patch(
        f"/api/wishlists/{wl_id}/items/{item_recv_id}",
        json={"quantity": 2},
        headers=headers,
    )
    assert resp_recv.status_code == 200, resp_recv.text
    assert resp_recv.json()["quantity"] == 2


def test_reduce_quantity_below_received_rejected_without_booking_leak(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """Reducing below received_quantity fails and cites only received_quantity."""
    client, sessions, app = test_app
    service: WishlistService = app.state.domain_service
    owner = _make_user(1002, "Alice")
    gifter = _make_user(2003, "Bob")

    async def setup() -> tuple[int, int]:
        wl = await service.create_wishlist(owner=owner, title="Birthday")
        item = await service.add_wish_item(
            wishlist_id=wl.id, actor=owner, title="Tripod", quantity=6
        )
        await service.record_item_fulfillment(item.id, owner, 2)
        await service.create_reservation(item_id=item.id, user=gifter, quantity=3)
        return wl.id, item.id

    wl_id, item_id = asyncio.run(setup())

    with pytest.raises(CannotReduceQuantityBelowReservedError) as exc_info:
        asyncio.run(service.update_wish_item(item_id=item_id, actor=owner, quantity=1))

    err_msg = str(exc_info.value).lower()
    assert "2" in err_msg
    assert "5" not in err_msg
    assert "3" not in err_msg
    assert "locked" not in err_msg
    assert "reserved" not in err_msg

    headers = _auth_headers(sessions, owner.telegram_id, owner.first_name)
    api_resp = client.patch(
        f"/api/wishlists/{wl_id}/items/{item_id}",
        json={"quantity": 1},
        headers=headers,
    )
    assert api_resp.status_code == 409
    detail = str(api_resp.json()["detail"]).lower()
    assert "2" in detail
    assert "5" not in detail
    assert "locked" not in detail
    assert "reserved" not in detail


def test_edit_modal_and_responses_identical_with_or_without_promises(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """Edit modal HTML and PATCH/POST responses must not vary when promises exist."""
    client, sessions, app = test_app
    service: WishlistService = app.state.domain_service
    owner = _make_user(1003, "Alice")
    gifter = _make_user(2004, "Bob")

    async def setup() -> tuple[int, int, int]:
        wl = await service.create_wishlist(owner=owner, title="Privacy Check")
        plain_item = await service.add_wish_item(
            wishlist_id=wl.id, actor=owner, title="Same Mug", quantity=5
        )
        await service.record_item_fulfillment(plain_item.id, owner, 2)

        booked_item = await service.add_wish_item(
            wishlist_id=wl.id, actor=owner, title="Same Mug", quantity=5
        )
        await service.record_item_fulfillment(booked_item.id, owner, 2)
        await service.create_reservation(item_id=booked_item.id, user=gifter, quantity=3)
        return wl.id, plain_item.id, booked_item.id

    wl_id, plain_id, booked_id = asyncio.run(setup())
    headers = _auth_headers(sessions, owner.telegram_id, owner.first_name)

    modal_plain = client.get(f"/web/wishlists/{wl_id}/items/{plain_id}/edit", headers=headers)
    modal_booked = client.get(f"/web/wishlists/{wl_id}/items/{booked_id}/edit", headers=headers)
    assert modal_plain.status_code == 200
    assert modal_booked.status_code == 200

    # min attribute must reflect received_quantity (2), never received + reserved (5)
    assert 'min="2"' in modal_booked.text
    assert 'min="5"' not in modal_booked.text
    assert "alert-warning" not in modal_booked.text

    def _norm(html: str, item_id: int) -> str:
        html = re.sub(rf"/items/{item_id}/", "/items/{ID}/", html)
        return re.sub(rf"#item-card-{item_id}\b", "#item-card-{ID}", html)

    assert _norm(modal_plain.text, plain_id) == _norm(modal_booked.text, booked_id)

    # Rejected edit via HTMX POST must return identical 409 HTML for both wishes
    post_plain = client.post(
        f"/web/wishlists/{wl_id}/items/{plain_id}/edit",
        data={"title": "Same Mug", "quantity": "1"},
        headers=headers,
    )
    post_booked = client.post(
        f"/web/wishlists/{wl_id}/items/{booked_id}/edit",
        data={"title": "Same Mug", "quantity": "1"},
        headers=headers,
    )
    assert post_plain.status_code == 409
    assert post_booked.status_code == 409
    assert _norm(post_plain.text, plain_id) == _norm(post_booked.text, booked_id)

    # Valid reduction via API PATCH must return identical payloads (barring id/updated_at)
    patch_plain = client.patch(
        f"/api/wishlists/{wl_id}/items/{plain_id}",
        json={"quantity": 2},
        headers=headers,
    )
    patch_booked = client.patch(
        f"/api/wishlists/{wl_id}/items/{booked_id}",
        json={"quantity": 2},
        headers=headers,
    )
    assert patch_plain.status_code == 200
    assert patch_booked.status_code == 200
    body_plain = {
        k: v
        for k, v in patch_plain.json().items()
        if k not in {"id", "updated_at", "position", "display_order"}
    }
    body_booked = {
        k: v
        for k, v in patch_booked.json().items()
        if k not in {"id", "updated_at", "position", "display_order"}
    }
    assert body_plain == body_booked


def test_overbooked_state_preserves_promises_and_queues_notices(tmp_path: Path) -> None:
    """Over-booking keeps promises intact, blocks new/upward bookings, and queues notices."""
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'overbooked_notices.db'}"
    owner = _make_user(3001, "Alice")
    gifter_a = _make_user(3002, "Bob")
    gifter_b = _make_user(3003, "Carol")
    gifter_c = _make_user(3004, "Dave")

    async def scenario() -> None:
        store = WishlistStore(db_url)
        try:
            await store.initialize()
            await _register_deliverable_users(db_url, [owner, gifter_a, gifter_b, gifter_c])

            async def seed(svc: WishlistService) -> tuple[int, int, int]:
                wl = await svc.create_wishlist(owner=owner, title="Party")
                item = await svc.add_wish_item(
                    wishlist_id=wl.id, actor=owner, title="Chairs", quantity=6
                )
                await svc.record_item_fulfillment(item.id, owner, 1)
                res_a = await svc.create_reservation(item_id=item.id, user=gifter_a, quantity=2)
                res_b = await svc.create_reservation(item_id=item.id, user=gifter_b, quantity=2)
                await svc.mark_reservation_purchased(res_b.id, gifter_b)
                return item.id, res_a.id, res_b.id

            item_id, res_a_id, res_b_id = await store.execute(seed)

            # Non-conflicting reduction (1 + 4 <= 5): must NOT queue overbooked notice
            await store.execute_wish(
                lambda svc: svc.update_wish_item(item_id=item_id, actor=owner, quantity=5),
                item_id=item_id,
                operation_name="reduce_no_conflict",
            )
            rows_before = await _fetch_outbox_rows(db_url, item_id)
            assert all(kind != "item_quantity_overbooked" for kind, _ in rows_before)

            # Conflicting reduction (1 + 4 > 3): enters over-booked state & queues notices
            await store.execute_wish(
                lambda svc: svc.update_wish_item(item_id=item_id, actor=owner, quantity=3),
                item_id=item_id,
                operation_name="reduce_overbooked",
            )

            rows_after = await _fetch_outbox_rows(db_url, item_id)
            overbooked_targets = {
                uid for kind, uid in rows_after if kind == "item_quantity_overbooked"
            }
            assert overbooked_targets == {gifter_a.telegram_id, gifter_b.telegram_id}

            async def verify_overbooked_rules(svc: WishlistService) -> None:
                res_a = svc._reservations[res_a_id]
                res_b = svc._reservations[res_b_id]
                assert res_a.status == ReservationStatus.ACTIVE
                assert res_a.quantity == 2
                assert res_b.status == ReservationStatus.PURCHASED
                assert res_b.quantity == 2

                # New bookings and upward edits are blocked
                with pytest.raises(InsufficientQuantityError):
                    await svc.create_reservation(item_id=item_id, user=gifter_c, quantity=1)
                with pytest.raises(InsufficientQuantityError):
                    await svc.update_reservation_quantity(res_a_id, gifter_a, 3)

                # Downward edits and purchase-marks still succeed
                reduced = await svc.update_reservation_quantity(res_a_id, gifter_a, 1)
                assert reduced.quantity == 1
                purchased = await svc.mark_reservation_purchased(res_a_id, gifter_a)
                assert purchased.status == ReservationStatus.PURCHASED

            await store.execute(verify_overbooked_rules)
        finally:
            await store.engine.dispose()

    asyncio.run(scenario())


def test_editing_coauthor_with_open_promise_receives_overbooked_notice(tmp_path: Path) -> None:
    """An editor who is also a giver receives the same notice as other givers."""
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'coauthor_overbooked.db'}"
    owner = _make_user(3101, "Alice")
    editor = _make_user(3102, "Bob")
    other_giver = _make_user(3103, "Carol")

    async def scenario() -> None:
        store = WishlistStore(db_url)
        try:
            await store.initialize()
            await _register_deliverable_users(db_url, [owner, editor, other_giver])

            async def seed(svc: WishlistService) -> int:
                wl = await svc.create_wishlist(owner=owner, title="Party")
                await svc.add_member(wl.id, owner, editor.telegram_id)
                item = await svc.add_wish_item(
                    wishlist_id=wl.id,
                    actor=owner,
                    title="Chairs",
                    quantity=4,
                    recipient_user_id=owner.telegram_id,
                )
                await svc.create_reservation(item_id=item.id, user=editor, quantity=1)
                await svc.create_reservation(item_id=item.id, user=other_giver, quantity=2)
                return item.id

            item_id = await store.execute(seed)
            await store.execute_wish(
                lambda svc: svc.update_wish_item(item_id=item_id, actor=editor, quantity=2),
                item_id=item_id,
                operation_name="coauthor_reduce_overbooked",
            )
            rows = await _fetch_outbox_rows(db_url, item_id)
            targets = [uid for kind, uid in rows if kind == "item_quantity_overbooked"]
            assert sorted(targets) == sorted([editor.telegram_id, other_giver.telegram_id])
            assert ("item_updated", editor.telegram_id) not in rows
        finally:
            await store.engine.dispose()

    asyncio.run(scenario())
