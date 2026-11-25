"""Multi-process notice-worker race test over a shared WAL SQLite database (WISHENKA-156)."""

from __future__ import annotations

import asyncio
import multiprocessing
import os
import queue
import time
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from tests.notice_support import FakeNoticeSender
from tests.receipt_support import (
    OWNER,
    SQLITE_PREFIX,
    make_user,
    open_store,
    outbox_rows,
    seed_wish,
)
from wishenka.auth.models import TelegramUser
from wishenka.config import Settings
from wishenka.notices.store import NoticeStore
from wishenka.notices.worker import NoticeWorker
from wishenka.users.store import UserStore
from wishenka.wishlists.service import WishlistService
from wishenka.wishlists.store import WishlistStore

pytestmark = pytest.mark.timeout(120)

_BARRIER_TIMEOUT = 10
_JOIN_TIMEOUT = 15
_DRAIN_TIMEOUT = 5
_GIVER_COUNT = 10
_BASE_GIVER_ID = 2001
_FIXED_NOW = 2_000_000_000


async def _seed_pending_notices(db: Path, giver_ids: list[int]) -> None:
    """Seed one wish with ``len(giver_ids)`` distinct givers and trigger pending outbox rows."""
    db_url = f"{SQLITE_PREFIX}{db}"
    async with open_store(db) as store:
        users = UserStore(db_url)
        try:
            await users.upsert_user(
                TelegramUser(id=OWNER.telegram_id, first_name=OWNER.first_name, language_code="ru")
            )
            for gid in giver_ids:
                profile = await users.upsert_user(
                    TelegramUser(id=gid, first_name=f"Giver{gid}", language_code="ru")
                )
                async with users.engine.begin() as conn:
                    await conn.execute(
                        text(
                            "INSERT OR REPLACE INTO bot_destinations "
                            "(user_id, chat_id, active) VALUES (:id, :chat, 1)"
                        ),
                        {"id": profile.telegram_id, "chat": gid},
                    )
        finally:
            await users.engine.dispose()

        async def setup(service: WishlistService) -> None:
            _, item_id = await seed_wish(service, quantity=_GIVER_COUNT + 5)
            for gid in giver_ids:
                await service.create_reservation(
                    item_id=item_id,
                    user=make_user(gid, f"Giver{gid}"),
                    quantity=1,
                )
            await service.record_item_fulfillment(item_id, OWNER, 1)

        await store.execute(setup)


async def _drain_in_process(db_path: str, fixed_now: int) -> dict[str, Any]:
    """Open an independent store + NoticeWorker in a child process and drain due rows."""
    db_url = f"{SQLITE_PREFIX}{db_path}"
    store = WishlistStore(db_url)
    try:
        settings = Settings(database_url=db_url, secret_key="notice-worker-race")
        notice_store = NoticeStore(store, settings)
        sender = FakeNoticeSender(sleep=0.01)
        worker = NoticeWorker(notice_store, sender, settings)
        processed = await worker.run_once(now=fixed_now)
        return {
            "pid": os.getpid(),
            "delivered": list(sender.calls),
            "processed": processed,
            "error": None,
        }
    finally:
        await store.engine.dispose()


def _worker_process(db_path: str, fixed_now: int, results: Any, barrier: Any) -> None:
    """Top-level picklable entrypoint for spawned worker processes."""
    try:
        barrier.wait(timeout=_BARRIER_TIMEOUT)
        payload = asyncio.run(_drain_in_process(db_path, fixed_now))
        results.put(payload)
    except Exception as exc:
        results.put(
            {
                "pid": os.getpid(),
                "delivered": [],
                "processed": 0,
                "error": f"{type(exc).__name__}: {exc}",
            }
        )


async def test_two_spawned_worker_processes_claim_and_deliver_once(tmp_path: Path) -> None:
    """Two OS processes racing on NoticeWorker.run_once deliver each queued notice once."""
    db = tmp_path / "notice_race.db"
    giver_ids = [_BASE_GIVER_ID + i for i in range(_GIVER_COUNT)]
    await _seed_pending_notices(db, giver_ids)

    initial_rows = outbox_rows(db)
    assert len(initial_rows) == _GIVER_COUNT
    assert all(row["status"] == "pending" for row in initial_rows)

    ctx = multiprocessing.get_context("spawn")
    barrier = ctx.Barrier(2)
    results_queue: Any = ctx.Queue()
    procs = [
        ctx.Process(
            target=_worker_process,
            args=(str(db), _FIXED_NOW, results_queue, barrier),
        )
        for _ in range(2)
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
        for proc in procs:
            assert not proc.is_alive(), f"worker process {proc.pid} timed out"
            assert proc.exitcode == 0, f"worker process {proc.pid} exited with {proc.exitcode}"
    finally:
        for proc in procs:
            if proc.is_alive():
                proc.terminate()
                proc.join(timeout=5)

    assert len(payloads) == 2, payloads
    errors = [p["error"] for p in payloads if p["error"] is not None]
    assert not errors, f"worker errors encountered: {errors}"

    all_deliveries = [call for p in payloads for call in p["delivered"]]
    assert len(all_deliveries) == _GIVER_COUNT
    assert len(set(all_deliveries)) == _GIVER_COUNT
    assert {chat_id for chat_id, _ in all_deliveries} == set(giver_ids)

    final_rows = outbox_rows(db)
    assert len(final_rows) == _GIVER_COUNT
    for row in final_rows:
        assert row["status"] == "sent"
        assert row["claim_token"] is None
        assert row["claimed_at"] is None
        assert row["attempts"] == 1
