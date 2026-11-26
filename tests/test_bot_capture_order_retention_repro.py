"""Failing repro tests for WISHENKA-178 bounded retention of bot_capture_order."""

from __future__ import annotations

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
from aiogram.types import Update
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from wishenka.auth.models import AuthenticatedUser
from wishenka.bot.capture import cleanup_drafts
from wishenka.bot.entry import create_router
from wishenka.items.schemas import ItemPreviewDTO
from wishenka.users.store import UserStore
from wishenka.wishlists.service import WishlistService
from wishenka.wishlists.store import WishlistStore

pytestmark = pytest.mark.timeout(30)

OWNER = AuthenticatedUser(telegram_id=101, first_name="Owner", auth_method="session_token")


class _Harness:
    """Deliver private Telegram updates to a dispatcher without network access."""

    def __init__(self, dispatcher: Dispatcher, bot: Bot, sent: list[Any]) -> None:
        self.dispatcher = dispatcher
        self.bot = bot
        self.sent = sent
        self.sequence = 0

    async def text(
        self,
        body: str,
        *,
        user: int = 101,
        lang: str = "en",
        message_id: int | None = None,
    ) -> None:
        self.sequence += 1
        effective_message_id = self.sequence if message_id is None else message_id
        update = Update.model_validate(
            {
                "update_id": self.sequence,
                "message": {
                    "message_id": effective_message_id,
                    "date": 1700000000,
                    "chat": {"id": user, "type": "private"},
                    "from": {
                        "id": user,
                        "is_bot": False,
                        "first_name": "Owner",
                        "language_code": lang,
                    },
                    "text": body,
                },
            }
        )
        await self.dispatcher.feed_update(self.bot, update)

    def sent_messages(self) -> list[SendMessage]:
        return [method for method in self.sent if isinstance(method, SendMessage)]


async def _setup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[_Harness, WishlistStore, list[Any]]:
    url = f"sqlite+aiosqlite:///{tmp_path / 'capture_retention.db'}"
    store = WishlistStore(url)
    users = UserStore(url)
    await store.initialize()

    async def create_default_list(service: Any) -> Any:
        return await service.create_wishlist(owner=OWNER, title="List 1")

    await create_default_list(WishlistService(store))

    preview = AsyncMock()
    preview.preview = AsyncMock(return_value=ItemPreviewDTO(title="Lamp"))
    deps = SimpleNamespace(
        mini_app_url="https://example.test/miniapp",
        user_store=users,
        wishlist_store=store,
        preview_service=preview,
    )
    sent: list[Any] = []

    async def transport(_bot: Bot, method: Any, request_timeout: Any = None) -> bool:
        sent.append(method)
        return True

    monkeypatch.setattr(Bot, "__call__", transport)
    dispatcher = Dispatcher()
    dispatcher.include_router(create_router(deps))
    bot = Bot("123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")
    return _Harness(dispatcher, bot, sent), store, sent


def test_alembic_bot_capture_order_retention_upgrade_backfill_and_index(tmp_path: Path) -> None:
    """Upgrading to head adds updated_at, backfills legacy rows, and creates an index."""
    db_file = tmp_path / "alembic_capture_order.db"
    cfg = Config()
    cfg.set_main_option("script_location", "wishenka/wishlists/alembic")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_file}")

    command.upgrade(cfg, "add_user_fk_cascades")
    with sqlite3.connect(str(db_file)) as conn:
        conn.execute(
            "INSERT INTO bot_capture_order (owner, chat, message_id) VALUES (101, 101, 42)"
        )
        conn.commit()

    command.upgrade(cfg, "head")
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
        row = conn.execute(
            "SELECT updated_at FROM bot_capture_order WHERE owner = 101 AND chat = 101"
        ).fetchone()

    assert "updated_at" in columns
    assert "idx_bot_capture_order_updated_at" in indexes
    assert row is not None
    assert isinstance(row[0], int) and row[0] > 0


async def test_cleanup_drafts_removes_stale_bot_capture_order_in_bounded_batches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """cleanup_drafts purges expired bot_capture_order rows in batches of at most 100."""
    _harness, store, _sent = await _setup(tmp_path, monkeypatch)
    stale_ts = int(time.time()) - 31 * 86400

    async def seed_stale(conn: Any) -> None:
        for idx in range(105):
            uid = 1000 + idx
            await conn.execute(
                text(
                    "INSERT INTO bot_capture_order (owner, chat, message_id, updated_at) "
                    "VALUES (:owner, :chat, :message_id, :updated_at)"
                ),
                {"owner": uid, "chat": uid, "message_id": 1, "updated_at": stale_ts},
            )

    await store.transaction(seed_stale)

    removed_first = await cleanup_drafts(store)
    assert removed_first == 100

    removed_second = await cleanup_drafts(store)
    assert removed_second == 5

    async def count_remaining(conn: Any) -> int:
        row = await conn.execute(text("SELECT COUNT(*) FROM bot_capture_order"))
        return int(row.scalar_one())

    assert await store.transaction(count_remaining) == 0


async def test_late_delivery_ignored_after_draft_expiry_within_retention_window(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Within the 30-day retention window, expired draft cleanup keeps ordering protection."""
    harness, store, _sent = await _setup(tmp_path, monkeypatch)

    await harness.text("Fresh wish", message_id=10)
    assert len(harness.sent_messages()) == 1

    # Simulate draft expiry (25h ago) while ordering watermark is still within 30d retention.
    expired_iso = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    recent_ts = int(time.time()) - 2 * 86400

    async def age_draft_only(conn: Any) -> None:
        await conn.execute(
            text("UPDATE bot_drafts SET expires = :expires WHERE owner = 101"),
            {"expires": expired_iso},
        )
        await conn.execute(
            text("UPDATE bot_capture_order SET updated_at = :updated_at WHERE owner = 101"),
            {"updated_at": recent_ts},
        )

    await store.transaction(age_draft_only)

    removed = await cleanup_drafts(store)
    assert removed == 1

    async def has_watermark(conn: Any) -> bool:
        row = await conn.execute(
            text("SELECT message_id FROM bot_capture_order WHERE owner = 101 AND chat = 101")
        )
        return bool(row.scalar_one_or_none() == 10)

    assert await store.transaction(has_watermark) is True

    # A delayed/replayed older message_id must still be ignored.
    before_count = len(harness.sent_messages())
    await harness.text("Delayed old wish", message_id=5)
    assert len(harness.sent_messages()) == before_count


async def test_cleanup_drafts_preserves_watermark_for_active_conversation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """cleanup_drafts never removes bot_capture_order when an active non-expired draft exists."""
    harness, store, _sent = await _setup(tmp_path, monkeypatch)

    await harness.text("Active wish", message_id=20)
    stale_ts = int(time.time()) - 45 * 86400

    async def age_watermark_only(conn: Any) -> None:
        await conn.execute(
            text("UPDATE bot_capture_order SET updated_at = :updated_at WHERE owner = 101"),
            {"updated_at": stale_ts},
        )

    await store.transaction(age_watermark_only)

    removed = await cleanup_drafts(store)
    assert removed == 0

    async def get_watermark(conn: Any) -> int | None:
        row = await conn.execute(
            text("SELECT message_id FROM bot_capture_order WHERE owner = 101 AND chat = 101")
        )
        val = row.scalar_one_or_none()
        return int(val) if val is not None else None

    assert await store.transaction(get_watermark) == 20


async def test_new_message_establishes_fresh_baseline_after_retention_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After stale watermark cleanup, a new message establishes a fresh ordering baseline."""
    harness, store, _sent = await _setup(tmp_path, monkeypatch)

    await harness.text("Initial wish", message_id=50)
    expired_iso = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    stale_ts = int(time.time()) - 35 * 86400

    async def expire_both(conn: Any) -> None:
        await conn.execute(
            text("UPDATE bot_drafts SET expires = :expires WHERE owner = 101"),
            {"expires": expired_iso},
        )
        await conn.execute(
            text("UPDATE bot_capture_order SET updated_at = :updated_at WHERE owner = 101"),
            {"updated_at": stale_ts},
        )

    await store.transaction(expire_both)

    removed = await cleanup_drafts(store)
    assert removed == 2

    # Even a lower message_id from a fresh session now succeeds and sets a new baseline.
    before_count = len(harness.sent_messages())
    await harness.text("New session wish", message_id=2)
    assert len(harness.sent_messages()) == before_count + 1

    async def get_watermark(conn: Any) -> tuple[int, int] | None:
        row = await conn.execute(
            text(
                "SELECT message_id, updated_at FROM bot_capture_order "
                "WHERE owner = 101 AND chat = 101"
            )
        )
        fetched = row.fetchone()
        return (int(fetched[0]), int(fetched[1])) if fetched is not None else None

    watermark = await store.transaction(get_watermark)
    assert watermark is not None
    assert watermark[0] == 2
    assert watermark[1] > stale_ts
