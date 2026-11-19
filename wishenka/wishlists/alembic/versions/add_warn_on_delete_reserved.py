"""Add the reserved-item deletion preference.

Revision ID: add_warn_on_delete_reserved
Revises: base_normalized
"""

import logging

from alembic import op

revision = "add_warn_on_delete_reserved"
down_revision = "base_normalized"
branch_labels = None
depends_on = None
ROLLBACK_POLICY = "one-way"

logger = logging.getLogger("wishenka.wishlists.migrations")


def upgrade() -> None:
    op.execute("ALTER TABLE wl_lists ADD COLUMN warn_on_delete_reserved INTEGER NOT NULL DEFAULT 1")


def downgrade() -> None:
    # SQLite cannot drop a column without a table rebuild; data-safe downgrade is unsupported.
    logger.warning(
        "Refusing one-way downgrade of revision %s",
        revision,
        extra={"event": "wishlist_migration_downgrade_refused", "revision": revision},
    )
    raise NotImplementedError(
        "Refusing to downgrade 'add_warn_on_delete_reserved': SQLite cannot drop a column "
        "without rebuilding the table. Restore from a database backup instead."
    )
