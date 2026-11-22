"""Wishlist detail workspace renders its primary and management regions in order."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Literal, cast

import pytest

from tests.test_miniapp_i18n_repro import _NODE_HARNESS
from wishenka.i18n import CATALOG

pytestmark = pytest.mark.timeout(20)

SOURCE = Path("wishenka/web/static/miniapp.js")
HARNESS = _NODE_HARNESS.replace(
    "out.rootText = collectText(rootEl);\n    out.statusText = statusEl.textContent;\n"
    "  } else if (scenario.action === 'public')",
    "out.rootText = collectText(rootEl);\n    out.tree = rootEl;\n"
    "    out.statusText = statusEl.textContent;\n  } else if (scenario.action === 'public')",
)


def _detail(locale: str, **changes: Any) -> dict[str, Any]:
    detail = {
        "id": 1,
        "name": "Birthday",
        "description": "A celebration",
        "event_title": "Party",
        "event_date": "2027-01-02",
        "status": "active",
        "role": "owner",
        "share_token": "share_tok",
        "invite_token": "inv_tok",
        "members": [{"user_id": 2, "display_name": "Alex", "role": "member"}],
        "items": [{"title": "Book", "reserved_by": "Secret giver"}],
    }
    detail.update(changes)
    payload = {
        "jsSource": SOURCE.read_text(encoding="utf-8"),
        "i18nJson": json.dumps(CATALOG),
        "scenario": {"action": "list", "datasetLocale": locale, "wishlistDetail": detail},
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
    return cast(dict[str, Any], json.loads(process.stdout))


def _classes(node: dict[str, Any]) -> set[str]:
    return set(node.get("attributes", {}).get("class", "").split())


def _walk(node: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        node,
        *(descendant for child in node.get("children", []) for descendant in _walk(child)),
    ]


def _with_class(tree: dict[str, Any], name: str) -> list[dict[str, Any]]:
    return [node for node in _walk(tree) if name in _classes(node)]


@pytest.mark.parametrize("locale", ["en", "ru"])
@pytest.mark.parametrize("role", ["owner", "admin", "member"])
def test_header_fallback_optional_fields_and_role_badge(
    locale: Literal["en", "ru"], role: str
) -> None:
    result = _detail(locale, name="", description="", event_title=None, event_date=None, role=role)
    tree = result["tree"]
    header = _with_class(tree, "wishlist-detail-header")
    assert len(header) == 1
    assert CATALOG[locale]["miniapp.common.untitled_wishlist"] in result["rootText"]
    assert not _with_class(header[0], "list-description")
    assert not _with_class(header[0], "list-event-meta")
    badges = _with_class(header[0], f"badge-{role}")
    assert len(badges) == 1
    assert badges[0]["textContent"] == CATALOG[locale][f"miniapp.role.{role}"]
    assert bool(_with_class(header[0], "list-favorite-btn")) == (role != "owner")


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_header_shows_description_and_occasion(locale: str) -> None:
    tree = _detail(locale)["tree"]
    description = _with_class(tree, "list-description")
    event = _with_class(tree, "list-event-meta")
    assert len(description) == len(event) == 1
    assert "A celebration" in description[0]["textContent"]
    assert "Party" in event[0]["textContent"]
    assert "2027" in event[0]["textContent"]


@pytest.mark.parametrize("locale", ["en", "ru"])
@pytest.mark.parametrize("role", ["owner", "admin", "member"])
def test_archived_restore_is_manager_only(locale: str, role: str) -> None:
    tree = _detail(locale, role=role, status="archived")["tree"]
    assert len(_with_class(tree, "list-archived-banner")) == 1
    assert bool(_with_class(tree, "list-restore-btn")) == (role in {"owner", "admin"})


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_member_rows_show_localized_role_badges(locale: Literal["en", "ru"]) -> None:
    members = [
        {"user_id": index, "display_name": role.title(), "role": role}
        for index, role in enumerate(("owner", "admin", "member"), start=1)
    ]
    rows = _with_class(_detail(locale, members=members)["tree"], "member-row")
    assert len(rows) == len(members)
    for role, row in zip(("owner", "admin", "member"), rows, strict=True):
        names = _with_class(row, "member-name")
        badges = _with_class(row, f"badge-{role}")
        assert len(names) == len(badges) == 1
        assert names[0]["textContent"] == role.title()
        assert badges[0]["textContent"] == CATALOG[locale][f"miniapp.role.{role}"]


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_owner_detail_prioritizes_wishes_and_distinguishes_management(locale: str) -> None:
    result = _detail(locale)
    tree = result["tree"]
    children = tree["children"]
    expected = [
        "wishlist-detail-header",
        "list-wishes-section",
        "list-settings-section",
        "share-panel--public",
        "list-members-section",
    ]
    positions = [
        next((i for i, node in enumerate(children) if name in _classes(node)), -1)
        for name in expected
    ]
    assert all(index >= 0 for index in positions), dict(zip(expected, positions, strict=True))
    assert positions == sorted(positions)
    nodes = _walk(tree)
    for name in (
        "list-event-meta",
        "list-wish-card",
        "settings-save-btn",
        "settings-cancel-btn",
        "share-panel--invite",
        "member-row",
        "member-name",
        "member-role-btn",
        "member-remove-btn",
    ):
        assert any(name in _classes(node) for node in nodes), name
    assert "Secret giver" not in result["rootText"]


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_archived_detail_hides_mutation_and_offers_restore(locale: str) -> None:
    result = _detail(locale, status="archived")
    names = set().union(*(_classes(node) for node in _walk(result["tree"])))
    assert {"list-archived-banner", "list-restore-btn"} <= names
    assert not names.intersection(
        {"list-settings-section", "share-panel--public", "list-members-section"}
    )


def test_new_detail_translations_match_placeholders() -> None:
    keys = {
        "miniapp.list.occasion_prefix",
        "miniapp.list.wishes_subtitle",
        "miniapp.list.wishes_empty",
        "miniapp.wishlist_settings.subtitle",
        "miniapp.wishlist_settings.hint_title",
        "miniapp.wishlist_settings.hint_description",
        "miniapp.wishlist_settings.hint_event",
        "miniapp.wishlist_settings.hint_date",
        "miniapp.wishlist_settings.saved",
        "miniapp.wishlist_settings.cancelled",
        "miniapp.wishlist_settings.save_failed",
        "miniapp.share.public_hint",
        "miniapp.members.invite_hint",
        "miniapp.members.subtitle",
        "miniapp.members.role_updated",
        "miniapp.members.role_change_failed",
        "miniapp.list.restored",
    }
    for key in sorted(keys):
        for locale in ("en", "ru"):
            assert CATALOG[locale].get(key), f"missing {locale} translation: {key}"
        assert set(re.findall(r"\{\w+\}", CATALOG["en"][key])) == set(
            re.findall(r"\{\w+\}", CATALOG["ru"][key])
        ), key
