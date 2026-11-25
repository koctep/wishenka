"""Failing repro tests for WISHENKA-181 (Step 3, red before Step 4)."""

from __future__ import annotations

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
    OWNER_ID,
    open_store,
    outbox_rows,
    sql_exec,
    sql_rows,
)
from tests.test_bot_capture_repro import _action, _setup
from tests.test_notice_delivery_repro import _verify_start
from tests.test_receipt_notices import _Env
from wishenka.config import Settings
from wishenka.notices.scheduler import ReminderScheduler
from wishenka.notices.store import NoticeStore
from wishenka.wishlists.cleanup import run_cleanup_cycle

pytestmark = pytest.mark.timeout(30)


def _birthday_rows(db: Path) -> list[dict[str, Any]]:
    return sql_rows(db, "SELECT * FROM birthday_entries ORDER BY id")


def _destination_rows(db: Path) -> list[dict[str, Any]]:
    return sql_rows(db, "SELECT * FROM bot_destinations ORDER BY user_id")


def _reminder_rows(db: Path) -> list[dict[str, Any]]:
    return sql_rows(db, "SELECT * FROM reminder_outbox ORDER BY id")


def _receipt_key_rows(db: Path) -> list[dict[str, Any]]:
    return sql_rows(db, "SELECT * FROM notice_receipt_keys ORDER BY giver_user_id")


async def _add_birthday(harness: Any, label: str, date_text: str) -> None:
    await harness.text("/birthdays")
    await harness.callback(_action(harness.last_message(), ("add", "добав")))
    await harness.text(label)
    await harness.text(date_text)


async def test_deleted_birthday_anonymized_and_purged_after_retention(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Deleted birthdays are anonymized immediately and purged after retention unless uncertain."""
    scan_dt = datetime(2030, 3, 2, 10, 0, tzinfo=UTC)
    harness, store, users, _, _ = await _setup(tmp_path, monkeypatch, clock=lambda: scan_dt)
    db = tmp_path / "capture.db"
    try:
        await _add_birthday(harness, "Alice Bday", "03-08")
        await _add_birthday(harness, "Bob Bday", "03-09")

        env = _Env(store, db)
        await ReminderScheduler(store, env.settings).run_once(int(scan_dt.timestamp()))

        # Leave Bob's reminder in 'uncertain' state; mark Alice's reminder as 'sent'.
        sender = FakeNoticeSender([send_result("delivered"), send_result("ambiguous")])
        worker = env.worker(sender)
        await worker.run_once(int(scan_dt.timestamp()))
        await worker.run_once(int(scan_dt.timestamp()) + 1)

        # Delete both birthdays via the bot UI flow.
        for _ in range(2):
            await harness.text("/birthdays")
            await harness.callback(_action(harness.last_message(), ("delete", "удал")))

        rows_after_delete = _birthday_rows(db)
        assert len(rows_after_delete) == 2
        for row in rows_after_delete:
            assert row["deleted"] == 1
            assert row["label"] == "", "Deleted birthday label must be anonymized immediately"
            assert row["month"] == 0, "Deleted birthday month must be anonymized immediately"
            assert row["day"] == 0, "Deleted birthday day must be anonymized immediately"

        # Within retention window: tombstones are still preserved.
        notice_store = NoticeStore(store, env.settings)
        await run_cleanup_cycle(
            store,
            env.settings,
            now=scan_dt + timedelta(days=5),
            notice_store=notice_store,
        )
        assert len(_birthday_rows(db)) == 2

        # Past retention window: Alice's tombstone is purged, Bob's is kept due to 'uncertain'.
        await run_cleanup_cycle(
            store,
            env.settings,
            now=scan_dt + timedelta(days=35),
            notice_store=notice_store,
        )
        remaining = _birthday_rows(db)
        assert len(remaining) == 1
        uncertain_birthdays = {
            r["birthday_id"] for r in _reminder_rows(db) if r["status"] == "uncertain"
        }
        assert {r["id"] for r in remaining} == uncertain_birthdays
    finally:
        await harness.bot.session.close()
        await users.engine.dispose()
        await store.engine.dispose()


async def test_inactive_bot_destination_purged_and_reestablished(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Inactive bot_destinations are purged after retention, active kept, and /start recreates."""
    db = tmp_path / "dest.db"
    async with open_store(db) as store:
        env = _Env(store, db)
        await env.seed(3, ((GIFTER, 1),))
        await _verify_start(monkeypatch, db, OWNER_ID)
        await _verify_start(monkeypatch, db, GIFTER_ID)

        await env.receive(1)
        now = int(time.time()) + 10
        sender = FakeNoticeSender([send_result("rejected", error_class="TelegramForbiddenError")])
        await env.worker(sender).run_once(now)

        dests = {row["chat_id"]: row["active"] for row in _destination_rows(db)}
        assert dests == {OWNER_ID: 1, GIFTER_ID: 0}

        now_dt = datetime.now(UTC)
        notice_store = NoticeStore(store, env.settings)

        # Within retention window: inactive destination is not purged yet.
        await run_cleanup_cycle(
            store,
            env.settings,
            now=now_dt + timedelta(days=5),
            notice_store=notice_store,
        )
        assert {row["chat_id"] for row in _destination_rows(db)} == {OWNER_ID, GIFTER_ID}

        # Past retention window: inactive destination is physically deleted, active stays.
        await run_cleanup_cycle(
            store,
            env.settings,
            now=now_dt + timedelta(days=35),
            notice_store=notice_store,
        )
        assert [row["chat_id"] for row in _destination_rows(db)] == [OWNER_ID]

        # Re-establishing bot delivery via /start creates an active destination cleanly.
        await _verify_start(monkeypatch, db, GIFTER_ID)
        reestablished = {row["chat_id"]: row["active"] for row in _destination_rows(db)}
        assert reestablished == {OWNER_ID: 1, GIFTER_ID: 1}


async def test_terminal_reminder_purge_preserves_active_cycle_and_uncertain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Terminal occasion reminders stay until event_date < today_utc; uncertain always stays."""
    db = tmp_path / "reminders.db"
    async with open_store(db) as store:
        settings = Settings(
            database_url=f"sqlite+aiosqlite:///{db}",
            reminder_retention_days=2,
            notice_reminder_lead_days=(7,),
        )
        await _verify_start(monkeypatch, db, OWNER_ID)
        sql_exec(
            db,
            "INSERT INTO birthday_entries(owner_id, label, month, day) VALUES (?, ?, ?, ?)",
            (OWNER_ID, "Cycle Friend", 3, 10),
        )
        sql_exec(
            db,
            "INSERT INTO birthday_entries(owner_id, label, month, day) VALUES (?, ?, ?, ?)",
            (OWNER_ID, "Uncertain Friend", 3, 1),
        )

        # Seed an old uncertain reminder row that must never be purged.
        old_epoch = int(datetime(2030, 2, 22, 10, 0, tzinfo=UTC).timestamp())
        sql_exec(
            db,
            "INSERT INTO reminder_outbox "
            "(occurrence_key, kind, user_id, birthday_id, revision, event_date, status, "
            "attempts, next_attempt_at) "
            "VALUES (?, 'birthday', ?, 2, 1, '2030-03-01', 'uncertain', 1, ?)",
            ("bday:2:1:2030-03-01:7", OWNER_ID, old_epoch),
        )

        # Schedule and send the 2030-03-10 birthday reminder 7 days early (2030-03-03).
        t_scan = datetime(2030, 3, 3, 10, 0, tzinfo=UTC)
        await ReminderScheduler(store, settings).run_once(int(t_scan.timestamp()))
        sender = FakeNoticeSender()
        notice_store = NoticeStore(store, settings)
        from wishenka.notices.worker import NoticeWorker

        worker = NoticeWorker(notice_store, sender, settings, clock=lambda: t_scan.timestamp())
        await worker.run_once(int(t_scan.timestamp()))
        assert len(sender.calls) == 1

        # Past reminder_retention_days=2 (2030-03-06), but event_date 2030-03-10 >= today_utc:
        # row must NOT be purged, and scheduler must NOT re-insert or re-send it.
        t_mid = datetime(2030, 3, 6, 10, 0, tzinfo=UTC)
        await run_cleanup_cycle(store, settings, now=t_mid, notice_store=notice_store)
        statuses = {row["event_date"]: row["status"] for row in _reminder_rows(db)}
        assert statuses == {"2030-03-01": "uncertain", "2030-03-10": "sent"}

        await ReminderScheduler(store, settings).run_once(int(t_mid.timestamp()))
        await worker.run_once(int(t_mid.timestamp()))
        assert len(sender.calls) == 1

        # After event_date < today_utc and past retention (2030-03-13):
        # terminal 'sent' row is purged, 'uncertain' row remains.
        t_after = datetime(2030, 3, 13, 10, 0, tzinfo=UTC)
        await run_cleanup_cycle(store, settings, now=t_after, notice_store=notice_store)
        remaining = _reminder_rows(db)
        assert [(r["event_date"], r["status"]) for r in remaining] == [("2030-03-01", "uncertain")]


async def test_receipt_dedup_keys_retained_within_window_and_purged_after(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """notice_receipt_keys are kept within window and purged after unless outbox is uncertain."""
    db = tmp_path / "receipt_keys.db"
    async with open_store(db) as store:
        env = _Env(store, db)
        await env.seed(5, ((GIFTER, 1), (OTHER_GIFTER, 1)))
        await _verify_start(monkeypatch, db, GIFTER_ID)
        await _verify_start(monkeypatch, db, OTHER_GIFTER_ID)

        await env.receive(1)
        assert len(_receipt_key_rows(db)) == 2

        # Deliver GIFTER's notice ('sent'), leave OTHER_GIFTER's notice 'uncertain'.
        sender = FakeNoticeSender([send_result("delivered"), send_result("ambiguous")])
        now = int(time.time()) + 10
        await env.worker(sender).run_once(now)
        await env.worker(sender).run_once(now + 1)

        statuses = {row["giver_user_id"]: row["status"] for row in outbox_rows(db)}
        assert statuses == {GIFTER_ID: "sent", OTHER_GIFTER_ID: "uncertain"}

        now_dt = datetime.now(UTC)
        notice_store = NoticeStore(store, env.settings)

        # Within retention window: both dedup keys are retained.
        await run_cleanup_cycle(
            store,
            env.settings,
            now=now_dt + timedelta(days=5),
            notice_store=notice_store,
        )
        assert {row["giver_user_id"] for row in _receipt_key_rows(db)} == {
            GIFTER_ID,
            OTHER_GIFTER_ID,
        }

        # Past retention window: GIFTER's outbox + dedup key are purged;
        # OTHER_GIFTER's outbox ('uncertain') and dedup key are preserved.
        await run_cleanup_cycle(
            store,
            env.settings,
            now=now_dt + timedelta(days=35),
            notice_store=notice_store,
        )
        assert [row["giver_user_id"] for row in outbox_rows(db)] == [OTHER_GIFTER_ID]
        assert [row["giver_user_id"] for row in _receipt_key_rows(db)] == [OTHER_GIFTER_ID]
