"""Bounded reminder scans must continue promptly and preserve delivery fairness."""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests.notice_support import FakeNoticeSender
from tests.receipt_support import OWNER, OWNER_ID, open_store
from tests.test_notice_delivery_repro import _verify_start
from tests.test_receipt_notices import _Env
from wishenka.notices.scheduler import ReminderScheduler
from wishenka.wishlists.service import WishlistService

pytestmark = pytest.mark.timeout(30)


async def _seed(store: object, db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    await _verify_start(monkeypatch, db, OWNER_ID)

    async def create(service: WishlistService) -> None:
        for index in range(5):
            await service.create_wishlist(
                owner=OWNER,
                title=f"List {index}",
                event_date=datetime(2030 if index in (0, 4) else 2031, 3, 8, tzinfo=UTC),
            )

    await store.execute(create)  # type: ignore[attr-defined]
    with sqlite3.connect(db) as conn:
        owner = conn.execute("SELECT id FROM users WHERE telegram_id=?", (OWNER_ID,)).fetchone()[0]
        for index in range(5):
            conn.execute(
                "INSERT INTO birthday_entries(owner_id,label,month,day) VALUES (?,?,?,?)",
                (owner, f"Birthday {index}", 3 if index == 4 else 8, 8),
            )


async def test_paged_scans_resume_and_concurrent_workers_do_not_duplicate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A restart and concurrent scans reach late records once within the same UTC window."""
    monkeypatch.setattr("wishenka.notices.scheduler.PAGE_SIZE", 2)
    db = tmp_path / "pages.db"
    now = int(datetime(2030, 3, 1, tzinfo=UTC).timestamp())
    async with open_store(db) as store:
        await _seed(store, db, monkeypatch)
        settings = _Env(store, db).settings
        assert await ReminderScheduler(store, settings).run_once(now) is True

    async with open_store(db) as store:
        scheduler = ReminderScheduler(store, _Env(store, db).settings)
        results = await asyncio.wait_for(
            asyncio.gather(scheduler.run_once(now), scheduler.run_once(now)), timeout=10
        )
        assert any(result is False for result in results)
        with sqlite3.connect(db) as conn:
            rows = conn.execute(
                "SELECT kind, COUNT(*) FROM reminder_outbox GROUP BY kind ORDER BY kind"
            ).fetchall()
        assert rows == [("birthday", 1), ("list", 2)]


async def test_worker_continues_pages_without_waiting_an_hour_and_drains_queue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Queue delivery runs between bounded scans, including while more pages remain."""
    monkeypatch.setattr("wishenka.notices.scheduler.PAGE_SIZE", 2)
    db = tmp_path / "worker-pages.db"
    now = int(datetime(2030, 3, 1, tzinfo=UTC).timestamp())
    async with open_store(db) as store:
        await _seed(store, db, monkeypatch)
        sender = FakeNoticeSender()
        worker = _Env(store, db).worker(sender, lambda: float(now))
        worker._poll = 0.001
        real_scheduler = ReminderScheduler(store, _Env(store, db).settings)
        stop = asyncio.Event()
        scans: list[bool] = []

        class CountingScheduler:
            async def run_once(self, when: int) -> bool:
                if scans:
                    assert sender.calls, "A queued reminder should be delivered between pages"
                more = await real_scheduler.run_once(when)
                scans.append(more)
                if not more:
                    stop.set()
                return more

        worker._scheduler = CountingScheduler()
        await asyncio.wait_for(worker.run(stop), timeout=10)
        assert scans == [True, True, False]
        with sqlite3.connect(db) as conn:
            kinds = conn.execute("SELECT kind FROM reminder_outbox ORDER BY kind").fetchall()
        assert kinds == [("birthday",), ("list",), ("list",)]
        assert len(sender.calls) == 1
