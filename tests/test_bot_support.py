"""Unit, integration, and migration tests for the Telegram support channel (WISHENKA-30)."""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from aiogram import Bot
from aiogram.methods import SendMessage
from alembic import command
from sqlalchemy import text

from tests.test_bot_support_repro import (
    ADMIN_CHAT_ID,
    SUPPORT_CHAT_ID,
    TICKET_REF_RE,
    _setup_support,
)
from wishenka.bot.capture import cleanup_drafts
from wishenka.bot.support import (
    DiagnosticContext,
    format_support_ticket,
    generate_ticket_ref,
    redact_capabilities,
)
from wishenka.config import Settings
from wishenka.logging import JsonFormatter
from wishenka.wishlists.migrations import _configured

pytestmark = pytest.mark.timeout(30)


def test_support_unit_helpers_redaction_formatting_and_settings() -> None:
    now = datetime(2026, 11, 17, 14, 30, tzinfo=UTC)
    ref = generate_ticket_ref(now)
    assert TICKET_REF_RE.fullmatch(ref)

    raw = (
        "Leak https://t.me/bot/app?startapp=p_sec123 and ?startapp=i_inv456 "
        "and /share/tok789 and /invite/inv999 and /api/public/wishlists/pub000/view "
        "plus custom_secret_token_value"
    )
    redacted = redact_capabilities(raw, known_tokens=["custom_secret_token_value"])
    for secret in ("sec123", "inv456", "tok789", "inv999", "pub000", "custom_secret_token_value"):
        assert secret not in redacted
    assert redacted.count("[REDACTED]") >= 6

    ctx = DiagnosticContext(
        ticket_ref=ref,
        submitted_at_iso="17.11.26 14:30:00 UTC",
        internal_user_id=7,
        telegram_user_id=707,
        username="tester",
        display_name="Test User",
        effective_language="ru",
        telegram_language_code="ru",
        bot_destination_active=True,
        active_wishlist_count=2,
        archived_wishlist_count=1,
        collaborative_membership_count=3,
        active_draft_present=True,
    )
    rendered = format_support_ticket(ctx, "A" * 5000)
    assert len(rendered) <= 4096
    assert ref in rendered
    assert "@tester" in rendered
    assert "Wishlists (active/archived): 2/1" in rendered
    assert "Collaborative memberships: 3" in rendered
    assert "Active wish draft: yes" in rendered

    settings = Settings(
        support_chat_id=-100123,
        support_admin_ids=(111, 222),
        support_session_ttl_seconds=1200,
        support_max_message_length=1500,
        support_rate_limit_window_seconds=1800,
        support_rate_limit_max_tickets=5,
    )
    assert settings.support_chat_id == -100123
    assert settings.support_admin_ids == (111, 222)


def test_add_support_channel_migration_upgrade_and_downgrade(tmp_path: Path) -> None:
    db_path = tmp_path / "migration.db"
    url = f"sqlite+aiosqlite:///{db_path}"
    command.upgrade(_configured(url), "add_support_channel")

    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        indexes = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
        }
    assert "support_input" in tables
    assert "support_tickets" in tables
    assert "idx_support_tickets_owner_time" in indexes

    command.downgrade(_configured(url), "add_notice_uncertain")
    with sqlite3.connect(db_path) as conn:
        tables_after_down = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert "support_input" not in tables_after_down
    assert "support_tickets" not in tables_after_down

    command.upgrade(_configured(url), "add_support_channel")
    with sqlite3.connect(db_path) as conn:
        tables_after_up = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert "support_input" in tables_after_up
    assert "support_tickets" in tables_after_up


async def test_session_precedence_with_birthday_input_and_draft_edit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness, store, users, _, _ = await _setup_support(tmp_path, monkeypatch)
    try:
        # 1. Start a wish draft and enter field-edit mode, then open support:
        #    support clears edit_field and consumes the text without mutating the draft.
        await harness.text("Initial wish")
        async with store.engine.connect() as conn:
            draft_row = (
                (await conn.execute(text("SELECT id, revision FROM bot_drafts LIMIT 1")))
                .mappings()
                .one()
            )
        await harness.callback(f"cap:{draft_row['id']}:{draft_row['revision']}:e_title")
        await harness.text("/support")
        await harness.text("Question during draft edit")
        assert len(harness.support_messages()) == 1
        async with store.engine.connect() as conn:
            updated_draft = (
                (await conn.execute(text("SELECT data, edit_field FROM bot_drafts LIMIT 1")))
                .mappings()
                .one()
            )
        assert updated_draft["edit_field"] is None
        assert "Initial wish" in updated_draft["data"]
        assert "Question during draft edit" not in updated_draft["data"]

        # 2. Start birthday add, then open support: birthday_input is cleared.
        await harness.callback("birthday:add")
        await harness.callback("support:open")
        await harness.text("Support overrides birthday input")
        assert len(harness.support_messages()) == 2
        async with store.engine.connect() as conn:
            bday_entries = (
                await conn.execute(text("SELECT COUNT(*) FROM birthday_entries"))
            ).scalar_one()
        assert bday_entries == 0

        # 3. Supersede active support via /birthdays, /help, and /reservation_confirmations
        for cmd in ("/birthdays", "/help", "/reservation_confirmations on"):
            await harness.text("/support")
            await harness.text(cmd)
            async with store.engine.connect() as conn:
                active = (
                    await conn.execute(text("SELECT COUNT(*) FROM support_input"))
                ).scalar_one()
            assert active == 0
    finally:
        await harness.bot.session.close()
        await users.engine.dispose()
        await store.engine.dispose()


async def test_partial_destination_success_stored_language_and_ticket_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    harness, store, users, _, _ = await _setup_support(tmp_path, monkeypatch)
    try:
        # 1. Stored language preference ('ru') overrides Telegram language_code ('en').
        await harness.text("/start", lang="en")
        await users.set_locale(101, "ru")
        await harness.text("/support", lang="en")
        assert "Отмена" in str(harness.last_user_message().reply_markup)

        # 2. Partial destination failure: SUPPORT_CHAT_ID fails, ADMIN_CHAT_ID succeeds.
        async def partial_transport(_bot: Bot, method: Any, request_timeout: Any = None) -> bool:
            if isinstance(method, SendMessage) and method.chat_id == SUPPORT_CHAT_ID:
                raise RuntimeError("Primary support chat error")
            harness.sent.append(method)
            return True

        monkeypatch.setattr(Bot, "__call__", partial_transport)
        caplog.clear()
        with caplog.at_level(logging.INFO, logger="wishenka.bot.support"):
            await harness.text("Вопрос на русском языке", lang="en")
        admin_msgs = harness.support_messages(ADMIN_CHAT_ID)
        assert len(admin_msgs) == 1
        assert TICKET_REF_RE.search(harness.last_user_message().text)
        assert "Номер обращения" in harness.last_user_message().text
        partial_events = [
            (r.levelname, getattr(r, "event", ""), getattr(r, "reason", getattr(r, "outcome", "")))
            for r in caplog.records
            if r.name == "wishenka.bot.support"
        ]
        assert ("WARNING", "bot_support_unavailable", "partial_send_failed") in partial_events
        assert ("INFO", "bot_support_submitted", "partial") in partial_events
        assert "Primary support chat error" not in caplog.text

        # 3. cleanup_drafts removes aged support_tickets (>30 days) while keeping recent ones.
        old_ts = int(time.time()) - 31 * 86400
        async with store.engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO support_tickets(ticket_ref, telegram_id, created_at) "
                    "VALUES ('SUP-01010000-OLDTICK1', 101, :old_ts)"
                ),
                {"old_ts": old_ts},
            )
        removed = await cleanup_drafts(store)
        assert removed >= 1
        async with store.engine.connect() as conn:
            remaining_refs = [
                row[0]
                for row in (
                    await conn.execute(text("SELECT ticket_ref FROM support_tickets"))
                ).all()
            ]
        assert "SUP-01010000-OLDTICK1" not in remaining_refs
        assert len(remaining_refs) == 1
    finally:
        await harness.bot.session.close()
        await users.engine.dispose()
        await store.engine.dispose()


async def test_support_observability_events_json_format_and_error_redaction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    harness, store, users, _, _ = await _setup_support(
        tmp_path,
        monkeypatch,
        support_max_message_length=120,
        support_rate_limit_max_tickets=1,
        support_rate_limit_window_seconds=3600,
    )
    formatter = JsonFormatter()
    secret_body = "secret-support-body-marker-4455"
    secret_exc = "secret-db-exception-detail-9988"
    try:
        caplog.clear()
        with caplog.at_level(logging.INFO, logger="wishenka.bot.support"):
            await harness.text("/support")
            await harness.text("/cancel")
            await harness.callback("support:open")
            await harness.photo()
            await harness.text("   ")
            await harness.text("z" * 121)
            await harness.text(f"{secret_body} https://example.test/share/p_secret_tok")
            await harness.text("/support")
            await harness.text("Second ticket hitting rate limit")

        support_records = [r for r in caplog.records if r.name == "wishenka.bot.support"]
        observed = [
            (r.levelname, getattr(r, "event", ""), getattr(r, "reason", getattr(r, "outcome", "")))
            for r in support_records
        ]
        assert ("INFO", "bot_support_prompted", "") in observed
        assert ("INFO", "bot_support_cancelled", "") in observed
        assert ("INFO", "bot_support_rejected", "non_text") in observed
        assert ("INFO", "bot_support_rejected", "empty") in observed
        assert ("INFO", "bot_support_rejected", "too_long") in observed
        assert ("INFO", "bot_support_submitted", "delivered") in observed
        assert ("INFO", "bot_support_rejected", "rate_limited") in observed

        for record in support_records:
            payload = json.loads(formatter.format(record))
            assert payload["logger"] == "wishenka.bot.support"
            assert "event" in payload["extra"]
            assert set(payload["extra"].keys()) <= {"event", "reason", "outcome", "taskName"}
            rendered = json.dumps(payload)
            for forbidden in (secret_body, "p_secret_tok", "alice_tg", "101", "SUP-"):
                assert forbidden not in rendered

        # Dispatcher error boundary catches unexpected handler failures without leaking details.
        async def broken_transaction(*_args: Any, **_kwargs: Any) -> Any:
            raise RuntimeError(secret_exc)

        monkeypatch.setattr(store, "transaction", broken_transaction)
        caplog.clear()
        with caplog.at_level(logging.ERROR, logger="wishenka.bot.entry"):
            await harness.text("/support")
        entry_errors = [r for r in caplog.records if getattr(r, "event", "") == "bot_start_failed"]
        assert len(entry_errors) == 1
        assert "RuntimeError" in entry_errors[0].getMessage()
        assert secret_exc not in caplog.text
        assert all(secret_exc not in str(r.__dict__) for r in caplog.records)
    finally:
        await harness.bot.session.close()
        await users.engine.dispose()
        await store.engine.dispose()
