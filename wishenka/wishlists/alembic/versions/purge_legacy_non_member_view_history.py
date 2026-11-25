"""Purge legacy non-member wl_view_history rows without verified share access.

Revision ID: purge_legacy_non_member_view_history
Revises: add_share_access_and_purge_favorites

Purging legacy ``wl_view_history`` rows where the user is neither the wishlist owner,
nor a current member, nor a holder of a valid ``wl_share_access`` grant matching
``wl_lists.public_token`` is intentionally irreversible as a security remediation so
previously leaked viewing history associations cannot persist or be restored.
"""

import logging

from alembic import context, op
from sqlalchemy import text

revision = "purge_legacy_non_member_view_history"
down_revision = "add_share_access_and_purge_favorites"
branch_labels = None
depends_on = None
ROLLBACK_POLICY = "one-way"

logger = logging.getLogger("wishenka.wishlists.migrations")

_PURGE_NON_MEMBER_VIEW_HISTORY_SQL = """
DELETE FROM wl_view_history
WHERE NOT EXISTS (
    SELECT 1 FROM wl_lists l
    WHERE l.id = wl_view_history.wishlist_id
      AND (
          l.owner_id = wl_view_history.user_id
          OR EXISTS (
              SELECT 1 FROM wl_members m
              WHERE m.wishlist_id = l.id AND m.user_id = wl_view_history.user_id
          )
          OR EXISTS (
              SELECT 1 FROM wl_share_access sa
              WHERE sa.wishlist_id = l.id
                AND sa.user_id = wl_view_history.user_id
                AND sa.public_token = l.public_token
          )
      )
)
"""


def upgrade() -> None:
    """Purge legacy unverified non-member rows from wl_view_history."""
    if context.is_offline_mode():
        op.execute(text(_PURGE_NON_MEMBER_VIEW_HISTORY_SQL))
        return

    connection = op.get_bind()
    purged = connection.execute(text(_PURGE_NON_MEMBER_VIEW_HISTORY_SQL)).rowcount
    logger.info(
        "Purged legacy unverified non-member view history rows",
        extra={"event": "legacy_non_member_view_history_purged", "rows": purged},
    )


def downgrade() -> None:
    """Refuse downgrade because purging legacy unverified view history is irreversible."""
    logger.warning(
        "Refusing one-way downgrade of revision %s",
        revision,
        extra={"event": "wishlist_migration_downgrade_refused", "revision": revision},
    )
    raise NotImplementedError(
        "Refusing to downgrade 'purge_legacy_non_member_view_history': purging legacy "
        "unverified wl_view_history rows is an irreversible security remediation. "
        "Restore from a database backup instead."
    )
