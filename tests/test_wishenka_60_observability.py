"""Observability tests for WISHENKA-60 (Step 6): structured logs and privacy invariants."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tests.notice_support import FakeNoticeSender
from tests.receipt_support import (
    GIFTER,
    GIFTER_ID,
    OWNER,
    OWNER_ID,
    open_store,
    seed_users,
    sql_exec,
)
from tests.test_notice_delivery_repro import _verify_start
from tests.test_receipt_notices import _Env
from wishenka.notices.store import NoticeStore
from wishenka.wishlists.models import WishlistRole
from wishenka.wishlists.service import WishlistService

pytestmark = pytest.mark.timeout(60)

_NOTICE_LOGGER = "wishenka.wishlists.notices"
_FORBIDDEN_JOIN_KEYS = {
    "receipt_id",
    "item_id",
    "wishlist_id",
    "event_type",
    "giver_user_id",
    "user_id",
    "chat_id",
}


def _notice_events(caplog: pytest.LogCaptureFixture, event_name: str) -> list[logging.LogRecord]:
    return [
        r
        for r in caplog.records
        if r.name == _NOTICE_LOGGER and getattr(r, "event", "") == event_name
    ]


def _assert_no_private_leak(
    records: list[logging.LogRecord],
    forbidden_strings: tuple[str, ...],
    forbidden_ids: tuple[int, ...],
) -> None:
    for record in records:
        extras = {
            k: v
            for k, v in record.__dict__.items()
            if k in _FORBIDDEN_JOIN_KEYS or isinstance(v, (str, int))
        }
        assert not (_FORBIDDEN_JOIN_KEYS & set(record.__dict__.keys()))
        rendered = f"{record.getMessage()} {extras}"
        for text_val in forbidden_strings:
            assert text_val not in rendered
        for uid in forbidden_ids:
            assert uid not in (record.__dict__.get("user_id"), record.__dict__.get("chat_id"))


async def test_shared_event_emission_logs_after_commit_and_not_on_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Shared event emission logs queued count after commit and emits nothing on rollback."""
    db = tmp_path / "shared-emit-obs.db"
    async with open_store(db) as store:
        seed_users(db, GIFTER_ID)
        await _verify_start(monkeypatch, db, GIFTER_ID)
        for uid, fname in ((OWNER_ID, "Alice"), (GIFTER_ID, "Gifter")):
            sql_exec(
                db,
                "INSERT OR IGNORE INTO users (telegram_id, first_name, created_at, updated_at) "
                "VALUES (?, ?, '2026-01-01', '2026-01-01')",
                (uid, fname),
            )

        async def setup(service: WishlistService) -> int:
            wl = await service.create_wishlist(owner=OWNER, title="Secret Birthday Token123")
            wl.is_collaborative = True
            await service.add_member(wl.id, OWNER, GIFTER_ID, role=WishlistRole.MEMBER)
            return wl.id

        wl_id = await store.execute(setup)
        caplog.clear()
        caplog.set_level(logging.DEBUG, logger=_NOTICE_LOGGER)

        async def transfer(service: WishlistService) -> None:
            await service.transfer_ownership(wl_id, OWNER, GIFTER_ID)

        await store.execute(transfer)
        queued_logs = _notice_events(caplog, "shared_notice_events_queued")
        assert len(queued_logs) == 1
        assert queued_logs[0].__dict__["kind"] == "membership_changed"
        assert queued_logs[0].__dict__["queued_count"] == 1
        _assert_no_private_leak(
            queued_logs,
            ("Secret Birthday", "Token123"),
            (OWNER_ID, GIFTER_ID),
        )

        caplog.clear()

        async def failing_transfer(service: WishlistService) -> None:
            service._record_shared_event("list_updated", service._wishlists[wl_id], None, OWNER_ID)
            raise RuntimeError("abort transaction")

        with pytest.raises(RuntimeError, match="abort transaction"):
            await store.execute(failing_transfer)

        assert _notice_events(caplog, "shared_notice_events_queued") == []


async def test_purge_finished_logs_receipt_and_reminder_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """purge_finished emits notice_outbox_purged with split counts only when rows are deleted."""
    db = tmp_path / "purge-obs.db"
    async with open_store(db) as store:
        await _verify_start(monkeypatch, db, GIFTER_ID)
        for uid, fname in ((OWNER_ID, "Alice"), (GIFTER_ID, "Gifter")):
            sql_exec(
                db,
                "INSERT OR IGNORE INTO users (telegram_id, first_name, created_at, updated_at) "
                "VALUES (?, ?, '2026-01-01', '2026-01-01')",
                (uid, fname),
            )

        async def setup(service: WishlistService) -> tuple[int, int]:
            wl = await service.create_wishlist(owner=OWNER, title="Private List")
            item = await service.add_wish_item(wl.id, OWNER, title="Private Gift", quantity=2)
            await service.create_reservation(item.id, GIFTER, quantity=1)
            return wl.id, item.id

        wl_id, item_id = await store.execute(setup)

        async def fulfill_and_archive(service: WishlistService) -> None:
            await service.record_item_fulfillment(item_id, OWNER, 1)
            await service.archive_wishlist(wl_id, OWNER)

        await store.execute(fulfill_and_archive)

        worker = _Env(store, db).worker(FakeNoticeSender())
        now = int(time.time()) + 10
        await worker.run_once(now)
        await worker.run_once(now + 1)

        notice_store = NoticeStore(store, _Env(store, db).settings)
        caplog.set_level(logging.INFO, logger=_NOTICE_LOGGER)

        # Threshold in the past: nothing purged -> no log emitted.
        assert await notice_store.purge_finished(datetime.now(UTC) - timedelta(days=1)) == 0
        assert _notice_events(caplog, "notice_outbox_purged") == []

        # Future threshold: purges both receipt and reminder rows and logs counts.
        purged = await notice_store.purge_finished(datetime.now(UTC) + timedelta(days=1))
        assert purged >= 2
        purge_logs = _notice_events(caplog, "notice_outbox_purged")
        assert len(purge_logs) == 1
        assert purge_logs[0].__dict__["receipt_purged"] == 1
        assert purge_logs[0].__dict__["reminder_purged"] >= 1
        assert purge_logs[0].__dict__["total_purged"] == purged
        _assert_no_private_leak(
            purge_logs,
            ("Private List", "Private Gift"),
            (OWNER_ID, GIFTER_ID),
        )


async def test_recipient_exclusion_skip_logs_safe_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """When a giver becomes the wish recipient, claim_reminder logs service_notice_skipped."""
    db = tmp_path / "skip-obs.db"
    async with open_store(db) as store:
        await _verify_start(monkeypatch, db, GIFTER_ID)
        for uid, fname in ((OWNER_ID, "Alice"), (GIFTER_ID, "Gifter")):
            sql_exec(
                db,
                "INSERT OR IGNORE INTO users (telegram_id, first_name, created_at, updated_at) "
                "VALUES (?, ?, '2026-01-01', '2026-01-01')",
                (uid, fname),
            )

        async def setup(service: WishlistService) -> int:
            wl = await service.create_wishlist(owner=OWNER, title="Collaborative Secret")
            wl.is_collaborative = True
            item = await service.add_wish_item(wl.id, OWNER, title="Surprise Camera", quantity=1)
            await service.create_reservation(item.id, GIFTER, quantity=1)
            return item.id

        item_id = await store.execute(setup)
        sql_exec(db, "DELETE FROM reminder_outbox")

        async def update_item(service: WishlistService) -> None:
            await service.update_wish_item(item_id, OWNER, title="Surprise Camera v2")

        await store.execute_wish(update_item, item_id=item_id)
        # Giver becomes the designated recipient before delivery.
        sql_exec(
            db,
            "UPDATE wl_items SET recipient_user_id = ? WHERE id = ?",
            (GIFTER_ID, item_id),
        )

        caplog.set_level(logging.DEBUG, logger=_NOTICE_LOGGER)
        sender = FakeNoticeSender()
        worker = _Env(store, db).worker(sender)
        now = int(time.time()) + 10
        await worker.run_once(now)

        assert sender.calls == []
        skip_logs = _notice_events(caplog, "service_notice_skipped")
        assert len(skip_logs) == 1
        assert skip_logs[0].__dict__["kind"] == "item_updated"
        assert skip_logs[0].__dict__["reason"] == "ineligible"
        _assert_no_private_leak(
            skip_logs,
            ("Collaborative Secret", "Surprise Camera"),
            (OWNER_ID, GIFTER_ID),
        )


async def test_partial_receipt_archival_logs_sent_and_summary_without_leaks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Partial receipt followed by wish archival logs receipt_notice_sent and window summary."""
    db = tmp_path / "partial-archival-obs.db"
    async with open_store(db) as store:
        await _verify_start(monkeypatch, db, GIFTER_ID)
        for uid, fname in ((OWNER_ID, "Alice"), (GIFTER_ID, "Gifter")):
            sql_exec(
                db,
                "INSERT OR IGNORE INTO users (telegram_id, first_name, created_at, updated_at) "
                "VALUES (?, ?, '2026-01-01', '2026-01-01')",
                (uid, fname),
            )

        async def setup(service: WishlistService) -> tuple[int, int]:
            wl = await service.create_wishlist(owner=OWNER, title="Secret List")
            item = await service.add_wish_item(wl.id, OWNER, title="Secret Watch", quantity=3)
            await service.create_reservation(item.id, GIFTER, quantity=2)
            return wl.id, item.id

        wl_id, item_id = await store.execute(setup)
        sql_exec(db, "DELETE FROM reminder_outbox")

        async def fulfill_then_archive(service: WishlistService) -> None:
            await service.record_item_fulfillment(item_id, OWNER, 1)
            await service.archive_wish_item(wl_id, item_id, OWNER)

        await store.execute(fulfill_then_archive)

        caplog.clear()
        caplog.set_level(logging.DEBUG, logger=_NOTICE_LOGGER)
        sender = FakeNoticeSender()
        now = int(time.time()) + 10
        worker = _Env(store, db).worker(sender, lambda: float(now))
        await worker.run_once(now)
        worker.flush_if_due(now + 3600)

        sent_logs = _notice_events(caplog, "receipt_notice_sent")
        assert len(sent_logs) == 1
        summaries = _notice_events(caplog, "receipt_notice_window_summary")
        assert len(summaries) == 1
        assert summaries[0].__dict__["sent"] == 1
        _assert_no_private_leak(
            [r for r in caplog.records if r.name == _NOTICE_LOGGER],
            ("Secret List", "Secret Watch"),
            (OWNER_ID, GIFTER_ID),
        )
