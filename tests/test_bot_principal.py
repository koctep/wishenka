"""Unit tests for ``wishenka.bot.principal.ensure_private_bot_user``."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text

import wishenka.bot.principal as principal_mod
from wishenka.bot.principal import ensure_private_bot_user
from wishenka.notices.destinations import upsert_bot_destination as real_upsert_bot_destination
from wishenka.users.store import UserStore
from wishenka.wishlists.store import WishlistStore

pytestmark = pytest.mark.timeout(10)


async def _make_stores(
    tmp_path: Path, db_name: str = "principal.db"
) -> tuple[WishlistStore, UserStore]:
    """Create and initialize WishlistStore + UserStore sharing one SQLite database."""
    url = f"sqlite+aiosqlite:///{tmp_path / db_name}"
    store = WishlistStore(url)
    users = UserStore(url)
    await store.initialize()
    await users.initialize()
    return store, users


def _make_tg_user(user_id: int = 101) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        first_name="Alice",
        last_name=None,
        username="alice",
        language_code="en",
        is_premium=False,
    )


async def _fetch_destination(users: UserStore, user_id: int) -> tuple[int, int, int, int] | None:
    async with users.engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT user_id, chat_id, active, updated_at "
                    "FROM bot_destinations WHERE user_id = :id"
                ),
                {"id": user_id},
            )
        ).first()
    if row is None:
        return None
    return (int(row.user_id), int(row.chat_id), int(row.active), int(row.updated_at))


@pytest.mark.asyncio
async def test_ensure_private_bot_user_returns_none_when_user_missing() -> None:
    """Missing Telegram user returns None without touching user_store."""
    fake_store = SimpleNamespace(
        get_by_telegram_id=AsyncMock(),
        upsert_from_bot=AsyncMock(),
    )
    deps = SimpleNamespace(user_store=fake_store)

    result = await ensure_private_bot_user(deps, None, 101)

    assert result is None
    fake_store.get_by_telegram_id.assert_not_awaited()
    fake_store.upsert_from_bot.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "deps",
    [
        SimpleNamespace(),
        SimpleNamespace(user_store=None),
    ],
)
async def test_ensure_private_bot_user_returns_none_when_user_store_missing(
    deps: SimpleNamespace,
) -> None:
    """Absent or None user_store returns None without raising."""
    result = await ensure_private_bot_user(deps, _make_tg_user(101), 101)
    assert result is None


@pytest.mark.asyncio
async def test_ensure_private_bot_user_returns_none_for_group_chat(tmp_path: Path) -> None:
    """Non-private chats (chat_id != user.id) must be ignored without DB writes."""
    store, users = await _make_stores(tmp_path, "group_chat.db")
    try:
        get_spy = AsyncMock(side_effect=users.get_by_telegram_id)
        upsert_spy = AsyncMock(side_effect=users.upsert_from_bot)
        deps = SimpleNamespace(
            user_store=SimpleNamespace(
                engine=users.engine,
                get_by_telegram_id=get_spy,
                upsert_from_bot=upsert_spy,
            )
        )
        tg_user = _make_tg_user(101)

        result = await ensure_private_bot_user(deps, tg_user, -100123456)

        assert result is None
        get_spy.assert_not_awaited()
        upsert_spy.assert_not_awaited()
        assert await _fetch_destination(users, 101) is None
    finally:
        await users.engine.dispose()
        await store.engine.dispose()


@pytest.mark.asyncio
async def test_ensure_private_bot_user_uses_preresolved_user_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pre-resolved user_record bypasses lookup/upsert and activates bot destination."""
    store, users = await _make_stores(tmp_path, "preresolved.db")
    try:
        tg_user = _make_tg_user(202)
        preresolved = await users.upsert_from_bot(tg_user)

        get_spy = AsyncMock(side_effect=users.get_by_telegram_id)
        upsert_spy = AsyncMock(side_effect=users.upsert_from_bot)
        monkeypatch.setattr(users, "get_by_telegram_id", get_spy)
        monkeypatch.setattr(users, "upsert_from_bot", upsert_spy)

        deps = SimpleNamespace(user_store=users)

        result = await ensure_private_bot_user(
            deps, tg_user, 202, user_record=preresolved, now=1_700_000_000
        )

        assert result == preresolved
        get_spy.assert_not_awaited()
        upsert_spy.assert_not_awaited()
        assert await _fetch_destination(users, 202) == (202, 202, 1, 1_700_000_000)
    finally:
        await users.engine.dispose()
        await store.engine.dispose()


@pytest.mark.asyncio
async def test_ensure_private_bot_user_clock_and_now_normalization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify explicit now, datetime clock, int clock, and missing/non-callable clock."""
    store, users = await _make_stores(tmp_path, "clock_norm.db")
    try:
        tg_user = _make_tg_user(303)
        preresolved = await users.upsert_from_bot(tg_user)

        # 1. Explicit now overrides dependencies.clock().
        deps_override = SimpleNamespace(user_store=users, clock=lambda: 999)
        await ensure_private_bot_user(
            deps_override, tg_user, 303, user_record=preresolved, now=1_700_000_123
        )
        assert await _fetch_destination(users, 303) == (303, 303, 1, 1_700_000_123)

        # 2. now=None with clock() returning datetime normalizes via int(dt.timestamp()).
        dt_value = datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC)
        deps_dt = SimpleNamespace(user_store=users, clock=lambda: dt_value)
        await ensure_private_bot_user(deps_dt, tg_user, 303, user_record=preresolved)
        assert await _fetch_destination(users, 303) == (303, 303, 1, int(dt_value.timestamp()))

        # 3. now=None with clock() returning int persists that integer.
        deps_int = SimpleNamespace(user_store=users, clock=lambda: 1_700_000_456)
        await ensure_private_bot_user(deps_int, tg_user, 303, user_record=preresolved)
        assert await _fetch_destination(users, 303) == (303, 303, 1, 1_700_000_456)

        # 4. now=None with absent or non-callable clock forwards effective_now=None.
        observed_nows: list[int | None] = []

        async def spy_upsert(conn: Any, user_id: int, chat_id: int, now: int | None = None) -> None:
            observed_nows.append(now)
            await real_upsert_bot_destination(conn, user_id, chat_id, now)

        monkeypatch.setattr(principal_mod, "upsert_bot_destination", spy_upsert)

        await ensure_private_bot_user(
            SimpleNamespace(user_store=users),
            tg_user,
            303,
            user_record=preresolved,
        )
        await ensure_private_bot_user(
            SimpleNamespace(user_store=users, clock="not-callable"),
            tg_user,
            303,
            user_record=preresolved,
        )

        assert observed_nows == [None, None]
        dest = await _fetch_destination(users, 303)
        assert dest is not None
        assert dest[:3] == (303, 303, 1)
    finally:
        await users.engine.dispose()
        await store.engine.dispose()
