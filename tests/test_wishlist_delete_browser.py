"""Browser checks for deleting a wishlist from its settings.

WISHENKA-317 checks, in Russian and English: a forced 410 returns to the home
screen, announces the existing failure, and focuses the home heading, which
describes that failure. The delete Cancel keeps its visible label and has its
own accessible name, different from the settings Cancel. A successful delete
still focuses a heading with no ``aria-describedby``.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Literal

import pytest

from tests.browser_cdp import CdpBrowser, CdpPage
from tests.browser_helpers import Seeded, scroll_to
from tests.browser_screens import (
    CONTRAST_JS,
    api,
    open_miniapp,
    provision_user,
    width_problems,
)
from tests.conftest import OWNER_TELEGRAM_ID, VIEWER_TELEGRAM_ID, BrowserServer
from wishenka.i18n import CATALOG

pytestmark = [pytest.mark.timeout(45), pytest.mark.browser]

PREFIX = "miniapp.wishlist_delete."
OPEN = ".wishlist-delete-open"
PANEL = ".wishlist-delete-confirm"
CANCEL = f"{PANEL} .wishlist-delete-actions button:nth-of-type(1)"
CONFIRM = f"{PANEL} .wishlist-delete-actions button:nth-of-type(2)"
ALERT = PANEL + ' [role="alert"]'
WISHLIST_TITLE = "Browser wishlist"
MARKUP_TITLE = "<b>x</b>&amp; 'quoted'"
LONG_TITLE = "Very long family birthday wishlist title to verify wrapping " + "W" * 80
RETENTION_DAYS = 30


def _table(locale: str) -> dict[str, str]:
    return CATALOG["ru" if locale == "ru" else "en"]


OpenList = Callable[..., CdpPage]


def _text(locale: str, key: str) -> str:
    """Catalog text of a key that Step 4 adds; a missing key reads as a marker, not an error."""
    return _table(locale).get(PREFIX + key, f"<missing catalog key {PREFIX + key}>")


def _fmt(locale: str, key: str, **params: object) -> str:
    template = _text(locale, key)
    for name, value in params.items():
        template = template.replace("{" + name + "}", str(value))
    return template


def _installed_fetch(path: str, mode: str) -> str:
    """JS that wraps ``fetch`` for ``DELETE <path>``: count calls, then hold, fail, 410, or pass."""
    return f"""(() => {{
      const real = window.fetch.bind(window);
      window.deleteCalls = 0; window.deleteMode = {json.dumps(mode)}; window.releaseDelete = null;
      window.fetch = async (input, options = {{}}) => {{
        const url = new URL(input, location.href);
        if ((options.method || 'GET') === 'DELETE' && url.pathname === {json.dumps(path)}) {{
          window.deleteCalls += 1;
          if (window.deleteMode === 'fail') return new Response('{{}}', {{status: 500}});
          if (window.deleteMode === '410') return new Response('{{}}', {{status: 410}});
          if (window.deleteMode === 'network') throw new TypeError('network down');
          if (window.deleteMode === 'hold') {{
            await new Promise(resolve => {{ window.releaseDelete = resolve; }});
          }}
        }}
        return real(input, options);
      }};
    }})()"""


def _delete_requests(page: CdpPage) -> list[Any]:
    return [
        r for r in page.requests if r.method == "DELETE" and r.path.startswith("/api/wishlists/")
    ]


def _wait_panel(page: CdpPage) -> None:
    page.wait_for("delete confirmation panel", f"!!document.querySelector({json.dumps(PANEL)})")


def _open_panel(page: CdpPage) -> None:
    present = page.evaluate(f"!!document.querySelector({json.dumps(OPEN)})")
    assert present, (
        f"no {OPEN} trigger in the owner's settings (feature missing)\n{page.snapshot()}"
    )
    scroll_to(page, OPEN)
    page.click(OPEN)
    _wait_panel(page)


_CANCEL_NAME = {
    "en": 'Cancel deleting "{title}"',
    "ru": "Отменить удаление «{title}»",
}


def _cancel_name(locale: str, title: str) -> str:
    return _CANCEL_NAME[locale].replace("{title}", title)


def _wait_expired_home(page: CdpPage, locale: str) -> None:
    title = json.dumps(_table(locale)["miniapp.home.title"])
    page.wait_for(
        "home after an expired delete",
        f"document.querySelector('#app h1')?.innerText === {title} "
        "&& document.getElementById('status')?.getAttribute('data-kind') === 'error'",
    )


def _ax_text(node: dict[str, Any], field: str) -> str:
    return " ".join(str((node.get(field) or {}).get("value", "")).split())


def _ax_focused(node: dict[str, Any]) -> bool:
    for prop in node.get("properties") or []:
        if prop.get("name") == "focused":
            value = (prop.get("value") or {}).get("value")
            return value is True or value == "true"
    return False


def _ax_tree(page: CdpPage) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    nodes = page._send("Accessibility.getFullAXTree")["nodes"]  # noqa: SLF001
    by_id = {str(node["nodeId"]): node for node in nodes}
    live = [node for node in nodes if not node.get("ignored")]
    return live, by_id


def _dom_backend_id(page: CdpPage, selector: str) -> int:
    """Backend DOM id of ``selector``, or 0 when the element is not in the document."""
    root_id = page._send("DOM.getDocument", {"depth": 0})["root"]["nodeId"]  # noqa: SLF001
    node_id = page._send(  # noqa: SLF001
        "DOM.querySelector", {"nodeId": root_id, "selector": selector}
    ).get("nodeId", 0)
    if not node_id:
        return 0
    backend = page._send("DOM.describeNode", {"nodeId": node_id})["node"].get(  # noqa: SLF001
        "backendNodeId"
    )
    return int(backend or 0)


def _is_button(node: dict[str, Any], backend_id: int) -> bool:
    return (
        int(node.get("backendDOMNodeId") or 0) == backend_id
        and node.get("role", {}).get("value") == "button"
        and not node.get("ignored")
    )


def _accessible_button_name(
    page: CdpPage, selector: str, nodes: list[dict[str, Any]]
) -> str | None:
    """Computed name of the accessibility button bound to the DOM element ``selector``."""
    backend_id = _dom_backend_id(page, selector)
    if backend_id == 0:
        return None
    matched = [node for node in nodes if _is_button(node, backend_id)]
    if len(matched) == 1:
        return _ax_text(matched[0], "name")
    root_id = page._send("DOM.getDocument", {"depth": 0})["root"]["nodeId"]  # noqa: SLF001
    node_id = page._send(  # noqa: SLF001
        "DOM.querySelector", {"nodeId": root_id, "selector": selector}
    ).get("nodeId", 0)
    if not node_id:
        return None
    partial = page._send(  # noqa: SLF001
        "Accessibility.getPartialAXTree",
        {"nodeId": node_id, "fetchRelatives": False},
    )["nodes"]
    partial_match = [node for node in partial if _is_button(node, backend_id)]
    if len(partial_match) == 1:
        return _ax_text(partial_match[0], "name")
    return None


def _subtree_text(node: dict[str, Any], by_id: dict[str, dict[str, Any]]) -> str:
    parts = [_ax_text(node, "name")]
    for child_id in node.get("childIds") or []:
        child = by_id.get(str(child_id))
        if child is not None:
            parts.append(_subtree_text(child, by_id))
    return " ".join(part for part in parts if part)


def _wait_home(page: CdpPage, locale: str) -> None:
    title = json.dumps(_table(locale)["miniapp.home.title"])
    page.wait_for(
        "home after the deletion",
        f"document.querySelector('#app h1')?.innerText === {title} "
        "&& document.getElementById('status')?.getAttribute('data-kind') === 'success'",
    )


def _status(page: CdpPage) -> dict[str, Any]:
    result: dict[str, Any] = page.evaluate(
        """(() => { const s = document.getElementById('status');
          return {text: s.innerText, kind: s.getAttribute('data-kind')}; })()"""
    )
    return result


def _normalized(text: str, title: str) -> str:
    return " ".join(text.replace(title, "<T>").split())


@pytest.fixture
def open_list(
    chromium_browser: CdpBrowser,
    wishlist_server: BrowserServer,
    _browser_pages: list[CdpPage],
) -> OpenList:
    """Factory ``open_list(locale, width=375, title=None) -> CdpPage`` on the owner's list screen.

    ``title`` picks the home card to open; the first card is opened when it is ``None``.
    """

    def factory(locale: Literal["en", "ru"], width: int = 375, title: str | None = None) -> CdpPage:
        server = wishlist_server
        provision_user(server, server.owner_token, OWNER_TELEGRAM_ID, "Owner", locale)
        provision_user(server, server.viewer_token, VIEWER_TELEGRAM_ID, "Viewer", locale)
        page = open_miniapp(
            chromium_browser,
            _browser_pages,
            server,
            server.owner_token,
            locale,
            viewport=(width, 800),
        )
        page.evaluate(
            f"""(() => {{
          const wanted = {json.dumps(title)};
          const card = Array.from(document.querySelectorAll('.wishlist-card')).find(
            c => wanted === null || c.querySelector('.wishlist-card-title')?.innerText === wanted);
          card?.querySelector('.wishlist-card-open')?.setAttribute('data-test-open', '1');
        }})()"""
        )
        scroll_to(page, "[data-test-open]")
        page.click("[data-test-open]")
        page.wait_for("owner list screen", "!!document.querySelector('.list-settings-section')")
        return page

    return factory


def _rename(server: BrowserServer, seeded: Seeded, name: str) -> None:
    api(
        server,
        seeded.owner_token,
        "PATCH",
        f"/api/wishlists/{seeded.wishlist_id}",
        json={"name": name},
    )


def _list_status(server: BrowserServer, seeded: Seeded) -> str:
    """Status of the owner's list; a deleted list is hidden from the detail route (404)."""
    deleted = api(server, seeded.owner_token, "GET", "/api/wishlists/deleted")
    if any(entry["id"] == seeded.wishlist_id for entry in deleted):
        return "deleted"
    stored = api(server, seeded.owner_token, "GET", f"/api/wishlists/{seeded.wishlist_id}")
    return str(stored["status"])


# --- 1 finding the action --------------------------------------------------------------------


@pytest.mark.parametrize(("locale", "width"), [("en", 375), ("ru", 320)])
def test_owner_sees_a_separated_destructive_zone_outside_the_settings_form(
    locale: Literal["en", "ru"],
    width: int,
    seed_wishlist: Callable[..., Seeded],
    open_list: OpenList,
) -> None:
    seed_wishlist(["Camera"])
    page = open_list(locale, width)

    found = page.evaluate(
        """(() => {
      const zone = document.querySelector('.wishlist-delete-zone');
      const section = document.querySelector('.list-settings-section');
      const form = document.querySelector('.wishlist-settings-form');
      const open = document.querySelector('.wishlist-delete-open');
      const save = document.querySelector('.settings-save-btn');
      const style = open ? getComputedStyle(open) : null;
      return {
        zone: !!zone, inSection: !!zone && section.contains(zone),
        inForm: !!zone && form.contains(zone),
        inFormActions: !!zone && !!zone.closest('.form-actions'),
        openText: open ? open.innerText : null,
        openHeight: open ? open.getBoundingClientRect().height : 0,
        openBackground: style ? style.backgroundColor : null,
        openBorder: style ? style.borderTopColor : null,
        saveBackground: getComputedStyle(save).backgroundColor,
        heading: zone && zone.querySelector('h3') ? zone.querySelector('h3').innerText : null,
        panelAttached: !!document.querySelector('.wishlist-delete-confirm'),
      };
    })()"""
    )
    problems = []
    if not found["zone"]:
        problems.append("no .wishlist-delete-zone in the owner's settings")
    else:
        if not found["inSection"]:
            problems.append("zone is outside .list-settings-section")
        if found["inForm"] or found["inFormActions"]:
            problems.append("zone sits inside the settings form or .form-actions")
        if found["openText"] != _text(locale, "open"):
            problems.append(f"trigger text {found['openText']!r} != {_text(locale, 'open')!r}")
        if found["heading"] != _text(locale, "heading"):
            problems.append(f"heading {found['heading']!r} != {_text(locale, 'heading')!r}")
        if found["openHeight"] < 44:
            problems.append(f"trigger is {found['openHeight']}px high, under 44")
        if found["openBackground"] != "rgba(0, 0, 0, 0)":
            problems.append(f"trigger is filled ({found['openBackground']}), not outlined")
        if found["openBorder"] == found["saveBackground"]:
            problems.append("trigger looks like the Save button")
        if found["panelAttached"]:
            problems.append("the confirmation is shown before the trigger is pressed")
    assert not problems, f"{problems}\n{page.snapshot()}"
    assert _delete_requests(page) == []


# --- 2 open: exact title, promises, focus ----------------------------------------------------


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_open_shows_exact_title_both_promises_and_focuses_cancel(
    locale: Literal["en", "ru"],
    seed_wishlist: Callable[..., Seeded],
    wishlist_server: BrowserServer,
    open_list: OpenList,
) -> None:
    seeded = seed_wishlist(["Camera"])
    _rename(wishlist_server, seeded, MARKUP_TITLE)
    page = open_list(locale)

    _open_panel(page)

    state = page.evaluate(
        f"""(() => {{
      const panel = document.querySelector({json.dumps(PANEL)});
      const active = document.activeElement;
      return {{
        text: panel.innerText, role: panel.getAttribute('role'),
        buttons: Array.from(panel.querySelectorAll('button'), b => b.innerText),
        activeText: active ? active.innerText : null,
        triggerGone: !document.querySelector({json.dumps(OPEN)}),
        injected: panel.querySelectorAll('b').length,
        height: Array.from(panel.querySelectorAll('button'),
          b => b.getBoundingClientRect().height),
      }};
    }})()"""
    )
    text = " ".join(state["text"].split())
    expected = [
        _fmt(locale, "confirm_title", title=MARKUP_TITLE),
        _text(locale, "consequences"),
        _fmt(locale, "restore_promise", days=RETENTION_DAYS),
        _fmt(locale, "purge_promise", days=RETENTION_DAYS),
    ]
    missing = [part for part in expected if " ".join(part.split()) not in text]
    assert not missing, f"panel text lacks {missing}\n{text}"
    assert state["role"] == "group"
    assert state["buttons"] == [_text(locale, "cancel"), _text(locale, "confirm")]
    assert state["activeText"] == _text(locale, "cancel"), "Cancel must hold the focus"
    assert state["triggerGone"], "the trigger is replaced by the panel"
    assert state["injected"] == 0, "the title must be shown as text, not parsed as HTML"
    assert all(h >= 44 for h in state["height"]), state["height"]
    nodes = page._send("Accessibility.getFullAXTree")["nodes"]  # noqa: SLF001
    named = [
        n
        for n in nodes
        if not n.get("ignored")
        and n.get("role", {}).get("value") == "group"
        and MARKUP_TITLE in str(n.get("name", {}).get("value", ""))
    ]
    assert named, "the group must be announced with the exact list title as its name"
    assert _delete_requests(page) == []


# --- 3 cancel and Escape ---------------------------------------------------------------------


@pytest.mark.parametrize("how", ["cancel", "escape"])
def test_cancel_and_escape_send_nothing_and_return_focus_to_the_trigger(
    how: str,
    seed_wishlist: Callable[..., Seeded],
    wishlist_server: BrowserServer,
    open_list: OpenList,
) -> None:
    seeded = seed_wishlist(["Camera"])
    page = open_list("en")
    _open_panel(page)

    if how == "cancel":
        page.click(CANCEL)
    else:
        page.press_key("Escape")
    page.wait_for("trigger is back", f"!!document.querySelector({json.dumps(OPEN)})")

    state = page.evaluate(
        f"""({{
      panel: !!document.querySelector({json.dumps(PANEL)}),
      focused: document.activeElement === document.querySelector({json.dumps(OPEN)}),
      status: document.getElementById('status').innerText,
    }})"""
    )
    assert state == {"panel": False, "focused": True, "status": ""}, state
    assert _delete_requests(page) == []
    assert _list_status(wishlist_server, seeded) == "active"


# --- 4, 5 confirm, result, restore round trip ------------------------------------------------


@pytest.mark.parametrize(("locale", "width"), [("en", 375), ("ru", 320)])
def test_confirm_sends_one_request_shows_result_on_home_and_restore_brings_it_back(
    locale: Literal["en", "ru"],
    width: int,
    seed_wishlist: Callable[..., Seeded],
    wishlist_server: BrowserServer,
    open_list: OpenList,
) -> None:
    seeded = seed_wishlist(["Camera"])
    path = f"/api/wishlists/{seeded.wishlist_id}"
    page = open_list(locale, width)
    page.evaluate(_installed_fetch(path, "hold"))
    _open_panel(page)

    page.click(CONFIRM)
    page.wait_for("request in flight", "window.deleteCalls === 1")
    busy = page.evaluate(
        f"""(() => {{
      const yes = document.querySelector({json.dumps(CONFIRM)});
      const no = document.querySelector({json.dumps(CANCEL)});
      return {{yesDisabled: yes.disabled, yesBusy: yes.getAttribute('aria-busy'),
               noDisabled: no.disabled}};
    }})()"""
    )
    assert busy == {"yesDisabled": True, "yesBusy": "true", "noDisabled": True}, busy
    page.click(CONFIRM)
    page.press_key("Enter")
    page.press_key("Escape")
    assert page.evaluate("window.deleteCalls") == 1, "a second tap must not send a second request"
    assert page.evaluate(f"!!document.querySelector({json.dumps(PANEL)})"), "closed mid-flight"

    page.evaluate("window.releaseDelete()")
    _wait_home(page, locale)

    done = _fmt(locale, "done", title=WISHLIST_TITLE, days=RETENTION_DAYS)
    assert _status(page) == {"text": done, "kind": "success"}
    home = page.evaluate(
        """(() => ({
      path: location.pathname,
      h1Focused: document.activeElement === document.querySelector('#app h1'),
      openCards: document.querySelectorAll('.wishlist-card-open').length,
      deleted: Array.from(document.querySelectorAll('.deleted-wishlist-card'), c => c.innerText),
    }))()"""
    )
    assert home["path"] == "/"
    assert home["h1Focused"], "focus must land on the home heading"
    assert (
        page.evaluate("document.querySelector('#app h1').getAttribute('aria-describedby')") is None
    )
    assert home["openCards"] == 0, "the list must not stay among the active lists"
    days_left = _table(locale)["miniapp.deleted.days_left"].replace("{days}", str(RETENTION_DAYS))
    assert len(home["deleted"]) == 1
    assert WISHLIST_TITLE in home["deleted"][0] and days_left in home["deleted"][0], home
    assert _list_status(wishlist_server, seeded) == "deleted"
    assert len(_delete_requests(page)) == 1, "exactly one DELETE reaches the server"

    scroll_to(page, ".wishlist-card-restore")
    page.click(".wishlist-card-restore")
    page.wait_for(
        "restored",
        "document.querySelectorAll('.wishlist-card-open').length === 1 && "
        "document.getElementById('status').getAttribute('data-kind') === 'success'",
    )
    assert _status(page)["text"] == _table(locale)["miniapp.deleted.restored"]
    assert _list_status(wishlist_server, seeded) == "active"


# --- expired return and distinct Cancel names (WISHENKA-317) --------------------------------


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_expired_delete_focuses_the_home_heading_and_describes_the_failure(
    locale: Literal["en", "ru"],
    seed_wishlist: Callable[..., Seeded],
    wishlist_server: BrowserServer,
    open_list: OpenList,
) -> None:
    seeded = seed_wishlist(["Camera"])
    path = f"/api/wishlists/{seeded.wishlist_id}"
    page = open_list(locale)
    _open_panel(page)
    page.evaluate(_installed_fetch(path, "410"))
    scroll_to(page, CONFIRM)
    page.click(CONFIRM)
    _wait_expired_home(page, locale)

    failed = _text(locale, "failed")
    home = _table(locale)["miniapp.home.title"]
    state = page.evaluate(
        """(() => {
      const h1 = document.querySelector('#app h1');
      const status = document.getElementById('status');
      const app = document.getElementById('app');
      return {
        activeIsHeading: document.activeElement === h1,
        activeIsBody: document.activeElement === document.body,
        activeTag: document.activeElement ? document.activeElement.tagName : null,
        tabindex: h1 ? h1.getAttribute('tabindex') : null,
        describedBy: h1 ? h1.getAttribute('aria-describedby') : null,
        statusText: status ? status.innerText : null,
        statusRole: status ? status.getAttribute('role') : null,
        statusLive: status ? status.getAttribute('aria-live') : null,
        statusOutsideApp: !!(status && app && !app.contains(status)),
        panel: !!document.querySelector('.wishlist-delete-confirm'),
        alert: !!document.querySelector('[role="alert"]'),
        deleteCalls: window.deleteCalls,
      };
    })()"""
    )
    problems: list[str] = []
    if not state["activeIsHeading"] or state["activeIsBody"]:
        problems.append(f"focus is {state['activeTag']}, not the home heading")
    if state["tabindex"] != "-1":
        problems.append(f"heading tabindex {state['tabindex']!r} != '-1'")
    if state["describedBy"] != "status":
        problems.append(f"aria-describedby {state['describedBy']!r} != 'status'")
    if state["statusText"] != failed:
        problems.append(f"status text {state['statusText']!r} != {failed!r}")
    if state["statusRole"] != "status":
        problems.append(f"status role {state['statusRole']!r} != 'status'")
    if state["statusLive"] != "assertive":
        problems.append(f"aria-live {state['statusLive']!r} != 'assertive'")
    if not state["statusOutsideApp"]:
        problems.append("#status is inside #app")
    if state["panel"] or state["alert"]:
        problems.append("the confirmation or an alert is still in the page")
    if state["deleteCalls"] != 1:
        problems.append(f"deleteCalls {state['deleteCalls']!r} != 1")
    live, by_id = _ax_tree(page)
    headings = [
        node
        for node in live
        if node.get("role", {}).get("value") == "heading" and _ax_text(node, "name") == home
    ]
    focused = [node for node in headings if _ax_focused(node)]
    if not focused:
        problems.append("the accessibility tree does not focus the home heading")
    heading = focused[0] if focused else (headings[0] if headings else {})
    described = _ax_text(heading, "description")
    if described != failed:
        problems.append(f"heading description {described!r} != {failed!r}")
    status_nodes = [
        node for node in by_id.values() if node.get("role", {}).get("value") == "status"
    ]
    if not any(failed in _subtree_text(node, by_id) for node in status_nodes):
        sample = [
            (node.get("role", {}).get("value"), _subtree_text(node, by_id)[:80])
            for node in status_nodes
        ]
        problems.append(f"status node does not expose the failure; status={sample}")
    if _list_status(wishlist_server, seeded) != "active":
        problems.append("the wishlist did not stay active")
    assert not problems, f"{problems}\n{page.snapshot()}"


@pytest.mark.parametrize("locale", ["en", "ru"])
@pytest.mark.parametrize("title", [WISHLIST_TITLE, MARKUP_TITLE])
def test_delete_and_settings_cancels_have_distinct_accessible_names(
    locale: Literal["en", "ru"],
    title: str,
    seed_wishlist: Callable[..., Seeded],
    wishlist_server: BrowserServer,
    open_list: OpenList,
) -> None:
    seeded = seed_wishlist(["Camera"])
    if title != WISHLIST_TITLE:
        _rename(wishlist_server, seeded, title)
    page = open_list(locale, title=title)
    _open_panel(page)

    expected = _cancel_name(locale, title)
    visible = _text(locale, "cancel")
    settings_name = _table(locale)["miniapp.wishlist_settings.cancel"]
    dom = page.evaluate(
        f"""(() => {{
      const del = document.querySelector({json.dumps(CANCEL)});
      const settings = document.querySelector('.settings-cancel-btn');
      return {{
        deleteText: del ? del.innerText : null,
        deleteLabel: del ? del.getAttribute('aria-label') : null,
        injected: del ? del.querySelectorAll('*').length : -1,
        settingsText: settings ? settings.innerText : null,
        settingsLabel: settings ? settings.getAttribute('aria-label') : null,
      }};
    }})()"""
    )
    live, _by_id = _ax_tree(page)
    delete_name = _accessible_button_name(page, CANCEL, live)
    settings_seen = _accessible_button_name(page, ".settings-cancel-btn", live)
    problems: list[str] = []
    if dom["deleteText"] != visible:
        problems.append(f"delete innerText {dom['deleteText']!r} != {visible!r}")
    if dom["deleteLabel"] != expected:
        problems.append(f"delete aria-label {dom['deleteLabel']!r} != {expected!r}")
    if dom["injected"] != 0:
        problems.append(f"delete Cancel contains {dom['injected']} elements")
    if title not in expected:
        problems.append("the accessible name does not contain the title")
    if dom["settingsText"] != settings_name:
        problems.append(f"settings innerText {dom['settingsText']!r} != {settings_name!r}")
    if dom["settingsLabel"] is not None:
        problems.append(f"settings Cancel has aria-label {dom['settingsLabel']!r}")
    if delete_name != expected:
        problems.append(f"delete accessible name {delete_name!r} != {expected!r}")
    if settings_seen != settings_name:
        problems.append(f"settings accessible name {settings_seen!r} != {settings_name!r}")
    if expected == settings_name:
        problems.append("the two accessible names are the same")
    assert not problems, f"{problems}\n{page.snapshot()}"


# --- 6 failure and retry ---------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["fail", "network"])
def test_failure_keeps_the_panel_shows_an_alert_and_a_retry_succeeds(
    mode: str,
    seed_wishlist: Callable[..., Seeded],
    wishlist_server: BrowserServer,
    open_list: OpenList,
) -> None:
    seeded = seed_wishlist(["Camera"])
    path = f"/api/wishlists/{seeded.wishlist_id}"
    page = open_list("en")
    page.evaluate(_installed_fetch(path, mode))
    _open_panel(page)

    page.click(CONFIRM)
    page.wait_for("failure alert", f"!!document.querySelector({json.dumps(ALERT)})")

    state = page.evaluate(
        f"""(() => {{
      const yes = document.querySelector({json.dumps(CONFIRM)});
      const status = document.getElementById('status');
      return {{
        alert: document.querySelector({json.dumps(ALERT)}).innerText,
        panel: !!document.querySelector({json.dumps(PANEL)}),
        yesDisabled: yes.disabled, yesFocused: document.activeElement === yes,
        statusText: status.innerText, statusKind: status.getAttribute('data-kind'),
      }};
    }})()"""
    )
    assert state["alert"] == _text("en", "failed")
    assert state["panel"] and not state["yesDisabled"] and state["yesFocused"], state
    assert state["statusKind"] != "success" and "deleted" not in state["statusText"].lower()
    assert _list_status(wishlist_server, seeded) == "active"

    page.evaluate("window.deleteMode = 'pass'")
    page.click(CONFIRM)
    _wait_home(page, "en")
    assert _status(page)["kind"] == "success"
    assert _list_status(wishlist_server, seeded) == "deleted"


# --- 7 layout, touch, focus ring -------------------------------------------------------------


@pytest.mark.parametrize(("locale", "width"), [("en", 320), ("ru", 320), ("en", 375)])
def test_panel_fits_narrow_phones_with_touch_targets_focus_ring_and_contrast(
    locale: Literal["en", "ru"],
    width: int,
    seed_wishlist: Callable[..., Seeded],
    wishlist_server: BrowserServer,
    open_list: OpenList,
) -> None:
    seeded = seed_wishlist(["Camera"])
    _rename(wishlist_server, seeded, LONG_TITLE)
    page = open_list(locale, width)
    _open_panel(page)

    problems = width_problems(page, width, targets=True)
    assert not problems, f"{problems}\n{page.snapshot()}"
    assert LONG_TITLE in page.evaluate(f"document.querySelector({json.dumps(PANEL)}).innerText")
    page.press_key("Tab")
    focus = page.evaluate(
        """(() => { const el = document.activeElement; const s = getComputedStyle(el);
          return {text: el.innerText, outline: s.outlineStyle, width: parseFloat(s.outlineWidth)};
        })()"""
    )
    assert focus["text"] == _text(locale, "confirm"), focus
    assert focus["outline"] != "none" and focus["width"] > 0, f"no focus ring {focus}"
    failures = [
        f
        for f in page.evaluate(CONTRAST_JS)
        if any(word in f for word in ("delete", "confirm", "danger"))
    ]
    assert not failures, failures
    assert page.evaluate(f"document.querySelectorAll({json.dumps(PANEL + ' button')}).length") == 2


# --- 8 surprise secrecy in the UI ------------------------------------------------------------


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_texts_are_identical_for_lists_with_and_without_reservations(
    locale: Literal["en", "ru"],
    seed_wishlist: Callable[..., Seeded],
    wishlist_server: BrowserServer,
    open_list: OpenList,
) -> None:
    reserved = seed_wishlist(["Camera"])
    _rename(wishlist_server, reserved, "Alpha list")
    item_id = api(
        wishlist_server, reserved.owner_token, "GET", f"/api/wishlists/{reserved.wishlist_id}"
    )["items"][0]["id"]
    api(
        wishlist_server,
        reserved.viewer_token,
        "POST",
        f"/api/public/wishlists/{reserved.public_token}/items/{item_id}/reservations",
        json={"quantity": 1},
    )
    quiet = api(
        wishlist_server, reserved.owner_token, "POST", "/api/wishlists", json={"name": "Beta list"}
    )

    def run(title: str) -> tuple[str, str]:
        page = open_list(locale, title=title)
        _open_panel(page)
        panel = page.evaluate(f"document.querySelector({json.dumps(PANEL)}).innerText")
        scroll_to(page, CONFIRM)
        page.click(CONFIRM)
        _wait_home(page, locale)
        return _normalized(panel, title), _normalized(_status(page)["text"], title)

    first = run("Alpha list")
    assert _list_status(wishlist_server, reserved) == "deleted"
    second = run("Beta list")

    assert first == second, f"texts differ between a reserved and an unreserved list: {first}"
    assert first[0] and first[1]
    assert (
        _list_status(
            wishlist_server,
            Seeded(int(quiet["id"]), "", [], reserved.owner_token, reserved.viewer_token),
        )
        == "deleted"
    )
