"""Checks for one wishlist rule set (WISHENKA-323).

Screens list and share a seeded wishlist without an injected service. A
store-backed history write keeps existing repository rows. Bot capture save
persists the wish through RepoWishlistOps.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot, Dispatcher
from aiogram.methods import SendMessage
from aiogram.types import InlineKeyboardMarkup, Update
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from wishenka.auth.models import AuthenticatedUser, TelegramUser
from wishenka.auth.session import SessionTokenService
from wishenka.bot.entry import create_router
from wishenka.config import Settings
from wishenka.items.schemas import ItemPreviewDTO
from wishenka.users.store import UserStore
from wishenka.web.app import create_app
from wishenka.wishlists.models import ViewHistoryEntry, WishItem
from wishenka.wishlists.repo_ops import RepoWishlistOps
from wishenka.wishlists.repository import WishlistRepository
from wishenka.wishlists.service import WishlistService
from wishenka.wishlists.store import WishlistStore

pytestmark = pytest.mark.timeout(30)

OWNER = AuthenticatedUser(telegram_id=101, first_name="Owner", auth_method="session_token")
SEEDED_TITLE = "One Rule List"
HISTORY_ROWS = 21


class _RejectingScreenService:
    """Stand-in that fails if a screen prefers the injected wishlist service."""

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AssertionError("injected wishlist service must not be used")

        async def reject(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("injected wishlist service must not be used")

        return reject


class _CaptureHarness:
    """Deliver a private capture draft and its save callback without network access."""

    def __init__(self, dispatcher: Dispatcher, bot: Bot, sent: list[Any]) -> None:
        self.dispatcher = dispatcher
        self.bot = bot
        self.sent = sent
        self.sequence = 0

    async def text(self, body: str) -> None:
        self.sequence += 1
        update = Update.model_validate(
            {
                "update_id": self.sequence,
                "message": {
                    "message_id": self.sequence,
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

    def last_save_callback(self) -> str:
        for method in reversed(self.sent):
            if isinstance(method, SendMessage) and isinstance(
                method.reply_markup, InlineKeyboardMarkup
            ):
                for row in method.reply_markup.inline_keyboard:
                    for button in row:
                        data = button.callback_data
                        if data and data.startswith("cap:") and data.endswith(":save"):
                            return data
        raise AssertionError("No capture save callback found")


def _settings(tmp_path: Path, name: str) -> Settings:
    return Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / name}",
        secret_key="wishenka-323-repro",
        background_cleanup_enabled=False,
        receipt_notice_worker_enabled=False,
    )


def test_screen_ignores_injected_wishlist_service(tmp_path: Path) -> None:
    """A seeded list is listed and shared even when an injected service rejects calls."""
    app = create_app(_settings(tmp_path, "screen.db"))
    sessions = SessionTokenService(app.state.settings.secret_key)
    headers = {"Authorization": f"Bearer {sessions.create_token(OWNER.telegram_id, 'Owner')}"}

    async def seed(conn: AsyncConnection) -> str:
        ops = RepoWishlistOps(WishlistRepository(conn))
        wishlist = await ops.create_wishlist(owner=OWNER, title=SEEDED_TITLE)
        return wishlist.public_token

    with TestClient(app, raise_server_exceptions=False) as client:
        portal = client.portal
        assert portal is not None
        token = portal.call(app.state.wishlist_store.transaction, seed)
        app.state.wishlist_service = _RejectingScreenService()
        listed = client.get("/api/wishlists", headers=headers)
        shared = client.get(f"/share/{token}")

    assert listed.status_code == 200
    assert any(row["name"] == SEEDED_TITLE for row in listed.json())
    assert shared.status_code == 200
    assert SEEDED_TITLE in shared.text


def test_record_view_keeps_existing_history_rows(tmp_path: Path) -> None:
    """Recording one more view leaves all 21 repository history rows in place."""
    app = create_app(_settings(tmp_path, "history.db"))
    base = datetime(2026, 1, 1, tzinfo=UTC)

    async def seed(conn: AsyncConnection) -> int:
        repo = WishlistRepository(conn)
        ops = RepoWishlistOps(repo)
        first_id = 0
        for index in range(HISTORY_ROWS):
            wishlist = await ops.create_wishlist(owner=OWNER, title=f"History {index}")
            if index == 0:
                first_id = wishlist.id
            await repo.record_view(
                ViewHistoryEntry(
                    user_id=OWNER.telegram_id,
                    wishlist_id=wishlist.id,
                    viewed_at=base + timedelta(minutes=index),
                )
            )
        return first_id

    async def count_rows(conn: AsyncConnection) -> int:
        value = await conn.scalar(
            text("SELECT COUNT(*) FROM wl_view_history WHERE user_id = :uid"),
            {"uid": OWNER.telegram_id},
        )
        return int(value or 0)

    async def ensure_user() -> None:
        await app.state.user_store.upsert_user(
            TelegramUser(id=OWNER.telegram_id, first_name=OWNER.first_name)
        )

    with TestClient(app) as client:
        portal = client.portal
        assert portal is not None
        portal.call(ensure_user)
        wishlist_id = portal.call(app.state.wishlist_store.transaction, seed)
        portal.call(app.state.domain_service.record_view, OWNER, wishlist_id)
        remaining = portal.call(app.state.wishlist_store.transaction, count_rows)

    assert remaining == HISTORY_ROWS


async def test_capture_save_uses_repository_add_wish_item(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Capture save persists the wish through RepoWishlistOps on the open connection."""
    url = f"sqlite+aiosqlite:///{tmp_path / 'capture.db'}"
    store = WishlistStore(url)
    users = UserStore(url)
    await store.initialize()
    await WishlistService(store).create_wishlist(owner=OWNER, title="List 1")
    saved: list[tuple[WishItem, bool]] = []
    original = RepoWishlistOps.add_wish_item

    async def spy(self: RepoWishlistOps, *args: Any, **kwargs: Any) -> WishItem:
        item = await original(self, *args, **kwargs)
        saved.append((item, self.repo.conn.in_transaction()))
        return item

    monkeypatch.setattr(RepoWishlistOps, "add_wish_item", spy)
    preview = AsyncMock()
    preview.preview = AsyncMock(return_value=ItemPreviewDTO(title="Desk lamp"))
    deps = SimpleNamespace(
        mini_app_url="https://example.test/miniapp",
        user_store=users,
        wishlist_store=store,
        preview_service=preview,
        clock=lambda: datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
    )
    sent: list[Any] = []

    async def transport(_bot: Bot, method: Any, request_timeout: Any = None) -> bool:
        sent.append(method)
        return True

    monkeypatch.setattr(Bot, "__call__", transport)
    dispatcher = Dispatcher()
    dispatcher.include_router(create_router(deps))
    bot = Bot("123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")
    harness = _CaptureHarness(dispatcher, bot, sent)
    try:
        await harness.text("Desk lamp")
        await harness.callback(harness.last_save_callback())

        async def read_items(conn: AsyncConnection) -> list[tuple[int, str]]:
            result = await conn.execute(text("SELECT id, title FROM wl_items ORDER BY id"))
            return [(int(row.id), str(row.title)) for row in result]

        rows = await store.transaction(read_items)
    finally:
        await store.dispose()
        await users.engine.dispose()

    assert len(rows) == 1
    assert len(saved) == 1
    item, connection_open = saved[0]
    assert connection_open
    assert rows == [(item.id, item.title)]
