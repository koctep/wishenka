"""Observability checks for WISHENKA-219 completion, fencing, suppression, and operator."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import pytest

from tests.receipt_support import (
    GIFTER_ID,
    OWNER_ID,
    app_env,
    bearer,
    db_path_of,
    sql_exec,
    sql_rows,
)
from tests.test_wishenka_219_repro import _complete_url, _seed
from wishenka.auth.models import AuthenticatedUser
from wishenka.notices.fence import (
    begin_attempt,
    defer_claim,
    delivery_lock,
    finish_attempt,
    resolve_attempt,
)
from wishenka.notices.operator import resolve as operator_resolve
from wishenka.wishlists.exceptions import (
    InventoryBusyError,
    ReservationError,
    ReservationNotFoundError,
)
from wishenka.wishlists.service import WishlistService

pytestmark = pytest.mark.timeout(60)


def _events(records: list[logging.LogRecord], event: str) -> list[logging.LogRecord]:
    return [r for r in records if getattr(r, "event", None) == event]


def _gift_notice_id(db_path: str | Path, item_id: int) -> int:
    rows = sql_rows(
        db_path,
        "SELECT id FROM notification_outbox WHERE wish_item_id=? AND giver_user_id=? "
        "ORDER BY id DESC LIMIT 1",
        (item_id, GIFTER_ID),
    )
    assert rows
    return int(rows[0]["id"])


def test_completion_and_suppression_logs(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Completing a purchased promise logs completion and queued notice suppression."""
    with app_env(tmp_path, name="obs_complete.db") as (client, sessions, app):
        wishlist, item, reservation, _ = _seed(app)
        assert _gift_notice_id(db_path_of(app), item) > 0
        caplog.set_level(logging.INFO)
        caplog.clear()

        response = client.post(
            _complete_url(wishlist, item, reservation),
            headers=bearer(sessions, GIFTER_ID),
        )
        assert response.status_code == 200

    completed = _events(caplog.records, "reservation_completed")
    assert len(completed) == 1
    assert completed[0].levelno == logging.INFO
    assert getattr(completed[0], "reservation_id", None) == reservation
    assert getattr(completed[0], "item_id", None) == item

    suppressed = _events(caplog.records, "receipt_notices_suppressed")
    assert len(suppressed) == 1
    assert suppressed[0].levelno == logging.INFO
    assert getattr(suppressed[0], "gift_skipped", None) == 1


def test_completion_refusal_and_fence_block_logs(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Invalid state, missing reservation, and active fence/lock emit structured WARNING logs."""
    with app_env(tmp_path, name="obs_refuse.db") as (client, sessions, app):
        wishlist, item, reservation, _ = _seed(app, purchased=False)
        store = app.state.wishlist_store
        svc: WishlistService = app.state.domain_service
        gifter = AuthenticatedUser(telegram_id=GIFTER_ID, first_name="Gifter")
        owner = AuthenticatedUser(telegram_id=OWNER_ID, first_name="Owner")
        caplog.set_level(logging.WARNING)
        caplog.clear()

        with pytest.raises(ReservationError):
            asyncio.run(
                svc.complete_reservation(reservation, gifter, wishlist_id=wishlist, item_id=item)
            )
        with pytest.raises(ReservationNotFoundError):
            asyncio.run(
                svc.complete_reservation(reservation, owner, wishlist_id=wishlist, item_id=item)
            )

        sql_exec(
            db_path_of(app),
            "INSERT INTO receipt_delivery_fence VALUES (?,?,?,?,?,?)",
            (item, GIFTER_ID, "attempt-1", "gift", 1, "in_flight"),
        )
        resp_fence = client.post(
            _complete_url(wishlist, item, reservation),
            headers=bearer(sessions, GIFTER_ID),
        )
        assert resp_fence.status_code == 503

        with pytest.raises(InventoryBusyError):
            asyncio.run(
                svc.complete_reservation(reservation, gifter, wishlist_id=wishlist, item_id=item)
            )

        async def _check_lock_busy() -> None:
            async with delivery_lock(store.database_url, item, GIFTER_ID):
                with pytest.raises(InventoryBusyError):
                    await svc.complete_reservation(
                        reservation, gifter, wishlist_id=wishlist, item_id=item
                    )

        asyncio.run(_check_lock_busy())

    assert len(_events(caplog.records, "invalid_reservation_transition")) == 1
    assert len(_events(caplog.records, "reservation_not_found")) == 1
    fence_blocks = _events(caplog.records, "reservation_complete_fence_blocked")
    assert len(fence_blocks) == 2
    route_block = next(r for r in fence_blocks if r.name == "wishenka.web.reservations")
    assert not hasattr(route_block, "actor_id")
    assert len(_events(caplog.records, "reservation_complete_lock_busy")) == 1


def test_fence_lifecycle_and_operator_resolve_logs(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Fence begin/finish/defer/resolve and operator resolve emit structured audit logs."""
    with app_env(tmp_path, name="obs_fence.db") as (_, _, app):
        _, item, _, _ = _seed(app)
        row_id = _gift_notice_id(db_path_of(app), item)
        sql_exec(
            db_path_of(app),
            "UPDATE notification_outbox SET status='sending', claim_token='tok-1' WHERE id=?",
            (row_id,),
        )
        store = app.state.wishlist_store
        caplog.set_level(logging.DEBUG)
        caplog.clear()

        async def _exercise() -> None:
            assert await begin_attempt(store, (item, GIFTER_ID), "gift", row_id, "tok-1")
            assert not await begin_attempt(store, (item, GIFTER_ID), "gift", row_id, "tok-1")
            await finish_attempt(store, (item, GIFTER_ID), "tok-1", definitive=False)
            assert await resolve_attempt(
                store,
                item,
                GIFTER_ID,
                operator="ops-user",
                evidence="confirmed not delivered",
            )
            assert await defer_claim(store, "gift", row_id, "tok-1", 1000)

        asyncio.run(_exercise())

        sql_exec(
            db_path_of(app),
            "UPDATE notification_outbox SET status='uncertain', claim_token='tok-2' WHERE id=?",
            (row_id,),
        )
        assert asyncio.run(
            operator_resolve(
                store, "receipt", row_id, "fail", 2000, operator="ops-user", evidence="final"
            )
        )
        assert not asyncio.run(
            operator_resolve(
                store, "receipt", row_id, "fail", 2001, operator="ops-user", evidence="final"
            )
        )

    assert len(_events(caplog.records, "receipt_fence_recorded")) == 1
    assert len(_events(caplog.records, "receipt_fence_busy")) == 1
    assert len(_events(caplog.records, "receipt_fence_uncertain")) == 1
    assert _events(caplog.records, "receipt_fence_uncertain")[0].levelno == logging.WARNING
    assert len(_events(caplog.records, "receipt_fence_resolved")) == 1
    assert _events(caplog.records, "receipt_fence_resolved")[0].levelno == logging.INFO
    assert len(_events(caplog.records, "receipt_claim_deferred")) == 1
    assert len(_events(caplog.records, "operator_notice_resolved")) == 1
    assert len(_events(caplog.records, "operator_notice_resolve_noop")) == 1


async def test_worker_deferral_logs_debug_only_on_notice_logger(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Busy delivery lock defers gift notice at DEBUG without INFO+ noise on notice logger."""
    from tests.notice_support import FakeNoticeSender
    from tests.receipt_support import GIFTER
    from tests.test_receipt_notices import _base, _store_env

    async with _store_env(tmp_path) as env:
        await env.seed(1, ((GIFTER, 1),))
        await env.receive(1)
        worker = env.worker(FakeNoticeSender())
        caplog.set_level(logging.DEBUG)
        caplog.clear()

        async with delivery_lock(env.store.database_url, env.item_id, GIFTER_ID):
            await worker.run_once(_base())

    deferred = _events(caplog.records, "receipt_notice_deferred")
    assert len(deferred) == 1
    assert deferred[0].levelno == logging.DEBUG
    assert getattr(deferred[0], "reason", None) == "lock_busy"
    loud_notice_logs = [
        r
        for r in caplog.records
        if r.name == "wishenka.wishlists.notices" and r.levelno >= logging.INFO
    ]
    assert loud_notice_logs == []
