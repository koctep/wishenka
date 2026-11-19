"""Notice queue and its two lookup-only settings tables.

Revision ID: add_notice_outbox
Revises: add_gift_receipts

``notification_outbox`` is the transactional outbox of giver notices (one event type today).
The two settings tables are read by the receipt producer; no production code writes them.
"""

from alembic import op

revision = "add_notice_outbox"
down_revision = "add_gift_receipts"
branch_labels = None
depends_on = None
ROLLBACK_POLICY = "reversible"

_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS notification_outbox (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      event_type TEXT NOT NULL,
      receipt_id INTEGER NOT NULL REFERENCES wl_receipts(id) ON DELETE CASCADE,
      wishlist_id INTEGER NOT NULL REFERENCES wl_lists(id) ON DELETE CASCADE,
      wish_item_id INTEGER NOT NULL REFERENCES wl_items(id) ON DELETE CASCADE,
      giver_user_id INTEGER NOT NULL,
      status TEXT NOT NULL
        CHECK (status IN ('pending', 'sending', 'sent', 'failed', 'skipped')),
      skip_reason TEXT,
      attempts INTEGER NOT NULL DEFAULT 0,
      ambiguous INTEGER NOT NULL DEFAULT 0 CHECK (ambiguous IN (0, 1)),
      next_attempt_at INTEGER NOT NULL,
      claimed_at INTEGER,
      last_error_class TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      UNIQUE (event_type, receipt_id, giver_user_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_notice_outbox_due "
    "ON notification_outbox(status, next_attempt_at)",
    """
    CREATE TABLE IF NOT EXISTS user_notification_settings (
      user_id INTEGER NOT NULL,
      event_type TEXT NOT NULL,
      enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
      updated_at TEXT NOT NULL,
      PRIMARY KEY (user_id, event_type)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS wl_list_notification_settings (
      user_id INTEGER NOT NULL,
      wishlist_id INTEGER NOT NULL REFERENCES wl_lists(id) ON DELETE CASCADE,
      event_type TEXT NOT NULL,
      enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
      updated_at TEXT NOT NULL,
      PRIMARY KEY (user_id, wishlist_id, event_type)
    )
    """,
)


def upgrade() -> None:
    """Create the outbox and the two settings tables."""
    for statement in _STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    """Drop the notice tables."""
    op.execute("DROP TABLE IF EXISTS wl_list_notification_settings")
    op.execute("DROP TABLE IF EXISTS user_notification_settings")
    op.execute("DROP TABLE IF EXISTS notification_outbox")
