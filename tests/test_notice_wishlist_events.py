"""Transaction, privacy and throughput behavior of wishlist notifications."""

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from tests.notice_support import FakeNoticeSender
from tests.receipt_support import GIFTER_ID, OWNER, open_store, seed_users
from tests.test_notice_delivery_repro import _list_with_member, _verify_start
from tests.test_receipt_notices import _Env
from wishenka.notices.rate import reserve_permit
from wishenka.wishlists.service import WishlistService

pytestmark = pytest.mark.timeout(60)


async def test_shared_item_change_and_archive_are_transactional_and_deliverable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "events.db"
    async with open_store(db) as store:
        wishlist = await _list_with_member(store)
        await _verify_start(monkeypatch, db, GIFTER_ID)

        async def create(service: WishlistService) -> int:
            return (await service.add_wish_item(wishlist, OWNER, title="Original")).id

        item = await store.execute(create)
        sender = FakeNoticeSender()
        worker = _Env(store, db).worker(sender)
        import time

        now = int(time.time()) + 10
        await worker.run_once(now)
        assert len(sender.calls) == 1 and "Original" in sender.calls[0][1]

        async def change(service: WishlistService) -> None:
            await service.update_wish_item(item, OWNER, title="Updated")

        await store.execute_wish(change, item_id=item)
        await worker.run_once(now + 1)
        assert len(sender.calls) == 2 and "Updated" in sender.calls[1][1]

        await store.execute_wish(change, item_id=item)
        await worker.run_once(now + 2)
        assert len(sender.calls) == 2, "An unchanged item must not produce another event"

        async def archive(service: WishlistService) -> None:
            await service.archive_wish_item(wishlist, item, OWNER)

        await store.execute(archive)
        await worker.run_once(now + 3)
        assert len(sender.calls) == 3 and "Updated" in sender.calls[2][1]
        assert all(chat == GIFTER_ID for chat, _ in sender.calls)


async def test_persistent_rate_reservations_are_shared_across_transactions(tmp_path: Path) -> None:
    async with open_store(tmp_path / "rates.db") as store:

        async def reserve(chat: int, now: int) -> bool:
            async def work(conn: AsyncConnection) -> bool:
                return await reserve_permit(conn, chat, now, 2, 1)

            return await store.transaction(work)

        assert await reserve(101, 10)
        assert not await reserve(101, 10)
        assert await reserve(202, 10)
        assert not await reserve(303, 10)
        assert await reserve(303, 11)


async def test_membership_and_list_archive_deliver_only_to_authorized_participants(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import time

    db = tmp_path / "membership.db"
    async with open_store(db) as store:
        seed_users(db, GIFTER_ID)

        async def create(service: WishlistService) -> int:
            return (await service.create_wishlist(owner=OWNER, title="Shared event")).id

        wishlist = await store.execute(create)
        await _verify_start(monkeypatch, db, GIFTER_ID)

        async def add(service: WishlistService) -> None:
            await service.add_member(wishlist, OWNER, GIFTER_ID)

        await store.execute(add)
        sender = FakeNoticeSender()
        worker = _Env(store, db).worker(sender)
        now = int(time.time()) + 10
        await worker.run_once(now)
        assert len(sender.calls) == 1 and sender.calls[0][0] == GIFTER_ID
        assert "Shared event" in sender.calls[0][1]

        async def archive(service: WishlistService) -> None:
            await service.archive_wishlist(wishlist, OWNER)

        await store.execute(archive)
        await worker.run_once(now + 1)
        assert len(sender.calls) == 2 and "Shared event" in sender.calls[1][1]


async def test_later_reservation_in_same_transaction_is_not_event_time_audience(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import time

    from tests.receipt_support import GIFTER

    db = tmp_path / "audience.db"
    async with open_store(db) as store:
        await _verify_start(monkeypatch, db, GIFTER_ID)

        async def setup(service: WishlistService) -> None:
            wl = await service.create_wishlist(owner=OWNER, title="Private event")
            item = await service.add_wish_item(wl.id, OWNER, title="Before reservation")
            await service.create_reservation(item.id, GIFTER, 1)

        await store.execute(setup)
        sender = FakeNoticeSender()
        await _Env(store, db).worker(sender).run_once(int(time.time()) + 10)
        assert sender.calls == []


async def test_provider_throttle_is_shared_with_other_worker(tmp_path: Path) -> None:
    import time

    from tests.notice_support import send_result
    from tests.receipt_support import GIFTER, OTHER_GIFTER

    db = tmp_path / "throttle.db"
    async with open_store(db) as store:
        env = _Env(store, db, verify_destinations=True)
        await env.seed(3, ((GIFTER, 1), (OTHER_GIFTER, 1)))
        await env.receive(1)
        now = int(time.time()) + 10
        first = FakeNoticeSender([send_result("retryable", retry_after=120.5)])
        await env.worker(first).run_once(now)
        assert len(first.calls) == 1
        second = FakeNoticeSender()
        worker = env.worker(second)
        await worker.run_once(now + 120)
        assert second.calls == []
        await worker.run_once(now + 121)
        assert len(second.calls) == 2


async def test_event_datetime_is_interpreted_as_utc_calendar_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import UTC, datetime, timedelta, timezone

    from tests.receipt_support import OWNER_ID
    from tests.test_notice_delivery_repro import _run_reminder_scan

    db = tmp_path / "utc.db"
    async with open_store(db) as store:

        async def create(service: WishlistService) -> None:
            await service.create_wishlist(
                owner=OWNER,
                title="UTC occasion",
                event_date=datetime(2030, 3, 8, 1, tzinfo=timezone(timedelta(hours=3))),
            )

        await store.execute(create)
        await _verify_start(monkeypatch, db, OWNER_ID)
        env = _Env(store, db)
        now = int(datetime(2030, 2, 28, tzinfo=UTC).timestamp())
        await _run_reminder_scan(store, env.settings, now)
        sender = FakeNoticeSender()
        await env.worker(sender).run_once(now)
        assert len(sender.calls) == 1 and "2030-03-07" in sender.calls[0][1]


async def test_private_bot_user_creation_does_not_log_identifier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    import logging

    db = tmp_path / "private-start.db"
    async with open_store(db):
        with caplog.at_level(logging.INFO):
            await _verify_start(monkeypatch, db, GIFTER_ID)
        messages = "\n".join(record.getMessage() for record in caplog.records)
        assert str(GIFTER_ID) not in messages


async def test_invitation_acceptance_notifies_existing_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import time

    from tests.receipt_support import GIFTER, OWNER_ID

    db = tmp_path / "invite-event.db"
    async with open_store(db) as store:
        seed_users(db, GIFTER_ID)

        async def create(service: WishlistService) -> str:
            return (await service.create_wishlist(owner=OWNER, title="Invite event")).invite_token

        token = await store.execute(create)
        await _verify_start(monkeypatch, db, OWNER_ID)

        async def join(service: WishlistService) -> None:
            await service.join_by_invite(token, GIFTER)

        await store.execute(join)
        sender = FakeNoticeSender()
        await _Env(store, db).worker(sender).run_once(int(time.time()) + 10)
        assert len(sender.calls) == 1
        assert sender.calls[0][0] == OWNER_ID and "Invite event" in sender.calls[0][1]
        assert token not in sender.calls[0][1]


async def test_favorite_tracking_reminder_respects_current_favorite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import UTC, datetime

    from tests.receipt_support import GIFTER
    from tests.test_notice_delivery_repro import _run_reminder_scan

    db = tmp_path / "favorite.db"
    async with open_store(db) as store:
        seed_users(db, GIFTER_ID)

        async def setup(service: WishlistService) -> tuple[int, int]:
            wl = await service.create_wishlist(
                owner=OWNER, title="Favorite occasion", event_date=datetime(2030, 3, 8, tzinfo=UTC)
            )
            await service.add_favorite(GIFTER, wl.id)
            revoked = await service.create_wishlist(
                owner=OWNER, title="Revoked occasion", event_date=datetime(2030, 3, 8, tzinfo=UTC)
            )
            await service.add_favorite(GIFTER, revoked.id)
            return wl.id, revoked.id

        wishlist, revoked = await store.execute(setup)
        await _verify_start(monkeypatch, db, GIFTER_ID)
        now = int(datetime(2030, 3, 1, tzinfo=UTC).timestamp())
        env = _Env(store, db)
        await _run_reminder_scan(store, env.settings, now)

        async def revoke(service: WishlistService) -> None:
            await service.remove_favorite(GIFTER, revoked)

        await store.execute(revoke)
        sender = FakeNoticeSender()
        await env.worker(sender).run_once(now)
        assert len(sender.calls) == 1 and sender.calls[0][0] == GIFTER_ID
        assert "Favorite occasion" in sender.calls[0][1]

        async def remove(service: WishlistService) -> None:
            await service.remove_favorite(GIFTER, wishlist)

        await store.execute(remove)
        await _run_reminder_scan(store, env.settings, now + 1)
        await env.worker(sender).run_once(now + 1)
        assert len(sender.calls) == 1


async def test_receipt_is_not_sent_after_member_access_revoked(tmp_path: Path) -> None:
    import time

    from tests.receipt_support import GIFTER

    db = tmp_path / "receipt-revoked.db"
    async with open_store(db) as store:
        seed_users(db, GIFTER_ID)
        env = _Env(store, db, verify_destinations=True)
        await env.seed(3, ((GIFTER, 1),))

        async def add(service: WishlistService) -> None:
            await service.add_member(env.wishlist_id, OWNER, GIFTER_ID)

        await store.execute(add)
        await env.receive(1)

        async def remove(service: WishlistService) -> None:
            await service.remove_member(env.wishlist_id, OWNER, GIFTER_ID)

        await store.execute(remove)
        sender = FakeNoticeSender()
        await env.worker(sender).run_once(int(time.time()) + 10)
        assert sender.calls == []
        assert env.outbox_one()["status"] == "skipped"


async def test_other_giver_reservation_activity_does_not_generate_notices(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No other giver or recipient learns of actions through notification timing."""
    import sqlite3
    import time

    from tests.receipt_support import GIFTER, OTHER_GIFTER, OTHER_GIFTER_ID, OWNER_ID

    db = tmp_path / "reservation-events.db"
    async with open_store(db) as store:
        seed_users(db, GIFTER_ID)
        for user_id in (GIFTER_ID, OTHER_GIFTER_ID, OWNER_ID):
            await _verify_start(monkeypatch, db, user_id)

        async def setup(service: WishlistService) -> tuple[int, int]:
            wl = await service.create_wishlist(owner=OWNER, title="Private")
            await service.add_member(wl.id, OWNER, GIFTER_ID)
            item = await service.add_wish_item(wl.id, OWNER, title="Gift", quantity=4)
            first = await service.create_reservation(item.id, GIFTER, 1)
            return item.id, first.id

        item, first = await store.execute(setup)
        with sqlite3.connect(db) as conn:
            conn.execute("DELETE FROM reminder_outbox")

        async def reserve(service: WishlistService) -> int:
            return (await service.create_reservation(item, OTHER_GIFTER, 1)).id

        second = await store.execute_wish(reserve, item_id=item)

        async def purchase(service: WishlistService) -> None:
            await service.mark_reservation_purchased(first, GIFTER)

        async def cancel(service: WishlistService) -> None:
            await service.cancel_reservation(second, OTHER_GIFTER)

        await store.execute_wish(purchase, item_id=item)
        await store.execute_wish(cancel, item_id=item)
        with sqlite3.connect(db) as conn:
            assert conn.execute("SELECT COUNT(*) FROM reminder_outbox").fetchone()[0] == 0
            # Guard against unsafe work created by an older or mixed-version producer.
            conn.execute(
                "INSERT INTO reminder_outbox "
                "(occurrence_key,kind,user_id,list_id,item_id,event_date,next_attempt_at) "
                "SELECT 'legacy', 'reservation_changed', ?, wishlist_id, id, '', 0 "
                "FROM wl_items WHERE id=?",
                (GIFTER_ID, item),
            )
        sender = FakeNoticeSender()
        await _Env(store, db).worker(sender).run_once(int(time.time()) + 10)
        assert sender.calls == []
        with sqlite3.connect(db) as conn:
            assert conn.execute(
                "SELECT status FROM reminder_outbox WHERE occurrence_key='legacy'"
            ).fetchone() == ("skipped",)


@pytest.mark.parametrize(
    ("kind", "english", "russian"),
    [
        ("item_created", "Wish added", "Желание добавлено"),
        ("item_updated", "Wish updated", "Желание изменено"),
        ("item_archived", "Wish archived", "Желание архивировано"),
        ("item_restored", "Wish restored", "Желание восстановлено"),
        ("list_updated", "Wishlist updated", "Список изменён"),
        ("list_archived", "Wishlist archived", "Список архивирован"),
        ("list_restored", "Wishlist restored", "Список восстановлен"),
        ("membership_changed", "Wishlist membership changed", "Изменился состав списка"),
    ],
)
def test_shared_event_text_is_localized_and_identifies_the_actual_change(
    kind: str, english: str, russian: str
) -> None:
    from wishenka.notices.reminders import _render

    assert _render(kind, "List", "Wish", "", "en").startswith(english + ":")
    assert _render(kind, "List", "Wish", "", "ru").startswith(russian + ":")
    assert _render(kind, "List", "Wish", "", None).startswith(english + ":")


async def test_shared_change_does_not_fall_back_to_reservation_after_member_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An event-time member must remain a member even with an active booking."""
    import sqlite3
    import time

    from tests.receipt_support import GIFTER

    db = tmp_path / "removed-member.db"
    async with open_store(db) as store:
        seed_users(db, GIFTER_ID)
        await _verify_start(monkeypatch, db, GIFTER_ID)

        async def setup(service: WishlistService) -> tuple[int, int]:
            wl = await service.create_wishlist(owner=OWNER, title="Private")
            await service.add_member(wl.id, OWNER, GIFTER_ID)
            item = await service.add_wish_item(wl.id, OWNER, title="Original", quantity=2)
            await service.create_reservation(item.id, GIFTER, 1)
            return wl.id, item.id

        wishlist, item = await store.execute(setup)
        with sqlite3.connect(db) as conn:
            conn.execute("DELETE FROM reminder_outbox")

        async def update(service: WishlistService) -> None:
            await service.update_wish_item(item, OWNER, title="Confidential")

        await store.execute_wish(update, item_id=item)
        with sqlite3.connect(db) as conn:
            assert conn.execute(
                "SELECT requires_membership FROM reminder_outbox "
                "WHERE kind='item_updated' AND user_id=?",
                (GIFTER_ID,),
            ).fetchone() == (1,)

        async def remove(service: WishlistService) -> None:
            await service.remove_member(wishlist, OWNER, GIFTER_ID)

        await store.execute(remove)
        sender = FakeNoticeSender()
        await _Env(store, db).worker(sender).run_once(int(time.time()) + 10)
        assert all(chat != GIFTER_ID for chat, _ in sender.calls)


async def test_opted_in_reservation_confirmations_reach_only_actor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only explicitly requested own actions are confirmed; other givers learn nothing."""
    import sqlite3
    import time
    from types import SimpleNamespace

    from aiogram import Bot, Dispatcher
    from aiogram.types import Update

    from tests.receipt_support import GIFTER, OTHER_GIFTER, OTHER_GIFTER_ID, OWNER_ID
    from wishenka.bot.entry import create_router
    from wishenka.users.store import UserStore

    db = tmp_path / "own-confirmations.db"
    async with open_store(db) as store:
        for user_id in (GIFTER_ID, OTHER_GIFTER_ID, OWNER_ID):
            await _verify_start(monkeypatch, db, user_id)
        users = UserStore(f"sqlite+aiosqlite:///{db}")
        await users.initialize()
        try:
            sent = []

            async def transport(_bot, method, request_timeout=None):
                sent.append(method)
                return True

            monkeypatch.setattr(Bot, "__call__", transport)
            dispatcher = Dispatcher()
            dispatcher.include_router(
                create_router(
                    SimpleNamespace(mini_app_url="https://example.test", user_store=users)
                )
            )

            async def command(value: str) -> None:
                command_name = "/reservation_confirmations"
                update = Update.model_validate(
                    {
                        "update_id": 1,
                        "message": {
                            "message_id": 1,
                            "date": 1700000000,
                            "chat": {"id": GIFTER_ID, "type": "private"},
                            "from": {"id": GIFTER_ID, "is_bot": False, "first_name": "Test"},
                            "text": f"{command_name} {value}",
                            "entities": [
                                {"type": "bot_command", "offset": 0, "length": len(command_name)}
                            ],
                        },
                    }
                )
                bot = Bot("123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")
                try:
                    await dispatcher.feed_update(bot, update)
                finally:
                    await bot.session.close()

            await command("on")
            assert sent

            async def setup(service: WishlistService) -> int:
                wl = await service.create_wishlist(owner=OWNER, title="Private")
                item = await service.add_wish_item(wl.id, OWNER, title="Gift", quantity=3)
                return item.id

            item = await store.execute(setup)

            async def reserve(service: WishlistService) -> int:
                return (await service.create_reservation(item, GIFTER)).id

            reservation = await store.execute_wish(reserve, item_id=item)
            sender = FakeNoticeSender()
            worker = _Env(store, db).worker(sender)
            now = int(time.time()) + 10
            await worker.run_once(now)
            assert len(sender.calls) == 1
            assert sender.calls[0][0] == GIFTER_ID
            assert "reservation" in sender.calls[0][1].lower()

            async def reserve_other(service: WishlistService) -> None:
                await service.create_reservation(item, OTHER_GIFTER)

            await store.execute_wish(reserve_other, item_id=item)
            await worker.run_once(now + 1)
            assert len(sender.calls) == 1

            async def roll_back(service: WishlistService) -> None:
                await service.update_reservation_quantity(reservation, GIFTER, 2)
                raise RuntimeError("abort")

            with pytest.raises(RuntimeError, match="abort"):
                await store.execute_wish(roll_back, item_id=item)
            await worker.run_once(now + 2)
            assert len(sender.calls) == 1, "A rolled-back action must not queue a confirmation"

            async def cancel(service: WishlistService) -> None:
                await service.cancel_reservation(reservation, GIFTER)

            await store.execute_wish(cancel, item_id=item)
            await worker.run_once(now + 2)
            assert len(sender.calls) == 2 and sender.calls[-1][0] == GIFTER_ID

            async def reserve_again(service: WishlistService) -> None:
                await service.create_reservation(item, GIFTER)

            await store.execute_wish(reserve_again, item_id=item)
            await command("off")
            await worker.run_once(now + 3)
            assert len(sender.calls) == 2, "Revoked consent must suppress queued confirmations"
            with sqlite3.connect(db) as conn:
                assert conn.execute(
                    "SELECT enabled FROM user_notification_settings "
                    "WHERE user_id=? AND event_type='reservation_changes'",
                    (GIFTER_ID,),
                ).fetchone() == (0,)
        finally:
            await users.engine.dispose()


@pytest.mark.parametrize("changed_role", [None, "recipient", "personal"])
async def test_list_owner_confirmation_uses_current_wish_recipient(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, changed_role: str | None
) -> None:
    """A collaborative owner may be a giver, but never receives a recipient's notice."""
    import sqlite3
    import time

    from tests.receipt_support import OWNER_ID

    db = tmp_path / "owner-confirmation.db"
    async with open_store(db) as store:
        seed_users(db, GIFTER_ID)
        await _verify_start(monkeypatch, db, OWNER_ID)
        with sqlite3.connect(db) as conn:
            conn.execute(
                "INSERT INTO user_notification_settings "
                "(user_id,event_type,enabled,updated_at) VALUES (?, 'reservation_changes',1,'')",
                (OWNER_ID,),
            )

        async def setup(service: WishlistService) -> tuple[int, int]:
            wishlist = await service.create_wishlist(owner=OWNER, title="Shared")
            await service.add_member(wishlist.id, OWNER, GIFTER_ID)
            item = await service.add_wish_item(
                wishlist.id, OWNER, title="Someone else's gift", recipient_user_id=GIFTER_ID
            )
            return wishlist.id, item.id

        wishlist, item = await store.execute(setup)
        with sqlite3.connect(db) as conn:
            conn.execute("DELETE FROM reminder_outbox")

        async def reserve(service: WishlistService) -> None:
            await service.create_reservation(item, OWNER)

        await store.execute_wish(reserve, item_id=item)
        with sqlite3.connect(db) as conn:
            assert conn.execute(
                "SELECT COUNT(*) FROM reminder_outbox "
                "WHERE kind='reservation_confirmation' AND user_id=?",
                (OWNER_ID,),
            ).fetchone() == (1,)
            if changed_role == "recipient":
                conn.execute("UPDATE wl_items SET recipient_user_id=? WHERE id=?", (OWNER_ID, item))
            elif changed_role == "personal":
                conn.execute("UPDATE wl_lists SET is_collaborative=0 WHERE id=?", (wishlist,))

        sender = FakeNoticeSender()
        await _Env(store, db).worker(sender).run_once(int(time.time()) + 10)
        if changed_role is None:
            assert len(sender.calls) == 1 and sender.calls[0][0] == OWNER_ID
            assert "reservation" in sender.calls[0][1].lower()
        else:
            assert sender.calls == []
            with sqlite3.connect(db) as conn:
                assert conn.execute(
                    "SELECT status FROM reminder_outbox WHERE kind='reservation_confirmation'"
                ).fetchone() == ("skipped",)


@pytest.mark.parametrize("changed_role", [None, "recipient", "personal"])
async def test_receipt_to_collaborative_owner_uses_current_wish_recipient(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, changed_role: str | None
) -> None:
    """A list owner can be a giver, but must not receive their own gift's receipt."""
    import sqlite3
    import time

    from tests.receipt_support import GIFTER, OWNER_ID

    db = tmp_path / "owner-receipt.db"
    async with open_store(db) as store:
        seed_users(db, GIFTER_ID)
        await _verify_start(monkeypatch, db, OWNER_ID)

        async def setup(service: WishlistService) -> tuple[int, int]:
            wishlist = await service.create_wishlist(owner=OWNER, title="Shared")
            await service.add_member(wishlist.id, OWNER, GIFTER_ID)
            item = await service.add_wish_item(wishlist.id, OWNER, title="Shared gift", quantity=2)
            await service.create_reservation(item.id, OWNER)
            await service.record_item_fulfillment(item.id, GIFTER, 1)
            return wishlist.id, item.id

        wishlist, item = await store.execute(setup)
        with sqlite3.connect(db) as conn:
            conn.execute("DELETE FROM reminder_outbox")
            assert conn.execute(
                "SELECT count(*) FROM notification_outbox WHERE giver_user_id=?", (OWNER_ID,)
            ).fetchone() == (1,)
            if changed_role == "recipient":
                conn.execute("UPDATE wl_items SET recipient_user_id=? WHERE id=?", (OWNER_ID, item))
            elif changed_role == "personal":
                conn.execute("UPDATE wl_lists SET is_collaborative=0 WHERE id=?", (wishlist,))

        sender = FakeNoticeSender()
        await _Env(store, db).worker(sender).run_once(int(time.time()) + 10)
        if changed_role is None:
            assert len(sender.calls) == 1 and sender.calls[0][0] == OWNER_ID
            assert "Shared gift" in sender.calls[0][1]
        else:
            assert sender.calls == []
            with sqlite3.connect(db) as conn:
                assert conn.execute(
                    "SELECT status FROM notification_outbox WHERE giver_user_id=?", (OWNER_ID,)
                ).fetchone() == ("skipped",)


@pytest.mark.parametrize("collaborative", [False, True])
async def test_confirmation_is_not_queued_for_actual_wish_recipient(collaborative: bool) -> None:
    """The recipient exclusion applies at production time for each type of wishlist."""
    from tests.receipt_support import OWNER_ID

    service = WishlistService.in_memory()
    wishlist = await service.create_wishlist(owner=OWNER, title="Gift")
    if collaborative:
        await service.add_member(wishlist.id, OWNER, GIFTER_ID)
    item = await service.add_wish_item(
        wishlist.id,
        OWNER,
        title="Gift",
        recipient_user_id=GIFTER_ID if collaborative else None,
    )
    service._new_shared_item_events.clear()
    service._record_reservation_confirmation(item, GIFTER_ID if collaborative else OWNER_ID)
    assert service._new_shared_item_events == []
