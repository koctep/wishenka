"""Failing repro tests for WISHENKA-60 (Step 3, red before Step 4)."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from tests.notice_support import FakeNoticeSender
from tests.receipt_support import (
    GIFTER,
    GIFTER_ID,
    OWNER,
    OWNER_ID,
    app_env,
    bearer,
    open_store,
    outbox_rows,
    sql_exec,
    sql_rows,
)
from tests.test_notice_delivery_repro import _verify_start
from tests.test_receipt_notices import _Env
from wishenka.auth.models import TelegramUser
from wishenka.notices.store import NoticeStore
from wishenka.wishlists.cleanup import run_cleanup_cycle
from wishenka.wishlists.models import WishlistRole
from wishenka.wishlists.service import WishlistService

pytestmark = pytest.mark.timeout(60)


def _reminder_rows(db: Path) -> list[dict[str, Any]]:
    return sql_rows(db, "SELECT * FROM reminder_outbox ORDER BY id")


async def test_partial_receipt_followed_by_wish_archive_still_delivers_receipt_notice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Gap 1: archiving remaining units of a partially received wish keeps receipt notice."""
    db = tmp_path / "partial-archive.db"
    async with open_store(db) as store:
        await _verify_start(monkeypatch, db, GIFTER_ID)

        async def setup(service: WishlistService) -> tuple[int, int]:
            wl = await service.create_wishlist(owner=OWNER, title="Birthday")
            item = await service.add_wish_item(wl.id, OWNER, title="Espresso Machine", quantity=3)
            await service.create_reservation(item.id, GIFTER, quantity=2)
            return wl.id, item.id

        wishlist_id, item_id = await store.execute(setup)
        sql_exec(db, "DELETE FROM reminder_outbox")

        async def fulfill_then_archive(service: WishlistService) -> None:
            await service.record_item_fulfillment(item_id, OWNER, 1)
            await service.archive_wish_item(wishlist_id, item_id, OWNER)

        await store.execute(fulfill_then_archive)

        sender = FakeNoticeSender()
        worker = _Env(store, db).worker(sender)
        now = int(time.time()) + 10
        await worker.run_once(now)
        await worker.run_once(now + 1)

        receipt_rows = outbox_rows(db)
        assert len(receipt_rows) == 1
        assert receipt_rows[0]["status"] == "sent"
        assert len(sender.calls) == 2
        assert all(chat_id == GIFTER_ID for chat_id, _ in sender.calls)


async def test_wishlist_restore_and_update_notify_giver_with_open_reservation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Gap 2 & 3: list_restored and list_updated must notify open-reservation givers."""
    db_name = "list-lifecycle.db"
    db = tmp_path / db_name

    with app_env(tmp_path, db_name) as (client, sessions, _app):
        await _app.state.user_store.upsert_user(TelegramUser(id=OWNER_ID, first_name="Alice"))
        await _app.state.user_store.upsert_user(TelegramUser(id=GIFTER_ID, first_name="Gifter"))
        async with open_store(db) as store:
            await _verify_start(monkeypatch, db, GIFTER_ID)

            async def setup(service: WishlistService) -> int:
                wl = await service.create_wishlist(owner=OWNER, title="Anniversary")
                item = await service.add_wish_item(wl.id, OWNER, title="Record Player")
                await service.create_reservation(item.id, GIFTER, quantity=1)
                return wl.id

            wishlist_id = await store.execute(setup)
            sql_exec(db, "DELETE FROM reminder_outbox")

            async def lifecycle(service: WishlistService) -> None:
                await service.archive_wishlist(wishlist_id, OWNER)
                await service.unarchive_wishlist(wishlist_id, OWNER)
                await service.update_wishlist_settings(
                    wishlist_id, OWNER, title="Anniversary Updated"
                )

            await store.execute(lifecycle)

        resp = client.patch(
            f"/api/wishlists/{wishlist_id}",
            headers=bearer(sessions, OWNER_ID, "Alice"),
            json={"name": "Anniversary Renamed"},
        )
        assert resp.status_code == 200

        async with open_store(db) as store:
            sender = FakeNoticeSender()
            worker = _Env(store, db).worker(sender)
            now = int(time.time()) + 10
            for step in range(4):
                await worker.run_once(now + step)

            assert len(sender.calls) == 4
            assert all(chat_id == GIFTER_ID for chat_id, _ in sender.calls)


async def test_member_role_patch_and_ownership_transfer_emit_membership_changed_notices(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Gap 3: PATCH role and transfer_ownership must emit membership_changed notifications."""
    db_name = "membership-changes.db"
    db = tmp_path / db_name

    with app_env(tmp_path, db_name) as (client, sessions, _app):
        await _app.state.user_store.upsert_user(TelegramUser(id=OWNER_ID, first_name="Alice"))
        await _app.state.user_store.upsert_user(TelegramUser(id=GIFTER_ID, first_name="Gifter"))
        async with open_store(db) as store:
            await _verify_start(monkeypatch, db, GIFTER_ID)

            async def setup(service: WishlistService) -> int:
                wl = await service.create_wishlist(owner=OWNER, title="Team Party")
                wl.is_collaborative = True
                await service.add_member(wl.id, OWNER, GIFTER_ID, role=WishlistRole.MEMBER)
                return wl.id

            wishlist_id = await store.execute(setup)
            sql_exec(db, "DELETE FROM reminder_outbox")

        resp = client.patch(
            f"/api/wishlists/{wishlist_id}/members/{GIFTER_ID}/role",
            headers=bearer(sessions, OWNER_ID, "Alice"),
            json={"role": "admin"},
        )
        assert resp.status_code == 200

        async with open_store(db) as store:

            async def transfer(service: WishlistService) -> None:
                await service.transfer_ownership(wishlist_id, OWNER, GIFTER_ID)

            await store.execute(transfer)

            sender = FakeNoticeSender()
            worker = _Env(store, db).worker(sender)
            now = int(time.time()) + 10
            await worker.run_once(now)
            await worker.run_once(now + 1)

            rows = _reminder_rows(db)
            assert [row["kind"] for row in rows] == ["membership_changed", "membership_changed"]
            assert len(sender.calls) == 2
            assert all(chat_id == GIFTER_ID for chat_id, _ in sender.calls)


async def test_reservation_does_not_grant_shared_event_delivery_when_giver_becomes_wish_recipient(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Gap 4: reservation must not grant shared-event eligibility to the wish recipient."""
    db = tmp_path / "recipient-exclusion.db"
    async with open_store(db) as store:
        await _verify_start(monkeypatch, db, GIFTER_ID)

        async def setup(service: WishlistService) -> int:
            wl = await service.create_wishlist(owner=OWNER, title="Family Gift List")
            wl.is_collaborative = True
            item = await service.add_wish_item(wl.id, OWNER, title="Shared Camera")
            await service.create_reservation(item.id, GIFTER, quantity=1)
            return item.id

        item_id = await store.execute(setup)
        sql_exec(db, "DELETE FROM reminder_outbox")

        async def update_item(service: WishlistService) -> None:
            await service.update_wish_item(item_id, OWNER, title="Shared Camera Pro")

        await store.execute_wish(update_item, item_id=item_id)

        sql_exec(db, "UPDATE wl_items SET recipient_user_id = ? WHERE id = ?", (GIFTER_ID, item_id))

        sender = FakeNoticeSender()
        worker = _Env(store, db).worker(sender)
        now = int(time.time()) + 10
        await worker.run_once(now)
        await worker.run_once(now + 1)

        assert sender.calls == []
        rows = _reminder_rows(db)
        assert rows
        assert all(row["status"] == "skipped" for row in rows)


async def test_purge_finished_cleans_terminal_reminder_outbox_rows(
    tmp_path: Path,
) -> None:
    """Gap 5: purge_finished and run_cleanup_cycle purge expired terminal rows in both queues."""
    db = tmp_path / "retention.db"
    async with open_store(db) as store:
        env = _Env(store, db)
        await env.seed(5, ((GIFTER, 1),))
        await env.receive(1)

        now_dt = datetime(2026, 6, 1, tzinfo=UTC)
        old_iso = (now_dt - timedelta(days=40)).isoformat()
        old_epoch = int((now_dt - timedelta(days=40)).timestamp())
        fresh_epoch = int((now_dt - timedelta(days=1)).timestamp())

        sql_exec(
            db,
            "UPDATE notification_outbox SET status = 'sent', updated_at = ? "
            "WHERE giver_user_id = ?",
            (old_iso, GIFTER_ID),
        )
        sql_exec(db, "DELETE FROM reminder_outbox")

        d = "2026-06-01"
        reminder_rows = [
            (1, "k1", "list_archived", GIFTER_ID, 1, None, d, "sent", 1, old_epoch, None),
            (2, "k2", "list_restored", GIFTER_ID, 1, None, d, "skipped", 0, old_epoch, None),
            (3, "k3", "list_updated", GIFTER_ID, 1, None, d, "failed", 3, old_epoch, None),
            (4, "k4", "item_updated", GIFTER_ID, 1, 1, d, "sent", 1, fresh_epoch, None),
            (5, "k5", "item_added", GIFTER_ID, 1, 1, d, "pending", 0, old_epoch, None),
            (6, "k6", "item_archived", GIFTER_ID, 1, 1, d, "sending", 1, old_epoch, "tok"),
            (7, "k7", "membership_changed", GIFTER_ID, 1, None, d, "uncertain", 1, old_epoch, None),
        ]
        for row in reminder_rows:
            sql_exec(
                db,
                "INSERT INTO reminder_outbox "
                "(id, occurrence_key, kind, user_id, list_id, item_id, event_date, status, "
                "attempts, next_attempt_at, claim_token) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                row,
            )

        notice_store = NoticeStore(store, env.settings)
        await run_cleanup_cycle(store, env.settings, now=now_dt, notice_store=notice_store)

        assert outbox_rows(db) == []
        remaining_ids = [row["id"] for row in _reminder_rows(db)]
        assert remaining_ids == [4, 5, 6, 7]
