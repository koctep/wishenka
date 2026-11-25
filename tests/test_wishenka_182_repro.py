"""Red repro tests for WISHENKA-182: scoped diagnostics & shared private bot principal."""

from __future__ import annotations

import inspect
import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot, Dispatcher
from aiogram.methods import SendMessage
from aiogram.types import Message, Update
from sqlalchemy import event, text

from wishenka.auth.models import AuthenticatedUser, TelegramUser
from wishenka.bot.entry import create_router
from wishenka.items.schemas import ItemPreviewDTO
from wishenka.users.store import UserStore
from wishenka.wishlists.store import WishlistStore

pytestmark = pytest.mark.timeout(30)

OWNER = AuthenticatedUser(telegram_id=101, first_name="Alice", auth_method="session_token")
COLLAB_OWNER = AuthenticatedUser(telegram_id=303, first_name="Bob", auth_method="session_token")
OTHER_USER = AuthenticatedUser(telegram_id=999, first_name="Eve", auth_method="session_token")
SUPPORT_CHAT_ID = -100999888


def _make_private_message_update(
    update_id: int,
    *,
    user_id: int,
    text_value: str,
    language_code: str | None = None,
    first_name: str = "Alice",
) -> Update:
    from_payload: dict[str, Any] = {
        "id": user_id,
        "is_bot": False,
        "first_name": first_name,
    }
    if language_code is not None:
        from_payload["language_code"] = language_code
    return Update.model_validate(
        {
            "update_id": update_id,
            "message": {
                "message_id": update_id,
                "date": 1700000000,
                "chat": {"id": user_id, "type": "private"},
                "from": from_payload,
                "text": text_value,
            },
        }
    )


def _make_callback_update(
    update_id: int,
    *,
    user_id: int,
    data: str,
    language_code: str | None = "en",
) -> Update:
    from_payload: dict[str, Any] = {
        "id": user_id,
        "is_bot": False,
        "first_name": "Alice",
    }
    if language_code is not None:
        from_payload["language_code"] = language_code
    return Update.model_validate(
        {
            "update_id": update_id,
            "callback_query": {
                "id": str(update_id),
                "chat_instance": "private",
                "from": from_payload,
                "message": {
                    "message_id": 1,
                    "date": 1700000000,
                    "chat": {"id": user_id, "type": "private"},
                    "from": {"id": 123456, "is_bot": True, "first_name": "Bot"},
                    "text": "Menu",
                },
                "data": data,
            },
        }
    )


async def test_support_diagnostic_context_avoids_full_table_scans_and_write_tx(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Support submission must scope token queries to the user and read outside BEGIN IMMEDIATE."""
    url = f"sqlite+aiosqlite:///{tmp_path / 'support_diag.db'}"
    store = WishlistStore(url)
    users = UserStore(url)
    await store.initialize()
    await users.initialize()

    for tg_user in (
        TelegramUser(id=OWNER.telegram_id, first_name="Alice", language_code="en"),
        TelegramUser(id=COLLAB_OWNER.telegram_id, first_name="Bob", language_code="en"),
        TelegramUser(id=OTHER_USER.telegram_id, first_name="Eve", language_code="en"),
    ):
        await users.upsert_user(tg_user)

    # Seed owner's wishlist, a collaborative wishlist, and an unrelated user's wishlist + tokens.
    async def seed_owner(service: Any) -> Any:
        return await service.create_wishlist(owner=OWNER, title="Owner List")

    async def seed_collab(service: Any) -> Any:
        wl = await service.create_wishlist(owner=COLLAB_OWNER, title="Collab List")
        await service.join_by_invite(wl.invite_token, OWNER)
        return wl

    async def seed_other(service: Any) -> Any:
        return await service.create_wishlist(owner=OTHER_USER, title="Other User List")

    owner_wl = await store.execute(seed_owner)
    collab_wl = await store.execute(seed_collab)
    other_wl = await store.execute(seed_other)

    async def seed_extra_tokens(conn: Any) -> None:
        await conn.execute(
            text("INSERT INTO wl_tokens (token, wishlist_id, active) VALUES (:tok, :wid, 1)"),
            {"tok": "tok_owner_extra_111", "wid": owner_wl.id},
        )
        await conn.execute(
            text("INSERT INTO wl_tokens (token, wishlist_id, active) VALUES (:tok, :wid, 1)"),
            {"tok": "tok_other_secret_999", "wid": other_wl.id},
        )
        await conn.execute(
            text("INSERT OR IGNORE INTO wl_invite_tokens (token) VALUES (:tok)"),
            {"tok": "i_other_invite_table_999"},
        )

    await store.transaction(seed_extra_tokens)

    preview = AsyncMock()
    preview.preview = AsyncMock(return_value=ItemPreviewDTO(title="Unused"))
    deps = SimpleNamespace(
        mini_app_url="https://example.test/miniapp",
        user_store=users,
        wishlist_store=store,
        preview_service=preview,
        support_chat_id=SUPPORT_CHAT_ID,
        support_admin_ids=(),
    )
    sent: list[Any] = []

    async def transport(_bot: Bot, method: Any, request_timeout: Any = None) -> bool:
        sent.append(method)
        return True

    monkeypatch.setattr(Bot, "__call__", transport)
    dispatcher = Dispatcher()
    dispatcher.include_router(create_router(deps))
    bot = Bot("123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")

    try:
        await dispatcher.feed_update(
            bot, _make_callback_update(1, user_id=OWNER.telegram_id, data="support:open")
        )

        executed: list[tuple[str, bool]] = []
        tx_state = {"immediate": False}

        def on_before_cursor_execute(
            conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool
        ) -> None:
            normalized = " ".join(statement.split())
            upper = normalized.upper()
            if upper.startswith("BEGIN IMMEDIATE"):
                tx_state["immediate"] = True
            elif upper == "BEGIN" or upper in ("COMMIT", "ROLLBACK"):
                tx_state["immediate"] = False
            executed.append((normalized, tx_state["immediate"]))

        def on_tx_end(_conn: Any) -> None:
            tx_state["immediate"] = False

        event.listen(store.engine.sync_engine, "before_cursor_execute", on_before_cursor_execute)
        event.listen(store.engine.sync_engine, "commit", on_tx_end)
        event.listen(store.engine.sync_engine, "rollback", on_tx_end)
        try:
            message_with_tokens = (
                f"Help with my token tok_owner_extra_111 and {owner_wl.public_token} "
                f"and collab {collab_wl.invite_token} "
                f"and other p_other_secret_789 "
                f"https://example.test/share/other_path_tok?startapp=p_other_startapp"
            )
            await dispatcher.feed_update(
                bot,
                _make_private_message_update(
                    2, user_id=OWNER.telegram_id, text_value=message_with_tokens, language_code="en"
                ),
            )
        finally:
            event.remove(
                store.engine.sync_engine, "before_cursor_execute", on_before_cursor_execute
            )
            event.remove(store.engine.sync_engine, "commit", on_tx_end)
            event.remove(store.engine.sync_engine, "rollback", on_tx_end)

        # 1. No unfiltered full-table scans on wl_lists, wl_tokens, or wl_invite_tokens.
        for stmt, _ in executed:
            upper = stmt.upper()
            if "FROM WL_LISTS" in upper:
                assert "WHERE" in upper, f"Unfiltered full-table scan on wl_lists: {stmt}"
            if "FROM WL_TOKENS" in upper:
                assert "WHERE" in upper, f"Unfiltered full-table scan on wl_tokens: {stmt}"
            if "FROM WL_INVITE_TOKENS" in upper:
                assert "WHERE" in upper, f"Unfiltered full-table scan on wl_invite_tokens: {stmt}"

        # 2. Rate-limit check and diagnostic reads must NOT run inside BEGIN IMMEDIATE.
        read_prefixes = (
            "SELECT CREATED_AT FROM SUPPORT_TICKETS",
            "SELECT ACTIVE FROM BOT_DESTINATIONS",
            "SELECT COUNT(*) FROM WL_LISTS",
            "SELECT COUNT(*) FROM WL_MEMBERS",
            "SELECT 1 FROM BOT_DRAFTS",
            "SELECT PUBLIC_TOKEN",
            "SELECT L.PUBLIC_TOKEN",
            "SELECT T.TOKEN FROM WL_TOKENS",
        )
        for stmt, in_immediate in executed:
            upper = stmt.upper()
            if any(upper.startswith(prefix) for prefix in read_prefixes):
                assert not in_immediate, (
                    f"Read-only diagnostic/rate-limit query ran inside BEGIN IMMEDIATE: {stmt}"
                )

        # 3. Redaction still masks both user-owned tokens and standard-format tokens.
        support_msgs = [
            m for m in sent if isinstance(m, SendMessage) and m.chat_id == SUPPORT_CHAT_ID
        ]
        assert len(support_msgs) == 1
        ticket_text = support_msgs[0].text
        for secret in (
            "tok_owner_extra_111",
            owner_wl.public_token,
            collab_wl.invite_token,
            "p_other_secret_789",
            "other_path_tok",
            "p_other_startapp",
        ):
            assert secret not in ticket_text, f"Secret {secret!r} leaked in ticket"
        assert "[REDACTED]" in ticket_text
    finally:
        await bot.session.close()
        await users.engine.dispose()
        await store.engine.dispose()


def test_principal_helper_exists_and_routers_delegate_without_duplication() -> None:
    """All four private bot routers must delegate user/destination init to shared helper."""
    from wishenka.bot import birthdays, capture, entry, principal, support

    assert callable(getattr(principal, "ensure_private_bot_user", None))

    for module in (entry, support, birthdays, capture):
        source = inspect.getsource(module)
        assert "ensure_private_bot_user" in source, (
            f"{module.__name__} does not delegate to wishenka.bot.principal.ensure_private_bot_user"
        )
        assert "upsert_from_bot" not in source, (
            f"{module.__name__} still calls upsert_from_bot directly instead of delegating"
        )


async def test_all_private_routers_preserve_stored_language_and_activate_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Invoking entry, support, birthdays, and capture with language_code=None preserves 'ru'."""
    from wishenka.bot import entry
    from wishenka.bot.birthdays import create_birthday_router
    from wishenka.bot.capture import create_capture_router
    from wishenka.bot.support import create_support_router

    url = f"sqlite+aiosqlite:///{tmp_path / 'principal_routers.db'}"
    store = WishlistStore(url)
    users = UserStore(url)
    await store.initialize()

    tg_id = 505
    seeded = await users.upsert_user(
        TelegramUser(
            id=tg_id,
            first_name="Ivan",
            language_code="ru",
        )
    )
    assert seeded.language_code == "ru"
    assert seeded.locale == "ru"

    preview = AsyncMock()
    preview.preview = AsyncMock(return_value=ItemPreviewDTO(title="Parsed Lamp"))
    deps = SimpleNamespace(
        mini_app_url="https://example.test/miniapp",
        user_store=users,
        wishlist_store=store,
        preview_service=preview,
        support_chat_id=SUPPORT_CHAT_ID,
        support_admin_ids=(),
    )
    sent: list[Any] = []

    async def transport(_bot: Bot, method: Any, request_timeout: Any = None) -> bool:
        sent.append(method)
        return True

    monkeypatch.setattr(Bot, "__call__", transport)
    bot = Bot("123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")

    async def reset_destination() -> None:
        async with users.engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM bot_destinations WHERE user_id = :uid"),
                {"uid": tg_id},
            )

    async def assert_preserved_and_activated(router_name: str) -> None:
        record = await users.get_by_telegram_id(tg_id)
        assert record is not None
        assert record.language_code == "ru", (
            f"{router_name} overwrote stored language_code={record.language_code!r}"
        )
        assert record.locale == "ru", f"{router_name} overwrote stored locale={record.locale!r}"
        async with users.engine.connect() as conn:
            active = await conn.scalar(
                text("SELECT active FROM bot_destinations WHERE user_id = :uid"),
                {"uid": tg_id},
            )
        assert active == 1, f"{router_name} did not activate bot_destinations"

    try:
        # 1. entry._ensure_private_destination without pre-injected user_record
        await reset_destination()
        entry_msg = Message.model_validate(
            {
                "message_id": 10,
                "date": 1700000000,
                "chat": {"id": tg_id, "type": "private"},
                "from": {"id": tg_id, "is_bot": False, "first_name": "Ivan"},
                "text": "/start",
            }
        )
        await entry._ensure_private_destination(deps, entry_msg, None)
        await assert_preserved_and_activated("entry")

        # 2. support router standalone (no LocaleMiddleware)
        await reset_destination()
        support_dp = Dispatcher()
        support_dp.include_router(create_support_router(deps))
        await support_dp.feed_update(
            bot,
            _make_private_message_update(
                11, user_id=tg_id, text_value="/support", first_name="Ivan"
            ),
        )
        await assert_preserved_and_activated("support")

        # 3. birthdays router standalone (no LocaleMiddleware)
        await reset_destination()
        bday_dp = Dispatcher()
        bday_dp.include_router(create_birthday_router(deps))
        await bday_dp.feed_update(
            bot,
            _make_private_message_update(
                12, user_id=tg_id, text_value="/birthdays", first_name="Ivan"
            ),
        )
        await assert_preserved_and_activated("birthdays")

        # 4. capture router standalone (no LocaleMiddleware)
        await reset_destination()
        capture_dp = Dispatcher()
        capture_dp.include_router(create_capture_router(deps))
        await capture_dp.feed_update(
            bot,
            _make_private_message_update(
                13, user_id=tg_id, text_value="Coffee grinder", first_name="Ivan"
            ),
        )
        await assert_preserved_and_activated("capture")
    finally:
        await bot.session.close()
        await users.engine.dispose()
        await store.engine.dispose()


async def test_ensure_private_bot_user_suppresses_user_identifier_logs(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """ensure_private_bot_user must suppress wishenka.users identifier logs on new user creation."""
    from wishenka.bot.principal import ensure_private_bot_user

    url = f"sqlite+aiosqlite:///{tmp_path / 'principal_logs.db'}"
    store = WishlistStore(url)
    users = UserStore(url)
    await store.initialize()
    await users.initialize()
    deps = SimpleNamespace(user_store=users)
    tg_user = SimpleNamespace(
        id=707,
        first_name="NewUser",
        last_name=None,
        username="new_user_707",
        language_code="en",
        is_premium=False,
    )
    try:
        with caplog.at_level(logging.INFO, logger="wishenka.users"):
            record = await ensure_private_bot_user(deps, tg_user, 707)
        assert record is not None
        assert record.telegram_id == 707
        assert not [r for r in caplog.records if r.name.startswith("wishenka.users")], (
            "Expected wishenka.users identifier logs to be suppressed"
        )
    finally:
        await users.engine.dispose()
        await store.engine.dispose()
