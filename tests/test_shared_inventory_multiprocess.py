"""Cross-process shared inventory for WISHENKA-57.

Quantity races are guards: today's snapshot transaction already serializes them.
A write lock held past ``busy_timeout`` raises ``InventoryBusyError`` and leaves
the wish unchanged.
"""

from __future__ import annotations

import asyncio
import logging
import multiprocessing
import queue
import sqlite3
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.exc import OperationalError

from wishenka.auth.models import AuthenticatedUser
from wishenka.wishlists import exceptions as wishlist_exceptions
from wishenka.wishlists.exceptions import (
    InsufficientQuantityError,
    SelfReservationError,
    WishlistArchivedError,
    WishlistError,
)
from wishenka.wishlists.models import ReservationStatus
from wishenka.wishlists.service import WishlistService
from wishenka.wishlists.store import WishlistStore

pytestmark = pytest.mark.timeout(60)

_OWNER_ID = 1001
_OWNER_NAME = "OwnerAda"
_ADA_ID = 81001
_ADA_NAME = "GifterAda"
_BEA_ID = 82002
_BEA_NAME = "GifterBea"
_CARA_ID = 83003
_CARA_NAME = "GifterCara"
_OCCUPYING = {ReservationStatus.ACTIVE.value, ReservationStatus.PURCHASED.value}
_STORE_LOGGER = "wishenka.wishlists.store"


@dataclass(frozen=True)
class _ReservationRow:
    reservation_id: int
    user_id: int
    quantity: int
    status: str


@dataclass(frozen=True)
class _ItemBalance:
    item_id: int
    quantity: int
    received: int
    available: int
    reservations: tuple[_ReservationRow, ...]

    @property
    def occupied(self) -> int:
        return sum(row.quantity for row in self.reservations if row.status in _OCCUPYING)

    @property
    def free_remainder(self) -> int:
        return max(0, self.quantity - self.received - self.occupied)


def _actor(telegram_id: int, first_name: str) -> AuthenticatedUser:
    return AuthenticatedUser(telegram_id=telegram_id, first_name=first_name)


def _create(
    item_id: int, user_id: int, first_name: str, quantity: int
) -> tuple[str, dict[str, Any]]:
    return (
        "create",
        {
            "item_id": item_id,
            "user_id": user_id,
            "first_name": first_name,
            "quantity": quantity,
        },
    )


def _set_quantity(
    reservation_id: int, user_id: int, first_name: str, quantity: int
) -> tuple[str, dict[str, Any]]:
    return (
        "set_quantity",
        {
            "reservation_id": reservation_id,
            "user_id": user_id,
            "first_name": first_name,
            "quantity": quantity,
        },
    )


def _cancel(reservation_id: int, user_id: int, first_name: str) -> tuple[str, dict[str, Any]]:
    return (
        "cancel",
        {
            "reservation_id": reservation_id,
            "user_id": user_id,
            "first_name": first_name,
        },
    )


def _lower(
    item_id: int, user_id: int, first_name: str, quantity: int
) -> tuple[str, dict[str, Any]]:
    return (
        "lower",
        {
            "item_id": item_id,
            "user_id": user_id,
            "first_name": first_name,
            "quantity": quantity,
        },
    )


def _receipt(
    item_id: int, user_id: int, first_name: str, received_quantity: int
) -> tuple[str, dict[str, Any]]:
    return (
        "receipt",
        {
            "item_id": item_id,
            "user_id": user_id,
            "first_name": first_name,
            "received_quantity": received_quantity,
        },
    )


async def _apply(service: WishlistService, op: str, payload: dict[str, Any]) -> dict[str, Any]:
    user = _actor(int(payload["user_id"]), str(payload["first_name"]))
    if op == "create":
        reservation = await service.create_reservation(
            item_id=int(payload["item_id"]),
            user=user,
            quantity=int(payload["quantity"]),
        )
        return {
            "reservation_id": reservation.id,
            "quantity": reservation.quantity,
            "res_status": reservation.status.value,
        }
    if op == "set_quantity":
        reservation = await service.update_reservation_quantity(
            reservation_id=int(payload["reservation_id"]),
            user=user,
            new_quantity=int(payload["quantity"]),
        )
        return {
            "reservation_id": reservation.id,
            "quantity": reservation.quantity,
            "res_status": reservation.status.value,
        }
    if op == "cancel":
        reservation = await service.cancel_reservation(
            reservation_id=int(payload["reservation_id"]),
            user=user,
        )
        return {
            "reservation_id": reservation.id,
            "quantity": reservation.quantity,
            "res_status": reservation.status.value,
        }
    if op == "lower":
        item = await service.update_wish_item(
            item_id=int(payload["item_id"]),
            actor=user,
            quantity=int(payload["quantity"]),
        )
        return {"quantity": item.quantity, "received": item.received_quantity}
    if op == "receipt":
        item = await service.record_item_fulfillment(
            item_id=int(payload["item_id"]),
            actor=user,
            received_quantity=int(payload["received_quantity"]),
        )
        return {"quantity": item.quantity, "received": item.received_quantity}
    raise AssertionError(f"unknown inventory op {op}")


def _error_result(op: str, payload: dict[str, Any], exc: BaseException) -> dict[str, Any]:
    return {
        "status": "error",
        "op": op,
        "user_id": payload.get("user_id"),
        "first_name": payload.get("first_name"),
        "error_type": type(exc).__name__,
        "message": str(exc),
    }


async def _run_op(db_path: str, op: str, payload: dict[str, Any]) -> dict[str, Any]:
    store = WishlistStore(f"sqlite+aiosqlite:///{db_path}")
    try:
        body = await store.execute(lambda service: _apply(service, op, payload))
    finally:
        await store.engine.dispose()
    return {
        "status": "ok",
        "op": op,
        "user_id": payload.get("user_id"),
        "first_name": payload.get("first_name"),
        **body,
    }


def _worker(
    db_path: str,
    op: str,
    payload: dict[str, Any],
    results: Any,
    barrier: Any,
) -> None:
    """Run one inventory change in its own process and engine."""
    try:
        if barrier is not None:
            barrier.wait(timeout=20)
        results.put(asyncio.run(_run_op(db_path, op, payload)))
    except Exception as exc:
        results.put(_error_result(op, payload, exc))


def _hold_write_lock(db_path: str, started: Any, release: Any, errors: Any) -> None:
    """Reserve the database file until the caller finishes the busy attempt."""
    conn = sqlite3.connect(db_path, isolation_level=None, timeout=5)
    try:
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("BEGIN IMMEDIATE")
        started.set()
        release.wait(timeout=30)
        conn.rollback()
    except Exception as exc:
        errors.put(f"{type(exc).__name__}: {exc}")
        raise
    finally:
        conn.close()


def _queue_dump(errors: Any) -> str:
    parts: list[str] = []
    while True:
        try:
            parts.append(str(errors.get_nowait()))
        except queue.Empty:
            break
    return "; ".join(parts) or "holder produced no error"


def _run_copies(db_path: Path, calls: list[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
    """Open one WishlistStore per call, each in its own process, on one file."""
    ctx = multiprocessing.get_context("spawn")
    barrier = ctx.Barrier(len(calls)) if len(calls) > 1 else None
    results_queue = ctx.Queue()
    procs = [
        ctx.Process(target=_worker, args=(str(db_path), op, payload, results_queue, barrier))
        for op, payload in calls
    ]
    for proc in procs:
        proc.start()
    outcomes: list[dict[str, Any]] = []
    try:
        for proc in procs:
            proc.join(timeout=25)
        deadline = time.monotonic() + 5
        while len(outcomes) < len(calls) and time.monotonic() < deadline:
            try:
                outcomes.append(results_queue.get(timeout=0.2))
            except queue.Empty:
                break
    finally:
        for proc in procs:
            if proc.is_alive():
                proc.terminate()
                proc.join(timeout=5)
    exits = [proc.exitcode for proc in procs]
    assert len(outcomes) == len(calls), f"exits={exits} outcomes={outcomes}"
    assert all(code == 0 for code in exits), f"exits={exits} outcomes={outcomes}"
    return outcomes


async def _execute[T](
    db_path: Path,
    operation: Callable[[WishlistService], Awaitable[T]],
    *,
    initialize: bool = False,
) -> T:
    store = WishlistStore(f"sqlite+aiosqlite:///{db_path}")
    try:
        if initialize:
            await store.initialize()
        return await store.execute(operation)
    finally:
        await store.engine.dispose()


async def _run_on_store[T](
    db_path: Path,
    call: Callable[[WishlistService], Awaitable[T]],
) -> T:
    """Call a store-backed service so inventory methods use the wish transaction."""
    store = WishlistStore(f"sqlite+aiosqlite:///{db_path}")
    try:
        return await call(WishlistService(store=store))
    finally:
        await store.engine.dispose()


def _capability_tokens(db_path: Path) -> list[str]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT public_token, invite_token FROM wl_lists").fetchall()
    return [str(value) for row in rows for value in row if value]


def _record_blob(record: logging.LogRecord) -> str:
    parts = [record.getMessage()]
    for key, value in record.__dict__.items():
        if key.startswith("_"):
            continue
        parts.append(f"{key}={value}")
    return " ".join(parts)


async def _seed_wishlist(db_path: Path, quantities: list[int]) -> tuple[int, list[int]]:
    owner = _actor(_OWNER_ID, _OWNER_NAME)

    async def setup(service: WishlistService) -> tuple[int, list[int]]:
        wishlist = await service.create_wishlist(owner=owner, title="Shared inventory")
        item_ids: list[int] = []
        for index, quantity in enumerate(quantities):
            item = await service.add_wish_item(
                wishlist_id=wishlist.id,
                actor=owner,
                title=f"Wish {index}",
                quantity=quantity,
            )
            item_ids.append(item.id)
        return wishlist.id, item_ids

    return await _execute(db_path, setup, initialize=True)


async def _seed_reservation(
    db_path: Path, item_id: int, user_id: int, first_name: str, quantity: int
) -> int:
    async def book(service: WishlistService) -> int:
        reservation = await service.create_reservation(
            item_id=item_id,
            user=_actor(user_id, first_name),
            quantity=quantity,
        )
        return reservation.id

    return await _execute(db_path, book)


async def _load(db_path: Path, item_id: int) -> _ItemBalance:
    async def read(service: WishlistService) -> _ItemBalance:
        item = service._items.get(item_id)
        assert item is not None, f"wish {item_id} was deleted"
        rows = tuple(
            sorted(
                (
                    _ReservationRow(
                        reservation_id=reservation.id,
                        user_id=reservation.user_id,
                        quantity=reservation.quantity,
                        status=reservation.status.value,
                    )
                    for reservation in item.reservations
                ),
                key=lambda row: row.reservation_id,
            )
        )
        return _ItemBalance(
            item_id=item.id,
            quantity=item.quantity,
            received=item.received_quantity,
            available=item.available_quantity,
            reservations=rows,
        )

    return await _execute(db_path, read)


def _assert_consistent(balance: _ItemBalance) -> None:
    assert balance.available == balance.free_remainder
    assert balance.available >= 0


def _assert_no_gifter(message: str, user_id: int, first_name: str) -> None:
    assert str(user_id) not in message
    assert first_name not in message


def _assert_single_winner(results: list[dict[str, Any]]) -> dict[str, Any]:
    wins = [row for row in results if row["status"] == "ok"]
    losses = [row for row in results if row["status"] == "error"]
    assert len(wins) == 1, results
    assert len(losses) == len(results) - 1, results
    winner = wins[0]
    for loser in losses:
        assert loser["error_type"] == "InsufficientQuantityError", loser
        message = str(loser["message"])
        _assert_no_gifter(message, int(winner["user_id"]), str(winner["first_name"]))
    return winner


async def test_last_free_units_one_success_across_processes(tmp_path: Path) -> None:
    """Exactly one copy takes the last unit. The loser names no other gifter."""
    db_path = tmp_path / "last-unit.db"
    _wishlist_id, item_ids = await _seed_wishlist(db_path, [1])
    item_id = item_ids[0]

    results = _run_copies(
        db_path,
        [
            _create(item_id, _ADA_ID, _ADA_NAME, 1),
            _create(item_id, _BEA_ID, _BEA_NAME, 1),
        ],
    )
    _assert_single_winner(results)
    balance = await _load(db_path, item_id)
    _assert_consistent(balance)
    assert balance.occupied == 1
    assert balance.free_remainder == 0
    assert len(balance.reservations) == 1


async def test_increase_refused_leaves_earlier_promise(tmp_path: Path) -> None:
    """An increase that loses the last unit does not change the earlier promise."""
    db_path = tmp_path / "increase.db"
    _wishlist_id, item_ids = await _seed_wishlist(db_path, [2])
    item_id = item_ids[0]
    reservation_id = await _seed_reservation(db_path, item_id, _ADA_ID, _ADA_NAME, 1)

    results = _run_copies(
        db_path,
        [
            _set_quantity(reservation_id, _ADA_ID, _ADA_NAME, 2),
            _create(item_id, _BEA_ID, _BEA_NAME, 1),
        ],
    )
    winner = _assert_single_winner(results)
    balance = await _load(db_path, item_id)
    _assert_consistent(balance)
    assert balance.occupied == 2
    assert balance.free_remainder == 0
    ada_rows = [row for row in balance.reservations if row.user_id == _ADA_ID]
    assert len(ada_rows) == 1
    if winner["user_id"] != _ADA_ID:
        assert ada_rows[0].quantity == 1
        assert ada_rows[0].reservation_id == reservation_id
    else:
        assert ada_rows[0].quantity == 2


async def test_cancel_releases_units_once(tmp_path: Path) -> None:
    """A cancel overlapping two creates frees the unit once and keeps the wish."""
    db_path = tmp_path / "cancel.db"
    _wishlist_id, item_ids = await _seed_wishlist(db_path, [1])
    item_id = item_ids[0]
    reservation_id = await _seed_reservation(db_path, item_id, _ADA_ID, _ADA_NAME, 1)

    results = _run_copies(
        db_path,
        [
            _cancel(reservation_id, _ADA_ID, _ADA_NAME),
            _create(item_id, _BEA_ID, _BEA_NAME, 1),
            _create(item_id, _CARA_ID, _CARA_NAME, 1),
        ],
    )
    cancel = next(row for row in results if row["op"] == "cancel")
    assert cancel["status"] == "ok", cancel
    creates = [row for row in results if row["op"] == "create"]
    assert len([row for row in creates if row["status"] == "ok"]) <= 1
    for row in creates:
        if row["status"] == "error":
            assert row["error_type"] == "InsufficientQuantityError", row
            _assert_no_gifter(str(row["message"]), _ADA_ID, _ADA_NAME)

    balance = await _load(db_path, item_id)
    _assert_consistent(balance)
    assert balance.quantity == 1
    assert balance.received == 0
    assert balance.occupied <= 1
    ada_rows = [row for row in balance.reservations if row.user_id == _ADA_ID]
    assert len(ada_rows) == 1
    assert ada_rows[0].status == ReservationStatus.CANCELLED.value
    active_others = [
        row for row in balance.reservations if row.user_id != _ADA_ID and row.status in _OCCUPYING
    ]
    assert len(active_others) <= 1
    assert balance.occupied + balance.free_remainder == 1


async def test_smaller_quantity_releases_units_once(tmp_path: Path) -> None:
    """A smaller promise overlapping two creates returns the freed unit once."""
    db_path = tmp_path / "decrease.db"
    _wishlist_id, item_ids = await _seed_wishlist(db_path, [2])
    item_id = item_ids[0]
    reservation_id = await _seed_reservation(db_path, item_id, _ADA_ID, _ADA_NAME, 2)

    results = _run_copies(
        db_path,
        [
            _set_quantity(reservation_id, _ADA_ID, _ADA_NAME, 1),
            _create(item_id, _BEA_ID, _BEA_NAME, 1),
            _create(item_id, _CARA_ID, _CARA_NAME, 1),
        ],
    )
    decreased = next(row for row in results if row["op"] == "set_quantity")
    assert decreased["status"] == "ok", decreased
    creates = [row for row in results if row["op"] == "create"]
    assert len([row for row in creates if row["status"] == "ok"]) <= 1
    for row in creates:
        if row["status"] == "error":
            assert row["error_type"] == "InsufficientQuantityError", row

    balance = await _load(db_path, item_id)
    _assert_consistent(balance)
    assert balance.quantity == 2
    assert balance.received == 0
    ada_rows = [row for row in balance.reservations if row.user_id == _ADA_ID]
    assert len(ada_rows) == 1
    assert ada_rows[0].quantity == 1
    assert ada_rows[0].status == ReservationStatus.ACTIVE.value
    active_others = [
        row for row in balance.reservations if row.user_id != _ADA_ID and row.status in _OCCUPYING
    ]
    assert len(active_others) <= 1
    assert balance.occupied <= 2
    assert balance.occupied + balance.free_remainder == 2


async def test_lower_requested_quantity_sees_other_process_booking(tmp_path: Path) -> None:
    """A lower that would pass under occupied units keeps the previous quantity."""
    db_path = tmp_path / "lower.db"
    _wishlist_id, item_ids = await _seed_wishlist(db_path, [2])
    item_id = item_ids[0]
    booked = _run_copies(db_path, [_create(item_id, _ADA_ID, _ADA_NAME, 2)])
    assert booked[0]["status"] == "ok", booked
    before = await _load(db_path, item_id)

    lowered = _run_copies(db_path, [_lower(item_id, _OWNER_ID, _OWNER_NAME, 1)])
    assert lowered[0]["status"] == "error", lowered
    assert lowered[0]["error_type"] == "CannotReduceQuantityBelowReservedError"

    after = await _load(db_path, item_id)
    assert after.quantity == before.quantity == 2
    assert after.received == before.received
    assert after.occupied == before.occupied == 2
    assert after.reservations == before.reservations
    _assert_consistent(after)


async def test_receipt_is_not_capped_by_occupied_units(tmp_path: Path) -> None:
    """Receipt counts once, leaves the promise open, and a later promise uses remainder."""
    db_path = tmp_path / "receipt.db"
    _wishlist_id, item_ids = await _seed_wishlist(db_path, [1])
    item_id = item_ids[0]
    promised = _run_copies(db_path, [_create(item_id, _ADA_ID, _ADA_NAME, 1)])
    assert promised[0]["status"] == "ok", promised

    recorded = _run_copies(db_path, [_receipt(item_id, _OWNER_ID, _OWNER_NAME, 1)])
    assert recorded[0]["status"] == "ok", recorded
    balance = await _load(db_path, item_id)
    _assert_consistent(balance)
    assert balance.received == 1
    assert balance.occupied == 1
    assert balance.occupied + balance.received > balance.quantity
    ada_rows = [row for row in balance.reservations if row.user_id == _ADA_ID]
    assert len(ada_rows) == 1
    assert ada_rows[0].status == ReservationStatus.ACTIVE.value

    later = _run_copies(db_path, [_create(item_id, _BEA_ID, _BEA_NAME, 1)])
    assert later[0]["status"] == "error", later
    assert later[0]["error_type"] == "InsufficientQuantityError"
    _assert_no_gifter(str(later[0]["message"]), _ADA_ID, _ADA_NAME)
    after_promise = await _load(db_path, item_id)
    _assert_consistent(after_promise)
    assert after_promise.free_remainder == 0
    assert after_promise.reservations == balance.reservations

    refused = _run_copies(db_path, [_receipt(item_id, _OWNER_ID, _OWNER_NAME, 1)])
    assert refused[0]["status"] == "error", refused
    assert refused[0]["error_type"] == "NothingRemainingError"
    final = await _load(db_path, item_id)
    assert final.received == 1
    assert final.quantity == balance.quantity
    assert final.reservations == balance.reservations
    _assert_consistent(final)


async def test_different_wishes_both_succeed(tmp_path: Path) -> None:
    """A commit on one wish does not change the other wish's quantities."""
    db_path = tmp_path / "two-wishes.db"
    _wishlist_id, item_ids = await _seed_wishlist(db_path, [1, 1])
    first_id, second_id = item_ids

    results = _run_copies(
        db_path,
        [
            _create(first_id, _ADA_ID, _ADA_NAME, 1),
            _create(second_id, _BEA_ID, _BEA_NAME, 1),
        ],
    )
    assert {row["status"] for row in results} == {"ok"}, results

    first = await _load(db_path, first_id)
    second = await _load(db_path, second_id)
    _assert_consistent(first)
    _assert_consistent(second)
    assert first.quantity == 1
    assert first.received == 0
    assert first.occupied == 1
    assert {row.user_id for row in first.reservations} == {_ADA_ID}
    assert second.quantity == 1
    assert second.received == 0
    assert second.occupied == 1
    assert {row.user_id for row in second.reservations} == {_BEA_ID}


async def test_one_store_keeps_self_booking_and_archive_rules(tmp_path: Path) -> None:
    """One copy still refuses self-booking and a new promise on an archived wish."""
    db_path = tmp_path / "one-store.db"
    wishlist_id, item_ids = await _seed_wishlist(db_path, [1, 1])
    booked_id, own_id = item_ids
    owner = _actor(_OWNER_ID, _OWNER_NAME)

    async def book_ada(service: WishlistService) -> None:
        await service.create_reservation(
            item_id=booked_id,
            user=_actor(_ADA_ID, _ADA_NAME),
            quantity=1,
        )

    await _execute(db_path, book_ada)

    async def book_bea(service: WishlistService) -> None:
        await service.create_reservation(
            item_id=booked_id,
            user=_actor(_BEA_ID, _BEA_NAME),
            quantity=1,
        )

    with pytest.raises(InsufficientQuantityError) as shortage:
        await _execute(db_path, book_bea)
    _assert_no_gifter(str(shortage.value), _ADA_ID, _ADA_NAME)
    booked = await _load(db_path, booked_id)
    _assert_consistent(booked)
    assert booked.free_remainder == 0
    assert booked.occupied == 1

    async def self_book(service: WishlistService) -> None:
        await service.create_reservation(item_id=own_id, user=owner, quantity=1)

    with pytest.raises(SelfReservationError):
        await _execute(db_path, self_book)

    async def archive(service: WishlistService) -> None:
        await service.archive_wishlist(wishlist_id, owner)

    await _execute(db_path, archive)

    async def book_archived(service: WishlistService) -> None:
        await service.create_reservation(
            item_id=own_id,
            user=_actor(_ADA_ID, _ADA_NAME),
            quantity=1,
        )

    with pytest.raises(WishlistArchivedError):
        await _execute(db_path, book_archived)

    kept = await _load(db_path, booked_id)
    assert any(
        row.user_id == _ADA_ID and row.status == ReservationStatus.ACTIVE.value
        for row in kept.reservations
    )
    untouched = await _load(db_path, own_id)
    assert untouched.reservations == ()
    assert untouched.quantity == 1


async def test_locked_wish_raises_inventory_busy_and_leaves_balance(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A wish locked past busy_timeout is a retryable refusal and writes nothing."""
    db_path = tmp_path / "busy.db"
    _wishlist_id, item_ids = await _seed_wishlist(db_path, [1])
    item_id = item_ids[0]
    before = await _load(db_path, item_id)

    ctx = multiprocessing.get_context("spawn")
    started = ctx.Event()
    release = ctx.Event()
    errors = ctx.Queue()
    holder = ctx.Process(
        target=_hold_write_lock,
        args=(str(db_path), started, release, errors),
    )
    holder.start()
    caught: Exception | None = None
    try:
        assert started.wait(timeout=10), (
            f"write lock was not acquired (exit={holder.exitcode}): {_queue_dump(errors)}"
        )

        async def book(service: WishlistService) -> None:
            await service.create_reservation(
                item_id=item_id,
                user=_actor(_ADA_ID, _ADA_NAME),
                quantity=1,
            )

        with caplog.at_level(logging.WARNING, logger=_STORE_LOGGER):
            try:
                await _run_on_store(db_path, book)
            except Exception as exc:
                caught = exc
    finally:
        release.set()
        holder.join(timeout=15)
        if holder.is_alive():
            holder.terminate()
            holder.join(timeout=5)

    assert caught is not None, "busy wish committed an inventory change"
    for record in caplog.records:
        _assert_no_gifter(_record_blob(record), _ADA_ID, _ADA_NAME)
    busy_logs = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "wishlist_inventory_busy"
    ]
    assert len(busy_logs) == 1
    assert getattr(busy_logs[0], "item_id", None) == item_id
    assert getattr(busy_logs[0], "operation", None) == "create_reservation"
    assert not hasattr(busy_logs[0], "user_id")
    assert "wishlist_inventory_committed" not in {
        getattr(record, "event", None) for record in caplog.records
    }

    after = await _load(db_path, item_id)
    assert after == before

    busy_type = getattr(wishlist_exceptions, "InventoryBusyError", None)
    assert (
        isinstance(busy_type, type)
        and issubclass(busy_type, WishlistError)
        and isinstance(caught, busy_type)
    ), f"expected InventoryBusyError after busy_timeout, got {type(caught).__name__}: {caught}"
    message = str(caught)
    assert "busy" in message.casefold()
    _assert_no_gifter(message, _ADA_ID, _ADA_NAME)


async def test_wish_transaction_logs_commit_without_row_or_gifter(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A committed wish transaction names the item and operation, not the gifter."""
    db_path = tmp_path / "commit-log.db"
    _wishlist_id, item_ids = await _seed_wishlist(db_path, [2])
    item_id = item_ids[0]
    tokens = _capability_tokens(db_path)

    async def book(service: WishlistService) -> None:
        await service.create_reservation(
            item_id=item_id,
            user=_actor(_ADA_ID, _ADA_NAME),
            quantity=1,
        )

    with caplog.at_level(logging.INFO, logger=_STORE_LOGGER):
        await _run_on_store(db_path, book)

    committed = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "wishlist_inventory_committed"
    ]
    assert len(committed) == 1
    record = committed[0]
    assert record.levelno == logging.INFO
    assert getattr(record, "item_id", None) == item_id
    assert getattr(record, "operation", None) == "create_reservation"
    assert getattr(record, "reservations_written", None) == 1
    blob = _record_blob(record)
    _assert_no_gifter(blob, _ADA_ID, _ADA_NAME)
    assert "Wish 0" not in blob
    assert "Shared inventory" not in blob
    for token in tokens:
        assert token not in blob


async def test_wish_transaction_logs_domain_rollback_without_gifter(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A refused wish change rolls back and does not name either gifter."""
    db_path = tmp_path / "domain-rollback.db"
    _wishlist_id, item_ids = await _seed_wishlist(db_path, [1])
    item_id = item_ids[0]
    tokens = _capability_tokens(db_path)

    async def book_ada(service: WishlistService) -> None:
        await service.create_reservation(
            item_id=item_id,
            user=_actor(_ADA_ID, _ADA_NAME),
            quantity=1,
        )

    await _run_on_store(db_path, book_ada)

    async def book_bea(service: WishlistService) -> None:
        await service.create_reservation(
            item_id=item_id,
            user=_actor(_BEA_ID, _BEA_NAME),
            quantity=1,
        )

    with caplog.at_level(logging.WARNING, logger=_STORE_LOGGER):
        caplog.clear()
        with pytest.raises(InsufficientQuantityError):
            await _run_on_store(db_path, book_bea)

    rolled = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "wishlist_inventory_rolled_back"
    ]
    assert len(rolled) == 1
    record = rolled[0]
    assert record.levelno == logging.WARNING
    assert getattr(record, "item_id", None) == item_id
    assert getattr(record, "operation", None) == "create_reservation"
    assert getattr(record, "error_type", None) == "InsufficientQuantityError"
    blob = _record_blob(record)
    _assert_no_gifter(blob, _ADA_ID, _ADA_NAME)
    _assert_no_gifter(blob, _BEA_ID, _BEA_NAME)
    assert "Wish 0" not in blob
    assert "Shared inventory" not in blob
    for token in tokens:
        assert token not in blob
    kept = await _load(db_path, item_id)
    assert kept.occupied == 1
    assert kept.free_remainder == 0


async def test_wish_transaction_logs_value_error_refusal_as_warning(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A quantity ValueError inside the wish transaction is WARNING, not ERROR."""
    db_path = tmp_path / "value-error-rollback.db"
    _wishlist_id, item_ids = await _seed_wishlist(db_path, [1])
    item_id = item_ids[0]
    reservation_id = await _seed_reservation(db_path, item_id, _ADA_ID, _ADA_NAME, 1)
    tokens = _capability_tokens(db_path)
    before = await _load(db_path, item_id)

    async def refuse(service: WishlistService) -> None:
        await service.update_reservation_quantity(
            reservation_id=reservation_id,
            user=_actor(_ADA_ID, _ADA_NAME),
            new_quantity=0,
        )

    with caplog.at_level(logging.WARNING, logger=_STORE_LOGGER):
        caplog.clear()
        with pytest.raises(ValueError, match="at least 1"):
            await _run_on_store(db_path, refuse)

    store_records = [record for record in caplog.records if record.name == _STORE_LOGGER]
    rolled = [
        record
        for record in store_records
        if getattr(record, "event", None) == "wishlist_inventory_rolled_back"
    ]
    assert len(rolled) == 1
    record = rolled[0]
    assert record.levelno == logging.WARNING
    assert not any(entry.levelno >= logging.ERROR for entry in store_records)
    assert getattr(record, "error_type", None) == "ValueError"
    assert getattr(record, "operation", None) == "update_reservation_quantity"
    assert getattr(record, "reservation_id", None) == reservation_id
    assert getattr(record, "item_id", None) == item_id
    blob = _record_blob(record)
    _assert_no_gifter(blob, _ADA_ID, _ADA_NAME)
    assert "at least 1" not in blob
    assert "Wish 0" not in blob
    assert "Shared inventory" not in blob
    for token in tokens:
        assert token not in blob
    after = await _load(db_path, item_id)
    assert after == before


async def test_wish_transaction_logs_storage_rollback_without_row_dump(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A non-busy storage failure rolls the wish back and logs only the error type."""
    db_path = tmp_path / "storage-rollback.db"
    _wishlist_id, item_ids = await _seed_wishlist(db_path, [1])
    item_id = item_ids[0]
    before = await _load(db_path, item_id)
    tokens = _capability_tokens(db_path)
    store = WishlistStore(f"sqlite+aiosqlite:///{db_path}")

    async def fail(_service: WishlistService) -> None:
        raise OperationalError("update", {}, sqlite3.OperationalError("disk I/O error"))

    try:
        with (
            caplog.at_level(logging.ERROR, logger=_STORE_LOGGER),
            pytest.raises(RuntimeError, match="Wishlist storage operation failed"),
        ):
            await store.execute_wish(
                fail,
                item_id=item_id,
                operation_name="create_reservation",
            )
    finally:
        await store.engine.dispose()

    after = await _load(db_path, item_id)
    assert after == before
    rolled = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "wishlist_inventory_rolled_back"
    ]
    assert len(rolled) == 1
    record = rolled[0]
    assert record.levelno == logging.ERROR
    assert getattr(record, "item_id", None) == item_id
    assert getattr(record, "operation", None) == "create_reservation"
    assert getattr(record, "error_type", None) == "OperationalError"
    blob = _record_blob(record)
    assert "disk I/O error" not in blob
    assert "Wish 0" not in blob
    assert "Shared inventory" not in blob
    for token in tokens:
        assert token not in blob
