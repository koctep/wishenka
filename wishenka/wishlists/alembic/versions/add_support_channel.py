"""Add durable support input sessions and ticket rate-limit tables."""

from alembic import op

revision = "add_support_channel"
down_revision = "add_notice_uncertain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create support_input and support_tickets tables."""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS support_input (
            owner_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            PRIMARY KEY (owner_id, chat_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS support_tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_ref TEXT NOT NULL UNIQUE,
            owner_id INTEGER NOT NULL,
            telegram_id INTEGER NOT NULL,
            created_at INTEGER NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_support_tickets_owner_time
            ON support_tickets(owner_id, created_at)
        """
    )


def downgrade() -> None:
    """Drop support_tickets and support_input tables."""
    op.execute("DROP INDEX IF EXISTS idx_support_tickets_owner_time")
    op.execute("DROP TABLE IF EXISTS support_tickets")
    op.execute("DROP TABLE IF EXISTS support_input")
