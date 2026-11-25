"""Add wl_share_access table and purge legacy non-member wl_favorites rows.

Revision ID: add_share_access_and_purge_favorites
Revises: unify_user_keys_and_cascades

Schema changes (creating ``wl_share_access`` and ``idx_wl_share_access_wishlist``) are
reversible via ``downgrade()``. Purging legacy non-member rows from ``wl_favorites``
is intentionally irreversible as a security remediation so previously leaked favorite
associations cannot persist or be restored.
"""

import logging

from alembic import context, op
from sqlalchemy import text

revision = "add_share_access_and_purge_favorites"
down_revision = "unify_user_keys_and_cascades"
branch_labels = None
depends_on = None
ROLLBACK_POLICY = "reversible"

logger = logging.getLogger("wishenka.wishlists.migrations")

_PURGE_NON_MEMBER_FAVORITES_SQL = """
DELETE FROM wl_favorites
WHERE NOT EXISTS (
    SELECT 1 FROM wl_members m
    WHERE m.wishlist_id = wl_favorites.wishlist_id
      AND m.user_id = wl_favorites.user_id
)
"""


def upgrade() -> None:
    """Create wl_share_access and purge legacy non-member favorites."""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS wl_share_access (
            user_id INTEGER NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
            wishlist_id INTEGER NOT NULL REFERENCES wl_lists(id) ON DELETE CASCADE,
            public_token TEXT NOT NULL,
            granted_at TEXT NOT NULL,
            PRIMARY KEY (user_id, wishlist_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_wl_share_access_wishlist ON wl_share_access(wishlist_id)"
    )
    if context.is_offline_mode():
        op.execute(text(_PURGE_NON_MEMBER_FAVORITES_SQL))
        return

    connection = op.get_bind()
    purged = connection.execute(text(_PURGE_NON_MEMBER_FAVORITES_SQL)).rowcount
    logger.info(
        "Purged legacy non-member favorite rows",
        extra={"event": "legacy_non_member_favorites_purged", "rows": purged},
    )


def downgrade() -> None:
    """Drop wl_share_access schema (the security purge of wl_favorites is irreversible)."""
    op.execute("DROP INDEX IF EXISTS idx_wl_share_access_wishlist")
    op.execute("DROP TABLE IF EXISTS wl_share_access")
