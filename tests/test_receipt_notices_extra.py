"""Extra tests of the gift notice path (WISHENKA-23): retention, title cut, late cancellation."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from tests.notice_support import FakeNoticeSender, send_result
from tests.receipt_support import (
    GIFTER,
    GIFTER_ID,
    OTHER_GIFTER,
    OTHER_GIFTER_ID,
    THIRD_GIFTER,
    THIRD_GIFTER_ID,
    new_symbol,
    outbox_rows,
    sql_exec,
)
from tests.test_receipt_notices import _DAN, _base, _Env, _store_env
from wishenka.config import Settings
from wishenka.wishlists.cleanup import run_cleanup_cycle

pytestmark = pytest.mark.timeout(60)

_OLD = "2020-01-01T00:00:00+00:00"
_NOW = datetime(2026, 6, 1, tzinfo=UTC)


def _set_state(db: Path, giver_id: int, status: str, updated_at: str) -> None:
    sql_exec(
        db,
        "UPDATE notification_outbox SET status = ?, updated_at = ? WHERE giver_user_id = ?",
        (status, updated_at, giver_id),
    )


async def _four_rows(env: _Env) -> None:
    """One receipt, four queue rows, then states: old sent, old failed, old pending, fresh sent."""
    await env.seed(10, ((GIFTER, 1), (OTHER_GIFTER, 1), (THIRD_GIFTER, 1), (_DAN, 1)))
    await env.receive(1)
    db = env.db
    _set_state(db, GIFTER_ID, "sent", _OLD)
    _set_state(db, OTHER_GIFTER_ID, "failed", _OLD)
    _set_state(db, THIRD_GIFTER_ID, "pending", _OLD)
    _set_state(db, _DAN.telegram_id, "sent", _NOW.isoformat())


async def test_purge_finished_keeps_open_and_fresh_rows(tmp_path: Path) -> None:
    """Retention: finished rows at or before the threshold go; pending and fresh rows stay."""
    async with _store_env(tmp_path) as env:
        await _four_rows(env)
        notice_store = new_symbol("wishenka.notices.store", "NoticeStore")(env.store, env.settings)

        purged = await notice_store.purge_finished(_NOW - timedelta(days=30))

        assert purged == 2
        left = {row["giver_user_id"]: row["status"] for row in outbox_rows(env.db)}
        assert left == {THIRD_GIFTER_ID: "pending", _DAN.telegram_id: "sent"}
        assert await notice_store.purge_finished(_NOW - timedelta(days=30)) == 0


async def test_cleanup_cycle_purges_notices_and_logs_only_when_rows(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Design 10: the cycle purges through the optional store and the event needs rows > 0."""
    async with _store_env(tmp_path) as env:
        await _four_rows(env)
        notice_store = new_symbol("wishenka.notices.store", "NoticeStore")(env.store, env.settings)
        caplog.set_level(logging.INFO)

        await run_cleanup_cycle(env.store, env.settings, now=_NOW, notice_store=notice_store)
        await run_cleanup_cycle(env.store, env.settings, now=_NOW, notice_store=notice_store)

        purged = [
            r for r in caplog.records if getattr(r, "event", "") == "receipt_notice_rows_purged"
        ]
        assert [getattr(r, "rows", None) for r in purged] == [2]
        assert len(outbox_rows(env.db)) == 2


async def test_cleanup_cycle_survives_a_failing_notice_purge(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Design 10: a failed purge is a WARNING with the class name; the cycle still completes."""

    class _Broken:
        async def purge_finished(self, threshold: datetime) -> int:
            raise RuntimeError("secret detail")

    async with _store_env(tmp_path) as env:
        caplog.set_level(logging.INFO)

        broken: Any = _Broken()
        stats = await run_cleanup_cycle(env.store, env.settings, now=_NOW, notice_store=broken)

        assert stats.wishlists_purged == 0
        events = {getattr(r, "event", ""): r for r in caplog.records}
        assert "background_cleanup_completed" in events
        failed = events["receipt_notice_purge_failed"]
        assert failed.levelno == logging.WARNING
        assert getattr(failed, "error_class", None) == "RuntimeError"
        assert "secret detail" not in str(failed.__dict__)


async def test_titles_are_cut_at_one_hundred_characters(tmp_path: Path) -> None:
    """Design 5: both titles are cut to 100 characters, short titles are untouched."""
    async with _store_env(tmp_path) as env:
        await env.seed(5, ((GIFTER, 1),), title="w" * 150, list_title="l" * 100 + "tail")
        await env.receive(1)
        sender = FakeNoticeSender()

        await env.worker(sender).run_once(_base())

        ((_chat, text),) = sender.calls
        assert "«" + "w" * 100 + "»" in text
        assert "«" + "l" * 100 + "»" in text
        assert "tail" not in text


async def test_promise_cancelled_after_receipt_does_not_get_notice(tmp_path: Path) -> None:
    """Receipt notices are delivered only while the giver has an open promise."""
    async with _store_env(tmp_path) as env:
        await env.seed(5, ((GIFTER, 1),))
        await env.receive(1)
        await env.cancel(GIFTER)
        sender = FakeNoticeSender()

        await env.worker(sender).run_once(_base())

        assert sender.calls == []
        assert [row["status"] for row in outbox_rows(env.db)] == ["skipped"]


def _info_events(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.levelno >= logging.INFO and hasattr(r, "event")]


async def test_run_loop_sends_until_stopped(tmp_path: Path) -> None:
    """Design 7: ``run`` polls the queue, settles rows and ends when the stop event is set."""
    async with _store_env(tmp_path) as env:
        env.settings = Settings(
            database_url=env.settings.database_url,
            secret_key="notice",
            receipt_notice_poll_interval_seconds=0.05,
        )
        await env.seed(5, ((GIFTER, 1),))
        await env.receive(1)
        sender = FakeNoticeSender()
        stop = asyncio.Event()
        task = asyncio.create_task(env.worker(sender).run(stop))
        try:
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline and not sender.calls:
                await asyncio.sleep(0.02)
        finally:
            stop.set()
            await asyncio.wait_for(task, timeout=15)

        assert [chat for chat, _text in sender.calls] == [GIFTER_ID]
        assert [row["status"] for row in outbox_rows(env.db)] == ["sent"]


async def test_run_loop_logs_one_error_per_failure_streak(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Design 7: an unreadable queue gives one ERROR with the class name and a backoff."""

    class _Broken:
        calls = 0

        async def claim_next(self, now: int) -> None:
            self.calls += 1
            raise RuntimeError("secret detail")

    broken = _Broken()
    worker_class = new_symbol("wishenka.notices.worker", "NoticeWorker")
    settings = Settings(receipt_notice_poll_interval_seconds=0.05)
    worker = worker_class(broken, FakeNoticeSender(), settings)
    caplog.set_level(logging.DEBUG)
    stop = asyncio.Event()
    delays: list[float] = []
    real_wait_for = asyncio.wait_for

    async def fake_wait_for(awaitable: Any, timeout: float | None = None) -> Any:
        if timeout is not None and len(delays) < 4:
            close = getattr(awaitable, "close", None)
            if callable(close):
                close()
            delays.append(timeout)
            if len(delays) == 4:
                stop.set()
            raise TimeoutError
        return await real_wait_for(awaitable, timeout=timeout)

    monkeypatch.setattr("wishenka.notices.worker.asyncio.wait_for", fake_wait_for)
    task = asyncio.create_task(worker.run(stop))
    await real_wait_for(task, timeout=15)

    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert [getattr(r, "event", "") for r in errors] == ["receipt_notice_worker_error"]
    assert getattr(errors[0], "error_class", None) == "RuntimeError"
    assert "secret detail" not in str(errors[0].__dict__)
    assert broken.calls == 4
    assert delays == [
        pytest.approx(0.1),
        pytest.approx(0.2),
        pytest.approx(0.4),
        pytest.approx(0.8),
    ]


async def test_window_summary_on_a_fixed_grid(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """50-observability: one INFO per closed window with rows, nothing for an idle window."""
    async with _store_env(tmp_path) as env:
        await env.seed(5, ((GIFTER, 1), (OTHER_GIFTER, 1), (THIRD_GIFTER, 1)))
        await env.receive(1)
        sender = FakeNoticeSender(
            [send_result("delivered"), send_result("retryable"), send_result("rejected")]
        )
        clock_value = [1000.0]
        worker = env.worker(sender, clock=lambda: clock_value[0])
        caplog.set_level(logging.DEBUG)
        caplog.clear()

        await worker.run_once(_base())
        worker.flush_if_due(1199.0)
        assert [r for r in _info_events(caplog) if r.levelno == logging.INFO] == []

        worker.flush_if_due(1200.0)
        worker.flush_if_due(1500.0)

        summaries = [
            r
            for r in _info_events(caplog)
            if getattr(r, "event", "") == "receipt_notice_window_summary"
        ]
        assert len(summaries) == 1
        record = summaries[0]
        fields = [getattr(record, name) for name in ("window_seconds", "sent", "retried")]
        assert fields + [record.__dict__["failed_terminal"]] == [300, 1, 1, 1]
        assert len([r for r in _info_events(caplog) if r.levelno == logging.INFO]) == 1


async def test_long_drain_stamps_each_claim_with_its_own_time(tmp_path: Path) -> None:
    """Design 7: claimed_at is the clock at the claim, so a long drain never looks stale."""
    async with _store_env(tmp_path) as env:
        await env.seed(5, ((GIFTER, 1), (OTHER_GIFTER, 1), (THIRD_GIFTER, 1)))
        await env.receive(1)
        lease = int(env.settings.receipt_notice_claim_lease_seconds)
        start = _base()
        clock_value = [float(start)]
        claimed_seen: list[tuple[int, int]] = []
        other_claims: list[Any] = []
        notice_store_class = new_symbol("wishenka.notices.store", "NoticeStore")

        class _SlowSender(FakeNoticeSender):
            async def send(self, chat_id: int, text: str) -> Any:
                sending = [row for row in outbox_rows(env.db) if row["status"] == "sending"]
                assert len(sending) == 1, sending
                claimed_seen.append((int(sending[0]["claimed_at"]), int(clock_value[0])))
                if len(self.calls) == 2:  # the last row: nothing else is pending
                    other = notice_store_class(env.store, env.settings)
                    other_claims.append(await other.claim_next(int(clock_value[0]) + 1))
                    after = [row for row in outbox_rows(env.db) if row["status"] == "sending"]
                    assert [(r["ambiguous"], r["status"]) for r in after] == [(0, "sending")]
                result = await super().send(chat_id, text)
                clock_value[0] += lease + 1  # a slow send, longer than the lease
                return result

        sender = _SlowSender()
        worker = env.worker(sender, clock=lambda: clock_value[0])

        await worker.run_once()

        assert len(sender.calls) == 3
        assert [claimed for claimed, _clock in claimed_seen] == [
            clock for _claimed, clock in claimed_seen
        ]
        assert claimed_seen[2][0] == start + 2 * (lease + 1)
        assert other_claims == [None]
        assert sorted(row["status"] for row in outbox_rows(env.db)) == ["sent"] * 3
        assert [row["ambiguous"] for row in outbox_rows(env.db)] == [0, 0, 0]
