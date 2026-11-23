"""Browser repro for WISHENKA-295 (Step 3): the owner deletes a wishlist from its settings.

Real Chromium against the real Mini App and server. Today the owner's settings have no delete
action, so every test fails at the first interaction with ``.wishlist-delete-*``. The tests
assert the designed behavior (``20-architecture.md`` D-3, D-5, D-6): a separated destructive
zone outside the settings form, an inline confirmation with the exact title and the real days,
Cancel as the default focus, a guarded single request, a clear result on the home screen, a
failure path that keeps the panel, restoration from "Recently deleted", layout at narrow widths
and identical texts whatever the reservations. Admin/member gating and invalid retention are
covered by ``test_wishlist_delete_ui.py`` and ``test_wishlist_delete_api.py``.
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
    """JS that wraps ``fetch`` for ``DELETE <path>``: count calls, then hold, fail or pass."""
    return f"""(() => {{
      const real = window.fetch.bind(window);
      window.deleteCalls = 0; window.deleteMode = {json.dumps(mode)}; window.releaseDelete = null;
      window.fetch = async (input, options = {{}}) => {{
        const url = new URL(input, location.href);
        if ((options.method || 'GET') === 'DELETE' && url.pathname === {json.dumps(path)}) {{
          window.deleteCalls += 1;
          if (window.deleteMode === 'fail') return new Response('{{}}', {{status: 500}});
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
