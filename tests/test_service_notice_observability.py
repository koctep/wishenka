"""Privacy-safe aggregate observability for service notices."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests.notice_support import FakeNoticeSender, send_result
from tests.receipt_support import OWNER, OWNER_ID, open_store
from tests.test_notice_delivery_repro import _run_reminder_scan, _verify_start
from tests.test_receipt_notices import _Env
from wishenka.wishlists.service import WishlistService

pytestmark = pytest.mark.timeout(60)


@pytest.mark.parametrize(
    ("outcome", "counter"),
    [
        ("delivered", "sent"),
        ("retryable", "retried"),
        ("rejected", "failed_terminal"),
        ("ambiguous", "uncertain"),
    ],
)
async def test_reminder_summary_is_aggregated_and_private(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    outcome: str,
    counter: str,
) -> None:
    """The real queue and sender outcome feed counters without logging private data."""
    db = tmp_path / "observability.db"
    async with open_store(db) as store:

        async def create(service: WishlistService) -> None:
            await service.create_wishlist(
                owner=OWNER,
                title="Secret occasion https://example.test/private-token",
                event_date=datetime(2030, 3, 8, tzinfo=UTC),
            )

        await store.execute(create)
        await _verify_start(monkeypatch, db, OWNER_ID)
        env = _Env(store, db)
        now = int(datetime(2030, 3, 1, tzinfo=UTC).timestamp())
        caplog.set_level(logging.DEBUG)
        await _run_reminder_scan(store, env.settings, now)
        sender = FakeNoticeSender([send_result(outcome, error_class="SafeError")])
        worker = env.worker(sender, lambda: float(now))
        assert await worker.run_once(now) == 1
        worker.flush_if_due(now + 3600)

    summaries = [
        r for r in caplog.records if getattr(r, "event", "") == "service_delivery_window_summary"
    ]
    assert len(summaries) == 1
    assert getattr(summaries[0], counter) == 1
    assert len(sender.calls) == 1
    events = [
        r
        for r in caplog.records
        if r.name in {"wishenka.wishlists.notices", "wishenka.notices.scheduler"}
    ]
    rendered = " ".join(f"{r.getMessage()} {r.__dict__}" for r in events)
    assert "Secret occasion" not in rendered
    assert "private-token" not in rendered
    assert all(
        OWNER_ID not in (r.__dict__.get("user_id"), r.__dict__.get("chat_id")) for r in events
    )
    assert any(getattr(r, "event", "") == "reminder_scan_completed" for r in events)


async def test_scheduler_failure_is_safe_and_loop_recovers(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """An error does not reveal input or terminate scheduling; the next tick runs normally."""
    import asyncio

    async with open_store(tmp_path / "scheduler-failure.db") as store:
        env = _Env(store, tmp_path / "scheduler-failure.db")
        worker = env.worker(FakeNoticeSender())
        worker._poll = 0.001
        stop = asyncio.Event()

        class FailingOnceScheduler:
            calls = 0

            async def run_once(self, _now: int) -> None:
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("secret birthday https://private.test/token")
                stop.set()

        scheduler = FailingOnceScheduler()
        worker._scheduler = scheduler
        caplog.set_level(logging.ERROR)
        await asyncio.wait_for(worker.run(stop), timeout=5)
        assert scheduler.calls == 2
    errors = [r for r in caplog.records if getattr(r, "event", "") == "reminder_scheduler_error"]
    assert len(errors) == 1
    assert errors[0].__dict__["error_class"] == "RuntimeError"
    assert "secret birthday" not in caplog.text
    assert "private.test" not in caplog.text


async def test_scheduler_failures_do_not_block_queued_receipt(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A failing scheduler backs off independently while the receipt queue still delivers."""
    import asyncio
    import time

    from tests.receipt_support import GIFTER

    path = tmp_path / "scheduler-independent.db"
    async with open_store(path) as store:
        env = _Env(store, path, verify_destinations=True)
        await env.seed(promises=((GIFTER, 1),))
        await env.receive(1)
        sender = FakeNoticeSender()
        worker = env.worker(sender, lambda: time.time() + 10)
        worker._poll = 0.001
        stop = asyncio.Event()

        class FailingTwiceScheduler:
            calls = 0

            async def run_once(self, _now: int) -> None:
                self.calls += 1
                if self.calls <= 2:
                    raise RuntimeError("private birthday detail")
                stop.set()

        scheduler = FailingTwiceScheduler()
        worker._scheduler = scheduler
        caplog.set_level(logging.ERROR, logger="wishenka.wishlists.notices")
        await asyncio.wait_for(worker.run(stop), timeout=5)
        assert scheduler.calls == 3
        assert len(sender.calls) == 1
        assert env.outbox_one()["status"] == "sent"
    errors = [r for r in caplog.records if getattr(r, "event", "") == "reminder_scheduler_error"]
    assert len(errors) == 1
    assert "private birthday detail" not in caplog.text


async def test_scheduler_cancellation_propagates(tmp_path: Path) -> None:
    """Cancellation interrupts a pending scan instead of being mistaken for a retryable error."""
    import asyncio

    async with open_store(tmp_path / "scheduler-cancel.db") as store:
        worker = _Env(store, tmp_path / "scheduler-cancel.db").worker(FakeNoticeSender())
        entered = asyncio.Event()

        class BlockingScheduler:
            async def run_once(self, _now: int) -> None:
                entered.set()
                await asyncio.Event().wait()

        worker._scheduler = BlockingScheduler()
        task = asyncio.create_task(worker.run(asyncio.Event()))
        await asyncio.wait_for(entered.wait(), timeout=5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=5)


async def test_default_logging_formatter_shows_safe_summary_and_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The actual default logging setup emits counters and error classes, not private text."""
    import io
    import sys

    from wishenka.logging import configure_logging

    output = io.StringIO()
    root = logging.getLogger()
    original_handlers, original_level = root.handlers[:], root.level
    monkeypatch.setattr(sys, "stdout", output)
    try:
        configure_logging()
        async with open_store(tmp_path / "formatter.db") as store:
            worker = _Env(store, tmp_path / "formatter.db").worker(FakeNoticeSender())
            worker._reminder_counts.update(sent=2, retried=1, failed_terminal=1, uncertain=1)
            worker.flush_if_due(worker._window_start + worker._window)
            import asyncio

            stop = asyncio.Event()

            class BrokenScheduler:
                async def run_once(self, _now: int) -> None:
                    stop.set()
                    raise RuntimeError("secret birthday https://private.test/token")

            worker._scheduler = BrokenScheduler()
            await asyncio.wait_for(worker.run(stop), timeout=5)
    finally:
        root.handlers[:] = original_handlers
        root.setLevel(original_level)
    rendered = output.getvalue()
    assert "sent=2" in rendered and "retried=1" in rendered
    assert "failed_terminal=1" in rendered and "uncertain=1" in rendered
    assert "error_class=RuntimeError" in rendered
    assert "secret birthday" not in rendered and "private.test" not in rendered


async def test_concurrent_scans_log_only_aggregate_committed_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Concurrent scheduler scans count one committed intent and omit private fields."""
    import asyncio

    db = tmp_path / "concurrent-scan.db"
    async with open_store(db) as store:

        async def create(service: WishlistService) -> None:
            await service.create_wishlist(
                owner=OWNER,
                title="Concurrent private occasion",
                event_date=datetime(2030, 3, 8, tzinfo=UTC),
            )

        await store.execute(create)
        await _verify_start(monkeypatch, db, OWNER_ID)
        env = _Env(store, db)
        now = int(datetime(2030, 3, 1, tzinfo=UTC).timestamp())
        caplog.set_level(logging.DEBUG, logger="wishenka.notices.scheduler")
        await asyncio.wait_for(
            asyncio.gather(
                _run_reminder_scan(store, env.settings, now),
                _run_reminder_scan(store, env.settings, now),
            ),
            timeout=10,
        )
    records = [r for r in caplog.records if getattr(r, "event", "") == "reminder_scan_completed"]
    assert len(records) == 2
    assert sum(r.__dict__["intents_created"] for r in records) == 1
    rendered = " ".join(f"{r.getMessage()} {r.__dict__}" for r in records)
    assert "Concurrent private occasion" not in rendered
    assert all(
        OWNER_ID not in (r.__dict__.get("user_id"), r.__dict__.get("chat_id")) for r in records
    )
