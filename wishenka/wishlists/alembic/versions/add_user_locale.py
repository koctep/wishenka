"""Add bilingual locale and locale_source columns to users profile table."""

from alembic import op

revision = "add_user_locale"
down_revision = "add_idempotency_records"
branch_labels = None
depends_on = None

_CREATE_USERS_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL UNIQUE,
    first_name TEXT NOT NULL,
    last_name TEXT,
    username TEXT,
    language_code TEXT,
    locale TEXT NOT NULL DEFAULT 'en' CHECK (locale IN ('ru', 'en')),
    locale_source TEXT NOT NULL DEFAULT 'auto' CHECK (locale_source IN ('auto', 'explicit')),
    is_premium INTEGER NOT NULL DEFAULT 0 CHECK (is_premium IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

_BACKFILL_ALL_SQL = """
UPDATE users
SET locale = CASE
        WHEN lower(trim(coalesce(language_code, ''))) LIKE 'ru%' THEN 'ru'
        ELSE 'en'
    END,
    locale_source = 'auto'
"""

_REPAIR_INVALID_SQL = """
UPDATE users
SET locale = CASE
        WHEN lower(trim(coalesce(language_code, ''))) LIKE 'ru%' THEN 'ru'
        ELSE 'en'
    END,
    locale_source = 'auto'
WHERE locale IS NULL
   OR locale NOT IN ('ru', 'en')
   OR locale_source IS NULL
   OR locale_source NOT IN ('auto', 'explicit')
"""


def upgrade() -> None:
    """Create or migrate users table with locale and locale_source and backfill existing rows."""
    bind = op.get_bind()
    bind.exec_driver_sql(_CREATE_USERS_SQL)
    bind.exec_driver_sql(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id)"
    )
    bind.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")

    columns = {row[1] for row in bind.exec_driver_sql("PRAGMA table_info(users)").fetchall()}
    added_column = False
    if "locale" not in columns:
        bind.exec_driver_sql(
            "ALTER TABLE users ADD COLUMN locale TEXT NOT NULL DEFAULT 'en' "
            "CHECK (locale IN ('ru', 'en'))"
        )
        added_column = True
    if "locale_source" not in columns:
        bind.exec_driver_sql(
            "ALTER TABLE users ADD COLUMN locale_source TEXT NOT NULL DEFAULT 'auto' "
            "CHECK (locale_source IN ('auto', 'explicit'))"
        )
        added_column = True

    if added_column:
        bind.exec_driver_sql(_BACKFILL_ALL_SQL)
    else:
        bind.exec_driver_sql(_REPAIR_INVALID_SQL)


def downgrade() -> None:
    """Drop locale_source and locale columns from users table if present."""
    bind = op.get_bind()
    tables = {
        row[0]
        for row in bind.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if "users" not in tables:
        return
    columns = {row[1] for row in bind.exec_driver_sql("PRAGMA table_info(users)").fetchall()}
    if "locale_source" in columns:
        bind.exec_driver_sql("ALTER TABLE users DROP COLUMN locale_source")
    if "locale" in columns:
        bind.exec_driver_sql("ALTER TABLE users DROP COLUMN locale")
