"""Red tests for the gift notice path (WISHENKA-23, R-6, R-6.7, DoD 7 and 8).

The producer, the settings tables, the queue store, the sender, the worker and the app wiring
do not exist yet. Every sender is a fake; no test contacts Telegram.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import re
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from tests.notice_support import FakeNoticeSender, send_result
from tests.receipt_support import (
    GIFTER,
    GIFTER_ID,
    OTHER_GIFTER,
    OTHER_GIFTER_ID,
    OWNER,
    OWNER_ID,
    TEST_BOT_TOKEN,
    THIRD_GIFTER,
    THIRD_GIFTER_ID,
    app_env,
    attr_of,
    item_received,
    new_symbol,
    open_store,
    outbox_rows,
    receipt_rows,
    require_table,
    seed_wish,
    sql_exec,
)
from wishenka.auth.models import AuthenticatedUser, TelegramUser
from wishenka.config import Settings
from wishenka.users.store import UserStore
from wishenka.web.app import create_app
from wishenka.wishlists.service import WishlistService
from wishenka.wishlists.store import WishlistStore

pytestmark = pytest.mark.timeout(60)

_TEXT = (
    "Желание «{wish}» из списка «{wishlist}» отмечено как полученное.\n"
    "Проверьте свою бронь и при необходимости измените или отмените её."
)
_NOW = "2024-01-01T00:00:00+00:00"
_DAN = AuthenticatedUser(telegram_id=606, first_name="Dan", auth_method="session_token")


class _Env:
    """A migrated store with one list and one wish on a file database."""

    def __init__(
        self, store: WishlistStore, path: Path, *, verify_destinations: bool = False
    ) -> None:
        self.store = store
        self.db = path
        self.verify_destinations = verify_destinations
        self.settings = Settings(database_url=f"sqlite+aiosqlite:///{path}", secret_key="notice")
        self.wishlist_id = 0
        self.item_id = 0

    async def seed(
        self,
        quantity: int = 10,
        promises: tuple[tuple[AuthenticatedUser, int], ...] = (),
        title: str = "Kettle",
        list_title: str = "Alice Birthday",
    ) -> None:
        if self.verify_destinations:
            users = UserStore(self.settings.database_url)
            try:
                for user, _ in promises:
                    profile = await users.upsert_user(
                        TelegramUser(
                            id=user.telegram_id, first_name=user.first_name, language_code="ru"
                        )
                    )
                    from sqlalchemy import text

                    async with users.engine.begin() as conn:
                        await conn.execute(
                            text(
                                "INSERT OR REPLACE INTO bot_destinations "
                                "(user_id, chat_id, active) VALUES (:id, :chat, 1)"
                            ),
                            {"id": profile.telegram_id, "chat": user.telegram_id},
                        )
            finally:
                await users.engine.dispose()

        async def setup(service: WishlistService) -> tuple[int, int]:
            wishlist_id, item_id = await seed_wish(
                service, quantity=quantity, title=title, list_title=list_title
            )
            for user, amount in promises:
                await service.create_reservation(item_id=item_id, user=user, quantity=amount)
            return wishlist_id, item_id

        self.wishlist_id, self.item_id = await self.store.execute(setup)

    async def receive(self, quantity: int, *, full_snapshot: bool = False) -> None:
        async def act(service: WishlistService) -> None:
            await service.record_item_fulfillment(self.item_id, OWNER, quantity)

        if full_snapshot:
            await self.store.execute(act)
        else:
            await self.store.execute_wish(
                act, item_id=self.item_id, operation_name="record_item_fulfillment"
            )

    async def cancel(self, user: AuthenticatedUser) -> None:
        async def act(service: WishlistService) -> None:
            for reservation in list(service._items[self.item_id].reservations):
                if reservation.user_id == user.telegram_id:
                    await service.cancel_reservation(reservation.id, user)

        await self.store.execute(act)

    def settings_user(self, user_id: int, enabled: bool) -> None:
        require_table(self.db, "user_notification_settings")
        sql_exec(
            self.db,
            "INSERT OR REPLACE INTO user_notification_settings VALUES (?, 'gift_received', ?, ?)",
            (user_id, int(enabled), _NOW),
        )

    def settings_list(self, user_id: int, enabled: bool) -> None:
        require_table(self.db, "wl_list_notification_settings")
        sql_exec(
            self.db,
            "INSERT OR REPLACE INTO wl_list_notification_settings "
            "VALUES (?, ?, 'gift_received', ?, ?)",
            (user_id, self.wishlist_id, int(enabled), _NOW),
        )

    def rows_for(self, giver_id: int) -> list[dict[str, Any]]:
        return [row for row in outbox_rows(self.db) if row["giver_user_id"] == giver_id]

    def outbox_one(self) -> dict[str, Any]:
        rows = outbox_rows(self.db)
        assert len(rows) == 1, rows
        return rows[0]

    def worker(self, sender: FakeNoticeSender, clock: Callable[[], float] | None = None) -> Any:
        notice_store_class = new_symbol("wishenka.notices.store", "NoticeStore")
        worker_class = new_symbol("wishenka.notices.worker", "NoticeWorker")
        notice_store = notice_store_class(self.store, self.settings)
        return worker_class(notice_store, sender, self.settings, clock=clock or time.time)


def _base() -> int:
    """A fake 'now' safely after the rows were queued with the real clock."""
    return int(time.time()) + 10


@asynccontextmanager
async def _store_env(tmp_path: Path) -> AsyncIterator[_Env]:
    path = tmp_path / "notices.db"
    async with open_store(path) as store:
        yield _Env(store, path, verify_destinations=True)


async def test_producer_rules(tmp_path: Path) -> None:
    """R-6.1, R-6.2: one pending row per giver with an open promise, per act."""
    async with _store_env(tmp_path) as env:
        await env.seed(10, ((GIFTER, 1), (GIFTER, 1), (OTHER_GIFTER, 1), (THIRD_GIFTER, 1)))
        await env.cancel(OTHER_GIFTER)

        await env.receive(2)

        rows = outbox_rows(env.db)
        assert [r["giver_user_id"] for r in rows] == [GIFTER_ID, THIRD_GIFTER_ID]
        assert {r["status"] for r in rows} == {"pending"}
        assert {r["event_type"] for r in rows} == {"gift_received"}
        assert env.rows_for(OTHER_GIFTER_ID) == []
        assert env.rows_for(OWNER_ID) == []
        receipts = receipt_rows(env.db)
        assert {r["receipt_id"] for r in rows} == {receipts[0]["id"]}

        await env.receive(1, full_snapshot=True)
        assert len(env.rows_for(GIFTER_ID)) == 2
        assert len({r["receipt_id"] for r in env.rows_for(GIFTER_ID)}) == 2


async def test_producer_skips_recipient_and_unpromised(tmp_path: Path) -> None:
    """R-6.2, R-1.4: the person the wish is meant for and an unpromised wish get no notice."""
    async with _store_env(tmp_path) as env:
        await env.seed(10, ((GIFTER, 1),))
        sql_exec(
            env.db,
            "INSERT INTO wl_reservations (id, wish_item_id, user_id, quantity, status, "
            "created_at, updated_at) VALUES (900, ?, ?, 1, 'active', ?, ?)",
            (env.item_id, OWNER_ID, _NOW, _NOW),
        )
        await env.receive(1)
        assert [r["giver_user_id"] for r in outbox_rows(env.db)] == [GIFTER_ID]

    other = tmp_path / "other"
    other.mkdir()
    async with _store_env(other) as bare:
        await bare.seed(5)
        await bare.receive(2)
        assert len(receipt_rows(bare.db)) == 1
        assert outbox_rows(bare.db) == []


async def test_owner_with_promise_on_another_list_is_a_giver(tmp_path: Path) -> None:
    """R-6.2, corner case 18: an owner who promised elsewhere is a giver there."""
    async with _store_env(tmp_path) as env:

        async def setup(service: WishlistService) -> int:
            wishlist = await service.create_wishlist(owner=OTHER_GIFTER, title="Oleg list")
            item = await service.add_wish_item(
                wishlist_id=wishlist.id, actor=OTHER_GIFTER, title="Mug", quantity=3
            )
            await service.create_reservation(item_id=item.id, user=OWNER, quantity=1)
            return item.id

        item_id = await setup(WishlistService(env.store))

        async def act(service: WishlistService) -> None:
            await service.record_item_fulfillment(item_id, OTHER_GIFTER, 1)

        await env.store.execute_wish(act, item_id=item_id, operation_name="record_item_fulfillment")

        assert [r["giver_user_id"] for r in outbox_rows(env.db)] == [OWNER_ID]


async def test_settings_gate_matrix(tmp_path: Path) -> None:
    """R-6.4: list level wins in both directions, default is on, skipped rows are kept."""
    async with _store_env(tmp_path) as env:
        await env.seed(
            10,
            ((GIFTER, 1), (OTHER_GIFTER, 1), (THIRD_GIFTER, 1), (_DAN, 1)),
        )
        # Isolate receipt delivery from reservation-change events produced during setup.
        sql_exec(env.db, "DELETE FROM reminder_outbox WHERE kind='reservation_changed'")
        env.settings_list(GIFTER_ID, False)
        env.settings_user(GIFTER_ID, True)
        env.settings_list(OTHER_GIFTER_ID, True)
        env.settings_user(OTHER_GIFTER_ID, False)
        env.settings_user(THIRD_GIFTER_ID, False)

        await env.receive(1)

        by_giver = {r["giver_user_id"]: r for r in outbox_rows(env.db)}
        assert (by_giver[GIFTER_ID]["status"], by_giver[GIFTER_ID]["skip_reason"]) == (
            "skipped",
            "setting_list",
        )
        assert by_giver[OTHER_GIFTER_ID]["status"] == "pending"
        assert (by_giver[THIRD_GIFTER_ID]["status"], by_giver[THIRD_GIFTER_ID]["skip_reason"]) == (
            "skipped",
            "setting_user",
        )
        assert by_giver[606]["status"] == "pending"

        env.settings_user(THIRD_GIFTER_ID, True)
        env.settings_list(GIFTER_ID, True)
        await env.receive(1)
        rows = env.rows_for(THIRD_GIFTER_ID)
        assert [r["status"] for r in rows] == ["skipped", "pending"]
        assert [r["status"] for r in env.rows_for(GIFTER_ID)] == ["skipped", "pending"]

        sender = FakeNoticeSender()
        now = _base()
        worker = env.worker(sender)
        await worker.run_once(now)
        await worker.run_once(now + 1)
        assert sorted(chat for chat, _text in sender.calls) == sorted(
            [OTHER_GIFTER_ID, OTHER_GIFTER_ID, 606, 606, GIFTER_ID, THIRD_GIFTER_ID]
        )


@pytest.mark.parametrize("path", ["execute_wish", "execute"])
async def test_receipt_and_notice_atomic(tmp_path: Path, path: str) -> None:
    """R-1.8, R-6.5: a failure after the record insert leaves nothing behind."""
    async with _store_env(tmp_path) as env:
        await env.seed(5, ((GIFTER, 1),))
        original = attr_of(env.store, "_flush_receipt_effects")

        async def failing(*args: Any, **kwargs: Any) -> Any:
            await original(*args, **kwargs)
            raise RuntimeError("stop after the insert")

        env.store._flush_receipt_effects = failing  # type: ignore[method-assign]
        with pytest.raises(RuntimeError):
            await env.receive(2, full_snapshot=path == "execute")

        assert item_received(env.db, env.item_id) == 0
        assert receipt_rows(env.db) == []
        assert outbox_rows(env.db) == []


async def test_sender_failure_leaves_receipt(tmp_path: Path) -> None:
    """R-6.5, corner case 15: a failed delivery never changes the receipt."""
    async with _store_env(tmp_path) as env:
        await env.seed(5, ((GIFTER, 1),))
        await env.receive(2)
        sender = FakeNoticeSender([send_result("retryable")])

        await env.worker(sender).run_once(_base())

        assert len(sender.calls) == 1
        assert item_received(env.db, env.item_id) == 2
        assert len(receipt_rows(env.db)) == 1
        row = env.outbox_one()
        assert (row["status"], row["attempts"]) == ("pending", 1)


async def test_retry_backoff_and_max_attempts(tmp_path: Path) -> None:
    """R-6.5: delays 30, 60, 120, 240, then ``failed`` at the fifth attempt."""
    async with _store_env(tmp_path) as env:
        assert attr_of(env.settings, "receipt_notice_max_attempts") == 5
        await env.seed(5, ((GIFTER, 1),))
        await env.receive(1)
        sender = FakeNoticeSender([send_result("retryable", error_class="X")] * 5)
        worker = env.worker(sender)
        now = _base()

        for attempt, delay in enumerate((30, 60, 120, 240), start=1):
            await worker.run_once(now)
            row = env.outbox_one()
            assert (row["status"], row["attempts"], row["next_attempt_at"]) == (
                "pending",
                attempt,
                now + delay,
            )
            await worker.run_once(now + delay - 1)
            assert len(sender.calls) == attempt
            now += delay
        await worker.run_once(now)
        row = env.outbox_one()
        assert (row["status"], row["attempts"], row["last_error_class"]) == ("failed", 5, "X")
        await worker.run_once(now + 10_000)
        assert len(sender.calls) == 5


async def test_rejected_fails_at_once_and_error_class_is_stored(tmp_path: Path) -> None:
    """R-6.5: a blocked bot is final at the first attempt; only the class name is kept."""
    async with _store_env(tmp_path) as env:
        await env.seed(5, ((GIFTER, 1),))
        await env.receive(1)
        sender = FakeNoticeSender([send_result("rejected", error_class="TelegramForbiddenError")])

        await env.worker(sender).run_once(_base())

        row = env.outbox_one()
        assert (row["status"], row["attempts"]) == ("failed", 1)
        assert row["last_error_class"] == "TelegramForbiddenError"
        assert item_received(env.db, env.item_id) == 1


async def test_at_most_one_extra_send(tmp_path: Path) -> None:
    """An ambiguous send is held for explicit operator resolution."""
    async with _store_env(tmp_path) as env:
        await env.seed(5, ((GIFTER, 1),))
        await env.receive(1)
        sender = FakeNoticeSender(
            [send_result("ambiguous", error_class="TelegramNetworkError")] * 3
        )
        worker = env.worker(sender)
        now = _base()

        await worker.run_once(now)
        row = env.outbox_one()
        assert (row["status"], row["ambiguous"]) == ("uncertain", 1)
        await worker.run_once(now + 30)
        assert env.outbox_one()["status"] == "uncertain"
        await worker.run_once(now + 100_000)
        assert len(sender.calls) == 1


async def test_stale_sending_row_is_settled_not_sent(tmp_path: Path) -> None:
    """R-6.6: a stale claim gets the ambiguous transition first and is not sent in that claim."""
    async with _store_env(tmp_path) as env:
        await env.seed(10, ((GIFTER, 1), (OTHER_GIFTER, 1), (THIRD_GIFTER, 1)))
        # Isolate receipt delivery from reservation-change events produced during setup.
        sql_exec(env.db, "DELETE FROM reminder_outbox WHERE kind='reservation_changed'")
        await env.receive(1)
        lease = int(attr_of(env.settings, "receipt_notice_claim_lease_seconds"))
        now = _base()
        stale = now - lease - 1

        def make_stale(giver_id: int, *, ambiguous: int, attempts: int) -> None:
            sql_exec(
                env.db,
                "UPDATE notification_outbox SET status = 'sending', claimed_at = ?, "
                "ambiguous = ?, attempts = ? WHERE giver_user_id = ?",
                (stale, ambiguous, attempts, giver_id),
            )

        make_stale(GIFTER_ID, ambiguous=0, attempts=1)
        make_stale(OTHER_GIFTER_ID, ambiguous=0, attempts=2)
        make_stale(THIRD_GIFTER_ID, ambiguous=0, attempts=5)
        sender = FakeNoticeSender([send_result("ambiguous")])
        worker = env.worker(sender)

        await worker.run_once(now)

        assert sender.calls == []
        first = env.rows_for(GIFTER_ID)[0]
        assert (first["status"], first["ambiguous"], first["claimed_at"]) == ("uncertain", 1, None)
        second = env.rows_for(OTHER_GIFTER_ID)[0]
        assert (second["status"], second["last_error_class"]) == ("uncertain", "StaleClaim")
        assert env.rows_for(THIRD_GIFTER_ID)[0]["status"] == "uncertain"

        await worker.run_once(now + 30)
        assert sender.calls == []
        assert env.rows_for(GIFTER_ID)[0]["status"] == "uncertain"
        await worker.run_once(now + 100_000)
        assert len(sender.calls) == 0


async def test_second_death_after_reclaim_fails_without_third_send(tmp_path: Path) -> None:
    """R-6.6: worker dies, reclaim, dies again: the row fails with no further send."""
    async with _store_env(tmp_path) as env:
        await env.seed(5, ((GIFTER, 1),))
        await env.receive(1)
        lease = int(attr_of(env.settings, "receipt_notice_claim_lease_seconds"))
        now = _base()
        sql_exec(
            env.db,
            "UPDATE notification_outbox SET status = 'sending', claimed_at = ?, attempts = 1",
            (now - lease - 1,),
        )
        sender = FakeNoticeSender()
        worker = env.worker(sender)
        await worker.run_once(now)
        assert env.outbox_one()["status"] == "uncertain"

        from wishenka.notices.operator import resolve

        assert await resolve(env.store, "receipt", env.outbox_one()["id"], "retry", now + 30)

        sql_exec(
            env.db,
            "UPDATE notification_outbox SET status = 'sending', claimed_at = ?, attempts = 2",
            (now + 30,),
        )
        await worker.run_once(now + 30 + lease + 1)

        row = env.outbox_one()
        assert (row["status"], row["last_error_class"]) == ("uncertain", "StaleClaim")
        assert sender.calls == []


async def _wait_for_calls(sender: FakeNoticeSender, count: int) -> None:
    deadline = time.monotonic() + 10
    while len(sender.calls) < count and time.monotonic() < deadline:
        await asyncio.sleep(0.01)
    assert len(sender.calls) >= count, "the send did not start in time"


async def test_late_settle_write_is_ignored(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """R-6.6: a worker that finishes after its row was reclaimed changes nothing."""
    async with _store_env(tmp_path) as env:
        await env.seed(5, ((GIFTER, 1),))
        await env.receive(1)
        lease = int(attr_of(env.settings, "receipt_notice_claim_lease_seconds"))
        gate = asyncio.Event()
        sender_a = FakeNoticeSender([send_result("rejected", error_class="Late")], block_first=gate)
        sender_b = FakeNoticeSender([send_result("delivered")])
        worker_a, worker_b = env.worker(sender_a), env.worker(sender_b)
        now = _base()
        caplog.set_level(logging.DEBUG)

        task_a = asyncio.create_task(worker_a.run_once(now))
        try:
            await _wait_for_calls(sender_a, 1)
            later = now + lease + 1
            await worker_b.run_once(later)
            assert sender_b.calls == []
            await worker_b.run_once(later + 30)
            assert sender_b.calls == []
            assert env.outbox_one()["status"] == "uncertain"
        finally:
            gate.set()
            await asyncio.wait_for(task_a, timeout=20)

        row = env.outbox_one()
        assert (row["status"], row["last_error_class"]) == ("uncertain", "StaleClaim")
        events = [getattr(r, "event", "") for r in caplog.records]
        assert "receipt_notice_late_write_ignored" in events


def _aiogram_sender(monkeypatch: pytest.MonkeyPatch, raising: BaseException | None) -> Any:
    from aiogram import Bot

    build_sender = new_symbol("wishenka.notices.sender", "build_sender")
    sender = build_sender(Settings(bot_token=TEST_BOT_TOKEN))
    assert sender is not None, "a valid token must give a sender"

    async def fake_send(self: Any, chat_id: int, text: str, **kwargs: Any) -> Any:
        if raising is not None:
            raise raising
        return object()

    monkeypatch.setattr(Bot, "send_message", fake_send)
    return sender


def _telegram_error(name: str) -> BaseException:
    from aiogram import exceptions
    from aiogram.methods import SendMessage

    method = SendMessage(chat_id=1, text="x")
    cls = getattr(exceptions, name)
    if name == "TelegramRetryAfter":
        return cls(method=method, message="slow down", retry_after=7)  # type: ignore[no-any-return]
    return cls(method=method, message="boom")  # type: ignore[no-any-return]


async def _outcome(monkeypatch: pytest.MonkeyPatch, error: BaseException | None) -> Any:
    sender = _aiogram_sender(monkeypatch, error)
    try:
        return await sender.send(1, "text")
    finally:
        await sender.close()


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        ("TelegramEntityTooLarge", "rejected"),
        ("TelegramBadRequest", "rejected"),
        ("RestartingTelegram", "ambiguous"),
    ],
)
async def test_sender_outcome_order(
    monkeypatch: pytest.MonkeyPatch, error: str, expected: str
) -> None:
    """Design 7: the ordered mapping, subclasses are tested before their bases."""
    result = await _outcome(monkeypatch, _telegram_error(error))
    assert result.outcome == expected
    assert result.error_class == error


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        ("TelegramServerError", "ambiguous"),
        ("RestartingTelegram", "ambiguous"),
        ("TelegramNetworkError", "ambiguous"),
        ("TelegramRetryAfter", "retryable"),
        ("TelegramUnauthorizedError", "retryable"),
        ("TelegramForbiddenError", "rejected"),
    ],
)
async def test_server_error_is_ambiguous(
    monkeypatch: pytest.MonkeyPatch, error: str, expected: str
) -> None:
    """R-6.6: a 5xx may follow a delivered message; 429 and 401 were not processed."""
    result = await _outcome(monkeypatch, _telegram_error(error))
    assert result.outcome == expected
    if error == "TelegramRetryAfter":
        assert result.retry_after == 7


async def test_unexpected_error_and_success_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    """Design 7: success is delivered, any unexpected exception is ambiguous."""
    assert (await _outcome(monkeypatch, None)).outcome == "delivered"
    unexpected = await _outcome(monkeypatch, ValueError("odd"))
    assert unexpected.outcome == "ambiguous"
    assert unexpected.error_class == "ValueError"


def test_lease_must_outlive_request_timeout() -> None:
    """Design 10: a lease shorter than request timeout plus 30 seconds is refused."""
    fields = Settings.model_fields
    assert "receipt_notice_claim_lease_seconds" in fields, "settings field does not exist yet"
    assert "receipt_notice_request_timeout_seconds" in fields
    with pytest.raises(ValidationError):
        Settings(receipt_notice_claim_lease_seconds=40, receipt_notice_request_timeout_seconds=30)
    assert attr_of(Settings(), "receipt_notice_claim_lease_seconds") >= 60


async def test_send_timeout_is_ambiguous(tmp_path: Path) -> None:
    """Design 7: a send that outlives the request timeout is ``AMBIGUOUS`` (TimeoutError)."""
    async with _store_env(tmp_path) as env:
        env.settings = Settings(
            database_url=env.settings.database_url,
            secret_key="notice",
            receipt_notice_request_timeout_seconds=0.01,
        )
        await env.seed(5, ((GIFTER, 1),))
        await env.receive(1)
        sender = FakeNoticeSender(sleep=30)

        await env.worker(sender).run_once(_base())

        row = env.outbox_one()
        assert (row["status"], row["ambiguous"], row["last_error_class"]) == (
            "uncertain",
            1,
            "TimeoutError",
        )


async def test_fresh_claim_is_not_reclaimed_by_a_second_worker(tmp_path: Path) -> None:
    """Design 7: while a send is within its lease nobody else sends the row."""
    async with _store_env(tmp_path) as env:
        await env.seed(5, ((GIFTER, 1),))
        await env.receive(1)
        gate = asyncio.Event()
        sender_a = FakeNoticeSender(block_first=gate)
        sender_b = FakeNoticeSender()
        worker_a, worker_b = env.worker(sender_a), env.worker(sender_b)
        now = _base()

        task_a = asyncio.create_task(worker_a.run_once(now))
        try:
            await _wait_for_calls(sender_a, 1)
            await worker_b.run_once(now + 10)
            assert sender_b.calls == []
            assert env.outbox_one()["status"] == "sending"
        finally:
            gate.set()
            await asyncio.wait_for(task_a, timeout=20)
        assert env.outbox_one()["status"] == "sent"


async def test_notice_for_a_deleted_list_is_skipped_not_sent(tmp_path: Path) -> None:
    """Design 7, claim step 1: a row whose list was deleted is ``skipped`` (target_gone)."""
    async with _store_env(tmp_path) as env:
        await env.seed(5, ((GIFTER, 1),))
        await env.receive(1)

        async def delete(service: WishlistService) -> None:
            await service.delete_wishlist(env.wishlist_id, OWNER)

        await delete(WishlistService(env.store))
        sender = FakeNoticeSender()

        await env.worker(sender).run_once(_base())

        assert sender.calls == []
        row = env.outbox_one()
        assert (row["status"], row["skip_reason"]) == ("skipped", "target_gone")


async def test_text_has_no_quantities(tmp_path: Path) -> None:
    """R-6.3: the fixed template with the two titles and nothing else."""
    async with _store_env(tmp_path) as env:
        await env.seed(
            5, ((GIFTER, 2), (OTHER_GIFTER, 1)), title="Чайник", list_title="День рождения"
        )
        await env.receive(2)
        sender = FakeNoticeSender()

        await env.worker(sender).run_once(_base())

        expected = _TEXT.format(wish="Чайник", wishlist="День рождения")
        assert sorted(sender.calls) == sorted([(GIFTER_ID, expected), (OTHER_GIFTER_ID, expected)])
        assert re.search(r"\d", expected) is None
        assert {r["status"] for r in outbox_rows(env.db)} == {"sent"}


def test_token_never_logged_with_real_bot(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Design 7: a valid token starts the worker; the token is never logged; idle is silent."""
    caplog.set_level(logging.DEBUG)
    with app_env(tmp_path, bot_token=TEST_BOT_TOKEN, receipt_notice_poll_interval_seconds=0.05) as (
        _client,
        _sessions,
        app,
    ):
        task = getattr(app.state, "notice_task", None)
        assert task is not None, "the notice worker task does not exist yet"
        started = len(caplog.records)  # startup records stay in the token scan below
        time.sleep(0.4)
        assert not task.done()
    for record in caplog.records:
        assert TEST_BOT_TOKEN not in record.getMessage()
        assert TEST_BOT_TOKEN not in str(record.__dict__)
    idle = [
        r
        for r in caplog.records[started:]
        if str(getattr(r, "event", "")).startswith("receipt_notice_")
        and getattr(r, "event", "") != "receipt_notice_worker_stopped"
    ]
    assert idle == [], "an idle worker must write no record"


def test_no_token_no_worker_and_lifespan(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Design 7: no token, no worker and one INFO reason; an injected sender runs and stops."""
    caplog.set_level(logging.INFO)
    with app_env(tmp_path, "plain.db") as (_client, _sessions, app):
        assert getattr(app.state, "notice_task", None) is None
    disabled = [
        r for r in caplog.records if getattr(r, "event", "") == "receipt_notice_worker_disabled"
    ]
    assert len(disabled) == 1
    assert getattr(disabled[0], "reason", None), "the disabled record must carry a reason"

    assert "notice_sender" in inspect.signature(create_app).parameters, (
        "create_app does not accept notice_sender yet"
    )
    fake = FakeNoticeSender()
    with app_env(tmp_path, "fake.db", notice_sender=fake) as (_client, _sessions, app):
        task = app.state.notice_task
        assert not task.done()
    assert task.done()
    assert fake.closed is True


def _collect_route_paths(routes: Any) -> list[str]:
    paths: list[str] = []
    for route in routes:
        path = getattr(route, "path", None)
        if isinstance(path, str) and path:
            paths.append(path)
        nested = getattr(route, "routes", None)
        if nested is None and (orig := getattr(route, "original_router", None)) is not None:
            nested = getattr(orig, "routes", None)
        if nested:
            paths.extend(_collect_route_paths(nested))
    return paths


def test_settings_storage_only(tmp_path: Path) -> None:
    """Notification settings routes are limited to profile endpoints; writers stay scoped."""
    with app_env(tmp_path) as (_client, _sessions, app):
        db = str(app.state.settings.database_url).removeprefix("sqlite+aiosqlite:///")
        require_table(db, "user_notification_settings")
        require_table(db, "wl_list_notification_settings")
        paths = _collect_route_paths(app.routes)
    assert {p for p in paths if "notif" in p.lower()} == {
        "/api/profile/notifications/global",
        "/api/profile/notifications/wishlists/{wishlist_id}",
    }

    import wishenka

    root = Path(wishenka.__file__).parent
    writer = re.compile(
        r"(insert\s+(or\s+\w+\s+)?into|update|delete\s+from)\s+"
        r"(user_notification_settings|wl_list_notification_settings)",
        re.IGNORECASE,
    )
    offenders = [
        str(path.relative_to(root))
        for path in root.rglob("*.py")
        if "alembic" not in path.parts and writer.search(path.read_text(encoding="utf-8"))
    ]
    assert set(offenders) == {"bot/entry.py", "notices/preferences.py"}
