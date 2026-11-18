"""Observability tests for WISHENKA-181 (retention & anonymization structured logging)."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from tests.receipt_support import open_store, sql_exec
from tests.test_bot_capture_repro import _action, _setup
from wishenka.config import Settings
from wishenka.logging import JsonFormatter
from wishenka.notices.store import NoticeStore
from wishenka.wishlists.cleanup import run_cleanup_cycle

pytestmark = pytest.mark.timeout(30)


@pytest.mark.asyncio
async def test_birthday_delete_logs_structured_event_without_pii(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Deleting a birthday logs birthday_deleted_anonymized without label, date, or chat_id."""
    scan_dt = datetime(2030, 3, 2, 10, 0, tzinfo=UTC)
    harness, store, _, _, _ = await _setup(tmp_path, monkeypatch, clock=lambda: scan_dt)
    secret_label = "Secret Friend Alice"
    try:
        await harness.text("/birthdays")
        await harness.callback(_action(harness.last_message(), ("add", "добав")))
        await harness.text(secret_label)
        await harness.text("07-14")
        await harness.text("/birthdays")

        caplog.clear()
        with caplog.at_level(logging.INFO, logger="wishenka.bot.birthdays"):
            await harness.callback(_action(harness.last_message(), ("delete", "удал")))

        records = [
            r
            for r in caplog.records
            if r.name == "wishenka.bot.birthdays"
            and getattr(r, "event", None) == "birthday_deleted_anonymized"
        ]
        assert len(records) == 1
        rec = records[0]
        assert rec.levelno == logging.INFO
        assert getattr(rec, "owner_id", None) is not None
        assert getattr(rec, "birthday_id", None) is not None

        rendered = JsonFormatter().format(rec)
        parsed = json.loads(rendered)
        assert parsed["extra"]["event"] == "birthday_deleted_anonymized"
        assert "chat_id" not in parsed["extra"]
        assert secret_label not in rendered
        assert "07-14" not in rendered
    finally:
        await store.engine.dispose()


@pytest.mark.asyncio
async def test_retention_purge_and_cleanup_cycle_structured_logging(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Cleanup cycle and NoticeStore retention purge emit structured counts without PII."""
    db = tmp_path / "obs_retention.db"
    now = datetime(2030, 5, 1, 12, 0, tzinfo=UTC)
    old_epoch = int((now - timedelta(days=120)).timestamp())
    old_iso = (now - timedelta(days=120)).isoformat()
    settings = Settings(database_url=f"sqlite+aiosqlite:///{db}")

    async with open_store(db) as store:
        notice_store = NoticeStore(store, settings)
        sql_exec(
            db,
            "INSERT INTO birthday_entries "
            "(id, owner_id, label, month, day, deleted, deleted_at, revision) "
            "VALUES (1, 101, '', 0, 0, 1, ?, 2)",
            (old_epoch,),
        )
        sql_exec(
            db,
            "INSERT INTO bot_destinations (user_id, chat_id, active, updated_at) "
            "VALUES (202, 999888777, 0, ?)",
            (old_epoch,),
        )
        sql_exec(
            db,
            "INSERT INTO notice_receipt_keys (event_type, receipt_id, giver_user_id, created_at) "
            "VALUES ('wish_reserved', 501, 303, ?)",
            (old_epoch,),
        )
        sql_exec(
            db,
            "INSERT INTO reminder_outbox "
            "(occurrence_key, kind, user_id, birthday_id, revision, event_date, status, "
            "attempts, next_attempt_at) "
            "VALUES ('bday:99:1:2029-01-01:7', 'birthday', 101, NULL, 1, '2029-01-01', 'sent', "
            "1, ?)",
            (old_epoch,),
        )

        caplog.clear()
        with caplog.at_level(logging.INFO):
            stats = await run_cleanup_cycle(store, settings, now=now, notice_store=notice_store)

        assert stats.birthdays_purged == 1
        assert stats.bot_destinations_purged == 1
        assert stats.receipt_keys_purged == 1

        outbox_recs = [
            r for r in caplog.records if getattr(r, "event", None) == "notice_outbox_purged"
        ]
        assert len(outbox_recs) == 1
        assert getattr(outbox_recs[0], "reminder_purged", None) == 1

        retention_recs = [
            r
            for r in caplog.records
            if getattr(r, "event", None) == "notice_retention_records_purged"
        ]
        assert len(retention_recs) == 1
        assert getattr(retention_recs[0], "birthdays_purged", None) == 1
        assert getattr(retention_recs[0], "destinations_purged", None) == 1
        assert getattr(retention_recs[0], "receipt_keys_purged", None) == 1

        cycle_recs = [
            r for r in caplog.records if getattr(r, "event", None) == "background_cleanup_completed"
        ]
        assert len(cycle_recs) == 1
        cycle_rec = cycle_recs[0]
        assert getattr(cycle_rec, "birthdays_purged", None) == 1
        assert getattr(cycle_rec, "bot_destinations_purged", None) == 1
        assert getattr(cycle_rec, "receipt_keys_purged", None) == 1
        assert isinstance(getattr(cycle_rec, "duration_ms", None), float)

        rendered = JsonFormatter().format(cycle_rec)
        parsed = json.loads(rendered)
        assert parsed["extra"]["birthdays_purged"] == 1
        assert parsed["extra"]["bot_destinations_purged"] == 1
        assert parsed["extra"]["receipt_keys_purged"] == 1
        assert "999888777" not in caplog.text
        assert old_iso is not None


@pytest.mark.asyncio
async def test_retention_purge_failure_logs_warning_without_raising(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Failure in purge_retention_records logs receipt_notice_purge_failed WARNING."""
    db = tmp_path / "obs_retention_fail.db"
    failing_notice_store = AsyncMock(spec=NoticeStore)
    failing_notice_store.purge_finished.return_value = 0
    failing_notice_store.purge_retention_records.side_effect = RuntimeError("sqlite busy")
    settings = Settings(database_url=f"sqlite+aiosqlite:///{db}")

    async with open_store(db) as store:
        with caplog.at_level(logging.WARNING, logger="wishenka.wishlists.cleanup"):
            stats = await run_cleanup_cycle(
                store, settings, now=datetime.now(UTC), notice_store=failing_notice_store
            )

        assert stats.birthdays_purged == 0
        assert stats.bot_destinations_purged == 0
        assert stats.receipt_keys_purged == 0

        warn_recs = [
            r for r in caplog.records if getattr(r, "event", None) == "receipt_notice_purge_failed"
        ]
        assert len(warn_recs) == 1
        assert warn_recs[0].levelno == logging.WARNING
        assert getattr(warn_recs[0], "error_class", None) == "RuntimeError"
