"""Failing repro tests for WISHENKA-34 (Step 3, red before Step 4)."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests.notice_support import FakeNoticeSender
from tests.receipt_support import (
    GIFTER,
    GIFTER_ID,
    OWNER,
    OWNER_ID,
    STRANGER_ID,
    app_env,
    bearer,
    db_path_of,
    open_store,
    outbox_rows,
    sql_exec,
    sql_rows,
)
from tests.test_notice_delivery_repro import _verify_start
from tests.test_receipt_notices import _Env
from wishenka.auth.models import TelegramUser
from wishenka.notices.reminders import claim_reminder, refresh_reminder
from wishenka.users.store import UserStore
from wishenka.wishlists.service import WishlistService

pytestmark = pytest.mark.timeout(60)


def test_profile_preferences_and_global_notifications_api(tmp_path: Path) -> None:
    """GET /api/profile/preferences and PUT /api/profile/notifications/global work and persist."""
    with app_env(tmp_path, "prefs-global.db") as (client, sessions, _app):
        headers = bearer(sessions, OWNER_ID, "Alice")

        resp = client.get("/api/profile/preferences", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "locale" in data
        assert "birthdate" in data
        assert "birthday_reminders" in data
        assert "global_notifications" in data
        assert "wishlists" in data

        put_resp = client.put(
            "/api/profile/notifications/global",
            headers=headers,
            json={"settings": {"reservation_changes": True, "gift_received": False}},
        )
        assert put_resp.status_code == 200

        refreshed = client.get("/api/profile/preferences", headers=headers)
        assert refreshed.status_code == 200
        global_notifs = refreshed.json()["global_notifications"]
        assert global_notifs["reservation_changes"] is True
        assert global_notifs["gift_received"] is False


async def test_wishlist_notification_override_precedence_reset_and_authz(tmp_path: Path) -> None:
    """List overrides take precedence over global settings, null resets, stranger gets 404."""
    db_name = "prefs-wishlist.db"
    with app_env(tmp_path, db_name) as (client, sessions, app):
        db = Path(db_path_of(app))
        async with open_store(db) as store:
            wl = await WishlistService(store).create_wishlist(owner=OWNER, title="Birthday List")

        owner_headers = bearer(sessions, OWNER_ID, "Alice")
        stranger_headers = bearer(sessions, STRANGER_ID, "Sven")

        # Set global reminders=False
        g_resp = client.put(
            "/api/profile/notifications/global",
            headers=owner_headers,
            json={"settings": {"reminders": False}},
        )
        assert g_resp.status_code == 200

        # Override reminders=True for this specific wishlist
        o_resp = client.put(
            f"/api/profile/notifications/wishlists/{wl.id}",
            headers=owner_headers,
            json={"overrides": {"reminders": True}},
        )
        assert o_resp.status_code == 200
        o_data = o_resp.json()
        assert o_data["overrides"]["reminders"] is True
        assert o_data["effective"]["reminders"]["enabled"] is True

        # Reset override to null -> falls back to global (False)
        r_resp = client.put(
            f"/api/profile/notifications/wishlists/{wl.id}",
            headers=owner_headers,
            json={"overrides": {"reminders": None}},
        )
        assert r_resp.status_code == 200
        r_data = r_resp.json()
        assert r_data["overrides"]["reminders"] is None
        assert r_data["effective"]["reminders"]["enabled"] is False

        # Stranger cannot view or update overrides for private wishlist
        assert (
            client.get(
                f"/api/profile/notifications/wishlists/{wl.id}", headers=stranger_headers
            ).status_code
            == 404
        )
        assert (
            client.put(
                f"/api/profile/notifications/wishlists/{wl.id}",
                headers=stranger_headers,
                json={"overrides": {"reminders": True}},
            ).status_code
            == 404
        )


async def test_birthday_reminders_disabled_suppresses_delivery_and_keeps_entries(
    tmp_path: Path,
) -> None:
    """Disabling birthday_reminders suppresses claim & refresh while preserving birthday_entries."""
    db = tmp_path / "bday-prefs.db"
    users = UserStore(f"sqlite+aiosqlite:///{db}")
    await users.initialize()
    try:
        await users.upsert_user(TelegramUser(id=OWNER_ID, first_name="Alice", language_code="ru"))
    finally:
        await users.engine.dispose()

    async with open_store(db) as store:
        sql_exec(
            db,
            "INSERT OR REPLACE INTO bot_destinations (user_id, chat_id, active) VALUES (?, ?, 1)",
            (OWNER_ID, OWNER_ID),
        )
        sql_exec(
            db,
            "INSERT INTO birthday_entries (id, owner_id, label, month, day, revision, deleted) "
            "VALUES (1, ?, 'Mom', 5, 20, 1, 0)",
            (OWNER_ID,),
        )
        now = int(datetime(2030, 5, 13, tzinfo=UTC).timestamp())
        sql_exec(
            db,
            "INSERT INTO reminder_outbox "
            "(occurrence_key, kind, user_id, birthday_id, revision, event_date, status, "
            "next_attempt_at) VALUES (?, 'birthday', ?, 1, 1, '2030-05-20', 'pending', ?)",
            ("bday:1:2030-05-20", OWNER_ID, now - 10),
        )
        # Keep general reminders enabled, but disable birthday_reminders explicitly
        sql_exec(
            db,
            "INSERT INTO user_notification_settings (user_id, event_type, enabled, updated_at) "
            "VALUES (?, 'reminders', 1, ?)",
            (OWNER_ID, now),
        )
        sql_exec(
            db,
            "INSERT INTO user_notification_settings (user_id, event_type, enabled, updated_at) "
            "VALUES (?, 'birthday_reminders', 0, ?)",
            (OWNER_ID, now),
        )

        claimed = await claim_reminder(store, now, lease=60, global_limit=20, chat_interval=1)
        assert claimed is None

        outbox = sql_rows(db, "SELECT status FROM reminder_outbox WHERE id = 1")
        assert outbox[0]["status"] == "skipped"
        entries = sql_rows(db, "SELECT deleted FROM birthday_entries WHERE id = 1")
        assert entries[0]["deleted"] == 0

        # Also verify refresh_reminder suppresses an already-claimed birthday reminder
        sql_exec(
            db,
            "UPDATE user_notification_settings SET enabled = 1 "
            "WHERE event_type = 'birthday_reminders'",
        )
        sql_exec(
            db,
            "UPDATE reminder_outbox SET status = 'pending', claimed_at = NULL, "
            "claim_token = NULL WHERE id = 1",
        )
        claimed2 = await claim_reminder(store, now, lease=60, global_limit=20, chat_interval=1)
        assert claimed2 is not None
        sql_exec(
            db,
            "UPDATE user_notification_settings SET enabled = 0 "
            "WHERE event_type = 'birthday_reminders'",
        )
        refreshed = await refresh_reminder(store, claimed2, now)
        assert refreshed is None


async def test_birthdate_explicit_source_survives_upsert_and_rejects_invalid_date(
    tmp_path: Path,
) -> None:
    """PATCH /api/profile/birthdate validates dates, sets explicit source, and survives upsert."""
    db_name = "birthdate.db"
    with app_env(tmp_path, db_name) as (client, sessions, app):
        db = Path(db_path_of(app))
        headers = bearer(sessions, OWNER_ID, "Alice")

        # Invalid calendar date: Feb 30
        bad_resp = client.patch(
            "/api/profile/birthdate",
            headers=headers,
            json={"day": 30, "month": 2, "year": None},
        )
        assert bad_resp.status_code == 422

        # Valid Feb 29 without year
        ok_resp = client.patch(
            "/api/profile/birthdate",
            headers=headers,
            json={"day": 29, "month": 2, "year": None},
        )
        assert ok_resp.status_code == 200
        body = ok_resp.json()
        assert body["day"] == 29
        assert body["month"] == 2
        assert body["year"] is None
        assert body["source"] == "explicit"

        # Subsequent Telegram upsert must not overwrite explicit birthdate
        users = UserStore(f"sqlite+aiosqlite:///{db}")
        await users.initialize()
        try:
            await users.upsert_user(
                TelegramUser(id=OWNER_ID, first_name="Alice Updated", language_code="en")
            )
            record = await users.get_by_telegram_id(OWNER_ID)
            assert record is not None
            assert getattr(record, "birth_day", None) == 29
            assert getattr(record, "birth_month", None) == 2
            assert getattr(record, "birthdate_source", None) == "explicit"
        finally:
            await users.engine.dispose()

        # Explicit clear preserves birthdate_source='explicit'
        clr_resp = client.patch(
            "/api/profile/birthdate",
            headers=headers,
            json={"clear": True},
        )
        assert clr_resp.status_code == 200
        clr_body = clr_resp.json()
        assert clr_body["day"] is None
        assert clr_body["month"] is None
        assert clr_body["source"] == "explicit"


async def test_surprise_invariant_holds_when_recipient_enables_all_notifications(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Enabling reservation_changes & gift_received never leaks reservation/receipt to recipient."""
    db_name = "surprise-prefs.db"
    with app_env(tmp_path, db_name) as (client, sessions, app):
        db = Path(db_path_of(app))
        async with open_store(db) as store:
            await _verify_start(monkeypatch, db, OWNER_ID)
            await _verify_start(monkeypatch, db, GIFTER_ID)

            async def setup(service: WishlistService) -> tuple[int, int]:
                wl = await service.create_wishlist(owner=OWNER, title="Surprise Party")
                item = await service.add_wish_item(wl.id, OWNER, title="Headphones", quantity=2)
                return wl.id, item.id

            wishlist_id, item_id = await setup(WishlistService(store))

            owner_headers = bearer(sessions, OWNER_ID, "Alice")
            assert (
                client.put(
                    "/api/profile/notifications/global",
                    headers=owner_headers,
                    json={"settings": {"reservation_changes": True, "gift_received": True}},
                ).status_code
                == 200
            )
            assert (
                client.put(
                    f"/api/profile/notifications/wishlists/{wishlist_id}",
                    headers=owner_headers,
                    json={"overrides": {"reservation_changes": True, "gift_received": True}},
                ).status_code
                == 200
            )

            await store.execute(lambda svc: svc.create_reservation(item_id, GIFTER, quantity=1))
            await store.execute(lambda svc: svc.record_item_fulfillment(item_id, OWNER, 1))

            sender = FakeNoticeSender()
            worker = _Env(store, db).worker(sender)
            now = int(time.time()) + 10
            await worker.run_once(now)
            await worker.run_once(now + 1)

            assert all(chat_id != OWNER_ID for chat_id, _ in sender.calls)
            for row in outbox_rows(db):
                assert row["giver_user_id"] != OWNER_ID
