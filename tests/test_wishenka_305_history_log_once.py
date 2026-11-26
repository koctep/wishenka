"""WISHENKA-305: one log record per viewing-history event.

Counts ``view_history_recorded`` and ``view_history_listed`` across every logger.
``wishenka.wishlists`` writes each success event once. A deleted wishlist refuses
``record_view`` with ``view_history_deleted_wishlist_denied`` and does not emit
``favorite_deleted_wishlist_denied``.
"""

import asyncio
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from wishenka.auth.models import AuthenticatedUser, TelegramUser
from wishenka.auth.session import SessionTokenService
from wishenka.config import Settings
from wishenka.web.app import create_app
from wishenka.wishlists.exceptions import WishlistNotFoundError
from wishenka.wishlists.service import WishlistService

pytestmark = pytest.mark.timeout(30)

_TITLE = "WISHENKA-305 History Title"
_OWNER_ID = 101
_OTHER_ID = 202
_SERVICE_LOGGER = "wishenka.wishlists"


@pytest.fixture
def history_log_app(
    tmp_path: Path,
) -> Iterator[tuple[TestClient, SessionTokenService, FastAPI]]:
    """App whose default history path is RepoWishlistOps."""
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'history_log_once.db'}",
        secret_key="wishenka-305-history-log-once",
    )
    app = create_app(settings)
    sessions = SessionTokenService(settings.secret_key)
    with TestClient(app) as client:
        yield client, sessions, app


def _owner() -> AuthenticatedUser:
    """Owner who may record a view of their own wishlist."""
    return AuthenticatedUser(
        telegram_id=_OWNER_ID,
        first_name="Owner",
        auth_method="session_token",
    )


def _other() -> AuthenticatedUser:
    """Non-owner used for the favorites denial guard."""
    return AuthenticatedUser(
        telegram_id=_OTHER_ID,
        first_name="Other",
        auth_method="session_token",
    )


def _bearer(sessions: SessionTokenService, user_id: int = _OWNER_ID) -> dict[str, str]:
    """Authorization header for a session token."""
    return {"Authorization": f"Bearer {sessions.create_token(user_id, 'User')}"}


def _by_event(records: list[logging.LogRecord], event: str) -> list[logging.LogRecord]:
    """Log records whose structured event name matches, from any logger."""
    return [record for record in records if getattr(record, "event", None) == event]


@contextmanager
def _capture_history_loggers(caplog: pytest.LogCaptureFixture, level: int) -> Iterator[None]:
    """Enable the service logger and the route logger so a duplicate is visible."""
    with (
        caplog.at_level(level, logger=_SERVICE_LOGGER),
        caplog.at_level(level, logger="wishenka.web.wishlists"),
    ):
        yield


def _assert_one_owned_event(
    records: list[logging.LogRecord],
    event: str,
    *,
    title: str,
    user_id: int,
    wishlist_id: int | None = None,
    count: int | None = None,
) -> None:
    """Require a single service-owned record and the fields that record carries."""
    matched = _by_event(records, event)
    for record in matched:
        assert title not in record.getMessage()
        assert getattr(record, "user_id", None) == user_id
        if wishlist_id is not None:
            assert getattr(record, "wishlist_id", None) == wishlist_id
        if count is not None:
            assert getattr(record, "count", None) == count
    names = [record.name for record in matched]
    assert names == [_SERVICE_LOGGER], f"{event} count={len(matched)} loggers={names}"


def _record_and_list(
    client: TestClient,
    sessions: SessionTokenService,
    wishlist_id: int,
    caplog: pytest.LogCaptureFixture,
    *,
    title: str,
) -> None:
    """POST one view and GET history, expecting one owned line for each call."""
    headers = _bearer(sessions)
    caplog.clear()
    with _capture_history_loggers(caplog, logging.INFO):
        recorded = client.post(f"/api/history/{wishlist_id}", headers=headers)
        assert recorded.status_code == 200
    recorded_records = list(caplog.records)

    caplog.clear()
    with _capture_history_loggers(caplog, logging.INFO):
        listed = client.get("/api/history", headers=headers)
        assert listed.status_code == 200
        body = listed.json()
    assert isinstance(body, list)
    assert [item["id"] for item in body] == [wishlist_id]

    failures: list[str] = []
    checks = (
        (
            recorded_records,
            "view_history_recorded",
            {"wishlist_id": wishlist_id},
        ),
        (
            list(caplog.records),
            "view_history_listed",
            {"count": len(body)},
        ),
    )
    for records, event, extra in checks:
        try:
            _assert_one_owned_event(
                records,
                event,
                title=title,
                user_id=_OWNER_ID,
                **extra,
            )
        except AssertionError as exc:
            failures.append(str(exc))
    assert not failures, "; ".join(failures)


def _assert_history_denial_not_favorite(
    records: list[logging.LogRecord],
    *,
    wishlist_id: int,
    user_id: int,
) -> None:
    """Deleted-list history refusal stays the history event, once, on the service logger."""
    denied = _by_event(records, "view_history_deleted_wishlist_denied")
    favorites = _by_event(records, "favorite_deleted_wishlist_denied")
    assert favorites == []
    assert len(denied) == 1
    assert denied[0].name == _SERVICE_LOGGER
    assert getattr(denied[0], "wishlist_id", None) == wishlist_id
    assert getattr(denied[0], "user_id", None) == user_id
    assert _TITLE not in denied[0].getMessage()


def test_in_memory_route_logs_recorded_and_listed_once(
    history_log_app: tuple[TestClient, SessionTokenService, FastAPI],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The repository route emits each success event once, ignoring any injected service."""
    client, sessions, app = history_log_app
    service: WishlistService = app.state.domain_service

    async def seed() -> int:
        await app.state.user_store.upsert_user(TelegramUser(id=_OWNER_ID, first_name="Owner"))
        wishlist = await service.create_wishlist(_owner(), title=_TITLE)
        return wishlist.id

    wishlist_id = asyncio.run(seed())
    _record_and_list(client, sessions, wishlist_id, caplog, title=_TITLE)


def test_sqlite_route_logs_recorded_and_listed_once(
    history_log_app: tuple[TestClient, SessionTokenService, FastAPI],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """RepoWishlistOps must emit each success event once, on the service logger."""
    client, sessions, app = history_log_app
    service: WishlistService = app.state.domain_service

    async def seed() -> int:
        await app.state.user_store.upsert_user(TelegramUser(id=_OWNER_ID, first_name="Owner"))
        wishlist = await service.create_wishlist(_owner(), title=_TITLE)
        return wishlist.id

    wishlist_id = asyncio.run(seed())
    _record_and_list(client, sessions, wishlist_id, caplog, title=_TITLE)


def test_in_memory_route_denies_deleted_wishlist_without_favorite_event(
    history_log_app: tuple[TestClient, SessionTokenService, FastAPI],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A deleted list on the repository path logs the history denial only."""
    client, sessions, app = history_log_app
    service: WishlistService = app.state.domain_service
    owner = _owner()

    async def seed() -> int:
        await app.state.user_store.upsert_user(TelegramUser(id=_OWNER_ID, first_name="Owner"))
        wishlist = await service.create_wishlist(owner, title=_TITLE)
        await service.delete_wishlist(wishlist.id, actor=owner)
        return wishlist.id

    wishlist_id = asyncio.run(seed())
    caplog.clear()
    with _capture_history_loggers(caplog, logging.WARNING):
        response = client.post(f"/api/history/{wishlist_id}", headers=_bearer(sessions))
        assert response.status_code == 404
    _assert_history_denial_not_favorite(
        caplog.records,
        wishlist_id=wishlist_id,
        user_id=_OWNER_ID,
    )


def test_sqlite_route_denies_deleted_wishlist_without_favorite_event(
    history_log_app: tuple[TestClient, SessionTokenService, FastAPI],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """RepoWishlistOps record_view of a deleted list logs the history denial only."""
    client, sessions, app = history_log_app
    service: WishlistService = app.state.domain_service
    owner = _owner()

    async def seed() -> int:
        wishlist = await service.create_wishlist(owner, title=_TITLE)
        await service.delete_wishlist(wishlist.id, actor=owner)
        return wishlist.id

    wishlist_id = asyncio.run(seed())
    caplog.clear()
    with _capture_history_loggers(caplog, logging.WARNING):
        response = client.post(f"/api/history/{wishlist_id}", headers=_bearer(sessions))
        assert response.status_code == 404
    _assert_history_denial_not_favorite(
        caplog.records,
        wishlist_id=wishlist_id,
        user_id=_OWNER_ID,
    )


async def test_in_memory_record_view_fails_closed() -> None:
    """An in-memory service does not apply the viewing-history rule set."""
    service = WishlistService.in_memory()
    with pytest.raises(WishlistNotFoundError, match="repository path"):
        await service.record_view(_owner(), 1)


def test_service_record_view_of_deleted_wishlist_logs_history_denial_only(
    history_log_app: tuple[TestClient, SessionTokenService, FastAPI],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Store-backed record_view keeps the history denial and never the favorites name."""
    _client, _sessions, app = history_log_app
    service: WishlistService = app.state.domain_service
    owner = _owner()

    async def deny() -> int:
        wishlist = await service.create_wishlist(owner, title=_TITLE)
        await service.delete_wishlist(wishlist.id, actor=owner)
        caplog.clear()
        with pytest.raises(WishlistNotFoundError):
            await service.record_view(owner, wishlist.id)
        return wishlist.id

    with _capture_history_loggers(caplog, logging.WARNING):
        wishlist_id = asyncio.run(deny())
    _assert_history_denial_not_favorite(
        caplog.records,
        wishlist_id=wishlist_id,
        user_id=_OWNER_ID,
    )


def test_service_add_favorite_of_deleted_wishlist_logs_favorite_denial_once(
    history_log_app: tuple[TestClient, SessionTokenService, FastAPI],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Store-backed add_favorite remains the only writer of favorite_deleted_wishlist_denied."""
    _client, _sessions, app = history_log_app
    service: WishlistService = app.state.domain_service
    owner = _owner()

    async def deny() -> int:
        wishlist = await service.create_wishlist(owner, title=_TITLE)
        await service.delete_wishlist(wishlist.id, actor=owner)
        caplog.clear()
        with pytest.raises(WishlistNotFoundError):
            await service.add_favorite(_other(), wishlist.id)
        return wishlist.id

    with _capture_history_loggers(caplog, logging.WARNING):
        wishlist_id = asyncio.run(deny())
    denied = _by_event(caplog.records, "favorite_deleted_wishlist_denied")
    history = _by_event(caplog.records, "view_history_deleted_wishlist_denied")
    assert history == []
    assert len(denied) == 1
    assert denied[0].name == _SERVICE_LOGGER
    assert getattr(denied[0], "wishlist_id", None) == wishlist_id
    assert getattr(denied[0], "user_id", None) == _OTHER_ID
    assert _TITLE not in denied[0].getMessage()
