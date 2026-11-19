"""Failing repro tests for atomic WishlistStore.execute_with_connection and bot capture save."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from tests.test_bot_capture_repro import OWNER, _action, _count, _setup
from wishenka.wishlists.service import WishlistService
from wishenka.wishlists.store import WishlistStore

pytestmark = pytest.mark.timeout(15)


async def _seed_wishlist_and_draft(store: WishlistStore, draft_id: str) -> int:
    async def create_list(service: WishlistService) -> int:
        wishlist = await service.create_wishlist(owner=OWNER, title="Home")
        return wishlist.id

    wishlist_id = await store.execute(create_list)

    async def insert_draft(conn: AsyncConnection) -> None:
        await conn.execute(
            text(
                "INSERT INTO bot_drafts "
                "(id, owner, chat, revision, state, data, list_id, edit_field, expires) "
                "VALUES (:id, :owner, :chat, 1, 'active', '{}', :list_id, NULL, "
                "'2099-01-01T00:00:00+00:00')"
            ),
            {
                "id": draft_id,
                "owner": OWNER.telegram_id,
                "chat": OWNER.telegram_id,
                "list_id": wishlist_id,
            },
        )

    await store.transaction(insert_draft)
    return wishlist_id


async def test_execute_with_connection_commits_service_and_sql_atomically() -> None:
    store = WishlistStore("sqlite+aiosqlite:///:memory:")
    await store.initialize()
    try:
        wishlist_id = await _seed_wishlist_and_draft(store, "draft-commit")

        async def commit_both(service: WishlistService, conn: AsyncConnection) -> int:
            item = await service.add_wish_item(wishlist_id, OWNER, title="Ceramic Lamp")
            await conn.execute(
                text(
                    "UPDATE bot_drafts SET state = 'saved', "
                    "receipt_list_id = :list_id, receipt_item_id = :item_id "
                    "WHERE id = :id"
                ),
                {"list_id": wishlist_id, "item_id": item.id, "id": "draft-commit"},
            )
            return item.id

        item_id = await store.execute_with_connection(commit_both)
        assert await _count(store, wishlist_id) == 1

        async def fetch_draft(conn: AsyncConnection) -> Any:
            result = await conn.execute(
                text(
                    "SELECT state, receipt_list_id, receipt_item_id FROM bot_drafts WHERE id = :id"
                ),
                {"id": "draft-commit"},
            )
            return result.first()

        row = await store.transaction(fetch_draft)
        assert row == ("saved", wishlist_id, item_id)
    finally:
        await store.engine.dispose()


async def test_execute_with_connection_rolls_back_service_and_sql_on_error() -> None:
    store = WishlistStore("sqlite+aiosqlite:///:memory:")
    await store.initialize()
    try:
        wishlist_id = await _seed_wishlist_and_draft(store, "draft-rollback")

        async def fail_after_both(service: WishlistService, conn: AsyncConnection) -> None:
            item = await service.add_wish_item(wishlist_id, OWNER, title="Broken Lamp")
            await conn.execute(
                text(
                    "UPDATE bot_drafts SET state = 'saved', "
                    "receipt_list_id = :list_id, receipt_item_id = :item_id "
                    "WHERE id = :id"
                ),
                {"list_id": wishlist_id, "item_id": item.id, "id": "draft-rollback"},
            )
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            await store.execute_with_connection(fail_after_both)

        assert await _count(store, wishlist_id) == 0

        async def fetch_draft(conn: AsyncConnection) -> Any:
            result = await conn.execute(
                text(
                    "SELECT state, receipt_list_id, receipt_item_id FROM bot_drafts WHERE id = :id"
                ),
                {"id": "draft-rollback"},
            )
            return result.first()

        row = await store.transaction(fetch_draft)
        assert row == ("active", None, None)
    finally:
        await store.engine.dispose()


async def test_bot_capture_save_uses_execute_with_connection_and_preserves_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness, store, users, ids, _ = await _setup(tmp_path, monkeypatch)
    try:
        calls = 0
        original = store.execute_with_connection

        async def spy(operation: Any) -> Any:
            nonlocal calls
            calls += 1
            return await original(operation)

        monkeypatch.setattr(store, "execute_with_connection", spy)

        await harness.text("Lamp")
        save = _action(harness.last_message(), ("save", "сохран"))
        await harness.callback(save)

        assert calls >= 1
        assert "saved" in (harness.last_message().text or "").casefold()
        assert await _count(store, ids[0]) == 1

        await harness.callback(save)
        assert calls >= 2
        assert await _count(store, ids[0]) == 1
    finally:
        await harness.bot.session.close()
        await users.engine.dispose()
        await store.engine.dispose()


def test_bot_capture_does_not_access_private_store_read_write() -> None:
    capture_path = Path(__file__).resolve().parents[1] / "wishenka" / "bot" / "capture.py"
    tree = ast.parse(capture_path.read_text(encoding="utf-8"), filename=str(capture_path))
    private_attrs = {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr in {"_read", "_write"}
    }
    assert private_attrs == set()
