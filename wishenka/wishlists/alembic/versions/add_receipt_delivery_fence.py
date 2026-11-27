"""Persist unresolved receipt delivery attempts across process crashes."""

from alembic import op

revision = "add_receipt_delivery_fence"
down_revision = "add_reminder_outbox_updated_at"
branch_labels = None
depends_on = None
ROLLBACK_POLICY = "reversible"


def upgrade() -> None:
    """Create durable per-giver delivery fences."""
    op.execute(
        "CREATE TABLE IF NOT EXISTS receipt_delivery_fence ("
        "wish_item_id INTEGER NOT NULL, user_id INTEGER NOT NULL, "
        "attempt_id TEXT NOT NULL, queue TEXT NOT NULL, row_id INTEGER NOT NULL, "
        "state TEXT NOT NULL CHECK(state IN ('in_flight','uncertain')), "
        "PRIMARY KEY(wish_item_id, user_id))"
    )
    op.execute(
        "CREATE TABLE IF NOT EXISTS receipt_delivery_fence_audit ("
        "id INTEGER PRIMARY KEY, wish_item_id INTEGER NOT NULL, user_id INTEGER NOT NULL, "
        "attempt_id TEXT NOT NULL, operator TEXT NOT NULL, evidence TEXT NOT NULL, "
        "resolved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    )


def downgrade() -> None:
    """Remove delivery fences."""
    op.execute("DROP TABLE receipt_delivery_fence_audit")
    op.execute("DROP TABLE receipt_delivery_fence")
