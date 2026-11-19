"""Add deleted_session_revocations table for stateless token revocation."""

from alembic import op

revision = "add_deleted_session_revocations"
down_revision = "add_user_locale"
branch_labels = None
depends_on = None
ROLLBACK_POLICY = "reversible"


def upgrade() -> None:
    """Create deleted_session_revocations table and expiration index."""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS deleted_session_revocations (
            subject_hash TEXT PRIMARY KEY,
            revoked_before INTEGER NOT NULL,
            expires_at INTEGER NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_deleted_session_revocations_expires
            ON deleted_session_revocations(expires_at)
        """
    )


def downgrade() -> None:
    """Drop deleted_session_revocations table."""
    op.execute("DROP INDEX IF EXISTS idx_deleted_session_revocations_expires")
    op.execute("DROP TABLE IF EXISTS deleted_session_revocations")
