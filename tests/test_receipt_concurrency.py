"""Red tests for racing receipts (WISHENKA-23, R-1.7).

Same-process and spawned-process races over ``execute_wish``. Received never exceeds
requested, the loser gets a closed refusal and the history equals the counter.
"""

from __future__ import annotations

import asyncio
import logging
import multiprocessing
import queue
import time
from pathlib import Path
from typing import Any

import pytest

from tests.receipt_support import (
    CO_AUTHOR,
    CO_AUTHOR_ID,
    GIFTER,
    OTHER_GIFTER,
    OWNER,
    OWNER_ID,
    app_env,
    bearer,
    exc_class,
    item_received,
    open_store,
    receipt_rows,
    seed_wish,
    sql_exec,
    sql_rows,
)
from wishenka.auth.models import AuthenticatedUser
from wishenka.wishlists.exceptions import InsufficientQuantityError, InventoryBusyError
from wishenka.wishlists.models import ReservationStatus, WishlistRole
from wishenka.wishlists.service import WishlistService
from wishenka.wishlists.store import WishlistStore

pytestmark = pytest.mark.timeout(120)

_BARRIER_TIMEOUT = 20
_JOIN_TIMEOUT = 25
_DRAIN_TIMEOUT = 5
_REFUSALS = ("NothingRemainingError", "QuantityAboveRemainingError")


async def _seed(db: Path, quantity: int, promised: int = 0) -> int:
    async with open_store(db) as store:
        sql_exec(
            db,
            "INSERT OR IGNORE INTO users (telegram_id, first_name, created_at, updated_at) "
            "VALUES (?, ?, '2026-01-01', '2026-01-01')",
            (CO_AUTHOR_ID, "Carl"),
        )

        async def setup(service: WishlistService) -> int:
            wishlist_id, item_id = await seed_wish(service, quantity=quantity)
            await service.add_member(wishlist_id, OWNER, CO_AUTHOR_ID, WishlistRole.ADMIN)
            if promised:
                await service.create_reservation(item_id=item_id, user=GIFTER, quantity=promised)
            return item_id

        return await store.execute(setup)


async def _receive(
    store: WishlistStore, item_id: int, actor: AuthenticatedUser, quantity: int
) -> dict[str, Any]:
    async def act(service: WishlistService) -> None:
        await service.record_item_fulfillment(item_id, actor, quantity)

    try:
        await store.execute_wish(act, item_id=item_id, operation_name="record_item_fulfillment")
    except Exception as exc:
        return {"status": "error", "error_type": type(exc).__name__}
    return {"status": "ok"}


def _assert_one_winner(results: list[dict[str, Any]]) -> None:
    refusals = [r for r in results if r["status"] == "error"]
    assert [r["status"] for r in results].count("ok") == 1, results
    assert len(refusals) == 1, results
    assert refusals[0]["error_type"] in {exc_class(name).__name__ for name in _REFUSALS}, results


def _assert_consistent(db: Path, item_id: int, quantity: int, received: int) -> None:
    assert item_received(db, item_id) == received <= quantity
    rows = receipt_rows(db)
    assert sum(int(row["quantity"]) for row in rows) == received


async def test_two_receipts_race_same_process(tmp_path: Path) -> None:
    """Two authors take the last unit through one store: one wins, the other is refused."""
    db = tmp_path / "race.db"
    item_id = await _seed(db, 1)
    async with open_store(db) as store:
        results = await asyncio.gather(
            _receive(store, item_id, OWNER, 1), _receive(store, item_id, CO_AUTHOR, 1)
        )

    _assert_one_winner(list(results))
    _assert_consistent(db, item_id, 1, 1)


async def _receive_in_process(db: str, item_id: int, user_id: int) -> dict[str, Any]:
    store = WishlistStore(f"sqlite+aiosqlite:///{db}")
    try:
        actor = AuthenticatedUser(telegram_id=user_id, first_name="A", auth_method="session_token")
        return await _receive(store, item_id, actor, 1)
    finally:
        await store.engine.dispose()


def _worker(db: str, item_id: int, user_id: int, results: Any, barrier: Any) -> None:
    try:
        barrier.wait(timeout=_BARRIER_TIMEOUT)
        results.put(asyncio.run(_receive_in_process(db, item_id, user_id)))
    except Exception as exc:
        results.put({"status": "error", "error_type": type(exc).__name__})


async def test_two_receipts_race_spawned_processes(tmp_path: Path) -> None:
    """Two processes race for the last unit: one winner, history equals the counter."""
    db = tmp_path / "spawn.db"
    item_id = await _seed(db, 1)
    ctx = multiprocessing.get_context("spawn")
    barrier = ctx.Barrier(2)
    results_queue = ctx.Queue()
    procs = [
        ctx.Process(target=_worker, args=(str(db), item_id, user_id, results_queue, barrier))
        for user_id in (OWNER_ID, CO_AUTHOR_ID)
    ]
    for proc in procs:
        proc.start()
    payloads: list[dict[str, Any]] = []
    try:
        for proc in procs:
            proc.join(timeout=_JOIN_TIMEOUT)
        deadline = time.monotonic() + _DRAIN_TIMEOUT
        while len(payloads) < 2 and time.monotonic() < deadline:
            try:
                payloads.append(results_queue.get(timeout=0.2))
            except queue.Empty:
                break
    finally:
        for proc in procs:
            if proc.is_alive():
                proc.terminate()
                proc.join(timeout=5)

    assert len(payloads) == 2, payloads
    _assert_one_winner(payloads)
    _assert_consistent(db, item_id, 1, 1)


async def test_receipt_vs_promise_race(tmp_path: Path) -> None:
    """A receipt racing a promise never breaks the counters or loses the open promise."""
    db = tmp_path / "promise.db"
    item_id = await _seed(db, 2, promised=1)
    async with open_store(db) as store:

        async def promise(service: WishlistService) -> None:
            await service.create_reservation(item_id=item_id, user=OTHER_GIFTER, quantity=1)

        async def raced_promise() -> dict[str, Any]:
            try:
                await store.execute_wish(
                    promise, item_id=item_id, operation_name="create_reservation"
                )
            except InsufficientQuantityError as exc:
                return {"status": "error", "error_type": type(exc).__name__}
            return {"status": "ok"}

        receipt, booking = await asyncio.gather(_receive(store, item_id, OWNER, 1), raced_promise())

    assert receipt["status"] == "ok", receipt
    assert booking["status"] in {"ok", "error"}
    _assert_consistent(db, item_id, 2, 1)
    open_rows = sql_rows(
        db,
        "SELECT user_id, status FROM wl_reservations WHERE status IN (?, ?) ORDER BY user_id",
        (ReservationStatus.ACTIVE.value, ReservationStatus.PURCHASED.value),
    )
    expected = [GIFTER.telegram_id] + (
        [OTHER_GIFTER.telegram_id] if booking["status"] == "ok" else []
    )
    assert [row["user_id"] for row in open_rows] == expected


def test_cc13_busy_503_bounded_and_identical_with_or_without_reservations(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CC-13: bounded 503 busy response and logs are identical with 0 or active reservations."""
    with app_env(tmp_path) as (client, sessions, app):
        service: WishlistService = app.state.domain_service
        wl_empty, item_empty = asyncio.run(seed_wish(service, quantity=5))
        wl_booked, item_booked = asyncio.run(seed_wish(service, quantity=5))
        asyncio.run(service.create_reservation(item_id=item_booked, user=GIFTER, quantity=2))
        owner = bearer(sessions, OWNER_ID)

        async def busy(*_args: object, **_kwargs: object) -> None:
            raise InventoryBusyError()

        monkeypatch.setattr(app.state.wishlist_store, "execute_wish", busy)
        caplog.set_level(logging.INFO)
        resp_empty = client.post(
            f"/api/wishlists/{wl_empty}/items/{item_empty}/receipts",
            json={"quantity": 1},
            headers=owner,
        )
        resp_booked = client.post(
            f"/api/wishlists/{wl_booked}/items/{item_booked}/receipts",
            json={"quantity": 1},
            headers=owner,
        )

    assert resp_empty.status_code == 503
    assert resp_booked.status_code == 503
    assert resp_empty.json() == resp_booked.json()
    assert resp_empty.headers["content-type"] == resp_booked.headers["content-type"]
    assert "Greta" not in resp_booked.text
    busy_logs = [r for r in caplog.records if getattr(r, "event", None) == "receipt_inventory_busy"]
    assert len(busy_logs) == 2
    assert [r.levelno for r in busy_logs] == [logging.WARNING, logging.WARNING]
    standard = set(logging.LogRecord("n", 0, "p", 0, "m", (), None).__dict__) | {
        "message",
        "asctime",
    }
    for record, wid, iid in (
        (busy_logs[0], wl_empty, item_empty),
        (busy_logs[1], wl_booked, item_booked),
    ):
        extras = {k: v for k, v in record.__dict__.items() if k not in standard}
        assert extras == {
            "event": "receipt_inventory_busy",
            "operation": "record_receipt",
            "wishlist_id": wid,
            "item_id": iid,
            "actor_id": OWNER_ID,
        }
