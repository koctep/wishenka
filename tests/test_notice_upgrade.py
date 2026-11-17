"""Existing receipt queue rows survive the uncertain-state migration."""

import sqlite3
from pathlib import Path

import pytest
from alembic import command

from wishenka.wishlists.migrations import _configured, upgrade_to_head_sync

pytestmark = pytest.mark.timeout(60)


def test_legacy_queue_upgrade_preserves_receipts_and_quarantines_ambiguity(tmp_path: Path) -> None:
    path = tmp_path / "upgrade.db"
    url = f"sqlite+aiosqlite:///{path}"
    command.upgrade(_configured(url), "add_bot_capture_order")
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO wl_lists(id,owner_id,title,public_token,invite_token,"
            "created_at,updated_at) "
            "VALUES (1,101,'list','p','i','2026-01-01','2026-01-01')"
        )
        conn.execute(
            "INSERT INTO wl_items(id,wishlist_id,title,created_at,updated_at) "
            "VALUES (1,1,'wish','2026-01-01','2026-01-01')"
        )
        conn.execute(
            "INSERT INTO wl_receipts(id,wish_item_id,quantity,received_at) "
            "VALUES (1,1,1,'2026-01-01')"
        )
        for ident, status, ambiguous in ((1, "pending", 0), (2, "pending", 1), (3, "sent", 0)):
            conn.execute(
                "INSERT INTO notification_outbox "
                "(id,event_type,receipt_id,wishlist_id,wish_item_id,giver_user_id,status,"
                "ambiguous,next_attempt_at,created_at,updated_at) "
                "VALUES (?,'gift_received',1,1,1,?,?,?,10,'2026-01-01','2026-01-01')",
                (ident, ident + 200, status, ambiguous),
            )
    upgrade_to_head_sync(url)
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT id,status FROM notification_outbox ORDER BY id").fetchall() == [
            (1, "pending"),
            (2, "uncertain"),
            (3, "sent"),
        ]
        assert conn.execute(
            "SELECT requires_membership FROM notification_outbox ORDER BY id"
        ).fetchall() == [(1,), (1,), (1,)]
        assert conn.execute("SELECT count(*) FROM wl_receipts").fetchone() == (1,)
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE notification_outbox SET status='pending',ambiguous=1 WHERE id=2")
    command.downgrade(_configured(url), "add_birthday_reminders")
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT id,status FROM notification_outbox ORDER BY id").fetchall() == [
            (1, "pending"),
            (2, "failed"),
            (3, "sent"),
        ]
        assert "claim_token" not in {
            row[1] for row in conn.execute("PRAGMA table_info(notification_outbox)")
        }
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
