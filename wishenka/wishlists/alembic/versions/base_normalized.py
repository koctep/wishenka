"""Create the original normalized wishlist schema.

Revision ID: base_normalized
Revises:
"""

import logging
import os

from alembic import op

revision = "base_normalized"
down_revision = None
branch_labels = None
depends_on = None
ROLLBACK_POLICY = "one-way"

_ALLOW_DESTRUCTIVE_ENV = "WISHENKA_ALLOW_DESTRUCTIVE_BASELINE_DOWNGRADE"
logger = logging.getLogger("wishenka.wishlists.migrations")


DDL = (
    """CREATE TABLE wl_lists (id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL,
    owner_name TEXT NOT NULL DEFAULT '', title TEXT NOT NULL, description TEXT,
    event_title TEXT, event_date TEXT, is_collaborative INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active', public_token TEXT NOT NULL,
    invite_token TEXT NOT NULL, invite_token_expires_at TEXT, created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL)""",
    "CREATE INDEX idx_wl_lists_owner ON wl_lists(owner_id)",
    "CREATE UNIQUE INDEX idx_wl_lists_public_token ON wl_lists(public_token)",
    "CREATE UNIQUE INDEX idx_wl_lists_invite_token ON wl_lists(invite_token)",
    "CREATE INDEX idx_wl_lists_status ON wl_lists(status)",
    """CREATE TABLE wl_members (id INTEGER PRIMARY KEY, wishlist_id INTEGER NOT NULL
    REFERENCES wl_lists(id) ON DELETE CASCADE, user_id INTEGER NOT NULL,
    role TEXT NOT NULL DEFAULT 'member', joined_at TEXT NOT NULL)""",
    "CREATE UNIQUE INDEX idx_wl_members_unique ON wl_members(wishlist_id, user_id)",
    "CREATE INDEX idx_wl_members_user ON wl_members(user_id)",
    """CREATE TABLE wl_items (id INTEGER PRIMARY KEY, wishlist_id INTEGER NOT NULL
    REFERENCES wl_lists(id) ON DELETE CASCADE, recipient_user_id INTEGER,
    recipient_name TEXT, title TEXT NOT NULL, description TEXT, link TEXT, price INTEGER,
    currency TEXT NOT NULL DEFAULT 'RUB', quantity INTEGER NOT NULL DEFAULT 1,
    received_quantity INTEGER NOT NULL DEFAULT 0, image_url TEXT, store_name TEXT,
    store_icon_url TEXT, priority TEXT NOT NULL DEFAULT 'medium', category TEXT,
    is_archived INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
    "CREATE INDEX idx_wl_items_wishlist ON wl_items(wishlist_id)",
    "CREATE INDEX idx_wl_items_recipient ON wl_items(recipient_user_id)",
    """CREATE TABLE wl_reservations (id INTEGER PRIMARY KEY, wish_item_id INTEGER NOT NULL
    REFERENCES wl_items(id) ON DELETE CASCADE, user_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1, status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
    "CREATE INDEX idx_wl_reservations_item ON wl_reservations(wish_item_id)",
    "CREATE INDEX idx_wl_reservations_user ON wl_reservations(user_id)",
    "CREATE INDEX idx_wl_reservations_status ON wl_reservations(status)",
    """CREATE TABLE wl_favorites (user_id INTEGER NOT NULL, wishlist_id INTEGER NOT NULL
    REFERENCES wl_lists(id) ON DELETE CASCADE, created_at TEXT NOT NULL,
    PRIMARY KEY (user_id, wishlist_id))""",
    "CREATE INDEX idx_wl_favorites_user ON wl_favorites(user_id)",
    """CREATE TABLE wl_view_history (id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL, wishlist_id INTEGER NOT NULL REFERENCES wl_lists(id)
    ON DELETE CASCADE, viewed_at TEXT NOT NULL)""",
    "CREATE UNIQUE INDEX wl_view_history_user_wl ON wl_view_history(user_id, wishlist_id)",
    "CREATE INDEX idx_wl_view_history_user_time ON wl_view_history(user_id, viewed_at DESC)",
    "CREATE TABLE wl_tokens (token TEXT PRIMARY KEY, wishlist_id INTEGER NOT NULL, "
    "active INTEGER NOT NULL DEFAULT 1)",
    "CREATE INDEX idx_wl_tokens_wishlist ON wl_tokens(wishlist_id, active)",
    "CREATE TABLE wl_invite_tokens (token TEXT PRIMARY KEY)",
    "CREATE TABLE wl_counters (name TEXT PRIMARY KEY, value INTEGER NOT NULL)",
)


def upgrade() -> None:
    for statement in DDL:
        op.execute(statement)


def downgrade() -> None:
    """Drop baseline tables only when explicitly opted in via environment variable."""
    if os.environ.get(_ALLOW_DESTRUCTIVE_ENV) != "1":
        logger.warning(
            "Refusing one-way downgrade of revision %s",
            revision,
            extra={"event": "wishlist_migration_downgrade_refused", "revision": revision},
        )
        raise NotImplementedError(
            "Refusing to downgrade 'base_normalized': dropping the baseline schema would destroy "
            "all core wishlist data. Restore from a database backup instead, or set "
            f"{_ALLOW_DESTRUCTIVE_ENV}=1 for disposable/test databases."
        )
    logger.warning(
        "Executing destructive baseline downgrade because %s=1",
        _ALLOW_DESTRUCTIVE_ENV,
        extra={"event": "wishlist_migration_destructive_baseline_downgrade"},
    )
    for table in (
        "wl_counters",
        "wl_invite_tokens",
        "wl_tokens",
        "wl_view_history",
        "wl_favorites",
        "wl_reservations",
        "wl_items",
        "wl_members",
        "wl_lists",
    ):
        op.execute(f"DROP TABLE {table}")
