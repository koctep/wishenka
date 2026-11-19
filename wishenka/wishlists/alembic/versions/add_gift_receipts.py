"""Receipt history for gifted wishes.

Revision ID: add_gift_receipts
Revises: add_item_order_index

Creates ``wl_receipts`` (one row per receipt act, no giver column and no link to a reservation),
back-fills one *approximate* record per legacy wish that already has ``received_quantity > 0``
(the date is the wish's last update, so it is flagged ``is_approximate = 1``), and normalises
legacy archived rows whose quantity is fully received (a fully received wish is never archived).

The revision is safe to repeat after a partial failure. It is irreversible by design: a
downgrade could not tell which archived rows were normalised, and dropping the table would
lose receipt history.
"""

import logging

from alembic import context, op
from sqlalchemy import text

revision = "add_gift_receipts"
down_revision = "add_item_order_index"
branch_labels = None
depends_on = None
ROLLBACK_POLICY = "one-way"

logger = logging.getLogger("wishenka.wishlists.migrations")

_BACKFILL = """
INSERT INTO wl_receipts (wish_item_id, quantity, received_at, is_approximate)
SELECT i.id, i.received_quantity, i.updated_at, 1 FROM wl_items i
WHERE i.received_quantity > 0
  AND NOT EXISTS (SELECT 1 FROM wl_receipts r WHERE r.wish_item_id = i.id)
"""
_NORMALISE = """
UPDATE wl_items SET is_archived = 0
WHERE is_archived = 1 AND received_quantity > 0 AND received_quantity >= quantity
"""


def upgrade() -> None:
    """Create the receipt table, back-fill legacy receipts and normalise archived rows."""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS wl_receipts (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          wish_item_id INTEGER NOT NULL REFERENCES wl_items(id) ON DELETE CASCADE,
          quantity INTEGER NOT NULL CHECK (quantity >= 1),
          received_at TEXT NOT NULL,
          is_approximate INTEGER NOT NULL DEFAULT 0 CHECK (is_approximate IN (0, 1))
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_wl_receipts_item "
        "ON wl_receipts(wish_item_id, received_at, id)"
    )
    if context.is_offline_mode():
        op.execute(text(_BACKFILL))
        op.execute(text(_NORMALISE))
        return

    connection = op.get_bind()
    backfilled = connection.execute(text(_BACKFILL)).rowcount
    logger.info(
        "Legacy receipts back-filled",
        extra={"event": "legacy_receipts_backfilled", "rows": backfilled},
    )
    normalised = connection.execute(text(_NORMALISE)).rowcount
    logger.info(
        "Legacy archived rows normalised",
        extra={"event": "legacy_archived_rows_normalised", "rows": normalised},
    )


def downgrade() -> None:
    """Refuse to downgrade: the normalisation and the history cannot be restored."""
    logger.warning(
        "Refusing one-way downgrade of revision %s",
        revision,
        extra={"event": "wishlist_migration_downgrade_refused", "revision": revision},
    )
    raise NotImplementedError(
        "Refusing to downgrade 'add_gift_receipts': receipt backfill and archived-row "
        "normalisation are irreversible. Restore from a database backup instead."
    )
