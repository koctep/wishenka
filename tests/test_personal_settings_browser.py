"""Browser acceptance checks for personal settings and mutation reconciliation."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any, Literal

import httpx
import pytest

from tests.browser_cdp import CdpBrowser, CdpPage
from tests.browser_helpers import Seeded, scroll_to
from tests.conftest import OWNER_TELEGRAM_ID, VIEWER_TELEGRAM_ID, BrowserServer
from tests.test_home_overview_browser import _set_user_locale
from wishenka.i18n import t

pytestmark = [pytest.mark.timeout(45), pytest.mark.browser]


def _assert_unknown(message: str) -> None:
    assert re.search(
        r"unknown|uncertain|unavailable|could not|unable|reload|refresh", message, re.I
    ), message


def _open(
    browser: CdpBrowser,
    pages: list[CdpPage],
    server: BrowserServer,
    seeded: Seeded,
    width: int = 375,
) -> CdpPage:
    page = browser.new_page((width, 800), use_real_htmx=True)
    pages.append(page)
    page.set_cookie("session_id", seeded.owner_token, server.base_url)
    page.navigate(f"{server.base_url}/settings")
    page.wait_for("settings loaded", "!!document.querySelector('#birthdate-form')")
    return page


def _api(
    server: BrowserServer, seeded: Seeded, method: str, path: str, **kwargs: Any
) -> dict[str, Any]:
    response = httpx.request(
        method,
        f"{server.base_url}{path}",
        headers={"Authorization": f"Bearer {seeded.owner_token}"},
        timeout=10,
        **kwargs,
    )
    response.raise_for_status()
    result: dict[str, Any] = response.json()
    return result


def _click(page: CdpPage, selector: str) -> None:
    scroll_to(page, selector)
    page.click(selector)


def _retry(page: CdpPage, feedback_id: str) -> None:
    result = page.evaluate(f"""(() => {{
      const feedback = document.getElementById({json.dumps(feedback_id)});
      const section = feedback.closest('section');
      const retry = Array.from(section.querySelectorAll('button, a')).find(el =>
        /retry|try again|reload|refresh/i.test(el.textContent) && !el.disabled &&
        el.getClientRects().length);
      if (!retry) return false;
      retry.click(); return true;
    }})()""")
    assert result, "The error must offer a visible localized retry action"


def _intercept(page: CdpPage, path: str, mode: str, *, fail_read: bool = False) -> None:
    """Wrap real fetch; the commit mode persists before replacing its response with 500."""
    page.evaluate(
        """((target, mode, failRead) => {
          const real = window.fetch.bind(window);
          window.testRequests = [];
          window.testFinished = false;
          window.testReadCount = 0;
          window.testFailRead = failRead;
          window.fetch = async (input, options = {}) => {
            const path = new URL(input, location.href).pathname;
            const method = (options.method || 'GET').toUpperCase();
            window.testRequests.push({path, method});
            if (window.testFailRead && method === 'GET' &&
                (path === '/api/profile/preferences' ||
                 path.includes('/notifications/wishlists/'))) {
              window.testReadCount++;
              return new Response('{}', {status: 503});
            }
            if (path === target && method !== 'GET') {
              let result;
              if (mode === 'commit') {
                await real(input, options);
                result = new Response('{}', {status: 500});
              } else if (mode === 'reject') {
                result = new Response(JSON.stringify({detail: 'Rejected'}), {status: 422});
              } else {
                window.testFinished = true;
                throw new TypeError('simulated network loss');
              }
              window.testFinished = true;
              return result;
            }
            return real(input, options);
          };
        })("""
        + json.dumps(path)
        + ","
        + json.dumps(mode)
        + ","
        + json.dumps(fail_read)
        + ")"
    )


@pytest.mark.parametrize("locale", ["en", "ru"])
@pytest.mark.parametrize("width", [320, 375])
def test_settings_sections_visible_states_and_mobile_layout(
    locale: Literal["en", "ru"],
    width: int,
    seed_wishlist: Callable[..., Seeded],
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    seeded = seed_wishlist(["Camera"])
    _set_user_locale(wishlist_server, seeded.owner_token, OWNER_TELEGRAM_ID, "Owner", locale)
    page = _open(chromium_browser, _browser_pages, wishlist_server, seeded, width)
    result = page.evaluate("""(() => {
      const headings = ['language', 'birthdate', 'birthday-reminders', 'notifications',
        'wishlists', 'delete-account'].map(id => document.getElementById(id + '-heading'));
      const rows = Array.from(document.querySelectorAll('input[data-global-category]'), input => {
        const label = input.closest('label');
        return {checked: input.checked, text: label.innerText, name: label.textContent.trim()};
      });
      const inputs = Array.from(document.querySelectorAll('.settings-page button, '
        + '.settings-page select, .settings-page input'), e => {
        const r = e.getBoundingClientRect();
        return {visible: !!(r.width && r.height), width: r.width, height: r.height};
      }).filter(x => x.visible);
      return {headings: headings.map(e => !!e && !!e.innerText.trim()), rows, inputs,
        scrollWidth: document.documentElement.scrollWidth, width: innerWidth,
        danger: !!document.querySelector('.settings-danger-zone #delete-account-start-btn')};
    })()""")
    assert all(result["headings"]), result
    assert result["danger"] and result["scrollWidth"] <= result["width"], result
    assert result["rows"], result
    enabled = t("settings.state.enabled", locale)
    disabled = t("settings.state.disabled", locale)
    for row in result["rows"]:
        assert (enabled if row["checked"] else disabled) in row["text"], row
    assert all(control["height"] >= 44 for control in result["inputs"]), result


def test_global_update_changes_inherited_badge_and_persists(
    seed_wishlist: Callable[..., Seeded],
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    seeded = seed_wishlist(["Camera"])
    _set_user_locale(wishlist_server, seeded.owner_token, OWNER_TELEGRAM_ID, "Owner", "en")
    _api(
        wishlist_server,
        seeded,
        "PUT",
        "/api/profile/notifications/global",
        json={"settings": {"reminders": False}},
    )
    page = _open(chromium_browser, _browser_pages, wishlist_server, seeded)
    selector = 'input[data-global-category="reminders"]'
    badge = f'[data-effective-for="{seeded.wishlist_id}-reminders"] strong'
    assert (
        page.evaluate(f"document.querySelector({json.dumps(badge)}).textContent.trim()")
        == "Disabled"
    )
    _click(page, selector)
    page.wait_for(
        "global saved",
        "document.querySelector('#global-notifications-feedback').textContent.trim()",
    )
    assert _api(wishlist_server, seeded, "GET", "/api/profile/preferences")["global_notifications"][
        "reminders"
    ]
    assert (
        page.evaluate(f"document.querySelector({json.dumps(badge)}).textContent.trim()")
        == "Enabled"
    )
    page.navigate(f"{wishlist_server.base_url}/settings")
    assert page.evaluate(f"document.querySelector({json.dumps(selector)}).checked") is True


@pytest.mark.parametrize("mode", ["reject", "network", "commit"])
@pytest.mark.parametrize("target", ["global", "wishlist"])
def test_failed_preference_update_never_confirms_stale_value(
    mode: str,
    target: str,
    seed_wishlist: Callable[..., Seeded],
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    seeded = seed_wishlist(["Camera"])
    _set_user_locale(wishlist_server, seeded.owner_token, OWNER_TELEGRAM_ID, "Owner", "en")
    page = _open(chromium_browser, _browser_pages, wishlist_server, seeded)
    path = (
        "/api/profile/notifications/global"
        if target == "global"
        else f"/api/profile/notifications/wishlists/{seeded.wishlist_id}"
    )
    selector = (
        'input[data-global-category="reminders"]'
        if target == "global"
        else f'select[data-wishlist-id="{seeded.wishlist_id}"][data-category="reminders"]'
    )
    initial = page.evaluate(
        f"document.querySelector({json.dumps(selector)})."
        + ("checked" if target == "global" else "value")
    )
    _intercept(page, path, mode)
    if target == "global":
        _click(page, selector)
    else:
        page.evaluate(f"""(() => {{ const el = document.querySelector({json.dumps(selector)});
          el.value = 'false'; el.dispatchEvent(new Event('change', {{bubbles: true}})); }})()""")
    page.wait_for("intercepted mutation", "window.testFinished")
    page.wait_for(
        "feedback",
        "document.querySelector('#"
        + (
            "global-notifications-feedback"
            if target == "global"
            else "wishlist-notifications-feedback"
        )
        + "').textContent.trim()",
    )
    feedback_id = f"{target}-notifications-feedback"
    state = page.evaluate(f"""(() => {{ const el = document.querySelector({json.dumps(selector)});
      return {{value: {"el.checked" if target == "global" else "el.value"}, disabled: el.disabled,
        feedback: document.getElementById({json.dumps(feedback_id)}).textContent.trim()}}; }})()""")
    if mode == "reject":
        assert state["value"] == initial and not state["disabled"], state
    elif mode == "commit":
        expected = not initial if target == "global" else "false"
        assert state["value"] == expected and not state["disabled"], state
        assert state["feedback"] != t("settings.saved", "en"), state
        assert page.evaluate(
            "window.testRequests.some(r => r.method === 'GET' && r.path.includes('/api/profile/'))"
        ), state
    else:
        assert state["value"] == initial and not state["disabled"], state
        assert state["feedback"], state


def test_birthdate_clear_failure_is_visible_and_keeps_draft(
    seed_wishlist: Callable[..., Seeded],
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    seeded = seed_wishlist(["Camera"])
    _set_user_locale(wishlist_server, seeded.owner_token, OWNER_TELEGRAM_ID, "Owner", "en")
    page = _open(chromium_browser, _browser_pages, wishlist_server, seeded)
    page.evaluate(
        "document.querySelector('#birth-day').value = '15'; "
        "document.querySelector('#birth-month').value = '8'"
    )
    _intercept(page, "/api/profile/birthdate", "reject")
    _click(page, "#birthdate-clear-btn")
    page.wait_for("clear response", "window.testFinished")
    page.wait_for(
        "clear failure feedback",
        "!!document.querySelector('#birthdate-feedback').textContent.trim()",
    )
    assert page.evaluate("document.querySelector('#birth-day').value") == "15"
    assert page.evaluate("document.querySelector('#birth-month').value") == "8"
    assert page.evaluate("document.querySelector('#birthdate-feedback').textContent.trim()")


@pytest.mark.parametrize("target", ["global", "wishlist"])
def test_ambiguous_preference_and_failed_read_disable_control(
    target: str,
    seed_wishlist: Callable[..., Seeded],
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    seeded = seed_wishlist(["Camera"])
    _set_user_locale(wishlist_server, seeded.owner_token, OWNER_TELEGRAM_ID, "Owner", "en")
    page = _open(chromium_browser, _browser_pages, wishlist_server, seeded)
    path = (
        "/api/profile/notifications/global"
        if target == "global"
        else f"/api/profile/notifications/wishlists/{seeded.wishlist_id}"
    )
    selector = (
        'input[data-global-category="reminders"]'
        if target == "global"
        else f'select[data-wishlist-id="{seeded.wishlist_id}"][data-category="reminders"]'
    )
    initial = page.evaluate(
        f"document.querySelector({json.dumps(selector)})."
        + ("checked" if target == "global" else "value")
    )
    _intercept(page, path, "commit", fail_read=True)
    if target == "global":
        _click(page, selector)
    else:
        page.evaluate(
            f"""(() => {{ const el = document.querySelector({json.dumps(selector)});
              el.value = 'false'; el.dispatchEvent(new Event('change', {{bubbles: true}})); }})()"""
        )
    page.wait_for("committed response", "window.testFinished")
    page.wait_for(
        "uncertain state",
        f"document.querySelector({json.dumps(selector)}).disabled && window.testReadCount > 0 && "
        "document.querySelector('#"
        + (
            "global-notifications-feedback"
            if target == "global"
            else "wishlist-notifications-feedback"
        )
        + "').textContent.trim()",
    )
    feedback = (
        "global-notifications-feedback" if target == "global" else "wishlist-notifications-feedback"
    )
    message = page.evaluate(f"document.getElementById({json.dumps(feedback)}).textContent.trim()")
    assert message and message != t("settings.saved", "en")
    _assert_unknown(message)
    assert page.evaluate("""(() => {
      const input = document.querySelector('#birth-day');
      if (input.disabled) return false;
      input.value = '12'; input.dispatchEvent(new Event('input', {bubbles:true}));
      return input.value === '12';
    })()""")
    page.evaluate("window.testFailRead = false")
    _retry(page, feedback)
    page.wait_for("reconciled control", f"!document.querySelector({json.dumps(selector)}).disabled")
    value = page.evaluate(
        f"document.querySelector({json.dumps(selector)})."
        + ("checked" if target == "global" else "value")
    )
    assert value == (not initial if target == "global" else "false")
    assert not page.evaluate(f"document.querySelector({json.dumps(selector)}).disabled")


def test_birthdate_ambiguous_commit_and_failed_read_does_not_claim_old_value(
    seed_wishlist: Callable[..., Seeded],
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    seeded = seed_wishlist(["Camera"])
    _set_user_locale(wishlist_server, seeded.owner_token, OWNER_TELEGRAM_ID, "Owner", "en")
    page = _open(chromium_browser, _browser_pages, wishlist_server, seeded)
    page.evaluate(
        "document.querySelector('#birth-day').value = '15'; "
        "document.querySelector('#birth-month').value = '8'"
    )
    _intercept(page, "/api/profile/birthdate", "commit", fail_read=True)
    _click(page, '#birthdate-form button[type="submit"]')
    page.wait_for("date mutation committed", "window.testFinished")
    result = _api(wishlist_server, seeded, "GET", "/api/profile/preferences")
    assert result["birthdate"]["day"] == 15
    page.wait_for(
        "date uncertainty",
        "window.testReadCount > 0 && "
        "document.querySelector('#birthdate-feedback').textContent.trim() && "
        "document.querySelector('#birthdate-form button[type=submit]').disabled && "
        "document.querySelector('#birthdate-clear-btn').disabled",
    )
    message = page.evaluate("document.querySelector('#birthdate-feedback').textContent.trim()")
    assert message and message != t("settings.saved", "en")
    _assert_unknown(message)
    page.evaluate("window.testFailRead = false")
    _retry(page, "birthdate-feedback")
    page.wait_for("birthdate retry", "!document.querySelector('#birthdate-clear-btn').disabled")
    assert page.evaluate("document.querySelector('#birth-day').value") == "15"
    assert not page.evaluate("document.querySelector('#birthdate-clear-btn').disabled")


def test_deletion_preview_failure_prevents_confirmation_and_retrying_post(
    seed_wishlist: Callable[..., Seeded],
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    seeded = seed_wishlist(["Camera"])
    page = _open(chromium_browser, _browser_pages, wishlist_server, seeded)
    page.evaluate("""(() => {
      const real = window.fetch.bind(window); window.deletionCalls = [];
      window.fetch = async (input, options = {}) => {
        const path = new URL(input, location.href).pathname;
        window.deletionCalls.push({path, method: options.method || 'GET'});
        if (path === '/api/profile/deletion-preview') throw new TypeError('offline');
        return real(input, options);
      };
    })()""")
    _click(page, "#delete-account-start-btn")
    page.wait_for(
        "preview failure feedback",
        "document.querySelector('#delete-account-feedback').textContent.trim()",
    )
    assert page.evaluate("document.querySelector('#delete-account-confirm-panel').hidden")
    assert not page.evaluate("window.deletionCalls.some(c => c.path === '/api/profile/delete')")


def test_deletion_pending_blocks_duplicate_submissions(
    seed_wishlist: Callable[..., Seeded],
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    seeded = seed_wishlist(["Camera"])
    page = _open(chromium_browser, _browser_pages, wishlist_server, seeded)
    page.evaluate("""(() => {
      const real = window.fetch.bind(window); window.deleteCount = 0;
      window.fetch = async (input, options = {}) => {
        const path = new URL(input, location.href).pathname;
        if (path === '/api/profile/delete') {
          window.deleteCount++;
          return await new Promise(resolve => { window.finishDelete = resolve; });
        }
        return real(input, options);
      };
    })()""")
    _click(page, "#delete-account-start-btn")
    page.wait_for(
        "preview shown", "!document.querySelector('#delete-account-confirm-panel').hidden"
    )
    _click(page, "#delete-account-confirm-btn")
    page.wait_for("delete request pending", "window.deleteCount === 1")
    assert page.evaluate("document.querySelector('#delete-account-confirm-btn').disabled")
    page.evaluate("document.querySelector('#delete-account-confirm-btn').click()")
    assert page.evaluate("window.deleteCount") == 1


def test_wishlist_override_modes_persist_and_do_not_affect_other_category(
    seed_wishlist: Callable[..., Seeded],
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    seeded = seed_wishlist(["Camera"])
    _set_user_locale(wishlist_server, seeded.owner_token, OWNER_TELEGRAM_ID, "Owner", "en")
    page = _open(chromium_browser, _browser_pages, wishlist_server, seeded)
    path = f"/api/profile/notifications/wishlists/{seeded.wishlist_id}"
    selector = f'select[data-wishlist-id="{seeded.wishlist_id}"][data-category="reminders"]'
    other_before = _api(wishlist_server, seeded, "GET", path)["overrides"]["gift_received"]
    for value, expected in (("true", True), ("false", False), ("inherit", None)):
        page.evaluate(
            f"""(() => {{ const e = document.querySelector({json.dumps(selector)});
              document.querySelector('#wishlist-notifications-feedback').textContent = '';
              e.value = {json.dumps(value)}; e.dispatchEvent(new Event('change', {{bubbles:true}}));
            }})()"""
        )
        page.wait_for(
            "override saved",
            "document.querySelector('#wishlist-notifications-feedback')"
            ".textContent.trim() === 'Saved.'",
        )
        actual = _api(wishlist_server, seeded, "GET", path)["overrides"]
        assert actual["reminders"] is expected and actual["gift_received"] == other_before
    page.navigate(f"{wishlist_server.base_url}/settings")
    assert page.evaluate(f"document.querySelector({json.dumps(selector)}).value") == "inherit"


def test_deletion_cancel_never_posts(
    seed_wishlist: Callable[..., Seeded],
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    seeded = seed_wishlist(["Camera"])
    page = _open(chromium_browser, _browser_pages, wishlist_server, seeded)
    _click(page, "#delete-account-start-btn")
    page.wait_for("preview", "!document.querySelector('#delete-account-confirm-panel').hidden")
    assert page.evaluate(
        "document.querySelector('#delete-account-confirm-panel [role=alert]').textContent.trim()"
    )
    _click(page, "#delete-account-cancel-btn")
    assert page.evaluate("document.querySelector('#delete-account-confirm-panel').hidden")
    assert not any(request.path == "/api/profile/delete" for request in page.requests)
    assert _api(wishlist_server, seeded, "GET", "/api/profile/preferences")


@pytest.mark.parametrize("year", ["", "1992"])
def test_birthdate_save_is_independent_of_birthday_reminders(
    year: str,
    seed_wishlist: Callable[..., Seeded],
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    seeded = seed_wishlist(["Camera"])
    _set_user_locale(wishlist_server, seeded.owner_token, OWNER_TELEGRAM_ID, "Owner", "en")
    before = _api(wishlist_server, seeded, "GET", "/api/profile/preferences")["birthday_reminders"]
    page = _open(chromium_browser, _browser_pages, wishlist_server, seeded)
    page.evaluate(
        "document.querySelector('#birth-day').value = '15'; "
        "document.querySelector('#birth-month').value = '8'; "
        f"document.querySelector('#birth-year').value = {json.dumps(year)}"
    )
    _click(page, '#birthdate-form button[type="submit"]')
    page.wait_for("date saved", "document.querySelector('#birthdate-feedback').textContent.trim()")
    result = _api(wishlist_server, seeded, "GET", "/api/profile/preferences")
    assert result["birthdate"]["day"] == 15 and result["birthdate"]["month"] == 8
    assert result["birthdate"]["year"] == (int(year) if year else None)
    assert result["birthdate"]["source"] == "explicit"
    assert result["birthday_reminders"] == before


def test_locale_selection_persists_after_reload(
    seed_wishlist: Callable[..., Seeded],
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    seeded = seed_wishlist(["Camera"])
    _set_user_locale(wishlist_server, seeded.owner_token, OWNER_TELEGRAM_ID, "Owner", "en")
    page = _open(chromium_browser, _browser_pages, wishlist_server, seeded)
    _click(page, '.locale-option[hx-vals*="ru"]')
    page.wait_for("Russian locale saved", "document.documentElement.lang === 'ru'")
    page.navigate(f"{wishlist_server.base_url}/settings")
    page.wait_for(
        "reloaded settings page",
        "!!document.querySelector('.locale-option[hx-vals*=\"ru\"]')",
    )
    assert page.evaluate("document.documentElement.lang") == "ru"
    assert (
        page.evaluate(
            "document.querySelector('.locale-option[hx-vals*=\"ru\"]').getAttribute('aria-pressed')"
        )
        == "true"
    )


@pytest.mark.parametrize("width", [320, 375])
def test_long_russian_wishlist_title_does_not_overlap_controls(
    width: int,
    seed_wishlist: Callable[..., Seeded],
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    seeded = seed_wishlist(["Camera"])
    _set_user_locale(wishlist_server, seeded.owner_token, OWNER_TELEGRAM_ID, "Owner", "ru")
    name = "Очень длинное название списка подарков " * 4
    created = _api(wishlist_server, seeded, "POST", "/api/wishlists", json={"name": name})
    page = _open(chromium_browser, _browser_pages, wishlist_server, seeded, width)
    result = page.evaluate(f"""(() => {{
      const card = document.querySelector('article[data-wishlist-id="{created["id"]}"]');
      const controls = Array.from(card.querySelectorAll('select,button,input'), e => {{
        const r = e.getBoundingClientRect();
        return {{left:r.left, right:r.right, top:r.top, bottom:r.bottom, height:r.height}};
      }});
      const overlaps = controls.some((a, i) => controls.slice(i+1).some(b =>
        a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom));
      return {{count:controls.length, overlaps, controls, width:innerWidth,
        scrollWidth:document.documentElement.scrollWidth,
        title:card.querySelector('h3').innerText}};
    }})()""")
    assert result["count"] >= 4 and result["title"] == name.strip(), result
    assert result["scrollWidth"] <= result["width"] and not result["overlaps"], result
    assert all(control["height"] >= 44 for control in result["controls"]), result


def test_global_inheritance_updates_only_inheriting_list(
    seed_wishlist: Callable[..., Seeded],
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    seeded = seed_wishlist(["Camera"])
    _set_user_locale(wishlist_server, seeded.owner_token, OWNER_TELEGRAM_ID, "Owner", "en")
    second = _api(wishlist_server, seeded, "POST", "/api/wishlists", json={"name": "Second"})
    global_path = "/api/profile/notifications/global"
    second_path = f"/api/profile/notifications/wishlists/{second['id']}"
    _api(wishlist_server, seeded, "PUT", global_path, json={"settings": {"reminders": False}})
    _api(wishlist_server, seeded, "PUT", second_path, json={"overrides": {"reminders": False}})
    page = _open(chromium_browser, _browser_pages, wishlist_server, seeded)
    first_badge = f'[data-effective-for="{seeded.wishlist_id}-reminders"] strong'
    second_badge = f'[data-effective-for="{second["id"]}-reminders"] strong'
    _click(page, 'input[data-global-category="reminders"]')
    page.wait_for(
        "global update",
        "document.querySelector('#global-notifications-feedback').textContent.trim() === 'Saved.'",
    )
    assert (
        page.evaluate(f"document.querySelector({json.dumps(first_badge)}).textContent.trim()")
        == "Enabled"
    )
    assert (
        page.evaluate(f"document.querySelector({json.dumps(second_badge)}).textContent.trim()")
        == "Disabled"
    )
    assert _api(wishlist_server, seeded, "GET", second_path)["overrides"]["reminders"] is False


def test_pending_global_mutation_prevents_conflicting_override(
    seed_wishlist: Callable[..., Seeded],
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    seeded = seed_wishlist(["Camera"])
    page = _open(chromium_browser, _browser_pages, wishlist_server, seeded)
    page.evaluate("""(() => {
      const real = window.fetch.bind(window); window.globalPending = false;
      window.fetch = async (input, options = {}) => {
        if (new URL(input, location.href).pathname === '/api/profile/notifications/global') {
          window.globalPending = true;
          await new Promise(resolve => { window.releaseGlobal = resolve; });
        }
        return real(input, options);
      };
    })()""")
    _click(page, 'input[data-global-category="reminders"]')
    page.wait_for("pending request", "window.globalPending")
    selector = f'select[data-wishlist-id="{seeded.wishlist_id}"][data-category="reminders"]'
    assert page.evaluate(f"document.querySelector({json.dumps(selector)}).disabled")
    page.evaluate("window.releaseGlobal()")


def test_invalid_birthdate_and_clear_success_preserve_reminders(
    seed_wishlist: Callable[..., Seeded],
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    seeded = seed_wishlist(["Camera"])
    _set_user_locale(wishlist_server, seeded.owner_token, OWNER_TELEGRAM_ID, "Owner", "en")
    before = _api(wishlist_server, seeded, "GET", "/api/profile/preferences")["birthday_reminders"]
    page = _open(chromium_browser, _browser_pages, wishlist_server, seeded)
    page.evaluate(
        "document.querySelector('#birth-day').value = '31'; "
        "document.querySelector('#birth-month').value = '2'"
    )
    _click(page, '#birthdate-form button[type="submit"]')
    page.wait_for(
        "invalid date feedback", "document.querySelector('#birthdate-feedback').textContent.trim()"
    )
    assert page.evaluate("document.querySelector('#birth-day').value") == "31"
    assert page.evaluate("document.querySelector('#birthdate-feedback').textContent.trim()") != t(
        "settings.saved", "en"
    )
    _click(page, "#birthdate-clear-btn")
    page.wait_for("date cleared", "document.querySelector('#birth-day').value === ''")
    result = _api(wishlist_server, seeded, "GET", "/api/profile/preferences")
    assert result["birthdate"]["day"] is None
    assert result["birthday_reminders"] == before


def test_deletion_preview_displays_authoritative_counts(
    seed_wishlist: Callable[..., Seeded],
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    seeded = seed_wishlist(["Camera"])
    preview = _api(wishlist_server, seeded, "GET", "/api/profile/deletion-preview")
    page = _open(chromium_browser, _browser_pages, wishlist_server, seeded)
    _click(page, "#delete-account-start-btn")
    page.wait_for("preview", "!document.querySelector('#delete-account-confirm-panel').hidden")
    for selector, key in (
        ("impact-personal", "personal_lists_count"),
        ("impact-transferred", "collaborative_transferred_count"),
        ("impact-collab-deleted", "collaborative_deleted_count"),
        ("impact-reservations", "reservations_count"),
    ):
        assert (
            int(page.evaluate(f"document.getElementById({json.dumps(selector)}).textContent"))
            == preview[key]
        )


@pytest.mark.parametrize("mode", ["reject", "network", "server"])
def test_deletion_failure_never_retries_and_shows_feedback(
    mode: str,
    seed_wishlist: Callable[..., Seeded],
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    seeded = seed_wishlist(["Camera"])
    page = _open(chromium_browser, _browser_pages, wishlist_server, seeded)
    page.evaluate(
        """((mode) => {
      const real = window.fetch.bind(window); window.deleteAttempts = 0;
      window.fetch = async (input, options = {}) => {
        if (new URL(input, location.href).pathname === '/api/profile/delete') {
          window.deleteAttempts++;
          if (mode === 'network') throw new TypeError('network lost');
          return new Response('{}', {status: mode === 'reject' ? 422 : 500});
        }
        return real(input, options);
      };
    })("""
        + json.dumps(mode)
        + ")"
    )
    _click(page, "#delete-account-start-btn")
    page.wait_for("preview", "!document.querySelector('#delete-account-confirm-panel').hidden")
    _click(page, "#delete-account-confirm-btn")
    page.wait_for(
        "delete failure feedback",
        "document.querySelector('#delete-account-feedback').textContent.trim()",
    )
    assert page.evaluate("window.deleteAttempts") == 1
    assert _api(wishlist_server, seeded, "GET", "/api/profile/preferences")
    if mode != "reject":
        assert page.evaluate("document.querySelector('#delete-account-confirm-btn').disabled")


@pytest.mark.parametrize(
    ("mode", "fail_read"),
    [("reject", False), ("network", False), ("commit", False), ("commit", True)],
)
def test_locale_failure_reconciles_or_reports_unknown(
    mode: str,
    fail_read: bool,
    seed_wishlist: Callable[..., Seeded],
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    seeded = seed_wishlist(["Camera"])
    _set_user_locale(wishlist_server, seeded.owner_token, OWNER_TELEGRAM_ID, "Owner", "en")
    page = _open(chromium_browser, _browser_pages, wishlist_server, seeded)
    page.evaluate(
        """((mode, failRead) => {
      const realFetch = window.fetch.bind(window);
      const realOpen = XMLHttpRequest.prototype.open;
      const realSend = XMLHttpRequest.prototype.send;
      window.localeAttempted = false; window.localeFinished = false;
      window.localeFailRead = failRead;
      window.fetch = async (input, options = {}) => {
        if (window.localeFailRead &&
            new URL(input, location.href).pathname === '/api/profile/preferences') {
          return new Response('{}', {status: 503});
        }
        if (new URL(input, location.href).pathname === '/api/profile/locale' &&
            (options.method || 'GET').toUpperCase() !== 'GET') {
          window.localeAttempted = true;
          if (mode === 'network') {
            window.localeFinished = true;
            throw new TypeError('network lost');
          }
          if (mode === 'commit') await realFetch(input, options);
          window.localeFinished = true;
          return new Response('{}', {status: mode === 'reject' ? 422 : 500});
        }
        return realFetch(input, options);
      };
      XMLHttpRequest.prototype.open = function(method, url, ...rest) {
        this.localeTarget = new URL(url, location.href).pathname === '/api/profile/locale';
        if (this.localeTarget && mode === 'reject') {
          return realOpen.call(this, 'GET', '/api/profile/preferences', ...rest);
        }
        return realOpen.call(this, method, url, ...rest);
      };
      XMLHttpRequest.prototype.send = function(body) {
        if (!this.localeTarget) return realSend.call(this, body);
        window.localeAttempted = true;
        if (mode === 'network') {
          setTimeout(() => {
            this.abort(); window.localeFinished = true;
            this.dispatchEvent(new ProgressEvent('error'));
          }, 0);
          return;
        }
        const xhr = this;
        this.addEventListener('readystatechange', () => {
          if (xhr.readyState !== 4) return;
          window.localeFinished = true;
          Object.defineProperty(xhr, 'status', {value: mode === 'reject' ? 422 : 500});
          const readHeader = xhr.getResponseHeader.bind(xhr);
          xhr.getResponseHeader = name => name.toLowerCase() === 'hx-refresh'
            ? null : readHeader(name);
        });
        return realSend.call(this, mode === 'reject' ? null : body);
      };
    })("""
        + json.dumps(mode)
        + ","
        + json.dumps(fail_read)
        + ")"
    )
    _click(page, '.locale-option[hx-vals*="ru"]')
    page.wait_for("locale attempted", "window.localeAttempted")
    page.wait_for("locale request finished", "window.localeFinished")
    actual = _api(wishlist_server, seeded, "GET", "/api/profile/preferences")["locale"]
    assert actual == ("ru" if mode == "commit" else "en")
    page.wait_for(
        "locale error or unknown",
        "document.querySelector('#locale-feedback').textContent.trim()",
    )
    state = page.evaluate("""(() => ({
      en: document.querySelector('.locale-option[hx-vals*="en"]').getAttribute('aria-pressed'),
      ru: document.querySelector('.locale-option[hx-vals*="ru"]').getAttribute('aria-pressed'),
      disabled: document.querySelector('.locale-option').disabled,
      feedback: document.querySelector('#locale-feedback').textContent.trim()
    }))()""")
    assert state["feedback"] != t("settings.saved", "en"), state
    if fail_read:
        assert state["disabled"], state
        _assert_unknown(state["feedback"])
        page.evaluate("window.localeFailRead = false")
        _retry(page, "locale-feedback")
        page.wait_for("locale retry", "document.documentElement.lang === 'ru'")
        assert page.evaluate("document.documentElement.lang") == actual
    else:
        assert not state["disabled"] and state[actual] == "true", state


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_empty_wishlist_preferences_show_guidance_and_keyboard_focus(
    locale: Literal["en", "ru"],
    seed_wishlist: Callable[..., Seeded],
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    seeded = seed_wishlist(["Camera"])
    _set_user_locale(wishlist_server, seeded.viewer_token, VIEWER_TELEGRAM_ID, "Viewer", locale)
    page = chromium_browser.new_page((375, 800), use_real_htmx=True)
    _browser_pages.append(page)
    page.set_cookie("session_id", seeded.viewer_token, wishlist_server.base_url)
    page.navigate(f"{wishlist_server.base_url}/settings")
    page.wait_for("settings", "!!document.querySelector('#birthdate-form')")
    result = page.evaluate("""(() => {
      const empty = document.querySelector('[aria-labelledby="wishlists-heading"] .empty-state');
      const button = document.querySelector('#delete-account-start-btn');
      button.focus();
      return {empty: empty && empty.innerText.trim(), focused: document.activeElement === button,
        live: document.querySelector('#global-notifications-feedback').getAttribute('aria-live')};
    })()""")
    assert result["empty"] == t("settings.wishlists_empty", locale), result
    assert result["focused"] and result["live"] == "polite", result


def test_birthday_reminder_toggle_is_independent_of_birthdate(
    seed_wishlist: Callable[..., Seeded],
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    seeded = seed_wishlist(["Camera"])
    _set_user_locale(wishlist_server, seeded.owner_token, OWNER_TELEGRAM_ID, "Owner", "en")
    before = _api(wishlist_server, seeded, "GET", "/api/profile/preferences")
    page = _open(chromium_browser, _browser_pages, wishlist_server, seeded)
    _click(page, "#toggle-birthday-reminders")
    page.wait_for(
        "birthday reminder saved",
        "document.querySelector('#birthday-reminders-feedback').textContent.trim() === 'Saved.'",
    )
    after = _api(wishlist_server, seeded, "GET", "/api/profile/preferences")
    assert after["birthday_reminders"] is not before["birthday_reminders"]
    assert after["birthdate"] == before["birthdate"]
    page.navigate(f"{wishlist_server.base_url}/settings")
    assert (
        page.evaluate("document.querySelector('#toggle-birthday-reminders').checked")
        is after["birthday_reminders"]
    )


def test_delete_account_preserves_other_user_data_and_preview_privacy(
    seed_wishlist: Callable[..., Seeded],
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    seeded = seed_wishlist(["Camera"])
    _set_user_locale(wishlist_server, seeded.owner_token, OWNER_TELEGRAM_ID, "Owner", "en")
    private_title = "Other user private list"
    with httpx.Client(
        base_url=wishlist_server.base_url,
        headers={"Authorization": f"Bearer {seeded.viewer_token}"},
        timeout=10,
    ) as viewer:
        created = viewer.post("/api/wishlists", json={"name": private_title})
        created.raise_for_status()
        other_id = created.json()["id"]
        page = _open(chromium_browser, _browser_pages, wishlist_server, seeded)
        _click(page, "#delete-account-start-btn")
        page.wait_for("preview", "!document.querySelector('#delete-account-confirm-panel').hidden")
        assert private_title not in page.evaluate(
            "document.querySelector('#delete-account-confirm-panel').innerText"
        )
        _click(page, "#delete-account-confirm-btn")
        page.wait_for(
            "deletion result",
            "document.querySelector('#delete-account-feedback')"
            ".textContent.trim() && document.querySelector('#delete-account-confirm-panel')"
            ".hidden",
        )
        response = viewer.get(f"/api/wishlists/{other_id}")
        response.raise_for_status()
        assert response.json()["name"] == private_title
