"""Store private birthday entries, pending input and verified bot destinations."""

from alembic import op

revision = "add_birthday_reminders"
down_revision = "add_bot_capture_order"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the private birthday and destination tables."""
    op.execute("""
        CREATE TABLE IF NOT EXISTS bot_destinations (
            user_id INTEGER PRIMARY KEY, chat_id INTEGER NOT NULL, active INTEGER NOT NULL DEFAULT 1
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS birthday_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id INTEGER NOT NULL,
            label TEXT NOT NULL, month INTEGER NOT NULL, day INTEGER NOT NULL,
            revision INTEGER NOT NULL DEFAULT 1, deleted INTEGER NOT NULL DEFAULT 0
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS birthday_input (
            owner_id INTEGER NOT NULL, chat_id INTEGER NOT NULL, entry_id INTEGER,
            revision INTEGER, stage TEXT NOT NULL, label TEXT, expires_at INTEGER NOT NULL,
            PRIMARY KEY (owner_id, chat_id)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS reminder_outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT, occurrence_key TEXT NOT NULL UNIQUE,
            kind TEXT NOT NULL, user_id INTEGER NOT NULL, list_id INTEGER,
            item_id INTEGER, birthday_id INTEGER, revision INTEGER, event_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending', claimed_at INTEGER, claim_token TEXT,
            attempts INTEGER NOT NULL DEFAULT 0, next_attempt_at INTEGER NOT NULL
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS notice_rate_slots (
            bucket TEXT PRIMARY KEY, second INTEGER NOT NULL, count INTEGER NOT NULL
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS notice_scheduler_cursors (
            source TEXT PRIMARY KEY, last_id INTEGER NOT NULL
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_notice_rate_second ON notice_rate_slots(second)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminder_outbox(status,next_attempt_at)"
    )


def downgrade() -> None:
    """Drop private birthday and destination tables."""
    op.execute("DROP TABLE notice_scheduler_cursors")
    op.execute("DROP TABLE notice_rate_slots")
    op.execute("DROP TABLE reminder_outbox")
    op.execute("DROP TABLE birthday_input")
    op.execute("DROP TABLE birthday_entries")
    op.execute("DROP TABLE bot_destinations")
