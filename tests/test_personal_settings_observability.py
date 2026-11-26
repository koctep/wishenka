"""Pin existing observability of the settings API paths used by the page (WISHENKA-291)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from pathlib import Path
from typing import Any

import pytest

from tests.receipt_support import OWNER_ID, app_env, bearer
from wishenka.auth.models import AuthenticatedUser, TelegramUser
from wishenka.logging import JsonFormatter
from wishenka.wishlists.service import WishlistService

pytestmark = pytest.mark.timeout(30)

LOGGERS = ("wishenka.web.profile", "wishenka.users", "wishenka.notices.preferences")
EVENTS = {
    "locale_explicit_updated",
    "birthdate_explicit_updated",
    "birthdate_explicit_cleared",
    "notification_global_updated",
    "notification_wishlist_updated",
}


def _capture(caplog: pytest.LogCaptureFixture) -> contextlib.ExitStack:
    stack = contextlib.ExitStack()
    for name in LOGGERS:
        stack.enter_context(caplog.at_level(logging.INFO, logger=name))
    return stack


def _events(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if getattr(r, "event", None) in EVENTS]


def test_settings_mutations_log_safe_success_events(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Each successful settings mutation emits one INFO store event without values or PII."""
    with app_env(tmp_path, "settings-obs.db") as (client, sessions, app):
        asyncio.run(
            app.state.user_store.upsert_user(TelegramUser(id=OWNER_ID, first_name="SecretAlice"))
        )

        async def _create(service: WishlistService) -> int:
            return (await service.create_wishlist(owner=owner, title="PrivateListTitle")).id

        owner = AuthenticatedUser(
            telegram_id=OWNER_ID, first_name="SecretAlice", auth_method="session_token"
        )
        wishlist_id = asyncio.run(_create(WishlistService(app.state.wishlist_store)))
        headers = bearer(sessions, OWNER_ID, "SecretAlice")
        with _capture(caplog):
            calls: list[Any] = [
                client.patch("/api/profile/locale", headers=headers, json={"locale": "ru"}),
                client.patch(
                    "/api/profile/birthdate",
                    headers=headers,
                    json={"day": 17, "month": 3, "year": 1987},
                ),
                client.patch("/api/profile/birthdate", headers=headers, json={"clear": True}),
                client.put(
                    "/api/profile/notifications/global",
                    headers=headers,
                    json={"settings": {"reminders": True}},
                ),
                client.put(
                    f"/api/profile/notifications/wishlists/{wishlist_id}",
                    headers=headers,
                    json={"overrides": {"reminders": False}},
                ),
            ]
        assert [c.status_code for c in calls] == [200] * 5
    records = _events(caplog)
    assert [getattr(r, "event", None) for r in records] == [
        "locale_explicit_updated",
        "birthdate_explicit_updated",
        "birthdate_explicit_cleared",
        "notification_global_updated",
        "notification_wishlist_updated",
    ]
    assert all(r.levelno == logging.INFO for r in records)
    assert getattr(records[1], "has_year", None) is True
    assert getattr(records[4], "wishlist_id", None) == wishlist_id
    assert getattr(records[4], "updated_count", None) == 1
    rendered = " ".join(JsonFormatter().format(r) for r in records)
    for forbidden in ("1987", "SecretAlice", "PrivateListTitle", "Bearer", str(OWNER_ID)):
        assert forbidden not in rendered


def test_rejected_settings_mutations_emit_no_success_event(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Rejected payloads log only the existing WARNING events, never a success event."""
    with app_env(tmp_path, "settings-obs-bad.db") as (client, sessions, app):
        asyncio.run(app.state.user_store.upsert_user(TelegramUser(id=OWNER_ID, first_name="Alice")))
        headers = bearer(sessions, OWNER_ID, "Alice")
        with _capture(caplog):
            bad = [
                client.patch("/api/profile/locale", headers=headers, json={"locale": "xx"}),
                client.patch(
                    "/api/profile/birthdate", headers=headers, json={"day": 31, "month": 2}
                ),
                client.put(
                    "/api/profile/notifications/global",
                    headers=headers,
                    json={"settings": {"bogus": True}},
                ),
            ]
    assert [c.status_code for c in bad] == [422, 422, 422]
    assert _events(caplog) == []
    warned = {getattr(r, "event", None) for r in caplog.records if r.levelno == logging.WARNING}
    assert {
        "locale_invalid_request",
        "birthdate_invalid_request",
        "notification_global_invalid_request",
    } <= warned
