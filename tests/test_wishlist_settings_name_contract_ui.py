"""Settings-form name contract for WISHENKA-320, in the Node harness.

The same decision runs on edit, in English and Russian. An invisible-only, blank, or too-long
name is not saved. An accepted name is the normalized string, including an edge U+FEFF.
Description and event title have no maxlength.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Literal, cast

import pytest

from tests.test_wishlist_create_form_ui import HARNESS as CREATE_HARNESS
from tests.test_wishlist_create_form_ui import _attr, _field, _text
from wishenka.i18n import CATALOG

pytestmark = pytest.mark.timeout(20)

MAX_TITLE = 255
BOM = "\ufeff"
ZWSP = "\u200b"


def _settings_harness() -> str:
    anchor = (
        "  } else if (scenario.action === 'create_flow') {\n"
        "    await sandbox.showHome();\n"
        "    await runSteps(out);\n"
    )
    added = (
        "  } else if (scenario.action === 'settings_flow') {\n"
        "    await sandbox.showList(1);\n"
        "    await runSteps(out);\n"
    )
    assert CREATE_HARNESS.count(anchor) == 1, "create harness no longer exposes create_flow"
    return CREATE_HARNESS.replace(anchor, anchor + added, 1)


HARNESS = _settings_harness()


def _detail(**changes: Any) -> dict[str, Any]:
    detail = {
        "id": 1,
        "name": "Seed",
        "description": "Old",
        "event_title": "Party",
        "event_date": None,
        "status": "active",
        "role": "owner",
        "share_token": "share_tok",
        "invite_token": "inv_tok",
        "members": [],
        "items": [],
    }
    detail.update(changes)
    return detail


def _run(
    locale: str,
    steps: list[dict[str, Any]],
    *,
    name: str = "Seed",
) -> dict[str, Any]:
    scenario: dict[str, Any] = {
        "action": "settings_flow",
        "datasetLocale": locale,
        "wishlistDetail": _detail(name=name),
        "wishlists": [],
        "steps": steps,
    }
    payload = {
        "jsSource": Path("wishenka/web/static/miniapp.js").read_text(encoding="utf-8"),
        "i18nJson": json.dumps(CATALOG),
        "scenario": scenario,
    }
    process = subprocess.run(
        [shutil.which("node") or "node", "-e", HARNESS],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert process.returncode == 0, process.stderr
    result = cast(dict[str, Any], json.loads(process.stdout))
    assert result["stepExceptions"] == [], result["stepExceptions"]
    assert result["stepErrors"] == [], result["stepErrors"]
    return result


def _patches(result: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        call
        for call in result["fetchCalls"]
        if call["method"] == "PATCH" and str(call["url"]).startswith("/api/wishlists/")
    ]


def _fill(field: str, value: str) -> dict[str, Any]:
    return {"op": "fill", "field": field, "value": value}


SUBMIT: dict[str, Any] = {"op": "submit"}


def _required(locale: str) -> str:
    return _text(locale, "miniapp.create.error_title_required")


def _too_long(locale: str) -> str:
    return _text(locale, "miniapp.create.error_title_too_long").replace("{max}", str(MAX_TITLE))


@pytest.mark.parametrize("locale", ["en", "ru"])
@pytest.mark.parametrize(
    ("label", "title", "message"),
    [
        ("empty", "", "required"),
        ("spaces", "   ", "required"),
        ("zwsp", ZWSP, "required"),
        ("bom", BOM, "required"),
        ("mix", f" {ZWSP} {BOM} ", "required"),
        ("too-long", "a" * (MAX_TITLE + 1), "too_long"),
    ],
)
def test_invalid_settings_name_is_not_saved(
    locale: Literal["en", "ru"], label: str, title: str, message: str
) -> None:
    result = _run(locale, [_fill("name", title), _fill("description", "keep me"), SUBMIT])
    expected = _required(locale) if message == "required" else _too_long(locale)

    assert _patches(result) == [], f"{label} must not be saved"
    shown = _required(locale) in result["rootText"]
    assert expected in result["rootText"], (
        f"{label} must show the catalog string; required shown={shown}"
    )
    assert _field(result["tree"], "name")["value"] == title
    assert _field(result["tree"], "description")["value"] == "keep me"


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_accepted_settings_name_is_the_normalized_string(locale: Literal["en", "ru"]) -> None:
    description = "d" * (MAX_TITLE + 1)
    event_title = "e" * (MAX_TITLE + 1)
    result = _run(
        locale,
        [
            _fill("name", f"  {BOM}Hi{ZWSP}  "),
            _fill("description", description),
            _fill("event_title", event_title),
            SUBMIT,
        ],
    )
    patches = _patches(result)
    assert len(patches) == 1, "an accepted name is saved once"
    body = json.loads(patches[0]["body"])
    assert body["name"] == f"{BOM}Hi{ZWSP}"
    assert body["description"] == description
    assert body["event_title"] == event_title


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_settings_details_have_no_maxlength_and_a_long_value_is_submitted(
    locale: Literal["en", "ru"],
) -> None:
    description = "d" * (MAX_TITLE + 1)
    event_title = "e" * (MAX_TITLE + 1)
    opened = _run(locale, [])
    for field in ("description", "event_title"):
        assert _attr(_field(opened["tree"], field), "maxlength") is None, field
    result = _run(
        locale,
        [
            _fill("name", "Hi"),
            _fill("description", description),
            _fill("event_title", event_title),
            SUBMIT,
        ],
    )
    body = json.loads(_patches(result)[0]["body"])
    assert body["description"] == description
    assert body["event_title"] == event_title


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_spaces_only_settings_details_are_unset(locale: Literal["en", "ru"]) -> None:
    result = _run(
        locale,
        [
            _fill("name", "Hi"),
            _fill("description", "   "),
            _fill("event_title", " \t "),
            SUBMIT,
        ],
    )
    body = json.loads(_patches(result)[0]["body"])
    assert body["name"] == "Hi"
    assert body["description"] is None
    assert body["event_title"] is None


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_empty_stored_name_shows_the_untitled_label_and_is_not_rewritten(
    locale: Literal["en", "ru"],
) -> None:
    result = _run(locale, [], name="")
    untitled = _text(locale, "miniapp.common.untitled_wishlist")
    assert untitled in result["rootText"]
    assert _patches(result) == []
    assert _field(result["tree"], "name")["value"] == ""
