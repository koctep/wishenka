"""Failing repro for WISHENKA-295 (Step 3): Mini App delete-wishlist zone in the Node harness.

The real ``showList`` runs in the shared fake-DOM harness. Today no delete zone is rendered, so
the owner assertions fail; the non-owner and invalid-retention gating cases are regression
guards that already pass. The harness is patched (as ``test_wishlist_detail_ui`` does) with a
``retentionDays`` dataset field, ``replaceWith`` / ``remove`` / ``removeAttribute`` / ``focus``
on the fake element, a ``steps`` runner that clicks elements by class or exact text, and a
``fetch`` stub for ``DELETE /api/wishlists/1``.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Literal, cast

import pytest

from tests.test_miniapp_i18n_repro import _NODE_HARNESS
from wishenka.i18n import CATALOG

pytestmark = pytest.mark.timeout(20)

SOURCE = Path("wishenka/web/static/miniapp.js")
PREFIX = "miniapp.wishlist_delete."

_PATCHES = (
    (
        "  miniapp: 'app',\n};",
        "  miniapp: 'app',\n};\n"
        "if (scenario.retentionDays !== undefined && scenario.retentionDays !== null) {\n"
        "  rootEl.dataset.retentionDays = scenario.retentionDays;\n}",
    ),
    (
        "function makeEl(tag) {",
        "let focusedEl = null;\n"
        "function findParent(node, target) {\n"
        "  for (const child of (node.children || [])) {\n"
        "    if (child === target) return node;\n"
        "    const deeper = findParent(child, target);\n"
        "    if (deeper) return deeper;\n"
        "  }\n"
        "  return null;\n"
        "}\n"
        "function makeEl(tag) {",
    ),
    (
        "    select() {},\n    focus() {},",
        "    select() {},\n    focus() { focusedEl = this; },\n"
        "    removeAttribute(name) { delete this.attributes[name]; },\n"
        "    replaceWith(other) {\n"
        "      const parent = findParent(rootEl, this);\n"
        "      if (!parent) return;\n"
        "      parent.children[parent.children.indexOf(this)] = other;\n"
        "    },\n"
        "    remove() {\n"
        "      const parent = findParent(rootEl, this);\n"
        "      if (parent) parent.children.splice(parent.children.indexOf(this), 1);\n"
        "    },",
    ),
    (
        "sandbox.globalThis = sandbox;",
        "sandbox.globalThis = sandbox;\n"
        "const baseFetch = sandbox.fetch;\n"
        "const fetchCalls = [];\n"
        "sandbox.fetch = async (url, opts = {}) => {\n"
        "  if ((opts.method || 'GET') === 'DELETE' && url === '/api/wishlists/1') {\n"
        "    fetchCalls.push({url, method: 'DELETE', headers: opts.headers || {}});\n"
        "    const reply = scenario.deleteReply || {status: 200, body: {}};\n"
        "    if (reply.network) throw new Error('network down');\n"
        "    return {ok: reply.status < 400, status: reply.status, json: async () => reply.body};\n"
        "  }\n"
        "  if (url === '/api/wishlists/deleted') {\n"
        "    return {ok: true, status: 200, json: async () => scenario.deleted || []};\n"
        "  }\n"
        "  return baseFetch(url, opts);\n"
        "};\n"
        "function findNode(node, step) {\n"
        "  const classes = ((node.attributes || {}).class || '').split(/\\s+/);\n"
        "  if (step.cls && classes.includes(step.cls)) return node;\n"
        "  if (step.text !== undefined && node.tagName === 'BUTTON' &&\n"
        "      node.textContent === step.text) return node;\n"
        "  for (const child of (node.children || [])) {\n"
        "    const hit = findNode(child, step);\n"
        "    if (hit) return hit;\n"
        "  }\n"
        "  return null;\n"
        "}",
    ),
    (
        "    await sandbox.showList(1);\n    out.rootText = collectText(rootEl);\n"
        "    out.statusText = statusEl.textContent;\n  } else if (scenario.action === 'public')",
        "    await sandbox.showList(1);\n    out.stepErrors = [];\n"
        "    for (const step of scenario.steps || []) {\n"
        "      const scope = step.within ? findNode(rootEl, {cls: step.within}) : rootEl;\n"
        "      const hit = scope ? findNode(scope, step) : null;\n"
        "      if (!hit) { out.stepErrors.push('not found: ' + JSON.stringify(step)); continue; }\n"
        "      if (step.twice) await Promise.all([hit.click(), hit.click()]);\n"
        "      else if (step.key) {\n"
        "        const keydown = (hit.listeners || {}).keydown || [];\n"
        "        for (const fn of keydown) await fn({key: step.key});\n"
        "      } else await hit.click();\n"
        "      await new Promise(r => setImmediate(r));\n"
        "    }\n"
        "    out.rootText = collectText(rootEl);\n    out.tree = rootEl;\n"
        "    out.statusText = statusEl.textContent;\n"
        "    out.statusKind = statusEl.attributes['data-kind'] ?? null;\n"
        "    out.fetchCalls = fetchCalls;\n"
        "    out.focusedClass = focusedEl ? (focusedEl.attributes.class || '') : '';\n"
        "    out.focusedText = focusedEl ? focusedEl.textContent : '';\n"
        "  } else if (scenario.action === 'public')",
    ),
)


def _table(locale: str) -> dict[str, str]:
    return CATALOG["ru" if locale == "ru" else "en"]


def _patched_harness() -> str:
    harness = _NODE_HARNESS
    for old, new in _PATCHES:
        assert old in harness, f"harness anchor changed: {old[:50]!r}"
        harness = harness.replace(old, new)
    return harness


HARNESS = _patched_harness()


def _show(
    locale: str,
    *,
    role: str = "owner",
    status: str = "active",
    retention: str | None = "30",
    name: str = "Birthday",
    members: list[dict[str, Any]] | None = None,
    steps: list[dict[str, Any]] | None = None,
    reply: dict[str, Any] | None = None,
) -> dict[str, Any]:
    detail = {
        "id": 1,
        "name": name,
        "description": "A celebration",
        "status": status,
        "role": role,
        "share_token": "share_tok",
        "invite_token": "inv_tok",
        "members": members if members is not None else [],
        "items": [{"title": "Book", "reserved_by": "Secret giver"}],
    }
    scenario: dict[str, Any] = {
        "action": "list",
        "datasetLocale": locale,
        "wishlistDetail": detail,
        "retentionDays": retention,
        "steps": steps or [],
        "deleteReply": reply,
        "wishlists": [],
        "deleted": [{"id": 1, "name": name, "days_remaining": 5}],
    }
    payload = {
        "jsSource": SOURCE.read_text(encoding="utf-8"),
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
    assert result.get("stepErrors", []) == [], (
        f"a click target is not rendered yet (feature missing): {result.get('stepErrors')}"
    )
    return result


def _classes(node: dict[str, Any]) -> set[str]:
    return set(node.get("attributes", {}).get("class", "").split())


def _walk(node: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        node,
        *(descendant for child in node.get("children", []) for descendant in _walk(child)),
    ]


def _with_class(tree: dict[str, Any], name: str) -> list[dict[str, Any]]:
    return [node for node in _walk(tree) if name in _classes(node)]


def _text(node: dict[str, Any]) -> str:
    own = [str(node.get("textContent") or "")]
    return " | ".join(
        part for part in [*own, *(_text(c) for c in node.get("children", []))] if part
    )


def _path_to(tree: dict[str, Any], name: str) -> list[dict[str, Any]]:
    """Chain of nodes from ``tree`` down to the first node carrying class ``name`` (or [])."""
    if name in _classes(tree):
        return [tree]
    for child in tree.get("children", []):
        below = _path_to(child, name)
        if below:
            return [tree, *below]
    return []


def _fmt(locale: str, key: str, **params: object) -> str:
    template = _table(locale)[PREFIX + key]
    for name, value in params.items():
        template = template.replace("{" + name + "}", str(value))
    return template


def _open_steps(_locale: str) -> list[dict[str, Any]]:
    return [{"cls": "wishlist-delete-open"}]


def _confirm_text(locale: str) -> str:
    return _table(locale).get(PREFIX + "confirm", "<missing confirm key>")


def test_patched_harness_clicks_existing_controls_and_serves_the_deleted_section() -> None:
    """Control: the patched harness itself works on today's code (green before and after)."""
    back = CATALOG["en"]["nav.back"]
    result = _show("en", steps=[{"text": back}])

    assert result["fetchCalls"] == []
    assert CATALOG["en"]["miniapp.home.title"] in result["rootText"]
    assert CATALOG["en"]["miniapp.deleted.heading"] in result["rootText"]


# --- U1 gating -------------------------------------------------------------------------------


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_owner_of_active_list_gets_a_separate_delete_zone_outside_the_form(
    locale: Literal["en", "ru"],
) -> None:
    tree = _show(locale)["tree"]

    zones = _with_class(tree, "wishlist-delete-zone")
    assert len(zones) == 1, "owner of an active list must get exactly one .wishlist-delete-zone"
    chain = _path_to(tree, "wishlist-delete-zone")
    chain_classes = [_classes(node) for node in chain]
    assert any("list-settings-section" in names for names in chain_classes)
    assert not any("wishlist-settings-form" in names for names in chain_classes)
    assert not any("form-actions" in names for names in chain_classes)
    assert chain[-2]["tagName"] != "FORM"
    opener = _with_class(zones[0], "wishlist-delete-open")
    assert len(opener) == 1 and opener[0]["tagName"] == "BUTTON"
    assert opener[0]["textContent"] == _table(locale).get(PREFIX + "open")
    assert _table(locale).get(PREFIX + "heading", "") in _text(zones[0])
    assert opener[0].get("attributes", {}).get("type") == "button"
    assert not _with_class(zones[0], "btn-primary")


@pytest.mark.parametrize("locale", ["en", "ru"])
@pytest.mark.parametrize(
    ("role", "status"),
    [
        ("admin", "active"),
        ("member", "active"),
        ("favorite", "active"),
        ("owner", "archived"),
        ("admin", "archived"),
    ],
)
def test_nobody_but_the_owner_of_an_active_list_is_offered_deletion(
    locale: str, role: str, status: str
) -> None:
    """Regression guard: passes today and must stay green."""
    result = _show(locale, role=role, status=status)
    assert not _with_class(result["tree"], "wishlist-delete-zone"), (role, status)


@pytest.mark.parametrize("locale", ["en", "ru"])
@pytest.mark.parametrize("retention", [None, "", "0", "abc", "-5", "3.5", "30 days"])
def test_owner_is_not_offered_deletion_without_a_valid_retention_period(
    locale: str, retention: str | None
) -> None:
    """Design D-2: the exact number cannot be shown, so the action is not offered (guard)."""
    result = _show(locale, retention=retention)
    assert not _with_class(result["tree"], "wishlist-delete-zone"), retention


# --- U2 the real number ----------------------------------------------------------------------


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_confirmation_uses_the_dataset_retention_days_and_never_a_default(locale: str) -> None:
    result = _show(locale, retention="7", steps=_open_steps(locale))

    panels = _with_class(result["tree"], "wishlist-delete-confirm")
    assert len(panels) == 1, "clicking the trigger must attach one .wishlist-delete-confirm"
    panel = _text(panels[0])
    assert _fmt(locale, "restore_promise", days=7) in panel
    assert _fmt(locale, "purge_promise", days=7) in panel
    assert _fmt(locale, "confirm_title", title="Birthday") in panel
    assert _fmt(locale, "consequences") in panel
    assert "30" not in panel
    assert not _with_class(result["tree"], "wishlist-delete-open"), "trigger replaced by panel"
    assert "wishlist-delete-confirm" in _classes(panels[0])
    assert panels[0]["attributes"].get("role") == "group"
    assert panels[0]["attributes"].get("aria-labelledby")
    assert panels[0]["attributes"].get("aria-describedby")
    assert result["fetchCalls"] == []
    assert "Secret giver" not in result["rootText"]


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_confirmation_names_cancel_first_with_focus_and_a_distinct_confirm(locale: str) -> None:
    result = _show(locale, steps=_open_steps(locale))

    panel = _with_class(result["tree"], "wishlist-delete-confirm")
    assert len(panel) == 1
    buttons = [node for node in _walk(panel[0]) if node["tagName"] == "BUTTON"]
    labels = [node["textContent"] for node in buttons]
    assert labels == [_table(locale).get(PREFIX + "cancel"), _confirm_text(locale)], labels
    assert result["focusedText"] == _table(locale).get(PREFIX + "cancel")


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_success_message_uses_the_days_of_the_response_and_goes_home(locale: str) -> None:
    reply = {"status": 200, "body": {"status": "deleted", "wishlist_id": 1, "retention_days": 5}}
    steps = [*_open_steps(locale), {"text": _confirm_text(locale)}]

    result = _show(locale, retention="7", name="Birthday", steps=steps, reply=reply)

    assert result["statusText"] == _fmt(locale, "done", title="Birthday", days=5)
    assert result["statusKind"] == "success"
    calls = result["fetchCalls"]
    assert [(c["method"], c["url"]) for c in calls] == [("DELETE", "/api/wishlists/1")]
    assert calls[0]["headers"].get("X-CSRF-Token") == "csrf-123"
    assert _table(locale)["miniapp.home.title"] in result["rootText"]
    assert not _with_class(result["tree"], "wishlist-delete-zone")
    assert _table(locale)["miniapp.deleted.heading"] in result["rootText"]


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_title_is_shown_as_text_never_parsed(locale: str) -> None:
    title = "<b>x</b>&amp;"
    result = _show(locale, name=title, steps=_open_steps(locale))

    panel = _with_class(result["tree"], "wishlist-delete-confirm")[0]
    assert _fmt(locale, "confirm_title", title=title) in _text(panel)
    assert not [node for node in _walk(panel) if node["tagName"] == "B"]


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_double_confirm_sends_one_request(locale: str) -> None:
    reply = {"status": 200, "body": {"status": "deleted", "wishlist_id": 1, "retention_days": 30}}
    steps = [*_open_steps(locale), {"text": _confirm_text(locale), "twice": True}]

    result = _show(locale, steps=steps, reply=reply)

    assert len(result["fetchCalls"]) == 1
    assert result["statusText"] == _fmt(locale, "done", title="Birthday", days=30)


@pytest.mark.parametrize("locale", ["en", "ru"])
@pytest.mark.parametrize("reply", [{"status": 500, "body": {}}, {"network": True}])
def test_failure_keeps_the_panel_shows_an_alert_and_no_success_text(
    locale: str, reply: dict[str, Any]
) -> None:
    steps = [*_open_steps(locale), {"text": _confirm_text(locale)}]

    result = _show(locale, steps=steps, reply=reply)

    failed = _fmt(locale, "failed")
    alerts = [n for n in _walk(result["tree"]) if n.get("attributes", {}).get("role") == "alert"]
    assert [n["textContent"] for n in alerts] == [failed]
    assert _with_class(result["tree"], "wishlist-delete-confirm")
    done_prefix = _fmt(locale, "done", title="Birthday", days=30).split("Birthday")[0]
    assert done_prefix not in result["statusText"]
    assert result["statusKind"] != "success"
    confirm = [n for n in _walk(result["tree"]) if n.get("textContent") == _confirm_text(locale)]
    assert len(confirm) == 1 and not confirm[0].get("disabled")
    assert result["focusedText"] == _confirm_text(locale), "focus returns to the confirm button"
    assert len(result["fetchCalls"]) == 1


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_gone_after_retention_window_refreshes_home_with_generic_failure(locale: str) -> None:
    """D-3: a 410 on delete refreshes the home screen; the failure text, never a success."""
    steps = [*_open_steps(locale), {"text": _confirm_text(locale)}]

    result = _show(locale, steps=steps, reply={"status": 410, "body": {}})

    failed = _fmt(locale, "failed")
    assert _table(locale)["miniapp.home.title"] in result["rootText"], "home must be refreshed"
    assert failed in result["rootText"] or failed in result["statusText"], failed
    assert result["statusKind"] != "success"
    done_prefix = _fmt(locale, "done", title="Birthday", days=30).split("Birthday")[0]
    assert done_prefix not in result["statusText"]
    assert len(result["fetchCalls"]) == 1


@pytest.mark.parametrize("locale", ["en", "ru"])
@pytest.mark.parametrize("how", ["cancel", "escape"])
def test_cancel_and_escape_send_nothing_and_restore_the_trigger(locale: str, how: str) -> None:
    close: dict[str, Any] = (
        {
            "text": _table(locale).get(PREFIX + "cancel", "<missing cancel key>"),
            # The settings form has its own, identically labelled Cancel button.
            "within": "wishlist-delete-confirm",
        }
        if how == "cancel"
        else {"cls": "wishlist-delete-confirm", "key": "Escape"}
    )

    result = _show(locale, steps=[*_open_steps(locale), close])

    assert result["fetchCalls"] == []
    assert len(_with_class(result["tree"], "wishlist-delete-open")) == 1
    assert not _with_class(result["tree"], "wishlist-delete-confirm")
    assert result["focusedClass"].split()[:1] == ["wishlist-delete-open"] or (
        "wishlist-delete-open" in result["focusedClass"].split()
    )
    assert result["statusText"] == ""


# --- U3 shared vs personal -------------------------------------------------------------------


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_personal_and_shared_lists_get_identical_texts(locale: str) -> None:
    reply = {"status": 200, "body": {"status": "deleted", "wishlist_id": 1, "retention_days": 7}}
    shared_members = [
        {"user_id": 2, "display_name": "Alex", "role": "member"},
        {"user_id": 3, "display_name": "Sam", "role": "admin"},
    ]
    outcome: dict[str, tuple[str, str]] = {}
    for kind, title, members in (
        ("personal", "Alpha", []),
        ("shared", "Beta", shared_members),
    ):
        opened = _show(
            locale, retention="7", name=title, members=members, steps=_open_steps(locale)
        )
        panel = _text(_with_class(opened["tree"], "wishlist-delete-confirm")[0])
        done = _show(
            locale,
            retention="7",
            name=title,
            members=members,
            steps=[*_open_steps(locale), {"text": _confirm_text(locale)}],
            reply=reply,
        )
        outcome[kind] = (panel.replace(title, "<T>"), done["statusText"].replace(title, "<T>"))

    assert outcome["personal"][0] != "" and "<T>" in outcome["personal"][0]
    assert outcome["personal"] == outcome["shared"]
