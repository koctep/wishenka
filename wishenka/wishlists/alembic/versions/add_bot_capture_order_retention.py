"""Add updated_at retention column and index to bot_capture_order."""

from alembic import context, op
from sqlalchemy import text

revision = "add_bot_capture_order_retention"
down_revision = "add_user_fk_cascades"
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
    if "updated_at" not in _columns("bot_capture_order"):
        op.execute("ALTER TABLE bot_capture_order ADD COLUMN updated_at INTEGER")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_bot_capture_order_updated_at "
        "ON bot_capture_order(updated_at)"
    )
    op.execute(
        """
        UPDATE bot_capture_order
        SET updated_at = CAST(strftime('%s', 'now') AS INTEGER)
        WHERE updated_at IS NULL
        """
    )


def downgrade() -> None:
    """Drop retention index and updated_at column from bot_capture_order."""
    op.execute("DROP INDEX IF EXISTS idx_bot_capture_order_updated_at")
    if "updated_at" in _columns("bot_capture_order"):
        op.execute("ALTER TABLE bot_capture_order DROP COLUMN updated_at")
