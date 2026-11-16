"""Persist private bot drafts and idempotent save receipts."""

from alembic import op

revision = "add_bot_drafts"
down_revision = "add_notice_outbox"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the bot capture state table."""
    op.execute("""
        CREATE TABLE IF NOT EXISTS bot_drafts (
            id TEXT PRIMARY KEY, owner INTEGER NOT NULL, chat INTEGER NOT NULL,
            revision INTEGER NOT NULL, state TEXT NOT NULL, data TEXT NOT NULL,
            list_id INTEGER, edit_field TEXT, expires TEXT NOT NULL,
            receipt_list_id INTEGER, receipt_item_id INTEGER
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_bot_drafts_owner ON bot_drafts(owner, chat, state)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_bot_drafts_expiry ON bot_drafts(expires)")


def downgrade() -> None:
    """Remove capture state."""
    op.execute("DROP TABLE bot_drafts")
