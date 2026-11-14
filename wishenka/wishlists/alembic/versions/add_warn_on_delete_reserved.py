"""Add the reserved-item deletion preference.

Revision ID: add_warn_on_delete_reserved
Revises: base_normalized
"""

from alembic import op

revision = "add_warn_on_delete_reserved"
down_revision = "base_normalized"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE wl_lists ADD COLUMN warn_on_delete_reserved INTEGER NOT NULL DEFAULT 1")


def downgrade() -> None:
    # SQLite cannot drop a column without a table rebuild; data-safe downgrade is unsupported.
    raise NotImplementedError("Downgrading this SQLite migration is not supported")
