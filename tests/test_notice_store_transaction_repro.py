"""Failing repro tests for WISHENKA-180 (Step 3, red before Step 4)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from tests.receipt_support import SQLITE_PREFIX, open_store
from wishenka.config import Settings
from wishenka.notices.store import NoticeStore

pytestmark = pytest.mark.timeout(30)


async def test_notice_store_exposes_public_transaction(tmp_path: Path) -> None:
    """NoticeStore must expose a public async ``transaction(work)`` method."""
    db_path = tmp_path / "notices.db"
    settings = Settings(database_url=f"{SQLITE_PREFIX}{db_path}", secret_key="notice")
    async with open_store(db_path) as wishlist_store:
        notice_store = NoticeStore(wishlist_store, settings)

        async def work(conn: AsyncConnection) -> int:
            row = (await conn.execute(text("SELECT 42 AS answer"))).mappings().one()
            return int(row["answer"])

        result = await notice_store.transaction(work)
        assert result == 42


async def test_notice_store_transaction_rolls_back_on_error(tmp_path: Path) -> None:
    """An exception inside ``NoticeStore.transaction`` must roll back uncommitted writes."""
    db_path = tmp_path / "rollback.db"
    settings = Settings(database_url=f"{SQLITE_PREFIX}{db_path}", secret_key="notice")
    async with open_store(db_path) as wishlist_store:
        notice_store = NoticeStore(wishlist_store, settings)

        async def seed_destination(conn: AsyncConnection) -> None:
            await conn.execute(
                text(
                    "INSERT INTO users (id, telegram_id, first_name, created_at, updated_at) "
                    "VALUES (901, 901, 'RollbackUser', "
                    "'2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')"
                )
            )
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            await notice_store.transaction(seed_destination)

        async def count_users(conn: AsyncConnection) -> int:
            row = (
                await conn.execute(text("SELECT COUNT(*) AS cnt FROM users WHERE id = 901"))
            ).one()
            return int(row[0])

        assert await notice_store.transaction(count_users) == 0


def test_notices_package_has_no_private_store_access() -> None:
    """Modules in ``wishenka/notices/`` must not reach into ``_store._store``."""
    notices_dir = Path(__file__).resolve().parent.parent / "wishenka" / "notices"
    offending: list[str] = []
    for py_file in sorted(notices_dir.glob("*.py")):
        if py_file.name == "store.py":
            continue
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and node.attr == "_store"
                and not (isinstance(node.value, ast.Name) and node.value.id == "self")
            ):
                offending.append(f"{py_file.name}:{node.lineno}")
    assert offending == [], f"Private _store access found in wishenka/notices/: {offending}"
