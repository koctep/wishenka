"""Preserve uncertain receipt sends without automatic retries."""

from alembic import context, op
from sqlalchemy import text

revision = "add_notice_uncertain"
down_revision = "add_birthday_reminders"
branch_labels = None
depends_on = None
ROLLBACK_POLICY = "reversible"


def upgrade() -> None:
    """Rebuild the receipt table with an explicit uncertain state."""
    add_col_sql = (
        "ALTER TABLE reminder_outbox ADD COLUMN requires_membership INTEGER NOT NULL DEFAULT 0"
    )
    if context.is_offline_mode():
        op.execute(add_col_sql)
    else:
        columns = {
            row[1] for row in op.get_bind().execute(text("PRAGMA table_info(reminder_outbox)"))
        }
        if "requires_membership" not in columns:
            op.execute(add_col_sql)
    op.execute("DROP INDEX IF EXISTS idx_notice_outbox_due")
    op.execute("ALTER TABLE notification_outbox RENAME TO notice_outbox_legacy")
    op.execute("""
        CREATE TABLE notification_outbox (
          id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT NOT NULL,
          receipt_id INTEGER NOT NULL REFERENCES wl_receipts(id) ON DELETE CASCADE,
          wishlist_id INTEGER NOT NULL REFERENCES wl_lists(id) ON DELETE CASCADE,
          wish_item_id INTEGER NOT NULL REFERENCES wl_items(id) ON DELETE CASCADE,
          giver_user_id INTEGER NOT NULL,
          status TEXT NOT NULL CHECK(status IN
              ('pending','sending','sent','failed','skipped','uncertain')),
          skip_reason TEXT, attempts INTEGER NOT NULL DEFAULT 0,
          ambiguous INTEGER NOT NULL DEFAULT 0 CHECK(ambiguous IN (0,1)),
          next_attempt_at INTEGER NOT NULL, claimed_at INTEGER, last_error_class TEXT,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
          claim_token TEXT,
          requires_membership INTEGER NOT NULL DEFAULT 0 CHECK(requires_membership IN (0,1)),
          CHECK(ambiguous=0 OR status NOT IN ('pending','sending')),
          UNIQUE(event_type,receipt_id,giver_user_id)
        )
    """)
    op.execute("""
        INSERT INTO notification_outbox
        (id,event_type,receipt_id,wishlist_id,wish_item_id,giver_user_id,status,
         skip_reason,attempts,ambiguous,next_attempt_at,claimed_at,last_error_class,
         created_at,updated_at)
        SELECT id,event_type,receipt_id,wishlist_id,wish_item_id,giver_user_id,
               CASE WHEN status IN ('pending','sending') AND ambiguous=1
                    THEN 'uncertain' ELSE status END,
               skip_reason,attempts,ambiguous,next_attempt_at,claimed_at,last_error_class,
               created_at,updated_at FROM notice_outbox_legacy
    """)
    op.execute("""
        UPDATE notification_outbox SET requires_membership=1
    """)
    op.execute("DROP TABLE notice_outbox_legacy")
    op.execute("CREATE INDEX idx_notice_outbox_due ON notification_outbox(status,next_attempt_at)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS notice_receipt_keys (
            event_type TEXT NOT NULL, receipt_id INTEGER NOT NULL
                REFERENCES wl_receipts(id) ON DELETE CASCADE,
            giver_user_id INTEGER NOT NULL,
            PRIMARY KEY(event_type,receipt_id,giver_user_id)
        )
    """)
    op.execute(
        "INSERT OR IGNORE INTO notice_receipt_keys "
        "SELECT event_type,receipt_id,giver_user_id FROM notification_outbox"
    )


def downgrade() -> None:
    """Restore the original queue schema, preserving uncertain rows as failed."""
    op.execute("ALTER TABLE reminder_outbox DROP COLUMN requires_membership")
    op.execute("DROP TABLE notice_receipt_keys")
    op.execute("DROP INDEX IF EXISTS idx_notice_outbox_due")
    op.execute("ALTER TABLE notification_outbox RENAME TO notice_outbox_current")
    op.execute("""
        CREATE TABLE notification_outbox (
          id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT NOT NULL,
          receipt_id INTEGER NOT NULL REFERENCES wl_receipts(id) ON DELETE CASCADE,
          wishlist_id INTEGER NOT NULL REFERENCES wl_lists(id) ON DELETE CASCADE,
          wish_item_id INTEGER NOT NULL REFERENCES wl_items(id) ON DELETE CASCADE,
          giver_user_id INTEGER NOT NULL,
          status TEXT NOT NULL CHECK(status IN ('pending','sending','sent','failed','skipped')),
          skip_reason TEXT, attempts INTEGER NOT NULL DEFAULT 0,
          ambiguous INTEGER NOT NULL DEFAULT 0 CHECK(ambiguous IN (0,1)),
          next_attempt_at INTEGER NOT NULL, claimed_at INTEGER, last_error_class TEXT,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
          UNIQUE(event_type,receipt_id,giver_user_id)
        )
    """)
    op.execute("""
        INSERT INTO notification_outbox
        SELECT id,event_type,receipt_id,wishlist_id,wish_item_id,giver_user_id,
               CASE WHEN status='uncertain' THEN 'failed' ELSE status END,
               skip_reason,attempts,ambiguous,next_attempt_at,claimed_at,last_error_class,
               created_at,updated_at FROM notice_outbox_current
    """)
    op.execute("DROP TABLE notice_outbox_current")
    op.execute("CREATE INDEX idx_notice_outbox_due ON notification_outbox(status,next_attempt_at)")
