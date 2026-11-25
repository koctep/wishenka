"""Edge-case tests for WISHENKA-181 retention, recovery, replay protection, and migrations."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from pydantic import ValidationError

from tests.receipt_support import (
    GIFTER,
    GIFTER_ID,
    open_store,
    outbox_rows,
    sql_exec,
    sql_rows,
)
from tests.test_notice_delivery_repro import _verify_start
from tests.test_receipt_notices import _Env
from wishenka.config import Settings
from wishenka.notices.store import NoticeStore
from wishenka.wishlists.cleanup import run_cleanup_cycle
from wishenka.wishlists.migrations import _configured, upgrade_to_head_sync

pytestmark = pytest.mark.timeout(60)


def test_retention_migration_upgrade_backfills_and_downgrade_reverts(tmp_path: Path) -> None:
    """Upgrade anonymizes legacy deleted birthdays, backfills timestamps, and downgrades cleanly."""
    path = tmp_path / "retention_mig.db"
    url = f"sqlite+aiosqlite:///{path}"
    command.upgrade(_configured(url), "add_deleted_session_revocations")
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO wl_lists(id,owner_id,title,public_token,invite_token,"
            "created_at,updated_at) "
            "VALUES (1,101,'list','p','i','2026-01-01T00:00:00+00:00','2026-01-01T00:00:00+00:00')"
        )
        conn.execute(
            "INSERT INTO wl_items(id,wishlist_id,title,created_at,updated_at) "
            "VALUES (1,1,'wish','2026-01-01T00:00:00+00:00','2026-01-01T00:00:00+00:00')"
        )
        conn.execute(
            "INSERT INTO wl_receipts(id,wish_item_id,quantity,received_at) "
            "VALUES (1,1,1,'2026-01-01T00:00:00+00:00')"
        )
        conn.execute(
            "INSERT INTO notification_outbox "
            "(id,event_type,receipt_id,wishlist_id,wish_item_id,giver_user_id,status,"
            "ambiguous,next_attempt_at,created_at,updated_at) "
            "VALUES (1,'gift_received',1,1,1,202,'sent',0,10,"
            "'2026-01-01T00:00:00+00:00','2026-01-01T00:00:00+00:00')"
        )
        conn.execute(
            "INSERT INTO notice_receipt_keys(event_type,receipt_id,giver_user_id) "
            "VALUES ('gift_received',1,202)"
        )
        conn.execute(
            "INSERT INTO users(id,telegram_id,first_name,is_premium,created_at,updated_at) "
            "VALUES (1,101,'Test',0,'2026-01-01T00:00:00Z','2026-01-01T00:00:00Z')"
        )
        conn.execute(
            "INSERT INTO birthday_entries(id,owner_id,label,month,day,revision,deleted) "
            "VALUES (1,1,'Secret Friend',5,12,2,1)"
        )
        conn.execute(
            "INSERT INTO birthday_entries(id,owner_id,label,month,day,revision,deleted) "
            "VALUES (2,1,'Active Friend',6,15,1,0)"
        )
        conn.execute("INSERT INTO bot_destinations(user_id,chat_id,active) VALUES (1,101,1)")

    upgrade_to_head_sync(url)
    with sqlite3.connect(path) as conn:
        bdays = conn.execute(
            "SELECT id,label,month,day,deleted,deleted_at FROM birthday_entries ORDER BY id"
        ).fetchall()
        assert bdays[0][:5] == (1, "", 0, 0, 1)
        assert bdays[0][5] is not None and bdays[0][5] > 0
        assert bdays[1] == (2, "Active Friend", 6, 15, 0, None)

        dest = conn.execute("SELECT user_id,active,updated_at FROM bot_destinations").fetchone()
        assert dest is not None and dest[0] == 101 and dest[1] == 1 and dest[2] > 0

        keys = conn.execute("SELECT giver_user_id,created_at FROM notice_receipt_keys").fetchone()
        expected_ts = int(datetime(2026, 1, 1, 0, 0, tzinfo=UTC).timestamp())
        assert keys == (202, expected_ts)

    command.downgrade(_configured(url), "add_deleted_session_revocations")
    with sqlite3.connect(path) as conn:
        bday_cols = {row[1] for row in conn.execute("PRAGMA table_info(birthday_entries)")}
        dest_cols = {row[1] for row in conn.execute("PRAGMA table_info(bot_destinations)")}
        key_cols = {row[1] for row in conn.execute("PRAGMA table_info(notice_receipt_keys)")}
        assert "deleted_at" not in bday_cols
        assert "updated_at" not in dest_cols
        assert "created_at" not in key_cols

    upgrade_to_head_sync(url)
    with sqlite3.connect(path) as conn:
        bday_cols = {row[1] for row in conn.execute("PRAGMA table_info(birthday_entries)")}
        assert "deleted_at" in bday_cols


def test_retention_settings_reject_non_positive_days() -> None:
    """Retention policy settings must be >= 1 day."""
    for field in (
        "birthday_retention_days",
        "bot_destination_retention_days",
        "reminder_retention_days",
        "receipt_dedup_retention_days",
    ):
        with pytest.raises(ValidationError):
            Settings.model_validate({field: 0})


async def test_deleted_birthday_purged_after_uncertain_reminder_resolved(tmp_path: Path) -> None:
    """Deleted birthday stays while reminder is uncertain/pending and is purged once resolved."""
    db = tmp_path / "bday_resolve.db"
    async with open_store(db) as store:
        settings = Settings(
            database_url=f"sqlite+aiosqlite:///{db}",
            birthday_retention_days=5,
            reminder_retention_days=5,
        )
        old_dt = datetime(2030, 1, 1, 12, 0, tzinfo=UTC)
        old_ts = int(old_dt.timestamp())
        sql_exec(
            db,
            "INSERT INTO birthday_entries(id,owner_id,label,month,day,revision,deleted,deleted_at) "
            "VALUES (10,1,'',0,0,2,1,?)",
            (old_ts,),
        )
        sql_exec(
            db,
            "INSERT INTO reminder_outbox "
            "(occurrence_key,kind,user_id,birthday_id,revision,event_date,status,"
            "attempts,next_attempt_at) "
            "VALUES ('bday:10:1:2029-12-25:7','birthday',1,10,1,'2029-12-25','uncertain',1,?)",
            (old_ts,),
        )
        notice_store = NoticeStore(store, settings)
        after_dt = old_dt + timedelta(days=10)
        stats1 = await run_cleanup_cycle(store, settings, now=after_dt, notice_store=notice_store)
        assert stats1.birthdays_purged == 0
        assert len(sql_rows(db, "SELECT id FROM birthday_entries WHERE id=10")) == 1

        # Resolve the uncertain reminder to 'sent'; subsequent cleanup purges both.
        sql_exec(db, "UPDATE reminder_outbox SET status='sent' WHERE birthday_id=10")
        stats2 = await run_cleanup_cycle(store, settings, now=after_dt, notice_store=notice_store)
        assert stats2.birthdays_purged == 1
        assert sql_rows(db, "SELECT id FROM birthday_entries WHERE id=10") == []

        # Repeated cleanup is idempotent.
        stats3 = await run_cleanup_cycle(store, settings, now=after_dt, notice_store=notice_store)
        assert stats3.birthdays_purged == 0


async def test_receipt_dedup_survives_early_outbox_purge_and_blocks_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dedup keys outlive shorter outbox retention and prevent replay duplicates until expired."""
    db = tmp_path / "dedup_replay.db"
    async with open_store(db) as store:
        settings = Settings(
            database_url=f"sqlite+aiosqlite:///{db}",
            receipt_notice_retention_days=1,
            receipt_dedup_retention_days=30,
        )
        env = _Env(store, db)
        await env.seed(3, ((GIFTER, 1),))
        await _verify_start(monkeypatch, db, GIFTER_ID)

        await env.receive(1)
        outbox = outbox_rows(db)
        assert len(outbox) == 1
        sql_exec(
            db,
            "UPDATE notification_outbox SET status='sent', updated_at='2020-01-01T00:00:00+00:00'",
        )
        sql_exec(
            db,
            "UPDATE notice_receipt_keys SET created_at=?",
            (int(datetime(2020, 1, 1, 0, 0, tzinfo=UTC).timestamp()),),
        )

        notice_store = NoticeStore(store, settings)
        # At +5 days: outbox row (>1d) is purged, but dedup key (<30d) is retained.
        mid_dt = datetime(2020, 1, 6, 0, 0, tzinfo=UTC)
        stats_mid = await run_cleanup_cycle(store, settings, now=mid_dt, notice_store=notice_store)
        assert outbox_rows(db) == []
        assert stats_mid.receipt_keys_purged == 0
        assert len(sql_rows(db, "SELECT * FROM notice_receipt_keys")) == 1

        # Replaying INSERT OR IGNORE for the same receipt key is blocked.
        async with store.engine.begin() as conn:
            from sqlalchemy import text

            res = await conn.execute(
                text(
                    "INSERT OR IGNORE INTO notice_receipt_keys"
                    "(event_type,receipt_id,giver_user_id,created_at) "
                    "VALUES (:event,:receipt,:giver,:ts)"
                ),
                {
                    "event": outbox[0]["event_type"],
                    "receipt": outbox[0]["receipt_id"],
                    "giver": GIFTER_ID,
                    "ts": int(mid_dt.timestamp()),
                },
            )
            assert res.rowcount == 0

        # At +35 days: dedup key (>30d) is physically purged.
        after_dt = datetime(2020, 2, 5, 0, 0, tzinfo=UTC)
        stats_after = await run_cleanup_cycle(
            store, settings, now=after_dt, notice_store=notice_store
        )
        assert stats_after.receipt_keys_purged == 1
        assert sql_rows(db, "SELECT * FROM notice_receipt_keys") == []
