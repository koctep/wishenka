"""WISHENKA-29: real mutation, privacy, and private-bot entry regressions.

No network or real-time sleeps are used.  Generalized queue storage is discovered by its
persisted event kind rather than by prescribing a particular migration/table name.
"""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import sqlite3
import sys
import time
from importlib.machinery import ModuleSpec
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command
from aiogram.methods import SendMessage
from aiogram.types import Message, Update

from tests.notice_support import FakeNoticeSender, send_result
from tests.receipt_support import (
    GIFTER,
    GIFTER_ID,
    OTHER_GIFTER,
    OTHER_GIFTER_ID,
    OWNER,
    OWNER_ID,
    item_received,
    open_store,
    outbox_rows,
    sql_exec,
)
from tests.test_bot_capture_repro import _action, _setup
from tests.test_receipt_notices import _Env
from wishenka.bot.entry import create_router
from wishenka.users.store import UserStore
from wishenka.wishlists.service import WishlistService
from wishenka.wishlists.store import WishlistStore

pytestmark = pytest.mark.timeout(60)


def _notice_values(db: Path) -> list[str]:
    """Read values from notice/event tables, including future generalized queue tables."""
    with sqlite3.connect(db) as conn:
        names = [
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            if any(word in row[0].lower() for word in ("notice", "notification", "event"))
            and not row[0].startswith("sqlite_")
        ]
        values: list[str] = []
        for name in names:
            escaped = name.replace('"', '""')
            values.extend(str(row) for row in conn.execute(f'SELECT * FROM "{escaped}"'))
        return values


async def _run_reminder_scan(store: WishlistStore, settings: Any, now: int) -> None:
    """Invoke the scheduler if present; otherwise let delivery assertions expose absence.

    Only the exact missing module is treated as the unimplemented feature. Import errors,
    missing attributes, and runtime failures inside an existing module are not suppressed.
    """
    if importlib.util.find_spec("wishenka.notices.scheduler") is None:
        return
    from wishenka.notices.scheduler import ReminderScheduler

    await ReminderScheduler(store, settings).run_once(now)


async def test_scheduler_seam_invokes_present_implementation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A present scheduler is invoked with the live store, settings, and controlled time."""
    module = ModuleType("wishenka.notices.scheduler")
    module.__spec__ = ModuleSpec(module.__name__, loader=None)
    calls: list[tuple[Any, Any, int]] = []

    class ProbeScheduler:
        def __init__(self, store: WishlistStore, settings: Any) -> None:
            self.store = store
            self.settings = settings

        async def run_once(self, now: int) -> None:
            calls.append((self.store, self.settings, now))

    module.ReminderScheduler = ProbeScheduler  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, module.__name__, module)
    async with open_store(tmp_path / "scheduler-seam.db") as store:
        settings = _Env(store, tmp_path / "scheduler-seam.db").settings
        await _run_reminder_scan(store, settings, 123456)
        assert calls == [(store, settings, 123456)]


async def _list_with_member(store: WishlistStore) -> int:
    async def setup(service: WishlistService) -> int:
        wishlist = await service.create_wishlist(owner=OWNER, title="Friends")
        await service.add_member(wishlist.id, OWNER, GIFTER_ID)
        return wishlist.id

    return await store.execute(setup)


async def test_wish_creation_produces_durable_work_across_store_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A real, committed shared-list write must leave durable notification work."""
    db = tmp_path / "events.db"
    async with open_store(db) as store:
        wishlist_id = await _list_with_member(store)
        await _verify_start(monkeypatch, db, GIFTER_ID)

        async def add(service: WishlistService) -> Any:
            return await service.add_wish_item(wishlist_id, OWNER, title="Unique new wish")

        item = await store.execute(add)

    async with open_store(db) as restarted:
        sender = FakeNoticeSender()
        await _Env(restarted, db).worker(sender).run_once(int(time.time()) + 10)
        assert len(sender.calls) == 1, "The committed mutation must leave one durable delivery"
        chat, message = sender.calls[0]
        assert chat == GIFTER_ID
        assert "Unique new wish" in message and "Friends" in message
        assert item.id > 0


async def test_rolled_back_write_does_not_create_notification_work(tmp_path: Path) -> None:
    """A transaction that fails must not publish its associated notification."""
    db = tmp_path / "rollback.db"
    async with open_store(db) as store:
        wishlist_id = await _list_with_member(store)
        before = _notice_values(db)

        async def fail(service: WishlistService) -> None:
            await service.add_wish_item(wishlist_id, OWNER, title="Never committed")
            raise RuntimeError("deliberate rollback")

        with pytest.raises(RuntimeError, match="deliberate rollback"):
            await store.execute(fail)
        assert _notice_values(db) == before


async def test_changed_preference_is_rechecked_before_receipt_send(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Opting out after enqueue prevents delivery, without undoing the receipt."""
    db = tmp_path / "preferences.db"
    async with open_store(db) as store:
        env = _Env(store, db)
        await env.seed(2, ((GIFTER, 1),))
        await _verify_start(monkeypatch, db, GIFTER_ID)
        await env.receive(1)
        sql_exec(
            db,
            "INSERT OR REPLACE INTO user_notification_settings VALUES (?, 'gift_received', 0, ?)",
            (GIFTER_ID, "2024-01-01T00:00:00+00:00"),
        )
        sender = FakeNoticeSender()
        await env.worker(sender).run_once(int(time.time()) + 10)
        assert sender.calls == [], "Current opt-out must suppress an already queued receipt"
        assert item_received(db, env.item_id) == 1


async def test_uncertain_receipt_delivery_is_not_automatically_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A timeout may mean Telegram accepted the message; do not automatically resend it."""
    db = tmp_path / "uncertain.db"
    async with open_store(db) as store:
        env = _Env(store, db)
        await env.seed(2, ((GIFTER, 1),))
        await _verify_start(monkeypatch, db, GIFTER_ID)
        await env.receive(1)
        sender = FakeNoticeSender([send_result("ambiguous")])
        now = int(time.time()) + 10
        worker = env.worker(sender)
        await worker.run_once(now)
        await worker.run_once(now + 100_000)
        assert len(sender.calls) == 1, "An ambiguous attempt must await operator resolution"


async def _private_command(
    monkeypatch: pytest.MonkeyPatch, command: str, router: Router, user_id: int = 101
) -> list[SendMessage]:
    """Feed a private command through a dispatcher and capture actual bot API calls."""
    sent: list[Any] = []

    async def transport(_bot: Bot, method: Any, request_timeout: float | None = None) -> bool:
        sent.append(method)
        return True

    monkeypatch.setattr(Bot, "__call__", transport)
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    update = Update.model_validate(
        {
            "update_id": 1,
            "message": {
                "message_id": 1,
                "date": 1700000000,
                "chat": {"id": user_id, "type": "private"},
                "from": {"id": user_id, "is_bot": False, "first_name": "Test"},
                "text": command,
                "entities": [{"type": "bot_command", "offset": 0, "length": len(command)}],
            },
        }
    )
    bot = Bot("123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")
    try:
        await dispatcher.feed_update(bot, update)
    finally:
        await bot.session.close()
    return [method for method in sent if isinstance(method, SendMessage)]


async def test_fake_dispatcher_captures_birthday_command(monkeypatch: pytest.MonkeyPatch) -> None:
    router = Router()

    @router.message(Command("birthdays"))
    async def echo(message: Message) -> None:
        await message.answer("transport works")

    messages = await _private_command(monkeypatch, "/birthdays", router)
    assert [message.text for message in messages] == ["transport works"]


async def test_private_birthday_management_is_discoverable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A user can initiate the birthday flow without a fabricated profile birthday."""
    db = tmp_path / "birthdays.db"
    async with open_store(db) as store:
        users = UserStore(f"sqlite+aiosqlite:///{db}")
        await users.initialize()
        try:
            deps = SimpleNamespace(
                mini_app_url="https://example.test/miniapp",
                wishlist_store=store,
                user_store=users,
            )
            messages = await _private_command(monkeypatch, "/birthdays", create_router(deps))
            assert messages, "The bot must answer /birthdays with private birthday management"
            assert messages[-1].reply_markup is not None
        finally:
            await users.engine.dispose()


async def _verify_start(monkeypatch: pytest.MonkeyPatch, db: Path, user_id: int) -> None:
    """A private /start supplies the explicit delivery proof required by the design."""
    users = UserStore(f"sqlite+aiosqlite:///{db}")
    await users.initialize()
    try:
        deps = SimpleNamespace(mini_app_url="https://example.test/miniapp", user_store=users)
        messages = await _private_command(monkeypatch, "/start", create_router(deps), user_id)
        assert messages
    finally:
        await users.engine.dispose()


async def test_unstarted_bot_does_not_receive_receipt(tmp_path: Path) -> None:
    """A Telegram profile alone is not proof the user can receive bot messages."""
    db = tmp_path / "no-start.db"
    async with open_store(db) as store:
        env = _Env(store, db)
        await env.seed(2, ((GIFTER, 1),))
        await env.receive(1)
        sender = FakeNoticeSender()
        await env.worker(sender).run_once(int(time.time()) + 10)
        assert sender.calls == []
        assert item_received(db, env.item_id) == 1


async def test_list_override_is_rechecked_after_receipt_was_queued(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The more specific post-enqueue list choice overrides the global setting."""
    db = tmp_path / "override.db"
    async with open_store(db) as store:
        env = _Env(store, db)
        await env.seed(2, ((GIFTER, 1),))
        await _verify_start(monkeypatch, db, GIFTER_ID)
        await env.receive(1)
        env.settings_user(GIFTER_ID, True)
        env.settings_list(GIFTER_ID, False)
        sender = FakeNoticeSender()
        await env.worker(sender).run_once(int(time.time()) + 10)
        assert sender.calls == []
        assert item_received(db, env.item_id) == 1


async def test_rate_limit_does_not_undo_receipt_and_respects_retry_after(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A definite 429 retry remains delayed for the provider's requested period."""
    db = tmp_path / "retry-after.db"
    async with open_store(db) as store:
        env = _Env(store, db)
        await env.seed(2, ((GIFTER, 1),))
        await _verify_start(monkeypatch, db, GIFTER_ID)
        await env.receive(1)
        sender = FakeNoticeSender([send_result("retryable", retry_after=120)])
        worker = env.worker(sender)
        now = int(time.time()) + 10
        await worker.run_once(now)
        await worker.run_once(now + 119)
        assert len(sender.calls) == 1
        assert item_received(db, env.item_id) == 1
        await worker.run_once(now + 121)
        assert len(sender.calls) == 2


async def test_revoked_access_suppresses_pending_shared_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "revoked.db"
    async with open_store(db) as store:
        wishlist_id = await _list_with_member(store)
        await _verify_start(monkeypatch, db, GIFTER_ID)
        await _verify_start(monkeypatch, db, OTHER_GIFTER_ID)

        async def add_second_member(service: WishlistService) -> None:
            await service.add_member(wishlist_id, OWNER, OTHER_GIFTER_ID)

        await store.execute(add_second_member)

        async def add(service: WishlistService) -> None:
            await service.add_wish_item(wishlist_id, OWNER, title="Private surprise")

        await store.execute(add)

        async def revoke(service: WishlistService) -> None:
            await service.remove_member(wishlist_id, OWNER, GIFTER_ID)

        await store.execute(revoke)
        sender = FakeNoticeSender()
        worker = _Env(store, db).worker(sender)
        now = int(time.time()) + 10
        for offset in range(10):
            await worker.run_once(now + offset * 2)
        assert all(chat != GIFTER_ID for chat, _ in sender.calls)
        assert any(
            chat == OTHER_GIFTER_ID and "Private surprise" in text for chat, text in sender.calls
        ), "An eligible collaborator must still receive the shared change"


async def test_stale_receipt_claim_is_uncertain_and_never_resent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "stale.db"
    async with open_store(db) as store:
        env = _Env(store, db)
        await env.seed(2, ((GIFTER, 1),))
        await _verify_start(monkeypatch, db, GIFTER_ID)
        await env.receive(1)
        now = int(time.time()) + 1000
        sql_exec(
            db,
            "UPDATE notification_outbox SET status='sending', claimed_at=?, attempts=1",
            (now - env.settings.receipt_notice_claim_lease_seconds - 1,),
        )
        sender = FakeNoticeSender()
        worker = env.worker(sender)
        await worker.run_once(now)
        await worker.run_once(now + 100_000)
        assert sender.calls == [], "A stale sending lease is uncertain and must not be resent"
        assert outbox_rows(db)[0]["status"] == "uncertain"


async def test_concurrent_workers_do_not_send_same_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "claims.db"
    async with open_store(db) as store:
        env = _Env(store, db)
        await env.seed(2, ((GIFTER, 1),))
        await _verify_start(monkeypatch, db, GIFTER_ID)
        await env.receive(1)
        gate = asyncio.Event()
        entered = asyncio.Event()

        class SignallingSender(FakeNoticeSender):
            async def send(self, chat_id: int, text: str) -> Any:
                entered.set()
                return await super().send(chat_id, text)

        sender = SignallingSender(block_first=gate)
        now = int(time.time()) + 10
        first = asyncio.create_task(env.worker(sender).run_once(now))
        try:
            await asyncio.wait_for(entered.wait(), timeout=10)
            assert len(sender.calls) == 1, "First worker did not claim and start delivery"
            await env.worker(sender).run_once(now + 1)
            assert len(sender.calls) == 1
        finally:
            gate.set()
            await asyncio.wait_for(first, timeout=10)
        assert outbox_rows(db)[0]["status"] == "sent"


async def test_permanent_rejection_does_not_block_another_recipient(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "rejected.db"
    async with open_store(db) as store:
        env = _Env(store, db)
        await env.seed(3, ((GIFTER, 1), (OTHER_GIFTER, 1)))
        await _verify_start(monkeypatch, db, GIFTER_ID)
        await _verify_start(monkeypatch, db, OTHER_GIFTER_ID)
        await env.receive(1)
        sender = FakeNoticeSender([send_result("rejected"), send_result("delivered")])
        worker = env.worker(sender)
        now = int(time.time()) + 10
        await worker.run_once(now)
        await worker.run_once(now + 2)
        assert {chat for chat, _ in sender.calls} == {GIFTER_ID, OTHER_GIFTER_ID}
        assert {row["status"] for row in outbox_rows(db)} == {"failed", "sent"}


async def test_recipient_receives_no_receipt_even_if_also_a_giver(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    db = tmp_path / "overlap.db"
    async with open_store(db) as store:
        env = _Env(store, db)
        await env.seed(3, ((GIFTER, 1),))
        await _verify_start(monkeypatch, db, OWNER_ID)
        await _verify_start(monkeypatch, db, GIFTER_ID)
        sql_exec(
            db,
            "INSERT INTO wl_reservations (id, wish_item_id, user_id, quantity, status, "
            "created_at, updated_at) VALUES (900, ?, ?, 1, 'active', ?, ?)",
            (env.item_id, OWNER_ID, "2024-01-01", "2024-01-01"),
        )
        with caplog.at_level(logging.DEBUG):
            await env.receive(1)
            sender = FakeNoticeSender()
            await env.worker(sender).run_once(int(time.time()) + 10)
        assert [chat for chat, _ in sender.calls] == [GIFTER_ID]
        assert all(
            str(OWNER_ID) not in record.getMessage()
            for record in caplog.records
            if record.name.startswith("wishenka.wishlists.notices")
        )


async def _enter_birthday(harness: Any, *, user: int = OWNER_ID) -> None:
    """Enter a private birthday using the bot's visible add flow."""
    before = len(harness.sent)
    await harness.text("/birthdays", user=user)
    assert any(isinstance(method, SendMessage) for method in harness.sent[before:]), (
        "The birthday command must produce a fresh private response"
    )
    await harness.callback(_action(harness.last_message(), ("add", "добав")), user=user)
    await harness.text("Friend", user=user)
    await harness.text("03-08", user=user)


async def test_private_birthday_management_create_edit_cancel_and_delete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness, store, users, _, _ = await _setup(tmp_path, monkeypatch)
    try:
        await _enter_birthday(harness)
        await harness.text("/birthdays")
        listing = harness.last_message()
        assert "Friend" in listing.text
        await harness.callback(_action(listing, ("edit", "измен")))
        await harness.text("Changed friend")
        await harness.text("03-09")
        await harness.text("/birthdays")
        changed = harness.last_message()
        assert "Changed friend" in changed.text
        await harness.callback(_action(changed, ("edit", "измен")))
        await harness.text("/cancel")
        await harness.text("/birthdays")
        assert "Changed friend" in harness.last_message().text
        await harness.callback(_action(harness.last_message(), ("delete", "удал")))
        await harness.text("/birthdays")
        assert "Changed friend" not in harness.last_message().text
    finally:
        await harness.bot.session.close()
        await users.engine.dispose()
        await store.engine.dispose()


async def test_birthday_entries_are_private_and_invalid_dates_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness, store, users, _, _ = await _setup(tmp_path, monkeypatch)
    try:
        await _enter_birthday(harness)
        await harness.text("/birthdays", user=GIFTER_ID)
        assert "Friend" not in harness.last_message().text
        await harness.text("/birthdays")
        listing = harness.last_message()
        await harness.callback(_action(listing, ("add", "добав")))
        await harness.text("Invalid date")
        await harness.text("02-30")
        await harness.text("/cancel")
        await harness.text("/birthdays")
        assert "Invalid date" not in harness.last_message().text
        assert "Friend" in harness.last_message().text
    finally:
        await harness.bot.session.close()
        await users.engine.dispose()
        await store.engine.dispose()


async def test_entered_birthday_schedules_once_and_delivers_only_to_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The scheduled occurrence survives a repeated scan and targets the private owner."""
    from datetime import UTC, datetime

    harness, store, users, _, _ = await _setup(tmp_path, monkeypatch)
    try:
        await _enter_birthday(harness)
        settings = _Env(store, tmp_path / "capture.db").settings
        # Seven calendar days before the supplied March 8 date.
        now = int(datetime(2030, 3, 1, tzinfo=UTC).timestamp())
        await _run_reminder_scan(store, settings, now)
        await _run_reminder_scan(store, settings, now)
        sender = FakeNoticeSender()
        worker = _Env(store, tmp_path / "capture.db").worker(sender)
        await worker.run_once(now)
        await worker.run_once(now + 2)
        assert len(sender.calls) == 1
        assert sender.calls[0][0] == OWNER_ID
        assert "Friend" in sender.calls[0][1]
    finally:
        await harness.bot.session.close()
        await users.engine.dispose()
        await store.engine.dispose()


async def test_changed_or_deleted_birthday_invalidates_queued_occurrence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import UTC, datetime

    harness, store, users, _, _ = await _setup(tmp_path, monkeypatch)
    try:
        await _enter_birthday(harness)
        db = tmp_path / "capture.db"
        env = _Env(store, db)
        now = int(datetime(2030, 3, 1, tzinfo=UTC).timestamp())
        await _run_reminder_scan(store, env.settings, now)
        await harness.text("/birthdays")
        await harness.callback(_action(harness.last_message(), ("delete", "удал")))
        sender = FakeNoticeSender()
        await env.worker(sender).run_once(now)
        assert sender.calls == [], "Deleted birthday must invalidate its pending occurrence"
    finally:
        await harness.bot.session.close()
        await users.engine.dispose()
        await store.engine.dispose()


async def test_leap_day_birthday_schedules_february_28_in_non_leap_year(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import UTC, datetime

    harness, store, users, _, _ = await _setup(tmp_path, monkeypatch)
    try:
        await harness.text("/birthdays")
        await harness.callback(_action(harness.last_message(), ("add", "добав")))
        await harness.text("Leap friend")
        await harness.text("02-29")
        db = tmp_path / "capture.db"
        env = _Env(store, db)
        now = int(datetime(2031, 2, 21, tzinfo=UTC).timestamp())
        await _run_reminder_scan(store, env.settings, now)
        sender = FakeNoticeSender()
        await env.worker(sender).run_once(now)
        assert len(sender.calls) == 1
        assert sender.calls[0][0] == OWNER_ID
        assert "Leap friend" in sender.calls[0][1]
    finally:
        await harness.bot.session.close()
        await users.engine.dispose()
        await store.engine.dispose()


async def test_recipient_giver_overlap_still_receives_safe_list_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Role overlap must not suppress notifications unrelated to a reservation."""
    from wishenka.wishlists.models import WishlistRole

    db = tmp_path / "safe-overlap.db"
    async with open_store(db) as store:
        env = _Env(store, db)
        await env.seed(3, ((GIFTER, 1),))
        await _verify_start(monkeypatch, db, OWNER_ID)

        async def promote(service: WishlistService) -> None:
            await service.add_member(env.wishlist_id, OWNER, GIFTER_ID, WishlistRole.ADMIN)

        await store.execute(promote)
        sql_exec(
            db,
            "INSERT INTO wl_reservations (id, wish_item_id, user_id, quantity, status, "
            "created_at, updated_at) VALUES (900, ?, ?, 1, 'active', ?, ?)",
            (env.item_id, OWNER_ID, "2024-01-01", "2024-01-01"),
        )

        async def create(service: WishlistService) -> None:
            await service.add_wish_item(env.wishlist_id, GIFTER, title="Independent list change")

        await store.execute(create)
        sender = FakeNoticeSender()
        worker = env.worker(sender)
        now = int(time.time()) + 10
        for offset in range(10):
            await worker.run_once(now + 2 * offset)
        messages = [text for chat, text in sender.calls if chat == OWNER_ID]
        assert any("Independent list change" in text for text in messages)
        assert all("reservation" not in text.casefold() for text in messages)


async def test_dated_list_reminder_survives_scheduler_restart_and_utc_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A seven-day occurrence is scheduled once, including across midnight and restart."""
    from datetime import UTC, datetime

    db = tmp_path / "dated-restart.db"
    event_date = datetime(2030, 3, 8, 12, tzinfo=UTC)
    async with open_store(db) as store:

        async def create(service: WishlistService) -> None:
            await service.create_wishlist(
                owner=OWNER, title="Spring occasion", event_date=event_date
            )

        await store.execute(create)
        await _verify_start(monkeypatch, db, OWNER_ID)
        env = _Env(store, db)
        before = int(datetime(2030, 2, 28, 23, 59, tzinfo=UTC).timestamp())
        await _run_reminder_scan(store, env.settings, before)
        sender = FakeNoticeSender()
        await env.worker(sender).run_once(before)
        assert sender.calls == [], "The reminder must not precede its seven-day UTC window"

    async with open_store(db) as store:
        env = _Env(store, db)
        midnight = int(datetime(2030, 3, 1, tzinfo=UTC).timestamp())
        await _run_reminder_scan(store, env.settings, midnight)
        await _run_reminder_scan(store, env.settings, midnight + 3600)
        sender = FakeNoticeSender()
        worker = env.worker(sender)
        await worker.run_once(midnight + 3600)
        await worker.run_once(midnight + 7200)
        reminders = [text for user, text in sender.calls if user == OWNER_ID]
        assert len(reminders) == 1
        assert "Spring occasion" in reminders[0]


async def test_changed_event_date_invalidates_old_pending_reminder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import UTC, datetime

    db = tmp_path / "date-changed.db"
    async with open_store(db) as store:

        async def create(service: WishlistService) -> int:
            wl = await service.create_wishlist(
                owner=OWNER, title="Changed date", event_date=datetime(2030, 3, 8, tzinfo=UTC)
            )
            await service.create_wishlist(
                owner=OWNER, title="Control occasion", event_date=datetime(2030, 3, 8, tzinfo=UTC)
            )
            return wl.id

        list_id = await store.execute(create)
        await _verify_start(monkeypatch, db, OWNER_ID)
        env = _Env(store, db)
        now = int(datetime(2030, 3, 1, tzinfo=UTC).timestamp())
        await _run_reminder_scan(store, env.settings, now)

        async def change(service: WishlistService) -> None:
            await service.update_wishlist_settings(
                list_id, OWNER, event_date=datetime(2030, 4, 8, tzinfo=UTC)
            )

        await store.execute(change)
        sender = FakeNoticeSender()
        await env.worker(sender).run_once(now + 2)
        assert any("Control occasion" in message for _, message in sender.calls), (
            "The unchanged eligible occasion must produce a reminder"
        )
        assert not any("Changed date" in message for _, message in sender.calls)


async def test_no_birthday_entry_produces_no_birthday_reminder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import UTC, datetime

    db = tmp_path / "no-birthday.db"
    async with open_store(db) as store:

        async def create(service: WishlistService) -> None:
            await service.create_wishlist(
                owner=OWNER, title="Control occasion", event_date=datetime(2030, 3, 8, tzinfo=UTC)
            )

        await store.execute(create)
        await _verify_start(monkeypatch, db, OWNER_ID)
        env = _Env(store, db)
        now = int(datetime(2030, 3, 1, tzinfo=UTC).timestamp())
        await _run_reminder_scan(store, env.settings, now)
        sender = FakeNoticeSender()
        worker = env.worker(sender)
        for offset in range(4):
            await worker.run_once(now + offset * 2)
        assert len(sender.calls) == 1, "Only the known eligible occasion should produce a reminder"
        assert "Control occasion" in sender.calls[0][1]


async def test_recipient_who_is_also_giver_receives_neutral_event_reminder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import UTC, datetime

    db = tmp_path / "neutral-overlap.db"
    async with open_store(db) as store:
        env = _Env(store, db)
        await env.seed(3, ((GIFTER, 1),))
        await _verify_start(monkeypatch, db, OWNER_ID)
        sql_exec(
            db,
            "INSERT INTO wl_reservations (id, wish_item_id, user_id, quantity, status, "
            "created_at, updated_at) VALUES (900, ?, ?, 1, 'active', ?, ?)",
            (env.item_id, OWNER_ID, "2024-01-01", "2024-01-01"),
        )

        async def set_date(service: WishlistService) -> None:
            await service.update_wishlist_settings(
                env.wishlist_id, OWNER, event_date=datetime(2030, 3, 8, tzinfo=UTC)
            )

        await store.execute(set_date)
        now = int(datetime(2030, 3, 1, tzinfo=UTC).timestamp())
        await _run_reminder_scan(store, env.settings, now)
        sender = FakeNoticeSender()
        await env.worker(sender).run_once(now)
        texts = [message for user, message in sender.calls if user == OWNER_ID]
        assert len(texts) == 1, "Neutral reminder must remain eligible under overlapping roles"
        assert "Alice Birthday" in texts[0]
        assert not any(word in texts[0].casefold() for word in ("reservation", "брон"))


@pytest.mark.parametrize(
    ("language", "expected"),
    [("en-US", "received"), ("ru-RU", "получ"), ("fr", "получ")],
)
async def test_receipt_uses_language_and_safe_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, language: str, expected: str
) -> None:
    db = tmp_path / "language.db"
    async with open_store(db) as store:
        env = _Env(store, db)
        await env.seed(2, ((GIFTER, 1),), title="Safe item", list_title="Safe list")
        await _verify_start(monkeypatch, db, GIFTER_ID)
        sql_exec(
            db, "UPDATE users SET language_code = ? WHERE telegram_id = ?", (language, GIFTER_ID)
        )
        await env.receive(1)
        sender = FakeNoticeSender()
        await env.worker(sender).run_once(int(time.time()) + 10)
        assert len(sender.calls) == 1
        assert expected in sender.calls[0][1].casefold()


async def test_receipt_notice_text_links_and_logs_do_not_leak_private_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    db = tmp_path / "privacy.db"
    async with open_store(db) as store:
        env = _Env(store, db)
        await env.seed(3, ((GIFTER, 1), (OTHER_GIFTER, 1)), title="Tea", list_title="Party")
        await _verify_start(monkeypatch, db, GIFTER_ID)
        await _verify_start(monkeypatch, db, OTHER_GIFTER_ID)
        async with store.engine.connect() as conn:
            from sqlalchemy import text

            result = await conn.execute(
                text("SELECT public_token, invite_token FROM wl_lists WHERE id = :id"),
                {"id": env.wishlist_id},
            )
            tokens = tuple(value for value in result.one() if value)
        with caplog.at_level(logging.DEBUG):
            await env.receive(1)
            sender = FakeNoticeSender()
            await env.worker(sender).run_once(int(time.time()) + 10)
        assert {user for user, _ in sender.calls} == {GIFTER_ID, OTHER_GIFTER_ID}
        for user, message in sender.calls:
            assert "Tea" in message and "Party" in message
            assert not any(token in message for token in tokens)
            assert str(OTHER_GIFTER_ID if user == GIFTER_ID else GIFTER_ID) not in message
            assert "quantity" not in message.casefold()
        logs = "\n".join(record.getMessage() for record in caplog.records)
        assert not any(token in logs for token in tokens)
        assert "Tea" not in logs and "Party" not in logs


async def test_one_receipt_produces_one_notice_per_giver_despite_multiple_reservations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "receipt-dedupe.db"
    async with open_store(db) as store:
        env = _Env(store, db)
        await env.seed(5, ((GIFTER, 1), (GIFTER, 1), (OTHER_GIFTER, 1)))
        await _verify_start(monkeypatch, db, GIFTER_ID)
        await _verify_start(monkeypatch, db, OTHER_GIFTER_ID)
        await env.receive(1)
        rows = outbox_rows(db)
        assert len(rows) == 2
        assert {row["giver_user_id"] for row in rows} == {GIFTER_ID, OTHER_GIFTER_ID}
        assert len({row["receipt_id"] for row in rows}) == 1
        sender = FakeNoticeSender()
        worker = env.worker(sender)
        now = int(time.time()) + 10
        await worker.run_once(now)
        await worker.run_once(now + 2)
        assert sorted(user for user, _ in sender.calls) == [GIFTER_ID, OTHER_GIFTER_ID]
