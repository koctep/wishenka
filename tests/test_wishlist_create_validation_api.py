"""Create-wishlist validation, plus the shared name rule on edit.

A create still requires a trimmed name of 1 to 255 characters. A rejected create leaves no row
and no title in the logs. PATCH uses that same name rule: a blank or over-long name is refused,
and omitting the name keeps a valid stored title.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from wishenka.auth.session import SessionTokenService
from wishenka.config import Settings
from wishenka.web.app import create_app

pytestmark = pytest.mark.timeout(30)

OWNER_ID = 101
MAX_TITLE = 255
SECRET_TITLE = "Zq-secret-title-marker"


@dataclass
class Env:
    """Running app with a bearer header of the owner."""

    client: TestClient
    owner: dict[str, str]

    def lists(self) -> list[dict[str, Any]]:
        response = self.client.get("/api/wishlists", headers=self.owner)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        return data

    def create(self, payload: Any) -> Any:
        return self.client.post("/api/wishlists", json=payload, headers=self.owner)


@pytest.fixture
def env(tmp_path: Path) -> Iterator[Env]:
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'create-validation.db'}",
        secret_key="secret",
    )
    sessions = SessionTokenService(settings.secret_key)
    owner = {"Authorization": f"Bearer {sessions.create_token(OWNER_ID, 'Owner')}"}
    with TestClient(create_app(settings)) as client:
        yield Env(client, owner)


def _assert_title_rejected(env: Env, payload: Any) -> None:
    before = len(env.lists())
    response = env.create(payload)
    assert response.status_code == 422, (
        f"POST /api/wishlists {str(payload)[:40]!r} must be 422, got {response.status_code}"
    )
    detail = response.json()["detail"]
    assert detail[0]["loc"] == ["body", "name"], detail
    assert len(env.lists()) == before, "a rejected request must create no row"


# --- title is required and validated ----------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"name": None},
        {"name": ""},
        {"name": "   "},
        {"name": "\t\n "},
        {"name": "a" * (MAX_TITLE + 1)},
        {"name": " " + "a" * MAX_TITLE + "b"},
        {"name": 123},
        {"name": ["x"]},
        {"description": "only a description", "event_title": "Party"},
    ],
    ids=[
        "empty-object",
        "null",
        "empty",
        "spaces",
        "whitespace-kinds",
        "256-chars",
        "256-after-trim",
        "number",
        "list",
        "optional-fields-without-name",
    ],
)
def test_missing_blank_or_invalid_title_is_rejected_without_creating_a_list(
    env: Env, payload: Any
) -> None:
    _assert_title_rejected(env, payload)


def test_rejections_in_a_row_leave_the_account_empty(env: Env) -> None:
    for payload in ({}, {"name": ""}, {"name": "  "}, {"name": None}):
        assert env.create(payload).status_code == 422
    assert env.lists() == []


def test_title_of_exactly_255_characters_is_accepted(env: Env) -> None:
    title = "a" * MAX_TITLE
    response = env.create({"name": title})
    assert response.status_code == 201
    assert response.json()["name"] == title
    assert [item["name"] for item in env.lists()] == [title]


def test_title_is_counted_in_code_points_not_utf16_units(env: Env) -> None:
    """255 astral characters are 510 UTF-16 units but 255 code points: allowed."""
    title = "\U0001f381" * MAX_TITLE
    assert env.create({"name": title}).status_code == 201
    _assert_title_rejected(env, {"name": title + "\U0001f381"})


def test_title_is_trimmed_before_it_is_stored(env: Env) -> None:
    response = env.create({"name": "  Birthday  "})
    assert response.status_code == 201
    assert response.json()["name"] == "Birthday"
    fetched = env.client.get(f"/api/wishlists/{response.json()['id']}", headers=env.owner).json()
    assert fetched["name"] == "Birthday"
    assert [item["name"] for item in env.lists()] == ["Birthday"]


def test_trimmed_length_decides_the_limit_not_the_raw_length(env: Env) -> None:
    padded = " " * 5 + "a" * MAX_TITLE + " " * 5
    response = env.create({"name": padded})
    assert response.status_code == 201
    assert response.json()["name"] == "a" * MAX_TITLE


def test_422_detail_has_the_default_fastapi_shape(env: Env) -> None:
    detail = env.create({}).json()["detail"]
    assert isinstance(detail, list) and detail
    assert detail[0]["loc"] == ["body", "name"]
    assert {"msg", "type"} <= set(detail[0])


# --- valid creation is unchanged ---------------------------------------------------------------


def test_valid_creation_still_returns_the_owner_projection(env: Env) -> None:
    response = env.create(
        {
            "name": "Birthday",
            "description": "Party",
            "event_title": "Turns 30",
            "event_date": "2030-05-01T10:00:00Z",
        }
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Birthday"
    assert body["description"] == "Party"
    assert body["event_title"] == "Turns 30"
    assert body["role"] == "owner"
    assert body["status"] == "active"
    assert body["share_token"] and body["invite_token"]
    assert body["items"] == []
    assert [item["id"] for item in env.lists()] == [body["id"]]


def test_optional_fields_may_be_omitted_or_null(env: Env) -> None:
    response = env.create(
        {"name": "Plain", "description": None, "event_title": None, "event_date": None}
    )
    assert response.status_code == 201
    assert env.create({"name": "Plain 2"}).status_code == 201


def test_unparseable_event_date_is_rejected_and_creates_nothing(env: Env) -> None:
    before = len(env.lists())
    response = env.create({"name": "Dated", "event_date": "not-a-date"})
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "event_date"]
    assert len(env.lists()) == before


def test_unauthenticated_empty_body_is_still_401(env: Env) -> None:
    """Regression guard: authentication runs before body validation."""
    assert env.client.post("/api/wishlists", json={}).status_code == 401
    assert env.client.post("/api/wishlists", json={"name": "x"}).status_code == 401


def test_cookie_session_without_csrf_token_is_rejected_and_creates_nothing(env: Env) -> None:
    """Regression guard: CSRF protection of cookie sessions is unchanged (403, no row)."""
    token = env.owner["Authorization"].removeprefix("Bearer ")
    cookie_client = env.client
    cookie_client.cookies.set("session_id", token)
    origin = {"Origin": "http://testserver"}
    response = cookie_client.post("/api/wishlists", json={"name": "x"}, headers=origin)
    assert response.status_code == 403
    assert env.lists() == []


# --- PATCH shares the name contract -----------------------------------------------------------


def test_patch_keeps_a_valid_name_when_omitted_and_refuses_blank_or_long(env: Env) -> None:
    """Omitting the name keeps a valid title. A blank or over-long name is refused."""
    created = env.create({"name": "Seed"})
    assert created.status_code == 201, "a valid creation must work (precondition)"
    path = f"/api/wishlists/{created.json()['id']}"

    absent = env.client.patch(path, json={"description": "new"}, headers=env.owner)
    assert absent.status_code == 200
    assert absent.json()["name"] == "Seed"
    assert absent.json()["description"] == "new"

    empty = env.client.patch(path, json={}, headers=env.owner)
    assert empty.status_code == 200
    assert empty.json()["name"] == "Seed"

    blank = env.client.patch(path, json={"name": ""}, headers=env.owner)
    assert blank.status_code == 422
    assert blank.json()["detail"][0]["type"] == "wishlist_name_required"
    assert blank.json()["detail"][0]["loc"][-1] == "name"
    assert env.client.get(path, headers=env.owner).json()["name"] == "Seed"

    long_name = env.client.patch(path, json={"name": "b" * 300}, headers=env.owner)
    assert long_name.status_code == 422
    assert long_name.json()["detail"][0]["type"] == "wishlist_name_too_long"
    assert env.client.get(path, headers=env.owner).json()["name"] == "Seed"


# --- observability -----------------------------------------------------------------------------


def _committed_creations(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "wishlist_mutation_committed"
        and getattr(record, "operation", None) == "create_wishlist"
    ]


def test_committed_creation_signal_fires_once_per_valid_request_only(
    env: Env, caplog: pytest.LogCaptureFixture
) -> None:
    """Single-fire signal ``wishlist_mutation_committed`` counts confirmed creations only."""
    with caplog.at_level(logging.INFO, logger="wishenka.web.wishlists"):
        assert env.create({}).status_code == 422
        assert env.create({"name": " "}).status_code == 422
        assert len(_committed_creations(caplog)) == 0
        assert env.create({"name": "One"}).status_code == 201
        assert len(_committed_creations(caplog)) == 1
        assert env.create({"name": "Two"}).status_code == 201
        assert len(_committed_creations(caplog)) == 2


def test_rejected_creation_logs_neither_title_nor_text(
    env: Env, caplog: pytest.LogCaptureFixture
) -> None:
    too_long = SECRET_TITLE + "x" * MAX_TITLE
    with caplog.at_level(logging.DEBUG):
        response = env.create({"name": too_long, "description": "secret-description"})
    assert response.status_code == 422, "a 256+ character title must be rejected"
    assert not _committed_creations(caplog)
    for record in caplog.records:
        rendered = f"{record.getMessage()} {record.__dict__}"
        assert SECRET_TITLE not in rendered, record.name
        assert "secret-description" not in rendered, record.name


def test_successful_creation_logs_no_user_text(env: Env, caplog: pytest.LogCaptureFixture) -> None:
    """Guard for Step 6: records of a 201 never carry the title or description."""
    with caplog.at_level(logging.DEBUG):
        response = env.create({"name": SECRET_TITLE, "description": "secret-description"})
    assert response.status_code == 201
    assert len(_committed_creations(caplog)) == 1
    for record in caplog.records:
        if not record.name.startswith("wishenka."):
            continue
        rendered = f"{record.getMessage()} {record.__dict__}"
        assert SECRET_TITLE not in rendered, record.name
        assert "secret-description" not in rendered, record.name
