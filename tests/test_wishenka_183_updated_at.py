"""Tests for WISHENKA-183: reminder_outbox.updated_at stamping and Alembic migration."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncConnection

from tests.receipt_support import open_store, sql_exec, sql_rows
from wishenka.config import Settings
from wishenka.notices.events import EventProducer, SharedEvent
from wishenka.notices.operator import resolve
from wishenka.notices.scheduler import ReminderScheduler
from wishenka.notices.sender import SendOutcome, SendResult
from wishenka.notices.store import NoticeStore
from wishenka.notices.worker import NoticeWorker

pytestmark = pytest.mark.timeout(30)


class _RetrySender:
    async def send(self, chat_id: int, text_body: str) -> SendResult:
        del chat_id, text_body
        return SendResult(SendOutcome.RETRYABLE, retry_after=120.0)

    async def close(self) -> None:
        return None


def _alembic_config(db: Path) -> Config:
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    return cfg


def test_alembic_reminder_outbox_updated_at_upgrade_backfill_and_downgrade(tmp_path: Path) -> None:
    """Upgrade backfills COALESCE(claimed_at, next_attempt_at); downgrade drops index and column."""
    db = tmp_path / "alembic_reminder_updated_at.db"
    cfg = _alembic_config(db)

    command.upgrade(cfg, "add_bot_capture_order_retention")
    sql_exec(
        db,
        "INSERT INTO reminder_outbox "
        "(occurrence_key, kind, user_id, event_date, status, claimed_at, next_attempt_at) "
        "VALUES ('k:claimed', 'birthday', 1, '2030-01-01', 'sending', 1111, 2222)",
    )
    sql_exec(
        db,
        "INSERT INTO reminder_outbox "
        "(occurrence_key, kind, user_id, event_date, status, claimed_at, next_attempt_at) "
        "VALUES ('k:unclaimed', 'birthday', 1, '2030-01-01', 'sent', NULL, 3333)",
    )

    command.upgrade(cfg, "add_reminder_outbox_updated_at")

    cols = {row["name"] for row in sql_rows(db, "PRAGMA table_info(reminder_outbox)")}
    assert "updated_at" in cols
    indexes = {
        row["name"]
        for row in sql_rows(
            db,
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='reminder_outbox'",
        )
    }
    assert "idx_reminder_outbox_status_updated" in indexes

    rows = {
        row["occurrence_key"]: row["updated_at"]
        for row in sql_rows(db, "SELECT occurrence_key, updated_at FROM reminder_outbox")
    }
    assert rows == {"k:claimed": 1111, "k:unclaimed": 3333}

    command.downgrade(cfg, "add_bot_capture_order_retention")

    cols_after = {row["name"] for row in sql_rows(db, "PRAGMA table_info(reminder_outbox)")}
    assert "updated_at" not in cols_after
    indexes_after = {
        row["name"]
        for row in sql_rows(
            db,
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='reminder_outbox'",
        )
    }
    assert "idx_reminder_outbox_status_updated" not in indexes_after


async def test_reminder_outbox_writers_stamp_updated_at(tmp_path: Path) -> None:
    """Scheduler, events, claim_reminder, worker settle_reminder, and operator stamp updated_at."""
    db = tmp_path / "writers_updated_at.db"
    async with open_store(db) as store:
        settings = Settings(database_url=f"sqlite+aiosqlite:///{db}")
        notice_store = NoticeStore(store, settings)
        ts = "2030-01-01T00:00:00+00:00"

        sql_exec(
            db,
            "INSERT INTO users(id, telegram_id, first_name, locale, created_at, updated_at) "
            "VALUES (1, 1001, 'Test', 'en', ?, ?)",
            (ts, ts),
        )
        sql_exec(
            db,
            "INSERT INTO bot_destinations(user_id, chat_id, active, updated_at) "
            "VALUES (1, 1001, 1, 100)",
        )
        sql_exec(
            db,
            "INSERT INTO wl_lists(id, owner_id, title, public_token, invite_token, status, "
            "event_date, created_at, updated_at) "
            "VALUES (10, 1001, 'Bday List', 'pub10', 'inv10', 'active', '2030-01-12', ?, ?)",
            (ts, ts),
        )
        sql_exec(
            db,
            "INSERT INTO birthday_entries(id, owner_id, label, month, day, revision, deleted) "
            "VALUES (20, 1, 'Alice', 1, 12, 1, 0)",
        )

        # 1. Scheduler INSERTs stamp updated_at.
        scan_now = int(datetime(2030, 1, 10, 12, 0, tzinfo=UTC).timestamp())
        scheduler = ReminderScheduler(store, settings)
        await scheduler.run_once(now=scan_now)

        sched_rows = sql_rows(
            db,
            "SELECT kind, next_attempt_at, updated_at FROM reminder_outbox ORDER BY id",
        )
        assert len(sched_rows) >= 2
        assert all(row["updated_at"] == scan_now for row in sched_rows)

        # 2. Event INSERT stamps updated_at.
        event_now = scan_now + 10
        producer = EventProducer()

        async def _enqueue(conn: AsyncConnection) -> int:
            return await producer.record(
                conn,
                SharedEvent(
                    kind="list_updated",
                    wishlist_id=10,
                    item_id=None,
                    event_id="evt-183",
                    recipients=(1001,),
                ),
                now=event_now,
            )

        queued = await store.transaction(_enqueue)
        assert queued == 1
        evt_row = sql_rows(
            db,
            "SELECT updated_at FROM reminder_outbox WHERE occurrence_key='evt-183:1001'",
        )[0]
        assert evt_row["updated_at"] == event_now

        # Clear outbox to test claim -> settle retry -> stale -> operator cleanly.
        sql_exec(db, "DELETE FROM reminder_outbox")

        # 3. claim_reminder + NoticeWorker.run_once retry stamps updated_at = settled_at (< next).
        sql_exec(
            db,
            "INSERT INTO reminder_outbox "
            "(id, occurrence_key, kind, user_id, birthday_id, revision, event_date, "
            "status, attempts, next_attempt_at, updated_at) "
            "VALUES (1, 'worker:1', 'birthday', 1001, 20, 1, '2030-01-12', 'pending', 0, ?, ?)",
            (scan_now, scan_now),
        )
        settle_now = scan_now + 50
        worker = NoticeWorker(
            notice_store,
            _RetrySender(),
            settings,
            clock=lambda: float(settle_now),
        )
        processed = await worker.run_once(now=settle_now)
        assert processed == 1
        worker_row = sql_rows(
            db,
            "SELECT status, next_attempt_at, updated_at FROM reminder_outbox WHERE id=1",
        )[0]
        assert worker_row["status"] == "pending"
        assert worker_row["updated_at"] == settle_now
        assert worker_row["next_attempt_at"] > settle_now

        # 4. Stale recovery in claim_reminder stamps updated_at, and operator.resolve stamps it.
        sql_exec(
            db,
            "INSERT INTO reminder_outbox "
            "(id, occurrence_key, kind, user_id, birthday_id, revision, event_date, "
            "status, claimed_at, claim_token, attempts, next_attempt_at, updated_at) "
            "VALUES (2, 'stale:2', 'birthday', 1001, 20, 1, '2030-01-12', "
            "'sending', 100, 'tok', 1, 100, 100)",
        )
        stale_check_now = settle_now + 1000
        await notice_store.claim_reminder(stale_check_now)
        stale_row = sql_rows(
            db,
            "SELECT status, updated_at FROM reminder_outbox WHERE id=2",
        )[0]
        assert stale_row["status"] == "uncertain"
        assert stale_row["updated_at"] == stale_check_now

        resolve_now = stale_check_now + 200
        resolved = await resolve(store, "reminder", 2, "fail", resolve_now)
        assert resolved is True
        resolved_row = sql_rows(
            db,
            "SELECT status, updated_at FROM reminder_outbox WHERE id=2",
        )[0]
        assert resolved_row["status"] == "failed"
        assert resolved_row["updated_at"] == resolve_now


async def test_purge_finished_logs_batch_count_and_batch_size(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """purge_finished logs batches and batch_size on notice_outbox_purged."""
    db = tmp_path / "purge-batches-obs.db"
    settings = Settings(db_path=db, bot_token="test-token")
    now = datetime(2030, 1, 15, 12, 0, tzinfo=UTC)
    old_epoch = int((now - timedelta(days=40)).timestamp())

    async with open_store(db) as store:
        notice_store = NoticeStore(store, settings)
        for idx in range(5):
            sql_exec(
                db,
                "INSERT INTO reminder_outbox "
                "(occurrence_key, kind, user_id, birthday_id, revision, event_date, "
                "status, attempts, next_attempt_at, updated_at) "
                "VALUES (?, 'list_updated', 1001, NULL, 1, '2030-01-10', 'sent', 1, ?, ?)",
                (f"obs-batch:{idx}", old_epoch, old_epoch),
            )

        with caplog.at_level(logging.INFO, logger="wishenka.wishlists.notices"):
            caplog.clear()
            purged = await notice_store.purge_finished(
                now - timedelta(days=30),
                now=now,
                batch_size=2,
            )

        assert purged == 5
        events = [r for r in caplog.records if getattr(r, "event", None) == "notice_outbox_purged"]
        assert len(events) == 1
        rec = events[0]
        assert getattr(rec, "receipt_purged", None) == 0
        assert getattr(rec, "reminder_purged", None) == 5
        assert getattr(rec, "total_purged", None) == 5
        assert getattr(rec, "batches", None) == 3
        assert getattr(rec, "batch_size", None) == 2

        with caplog.at_level(logging.INFO, logger="wishenka.wishlists.notices"):
            caplog.clear()
            assert (
                await notice_store.purge_finished(
                    now - timedelta(days=30),
                    now=now,
                    batch_size=2,
                )
                == 0
            )
        empty_events = [
            r for r in caplog.records if getattr(r, "event", None) == "notice_outbox_purged"
        ]
        assert empty_events == []
