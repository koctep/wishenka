"""Add deterministic wishlist item ordering.

Revision ID: add_display_order
Revises: add_warn_on_delete_reserved
"""

import logging

from alembic import op

revision = "add_display_order"
down_revision = "add_warn_on_delete_reserved"
branch_labels = None
depends_on = None
ROLLBACK_POLICY = "one-way"

logger = logging.getLogger("wishenka.wishlists.migrations")


def upgrade() -> None:
    op.execute("ALTER TABLE wl_items ADD COLUMN display_order INTEGER NOT NULL DEFAULT 0")


def downgrade() -> None:
    logger.warning(
        "Refusing one-way downgrade of revision %s",
        revision,
        extra={"event": "wishlist_migration_downgrade_refused", "revision": revision},
    )
    raise NotImplementedError(
        "Refusing to downgrade 'add_display_order': SQLite cannot drop a column "
        "without rebuilding the table. Restore from a database backup instead."
    )
