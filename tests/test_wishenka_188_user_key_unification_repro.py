"""Failing reproduction tests for WISHENKA-188 (Step 3, red before Step 4)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic import command

from tests.receipt_support import TEST_BOT_TOKEN, make_user, open_store, sql_exec, sql_rows
from wishenka.auth.models import TelegramUser
from wishenka.bot.principal import ensure_private_bot_user
from wishenka.config import Settings
from wishenka.notices.events import EventProducer, SharedEvent
from wishenka.notices.scheduler import ReminderScheduler
from wishenka.users import store as user_store_module
from wishenka.users.store import UserStore
from wishenka.wishlists.deletion import AccountDeletionService
from wishenka.wishlists.migrations import _configured, head_revision, upgrade_to_head

pytestmark = pytest.mark.timeout(30)


def _table_columns(db_path: Path, table: str) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


async def test_user_store_initialize_delegates_to_alembic_and_has_birthdate_columns(
    tmp_path: Path,
) -> None:
    """UserStore.initialize() delegates DDL to Alembic and Alembic owns birthdate columns."""
    assert not hasattr(user_store_module, "_USERS_TABLE_DDL")

    store_db = tmp_path / "user_store_only.db"
    store_url = f"sqlite+aiosqlite:///{store_db}"
    store = UserStore(store_url)
    try:
        await store.initialize()
    finally:
        await store.engine.dispose()

    with sqlite3.connect(store_db) as conn:
        version = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    assert version is not None and version[0] == head_revision(store_url)
    assert {"birth_day", "birth_month", "birth_year", "birthdate_source"}.issubset(
        _table_columns(store_db, "users")
    )

    alembic_db = tmp_path / "alembic_only.db"
    alembic_url = f"sqlite+aiosqlite:///{alembic_db}"
    await upgrade_to_head(alembic_url)
    assert {"birth_day", "birth_month", "birth_year", "birthdate_source"}.issubset(
        _table_columns(alembic_db, "users")
    )


async def test_migration_unifies_user_keys_to_telegram_id_and_enforces_fks(
    tmp_path: Path,
) -> None:
    """Upgrade migrates users.id -> users.telegram_id across bot/birthday/support tables."""
    db_path = tmp_path / "legacy_keys.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    command.upgrade(_configured(db_url), "add_receipt_delivery_fence")

    sql_exec(
        db_path,
        "INSERT INTO users (id, telegram_id, first_name, is_premium, created_at, updated_at) "
        "VALUES (42, 999001, 'Legacy', 0, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')",
    )
    sql_exec(
        db_path,
        "INSERT INTO bot_destinations (user_id, chat_id, active, updated_at) "
        "VALUES (42, 999001, 1, 100)",
    )
    sql_exec(
        db_path,
        "INSERT INTO birthday_entries (id, owner_id, label, month, day, revision, deleted) "
        "VALUES (1, 42, 'Mom', 5, 12, 1, 0)",
    )
    sql_exec(
        db_path,
        "INSERT INTO birthday_input (owner_id, chat_id, stage, expires_at) "
        "VALUES (42, 999001, 'label', 9999999999)",
    )
    sql_exec(
        db_path,
        "INSERT INTO support_input (owner_id, chat_id, expires_at) VALUES (42, 999001, 9999999999)",
    )
    sql_exec(
        db_path,
        "INSERT INTO support_tickets (id, ticket_ref, owner_id, telegram_id, created_at) "
        "VALUES (1, 'SUP-LEGACY-1', 42, 999001, 100)",
    )

    await upgrade_to_head(db_url)

    assert sql_rows(db_path, "SELECT user_id FROM bot_destinations") == [{"user_id": 999001}]
    assert sql_rows(db_path, "SELECT owner_id FROM birthday_entries") == [{"owner_id": 999001}]
    assert sql_rows(db_path, "SELECT owner_id FROM birthday_input") == [{"owner_id": 999001}]
    assert sql_rows(db_path, "SELECT owner_id FROM support_input") == [{"owner_id": 999001}]
    assert "owner_id" not in _table_columns(db_path, "support_tickets")
    assert sql_rows(db_path, "SELECT telegram_id FROM support_tickets") == [{"telegram_id": 999001}]

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        for stmt in (
            "INSERT INTO bot_destinations (user_id, chat_id, active, updated_at) "
            "VALUES (888888, 888888, 1, 100)",
            "INSERT INTO birthday_entries (owner_id, label, month, day) "
            "VALUES (888888, 'Ghost', 1, 1)",
            "INSERT INTO birthday_input (owner_id, chat_id, stage, expires_at) "
            "VALUES (888888, 888888, 'label', 9999999999)",
            "INSERT INTO support_input (owner_id, chat_id, expires_at) "
            "VALUES (888888, 888888, 9999999999)",
            "INSERT INTO support_tickets (ticket_ref, telegram_id, created_at) "
            "VALUES ('SUP-GHOST', 888888, 100)",
        ):
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(stmt)


async def test_deleting_wishlist_cascades_tokens_invite_tokens_and_reminders(
    tmp_path: Path,
) -> None:
    """Deleting wl_lists with FK=ON cascades to wl_tokens, wl_invite_tokens, reminder_outbox."""
    db_path = tmp_path / "cascade_wl.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    user_store = UserStore(db_url)
    try:
        await user_store.initialize()
        await user_store.upsert_user(TelegramUser(id=101010, first_name="Owner"))
    finally:
        await user_store.engine.dispose()

    async with open_store(db_path) as store:
        owner = make_user(101010, "Owner")
        wl = await store.execute(lambda svc: svc.create_wishlist(owner=owner, title="Birthday"))

    sql_exec(
        db_path,
        "INSERT INTO reminder_outbox "
        "(occurrence_key, kind, user_id, list_id, event_date, next_attempt_at, updated_at) "
        "VALUES (?, 'list', 101010, ?, '2026-12-01', 100, 100)",
        (f"list:{wl.id}", wl.id),
    )

    assert (
        len(sql_rows(db_path, "SELECT token FROM wl_tokens WHERE wishlist_id = ?", (wl.id,))) == 1
    )
    assert (
        len(
            sql_rows(
                db_path, "SELECT token FROM wl_invite_tokens WHERE token = ?", (wl.invite_token,)
            )
        )
        == 1
    )
    assert len(sql_rows(db_path, "SELECT id FROM reminder_outbox WHERE list_id = ?", (wl.id,))) == 1

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("DELETE FROM wl_lists WHERE id = ?", (wl.id,))
        conn.commit()

    assert sql_rows(db_path, "SELECT token FROM wl_tokens WHERE wishlist_id = ?", (wl.id,)) == []
    assert (
        sql_rows(db_path, "SELECT token FROM wl_invite_tokens WHERE token = ?", (wl.invite_token,))
        == []
    )
    assert sql_rows(db_path, "SELECT id FROM reminder_outbox WHERE list_id = ?", (wl.id,)) == []


async def test_end_to_end_bot_notices_and_deletion_use_telegram_id(tmp_path: Path) -> None:
    """Bot destination, EventProducer, ReminderScheduler, and deletion use telegram_id."""
    db_path = tmp_path / "e2e_tg_id.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"

    async with open_store(db_path) as store:
        user_store = UserStore(db_url)
        try:
            await user_store.initialize()
            # Insert spacer user first so Alice's users.id (2) differs from telegram_id (777001).
            await user_store.upsert_user(TelegramUser(id=111111, first_name="Spacer"))

            deps = SimpleNamespace(user_store=user_store, clock=lambda: 1000)
            alice_tg = TelegramUser(id=777001, first_name="Alice", language_code="en")
            alice_rec = await ensure_private_bot_user(deps, alice_tg, chat_id=777001, now=1000)
            assert alice_rec is not None
            assert alice_rec.id != alice_rec.telegram_id

            assert sql_rows(
                db_path, "SELECT user_id FROM bot_destinations WHERE chat_id = 777001"
            ) == [{"user_id": 777001}]

            alice = make_user(777001, "Alice")
            wl = await store.execute(
                lambda svc: svc.create_wishlist(owner=alice, title="Alice List")
            )

            async with store.engine.begin() as conn:
                queued = await EventProducer().record(
                    conn,
                    SharedEvent(
                        kind="item_created",
                        wishlist_id=wl.id,
                        item_id=None,
                        event_id="evt-188",
                        recipients=(777001,),
                    ),
                    now=1000,
                )
            assert queued == 1

            now_ts = int(datetime(2026, 11, 24, 12, 0, tzinfo=UTC).timestamp())
            sql_exec(
                db_path,
                "INSERT INTO birthday_entries (owner_id, label, month, day, revision, deleted) "
                "VALUES (777001, 'Mom', 11, 25, 1, 0)",
            )
            scheduler = ReminderScheduler(
                store, Settings(bot_token=TEST_BOT_TOKEN, database_url=db_url)
            )
            await scheduler.run_once(now=now_ts)
            assert (
                len(
                    sql_rows(
                        db_path,
                        "SELECT id FROM reminder_outbox "
                        "WHERE kind = 'birthday' AND user_id = 777001",
                    )
                )
                >= 1
            )

            deletion = AccountDeletionService(store)
            await deletion.delete_account(
                777001, secret_key="test-secret", session_ttl_seconds=3600
            )
        finally:
            await user_store.engine.dispose()

    assert sql_rows(db_path, "SELECT id FROM users WHERE telegram_id = 777001") == []
    assert sql_rows(db_path, "SELECT user_id FROM bot_destinations WHERE user_id = 777001") == []
    assert sql_rows(db_path, "SELECT id FROM birthday_entries WHERE owner_id = 777001") == []
    assert sql_rows(db_path, "SELECT id FROM reminder_outbox WHERE user_id = 777001") == []


async def test_migration_logs_orphans_cleaned_and_completion_summary(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Upgrade logs orphan cleanup warnings per table and total_orphans_removed at completion."""
    db_path = tmp_path / "orphan_logging.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    command.upgrade(_configured(db_url), "add_receipt_delivery_fence")

    sql_exec(
        db_path,
        "INSERT INTO bot_destinations (user_id, chat_id, active, updated_at) "
        "VALUES (999999, 999999, 1, 100)",
    )
    sql_exec(
        db_path,
        "INSERT INTO wl_invite_tokens (token) VALUES ('orphan-invite-tok')",
    )

    with caplog.at_level("INFO", logger="wishenka.wishlists.migrations"):
        await upgrade_to_head(db_url)

    orphan_warnings = [
        rec
        for rec in caplog.records
        if getattr(rec, "event", None) == "unify_user_keys_orphans_cleaned"
    ]
    assert {getattr(rec, "table", None) for rec in orphan_warnings} == {
        "bot_destinations",
        "wl_invite_tokens",
    }
    assert all(rec.levelname == "WARNING" for rec in orphan_warnings)

    completed = [
        rec
        for rec in caplog.records
        if getattr(rec, "event", None) == "unify_user_keys_migration_completed"
    ]
    assert len(completed) == 1
    assert getattr(completed[0], "tables", None) == 8
    assert getattr(completed[0], "total_orphans_removed", None) == 2
