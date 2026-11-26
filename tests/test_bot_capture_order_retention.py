"""Additional tests for WISHENKA-178 bounded retention of bot_capture_order."""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot, Dispatcher
from aiogram.methods import SendMessage
from aiogram.types import InlineKeyboardMarkup, Update
from alembic import command
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy import text

import wishenka.bot.__main__ as bot_main
from wishenka.auth.models import AuthenticatedUser, TelegramUser
from wishenka.bot.capture import cleanup_drafts
from wishenka.bot.entry import create_router
from wishenka.config import Settings
from wishenka.items.schemas import ItemPreviewDTO
from wishenka.users.store import UserStore
from wishenka.wishlists.deletion import AccountDeletionService
from wishenka.wishlists.service import WishlistService
from wishenka.wishlists.store import WishlistStore

pytestmark = pytest.mark.timeout(30)

OWNER = AuthenticatedUser(telegram_id=101, first_name="Owner", auth_method="session_token")


class _BotHarness:
    """Deliver private Telegram messages and callbacks without network access."""

    def __init__(self, dispatcher: Dispatcher, bot: Bot, sent: list[Any]) -> None:
        self.dispatcher = dispatcher
        self.bot = bot
        self.sent = sent
        self.sequence = 0

    async def text(self, body: str, *, message_id: int | None = None) -> None:
        self.sequence += 1
        effective_message_id = self.sequence if message_id is None else message_id
        update = Update.model_validate(
            {
                "update_id": self.sequence,
                "message": {
                    "message_id": effective_message_id,
                    "date": 1700000000,
                    "chat": {"id": 101, "type": "private"},
                    "from": {
                        "id": 101,
                        "is_bot": False,
                        "first_name": "Owner",
                        "language_code": "en",
                    },
                    "text": body,
                },
            }
        )
        await self.dispatcher.feed_update(self.bot, update)

    async def callback(self, data: str) -> None:
        self.sequence += 1
        update = Update.model_validate(
            {
                "update_id": self.sequence,
                "callback_query": {
                    "id": f"cb-{self.sequence}",
                    "from": {
                        "id": 101,
                        "is_bot": False,
                        "first_name": "Owner",
                        "language_code": "en",
                    },
                    "chat_instance": "101",
                    "data": data,
                    "message": {
                        "message_id": self.sequence,
                        "date": 1700000000,
                        "chat": {"id": 101, "type": "private"},
                        "text": "Review",
                    },
                },
            }
        )
        await self.dispatcher.feed_update(self.bot, update)

    def last_draft_id_and_rev(self) -> tuple[str, int]:
        for method in reversed(self.sent):
            if isinstance(method, SendMessage) and isinstance(
                method.reply_markup, InlineKeyboardMarkup
            ):
                for row in method.reply_markup.inline_keyboard:
                    for button in row:
                        if button.callback_data and button.callback_data.startswith("cap:"):
                            _, ident, rev_text, _ = button.callback_data.split(":", 3)
                            return ident, int(rev_text)
        raise AssertionError("No capture inline keyboard found")


async def _get_updated_at(store: WishlistStore, owner: int = 101, chat: int = 101) -> int | None:
    async def read(conn: Any) -> int | None:
        row = await conn.execute(
            text("SELECT updated_at FROM bot_capture_order WHERE owner = :o AND chat = :c"),
            {"o": owner, "c": chat},
        )
        val = row.scalar_one_or_none()
        return int(val) if val is not None else None

    return await store.transaction(read)


async def test_watermark_updated_at_refreshed_on_edit_and_save(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Active draft callbacks and field edits refresh bot_capture_order.updated_at."""
    url = f"sqlite+aiosqlite:///{tmp_path / 'refresh.db'}"
    store = WishlistStore(url)
    users = UserStore(url)
    await store.initialize()
    await WishlistService(store).create_wishlist(owner=OWNER, title="List 1")

    clock_now = [datetime(2026, 6, 1, 12, 0, tzinfo=UTC)]
    preview = AsyncMock()
    preview.preview = AsyncMock(return_value=ItemPreviewDTO(title="Lamp"))
    deps = SimpleNamespace(
        mini_app_url="https://example.test/miniapp",
        user_store=users,
        wishlist_store=store,
        preview_service=preview,
        clock=lambda: clock_now[0],
    )
    sent: list[Any] = []

    async def transport(_bot: Bot, method: Any, request_timeout: Any = None) -> bool:
        sent.append(method)
        return True

    monkeypatch.setattr(Bot, "__call__", transport)
    dispatcher = Dispatcher()
    dispatcher.include_router(create_router(deps))
    bot = Bot("123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")
    harness = _BotHarness(dispatcher, bot, sent)

    await harness.text("Desk lamp", message_id=10)
    assert await _get_updated_at(store) == int(clock_now[0].timestamp())

    clock_now[0] += timedelta(hours=2)
    ident, rev = harness.last_draft_id_and_rev()
    await harness.callback(f"cap:{ident}:{rev}:e_title")
    assert await _get_updated_at(store) == int(clock_now[0].timestamp())

    clock_now[0] += timedelta(hours=2)
    await harness.text("Brass desk lamp", message_id=11)
    assert await _get_updated_at(store) == int(clock_now[0].timestamp())

    clock_now[0] += timedelta(hours=2)
    ident, rev = harness.last_draft_id_and_rev()
    await harness.callback(f"cap:{ident}:{rev}:save")
    assert await _get_updated_at(store) == int(clock_now[0].timestamp())

    await store.dispose()
    await users.engine.dispose()


def test_settings_bot_capture_order_retention_days_validation() -> None:
    """bot_capture_order_retention_days defaults to 30 and rejects values < 2."""
    assert Settings().bot_capture_order_retention_days == 30
    assert Settings(bot_capture_order_retention_days=2).bot_capture_order_retention_days == 2
    with pytest.raises(ValidationError):
        Settings(bot_capture_order_retention_days=1)


async def test_cleanup_loop_forwards_custom_order_retention_days(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """cleanup_loop forwards explicit order_retention_days to cleanup_drafts."""
    url = f"sqlite+aiosqlite:///{tmp_path / 'loop.db'}"
    store = WishlistStore(url)
    calls: list[dict[str, Any]] = []

    async def fake_cleanup(s: WishlistStore, **kwargs: Any) -> int:
        calls.append({"store": s, "kwargs": kwargs})
        return 0

    async def stop_sleep(_seconds: float) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr(bot_main, "cleanup_drafts", fake_cleanup)
    monkeypatch.setattr(asyncio, "sleep", stop_sleep)

    with pytest.raises(asyncio.CancelledError):
        await bot_main.cleanup_loop(store, order_retention_days=14)

    assert calls == [{"store": store, "kwargs": {"order_retention_days": 14}}]


async def test_account_deletion_removes_fresh_bot_capture_order_immediately(
    tmp_path: Path,
) -> None:
    """Account deletion purges bot_capture_order even when updated_at is fresh."""
    url = f"sqlite+aiosqlite:///{tmp_path / 'deletion.db'}"
    store = WishlistStore(url)
    users = UserStore(url)
    await store.initialize()
    await users.upsert_user(TelegramUser(id=101, first_name="Owner"))

    fresh_ts = int(time.time())

    async def seed(conn: Any) -> None:
        await conn.execute(
            text(
                "INSERT INTO bot_capture_order (owner, chat, message_id, updated_at) "
                "VALUES (101, 101, 42, :ts)"
            ),
            {"ts": fresh_ts},
        )

    await store.transaction(seed)
    assert await _get_updated_at(store) == fresh_ts

    svc = AccountDeletionService(store)
    await svc.delete_account(101, secret_key="test-secret", session_ttl_seconds=600)
    assert await _get_updated_at(store) is None

    await store.dispose()
    await users.engine.dispose()


def test_alembic_bot_capture_order_retention_downgrade(tmp_path: Path) -> None:
    """Downgrading from head removes updated_at and idx_bot_capture_order_updated_at."""
    db_file = tmp_path / "alembic_downgrade.db"
    cfg = Config()
    cfg.set_main_option("script_location", "wishenka/wishlists/alembic")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_file}")

    command.upgrade(cfg, "add_bot_capture_order_retention")
    command.downgrade(cfg, "add_user_fk_cascades")

    with sqlite3.connect(str(db_file)) as conn:
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(bot_capture_order)").fetchall()
        }
        indexes = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'index' AND tbl_name = 'bot_capture_order'"
            ).fetchall()
        }

    assert "updated_at" not in columns
    assert "idx_bot_capture_order_updated_at" not in indexes


async def test_cleanup_drafts_logs_structured_completion(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """cleanup_drafts emits structured INFO when rows are purged and DEBUG when idle."""
    url = f"sqlite+aiosqlite:///{tmp_path / 'obs.db'}"
    store = WishlistStore(url)
    await store.initialize()

    stale_ts = int(time.time()) - 40 * 86400

    async def seed(conn: Any) -> None:
        await conn.execute(
            text(
                "INSERT INTO bot_capture_order (owner, chat, message_id, updated_at) "
                "VALUES (777, 888, 1, :ts)"
            ),
            {"ts": stale_ts},
        )

    await store.transaction(seed)

    with caplog.at_level(logging.DEBUG, logger="wishenka.bot.capture"):
        removed = await cleanup_drafts(store, order_retention_days=30)
        removed_idle = await cleanup_drafts(store, order_retention_days=30)

    await store.dispose()

    assert removed == 1
    assert removed_idle == 0

    events = [
        r for r in caplog.records if getattr(r, "event", None) == "bot_draft_cleanup_completed"
    ]
    assert len(events) == 2

    purged_rec, idle_rec = events
    assert purged_rec.levelno == logging.INFO
    assert getattr(purged_rec, "total_removed", None) == 1
    assert getattr(purged_rec, "bot_capture_order_removed", None) == 1
    assert getattr(purged_rec, "order_retention_days", None) == 30
    assert isinstance(getattr(purged_rec, "duration_ms", None), float)
    assert "777" not in purged_rec.getMessage()
    assert "888" not in purged_rec.getMessage()

    assert idle_rec.levelno == logging.DEBUG
    assert getattr(idle_rec, "total_removed", None) == 0
    assert getattr(idle_rec, "bot_capture_order_removed", None) == 0
