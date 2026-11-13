"""Row R5 ceiling checks for WISHENKA-39.

Five gifters race through ``execute_wish``. Booked units equal the free
units. A refusal is ``InsufficientQuantityError`` and adds no row.
``InventoryBusyError`` fails the check: at this crowd it means the fan-out
outran ``busy_timeout``, and the test does not retry it.
"""

from __future__ import annotations

import asyncio
import multiprocessing
import queue
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from wishenka.auth.models import AuthenticatedUser
from wishenka.wishlists.exceptions import InsufficientQuantityError
from wishenka.wishlists.models import ReservationStatus
from wishenka.wishlists.service import WishlistService
from wishenka.wishlists.store import WishlistStore

pytestmark = pytest.mark.timeout(120)

_OWNER_ID = 1001
_OWNER_NAME = "OwnerAda"
_GIFTERS: tuple[tuple[int, str], ...] = (
    (81001, "GifterAda"),
    (82002, "GifterBea"),
    (83003, "GifterCara"),
    (84004, "GifterDora"),
    (85005, "GifterEve"),
)
_SEED_ID = 86006
_SEED_NAME = "GifterSeed"
_GIFTER_COUNT = 5
_ONE_UNIT_FREE = 2
_WHOLE_FREE = 3
_SEEDED_REQUESTED = 4
_SEEDED_OCCUPIED = 1
_SEEDED_FREE = 3
_REPETITIONS = 3
_LOAD_ROUNDS = 2
_ONE_UNIT_ASK = 1
_OCCUPYING = {ReservationStatus.ACTIVE.value, ReservationStatus.PURCHASED.value}
_BARRIER_TIMEOUT_SECONDS = 20
_JOIN_TIMEOUT_SECONDS = 25
_DRAIN_TIMEOUT_SECONDS = 5
_TERMINATE_TIMEOUT_SECONDS = 5


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
    reservations: tuple[_ReservationRow, ...]

    @property
    def occupied(self) -> int:
        return sum(row.quantity for row in self.reservations if row.status in _OCCUPYING)

    @property
    def free_remainder(self) -> int:
        return max(0, self.quantity - self.received - self.occupied)


@dataclass(frozen=True)
class _Attempt:
    gifter_id: int
    quantity: int
    status: str
    error_type: str | None = None
    reservation_id: int | None = None


def _actor(telegram_id: int, first_name: str) -> AuthenticatedUser:
    return AuthenticatedUser(telegram_id=telegram_id, first_name=first_name)


def _error_payload(gifter_id: int, quantity: int, exc: BaseException) -> dict[str, Any]:
    return {
        "status": "error",
        "gifter_id": gifter_id,
        "quantity": quantity,
        "error_type": type(exc).__name__,
    }


async def _reserve(
    store: WishlistStore,
    item_id: int,
    user_id: int,
    first_name: str,
    quantity: int,
) -> dict[str, Any]:
    """Book through the wish-scoped transaction. Only a shortage is a result."""
    user = _actor(user_id, first_name)

    async def operation(service: WishlistService) -> int:
        reservation = await service.create_reservation(
            item_id=item_id,
            user=user,
            quantity=quantity,
        )
        return reservation.id

    try:
        reservation_id = await store.execute_wish(
            operation,
            item_id=item_id,
            operation_name="create_reservation",
        )
    except InsufficientQuantityError as exc:
        return _error_payload(user_id, quantity, exc)
    return {
        "status": "ok",
        "gifter_id": user_id,
        "quantity": quantity,
        "reservation_id": reservation_id,
    }


async def _book_in_process(
    db_path: str,
    item_id: int,
    user_id: int,
    first_name: str,
    quantity: int,
) -> dict[str, Any]:
    store = WishlistStore(f"sqlite+aiosqlite:///{db_path}")
    try:
        return await _reserve(store, item_id, user_id, first_name, quantity)
    finally:
        await store.engine.dispose()


def _worker(
    db_path: str,
    item_id: int,
    user_id: int,
    first_name: str,
    quantity: int,
    results: Any,
    barrier: Any,
) -> None:
    """Run one gifter's booking in its own process and engine."""
    try:
        if barrier is not None:
            barrier.wait(timeout=_BARRIER_TIMEOUT_SECONDS)
        results.put(asyncio.run(_book_in_process(db_path, item_id, user_id, first_name, quantity)))
    except Exception as exc:
        results.put(_error_payload(user_id, quantity, exc))


def _race_processes(db_path: Path, item_id: int, quantity: int) -> list[_Attempt]:
    """One process and one store per gifter, then the R2 join and drain."""
    assert len(_GIFTERS) == _GIFTER_COUNT
    ctx = multiprocessing.get_context("spawn")
    barrier = ctx.Barrier(_GIFTER_COUNT)
    results_queue = ctx.Queue()
    procs = [
        ctx.Process(
            target=_worker,
            args=(str(db_path), item_id, user_id, first_name, quantity, results_queue, barrier),
        )
        for user_id, first_name in _GIFTERS
    ]
    for proc in procs:
        proc.start()
    payloads: list[dict[str, Any]] = []
    try:
        for proc in procs:
            proc.join(timeout=_JOIN_TIMEOUT_SECONDS)
        deadline = time.monotonic() + _DRAIN_TIMEOUT_SECONDS
        while len(payloads) < _GIFTER_COUNT and time.monotonic() < deadline:
            try:
                payloads.append(results_queue.get(timeout=0.2))
            except queue.Empty:
                break
    finally:
        for proc in procs:
            if proc.is_alive():
                proc.terminate()
                proc.join(timeout=_TERMINATE_TIMEOUT_SECONDS)
    exits = [proc.exitcode for proc in procs]
    assert len(payloads) == _GIFTER_COUNT, f"exits={exits} outcomes={payloads}"
    assert all(code == 0 for code in exits), f"exits={exits} outcomes={payloads}"
    return [_require_attempt(payload) for payload in payloads]


async def _race_one_store(db_path: Path, item_id: int, quantity: int) -> list[_Attempt]:
    """One store, five ``execute_wish`` calls overlapped with ``asyncio.gather``."""
    assert len(_GIFTERS) == _GIFTER_COUNT
    store = WishlistStore(f"sqlite+aiosqlite:///{db_path}")
    try:
        payloads = await asyncio.gather(
            *[
                _reserve(store, item_id, user_id, first_name, quantity)
                for user_id, first_name in _GIFTERS
            ]
        )
    finally:
        await store.engine.dispose()
    return [_require_attempt(payload) for payload in payloads]


def _require_attempt(payload: dict[str, Any]) -> _Attempt:
    gifter_id = int(payload["gifter_id"])
    quantity = int(payload["quantity"])
    status = str(payload["status"])
    raw_error = payload.get("error_type")
    error_type = None if raw_error is None else str(raw_error)
    if error_type == "InventoryBusyError":
        raise AssertionError(f"InventoryBusyError fails the ceiling check: {payload}")
    if status == "ok":
        assert error_type is None, payload
        return _Attempt(
            gifter_id=gifter_id,
            quantity=quantity,
            status="ok",
            reservation_id=int(payload["reservation_id"]),
        )
    assert status == "error", payload
    assert error_type == "InsufficientQuantityError", payload
    return _Attempt(
        gifter_id=gifter_id,
        quantity=quantity,
        status="error",
        error_type=error_type,
    )


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


async def _seed_wishlist(db_path: Path, quantities: list[int]) -> tuple[int, list[int]]:
    owner = _actor(_OWNER_ID, _OWNER_NAME)

    async def setup(service: WishlistService) -> tuple[int, list[int]]:
        wishlist = await service.create_wishlist(owner=owner, title="Booking ceiling")
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


async def _seed_reservation(db_path: Path, item_id: int) -> int:
    async def book(service: WishlistService) -> int:
        reservation = await service.create_reservation(
            item_id=item_id,
            user=_actor(_SEED_ID, _SEED_NAME),
            quantity=_SEEDED_OCCUPIED,
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
            reservations=rows,
        )

    return await _execute(db_path, read)


def _assert_ceiling(
    before: _ItemBalance,
    after: _ItemBalance,
    attempts: list[_Attempt],
    *,
    ask: int,
) -> None:
    assert _GIFTER_COUNT > before.free_remainder >= 1
    assert ask == _ONE_UNIT_ASK or ask == before.free_remainder
    expected_wins = before.free_remainder if ask == _ONE_UNIT_ASK else 1
    assert sorted(attempt.gifter_id for attempt in attempts) == sorted(
        user_id for user_id, _first_name in _GIFTERS
    )

    before_ids = {row.reservation_id for row in before.reservations}
    new_rows = [row for row in after.reservations if row.reservation_id not in before_ids]
    assert all(row.status in _OCCUPYING for row in new_rows)
    booked = sum(row.quantity for row in new_rows)
    successes = [attempt for attempt in attempts if attempt.status == "ok"]
    refusals = [attempt for attempt in attempts if attempt.status == "error"]
    assert len(successes) == expected_wins
    assert len(refusals) == _GIFTER_COUNT - expected_wins
    assert booked == before.free_remainder
    assert {row.user_id for row in new_rows} == {attempt.gifter_id for attempt in successes}
    assert len(new_rows) == len(successes)
    for attempt in successes:
        matched = [row for row in new_rows if row.user_id == attempt.gifter_id]
        assert len(matched) == 1
        assert matched[0].quantity == attempt.quantity == ask
        assert matched[0].reservation_id == attempt.reservation_id
    refused_ids = {attempt.gifter_id for attempt in refusals}
    assert not any(row.user_id in refused_ids for row in after.reservations)
    assert all(attempt.error_type == "InsufficientQuantityError" for attempt in refusals)

    after_by_id = {row.reservation_id: row for row in after.reservations}
    for row in before.reservations:
        assert after_by_id[row.reservation_id] == row
    assert after.quantity == before.quantity
    assert after.received == before.received
    assert after.occupied == before.occupied + booked
    assert after.free_remainder >= 0
    assert after.free_remainder == 0


async def _contend(
    db_path: Path,
    item_id: int,
    *,
    ask: int,
    many_copies: bool,
    free: int,
    seeded: bool = False,
) -> _ItemBalance:
    before = await _load(db_path, item_id)
    assert before.received == 0
    assert before.free_remainder == free
    if seeded:
        assert before.quantity == _SEEDED_REQUESTED
        assert before.occupied == _SEEDED_OCCUPIED
        assert len(before.reservations) == 1
        seed = before.reservations[0]
        assert seed.user_id == _SEED_ID
        assert seed.quantity == _SEEDED_OCCUPIED
        assert seed.status in _OCCUPYING
    else:
        assert before.quantity == free
        assert before.occupied == 0
        assert before.reservations == ()
    if many_copies:
        attempts = _race_processes(db_path, item_id, ask)
    else:
        attempts = await _race_one_store(db_path, item_id, ask)
    after = await _load(db_path, item_id)
    _assert_ceiling(before, after, attempts, ask=ask)
    return after


@pytest.mark.timeout(30)
async def test_one_copy_one_unit_each(tmp_path: Path) -> None:
    """Five gifters on one store each ask for one of two free units."""
    db_path = tmp_path / "one-copy-one-unit.db"
    _wishlist_id, item_ids = await _seed_wishlist(db_path, [_ONE_UNIT_FREE])
    await _contend(
        db_path,
        item_ids[0],
        ask=_ONE_UNIT_ASK,
        many_copies=False,
        free=_ONE_UNIT_FREE,
    )


@pytest.mark.timeout(60)
async def test_many_copies_one_unit_each(tmp_path: Path) -> None:
    """Five processes each ask for one of two free units."""
    db_path = tmp_path / "many-copies-one-unit.db"
    _wishlist_id, item_ids = await _seed_wishlist(db_path, [_ONE_UNIT_FREE])
    await _contend(
        db_path,
        item_ids[0],
        ask=_ONE_UNIT_ASK,
        many_copies=True,
        free=_ONE_UNIT_FREE,
    )


@pytest.mark.timeout(30)
async def test_one_copy_whole_remainder(tmp_path: Path) -> None:
    """Five gifters on one store each ask for all three free units."""
    db_path = tmp_path / "one-copy-whole.db"
    _wishlist_id, item_ids = await _seed_wishlist(db_path, [_WHOLE_FREE])
    await _contend(
        db_path,
        item_ids[0],
        ask=_WHOLE_FREE,
        many_copies=False,
        free=_WHOLE_FREE,
    )


@pytest.mark.timeout(60)
async def test_many_copies_whole_remainder(tmp_path: Path) -> None:
    """Five processes each ask for all three free units."""
    db_path = tmp_path / "many-copies-whole.db"
    _wishlist_id, item_ids = await _seed_wishlist(db_path, [_WHOLE_FREE])
    await _contend(
        db_path,
        item_ids[0],
        ask=_WHOLE_FREE,
        many_copies=True,
        free=_WHOLE_FREE,
    )


@pytest.mark.timeout(90)
async def test_repeated_contention_many_copies(tmp_path: Path) -> None:
    """Three one-unit starts and three whole-remainder starts, one process each."""
    assert _REPETITIONS == 3
    assert _SEEDED_FREE == _SEEDED_REQUESTED - _SEEDED_OCCUPIED
    db_path = tmp_path / "repeated.db"
    quantities = [
        _ONE_UNIT_FREE,
        _ONE_UNIT_FREE,
        _SEEDED_REQUESTED,
        _WHOLE_FREE,
        _WHOLE_FREE,
        _SEEDED_REQUESTED,
    ]
    _wishlist_id, item_ids = await _seed_wishlist(db_path, quantities)
    await _seed_reservation(db_path, item_ids[2])
    await _seed_reservation(db_path, item_ids[5])

    for index in (0, 1):
        await _contend(
            db_path,
            item_ids[index],
            ask=_ONE_UNIT_ASK,
            many_copies=True,
            free=_ONE_UNIT_FREE,
        )
    await _contend(
        db_path,
        item_ids[2],
        ask=_ONE_UNIT_ASK,
        many_copies=True,
        free=_SEEDED_FREE,
        seeded=True,
    )
    for index in (3, 4):
        await _contend(
            db_path,
            item_ids[index],
            ask=_WHOLE_FREE,
            many_copies=True,
            free=_WHOLE_FREE,
        )
    await _contend(
        db_path,
        item_ids[5],
        ask=_WHOLE_FREE,
        many_copies=True,
        free=_SEEDED_FREE,
        seeded=True,
    )


@pytest.mark.timeout(120)
async def test_load_profile_one_copy_and_many_copies(tmp_path: Path) -> None:
    """Two rounds on one store and two rounds on one process per gifter."""
    db_path = tmp_path / "load.db"
    quantities = [_ONE_UNIT_FREE, _WHOLE_FREE] * (_LOAD_ROUNDS * 2)
    _wishlist_id, item_ids = await _seed_wishlist(db_path, quantities)
    finished: list[tuple[int, _ItemBalance]] = []
    for mode_index, many_copies in enumerate((False, True)):
        for round_index in range(_LOAD_ROUNDS):
            base = (mode_index * _LOAD_ROUNDS + round_index) * 2
            one_unit = await _contend(
                db_path,
                item_ids[base],
                ask=_ONE_UNIT_ASK,
                many_copies=many_copies,
                free=_ONE_UNIT_FREE,
            )
            whole = await _contend(
                db_path,
                item_ids[base + 1],
                ask=_WHOLE_FREE,
                many_copies=many_copies,
                free=_WHOLE_FREE,
            )
            finished.append((item_ids[base], one_unit))
            finished.append((item_ids[base + 1], whole))
    for item_id, ended in finished:
        again = await _load(db_path, item_id)
        assert again == ended
        assert again.free_remainder >= 0
        assert again.quantity == ended.quantity
        assert again.received == ended.received
