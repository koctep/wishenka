"""Persist the latest received capture message per private conversation."""

from alembic import op

revision = "add_bot_capture_order"
down_revision = "add_bot_drafts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create durable ordering watermarks for concurrently processed messages."""
    op.execute("""
        CREATE TABLE IF NOT EXISTS bot_capture_order (
            owner INTEGER NOT NULL, chat INTEGER NOT NULL, message_id INTEGER NOT NULL,
            PRIMARY KEY (owner, chat)
        )
    """)


def downgrade() -> None:
    """Remove the ordering watermarks."""
    op.execute("DROP TABLE bot_capture_order")
