"""Pin production logs of wishlist creation (WISHENKA-296, Step 6, D-7).

Every path of ``POST /api/wishlists`` must leave a diagnosable server-side signal without logging
the title, description, event name or tokens. A validation rejection (422) has no dedicated event
by design: it shows up only in the request-completed line.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from wishenka.auth.session import SessionTokenService
from wishenka.config import Settings
from wishenka.logging import JsonFormatter
from wishenka.web.app import create_app
from wishenka.wishlists.service import WishlistService

pytestmark = pytest.mark.timeout(30)

OWNER_ID = 101
TITLE = "Zz Sécret <Títle> 'Qq' 🎁"
DESCRIPTION = "ZzSecretDescriptionQq"
EVENT = "ZzSecretEventQq"
EVENT_DATE = "2031-05-17T10:00:00"
SECRETS = [TITLE, DESCRIPTION, EVENT]
CREATE_EVENTS = {"wishlist_created", "wishlist_mutation_committed"}


@dataclass
class Env:
    client: TestClient
    owner: dict[str, str]
    session_token: str


@pytest.fixture
def env(tmp_path: Path) -> Iterator[Env]:
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'create-observability.db'}",
        secret_key="secret",
    )
    token = SessionTokenService(settings.secret_key).create_token(OWNER_ID, "Owner")
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        yield Env(client, {"Authorization": f"Bearer {token}"}, token)


def _post(env: Env, payload: Any) -> Any:
    return env.client.post("/api/wishlists", json=payload, headers=env.owner)


def _named(caplog: pytest.LogCaptureFixture, event: str) -> list[logging.LogRecord]:
    return [r for r in caplog.records if getattr(r, "event", None) == event]


def _assert_no_leak(caplog: pytest.LogCaptureFixture, *extra_secrets: str) -> None:
    """Nothing user-typed or secret in any record: message, args, extras, JSON line."""
    assert caplog.records, "the path must log something"
    formatter = JsonFormatter()
    secrets = [*SECRETS, *extra_secrets]
    for record in caplog.records:
        line = formatter.format(record)
        json.loads(line)
        parsed = json.dumps(json.loads(line), ensure_ascii=False)
        rendered = f"{record.getMessage()} {record.args!r} {line} {parsed} {vars(record)}"
        for secret in secrets:
            assert secret not in rendered, f"{record.getMessage()!r} leaks {secret!r}"
        assert not ({"title", "description", "event_title"} & set(vars(record)))
        extra = json.loads(line).get("extra", {})
        assert not ({"title", "name", "description", "event_title"} & set(extra))


def _creation_events(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if getattr(r, "event", None) in CREATE_EVENTS]


def _completed(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.getMessage().startswith("HTTP request completed")]


def test_success_logs_one_commit_and_two_created_records_with_ids_only(
    env: Env, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG, logger="wishenka"):
        caplog.clear()
        response = _post(
            env,
            {
                "name": f"  {TITLE}  ",
                "description": DESCRIPTION,
                "event_title": EVENT,
                "event_date": EVENT_DATE,
            },
        )

    assert response.status_code == 201
    wishlist_id = response.json()["id"]
    committed = _named(caplog, "wishlist_mutation_committed")
    assert [r.__dict__["operation"] for r in committed] == ["create_wishlist"]
    created = _named(caplog, "wishlist_created")
    assert len(created) == 2
    assert {r.name for r in created} >= {"wishenka.web.wishlists"}
    assert len({r.name for r in created}) == 2
    route_record = next(r for r in created if r.name == "wishenka.web.wishlists")
    assert route_record.levelno == logging.INFO
    assert route_record.__dict__["wishlist_id"] == wishlist_id
    assert route_record.__dict__["user_id"] == OWNER_ID
    service_record = next(r for r in created if r.name != "wishenka.web.wishlists")
    assert service_record.__dict__["owner_id"] == OWNER_ID
    # Pre-existing behaviour: the service record carries the user-entered date, the format and
    # the time type, but never the title, description or event title.
    assert service_record.__dict__["event_date"].startswith("2031-05-17")
    assert {"format", "time_type"} <= set(vars(service_record))
    assert "event_date" not in vars(route_record)
    assert all(r.levelno < logging.WARNING for r in _creation_events(caplog))
    done = _completed(caplog)
    assert [r.__dict__["status_code"] for r in done] == [201]
    _assert_no_leak(caplog)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"name": None},
        {"name": "   "},
        {"name": "x" * 256, "description": DESCRIPTION, "event_title": EVENT},
        {"name": 12345},
        {"name": [TITLE]},
    ],
)
def test_validation_rejection_has_no_dedicated_event_and_no_user_text(
    env: Env, caplog: pytest.LogCaptureFixture, payload: dict[str, Any]
) -> None:
    with caplog.at_level(logging.DEBUG, logger="wishenka"):
        caplog.clear()
        response = _post(env, payload)

    assert response.status_code == 422
    assert not _creation_events(caplog)
    assert not _named(caplog, "wishlist_create_rejected")
    assert [r.__dict__["status_code"] for r in _completed(caplog)] == [422]
    assert all(r.levelno < logging.WARNING for r in caplog.records)
    _assert_no_leak(caplog, "x" * 256)


def test_rejection_with_secret_text_in_other_fields_logs_none_of_it(
    env: Env, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG, logger="wishenka"):
        caplog.clear()
        response = _post(env, {"name": " ", "description": DESCRIPTION, "event_title": EVENT})

    assert response.status_code == 422
    assert not _creation_events(caplog)
    _assert_no_leak(caplog)


def test_unauthenticated_request_logs_no_creation_event_and_no_text(
    env: Env, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG, logger="wishenka"):
        caplog.clear()
        response = env.client.post(
            "/api/wishlists", json={"name": TITLE, "description": DESCRIPTION}
        )

    assert response.status_code == 401
    assert not _creation_events(caplog)
    assert [r.__dict__["status_code"] for r in _completed(caplog)] == [401]
    _assert_no_leak(caplog)


def test_csrf_rejection_warns_with_path_only_and_no_text(
    env: Env, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG, logger="wishenka"):
        caplog.clear()
        env.client.cookies.set("wishenka_session", env.session_token)
        response = env.client.post(
            "/api/wishlists",
            json={"name": TITLE, "description": DESCRIPTION, "event_title": EVENT},
        )

    assert response.status_code == 403
    assert not _creation_events(caplog)
    rejected = _named(caplog, "csrf_origin_mismatch")
    assert len(rejected) == 1
    assert rejected[0].levelno == logging.WARNING
    assert rejected[0].__dict__["path"] == "/api/wishlists"
    _assert_no_leak(caplog, env.session_token)


def test_unexpected_error_is_logged_by_request_middleware_without_text(
    env: Env, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom(self: WishlistService, *args: object, **kwargs: object) -> None:
        raise RuntimeError("storage failure")

    monkeypatch.setattr(WishlistService, "create_wishlist", boom)

    with caplog.at_level(logging.DEBUG, logger="wishenka"):
        caplog.clear()
        response = _post(env, {"name": TITLE, "description": DESCRIPTION, "event_title": EVENT})

    assert response.status_code == 500
    failed = [r for r in caplog.records if "unhandled exception" in r.getMessage()]
    assert len(failed) == 1
    assert failed[0].levelno == logging.ERROR
    assert failed[0].__dict__["path"] == "/api/wishlists"
    assert not _creation_events(caplog)
    assert not _named(caplog, "wishlist_created")
    # The exception text of the failure itself is the only thing allowed in exc_text.
    _assert_no_leak(caplog)
    assert any(r.exc_info for r in failed)
    formatter = JsonFormatter()
    for record in failed:
        line = json.dumps(json.loads(formatter.format(record)), ensure_ascii=False)
        assert record.exc_text is None or not any(s in record.exc_text for s in SECRETS)
        for secret in SECRETS:
            assert secret not in line
