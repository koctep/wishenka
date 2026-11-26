"""Comprehensive unit and integration tests for WISHENKA-34 preferences & settings."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests.receipt_support import (
    GIFTER,
    OWNER,
    OWNER_ID,
    STRANGER_ID,
    app_env,
    bearer,
    open_store,
    seed_users,
    sql_exec,
)
from wishenka.auth.models import TelegramUser
from wishenka.notices.preferences import (
    GLOBAL_NOTIFICATION_DEFAULTS,
    NotificationPreferencesStore,
)
from wishenka.notices.reminders import claim_reminder
from wishenka.users.store import UserNotFoundError, UserStore, validate_birthdate
from wishenka.wishlists.service import WishlistService

pytestmark = pytest.mark.timeout(30)


def test_validate_birthdate_cases() -> None:
    """validate_birthdate accepts valid dates (incl. Feb 29 without year) and rejects invalid."""
    assert validate_birthdate(29, 2, None) == (29, 2, None)
    assert validate_birthdate(29, 2, 2000) == (29, 2, 2000)
    assert validate_birthdate(15, 8, 1995) == (15, 8, 1995)

    for bad in [
        (30, 2, None),
        (29, 2, 2023),
        (31, 4, 2020),
        (0, 1, None),
        (10, 13, None),
        (10, 1, 1899),
        (True, 1, None),
        (1, True, None),
        (1, 1, True),
    ]:
        with pytest.raises(ValueError):
            validate_birthdate(*bad)


async def test_user_store_birthdate_lifecycle_and_not_found(tmp_path: Path) -> None:
    """UserStore.set_birthdate and clear_birthdate persist explicit source and raise on missing."""
    db = tmp_path / "users-bday.db"
    store = UserStore(f"sqlite+aiosqlite:///{db}")
    await store.initialize()
    try:
        with pytest.raises(UserNotFoundError):
            await store.set_birthdate(9999, day=1, month=1, year=2000)
        with pytest.raises(UserNotFoundError):
            await store.clear_birthdate(9999)

        await store.upsert_user(TelegramUser(id=OWNER_ID, first_name="Alice", language_code="ru"))
        updated = await store.set_birthdate(OWNER_ID, day=12, month=6, year=1998)
        assert updated.birth_day == 12
        assert updated.birth_month == 6
        assert updated.birth_year == 1998
        assert updated.birthdate_source == "explicit"

        # Subsequent Telegram upsert preserves explicit birthdate
        after_upsert = await store.upsert_user(
            TelegramUser(id=OWNER_ID, first_name="Alice2", language_code="en")
        )
        assert after_upsert.birth_day == 12
        assert after_upsert.birth_month == 6
        assert after_upsert.birth_year == 1998
        assert after_upsert.birthdate_source == "explicit"

        cleared = await store.clear_birthdate(OWNER_ID)
        assert cleared.birth_day is None
        assert cleared.birth_month is None
        assert cleared.birth_year is None
        assert cleared.birthdate_source == "explicit"
    finally:
        await store.engine.dispose()


async def test_preferences_store_validation_roles_and_isolation(tmp_path: Path) -> None:
    """NotificationPreferencesStore validates inputs, tracks roles, and isolates wishlists."""
    db = tmp_path / "prefs-store.db"
    async with open_store(db) as wl_store:
        seed_users(db, OWNER_ID)
        sql_exec(
            db,
            "INSERT OR IGNORE INTO users (telegram_id, first_name, created_at, updated_at) "
            "VALUES (?, 'Owner', '2026-01-01', '2026-01-01')",
            (OWNER_ID,),
        )
        wl_owner = await WishlistService(wl_store).create_wishlist(owner=OWNER, title="Own")
        wl_other = await WishlistService(wl_store).create_wishlist(
            owner=GIFTER, title="Gifter List"
        )
        await WishlistService(wl_store).get_wishlist_by_public_token(wl_other.public_token, OWNER)
        await WishlistService(wl_store).add_favorite(OWNER, wl_other.id)

        prefs = NotificationPreferencesStore(wl_store.engine)
        defaults = await prefs.get_global_settings(OWNER_ID)
        assert defaults == GLOBAL_NOTIFICATION_DEFAULTS

        with pytest.raises(ValueError):
            await prefs.update_global_settings(OWNER_ID, {})
        with pytest.raises(ValueError):
            await prefs.update_global_settings(OWNER_ID, {"unknown_cat": True})
        with pytest.raises(ValueError):
            await prefs.update_global_settings(OWNER_ID, {"reminders": 1})

        with pytest.raises(ValueError):
            await prefs.update_wishlist_overrides(OWNER_ID, wl_owner.id, {"unknown": True})
        with pytest.raises(ValueError):
            await prefs.update_wishlist_overrides(OWNER_ID, wl_owner.id, {"reminders": "yes"})

        # Override on wl_owner does not affect wl_other
        await prefs.update_wishlist_overrides(OWNER_ID, wl_owner.id, {"reminders": False})
        lists = await prefs.list_accessible_wishlists_with_preferences(OWNER_ID)
        by_id = {w.id: w for w in lists}
        assert by_id[wl_owner.id].role == "owner"
        assert by_id[wl_owner.id].effective["reminders"].enabled is False
        assert by_id[wl_owner.id].effective["reminders"].source == "override"
        assert by_id[wl_other.id].role == "favorite"
        assert by_id[wl_other.id].effective["reminders"].enabled is True
        assert by_id[wl_other.id].effective["reminders"].source == "default"

        # Stranger has no access
        assert await prefs.get_wishlist_preferences(STRANGER_ID, wl_owner.id) is None
        assert (
            await prefs.update_wishlist_overrides(STRANGER_ID, wl_owner.id, {"reminders": False})
            is None
        )


def test_preferences_api_auth_validation_and_bilingual_settings_page(tmp_path: Path) -> None:
    """API enforces auth & 422 validation; /settings renders RU and EN preference sections."""
    with app_env(tmp_path, "prefs-api.db") as (client, sessions, _app):
        assert client.get("/api/profile/preferences").status_code == 401
        assert (
            client.patch("/api/profile/birthdate", json={"day": 1, "month": 1}).status_code == 401
        )
        assert (
            client.put(
                "/api/profile/notifications/global", json={"settings": {"reminders": False}}
            ).status_code
            == 401
        )
        assert client.get("/api/profile/notifications/wishlists/1").status_code == 401

        headers = bearer(sessions, OWNER_ID, "Alice")

        # Invalid global notification payload -> 422
        assert (
            client.put(
                "/api/profile/notifications/global",
                headers=headers,
                json={"settings": {"nonexistent": True}},
            ).status_code
            == 422
        )
        assert (
            client.put(
                "/api/profile/notifications/global",
                headers=headers,
                json={"settings": {"reminders": "not-a-bool"}},
            ).status_code
            == 422
        )

        # Invalid birthdate payload -> 422
        assert (
            client.patch("/api/profile/birthdate", headers=headers, json={"day": 1}).status_code
            == 422
        )

        # Settings HTML page renders in EN by default and in RU after locale change
        page_en = client.get("/settings", headers=headers)
        assert page_en.status_code == 200
        assert "Birthday reminders" in page_en.text
        assert "Global notification preferences" in page_en.text

        # Create user row via birthdate update, then switch locale to RU
        assert (
            client.patch(
                "/api/profile/birthdate",
                headers=headers,
                json={"day": 5, "month": 11, "year": 1992},
            ).status_code
            == 200
        )
        assert (
            client.patch("/api/profile/locale", headers=headers, json={"locale": "ru"}).status_code
            == 200
        )
        page_ru = client.get("/settings", headers=headers)
        assert page_ru.status_code == 200
        assert "Напоминания о днях рождения" in page_ru.text
        assert "Глобальные настройки уведомлений" in page_ru.text


async def test_birthday_reminders_reenable_resumes_future_delivery(tmp_path: Path) -> None:
    """Re-enabling birthday_reminders allows future birthday reminders to be claimed."""
    db = tmp_path / "bday-reenable.db"
    users = UserStore(f"sqlite+aiosqlite:///{db}")
    await users.initialize()
    try:
        await users.upsert_user(TelegramUser(id=OWNER_ID, first_name="Alice", language_code="en"))
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
            "VALUES (1, ?, 'Dad', 7, 10, 1, 0)",
            (OWNER_ID,),
        )
        now = int(datetime(2030, 7, 3, tzinfo=UTC).timestamp())
        sql_exec(
            db,
            "INSERT INTO reminder_outbox "
            "(occurrence_key, kind, user_id, birthday_id, revision, event_date, status, "
            "next_attempt_at) VALUES (?, 'birthday', ?, 1, 1, '2030-07-10', 'pending', ?)",
            ("bday:1:2030-07-10", OWNER_ID, now - 5),
        )

        prefs = NotificationPreferencesStore(store.engine)
        await prefs.update_global_settings(OWNER_ID, {"birthday_reminders": False})
        assert await claim_reminder(store, now, lease=60, global_limit=20, chat_interval=1) is None

        # Re-enable and queue a new occurrence
        await prefs.update_global_settings(OWNER_ID, {"birthday_reminders": True})
        sql_exec(
            db,
            "INSERT INTO reminder_outbox "
            "(occurrence_key, kind, user_id, birthday_id, revision, event_date, status, "
            "next_attempt_at) VALUES (?, 'birthday', ?, 1, 1, '2030-07-10', 'pending', ?)",
            ("bday:1:2030-07-10-b", OWNER_ID, now - 5),
        )
        claimed = await claim_reminder(store, now + 10, lease=60, global_limit=20, chat_interval=1)
        assert claimed is not None
        assert "Dad" in claimed.body
