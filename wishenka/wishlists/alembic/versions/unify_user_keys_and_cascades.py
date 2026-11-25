"""Unify user foreign keys on users.telegram_id and add cascade deletes."""

import logging

from alembic import context, op
from sqlalchemy import text

logger = logging.getLogger("wishenka.wishlists.migrations")

revision = "unify_user_keys_and_cascades"
down_revision = "add_receipt_delivery_fence"
branch_labels = None
depends_on = None
ROLLBACK_POLICY = "reversible"

_ENSURE_USERS_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL UNIQUE,
    first_name TEXT NOT NULL,
    last_name TEXT,
    username TEXT,
    language_code TEXT,
    locale TEXT NOT NULL DEFAULT 'en' CHECK (locale IN ('ru', 'en')),
    locale_source TEXT NOT NULL DEFAULT 'auto' CHECK (locale_source IN ('auto', 'explicit')),
    birth_day INTEGER,
    birth_month INTEGER,
    birth_year INTEGER,
    birthdate_source TEXT NOT NULL DEFAULT 'auto' CHECK (birthdate_source IN ('auto', 'explicit')),
    is_premium INTEGER NOT NULL DEFAULT 0 CHECK (is_premium IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""


def _ensure_users_columns() -> None:
    """Consolidate users DDL and birthdate columns in Alembic."""
    if context.is_offline_mode():
        op.execute(_ENSURE_USERS_SQL)
        op.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id)")
        op.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
        return

    bind = op.get_bind()
    bind.exec_driver_sql(_ENSURE_USERS_SQL)
    bind.exec_driver_sql(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id)"
    )
    bind.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")

    columns = {row[1] for row in bind.exec_driver_sql("PRAGMA table_info(users)").fetchall()}
    added_columns: list[str] = []
    if "birth_day" not in columns:
        bind.exec_driver_sql("ALTER TABLE users ADD COLUMN birth_day INTEGER")
        added_columns.append("birth_day")
    if "birth_month" not in columns:
        bind.exec_driver_sql("ALTER TABLE users ADD COLUMN birth_month INTEGER")
        added_columns.append("birth_month")
    if "birth_year" not in columns:
        bind.exec_driver_sql("ALTER TABLE users ADD COLUMN birth_year INTEGER")
        added_columns.append("birth_year")
    if "birthdate_source" not in columns:
        bind.exec_driver_sql(
            "ALTER TABLE users ADD COLUMN birthdate_source TEXT NOT NULL DEFAULT 'auto' "
            "CHECK (birthdate_source IN ('auto', 'explicit'))"
        )
        added_columns.append("birthdate_source")
    if added_columns:
        logger.info(
            "Added missing birthdate columns to users",
            extra={
                "event": "unify_user_keys_users_columns_added",
                "columns": added_columns,
            },
        )


def _rebuild(
    table: str,
    create_sql: str,
    insert_sql: str,
    *,
    drop_indexes: tuple[str, ...] = (),
    create_indexes: tuple[str, ...] = (),
) -> int:
    """Rebuild ``table`` atomically via a temporary ``_legacy`` rename."""
    legacy = f"{table}_legacy"
    for idx in drop_indexes:
        op.execute(f"DROP INDEX IF EXISTS {idx}")
    op.execute(f"ALTER TABLE {table} RENAME TO {legacy}")
    op.execute(create_sql)
    removed_orphans = 0
    if context.is_offline_mode():
        op.execute(insert_sql.format(legacy=legacy))
    else:
        bind = op.get_bind()
        total_rows = int(bind.execute(text(f"SELECT COUNT(*) FROM {legacy}")).scalar_one())
        inserted = bind.execute(text(insert_sql.format(legacy=legacy)))
        kept_rows = max(0, int(inserted.rowcount or 0))
        removed_orphans = max(0, total_rows - kept_rows)
        if removed_orphans > 0:
            logger.warning(
                "Cleaned orphaned rows during table rebuild",
                extra={
                    "event": "unify_user_keys_orphans_cleaned",
                    "table": table,
                    "rows_removed": removed_orphans,
                    "rows_kept": kept_rows,
                },
            )
        else:
            logger.info(
                "Rebuilt table during user key unification",
                extra={
                    "event": "unify_user_keys_table_rebuilt",
                    "table": table,
                    "rows_kept": kept_rows,
                },
            )
    op.execute(f"DROP TABLE {legacy}")
    for idx_sql in create_indexes:
        op.execute(idx_sql)
    return removed_orphans


def upgrade() -> None:
    """Migrate user FKs to users.telegram_id and add cascade FKs on tokens and reminders."""
    _ensure_users_columns()
    total_orphans_removed = 0

    total_orphans_removed += _rebuild(
        "bot_destinations",
        """
        CREATE TABLE bot_destinations (
            user_id INTEGER PRIMARY KEY REFERENCES users(telegram_id) ON DELETE CASCADE,
            chat_id INTEGER NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            updated_at INTEGER
        )
        """,
        """
        INSERT INTO bot_destinations (user_id, chat_id, active, updated_at)
        SELECT u.telegram_id, d.chat_id, d.active, d.updated_at
        FROM {legacy} d
        JOIN users u ON u.id = d.user_id
        """,
        drop_indexes=("idx_bot_destinations_active_updated",),
        create_indexes=(
            "CREATE INDEX idx_bot_destinations_active_updated "
            "ON bot_destinations(active, updated_at)",
        ),
    )

    total_orphans_removed += _rebuild(
        "birthday_entries",
        """
        CREATE TABLE birthday_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
            label TEXT NOT NULL,
            month INTEGER NOT NULL,
            day INTEGER NOT NULL,
            revision INTEGER NOT NULL DEFAULT 1,
            deleted INTEGER NOT NULL DEFAULT 0,
            deleted_at INTEGER
        )
        """,
        """
        INSERT INTO birthday_entries
            (id, owner_id, label, month, day, revision, deleted, deleted_at)
        SELECT b.id, u.telegram_id, b.label, b.month, b.day, b.revision, b.deleted, b.deleted_at
        FROM {legacy} b
        JOIN users u ON u.id = b.owner_id
        """,
        drop_indexes=("idx_birthday_entries_deleted_at",),
        create_indexes=(
            "CREATE INDEX idx_birthday_entries_deleted_at ON birthday_entries(deleted, deleted_at)",
        ),
    )

    total_orphans_removed += _rebuild(
        "birthday_input",
        """
        CREATE TABLE birthday_input (
            owner_id INTEGER NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
            chat_id INTEGER NOT NULL,
            entry_id INTEGER,
            revision INTEGER,
            stage TEXT NOT NULL,
            label TEXT,
            expires_at INTEGER NOT NULL,
            PRIMARY KEY (owner_id, chat_id)
        )
        """,
        """
        INSERT INTO birthday_input
            (owner_id, chat_id, entry_id, revision, stage, label, expires_at)
        SELECT u.telegram_id, bi.chat_id, bi.entry_id, bi.revision,
               bi.stage, bi.label, bi.expires_at
        FROM {legacy} bi
        JOIN users u ON u.id = bi.owner_id
        """,
    )

    total_orphans_removed += _rebuild(
        "support_input",
        """
        CREATE TABLE support_input (
            owner_id INTEGER NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
            chat_id INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            PRIMARY KEY (owner_id, chat_id)
        )
        """,
        """
        INSERT INTO support_input (owner_id, chat_id, expires_at)
        SELECT u.telegram_id, si.chat_id, si.expires_at
        FROM {legacy} si
        JOIN users u ON u.id = si.owner_id
        """,
    )

    total_orphans_removed += _rebuild(
        "support_tickets",
        """
        CREATE TABLE support_tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_ref TEXT NOT NULL UNIQUE,
            telegram_id INTEGER NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
            created_at INTEGER NOT NULL
        )
        """,
        """
        INSERT INTO support_tickets (id, ticket_ref, telegram_id, created_at)
        SELECT st.id, st.ticket_ref, u.telegram_id, st.created_at
        FROM {legacy} st
        JOIN users u ON u.telegram_id = st.telegram_id
        """,
        drop_indexes=("idx_support_tickets_owner_time",),
        create_indexes=(
            "CREATE INDEX idx_support_tickets_owner_time "
            "ON support_tickets(telegram_id, created_at)",
        ),
    )

    total_orphans_removed += _rebuild(
        "wl_tokens",
        """
        CREATE TABLE wl_tokens (
            token TEXT PRIMARY KEY,
            wishlist_id INTEGER NOT NULL REFERENCES wl_lists(id) ON DELETE CASCADE,
            active INTEGER NOT NULL DEFAULT 1
        )
        """,
        """
        INSERT INTO wl_tokens (token, wishlist_id, active)
        SELECT t.token, t.wishlist_id, t.active
        FROM {legacy} t
        WHERE t.wishlist_id IN (SELECT id FROM wl_lists)
        """,
        drop_indexes=("idx_wl_tokens_wishlist",),
        create_indexes=("CREATE INDEX idx_wl_tokens_wishlist ON wl_tokens(wishlist_id, active)",),
    )

    total_orphans_removed += _rebuild(
        "wl_invite_tokens",
        """
        CREATE TABLE wl_invite_tokens (
            token TEXT PRIMARY KEY,
            wishlist_id INTEGER NOT NULL REFERENCES wl_lists(id) ON DELETE CASCADE
        )
        """,
        """
        INSERT INTO wl_invite_tokens (token, wishlist_id)
        SELECT i.token, l.id
        FROM {legacy} i
        JOIN wl_lists l ON l.invite_token = i.token
        """,
        create_indexes=(
            "CREATE INDEX idx_wl_invite_tokens_wishlist ON wl_invite_tokens(wishlist_id)",
        ),
    )

    total_orphans_removed += _rebuild(
        "reminder_outbox",
        """
        CREATE TABLE reminder_outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            occurrence_key TEXT NOT NULL UNIQUE,
            kind TEXT NOT NULL,
            user_id INTEGER NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
            list_id INTEGER REFERENCES wl_lists(id) ON DELETE CASCADE,
            item_id INTEGER REFERENCES wl_items(id) ON DELETE CASCADE,
            birthday_id INTEGER REFERENCES birthday_entries(id) ON DELETE CASCADE,
            revision INTEGER,
            event_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            claimed_at INTEGER,
            claim_token TEXT,
            attempts INTEGER NOT NULL DEFAULT 0,
            next_attempt_at INTEGER NOT NULL,
            requires_membership INTEGER NOT NULL DEFAULT 0,
            updated_at INTEGER
        )
        """,
        """
        INSERT INTO reminder_outbox (
            id, occurrence_key, kind, user_id, list_id, item_id, birthday_id,
            revision, event_date, status, claimed_at, claim_token, attempts,
            next_attempt_at, requires_membership, updated_at
        )
        SELECT
            id, occurrence_key, kind, user_id, list_id, item_id, birthday_id,
            revision, event_date, status, claimed_at, claim_token, attempts,
            next_attempt_at, requires_membership, updated_at
        FROM {legacy}
        WHERE user_id IN (SELECT telegram_id FROM users)
          AND (list_id IS NULL OR list_id IN (SELECT id FROM wl_lists))
          AND (item_id IS NULL OR item_id IN (SELECT id FROM wl_items))
          AND (birthday_id IS NULL OR birthday_id IN (SELECT id FROM birthday_entries))
        """,
        drop_indexes=("idx_reminders_due", "idx_reminder_outbox_status_updated"),
        create_indexes=(
            "CREATE INDEX idx_reminders_due ON reminder_outbox(status, next_attempt_at)",
            "CREATE INDEX idx_reminder_outbox_status_updated "
            "ON reminder_outbox(status, updated_at)",
        ),
    )

    logger.info(
        "Unified user keys on telegram_id and added cascade FKs",
        extra={
            "event": "unify_user_keys_migration_completed",
            "tables": 8,
            "total_orphans_removed": total_orphans_removed,
        },
    )


def downgrade() -> None:
    """Restore previous user_id/owner_id mappings and remove cascade FKs."""
    _rebuild(
        "reminder_outbox",
        """
        CREATE TABLE reminder_outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            occurrence_key TEXT NOT NULL UNIQUE,
            kind TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            list_id INTEGER,
            item_id INTEGER,
            birthday_id INTEGER,
            revision INTEGER,
            event_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            claimed_at INTEGER,
            claim_token TEXT,
            attempts INTEGER NOT NULL DEFAULT 0,
            next_attempt_at INTEGER NOT NULL,
            requires_membership INTEGER NOT NULL DEFAULT 0,
            updated_at INTEGER
        )
        """,
        """
        INSERT INTO reminder_outbox (
            id, occurrence_key, kind, user_id, list_id, item_id, birthday_id,
            revision, event_date, status, claimed_at, claim_token, attempts,
            next_attempt_at, requires_membership, updated_at
        )
        SELECT
            id, occurrence_key, kind, user_id, list_id, item_id, birthday_id,
            revision, event_date, status, claimed_at, claim_token, attempts,
            next_attempt_at, requires_membership, updated_at
        FROM {legacy}
        """,
        drop_indexes=("idx_reminders_due", "idx_reminder_outbox_status_updated"),
        create_indexes=(
            "CREATE INDEX idx_reminders_due ON reminder_outbox(status, next_attempt_at)",
            "CREATE INDEX idx_reminder_outbox_status_updated "
            "ON reminder_outbox(status, updated_at)",
        ),
    )

    _rebuild(
        "wl_invite_tokens",
        "CREATE TABLE wl_invite_tokens (token TEXT PRIMARY KEY)",
        "INSERT INTO wl_invite_tokens (token) SELECT token FROM {legacy}",
        drop_indexes=("idx_wl_invite_tokens_wishlist",),
    )

    _rebuild(
        "wl_tokens",
        """
        CREATE TABLE wl_tokens (
            token TEXT PRIMARY KEY,
            wishlist_id INTEGER NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        )
        """,
        "INSERT INTO wl_tokens (token, wishlist_id, active) "
        "SELECT token, wishlist_id, active FROM {legacy}",
        drop_indexes=("idx_wl_tokens_wishlist",),
        create_indexes=("CREATE INDEX idx_wl_tokens_wishlist ON wl_tokens(wishlist_id, active)",),
    )

    _rebuild(
        "support_tickets",
        """
        CREATE TABLE support_tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_ref TEXT NOT NULL UNIQUE,
            owner_id INTEGER NOT NULL,
            telegram_id INTEGER NOT NULL,
            created_at INTEGER NOT NULL
        )
        """,
        """
        INSERT INTO support_tickets (id, ticket_ref, owner_id, telegram_id, created_at)
        SELECT st.id, st.ticket_ref, u.id, st.telegram_id, st.created_at
        FROM {legacy} st
        JOIN users u ON u.telegram_id = st.telegram_id
        """,
        drop_indexes=("idx_support_tickets_owner_time",),
        create_indexes=(
            "CREATE INDEX idx_support_tickets_owner_time ON support_tickets(owner_id, created_at)",
        ),
    )

    _rebuild(
        "support_input",
        """
        CREATE TABLE support_input (
            owner_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            PRIMARY KEY (owner_id, chat_id)
        )
        """,
        """
        INSERT INTO support_input (owner_id, chat_id, expires_at)
        SELECT u.id, si.chat_id, si.expires_at
        FROM {legacy} si
        JOIN users u ON u.telegram_id = si.owner_id
        """,
    )

    _rebuild(
        "birthday_input",
        """
        CREATE TABLE birthday_input (
            owner_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            entry_id INTEGER,
            revision INTEGER,
            stage TEXT NOT NULL,
            label TEXT,
            expires_at INTEGER NOT NULL,
            PRIMARY KEY (owner_id, chat_id)
        )
        """,
        """
        INSERT INTO birthday_input
            (owner_id, chat_id, entry_id, revision, stage, label, expires_at)
        SELECT u.id, bi.chat_id, bi.entry_id, bi.revision, bi.stage, bi.label, bi.expires_at
        FROM {legacy} bi
        JOIN users u ON u.telegram_id = bi.owner_id
        """,
    )

    _rebuild(
        "birthday_entries",
        """
        CREATE TABLE birthday_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL,
            label TEXT NOT NULL,
            month INTEGER NOT NULL,
            day INTEGER NOT NULL,
            revision INTEGER NOT NULL DEFAULT 1,
            deleted INTEGER NOT NULL DEFAULT 0,
            deleted_at INTEGER
        )
        """,
        """
        INSERT INTO birthday_entries
            (id, owner_id, label, month, day, revision, deleted, deleted_at)
        SELECT b.id, u.id, b.label, b.month, b.day, b.revision, b.deleted, b.deleted_at
        FROM {legacy} b
        JOIN users u ON u.telegram_id = b.owner_id
        """,
        drop_indexes=("idx_birthday_entries_deleted_at",),
        create_indexes=(
            "CREATE INDEX idx_birthday_entries_deleted_at ON birthday_entries(deleted, deleted_at)",
        ),
    )

    _rebuild(
        "bot_destinations",
        """
        CREATE TABLE bot_destinations (
            user_id INTEGER PRIMARY KEY,
            chat_id INTEGER NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            updated_at INTEGER
        )
        """,
        """
        INSERT INTO bot_destinations (user_id, chat_id, active, updated_at)
        SELECT u.id, d.chat_id, d.active, d.updated_at
        FROM {legacy} d
        JOIN users u ON u.telegram_id = d.user_id
        """,
        drop_indexes=("idx_bot_destinations_active_updated",),
        create_indexes=(
            "CREATE INDEX idx_bot_destinations_active_updated "
            "ON bot_destinations(active, updated_at)",
        ),
    )

    logger.info(
        "Reverted user key unification migration",
        extra={
            "event": "unify_user_keys_downgrade_completed",
            "tables": 8,
        },
    )
