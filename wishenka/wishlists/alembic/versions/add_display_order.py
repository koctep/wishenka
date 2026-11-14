"""Add deterministic wishlist item ordering.

Revision ID: add_display_order
Revises: add_warn_on_delete_reserved
"""

from alembic import op

revision = "add_display_order"
down_revision = "add_warn_on_delete_reserved"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE wl_items ADD COLUMN display_order INTEGER NOT NULL DEFAULT 0")


def downgrade() -> None:
    raise NotImplementedError("Downgrading this SQLite migration is not supported")
