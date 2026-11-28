"""Failing browser repro for WISHENKA-294: a comfortable, reliable experience on every key screen.

Spec: ``ai-tasks/WISHENKA-294/20-architecture.md`` ("Test strategy for Step 3"). One module,
every screen and phone width (320, 360, 375, 390, 412 px) in Russian and English, one page and
one server per test (``CdpPage.set_viewport`` switches the width). Red tests (defects D1-D9)
fail on the unchanged code; ``test_control_*`` tests are positive controls that must stay green.

Hooks fixed here (Step 4 implements them exactly)
-------------------------------------------------
Mini App (``miniapp.js`` / ``miniapp.css``):

- ``#status[data-kind]`` with ``data-kind`` in ``pending | success | error``; ``aria-live`` is
  ``assertive`` for ``error`` and ``polite`` otherwise; the element is sticky at the top of the
  viewport, so a message written while the user is lower on the page is visible.
- A control whose action is running (favorite toggle, reset public link; the create button
  is only checked for duplicate POSTs) has ``disabled``, ``aria-busy="true"`` and the class
  ``is-pending``; ``#status`` shows ``nav.working`` with ``data-kind="pending"``; one tap
  burst sends exactly one request. After the response the new screen shows the success text
  with ``data-kind="success"``.
- A failed create shows ``miniapp.home.create_failed`` with ``data-kind="error"``.
- New catalog keys (RU and EN): ``nav.working``, ``web.common.request_failed``,
  ``web.unavailable.heading``, ``web.unavailable.description``, ``web.unavailable.auth``.

Server-rendered pages (``app.js``, ``base.html``, ``miniapp.css``):

- Feedback region ``#feedback`` (``FEEDBACK``), present in ``base.html`` on every server page,
  empty and hidden when idle. A request error (``htmx:sendError``, ``htmx:timeout`` or an
  unswapped error answer) of quick add fills it with ``web.common.request_failed``,
  ``data-kind="error"`` and ``role="alert"``; the region is inside the viewport.
- While a quick-add request is in flight ``#quick-add-form`` has ``aria-busy="true"`` and
  ``#btn-quick-add`` is ``disabled``; both are restored when it ends (success or error).
- ``#quick-add-bar``, ``#quick-add-input`` (at least 10rem wide), the last content ends above
  the bar (``--quick-add-clearance``).
- Unavailable page (``GET`` ``/share/<token>``, ``/web/wishlists/<id>``, ``/web/reservations``;
  404 and 401; ``Accept`` prefers ``text/html``; no ``HX-Request``): status preserved,
  ``text/html``, ``<html lang>``, ``.unavailable-card`` containing ``h1`` (heading) and a text
  paragraph (404: ``web.unavailable.description``, 401: ``web.unavailable.auth``) and
  ``a.unavailable-home`` (href ``/``, at least 44 px).
- ``:root`` font size is relative (no ``px``).
"""

from __future__ import annotations

import html
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

import httpx
import pytest

from tests.browser_cdp import CdpBrowser, CdpPage, PageWaitTimeout
from tests.browser_helpers import assert_clean_console, scroll_to
from tests.browser_screens import (  # noqa: F401
    APP_NAME,
    BOT_NAME,
    GEOMETRY_JS,
    VIEWPORT_HEIGHT,
    WIDTHS,
    ComfortData,
    api,
    assert_contrast_and_focus,
    assert_reachable,
    assert_screen_fits,
    assert_texts_present,
    bot_environment,
    catalog_text,
    configured_server,
    dialog_problems,
    open_miniapp,
    open_path,
    seed_comfort_wishlist,
    wait_for_width,
)
from tests.conftest import BrowserServer
from wishenka.i18n import SupportedLocale, t

pytestmark = [pytest.mark.timeout(45), pytest.mark.browser]

LOCALES: list[SupportedLocale] = ["en", "ru"]
FEEDBACK = "#feedback"
QUICK_FORM = "#quick-add-form"
QUICK_BUTTON = "#btn-quick-add"
QUICK_INPUT = "#quick-add-input"
NAV_HISTORY = ".home-top-nav button.home-nav-action"
WAIT = 3.0
# Server-rendered controls that are known to be too small (D4); everything else is a control.
D4_SUSPECTS = ("a.item-link", "select ", "a ", "summary ")

# Fetch wrapper installed before the Mini App boots (counts requests, forces 500, holds replies).
API_PRELOAD = """(() => {
  const real = window.fetch.bind(window);
  const state = {posts: [], mode: {}, waiters: []};
  state.releaseAll = () => state.waiters.splice(0).forEach(resolve => resolve());
  window.__t = state;
  const classify = (method, path) => {
    if (method === 'POST' && path === '/api/wishlists') return 'create';
    if (method !== 'GET' && path.startsWith('/api/favorites/')) return 'favorite';
    if (method === 'POST' && path.endsWith('/share/reset')) return 'reset';
    return null;
  };
  window.fetch = async (input, options = {}) => {
    const url = new URL(typeof input === 'string' ? input : input.url, location.href);
    const method = (options.method || 'GET').toUpperCase();
    const key = classify(method, url.pathname);
    if (key) state.posts.push(key);
    const mode = key ? (state.mode[key] || 'real') : 'real';
    if (mode === '500') {
      return new Response('{}', {status: 500, headers: {'content-type': 'application/json'}});
    }
    if (mode === 'hold') await new Promise(resolve => state.waiters.push(resolve));
    return real(input, options);
  };
})();"""

# XMLHttpRequest wrapper for the real htmx pages: modes real | error | hold.
XHR_WRAPPER = """(() => {
  const send = XMLHttpRequest.prototype.send;
  window.__x = {mode: 'real', sent: 0, held: []};
  XMLHttpRequest.prototype.send = function (body) {
    const xhr = this;
    window.__x.sent++;
    if (window.__x.mode === 'error') {
      setTimeout(() => xhr.dispatchEvent(new ProgressEvent('error')), 20);
      return;
    }
    if (window.__x.mode === 'hold') {
      window.__x.held.push(() => send.call(xhr, body));
      return;
    }
    return send.call(xhr, body);
  };
})()"""


# --- helpers ---------------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _bot_server(configured_server: BrowserServer) -> BrowserServer:  # noqa: F811
    """Every test of the module runs on a server with a configured bot (shared link texts)."""
    return configured_server


def _seed(server: BrowserServer, locale: SupportedLocale) -> ComfortData:
    return seed_comfort_wishlist(server, locale)


def _mini_detail(
    browser: CdpBrowser,
    pages: list[CdpPage],
    server: BrowserServer,
    data: ComfortData,
    *,
    token: str | None = None,
    viewport: tuple[int, int] = (412, VIEWPORT_HEIGHT),
    preload: str | None = None,
) -> CdpPage:
    """Mini App home, then the detail of the seeded wishlist (real ``showList``)."""
    page = open_miniapp(
        browser,
        pages,
        server,
        token or server.owner_token,
        data.locale,
        viewport=viewport,
        preload_script=preload,
    )
    page.evaluate(f"showList({data.seeded.wishlist_id})", await_promise=True)
    page.wait_for(
        "Mini App detail rendered",
        "!!document.querySelector('#app .list-title') && "
        "document.getElementById('status')?.innerText === ''",
        timeout=WAIT,
    )
    return page


def _expand_all(page: CdpPage) -> None:
    """Open every item card like a user (the real card script toggles ``aria-expanded``)."""
    page.evaluate("document.querySelectorAll('.item-card-summary').forEach(s => s.click())")
    page.wait_for(
        "all cards expanded",
        "Array.from(document.querySelectorAll('.item-card-summary'))"
        ".every(s => s.getAttribute('aria-expanded') === 'true')",
        timeout=WAIT,
    )


def _status(page: CdpPage) -> dict[str, Any]:
    result: dict[str, Any] = page.evaluate(
        """(() => {
          const s = document.getElementById('status');
          const r = s.getBoundingClientRect();
          return {text: s.innerText, kind: s.getAttribute('data-kind'),
            live: s.getAttribute('aria-live'), top: Math.round(r.top),
            bottom: Math.round(r.bottom), inside: r.bottom > 0 && r.top < window.innerHeight};
        })()"""
    )
    return result


# --- D1: unbroken long text widens server-rendered pages (A1, A2) ----------------------------


@pytest.mark.parametrize("locale", LOCALES)
def test_ssr_detail_page_fits_every_phone_width(
    locale: SupportedLocale,
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    """D1 (A1/A2): the owner's detail page has no horizontal scroll and no clipped text."""
    data = _seed(wishlist_server, locale)
    page = open_path(
        chromium_browser,
        _browser_pages,
        wishlist_server,
        f"/web/wishlists/{data.seeded.wishlist_id}",
        token=wishlist_server.owner_token,
    )
    _expand_all(page)
    assert_texts_present(page, "ssr_detail", [data.texts.description_unbroken, data.texts.unbroken])
    assert_screen_fits(page, f"ssr_detail[{locale}]")


@pytest.mark.parametrize("locale", LOCALES)
def test_public_share_page_fits_every_phone_width(
    locale: SupportedLocale,
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    """D1 (A1/A2): the anonymous public page has no horizontal scroll and no clipped text."""
    data = _seed(wishlist_server, locale)
    page = open_path(
        chromium_browser,
        _browser_pages,
        wishlist_server,
        f"/share/{data.seeded.public_token}?lang={locale}",
    )
    _expand_all(page)
    assert_texts_present(
        page, "public_share", [data.texts.description_unbroken, data.texts.unbroken]
    )
    assert_screen_fits(page, f"public_share[{locale}]")


# --- D2 and D3: the quick-add bar (A5, A3) ---------------------------------------------------


@pytest.mark.parametrize("locale", LOCALES)
def test_quick_add_input_keeps_a_usable_width(
    locale: SupportedLocale,
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    """D2 (A5): the quick-add field is at least 10rem wide at every width."""
    data = _seed(wishlist_server, locale)
    page = open_path(
        chromium_browser,
        _browser_pages,
        wishlist_server,
        f"/web/wishlists/{data.seeded.wishlist_id}",
        token=wishlist_server.owner_token,
    )
    report: list[str] = []
    for width in WIDTHS:
        wait_for_width(page, width)
        measured = page.evaluate(
            f"""({{field: document.querySelector({json.dumps(QUICK_INPUT)})
                .getBoundingClientRect().width,
              rem: parseFloat(getComputedStyle(document.documentElement).fontSize)}})"""
        )
        if measured["field"] < measured["rem"] * 10:
            report.append(f"@{width}px: input {measured['field']:.0f}px < 10rem")
    assert not report, f"quick-add input is squeezed: {report}\n{page.snapshot()}"


@pytest.mark.parametrize("locale", LOCALES)
def test_last_content_clears_the_quick_add_bar(
    locale: SupportedLocale,
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    """D3 (A3): scrolled to the end, the last content ends above the fixed quick-add bar."""
    data = _seed(wishlist_server, locale)
    page = open_path(
        chromium_browser,
        _browser_pages,
        wishlist_server,
        f"/web/wishlists/{data.seeded.wishlist_id}",
        token=wishlist_server.owner_token,
        viewport=(412, 700),
    )
    report: list[str] = []
    for width in WIDTHS:
        page.set_viewport(width, 700)
        page.wait_for(f"viewport {width}px applied", f"window.innerWidth === {width}")
        covered = page.evaluate(
            """(() => {
              window.scrollTo(0, document.documentElement.scrollHeight);
              const bar = document.getElementById('quick-add-bar').getBoundingClientRect();
              const bottoms = Array.from(document.querySelectorAll('main *'))
                .filter(el => !el.closest('#quick-add-bar') && !el.closest('[hidden]'))
                .map(el => el.getBoundingClientRect())
                .filter(r => r.width > 0 && r.height > 0).map(r => r.bottom);
              return Math.round(Math.max(...bottoms) - bar.top);
            })()"""
        )
        if covered > 0:
            report.append(f"@{width}px: last content is {covered}px under the quick-add bar")
    assert not report, f"content is hidden behind the bar: {report}\n{page.snapshot()}"


@pytest.mark.parametrize("locale", LOCALES)
def test_control_quick_add_button_stays_reachable(
    locale: SupportedLocale,
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    """Control (A3/A4): the Add button is visible, 44 px and not covered at every width."""
    data = _seed(wishlist_server, locale)
    page = open_path(
        chromium_browser,
        _browser_pages,
        wishlist_server,
        f"/web/wishlists/{data.seeded.wishlist_id}",
        token=wishlist_server.owner_token,
    )
    assert_reachable(page, "ssr_detail", QUICK_BUTTON, WIDTHS)
    for width in WIDTHS:
        wait_for_width(page, width)
        size = page.evaluate(
            f"(() => {{ const r = document.querySelector({json.dumps(QUICK_BUTTON)})"
            ".getBoundingClientRect(); return [r.width, r.height]; })()"
        )
        assert min(size) >= 43.5, f"@{width}px: Add button is {size}"


# --- D4: touch targets on server-rendered pages (A4) -----------------------------------------


def _undersized(page: CdpPage, width: int) -> list[str]:
    wait_for_width(page, width)
    result = page.evaluate(GEOMETRY_JS)
    # The quick-add field width belongs to D2 (its own test), not to the target-size audit.
    return [
        f"@{width}px {entry}"
        for entry in result["undersized"]
        if not entry.startswith("input#quick-add-input")
    ]


def _server_pages(
    server: BrowserServer,
    browser: CdpBrowser,
    pages: list[CdpPage],
    data: ComfortData,
) -> dict[str, CdpPage]:
    """Owner detail (cards expanded), giver share page and the reservations cabinet."""
    seeded = data.seeded
    detail = open_path(
        browser,
        pages,
        server,
        f"/web/wishlists/{seeded.wishlist_id}",
        token=server.owner_token,
    )
    _expand_all(detail)
    giver = open_path(
        browser, pages, server, f"/share/{seeded.public_token}", token=server.viewer_token
    )
    cabinet = open_path(browser, pages, server, "/web/reservations", token=server.viewer_token)
    return {"ssr_detail": detail, "giver_share": giver, "cabinet": cabinet}


@pytest.mark.parametrize("locale", LOCALES)
def test_server_pages_have_no_undersized_touch_targets(
    locale: SupportedLocale,
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    """D4 (A4): store link, "Go to wish" link and giver quantity select reach 44 px."""
    data = _seed(wishlist_server, locale)
    screens = _server_pages(wishlist_server, chromium_browser, _browser_pages, data)
    report: list[str] = []
    for name, page in screens.items():
        for width in WIDTHS:
            report.extend(f"{name} {line}" for line in _undersized(page, width))
    assert not report, "touch targets under 44 px:\n" + "\n".join(report)


@pytest.mark.parametrize("locale", LOCALES)
def test_control_server_buttons_and_fields_keep_touch_size(
    locale: SupportedLocale,
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    """Control (A4): everything on the same pages except the D4 suspects is already 44 px."""
    data = _seed(wishlist_server, locale)
    screens = _server_pages(wishlist_server, chromium_browser, _browser_pages, data)
    report: list[str] = []
    for name, page in screens.items():
        for width in WIDTHS:
            report.extend(
                f"{name} {line}"
                for line in _undersized(page, width)
                if not line.split(" ", 1)[1].startswith(D4_SUSPECTS)
            )
    assert not report, "touch targets under 44 px:\n" + "\n".join(report)


# --- D5: Mini App feedback out of sight (A6) -------------------------------------------------


@pytest.mark.parametrize("locale", LOCALES)
def test_copy_feedback_is_visible_and_typed_on_a_long_screen(
    locale: SupportedLocale,
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    """D5 (A6): after "Copy link" low on a long detail screen the message is in view."""
    data = _seed(wishlist_server, locale)
    page = _mini_detail(
        chromium_browser, _browser_pages, wishlist_server, data, viewport=(320, 568)
    )
    link = page.evaluate("document.querySelector('.share-panel--public .share-link-input').value")
    assert link.startswith(f"https://t.me/{BOT_NAME}/{APP_NAME}?startapp=p_"), link
    scroll_to(page, ".share-panel--public .share-copy-btn")
    assert page.evaluate("window.scrollY") > 300, "the screen must be scrolled for this check"
    page.click(".share-panel--public .share-copy-btn")
    copied = t("miniapp.share.link_copied", locale)
    failed = t("miniapp.share.copy_failed", locale)
    page.wait_for(
        "copy feedback written",
        f"[{json.dumps(copied)}, {json.dumps(failed)}]"
        ".includes(document.getElementById('status').innerText)",
        timeout=WAIT,
    )
    state = _status(page)
    kind = "success" if state["text"] == copied else "error"
    problems = []
    if state["kind"] != kind:
        problems.append(f"data-kind is {state['kind']!r}, expected {kind!r}")
    if not state["inside"]:
        problems.append(
            f"#status is out of sight (top {state['top']}px, bottom {state['bottom']}px)"
        )
    assert not problems, f"{problems}: {state}\n{page.snapshot()}"


# --- D6: duplicate submissions and failure feedback (A6) -------------------------------------


def _open_create_form(page: CdpPage, title: str) -> None:
    """Open the creation form from home and type a title (nothing is sent yet)."""
    page.click(".home-create-btn")
    page.wait_for("creation form", "!!document.querySelector('.wishlist-create-form')")
    page.evaluate(
        "(() => { const i = document.querySelector('.wishlist-create-form input[name=name]');"
        f" i.value = {json.dumps(title)};"
        " i.dispatchEvent(new Event('input', {bubbles: true})); })()"
    )


@pytest.mark.parametrize("locale", LOCALES)
def test_create_wishlist_burst_sends_a_single_post(
    locale: SupportedLocale,
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    """D6 (A6): three taps issued before the response resolves send one ``POST``.

    Since WISHENKA-296 the burst is sent on the creation form's Create button; only "no duplicate
    request per tap burst" is asserted, not the later state of the screen.
    """
    _seed(wishlist_server, locale)
    page = open_miniapp(
        chromium_browser,
        _browser_pages,
        wishlist_server,
        wishlist_server.owner_token,
        locale,
        preload_script=API_PRELOAD,
    )
    page.evaluate("window.__t.mode.create = 'hold'")
    _open_create_form(page, "Burst list")
    page.evaluate(
        "(() => { const b = document.querySelector('.create-submit-btn');"
        " b.click(); b.click(); b.click(); })()"
    )
    sent = page.evaluate("window.__t.posts.filter(k => k === 'create').length")
    page.evaluate("window.__t.releaseAll()")
    page.wait_for("created wishlist opened", "!!document.querySelector('#app .list-title')")
    total = page.evaluate("window.__t.posts.filter(k => k === 'create').length")
    assert (sent, total) == (1, 1), (
        f"a burst of 3 taps sent {sent} create requests (total {total}), expected 1\n"
        f"{page.snapshot()}"
    )


@pytest.mark.parametrize("locale", LOCALES)
def test_create_wishlist_failure_is_announced_as_an_error(
    locale: SupportedLocale,
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    """D6 (A6): a failed create shows the localized text typed as an assertive error."""
    _seed(wishlist_server, locale)
    page = open_miniapp(
        chromium_browser,
        _browser_pages,
        wishlist_server,
        wishlist_server.owner_token,
        locale,
        preload_script=API_PRELOAD,
    )
    page.evaluate("window.__t.mode.create = '500'")
    _open_create_form(page, "Failing list")
    page.click(".create-submit-btn")
    message = t("miniapp.home.create_failed", locale)
    page.wait_for(
        "create failure text",
        f"document.getElementById('status').innerText === {json.dumps(message)}",
        timeout=WAIT,
    )
    state = _status(page)
    problems = []
    if state["kind"] != "error":
        problems.append(f"data-kind is {state['kind']!r}, expected 'error'")
    if state["live"] != "assertive":
        problems.append(f"aria-live is {state['live']!r}, expected 'assertive'")
    assert not problems, f"{problems}: {state}\n{page.snapshot()}"


def _guard_problems(
    page: CdpPage, selector: str, key: str, locale: str, done_key: str
) -> list[str]:
    """Double tap a held action; describe every missing pending/guard behavior (A6)."""
    problems: list[str] = []
    quoted = json.dumps(selector)
    page.evaluate(f"window.__t.mode[{json.dumps(key)}] = 'hold'")
    page.evaluate(
        f"(() => {{ const b = document.querySelector({quoted}); b.click(); b.click(); }})()"
    )
    state = page.evaluate(
        f"""(() => {{
          const b = document.querySelector({quoted});
          const s = document.getElementById('status');
          return {{posts: window.__t.posts.filter(k => k === {json.dumps(key)}).length,
            disabled: b.disabled, busy: b.getAttribute('aria-busy'),
            pending: b.classList.contains('is-pending'), text: s.innerText,
            kind: s.getAttribute('data-kind')}};
        }})()"""
    )
    if state["posts"] != 1:
        problems.append(f"a double tap sent {state['posts']} requests, expected 1")
    if not (state["disabled"] and state["busy"] == "true" and state["pending"]):
        problems.append(
            f"control is not marked pending: disabled={state['disabled']} "
            f"aria-busy={state['busy']!r} is-pending={state['pending']}"
        )
    working = catalog_text("nav.working", locale, problems)
    if state["text"] != working or state["kind"] != "pending":
        problems.append(
            f"#status is {state['text']!r}/{state['kind']!r}, expected {working!r}/'pending'"
        )
    page.evaluate("window.__t.releaseAll()")
    done = t(done_key, locale)
    page.wait_for(
        "action finished",
        f"document.getElementById('status').innerText === {json.dumps(done)}",
        timeout=WAIT,
    )
    after = page.evaluate(
        f"""(() => {{
          const b = document.querySelector({quoted});
          return {{disabled: b.disabled, busy: b.getAttribute('aria-busy'),
            kind: document.getElementById('status').getAttribute('data-kind')}};
        }})()"""
    )
    if after["disabled"] or after["busy"]:
        problems.append(f"control did not recover: {after}")
    if after["kind"] != "success":
        problems.append(f"success text has data-kind {after['kind']!r}, expected 'success'")
    return problems


@pytest.mark.parametrize("locale", LOCALES)
def test_favorite_toggle_is_guarded_while_pending(
    locale: SupportedLocale,
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    """D6 (A6): the favorite toggle ignores a second tap and shows its pending state."""
    data = _seed(wishlist_server, locale)
    api(
        wishlist_server,
        wishlist_server.viewer_token,
        "POST",
        "/api/invitations/accept",
        headers={"x-invite-token": data.invite_token},
    )
    page = _mini_detail(
        chromium_browser,
        _browser_pages,
        wishlist_server,
        data,
        token=wishlist_server.viewer_token,
        preload=API_PRELOAD,
    )
    problems = _guard_problems(
        page, ".list-favorite-btn", "favorite", locale, "miniapp.list.added_favorite"
    )
    assert not problems, f"{problems}\n{page.snapshot()}"


@pytest.mark.parametrize("locale", LOCALES)
def test_reset_public_link_is_guarded_while_pending(
    locale: SupportedLocale,
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    """D6 (A6): "Replace public link" ignores a second tap and shows its pending state."""
    data = _seed(wishlist_server, locale)
    page = _mini_detail(
        chromium_browser, _browser_pages, wishlist_server, data, preload=API_PRELOAD
    )
    problems = _guard_problems(
        page, ".share-reset-btn", "reset", locale, "miniapp.share.public_replaced"
    )
    assert not problems, f"{problems}\n{page.snapshot()}"


# --- D7: unavailable states (A7) -------------------------------------------------------------

UNAVAILABLE_CASES = (
    ("/share/no-such-token", 404, "web.unavailable.description", None),
    ("/web/wishlists/999999", 404, "web.unavailable.description", "owner"),
    ("/web/reservations", 401, "web.unavailable.auth", None),
)


def _page_request(
    server: BrowserServer, path: str, locale: str, who: str | None, **headers: str
) -> httpx.Response:
    base = {"Accept": "text/html,application/xhtml+xml", "Accept-Language": locale}
    if who == "owner":
        base["Authorization"] = f"Bearer {server.owner_token}"
    return httpx.get(f"{server.base_url}{path}", headers={**base, **headers}, timeout=10)


@pytest.mark.parametrize("locale", LOCALES)
def test_unavailable_states_are_localized_html_pages(
    locale: SupportedLocale, wishlist_server: BrowserServer
) -> None:
    """D7 (A7): a bad link, a missing wishlist and a missing session answer with a page."""
    problems: list[str] = []
    for path, status, text_key, who in UNAVAILABLE_CASES:
        response = _page_request(wishlist_server, path, locale, who)
        body = response.text
        head = f"{path}:"
        if response.status_code != status:
            problems.append(f"{head} status {response.status_code}, expected {status}")
        if not response.headers["content-type"].startswith("text/html"):
            problems.append(f"{head} content-type {response.headers['content-type']!r}")
            continue
        if f'lang="{locale}"' not in body:
            problems.append(f"{head} <html lang> is not {locale!r}")
        heading = re.search(r"<h1[^>]*>(.*?)</h1>", body, re.S)
        expected_heading = catalog_text("web.unavailable.heading", locale, problems)
        if not heading or html.unescape(heading.group(1)).strip() != expected_heading:
            problems.append(f"{head} h1 is not {expected_heading!r}")
        expected_text = catalog_text(text_key, locale, problems)
        if expected_text not in html.unescape(body):
            problems.append(f"{head} text {expected_text!r} is missing")
        if "unavailable-card" not in body:
            problems.append(f"{head} no .unavailable-card")
        if not re.search(
            r'<a[^>]*href="/"[^>]*unavailable-home|<a[^>]*unavailable-home[^>]*href="/"', body
        ):
            problems.append(f"{head} no a.unavailable-home pointing to /")
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("locale", LOCALES)
def test_unavailable_page_renders_in_the_browser_and_fits(
    locale: SupportedLocale,
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    """D7 (A7): the page shows a heading and a 44 px home link without horizontal scroll."""
    report: list[str] = []
    for path, _status, _key, _who in UNAVAILABLE_CASES:
        page = open_path(
            chromium_browser,
            _browser_pages,
            wishlist_server,
            f"{path}?lang={locale}",
            token=wishlist_server.owner_token if path.startswith("/web/wishlists") else None,
        )
        for width in WIDTHS:
            wait_for_width(page, width)
            state = page.evaluate(
                """(() => {
                  const h1 = document.querySelector('.unavailable-card h1');
                  const home = document.querySelector('a.unavailable-home');
                  const r = home ? home.getBoundingClientRect() : null;
                  return {h1: h1 ? h1.innerText : null, home: !!home,
                    size: r ? [Math.round(r.width), Math.round(r.height)] : null,
                    scrollWidth: document.documentElement.scrollWidth,
                    innerWidth: window.innerWidth};
                })()"""
            )
            if not state["h1"] or not state["home"]:
                report.append(f"{path} @{width}px: no heading or home link {state}")
            elif min(state["size"]) < 44:
                report.append(f"{path} @{width}px: home link is {state['size']}")
            if state["scrollWidth"] > state["innerWidth"]:
                report.append(f"{path} @{width}px: horizontal scroll {state}")
    assert not report, "\n".join(report)


def test_unavailable_page_does_not_reveal_whether_a_wishlist_existed(
    wishlist_server: BrowserServer, tmp_path: Path
) -> None:
    """D7 (A7): missing, deleted and invalid links give the same 404 page, no title leaks."""
    data = _seed(wishlist_server, "en")
    wishlist_id = data.seeded.wishlist_id
    with sqlite3.connect(tmp_path / "browser.db") as connection:
        stored = connection.execute("SELECT status FROM wl_lists WHERE id = ?", (wishlist_id,))
        value = str(stored.fetchone()[0])
        deleted = "DELETED" if value.isupper() else "deleted"
        connection.execute("UPDATE wl_lists SET status = ? WHERE id = ?", (deleted, wishlist_id))
        connection.commit()
    token = data.seeded.public_token
    answers = {
        "missing": _page_request(wishlist_server, "/web/wishlists/999999", "en", "owner"),
        "deleted": _page_request(wishlist_server, f"/web/wishlists/{wishlist_id}", "en", "owner"),
        "deleted link": _page_request(wishlist_server, f"/share/{token}", "en", None),
        "invalid link": _page_request(wishlist_server, "/share/no-such-token", "en", None),
    }
    problems = []
    for name, response in answers.items():
        if response.status_code != 404:
            problems.append(f"{name}: status {response.status_code}")
        if not response.headers["content-type"].startswith("text/html"):
            problems.append(f"{name}: content-type {response.headers['content-type']!r}")
        if data.texts.title in html.unescape(response.text):
            problems.append(f"{name}: the page shows the title of the deleted wishlist")
    assert not problems, "\n".join(problems)
    bodies = {response.text for response in answers.values()}
    assert len(bodies) == 1, f"404 pages differ between cases: {list(answers)}"


def test_control_json_errors_stay_json_for_non_page_clients(
    wishlist_server: BrowserServer,
) -> None:
    """Control (A7): JSON clients, ``/api``, htmx requests and sub-paths keep their answers."""
    data = _seed(wishlist_server, "en")
    wishlist_id = data.seeded.wishlist_id
    owner = f"Bearer {wishlist_server.owner_token}"
    cases: list[tuple[str, dict[str, str], int]] = [
        ("/share/no-such-token", {"Accept": "*/*"}, 404),
        ("/share/no-such-token", {"Accept": "application/json"}, 404),
        ("/web/wishlists/999999", {"Accept": "application/json", "Authorization": owner}, 404),
        ("/web/reservations", {"Accept": "*/*"}, 401),
        ("/web/reservations", {"Accept": "application/json"}, 401),
        ("/api/wishlists/999999", {"Accept": "text/html", "Authorization": owner}, 404),
        (
            "/web/wishlists/999999",
            {"Accept": "text/html", "HX-Request": "true", "Authorization": owner},
            404,
        ),
        ("/static/missing.css", {"Accept": "text/html"}, 404),
        ("/no-such-route", {"Accept": "text/html"}, 404),
    ]
    problems = []
    for path, headers, status in cases:
        response = httpx.get(f"{wishlist_server.base_url}{path}", headers=headers, timeout=10)
        if response.status_code != status:
            problems.append(f"{path} {headers}: status {response.status_code}")
        if not response.headers["content-type"].startswith("application/json"):
            problems.append(f"{path} {headers}: content-type {response.headers['content-type']}")
    fragment = httpx.get(
        f"{wishlist_server.base_url}/web/wishlists/{wishlist_id}/items/999999/archive-confirm",
        headers={"Accept": "text/html", "Authorization": owner},
        timeout=10,
    )
    if fragment.status_code != 404 or "unavailable-card" in fragment.text:
        problems.append(f"item sub-path answer changed: {fragment.status_code}")
    assert not problems, "\n".join(problems)


# --- D8: root text size (A9) -----------------------------------------------------------------


@pytest.mark.parametrize("screen", ["mini_home", "ssr_detail"])
def test_root_font_size_follows_the_user_setting(
    screen: str,
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    """D8 (A9): the ``:root`` rule does not fix the text size in pixels."""
    data = _seed(wishlist_server, "en")
    if screen == "mini_home":
        page = open_miniapp(
            chromium_browser, _browser_pages, wishlist_server, wishlist_server.owner_token, "en"
        )
    else:
        page = open_path(
            chromium_browser,
            _browser_pages,
            wishlist_server,
            f"/web/wishlists/{data.seeded.wishlist_id}",
            token=wishlist_server.owner_token,
        )
    declared = page.evaluate(
        """(() => {
          for (const sheet of document.styleSheets) {
            let rules;
            try { rules = sheet.cssRules; } catch (_) { continue; }
            for (const rule of rules) {
              if (rule.selectorText === ':root' && rule.style.fontSize) {
                return rule.style.fontSize;
              }
            }
          }
          return null;
        })()"""
    )
    assert declared is not None, "no :root rule declares a font size"
    assert not str(declared).endswith("px"), f":root font size is fixed: {declared}"


def test_control_root_font_size_default_is_unchanged(
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    """Control (A9): the default root size stays 16 px (the scale only becomes relative)."""
    page = open_miniapp(
        chromium_browser, _browser_pages, wishlist_server, wishlist_server.owner_token, "en"
    )
    assert page.evaluate("getComputedStyle(document.documentElement).fontSize") == "16px"


# --- D9: htmx pending and failure feedback (A10) ---------------------------------------------


def _quick_add_page(
    server: BrowserServer,
    browser: CdpBrowser,
    pages: list[CdpPage],
    data: ComfortData,
    mode: str,
    *,
    timeout: float = WAIT,
) -> CdpPage:
    """Detail page with real htmx and the XHR wrapper in ``mode``; the field holds a title."""
    page = open_path(
        browser,
        pages,
        server,
        f"/web/wishlists/{data.seeded.wishlist_id}",
        token=server.owner_token,
        viewport=(390, VIEWPORT_HEIGHT),
        real_htmx=True,
    )
    page.wait_for("real htmx loaded", "typeof window.htmx === 'object'", timeout=timeout)
    page.evaluate(XHR_WRAPPER)
    page.evaluate(f"window.__x.mode = {json.dumps(mode)}")
    page.evaluate(f"document.querySelector({json.dumps(QUICK_INPUT)}).value = 'Gift'")
    return page


@pytest.mark.parametrize("locale", LOCALES)
def test_htmx_network_failure_is_announced(
    locale: SupportedLocale,
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    """D9 (A10): a network error on quick add shows a localized alert and unlocks the form."""
    data = _seed(wishlist_server, locale)
    page = _quick_add_page(wishlist_server, chromium_browser, _browser_pages, data, "error")
    page.click(QUICK_BUTTON)
    page.wait_for("request attempted", "window.__x.sent > 0", timeout=WAIT)
    problems: list[str] = []
    expected = catalog_text("web.common.request_failed", locale, problems)
    try:
        page.wait_for(
            "visible role=alert feedback",
            f"""(() => {{
              const f = document.querySelector({json.dumps(FEEDBACK)});
              if (!f || f.getAttribute('role') !== 'alert') return false;
              const r = f.getBoundingClientRect();
              return f.innerText.trim() === {json.dumps(expected)} && r.bottom > 0 &&
                r.top < window.innerHeight && f.getAttribute('data-kind') === 'error';
            }})()""",
            timeout=WAIT,
        )
    except PageWaitTimeout:
        problems.append(f"no visible {FEEDBACK}[role=alert][data-kind=error] with {expected!r}")
    state = page.evaluate(
        f"""({{busy: document.querySelector({json.dumps(QUICK_FORM)}).getAttribute('aria-busy'),
          disabled: document.querySelector({json.dumps(QUICK_BUTTON)}).disabled}})"""
    )
    if state["busy"] or state["disabled"]:
        problems.append(f"the form is still locked after the error: {state}")
    assert not problems, f"{problems}\n{page.snapshot()}"


def test_htmx_pending_request_marks_the_form_busy(
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    """D9 (A10): while quick add waits for the server the form is busy, then it recovers."""
    data = _seed(wishlist_server, "ru")
    page = _quick_add_page(
        wishlist_server, chromium_browser, _browser_pages, data, "hold", timeout=45
    )
    page.click(QUICK_BUTTON)
    page.wait_for("request held", "window.__x.held.length === 1", timeout=45)
    pending = page.evaluate(
        f"""({{busy: document.querySelector({json.dumps(QUICK_FORM)}).getAttribute('aria-busy'),
          disabled: document.querySelector({json.dumps(QUICK_BUTTON)}).disabled}})"""
    )
    problems = []
    if pending["busy"] != "true" or not pending["disabled"]:
        problems.append(f"in flight: aria-busy={pending['busy']!r} disabled={pending['disabled']}")
    page.evaluate("window.__x.held.splice(0).forEach(send => send())")
    page.wait_for(
        "new item rendered",
        "document.querySelectorAll('#items-list .item-card').length === 4",
        timeout=45,
    )
    after = page.evaluate(
        f"""({{busy: document.querySelector({json.dumps(QUICK_FORM)}).getAttribute('aria-busy'),
          disabled: document.querySelector({json.dumps(QUICK_BUTTON)}).disabled}})"""
    )
    if after["busy"] or after["disabled"]:
        problems.append(f"after the response the form stays locked: {after}")
    assert not problems, f"{problems}\n{page.snapshot()}"


# --- positive controls: screens that are already comfortable ---------------------------------


@pytest.mark.parametrize("locale", LOCALES)
def test_control_mini_home_and_history_fit(
    locale: SupportedLocale,
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    """Control (A1/A2/A3/A4): Mini App home (long titles, empty sections) and history fit."""
    data = _seed(wishlist_server, locale)
    owner = wishlist_server.owner_token
    for name in (data.texts.title, data.texts.other_title, data.texts.unbroken):
        created = api(wishlist_server, owner, "POST", "/api/wishlists", json={"name": name})
        api(wishlist_server, owner, "POST", f"/api/history/{created['id']}")
    api(wishlist_server, owner, "POST", f"/api/history/{data.seeded.wishlist_id}")
    page = open_miniapp(chromium_browser, _browser_pages, wishlist_server, owner, locale)
    assert_texts_present(page, "mini_home", [data.texts.title])
    assert_screen_fits(page, f"mini_home[{locale}]", targets=True)
    assert_reachable(page, "mini_home", ".home-create-btn", WIDTHS)
    page.click(NAV_HISTORY)
    page.wait_for("history rows", "document.querySelectorAll('li.history-card').length >= 4")
    assert_screen_fits(page, f"history[{locale}]", targets=True)
    assert_reachable(page, "history", ".history-open", WIDTHS)
    assert_clean_console(page)
    # Empty sections of the second user explain themselves.
    empty = open_miniapp(
        chromium_browser, _browser_pages, wishlist_server, wishlist_server.viewer_token, locale
    )
    states = empty.evaluate(
        "Array.from(document.querySelectorAll('.empty-state'), e => ["
        "e.querySelector('.empty-notice')?.innerText.trim(),"
        " e.querySelector('.empty-hint')?.innerText.trim()])"
    )
    assert states, "the second user has no empty section"
    assert all(notice and hint for notice, hint in states), states
    assert_screen_fits(empty, f"mini_home_empty[{locale}]", targets=True)


@pytest.mark.parametrize("locale", LOCALES)
def test_control_mini_detail_fits(
    locale: SupportedLocale,
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    """Control (A1/A2/A3/A4): Mini App detail with long texts, share panels and members."""
    data = _seed(wishlist_server, locale)
    page = _mini_detail(chromium_browser, _browser_pages, wishlist_server, data)
    assert_texts_present(
        page,
        "mini_detail",
        [data.wishlist_name, data.wishlist_description, data.texts.other_title],
    )
    assert page.evaluate("document.querySelectorAll('.share-link-input').length") == 2
    assert_screen_fits(page, f"mini_detail[{locale}]", targets=True)
    assert_reachable(page, "mini_detail", ".settings-save-btn", WIDTHS)
    assert_reachable(page, "mini_detail", ".share-copy-btn", WIDTHS)
    assert_clean_console(page)


@pytest.mark.parametrize("locale", LOCALES)
def test_control_settings_and_invitations_fit(
    locale: SupportedLocale,
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    """Control (A1/A2/A4): personal settings, a valid and an invalid invitation fit."""
    data = _seed(wishlist_server, locale)
    settings = open_path(
        chromium_browser,
        _browser_pages,
        wishlist_server,
        "/settings",
        token=wishlist_server.owner_token,
        real_htmx=True,
    )
    settings.wait_for("settings loaded", "!!document.querySelector('#birthdate-form')")
    assert_screen_fits(settings, f"settings[{locale}]", targets=True)
    for label, path, primary in (
        ("invite_valid", f"/invite/{data.invite_token}", "#invite-card button"),
        ("invite_invalid", "/invite/no-such-token", "a.btn-primary"),
    ):
        page = open_path(chromium_browser, _browser_pages, wishlist_server, f"{path}?lang={locale}")
        assert_screen_fits(page, f"{label}[{locale}]", targets=True)
        assert_reachable(page, label, primary, WIDTHS)


def _dialog_report(
    server: BrowserServer,
    browser: CdpBrowser,
    pages: list[CdpPage],
    data: ComfortData,
    part: str,
) -> list[str]:
    """Open the add, edit, archive and receipt dialogs like a user; collect ``part`` problems."""
    page = open_path(
        browser,
        pages,
        server,
        f"/web/wishlists/{data.seeded.wishlist_id}",
        token=server.owner_token,
        real_htmx=True,
    )
    page.wait_for("real htmx loaded", "typeof window.htmx === 'object'", timeout=WAIT)
    first = data.seeded.item_ids[0]
    page.evaluate(f"document.querySelector('#item-card-{first} .item-card-summary').click()")
    page.evaluate(
        f"document.querySelector({json.dumps(QUICK_INPUT)}).value = {json.dumps(data.texts.title)}"
    )
    openers = (
        ("add", "#btn-quick-details", "#item-edit-sheet"),
        ("edit", f"#item-card-{first} .btn-edit-item", "#item-edit-sheet"),
        ("archive", f"#item-card-{first} .btn-archive-confirm", "#item-archive-modal"),
        ("receipt", f"#item-card-{first} .btn-receipt-item", "#item-receipt-modal"),
    )
    report: list[str] = []
    for name, opener, dialog in openers:
        page.evaluate("document.getElementById('item-modal-container').replaceChildren()")
        page.evaluate(f"document.querySelector({json.dumps(opener)}).click()")
        page.wait_for(f"{name} dialog opened", f"!!document.querySelector({json.dumps(dialog)})")
        report.extend(dialog_problems(page, f"dialog {name}[{data.locale}]", dialog, part))
    assert_clean_console(page)
    return report


@pytest.mark.parametrize("locale", LOCALES)
def test_dialog_content_wraps_long_text(
    locale: SupportedLocale,
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    """D1 (A1/A2): long item titles and long labels stay inside the item dialogs."""
    data = _seed(wishlist_server, locale)
    report = _dialog_report(wishlist_server, chromium_browser, _browser_pages, data, "content")
    assert not report, "\n".join(report)


@pytest.mark.parametrize("locale", LOCALES)
def test_control_dialogs_sit_inside_the_viewport(
    locale: SupportedLocale,
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    """Control (A1): add, edit, archive and receipt sheets stay in the viewport at every width."""
    data = _seed(wishlist_server, locale)
    report = _dialog_report(wishlist_server, chromium_browser, _browser_pages, data, "placement")
    assert not report, "\n".join(report)


@pytest.mark.parametrize("locale", LOCALES)
def test_control_contrast_and_focus_on_every_screen(
    locale: SupportedLocale,
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    """Control (A8): text meets WCAG AA and a keyboard-focused control has an outline."""
    data = _seed(wishlist_server, locale)
    seeded = data.seeded
    home = open_miniapp(
        chromium_browser, _browser_pages, wishlist_server, wishlist_server.owner_token, locale
    )
    assert_contrast_and_focus(home, f"mini_home[{locale}]")
    home.evaluate(f"showList({seeded.wishlist_id})", await_promise=True)
    home.wait_for("detail rendered", "!!document.querySelector('#app .list-title')")
    assert_contrast_and_focus(home, f"mini_detail[{locale}]")
    detail = open_path(
        chromium_browser,
        _browser_pages,
        wishlist_server,
        f"/web/wishlists/{seeded.wishlist_id}",
        token=wishlist_server.owner_token,
    )
    _expand_all(detail)
    assert_contrast_and_focus(detail, f"ssr_detail[{locale}]")
    screens = (
        ("public_share", f"/share/{seeded.public_token}?lang={locale}", None),
        ("giver_share", f"/share/{seeded.public_token}", wishlist_server.viewer_token),
        ("cabinet", "/web/reservations", wishlist_server.viewer_token),
        ("settings", "/settings", wishlist_server.owner_token),
    )
    for label, path, token in screens:
        page = open_path(chromium_browser, _browser_pages, wishlist_server, path, token=token)
        assert_contrast_and_focus(page, f"{label}[{locale}]")
