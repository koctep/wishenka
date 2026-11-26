"""Add a monotonic recording sequence for equal view times.

Revision ID: add_view_history_recorded_seq
Revises: purge_legacy_non_member_view_history
"""

from alembic import context, op
from sqlalchemy import text

revision = "add_view_history_recorded_seq"
down_revision = "purge_legacy_non_member_view_history"
branch_labels = None
depends_on = None
ROLLBACK_POLICY = "reversible"

_INDEX = "idx_wl_view_history_user_time"
_COUNTER = "view_history_seq"


def _columns(table: str) -> set[str]:
    """Return existing column names for ``table`` (empty set in offline mode)."""
    if context.is_offline_mode():
        return set()
    return {row[1] for row in op.get_bind().execute(text(f"PRAGMA table_info({table})"))}


def upgrade() -> None:
    """Add recorded_seq, backfill it, and order the history index by that sequence."""
    if "recorded_seq" not in _columns("wl_view_history"):
        op.execute("ALTER TABLE wl_view_history ADD COLUMN recorded_seq INTEGER NOT NULL DEFAULT 0")
    # Fill the new column once. Later recordings replace it from the counter.
    op.execute("UPDATE wl_view_history SET recorded_seq = id WHERE recorded_seq = 0")
    op.execute(f"DROP INDEX IF EXISTS {_INDEX}")
    op.execute(
        f"CREATE INDEX {_INDEX} ON wl_view_history(user_id, viewed_at DESC, recorded_seq DESC)"
    )
    # INSERT ... SELECT ... ON CONFLICT is a syntax error on this SQLite build.
    op.execute(
        "INSERT INTO wl_counters (name, value) VALUES ("
        f"'{_COUNTER}', "
        "(SELECT COALESCE(MAX(recorded_seq), 0) FROM wl_view_history)"
        ") ON CONFLICT(name) DO UPDATE SET value = excluded.value"
    )


def downgrade() -> None:
    """Restore the time-only history index and drop recorded_seq."""
    op.execute(f"DROP INDEX IF EXISTS {_INDEX}")
    op.execute(f"CREATE INDEX {_INDEX} ON wl_view_history(user_id, viewed_at DESC)")
    if context.is_offline_mode() or "recorded_seq" in _columns("wl_view_history"):
        op.execute("ALTER TABLE wl_view_history DROP COLUMN recorded_seq")
    op.execute(f"DELETE FROM wl_counters WHERE name = '{_COUNTER}'")
