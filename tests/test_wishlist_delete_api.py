"""Failing repro for WISHENKA-295 (Step 3): the owner deletes a wishlist through the API.

Today the domain rule exists (``WishlistService.delete_wishlist``) but no HTTP route calls it, so
every ``DELETE /api/wishlists/{id}`` answers 405 and the Mini App shell has no retention
attribute. These tests assert the designed behavior (``20-architecture.md``, D-1, D-2, D-4):
owner-only, idempotent, secrecy-safe deletion on top of the existing restore flow.
"""

from __future__ import annotations

import asyncio
import logging
import re
import sqlite3
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from wishenka.auth.models import AuthenticatedUser, TelegramUser
from wishenka.auth.session import SessionTokenService
from wishenka.config import Settings
from wishenka.i18n.catalog import CATALOG, miniapp_catalog
from wishenka.web.app import create_app
from wishenka.wishlists.models import ReservationStatus
from wishenka.wishlists.service import WishlistService

pytestmark = pytest.mark.timeout(30)

OWNER_ID = 101
ADMIN_ID = 102
MEMBER_ID = 103
OTHER_OWNER_ID = 104
GIFTER_ID = 202
STRANGER_ID = 303
ORIGIN = "http://testserver"
UNKNOWN_ID = 999999
USERS = {
    OWNER_ID: "Owner",
    ADMIN_ID: "Admin",
    MEMBER_ID: "Member",
    OTHER_OWNER_ID: "Other",
    GIFTER_ID: "Giver",
    STRANGER_ID: "Stranger",
}


def _table(locale: str) -> dict[str, str]:
    return CATALOG["ru" if locale == "ru" else "en"]


OWNER = AuthenticatedUser(telegram_id=OWNER_ID, first_name="Owner", auth_method="session_token")
GIFTER = AuthenticatedUser(telegram_id=GIFTER_ID, first_name="Giver", auth_method="session_token")
DELETE_KEYS = (
    "heading",
    "hint",
    "open",
    "confirm_title",
    "consequences",
    "restore_promise",
    "purge_promise",
    "cancel",
    "confirm",
    "pending",
    "done",
    "failed",
)
PROMISE_KEYS = ("restore_promise", "purge_promise")
RESERVATION_ALLOWED_KEYS = ("consequences", "restore_promise")
# The only reservation wording the two allowed keys may carry (requirement 3 and 8).
RESERVATION_CLAUSES = {
    "en": ("any reservations", "cancelled reservations stay cancelled"),
    "ru": ("все резервирования", "отменённые резервирования не восстанавливаются"),
}
RESERVATION_WORD = re.compile(r"reserv|резерв|бронир|бронь", re.IGNORECASE)
COUNT_STATE_PERSON = re.compile(
    r"\d|bought|purchased|куплен|приобрет|приобре|\bwho\b|by whom|\bкто\b|кем\b", re.IGNORECASE
)
IMMEDIATE = re.compile(r"immediately|at once|right away|сразу|немедленно|мгновенно", re.IGNORECASE)


@dataclass
class Env:
    """A running app on its own database with the users of the scenario."""

    client: TestClient
    app: FastAPI
    sessions: SessionTokenService
    db_path: Path
    settings: Settings

    def headers(self, user_id: int) -> dict[str, str]:
        """Bearer headers of a seeded user (no CSRF check applies to Bearer)."""
        return {"Authorization": f"Bearer {self.sessions.create_token(user_id, USERS[user_id])}"}


def _settings(db_path: Path, retention_days: int = 30) -> Settings:
    return Settings(
        database_url=f"sqlite+aiosqlite:///{db_path}",
        sqlite_db_path=str(db_path),
        secret_key="test-secret-key",
        wishlist_retention_days=retention_days,
        application_origin=ORIGIN,
    )


@contextmanager
def _open_app(db_path: Path, retention_days: int = 30) -> Iterator[Env]:
    settings = _settings(db_path, retention_days)
    app = create_app(settings)
    sessions = SessionTokenService(settings.secret_key)
    with TestClient(app) as client:

        async def seed_users() -> None:
            for user_id, name in USERS.items():
                await app.state.user_store.upsert_user(TelegramUser(id=user_id, first_name=name))

        asyncio.run(seed_users())
        yield Env(client, app, sessions, db_path, settings)


@pytest.fixture
def env(tmp_path: Path) -> Iterator[Env]:
    """Application with six seeded users and the default 30-day retention."""
    with _open_app(tmp_path / "delete-api.db") as opened:
        yield opened


def _run[T](env: Env, action: Callable[[WishlistService], Awaitable[T]]) -> T:
    assert env.client.portal is not None
    result: T = env.client.portal.call(env.app.state.wishlist_store.execute, action)
    return result


def _create(env: Env, name: str = "Birthday", user_id: int = OWNER_ID) -> dict[str, Any]:
    created = env.client.post("/api/wishlists", json={"name": name}, headers=env.headers(user_id))
    assert created.status_code == 201, created.text
    body: dict[str, Any] = created.json()
    return body


def _delete(env: Env, wishlist_id: int, user_id: int = OWNER_ID) -> Any:
    return env.client.delete(f"/api/wishlists/{wishlist_id}", headers=env.headers(user_id))


def _get(env: Env, wishlist_id: int, user_id: int = OWNER_ID) -> Any:
    return env.client.get(f"/api/wishlists/{wishlist_id}", headers=env.headers(user_id))


def _ids(env: Env, path: str, user_id: int = OWNER_ID) -> list[int]:
    response = env.client.get(path, headers=env.headers(user_id))
    assert response.status_code == 200, response.text
    return [int(row["id"]) for row in response.json()]


def _row(db_path: Path, wishlist_id: int) -> tuple[str, str]:
    with sqlite3.connect(db_path) as conn:
        found = conn.execute(
            "SELECT status, updated_at FROM wl_lists WHERE id = ?", (wishlist_id,)
        ).fetchone()
    assert found is not None
    return str(found[0]), str(found[1])


def _share(env: Env, wishlist: dict[str, Any]) -> None:
    """Invite an administrator and a plain member (existing invitation flow)."""
    for user_id in (ADMIN_ID, MEMBER_ID):
        accepted = env.client.post(
            "/api/invitations/accept",
            headers={**env.headers(user_id), "x-invite-token": wishlist["invite_token"]},
        )
        assert accepted.status_code == 200, accepted.text
    promoted = env.client.patch(
        f"/api/wishlists/{wishlist['id']}/members/{ADMIN_ID}/role",
        json={"role": "admin"},
        headers=env.headers(OWNER_ID),
    )
    assert promoted.status_code == 200, promoted.text


def _add_item(env: Env, wishlist_id: int, title: str) -> int:
    response = env.client.post(
        f"/api/wishlists/{wishlist_id}/items",
        json={"title": title, "quantity": 1},
        headers=env.headers(OWNER_ID),
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def _reserve(env: Env, item_id: int, *, purchased: bool) -> int:
    async def action(service: WishlistService) -> int:
        reservation = await service.create_reservation(item_id, GIFTER, quantity=1)
        if purchased:
            await service.mark_reservation_purchased(reservation.id, GIFTER)
        return reservation.id

    return _run(env, action)


def _reservation_status(env: Env, reservation_id: int) -> ReservationStatus:
    async def action(service: WishlistService) -> ReservationStatus:
        return service._reservations[reservation_id].status

    return _run(env, action)


def _status_changes(caplog: pytest.LogCaptureFixture, wishlist_id: int) -> list[str]:
    return [
        str(getattr(record, "to_status", ""))
        for record in caplog.records
        if getattr(record, "event", None) == "wishlist_status_changed"
        and getattr(record, "wishlist_id", None) == wishlist_id
    ]


# --- owner flow (requirements 5, 6, 7) -------------------------------------------------------


def test_owner_delete_returns_constant_body_and_moves_list_to_recently_deleted(env: Env) -> None:
    created = _create(env)
    wishlist_id = created["id"]

    response = _delete(env, wishlist_id)

    assert response.status_code == 200, response.text
    assert response.json() == {
        "status": "deleted",
        "wishlist_id": wishlist_id,
        "retention_days": 30,
    }
    assert wishlist_id not in _ids(env, "/api/wishlists")
    assert _get(env, wishlist_id).status_code == 404
    deleted = env.client.get("/api/wishlists/deleted", headers=env.headers(OWNER_ID)).json()
    assert [row["id"] for row in deleted] == [wishlist_id]
    assert deleted[0]["days_remaining"] == 30
    assert _row(env.db_path, wishlist_id)[0] == "deleted"


def test_deleted_list_is_hidden_from_members_and_links_stop_working(env: Env) -> None:
    created = _create(env)
    _share(env, created)

    assert _delete(env, created["id"]).status_code == 200

    for user_id in (ADMIN_ID, MEMBER_ID):
        assert created["id"] not in _ids(env, "/api/wishlists", user_id)
        assert _get(env, created["id"], user_id).status_code == 404
    assert env.client.get(f"/api/public/wishlists/{created['share_token']}").status_code == 404
    preview = env.client.get(
        "/api/invitations/preview", headers={"x-invite-token": created["invite_token"]}
    )
    assert preview.status_code == 404


def test_delete_leaves_other_lists_of_owner_and_of_other_users_unchanged(env: Env) -> None:
    doomed = _create(env, "Doomed")
    kept = _create(env, "Kept")
    other = _create(env, "Other user list", OTHER_OWNER_ID)
    _add_item(env, kept["id"], "Camera")
    before = {
        "kept": _get(env, kept["id"]).json(),
        "other": _get(env, other["id"], OTHER_OWNER_ID).json(),
    }

    assert _delete(env, doomed["id"]).status_code == 200

    assert _get(env, kept["id"]).json() == before["kept"]
    assert _get(env, other["id"], OTHER_OWNER_ID).json() == before["other"]
    assert _ids(env, "/api/wishlists") == [kept["id"]]
    assert _ids(env, "/api/wishlists", OTHER_OWNER_ID) == [other["id"]]
    assert _ids(env, "/api/wishlists/deleted", OTHER_OWNER_ID) == []


def test_delete_cancels_reservations_of_that_list_only(env: Env) -> None:
    doomed = _create(env, "Doomed")
    kept = _create(env, "Kept")
    active = _reserve(env, _add_item(env, doomed["id"], "Active gift"), purchased=False)
    bought = _reserve(env, _add_item(env, doomed["id"], "Bought gift"), purchased=True)
    elsewhere = _reserve(env, _add_item(env, kept["id"], "Other gift"), purchased=False)

    assert _delete(env, doomed["id"]).status_code == 200

    assert _reservation_status(env, active) == ReservationStatus.CANCELLED
    assert _reservation_status(env, bought) == ReservationStatus.CANCELLED
    assert _reservation_status(env, elsewhere) == ReservationStatus.ACTIVE


def test_retention_days_in_reply_and_recently_deleted_follow_settings(tmp_path: Path) -> None:
    with _open_app(tmp_path / "retention-7.db", retention_days=7) as env7:
        wishlist_id = _create(env7)["id"]
        response = _delete(env7, wishlist_id)
        assert response.status_code == 200, response.text
        assert response.json()["retention_days"] == 7
        deleted = env7.client.get("/api/wishlists/deleted", headers=env7.headers(OWNER_ID))
        assert deleted.json()[0]["days_remaining"] == 7


def test_deleted_by_owner_can_be_restored_with_new_links_and_cancelled_reservation(
    env: Env,
) -> None:
    created = _create(env)
    reservation = _reserve(env, _add_item(env, created["id"], "Gift"), purchased=False)

    assert _delete(env, created["id"]).status_code == 200
    restored = env.client.post(
        f"/api/wishlists/{created['id']}/restore-deleted", headers=env.headers(OWNER_ID)
    )

    assert restored.status_code == 200, restored.text
    body = restored.json()
    assert body["status"] == "active"
    assert body["share_token"] != created["share_token"]
    assert body["invite_token"] != created["invite_token"]
    assert len(body["items"]) == 1
    assert created["id"] in _ids(env, "/api/wishlists")
    assert _ids(env, "/api/wishlists/deleted") == []
    assert _reservation_status(env, reservation) == ReservationStatus.CANCELLED


# --- idempotency and repeat (requirement 9) --------------------------------------------------


def test_repeat_delete_is_idempotent_and_does_not_slide_retention_window(
    env: Env, caplog: pytest.LogCaptureFixture
) -> None:
    wishlist_id = _create(env)["id"]
    with caplog.at_level(logging.INFO, logger="wishenka"):
        first = _delete(env, wishlist_id)
        stamp = _row(env.db_path, wishlist_id)
        second = _delete(env, wishlist_id)
        third = _delete(env, wishlist_id)

    assert first.status_code == second.status_code == third.status_code == 200, second.text
    assert first.json() == second.json() == third.json()
    assert _row(env.db_path, wishlist_id) == stamp
    assert _status_changes(caplog, wishlist_id) == ["deleted"]
    assert _ids(env, "/api/wishlists/deleted") == [wishlist_id]


def test_repeat_delete_after_retention_window_is_410_and_changes_nothing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    db_path = tmp_path / "window.db"
    with _open_app(db_path) as first:
        wishlist_id = _create(first)["id"]

        async def delete(service: WishlistService) -> None:
            await service.delete_wishlist(wishlist_id, OWNER)

        _run(first, delete)
    expired = (datetime.now(UTC) - timedelta(days=31)).isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE wl_lists SET updated_at = ? WHERE id = ?", (expired, wishlist_id))
        conn.commit()

    with _open_app(db_path) as second, caplog.at_level(logging.INFO, logger="wishenka"):
        caplog.clear()  # drop the setup delete: create_app() makes the INFO record capturable
        response = _delete(second, wishlist_id)

        assert response.status_code == 410, response.text
        assert response.json()["detail"]["code"] == "retention_expired"
        assert _row(db_path, wishlist_id) == ("deleted", expired)
        assert _status_changes(caplog, wishlist_id) == []


# --- who may delete (requirement 2) ----------------------------------------------------------


@pytest.mark.parametrize("caller", [ADMIN_ID, MEMBER_ID, STRANGER_ID, GIFTER_ID])
def test_non_owner_gets_the_same_404_as_unknown_id_and_nothing_changes(
    env: Env, caller: int
) -> None:
    created = _create(env)
    _share(env, created)
    before = _get(env, created["id"]).json()

    refused = _delete(env, created["id"], caller)
    unknown = _delete(env, UNKNOWN_ID, caller)

    assert refused.status_code == unknown.status_code == 404
    assert refused.content == unknown.content
    assert _get(env, created["id"]).json() == before
    assert _row(env.db_path, created["id"])[0] == "active"


def test_favorite_viewer_gets_the_same_404_as_unknown_id(env: Env) -> None:
    created = _create(env)
    favorite = env.client.post(f"/api/favorites/{created['id']}", headers=env.headers(STRANGER_ID))
    assert favorite.status_code in {200, 201}, favorite.text
    unknown = _delete(env, UNKNOWN_ID, STRANGER_ID)

    refused = _delete(env, created["id"], STRANGER_ID)

    assert refused.status_code == unknown.status_code == 404
    assert refused.content == unknown.content
    assert _row(env.db_path, created["id"])[0] == "active"


def test_unknown_id_is_404_for_owner_too(env: Env) -> None:
    response = _delete(env, UNKNOWN_ID)
    assert response.status_code == 404
    assert response.json() == {"detail": "Wishlist not found"}


def test_anonymous_delete_is_401_and_changes_nothing(env: Env) -> None:
    created = _create(env)

    response = env.client.delete(f"/api/wishlists/{created['id']}")

    assert response.status_code == 401
    assert _row(env.db_path, created["id"])[0] == "active"


@pytest.mark.parametrize("state", ["deleted", "archived"])
def test_non_owner_never_learns_that_a_list_is_deleted_or_archived(env: Env, state: str) -> None:
    created = _create(env)
    _share(env, created)
    unknown = _delete(env, UNKNOWN_ID, ADMIN_ID)

    async def move(service: WishlistService) -> None:
        if state == "deleted":
            await service.delete_wishlist(created["id"], OWNER)
        else:
            await service.archive_wishlist(created["id"], OWNER)

    _run(env, move)

    for caller in (ADMIN_ID, MEMBER_ID, STRANGER_ID):
        response = _delete(env, created["id"], caller)
        assert response.status_code == 404, f"{caller}: {response.status_code} {response.text}"
        assert response.content == unknown.content
    assert _row(env.db_path, created["id"])[0] == state


def test_owner_cannot_delete_archived_list_directly(env: Env) -> None:
    created = _create(env)

    async def archive(service: WishlistService) -> None:
        await service.archive_wishlist(created["id"], OWNER)

    _run(env, archive)

    response = _delete(env, created["id"])

    assert response.status_code == 409, response.text
    assert _row(env.db_path, created["id"])[0] == "archived"


# --- CSRF (cookie session) -------------------------------------------------------------------


def test_cookie_session_delete_requires_origin_and_csrf_token(env: Env) -> None:
    created = _create(env)
    url = f"/api/wishlists/{created['id']}"
    token = env.sessions.create_token(OWNER_ID, "Owner")
    env.client.cookies.set("session_id", token)  # cookie session, no Authorization header

    # The 403 half is a regression guard (the CSRF middleware already runs before routing); the
    # test is red today through the final 200 assertion.
    missing = env.client.delete(url, headers={"Origin": ORIGIN})
    wrong = env.client.delete(url, headers={"Origin": ORIGIN, "X-CSRF-Token": "0" * 64})
    csrf = env.client.get("/api/auth/csrf").json()["csrf_token"]
    foreign = env.client.delete(
        url, headers={"Origin": "http://evil.example", "X-CSRF-Token": csrf}
    )

    assert missing.status_code == wrong.status_code == foreign.status_code == 403
    assert _row(env.db_path, created["id"])[0] == "active"

    accepted = env.client.delete(url, headers={"Origin": ORIGIN, "X-CSRF-Token": csrf})
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "deleted"
    assert _row(env.db_path, created["id"])[0] == "deleted"


# --- surprise secrecy (requirement 8) --------------------------------------------------------


def test_reply_is_identical_for_lists_with_and_without_reservations(env: Env) -> None:
    quiet = _create(env, "Quiet")
    busy = _create(env, "Busy")
    _reserve(env, _add_item(env, busy["id"], "Active gift"), purchased=False)
    _reserve(env, _add_item(env, busy["id"], "Bought gift"), purchased=True)

    quiet_reply = _delete(env, quiet["id"])
    busy_reply = _delete(env, busy["id"])

    assert quiet_reply.status_code == busy_reply.status_code == 200, busy_reply.text
    quiet_body, busy_body = quiet_reply.json(), busy_reply.json()
    assert set(busy_body) == {"status", "wishlist_id", "retention_days"}
    assert {**quiet_body, "wishlist_id": 0} == {**busy_body, "wishlist_id": 0}
    assert "Busy" not in busy_reply.text and "Gift" not in busy_reply.text
    assert not re.search(r"reserv|purchas|bought|member|item", busy_reply.text, re.IGNORECASE)


# --- shell and catalog (design D-2, D-4) -----------------------------------------------------


@pytest.mark.parametrize("retention_days", [30, 7])
def test_miniapp_shell_exposes_the_real_retention_days(tmp_path: Path, retention_days: int) -> None:
    with _open_app(tmp_path / "shell.db", retention_days) as opened:
        html = opened.client.get("/").text

    assert re.search(
        rf'<main id="app"[^>]*\bdata-retention-days="{retention_days}"', html, re.DOTALL
    ), html[-400:]


def _params(text: str) -> set[str]:
    return set(re.findall(r"\{(\w+)\}", text))


def _delete_keys() -> list[str]:
    return [f"miniapp.wishlist_delete.{name}" for name in DELETE_KEYS]


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_delete_keys_exist_in_both_languages_and_reach_the_embedded_catalog(locale: str) -> None:
    missing = [key for key in _delete_keys() if not _table(locale).get(key, "").strip()]
    assert not missing, f"missing {locale} keys: {missing}"
    embedded = miniapp_catalog()["ru" if locale == "ru" else "en"]
    assert [key for key in _delete_keys() if key not in embedded] == []
    for key in _delete_keys():
        assert _params(CATALOG["en"].get(key, "")) == _params(CATALOG["ru"].get(key, "")), key


def test_delete_texts_use_the_expected_placeholders() -> None:
    for locale in ("en", "ru"):
        table = _table(locale)
        title = table.get("miniapp.wishlist_delete.confirm_title", "")
        done = table.get("miniapp.wishlist_delete.done", "")
        assert _params(title) == {"title"}, (locale, title)
        assert _params(done) == {"title", "days"}, (locale, done)
        for name in PROMISE_KEYS:
            promise = table.get(f"miniapp.wishlist_delete.{name}", "")
            assert "days" in _params(promise), (locale, name, promise)


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_delete_texts_never_promise_immediate_removal_and_name_no_count_state_or_person(
    locale: str,
) -> None:
    problems = []
    for name in DELETE_KEYS:
        key = f"miniapp.wishlist_delete.{name}"
        text = _table(locale).get(key, "")
        if not text:
            problems.append(f"{key} is missing")
        if IMMEDIATE.search(text):
            problems.append(f"{key} promises immediate removal: {text!r}")
        if COUNT_STATE_PERSON.search(text):
            problems.append(f"{key} names a count, state or person: {text!r}")
    assert not problems, problems


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_reservation_wording_is_limited_to_two_keys_and_fixed_clauses(locale: str) -> None:
    problems = []
    for name in DELETE_KEYS:
        key = f"miniapp.wishlist_delete.{name}"
        text = _table(locale).get(key, "")
        if not text:
            problems.append(f"{key} is missing")
            continue
        remainder = text.lower()
        if name in RESERVATION_ALLOWED_KEYS:
            for clause in RESERVATION_CLAUSES[locale]:
                remainder = remainder.replace(clause, "")
        if RESERVATION_WORD.search(remainder):
            problems.append(f"{key} has reservation wording outside the fixed clauses: {text!r}")
    consequences = _table(locale).get("miniapp.wishlist_delete.consequences", "").lower()
    assert RESERVATION_CLAUSES[locale][0] in consequences, consequences
    restore = _table(locale).get("miniapp.wishlist_delete.restore_promise", "").lower()
    assert RESERVATION_CLAUSES[locale][1] in restore, restore
    assert not problems, problems


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_confirmation_makes_both_promises_and_names_the_link_consequences(locale: str) -> None:
    table = _table(locale)
    restore = table.get("miniapp.wishlist_delete.restore_promise", "")
    purge = table.get("miniapp.wishlist_delete.purge_promise", "")
    consequences = table.get("miniapp.wishlist_delete.consequences", "")
    deleted_heading = table["miniapp.deleted.heading"]
    assert restore and purge and consequences, "miniapp.wishlist_delete.* texts are missing"
    gifted = "Gifted" if locale == "en" else "Подаренные"
    assert deleted_heading in restore, restore  # restorable from the existing section
    assert gifted in restore and gifted in purge, (restore, purge)
    assert re.search(r"link|ссыл", consequences, re.IGNORECASE), consequences
    assert re.search(r"permanent|окончательно", purge, re.IGNORECASE), purge
    confirm = table.get("miniapp.wishlist_delete.confirm", "")
    assert confirm and confirm != table.get("miniapp.wishlist_delete.cancel", "")
