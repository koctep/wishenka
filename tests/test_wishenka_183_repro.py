"""Failing repro tests for WISHENKA-183: bounded batched purge and reminder_outbox.updated_at."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from tests.receipt_support import open_store, sql_exec, sql_rows
from wishenka.config import Settings
from wishenka.notices.store import NoticeStore

pytestmark = pytest.mark.timeout(30)


def _seed_receipt_chain(db: Path, count: int) -> None:
    """Seed minimal wishlist/item/receipt rows so notification_outbox FKs are satisfied."""
    ts = "2026-01-01T00:00:00+00:00"
    sql_exec(
        db,
        "INSERT INTO wl_lists(id, owner_id, title, public_token, invite_token, "
        "created_at, updated_at) VALUES (1, 101, 'List', 'pub', 'inv', ?, ?)",
        (ts, ts),
    )
    sql_exec(
        db,
        "INSERT INTO wl_items(id, wishlist_id, title, created_at, updated_at) "
        "VALUES (1, 1, 'Item', ?, ?)",
        (ts, ts),
    )
    for receipt_id in range(1, count + 1):
        sql_exec(
            db,
            "INSERT INTO wl_receipts(id, wish_item_id, quantity, received_at) VALUES (?, 1, 1, ?)",
            (receipt_id, ts),
        )


async def test_purge_finished_validates_non_positive_batch_size(tmp_path: Path) -> None:
    """NoticeStore.purge_finished rejects batch_size <= 0 with ValueError."""
    db = tmp_path / "batch_validation.db"
    async with open_store(db) as store:
        settings = Settings(database_url=f"sqlite+aiosqlite:///{db}")
        notice_store = NoticeStore(store, settings)
        now = datetime(2030, 1, 10, 12, 0, tzinfo=UTC)
        threshold = now - timedelta(days=7)

        for invalid in (0, -1):
            with pytest.raises(ValueError, match="batch_size"):
                await notice_store.purge_finished(threshold, now=now, batch_size=invalid)


async def test_purge_finished_drains_both_outboxes_and_preserves_protected_rows(
    tmp_path: Path,
) -> None:
    """purge_finished drains >batch_size rows across multiple transactions."""
    db = tmp_path / "batched_purge.db"
    async with open_store(db) as store:
        settings = Settings(database_url=f"sqlite+aiosqlite:///{db}")
        notice_store = NoticeStore(store, settings)

        now = datetime(2030, 1, 20, 12, 0, tzinfo=UTC)
        threshold = now - timedelta(days=7)
        old_iso = (threshold - timedelta(days=1)).isoformat()
        fresh_iso = (threshold + timedelta(days=1)).isoformat()
        old_epoch = int((threshold - timedelta(days=1)).timestamp())
        fresh_epoch = int((threshold + timedelta(days=1)).timestamp())
        past_event = "2030-01-10"
        active_event = "2030-01-25"

        _seed_receipt_chain(db, 10)

        # 5 expired terminal notification_outbox rows + 2 protected rows.
        terminal_statuses = ("sent", "skipped", "failed", "sent", "failed")
        for idx, status in enumerate(terminal_statuses, start=1):
            sql_exec(
                db,
                "INSERT INTO notification_outbox "
                "(id, event_type, receipt_id, wishlist_id, wish_item_id, giver_user_id, "
                "status, ambiguous, next_attempt_at, created_at, updated_at) "
                "VALUES (?, 'gift_received', ?, 1, 1, 202, ?, 0, ?, ?, ?)",
                (idx, idx, status, old_epoch, old_iso, old_iso),
            )
        sql_exec(
            db,
            "INSERT INTO notification_outbox "
            "(id, event_type, receipt_id, wishlist_id, wish_item_id, giver_user_id, "
            "status, ambiguous, next_attempt_at, created_at, updated_at) "
            "VALUES (6, 'gift_received', 6, 1, 1, 202, 'pending', 0, ?, ?, ?)",
            (old_epoch, old_iso, old_iso),
        )
        sql_exec(
            db,
            "INSERT INTO notification_outbox "
            "(id, event_type, receipt_id, wishlist_id, wish_item_id, giver_user_id, "
            "status, ambiguous, next_attempt_at, created_at, updated_at) "
            "VALUES (7, 'gift_received', 7, 1, 1, 202, 'sent', 0, ?, ?, ?)",
            (fresh_epoch, fresh_iso, fresh_iso),
        )

        # 5 expired terminal reminder_outbox rows + 3 protected rows.
        for idx, status in enumerate(terminal_statuses, start=1):
            sql_exec(
                db,
                "INSERT INTO reminder_outbox "
                "(occurrence_key, kind, user_id, birthday_id, revision, event_date, "
                "status, attempts, next_attempt_at) "
                "VALUES (?, 'birthday', 101, ?, 1, ?, ?, 1, ?)",
                (f"bday:expired:{idx}", idx, past_event, status, old_epoch),
            )
        # Protected 1: non-terminal (uncertain) even though old.
        sql_exec(
            db,
            "INSERT INTO reminder_outbox "
            "(occurrence_key, kind, user_id, birthday_id, revision, event_date, "
            "status, attempts, next_attempt_at) "
            "VALUES ('bday:uncertain', 'birthday', 101, 99, 1, ?, 'uncertain', 1, ?)",
            (past_event, old_epoch),
        )
        # Protected 2: terminal but fresh.
        sql_exec(
            db,
            "INSERT INTO reminder_outbox "
            "(occurrence_key, kind, user_id, birthday_id, revision, event_date, "
            "status, attempts, next_attempt_at) "
            "VALUES ('bday:fresh', 'birthday', 101, 100, 1, ?, 'sent', 1, ?)",
            (past_event, fresh_epoch),
        )
        # Protected 3: terminal and old, but active-cycle occasion reminder.
        sql_exec(
            db,
            "INSERT INTO reminder_outbox "
            "(occurrence_key, kind, user_id, list_id, revision, event_date, "
            "status, attempts, next_attempt_at) "
            "VALUES ('occasion:1:101:2030-01-25:7', 'list', 101, 1, 1, ?, 'sent', 1, ?)",
            (active_event, old_epoch),
        )

        # Spy on store.transaction to verify bounded multi-transaction execution.
        original_transaction = store.transaction
        per_tx_remaining: list[tuple[int, int]] = []

        async def tracked_transaction(work: Callable[[Any], Any]) -> Any:
            result = await original_transaction(work)
            r_left = len(sql_rows(db, "SELECT id FROM notification_outbox"))
            m_left = len(sql_rows(db, "SELECT id FROM reminder_outbox"))
            per_tx_remaining.append((r_left, m_left))
            return result

        store.transaction = tracked_transaction  # type: ignore[method-assign]

        deleted = await notice_store.purge_finished(threshold, now=now, batch_size=2)

        assert deleted == 10
        # 5 expired rows with batch_size=2 requires 3 batches (2 + 2 + 1).
        assert len(per_tx_remaining) >= 3
        # First batch must not delete more than batch_size=2 from either table (7->5, 8->6).
        assert per_tx_remaining[0][0] >= 5
        assert per_tx_remaining[0][1] >= 6

        remaining_receipts = {
            row["id"] for row in sql_rows(db, "SELECT id FROM notification_outbox")
        }
        assert remaining_receipts == {6, 7}

        remaining_reminders = {
            row["occurrence_key"]
            for row in sql_rows(db, "SELECT occurrence_key FROM reminder_outbox")
        }
        assert remaining_reminders == {
            "bday:uncertain",
            "bday:fresh",
            "occasion:1:101:2030-01-25:7",
        }


async def test_reminder_outbox_has_updated_at_column_index_and_coalesce_retention(
    tmp_path: Path,
) -> None:
    """reminder_outbox has updated_at + index and uses COALESCE(updated_at, next_attempt_at)."""
    db = tmp_path / "reminder_updated_at.db"
    async with open_store(db) as store:
        settings = Settings(database_url=f"sqlite+aiosqlite:///{db}")
        notice_store = NoticeStore(store, settings)

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

        now = datetime(2030, 1, 20, 12, 0, tzinfo=UTC)
        threshold = now - timedelta(days=7)
        old_epoch = int((threshold - timedelta(days=1)).timestamp())
        fresh_epoch = int((threshold + timedelta(days=1)).timestamp())
        past_event = "2030-01-10"

        # 1. updated_at fresh, next_attempt_at old -> must be preserved.
        sql_exec(
            db,
            "INSERT INTO reminder_outbox "
            "(occurrence_key, kind, user_id, birthday_id, revision, event_date, "
            "status, attempts, next_attempt_at, updated_at) "
            "VALUES ('rem:fresh-updated', 'birthday', 101, 1, 1, ?, 'sent', 1, ?, ?)",
            (past_event, old_epoch, fresh_epoch),
        )
        # 2. updated_at old, next_attempt_at fresh -> must be purged.
        sql_exec(
            db,
            "INSERT INTO reminder_outbox "
            "(occurrence_key, kind, user_id, birthday_id, revision, event_date, "
            "status, attempts, next_attempt_at, updated_at) "
            "VALUES ('rem:old-updated', 'birthday', 101, 2, 1, ?, 'sent', 1, ?, ?)",
            (past_event, fresh_epoch, old_epoch),
        )
        # 3. updated_at NULL, next_attempt_at old -> COALESCE falls back and purges.
        sql_exec(
            db,
            "INSERT INTO reminder_outbox "
            "(occurrence_key, kind, user_id, birthday_id, revision, event_date, "
            "status, attempts, next_attempt_at, updated_at) "
            "VALUES ('rem:null-old', 'birthday', 101, 3, 1, ?, 'failed', 1, ?, NULL)",
            (past_event, old_epoch),
        )
        # 4. updated_at NULL, next_attempt_at fresh -> COALESCE falls back and preserves.
        sql_exec(
            db,
            "INSERT INTO reminder_outbox "
            "(occurrence_key, kind, user_id, birthday_id, revision, event_date, "
            "status, attempts, next_attempt_at, updated_at) "
            "VALUES ('rem:null-fresh', 'birthday', 101, 4, 1, ?, 'skipped', 1, ?, NULL)",
            (past_event, fresh_epoch),
        )

        deleted = await notice_store.purge_finished(threshold, now=now, batch_size=10)
        assert deleted == 2

        remaining = {
            row["occurrence_key"]
            for row in sql_rows(db, "SELECT occurrence_key FROM reminder_outbox")
        }
        assert remaining == {"rem:fresh-updated", "rem:null-fresh"}
