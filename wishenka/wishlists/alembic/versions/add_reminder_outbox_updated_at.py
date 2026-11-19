"""Add updated_at retention column and index to reminder_outbox."""

from alembic import context, op
from sqlalchemy import text

revision = "add_reminder_outbox_updated_at"
down_revision = "add_bot_capture_order_retention"
branch_labels = None
depends_on = None
ROLLBACK_POLICY = "reversible"


def _columns(table: str) -> set[str]:
    """Return existing column names for ``table`` (empty set in offline mode)."""
    if context.is_offline_mode():
        return set()
    return {row[1] for row in op.get_bind().execute(text(f"PRAGMA table_info({table})"))}


def upgrade() -> None:
    """Add updated_at timestamp column, index, and backfill existing rows."""
    if "updated_at" not in _columns("reminder_outbox"):
        op.execute("ALTER TABLE reminder_outbox ADD COLUMN updated_at INTEGER")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_reminder_outbox_status_updated "
        "ON reminder_outbox(status, updated_at)"
    )
    op.execute(
        """
        UPDATE reminder_outbox
        SET updated_at = COALESCE(claimed_at, next_attempt_at)
        WHERE updated_at IS NULL
        """
    )


def downgrade() -> None:
    """Drop retention index and updated_at column from reminder_outbox."""
    op.execute("DROP INDEX IF EXISTS idx_reminder_outbox_status_updated")
    if "updated_at" in _columns("reminder_outbox"):
        op.execute("ALTER TABLE reminder_outbox DROP COLUMN updated_at")
