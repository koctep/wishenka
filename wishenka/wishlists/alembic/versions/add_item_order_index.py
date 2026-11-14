"""Index wishlist item ordering.

Revision ID: add_item_order_index
Revises: add_display_order
"""

from alembic import op

revision = "add_item_order_index"
down_revision = "add_display_order"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE INDEX idx_wl_items_order ON wl_items(wishlist_id, display_order)")


def downgrade() -> None:
    op.execute("DROP INDEX idx_wl_items_order")
