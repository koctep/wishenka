"""Add durable client idempotency records table for booking and receipt mutations."""

from alembic import op

revision = "add_idempotency_records"
down_revision = "add_support_channel"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create wl_idempotency_records table and expiration index."""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS wl_idempotency_records (
            actor_id INTEGER NOT NULL,
            idempotency_key TEXT NOT NULL,
            request_hash TEXT NOT NULL,
            response_status INTEGER NOT NULL,
            response_content_type TEXT NOT NULL,
            response_body TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            PRIMARY KEY (actor_id, idempotency_key)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_wl_idempotency_expires_at
            ON wl_idempotency_records (expires_at)
        """
    )


def downgrade() -> None:
    """Drop wl_idempotency_records index and table."""
    op.execute("DROP INDEX IF EXISTS idx_wl_idempotency_expires_at")
    op.execute("DROP TABLE IF EXISTS wl_idempotency_records")
