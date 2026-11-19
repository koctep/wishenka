"""Add retention timestamps and anonymize legacy deleted birthdays."""

from alembic import context, op
from sqlalchemy import text

revision = "add_notice_retention_columns"
down_revision = "add_deleted_session_revocations"
branch_labels = None
depends_on = None
ROLLBACK_POLICY = "reversible"


def _columns(table: str) -> set[str]:
    """Return existing column names for ``table`` (empty set in offline mode)."""
    if context.is_offline_mode():
        return set()
    return {row[1] for row in op.get_bind().execute(text(f"PRAGMA table_info({table})"))}


def upgrade() -> None:
    """Add retention timestamp columns, indexes, and backfill existing rows."""
    if "deleted_at" not in _columns("birthday_entries"):
        op.execute("ALTER TABLE birthday_entries ADD COLUMN deleted_at INTEGER")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_birthday_entries_deleted_at "
        "ON birthday_entries(deleted, deleted_at)"
    )
    op.execute(
        """
        UPDATE birthday_entries
        SET label = '',
            month = 0,
            day = 0,
            deleted_at = COALESCE(deleted_at, CAST(strftime('%s', 'now') AS INTEGER))
        WHERE deleted = 1
        """
    )

    if "updated_at" not in _columns("bot_destinations"):
        op.execute("ALTER TABLE bot_destinations ADD COLUMN updated_at INTEGER")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_bot_destinations_active_updated "
        "ON bot_destinations(active, updated_at)"
    )
    op.execute(
        """
        UPDATE bot_destinations
        SET updated_at = CAST(strftime('%s', 'now') AS INTEGER)
        WHERE updated_at IS NULL
        """
    )

    if "created_at" not in _columns("notice_receipt_keys"):
        op.execute(
            "ALTER TABLE notice_receipt_keys ADD COLUMN created_at INTEGER NOT NULL DEFAULT 0"
        )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_notice_receipt_keys_created "
        "ON notice_receipt_keys(created_at)"
    )
    op.execute(
        """
        UPDATE notice_receipt_keys
        SET created_at = COALESCE(
            (
                SELECT CAST(strftime('%s', o.created_at) AS INTEGER)
                FROM notification_outbox o
                WHERE o.event_type = notice_receipt_keys.event_type
                  AND o.receipt_id = notice_receipt_keys.receipt_id
                  AND o.giver_user_id = notice_receipt_keys.giver_user_id
            ),
            CAST(strftime('%s', 'now') AS INTEGER)
        )
        WHERE created_at = 0
        """
    )


def downgrade() -> None:
    """Drop retention indexes and timestamp columns."""
    op.execute("DROP INDEX IF EXISTS idx_notice_receipt_keys_created")
    if "created_at" in _columns("notice_receipt_keys"):
        op.execute("ALTER TABLE notice_receipt_keys DROP COLUMN created_at")

    op.execute("DROP INDEX IF EXISTS idx_bot_destinations_active_updated")
    if "updated_at" in _columns("bot_destinations"):
        op.execute("ALTER TABLE bot_destinations DROP COLUMN updated_at")

    op.execute("DROP INDEX IF EXISTS idx_birthday_entries_deleted_at")
    if "deleted_at" in _columns("birthday_entries"):
        op.execute("ALTER TABLE birthday_entries DROP COLUMN deleted_at")
