"""One wishlist name rule on create and on edit.

Missing, blank, and invisible-only names are ``wishlist_name_required``. A name over 255 code
points is ``wishlist_name_too_long``. Description and event title stay uncapped, and blank means
unset. Domain ``create_wishlist`` still accepts any stored title, and that is how an empty or
already too-long row is seeded.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from wishenka.auth.models import AuthenticatedUser
from wishenka.auth.session import SessionTokenService
from wishenka.config import Settings
from wishenka.web.app import create_app

pytestmark = pytest.mark.timeout(30)

OWNER_ID = 101
NAME_MAX = 255
REQUIRED = "wishlist_name_required"
TOO_LONG = "wishlist_name_too_long"
WHEN = datetime(2030, 5, 1, 10, 0, tzinfo=UTC)
DETAIL_KEYS = ("name", "description", "event_title", "event_date")
ZWSP = "\u200b"
WORD_JOINER = "\u2060"
BOM = "\ufeff"
LRM = "\u200e"
RLM = "\u200f"
INVISIBLE = (
    ("zwsp", ZWSP),
    ("word-joiner", WORD_JOINER),
    ("bom", BOM),
    ("lrm", LRM),
    ("rlm", RLM),
    ("marks-and-spaces", f" {ZWSP} {WORD_JOINER} {BOM} {LRM} {RLM} "),
    ("bom-between-spaces", f"{BOM}   {BOM}"),
    ("marks-with-inner-spaces", f"{LRM} {RLM} {ZWSP}"),
    ("zwsp-256", ZWSP * (NAME_MAX + 1)),
)
KEPT_MARKS = (
    (f"{BOM}Cafe", f"{BOM}Cafe"),
    (f"Cafe{BOM}", f"Cafe{BOM}"),
    (f"  {BOM}Hi{ZWSP}  ", f"{BOM}Hi{ZWSP}"),
    (f"A{WORD_JOINER}B", f"A{WORD_JOINER}B"),
)
TOO_LONG_NAMES = (
    ("256-letters", "a" * (NAME_MAX + 1)),
    ("256-emoji", "\U0001f381" * (NAME_MAX + 1)),
    ("256-after-edge-spaces", " " * 3 + "b" * (NAME_MAX + 1) + " " * 3),
)


@dataclass
class Env:
    """Running app with a bearer header of the owner."""

    client: TestClient
    owner: dict[str, str]

    def lists(self) -> list[dict[str, Any]]:
        response = self.client.get("/api/wishlists", headers=self.owner)
        assert response.status_code == 200, response.text
        data = response.json()
        assert isinstance(data, list)
        return data

    def create(self, payload: Any) -> Any:
        return self.client.post("/api/wishlists", json=payload, headers=self.owner)

    def patch(self, wishlist_id: int, payload: dict[str, Any]) -> Any:
        return self.client.patch(f"/api/wishlists/{wishlist_id}", json=payload, headers=self.owner)

    def read(self, wishlist_id: int) -> dict[str, Any]:
        response = self.client.get(f"/api/wishlists/{wishlist_id}", headers=self.owner)
        assert response.status_code == 200, response.text
        body = response.json()
        assert isinstance(body, dict)
        return body


@pytest.fixture
def env(tmp_path: Path) -> Iterator[Env]:
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'name-contract.db'}",
        secret_key="secret",
    )
    sessions = SessionTokenService(settings.secret_key)
    owner = {"Authorization": f"Bearer {sessions.create_token(OWNER_ID, 'Owner')}"}
    with TestClient(create_app(settings)) as client:
        yield Env(client, owner)


def _assert_name_error(response: Any, expected: str, label: str) -> None:
    assert response.status_code == 422, (
        f"{label} must be 422 {expected}, got {response.status_code}"
    )
    detail = response.json()["detail"]
    assert isinstance(detail, list) and detail, detail
    item = detail[0]
    assert item["loc"][-1] == "name", item
    assert item["type"] == expected, item
    other = REQUIRED if expected == TOO_LONG else TOO_LONG
    assert item["type"] != other, item
    if expected == TOO_LONG:
        assert (item.get("ctx") or {}).get("max_length") == NAME_MAX, item


def _snapshot(body: dict[str, Any]) -> dict[str, Any]:
    return {key: body[key] for key in DETAIL_KEYS}


def _create_named(env: Env, name: str = "Seed") -> dict[str, Any]:
    response = env.create(
        {
            "name": name,
            "description": "Old",
            "event_title": "Party",
            "event_date": "2030-05-01T10:00:00Z",
        }
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert isinstance(body, dict)
    assert body["name"] == name
    return cast(dict[str, Any], body)


def _seed(env: Env, title: str) -> int:
    """Persist ``title`` through the domain service. HTTP create cannot store these titles."""
    app = cast(FastAPI, env.client.app)

    async def create() -> int:
        owner = AuthenticatedUser(
            telegram_id=OWNER_ID, first_name="Owner", auth_method="session_token"
        )
        wishlist = await app.state.domain_service.create_wishlist(
            owner=owner,
            title=title,
            description="Kept",
            event_title="Party",
            event_date=WHEN,
        )
        return int(wishlist.id)

    portal = getattr(env.client, "portal", None)
    assert portal is not None, "TestClient portal is required to seed on the app loop"
    return int(portal.call(create))


def _reject_patch(env: Env, wishlist_id: int, payload: dict[str, Any], expected: str) -> None:
    before = _snapshot(env.read(wishlist_id))
    response = env.patch(wishlist_id, payload)
    _assert_name_error(response, expected, f"PATCH {payload!r}")
    assert _snapshot(env.read(wishlist_id)) == before


# --- missing name -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "payload"),
    [
        ("absent", {}),
        ("null", {"name": None}),
        ("empty", {"name": ""}),
        ("spaces", {"name": "   "}),
        ("whitespace", {"name": "\t\n "}),
        ("other-fields", {"description": "only", "event_title": "Party"}),
    ],
)
def test_post_missing_blank_or_null_name_is_required(
    env: Env, label: str, payload: dict[str, Any]
) -> None:
    before = len(env.lists())
    _assert_name_error(env.create(payload), REQUIRED, f"POST {label}")
    assert len(env.lists()) == before


@pytest.mark.parametrize(
    ("label", "name"),
    [("null", None), ("empty", ""), ("spaces", "   "), ("whitespace", "\t\n ")],
)
def test_patch_null_blank_or_spaces_name_is_required(
    env: Env, label: str, name: str | None
) -> None:
    created = _create_named(env)
    _reject_patch(env, int(created["id"]), {"name": name}, REQUIRED)


def test_omitted_name_on_a_valid_title_still_updates_the_description(env: Env) -> None:
    """A stored name that already passes may change its description without restating the name."""
    created = _create_named(env)
    response = env.patch(int(created["id"]), {"description": "Updated"})
    assert response.status_code == 200, response.status_code
    body = response.json()
    assert body["name"] == "Seed"
    assert body["description"] == "Updated"


# --- invisible-only name ----------------------------------------------------------------------


@pytest.mark.parametrize(("label", "name"), INVISIBLE)
def test_post_invisible_only_name_is_required(env: Env, label: str, name: str) -> None:
    before = len(env.lists())
    _assert_name_error(env.create({"name": name}), REQUIRED, f"POST {label}")
    assert len(env.lists()) == before


@pytest.mark.parametrize(("label", "name"), INVISIBLE)
def test_patch_invisible_only_name_is_required(env: Env, label: str, name: str) -> None:
    created = _create_named(env)
    _reject_patch(env, int(created["id"]), {"name": name}, REQUIRED)


@pytest.mark.parametrize(("raw", "stored"), KEPT_MARKS)
def test_post_keeps_invisible_marks_beside_a_visible_character(
    env: Env, raw: str, stored: str
) -> None:
    response = env.create({"name": raw})
    assert response.status_code == 201, response.text
    assert response.json()["name"] == stored
    assert env.read(int(response.json()["id"]))["name"] == stored


@pytest.mark.parametrize(("raw", "stored"), KEPT_MARKS)
def test_patch_keeps_invisible_marks_beside_a_visible_character(
    env: Env, raw: str, stored: str
) -> None:
    created = _create_named(env)
    response = env.patch(int(created["id"]), {"name": raw})
    assert response.status_code == 200, response.status_code
    assert response.json()["name"] == stored
    assert env.read(int(created["id"]))["name"] == stored


# --- too long, distinct from missing ----------------------------------------------------------


@pytest.mark.parametrize(("label", "name"), TOO_LONG_NAMES)
def test_post_name_over_255_code_points_is_too_long(env: Env, label: str, name: str) -> None:
    before = len(env.lists())
    response = env.create({"name": name})
    _assert_name_error(response, TOO_LONG, f"POST {label}")
    assert REQUIRED not in response.text
    assert len(env.lists()) == before


@pytest.mark.parametrize(("label", "name"), TOO_LONG_NAMES)
def test_patch_name_over_255_code_points_is_too_long(env: Env, label: str, name: str) -> None:
    created = _create_named(env)
    _reject_patch(env, int(created["id"]), {"name": name}, TOO_LONG)


# --- description and event title stay uncapped ------------------------------------------------


def _assert_no_length_ceiling(schema: dict[str, Any]) -> None:
    if "maxLength" in schema or "minLength" in schema:
        raise AssertionError(schema)
    for value in schema.values():
        if isinstance(value, dict):
            _assert_no_length_ceiling(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    _assert_no_length_ceiling(item)


def test_description_and_event_title_schema_have_no_length_ceiling(env: Env) -> None:
    """No numeric ceiling is part of this contract. A later maxLength fails this check."""
    response = env.client.get("/openapi.json")
    assert response.status_code == 200, response.status_code
    schemas = response.json()["components"]["schemas"]
    for model in ("WishlistCreateInput", "WishlistInput"):
        properties = schemas[model]["properties"]
        for field in ("description", "event_title"):
            _assert_no_length_ceiling(properties[field])


def test_description_and_event_title_longer_than_the_name_are_stored(env: Env) -> None:
    description = "d" * (NAME_MAX + 1)
    event_title = "e" * (NAME_MAX + 1)
    created = env.create({"name": "Named", "description": description, "event_title": event_title})
    assert created.status_code == 201, created.text
    assert "string_too_long" not in created.text
    assert created.json()["description"] == description
    assert created.json()["event_title"] == event_title
    edited = env.patch(
        int(created.json()["id"]),
        {"description": description + "d", "event_title": event_title + "e"},
    )
    assert edited.status_code == 200, edited.status_code
    assert "string_too_long" not in edited.text
    assert edited.json()["description"] == description + "d"
    assert edited.json()["event_title"] == event_title + "e"
    assert edited.json()["name"] == "Named"


@pytest.mark.parametrize(
    ("description", "event_title"),
    [("", ""), ("   ", "   "), ("\t\n", " \t "), (None, None)],
    ids=["empty", "spaces", "whitespace", "null"],
)
def test_blank_description_and_event_title_are_unset(
    env: Env, description: str | None, event_title: str | None
) -> None:
    created = env.create({"name": "Named", "description": description, "event_title": event_title})
    assert created.status_code == 201, created.text
    assert created.json()["description"] is None
    assert created.json()["event_title"] is None
    edited = env.patch(
        int(created.json()["id"]),
        {"description": description, "event_title": event_title},
    )
    assert edited.status_code == 200, edited.status_code
    assert edited.json()["name"] == "Named"
    assert edited.json()["description"] is None
    assert edited.json()["event_title"] is None


# --- stored titles the HTTP create cannot produce ---------------------------------------------


def test_stored_empty_name_stays_readable_and_blocks_a_detail_only_save(env: Env) -> None:
    wishlist_id = _seed(env, "")
    assert env.read(wishlist_id)["name"] == ""
    _reject_patch(env, wishlist_id, {"description": "note"}, REQUIRED)
    _reject_patch(env, wishlist_id, {"event_title": "Later"}, REQUIRED)
    assert env.read(wishlist_id)["name"] == ""


@pytest.mark.parametrize(
    "name",
    ["", "   ", None, ZWSP, BOM, f" {WORD_JOINER} {LRM} "],
    ids=["empty", "spaces", "null", "zwsp", "bom", "mix"],
)
def test_stored_empty_name_rejects_a_blank_or_invisible_name(env: Env, name: str | None) -> None:
    wishlist_id = _seed(env, "")
    _reject_patch(env, wishlist_id, {"name": name}, REQUIRED)
    assert env.read(wishlist_id)["name"] == ""


def test_stored_empty_name_accepts_a_real_name(env: Env) -> None:
    wishlist_id = _seed(env, "")
    response = env.patch(wishlist_id, {"name": "Real"})
    assert response.status_code == 200, response.status_code
    assert response.json()["name"] == "Real"
    assert env.read(wishlist_id)["name"] == "Real"


def test_stored_too_long_name_blocks_a_detail_only_save(env: Env) -> None:
    title = "L" * (NAME_MAX + 1)
    wishlist_id = _seed(env, title)
    assert env.read(wishlist_id)["name"] == title
    _reject_patch(env, wishlist_id, {"description": "note"}, TOO_LONG)
    _reject_patch(env, wishlist_id, {"event_title": "Later"}, TOO_LONG)
    assert env.read(wishlist_id)["name"] == title


def test_stored_too_long_name_classifies_a_sent_name(env: Env) -> None:
    title = "L" * (NAME_MAX + 1)
    wishlist_id = _seed(env, title)
    _reject_patch(env, wishlist_id, {"name": None}, REQUIRED)
    _reject_patch(env, wishlist_id, {"name": ""}, REQUIRED)
    _reject_patch(env, wishlist_id, {"name": "   "}, REQUIRED)
    _reject_patch(env, wishlist_id, {"name": f" {BOM}{ZWSP} "}, REQUIRED)
    _reject_patch(env, wishlist_id, {"name": "z" * (NAME_MAX + 1)}, TOO_LONG)
    assert env.read(wishlist_id)["name"] == title
    response = env.patch(wishlist_id, {"name": "Real"})
    assert response.status_code == 200, response.status_code
    assert env.read(wishlist_id)["name"] == "Real"


def test_post_long_invisible_run_is_not_reported_as_too_long(env: Env) -> None:
    name = BOM * (NAME_MAX + 1)
    response = env.create({"name": name})
    _assert_name_error(response, REQUIRED, "POST bom-256")
    assert response.json()["detail"][0]["type"] != TOO_LONG
