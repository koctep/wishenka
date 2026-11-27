"""Red tests for the receipt history migration and purge (WISHENKA-23, R-2, R-4.5).

Today no revision creates ``wl_receipts``; the tests fail on that with a readable message.
"""

from __future__ import annotations

import importlib
import logging
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tests.receipt_support import (
    GIFTER,
    OWNER,
    RECEIPT_COLUMNS,
    open_store,
    outbox_rows,
    receipt_rows,
    require_table,
    seed_wish,
    sql_exec,
    sql_rows,
)
from wishenka.wishlists.alembic.versions import base_normalized
from wishenka.wishlists.migrations import upgrade_to_head_sync
from wishenka.wishlists.service import WishlistService

pytestmark = pytest.mark.timeout(60)

_LOGGER = "wishenka.wishlists.migrations"
_PREVIOUS_HEAD = "add_item_order_index"
_STAMP = "2024-05-01T10:00:00+00:00"
# id, quantity, received, archived
_LEGACY_ITEMS = [(1, 3, 2, 0), (2, 2, 2, 1), (3, 4, 1, 1), (4, 2, 0, 1), (5, 1, 0, 0)]


def _create_legacy(path: Path) -> str:
    connection = sqlite3.connect(path)
    try:
        for statement in base_normalized.DDL:
            connection.execute(statement)
        connection.execute(
            "INSERT INTO wl_lists (id, owner_id, title, public_token, invite_token, created_at, "
            "updated_at) VALUES (1, 101, 'Legacy', 'public-token', 'invite-token', 'now', 'now')"
        )
        for item_id, quantity, received, archived in _LEGACY_ITEMS:
            connection.execute(
                "INSERT INTO wl_items (id, wishlist_id, title, quantity, received_quantity, "
                "is_archived, created_at, updated_at) VALUES (?, 1, ?, ?, ?, ?, ?, ?)",
                (item_id, f"Wish {item_id}", quantity, received, archived, _STAMP, _STAMP),
            )
        connection.commit()
    finally:
        connection.close()
    return f"sqlite+aiosqlite:///{path}"


def _flags(db: Path) -> dict[int, int]:
    rows = sql_rows(db, "SELECT id, is_archived FROM wl_items ORDER BY id")
    return {int(row["id"]): int(row["is_archived"]) for row in rows}


def test_revisions_backfill_and_normalise(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """R-2.2, R-4.5: one approximate record per received wish, full archived rows un-archived."""
    db = tmp_path / "legacy.db"
    url = _create_legacy(db)

    with caplog.at_level(logging.INFO, logger=_LOGGER):
        upgrade_to_head_sync(url)

    rows = receipt_rows(db)
    assert [(r["wish_item_id"], r["quantity"], r["is_approximate"]) for r in rows] == [
        (1, 2, 1),
        (2, 2, 1),
        (3, 1, 1),
    ]
    assert {r["received_at"] for r in rows} == {_STAMP}
    assert _flags(db) == {1: 0, 2: 0, 3: 1, 4: 1, 5: 0}
    stamps = sql_rows(db, "SELECT DISTINCT updated_at FROM wl_items")
    assert [row["updated_at"] for row in stamps] == [_STAMP]
    counts = {
        getattr(r, "event", ""): getattr(r, "rows", None)
        for r in caplog.records
        if getattr(r, "event", "")
        in {"legacy_receipts_backfilled", "legacy_archived_rows_normalised"}
    }
    assert counts == {"legacy_receipts_backfilled": 3, "legacy_archived_rows_normalised": 1}


def _notice_history(db: Path) -> dict[str, object]:
    """Receipts, archive flags, and notice rows a second upgrade must leave unchanged."""
    return {
        "receipts": receipt_rows(db),
        "flags": _flags(db),
        "key": sql_rows(
            db,
            "SELECT event_type, receipt_id, giver_user_id, created_at "
            "FROM notice_receipt_keys ORDER BY receipt_id",
        ),
        "outbox": sql_rows(
            db,
            "SELECT event_type, receipt_id, giver_user_id, status "
            "FROM notification_outbox ORDER BY receipt_id",
        ),
        "fence": sql_rows(
            db,
            "SELECT wish_item_id, user_id, state FROM receipt_delivery_fence ORDER BY wish_item_id",
        ),
    }


def test_upgrade_is_repeatable(tmp_path: Path) -> None:
    """A second upgrade keeps receipts, archive flags, and notice history."""
    db = tmp_path / "again.db"
    url = _create_legacy(db)
    upgrade_to_head_sync(url)
    receipt = sql_rows(db, "SELECT id, wish_item_id FROM wl_receipts ORDER BY id LIMIT 1")[0]
    receipt_id = int(receipt["id"])
    wish_item_id = int(receipt["wish_item_id"])
    sql_exec(
        db,
        "INSERT INTO notification_outbox "
        "(event_type, receipt_id, wishlist_id, wish_item_id, giver_user_id, status, "
        "ambiguous, next_attempt_at, created_at, updated_at) "
        "VALUES ('gift_received', ?, 1, ?, 501, 'uncertain', 1, 0, ?, ?)",
        (receipt_id, wish_item_id, _STAMP, _STAMP),
    )
    sql_exec(
        db,
        "INSERT INTO notice_receipt_keys "
        "(event_type, receipt_id, giver_user_id, created_at) "
        "VALUES ('gift_received', ?, 501, 1700000000)",
        (receipt_id,),
    )
    outbox_id = int(sql_rows(db, "SELECT id FROM notification_outbox")[0]["id"])
    sql_exec(
        db,
        "INSERT INTO receipt_delivery_fence "
        "(wish_item_id, user_id, attempt_id, queue, row_id, state) "
        "VALUES (?, 501, 'attempt', 'gift', ?, 'uncertain')",
        (wish_item_id, outbox_id),
    )
    before = _notice_history(db)

    sql_exec(db, "UPDATE alembic_version SET version_num = ?", (_PREVIOUS_HEAD,))
    upgrade_to_head_sync(url)

    assert _notice_history(db) == before


async def test_receipt_table_has_no_giver_column_and_downgrade_is_irreversible(
    tmp_path: Path,
) -> None:
    """R-2.1: the column set is fixed; the revision cannot be downgraded."""
    async with open_store(tmp_path / "shape.db"):
        pass
    require_table(tmp_path / "shape.db", "wl_receipts")
    columns = sql_rows(tmp_path / "shape.db", "PRAGMA table_info(wl_receipts)")
    assert {row["name"] for row in columns} == RECEIPT_COLUMNS
    revision = importlib.import_module("wishenka.wishlists.alembic.versions.add_gift_receipts")
    with pytest.raises(NotImplementedError):
        revision.downgrade()


async def test_cascade_on_purge_and_soft_delete_keeps_rows(tmp_path: Path) -> None:
    """R-2.3: rows survive soft deletion and go with the list on purge."""
    db = tmp_path / "purge.db"
    async with open_store(db) as store:

        async def setup(service: WishlistService) -> tuple[int, int]:
            wishlist_id, item_id = await seed_wish(service, quantity=5)
            await service.create_reservation(item_id=item_id, user=GIFTER, quantity=1)
            await service.record_item_fulfillment(item_id, OWNER, 2)
            return wishlist_id, item_id

        wishlist_id, _item_id = await store.execute(setup)
        assert len(receipt_rows(db)) == 1
        assert len(outbox_rows(db)) == 1

        async def delete(service: WishlistService) -> None:
            await service.delete_wishlist(wishlist_id, OWNER)

        await delete(WishlistService(store))
        assert len(receipt_rows(db)) == 1
        assert len(outbox_rows(db)) == 1

        purged = await store.purge_archived_wishlists(datetime.now(UTC) + timedelta(days=31))
        assert purged == 1
        assert receipt_rows(db) == []
        assert outbox_rows(db) == []
