"""Cross-process delivery fence and crash recovery checks."""

from __future__ import annotations

import asyncio
import multiprocessing
from pathlib import Path
from typing import Any

import pytest

from tests.receipt_support import GIFTER_ID, app_env, bearer, db_path_of, sql_exec, sql_rows
from tests.test_wishenka_219_repro import _complete_url, _seed
from wishenka.notices.fence import delivery_lock, resolve_attempt

pytestmark = pytest.mark.timeout(90)


def _hold(url: str, item_id: int, entered: Any, release: Any) -> None:
    with delivery_lock(url, item_id, GIFTER_ID):
        entered.set()
        release.wait(timeout=30)


def test_other_process_holding_delivery_lock_refuses_completion(tmp_path: Path) -> None:
    with app_env(tmp_path, name="fence.db") as (client, sessions, app):
        wishlist, item, reservation, _ = _seed(app)
        ctx = multiprocessing.get_context("spawn")
        entered, release = ctx.Event(), ctx.Event()
        process = ctx.Process(
            target=_hold, args=(app.state.wishlist_store.database_url, item, entered, release)
        )
        process.start()
        try:
            assert entered.wait(timeout=20)
            url = _complete_url(wishlist, item, reservation)
            assert client.post(url, headers=bearer(sessions, GIFTER_ID)).status_code == 503
            assert sql_rows(
                db_path_of(app), "SELECT status FROM wl_reservations WHERE id=?", (reservation,)
            ) == [{"status": "purchased"}]
        finally:
            release.set()
            process.join(timeout=5)
            if process.is_alive():
                process.kill()
                process.join(timeout=3)
        assert process.exitcode == 0
        assert client.post(url, headers=bearer(sessions, GIFTER_ID)).status_code == 200


@pytest.mark.parametrize("queue", ["gift", "reminder"])
def test_unresolved_crashed_attempt_blocks_until_audited_resolution(
    tmp_path: Path, queue: str
) -> None:
    with app_env(tmp_path, name="recovery.db") as (client, sessions, app):
        wishlist, item, reservation, _ = _seed(app)
        sql_exec(
            db_path_of(app),
            "INSERT INTO receipt_delivery_fence VALUES (?,?,?,?,?,?)",
            (item, GIFTER_ID, "attempt", queue, 1, "in_flight"),
        )
        url = _complete_url(wishlist, item, reservation)
        headers = bearer(sessions, GIFTER_ID)
        assert client.post(url, headers=headers).status_code == 503
        assert asyncio.run(
            resolve_attempt(
                app.state.wishlist_store,
                item,
                GIFTER_ID,
                operator="test operator",
                evidence="process gone; final",
            )
        )
        assert len(sql_rows(db_path_of(app), "SELECT id FROM receipt_delivery_fence_audit")) == 1
        assert client.post(url, headers=headers).status_code == 200


def _run_blocked_worker(database_url: str, entered: Any, release: Any) -> None:
    from wishenka.config import Settings
    from wishenka.notices.sender import SendOutcome, SendResult
    from wishenka.notices.store import NoticeStore
    from wishenka.notices.worker import NoticeWorker
    from wishenka.wishlists.store import WishlistStore

    class Sender:
        async def send(self, chat_id: int, text: str) -> SendResult:
            entered.set()
            await asyncio.to_thread(release.wait, 40)
            return SendResult(SendOutcome.DELIVERED)

        async def close(self) -> None:
            pass

    async def run() -> None:
        store = WishlistStore(database_url)
        settings = Settings(database_url=database_url, secret_key="notice")
        try:
            await NoticeWorker(NoticeStore(store, settings), Sender(), settings).run_once()
        finally:
            await store.engine.dispose()

    asyncio.run(run())


@pytest.mark.parametrize("queue", ["gift", "reminder"])
async def test_killed_sender_preserves_fence_across_expiry_and_restart(
    tmp_path: Path, queue: str
) -> None:
    from tests.notice_support import FakeNoticeSender
    from tests.receipt_support import GIFTER
    from tests.test_receipt_notices import _base, _store_env
    from wishenka.wishlists.exceptions import InventoryBusyError
    from wishenka.wishlists.service import WishlistService

    async with _store_env(tmp_path) as env:
        await env.seed(2, ((GIFTER, 1),))

        async def purchase(service):
            reservation = service._items[env.item_id].reservations[0]
            return await service.mark_reservation_purchased(reservation.id, GIFTER)

        reservation = await env.store.execute_wish(purchase, item_id=env.item_id)
        await env.receive(2)
        if queue == "reminder":
            sql_exec(env.db, "DELETE FROM notification_outbox")
            sql_exec(
                env.db,
                "INSERT INTO reminder_outbox "
                "(occurrence_key,kind,user_id,list_id,item_id,event_date,status,next_attempt_at) "
                "VALUES ('test-219','receipt_increased',?,?,?,'2024-01-01','pending',0)",
                (GIFTER_ID, env.wishlist_id, env.item_id),
            )
        ctx = multiprocessing.get_context("spawn")
        entered, release = ctx.Event(), ctx.Event()
        process = ctx.Process(
            target=_run_blocked_worker, args=(env.store.database_url, entered, release)
        )
        process.start()
        try:
            assert await asyncio.to_thread(entered.wait, 20)
            assert sql_rows(env.db, "SELECT state FROM receipt_delivery_fence") == [
                {"state": "in_flight"}
            ]
            service = WishlistService(store=env.store)
            with pytest.raises(InventoryBusyError):
                await service.complete_reservation(reservation.id, GIFTER)
            competing = FakeNoticeSender()
            await env.worker(competing).run_once(_base() + 10_000)
            assert competing.calls == []
            process.kill()
            await asyncio.to_thread(process.join, 5)
            with pytest.raises(InventoryBusyError):
                await service.complete_reservation(reservation.id, GIFTER)
            assert await resolve_attempt(
                env.store,
                env.item_id,
                GIFTER_ID,
                operator="test",
                evidence="sender killed; result final",
            )
            completed = await service.complete_reservation(reservation.id, GIFTER)
            assert completed.status.value == "completed"
        finally:
            if process.is_alive():
                process.kill()
                await asyncio.to_thread(process.join, 5)


def test_completion_idempotency_and_queued_suppression(tmp_path: Path) -> None:
    with app_env(tmp_path, name="replay.db") as (client, sessions, app):
        wishlist, item, reservation, _ = _seed(app)
        headers = bearer(sessions, GIFTER_ID) | {"Idempotency-Key": "complete-219-test"}
        url = _complete_url(wishlist, item, reservation)
        first = client.post(url, headers=headers)
        second = client.post(url, headers=headers)
        assert first.status_code == second.status_code == 200
        assert first.json() == second.json()
        assert sql_rows(
            db_path_of(app),
            "SELECT status FROM notification_outbox WHERE wish_item_id=? AND giver_user_id=?",
            (item, GIFTER_ID),
        ) == [{"status": "skipped"}]


@pytest.mark.parametrize("queue", ["gift", "reminder"])
async def test_ambiguous_result_keeps_completion_busy(tmp_path: Path, queue: str) -> None:
    from tests.notice_support import FakeNoticeSender, send_result
    from tests.receipt_support import GIFTER
    from tests.test_receipt_notices import _base, _store_env
    from wishenka.wishlists.exceptions import InventoryBusyError
    from wishenka.wishlists.service import WishlistService

    async with _store_env(tmp_path) as env:
        await env.seed(2, ((GIFTER, 1),))

        async def purchase(service: WishlistService) -> Any:
            reservation = service._items[env.item_id].reservations[0]
            return await service.mark_reservation_purchased(reservation.id, GIFTER)

        reservation = await env.store.execute_wish(purchase, item_id=env.item_id)
        await env.receive(2)
        if queue == "reminder":
            sql_exec(env.db, "DELETE FROM notification_outbox")
            sql_exec(
                env.db,
                "INSERT INTO reminder_outbox "
                "(occurrence_key,kind,user_id,list_id,item_id,event_date,status,next_attempt_at) "
                "VALUES ('ambiguous-219','receipt_increased',?,?,?,'2024-01-01','pending',0)",
                (GIFTER_ID, env.wishlist_id, env.item_id),
            )
        sender = FakeNoticeSender([send_result("ambiguous")])
        await env.worker(sender).run_once(_base())
        assert len(sender.calls) == 1
        assert sql_rows(env.db, "SELECT state FROM receipt_delivery_fence") == [
            {"state": "uncertain"}
        ]
        with pytest.raises(InventoryBusyError):
            await WishlistService(store=env.store).complete_reservation(reservation.id, GIFTER)


async def test_other_open_promise_retains_receipt_notice(tmp_path: Path) -> None:
    from tests.notice_support import FakeNoticeSender
    from tests.receipt_support import GIFTER
    from tests.test_receipt_notices import _base, _store_env
    from wishenka.wishlists.service import WishlistService

    async with _store_env(tmp_path) as env:
        await env.seed(2, ((GIFTER, 1), (GIFTER, 1)))

        async def purchase(service: WishlistService) -> Any:
            reservation = service._items[env.item_id].reservations[0]
            return await service.mark_reservation_purchased(reservation.id, GIFTER)

        reservation = await env.store.execute_wish(purchase, item_id=env.item_id)
        await env.receive(2)
        await WishlistService(store=env.store).complete_reservation(reservation.id, GIFTER)
        sender = FakeNoticeSender()
        await env.worker(sender).run_once(_base())
        assert len(sender.calls) == 1
        assert env.rows_for(GIFTER_ID)[0]["status"] == "sent"


def _run_before_handoff(database_url: str, entered: Any, release: Any) -> None:
    """Hold the worker immediately after its durable fence is committed."""
    import wishenka.notices.worker as _worker

    worker_module: Any = _worker
    original = worker_module.begin_attempt

    async def pause_after_fence(*args: Any, **kwargs: Any) -> bool:
        result = await original(*args, **kwargs)
        if result:
            entered.set()
            await asyncio.to_thread(release.wait, 40)
        return bool(result)

    worker_module.begin_attempt = pause_after_fence
    _run_blocked_worker(database_url, entered, release)


async def _seed_receipt_queue(env: Any, queue: str) -> Any:
    from tests.receipt_support import GIFTER
    from wishenka.wishlists.service import WishlistService

    await env.seed(2, ((GIFTER, 1),))

    async def purchase(service: WishlistService) -> Any:
        reservation = service._items[env.item_id].reservations[0]
        return await service.mark_reservation_purchased(reservation.id, GIFTER)

    reservation = await env.store.execute_wish(purchase, item_id=env.item_id)
    await env.receive(2)
    if queue == "reminder":
        sql_exec(env.db, "DELETE FROM notification_outbox")
        sql_exec(
            env.db,
            "INSERT INTO reminder_outbox "
            "(occurrence_key,kind,user_id,list_id,item_id,event_date,status,next_attempt_at) "
            "VALUES ('fence-extra-219','receipt_increased',?,?,?,'2024-01-01','pending',0)",
            (GIFTER_ID, env.wishlist_id, env.item_id),
        )
    return reservation


@pytest.mark.parametrize("queue", ["gift", "reminder"])
@pytest.mark.parametrize("blocked_by", ["lock", "fence"])
async def test_unsent_busy_claim_is_deferred_without_consuming_attempt(
    tmp_path: Path, queue: str, blocked_by: str
) -> None:
    from tests.notice_support import FakeNoticeSender
    from tests.test_receipt_notices import _base, _store_env

    async with _store_env(tmp_path) as env:
        await _seed_receipt_queue(env, queue)
        if blocked_by == "fence":
            sql_exec(
                env.db,
                "INSERT INTO receipt_delivery_fence VALUES (?,?,?,?,?,?)",
                (env.item_id, GIFTER_ID, "old-attempt", queue, 999, "uncertain"),
            )
        sender = FakeNoticeSender()
        if blocked_by == "lock":
            async with delivery_lock(env.store.database_url, env.item_id, GIFTER_ID):
                await env.worker(sender).run_once(_base())
        else:
            await env.worker(sender).run_once(_base())
        table = "notification_outbox" if queue == "gift" else "reminder_outbox"
        assert sql_rows(env.db, f"SELECT status,attempts,claim_token FROM {table}") == [
            {"status": "pending", "attempts": 0, "claim_token": None}
        ]
        assert sender.calls == []


@pytest.mark.parametrize("queue", ["gift", "reminder"])
@pytest.mark.parametrize("pause", ["before_handoff", "during_send"])
async def test_suspended_sender_cannot_be_overtaken_after_lease_expiry(
    tmp_path: Path, queue: str, pause: str
) -> None:
    from tests.notice_support import FakeNoticeSender
    from tests.receipt_support import GIFTER
    from tests.test_receipt_notices import _base, _store_env
    from wishenka.wishlists.exceptions import InventoryBusyError
    from wishenka.wishlists.service import WishlistService

    async with _store_env(tmp_path) as env:
        reservation = await _seed_receipt_queue(env, queue)
        ctx = multiprocessing.get_context("spawn")
        entered, release = ctx.Event(), ctx.Event()
        process = ctx.Process(
            target=_run_before_handoff if pause == "before_handoff" else _run_blocked_worker,
            args=(env.store.database_url, entered, release),
        )
        process.start()
        try:
            assert await asyncio.to_thread(entered.wait, 20)
            sender = FakeNoticeSender()
            await env.worker(sender).run_once(_base() + 10_000)
            assert sender.calls == []
            with pytest.raises(InventoryBusyError):
                await WishlistService(store=env.store).complete_reservation(reservation.id, GIFTER)
            release.set()
            await asyncio.to_thread(process.join, 15)
            assert process.exitcode == 0
            assert sql_rows(env.db, "SELECT state FROM receipt_delivery_fence") == [
                {"state": "uncertain"}
            ]
            with pytest.raises(InventoryBusyError):
                await WishlistService(store=env.store).complete_reservation(reservation.id, GIFTER)
        finally:
            if process.is_alive():
                process.kill()
                await asyncio.to_thread(process.join, 5)


@pytest.mark.parametrize("queue", ["gift", "reminder"])
async def test_crash_after_fence_before_handoff_stays_blocked(tmp_path: Path, queue: str) -> None:
    from tests.notice_support import FakeNoticeSender
    from tests.receipt_support import GIFTER
    from tests.test_receipt_notices import _base, _store_env
    from wishenka.wishlists.exceptions import InventoryBusyError
    from wishenka.wishlists.service import WishlistService

    async with _store_env(tmp_path) as env:
        reservation = await _seed_receipt_queue(env, queue)
        ctx = multiprocessing.get_context("spawn")
        entered, release = ctx.Event(), ctx.Event()
        process = ctx.Process(
            target=_run_before_handoff, args=(env.store.database_url, entered, release)
        )
        process.start()
        try:
            assert await asyncio.to_thread(entered.wait, 20)
            assert sql_rows(env.db, "SELECT state FROM receipt_delivery_fence") == [
                {"state": "in_flight"}
            ]
            process.kill()
            await asyncio.to_thread(process.join, 5)
            sender = FakeNoticeSender()
            await env.worker(sender).run_once(_base() + 10_000)
            assert sender.calls == []
            with pytest.raises(InventoryBusyError):
                await WishlistService(store=env.store).complete_reservation(reservation.id, GIFTER)
            assert sql_rows(env.db, "SELECT state FROM receipt_delivery_fence") == [
                {"state": "in_flight"}
            ]
        finally:
            if process.is_alive():
                process.kill()
                await asyncio.to_thread(process.join, 5)


@pytest.mark.timeout(30)
async def test_in_process_async_keyed_lock_fences_same_key_without_blocking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fcntl

    from tests.receipt_support import OTHER_GIFTER_ID

    url = f"sqlite+aiosqlite:///{tmp_path / 'local-lock.db'}"
    # Disable OS flock to prove the in-process asyncio.Lock alone fences same-key tasks.
    monkeypatch.setattr(fcntl, "flock", lambda *_args, **_kwargs: None)

    async with delivery_lock(url, 1, GIFTER_ID):
        with pytest.raises(BlockingIOError):
            async with delivery_lock(url, 1, GIFTER_ID):
                pass
        # A different (item_id, user_id) key is not blocked.
        async with delivery_lock(url, 1, OTHER_GIFTER_ID):
            pass

    # Released cleanly after exit.
    async with delivery_lock(url, 1, GIFTER_ID):
        pass
