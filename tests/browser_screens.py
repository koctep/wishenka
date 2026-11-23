"""Shared helpers for the browser tests that audit many screens (WISHENKA-289 and later).

Moved here from ``test_home_overview_browser.py`` (the old private names stay importable there):
``telegram_init_data``, ``provision_user`` and ``open_miniapp``. New for WISHENKA-294: the
page-side measurement scripts (``GEOMETRY_JS``, ``CONTRAST_JS``), ``assert_screen_fits``,
``long_texts``, ``seed_comfort_wishlist`` and the ``configured_server`` fixture (a test server
with a configured bot name, so the Mini App share panels render a link and a copy button).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
import pytest

from tests.browser_cdp import CdpBrowser, CdpPage
from tests.browser_helpers import Seeded
from tests.conftest import OWNER_TELEGRAM_ID, VIEWER_TELEGRAM_ID, BrowserServer
from wishenka.config import Settings
from wishenka.i18n import SupportedLocale, t

WIDTHS = (320, 360, 375, 390, 412)
VIEWPORT_HEIGHT = 800
BOT_NAME = "wishenka_test_bot"
APP_NAME = "wishenka"
UNBROKEN_WORD = "W" * 80
UNBROKEN_DESCRIPTION = "D" * 240
LONG_URL = "https://example.com/" + "a" * 100
LONG_TITLES: dict[str, str] = {
    "en": "Very long family birthday wishlist title to verify mobile card wrapping cleanly",
    "ru": "Очень длинный семейный вишлист для большого праздника и проверки переноса текста",
}
MEMBER_NAME = "Maximilian Alexander Wolfeschlegelstein"


# --- moved from test_home_overview_browser.py ------------------------------------------------


def telegram_init_data(telegram_id: int, first_name: str, language: SupportedLocale) -> str:
    """Create signed Telegram WebApp initData using default test bot token."""
    user = json.dumps(
        {"id": telegram_id, "first_name": first_name, "language_code": language},
        separators=(",", ":"),
    )
    fields = {"auth_date": str(int(time.time())), "user": user}
    check = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", Settings().bot_token.encode("utf-8"), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode("utf-8"), hashlib.sha256).hexdigest()
    return urlencode(fields)


def provision_user(
    server: BrowserServer,
    token: str,
    telegram_id: int,
    first_name: str,
    language: SupportedLocale,
) -> None:
    """Ensure user exists in DB and persist explicit locale for Mini App shell & API."""
    init_data = telegram_init_data(telegram_id, first_name, language)
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(base_url=server.base_url, headers=headers, timeout=10) as api:
        auth_resp = api.post(
            "/api/auth/telegram",
            json={"init_data": init_data},
            headers={"Origin": server.base_url},
        )
        auth_resp.raise_for_status()
        locale_resp = api.patch("/api/profile/locale", json={"locale": language})
        locale_resp.raise_for_status()


def open_miniapp(
    browser: CdpBrowser,
    pages: list[CdpPage],
    server: BrowserServer,
    token: str,
    locale: SupportedLocale,
    *,
    viewport: tuple[int, int] = (412, 800),
    query: str = "",
    preload_script: str | None = None,
) -> CdpPage:
    """Open Mini App home with session cookie and wait until showHome settles."""
    browser.ensure_alive()
    page = browser.new_page(viewport)
    pages.append(page)
    page.set_cookie("session_id", token, server.base_url)
    if preload_script:
        page._send("Page.addScriptToEvaluateOnNewDocument", {"source": preload_script})
    url = f"{server.base_url}/" if not query else f"{server.base_url}/?{query}"
    page.navigate(url)
    expected_title = json.dumps(t("miniapp.home.title", locale))
    page.wait_for(
        f"home overview settled ({locale})",
        f"document.querySelector('#app h1')?.innerText === {expected_title} "
        "&& document.getElementById('status')?.innerText === '' "
        "&& document.querySelectorAll('.wishlist-section').length >= 3",
    )
    return page


# --- fixtures --------------------------------------------------------------------------------


@pytest.fixture
def bot_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configure the bot and Mini App names (read by ``Settings`` when the server starts)."""
    monkeypatch.setenv("WISHENKA_TELEGRAM_BOT_USERNAME", BOT_NAME)
    monkeypatch.setenv("WISHENKA_TELEGRAM_APP_SHORT_NAME", APP_NAME)


@pytest.fixture
def configured_server(bot_environment: None, wishlist_server: BrowserServer) -> BrowserServer:
    """The per-test server started with a configured bot name (share links are rendered).

    ``bot_environment`` is listed first, so the variables are set before the server fixture
    builds its ``Settings``. Request this fixture before any page factory.
    """
    return wishlist_server


# --- long texts and seeding ------------------------------------------------------------------


@dataclass(frozen=True)
class LongTexts:
    """Long fixture strings for one locale."""

    title: str
    other_title: str
    unbroken: str
    description_unbroken: str
    url: str


def long_texts(locale: str) -> LongTexts:
    """Long title in the locale, the other language's long title, an 80-character unbroken word,
    a 240-character unbroken description and a 120-character URL."""
    other = "ru" if locale == "en" else "en"
    return LongTexts(
        title=LONG_TITLES[locale],
        other_title=LONG_TITLES[other],
        unbroken=UNBROKEN_WORD,
        description_unbroken=UNBROKEN_DESCRIPTION,
        url=LONG_URL,
    )


@dataclass(frozen=True)
class ComfortData:
    """Everything ``seed_comfort_wishlist`` created, for building expectations."""

    seeded: Seeded
    locale: SupportedLocale
    texts: LongTexts
    invite_token: str
    archived_item_id: str
    reserved_item_id: str
    wishlist_name: str
    wishlist_description: str


def api(server: BrowserServer, token: str, method: str, path: str, **kwargs: Any) -> Any:
    """REST call as ``token`` (test setup only); raises on a non-2xx answer."""
    response = httpx.request(
        method,
        f"{server.base_url}{path}",
        headers={"Authorization": f"Bearer {token}", **kwargs.pop("headers", {})},
        timeout=10,
        **kwargs,
    )
    response.raise_for_status()
    return response.json() if response.content else None


def seed_comfort_wishlist(server: BrowserServer, locale: SupportedLocale) -> ComfortData:
    """Owner (long name) wishlist with every long field and a second user holding a reservation.

    The wishlist carries a title, a 240-character unbroken description, an event, four items
    (long title, unbroken recipient, 240-character item description, 120-character link,
    quantity 3, price, category) and one archived item. The owner has a long first name (the
    author line of the server pages; the API member rows always read "User <id>"); the second
    user (outside the list) reserved one item. Setup is checked over the API, so a red run is
    never a broken fixture.
    """
    texts = long_texts(locale)
    provision_user(server, server.owner_token, OWNER_TELEGRAM_ID, MEMBER_NAME, locale)
    provision_user(server, server.viewer_token, VIEWER_TELEGRAM_ID, "Viewer", locale)
    owner = server.owner_token
    name = f"{texts.title} {texts.unbroken}"
    description = f"{texts.title} {texts.description_unbroken}"
    wishlist = api(
        server,
        owner,
        "POST",
        "/api/wishlists",
        json={
            "name": name,
            "description": description,
            "event_title": texts.other_title,
            "event_date": "2026-09-15T12:00:00Z",
        },
    )
    wishlist_id = int(wishlist["id"])
    item_ids: list[str] = []
    for index in range(4):
        body: dict[str, Any] = {
            "title": f"{texts.title} {texts.unbroken}" if index < 2 else f"Camera {index}",
            "description": f"{texts.title} {texts.description_unbroken}",
            "quantity": 3,
            "price": 1999,
            "category": "Home and garden category",
        }
        if index < 2:
            body["link"] = texts.url
            body["recipient_name"] = texts.unbroken
        item_ids.append(
            str(api(server, owner, "POST", f"/api/wishlists/{wishlist_id}/items", json=body)["id"])
        )
    archived = item_ids.pop()
    api(server, owner, "POST", f"/api/wishlists/{wishlist_id}/items/{archived}/archive")
    reserved = item_ids[-1]
    api(
        server,
        server.viewer_token,
        "POST",
        f"/api/public/wishlists/{wishlist['share_token']}/items/{reserved}/reservations",
        json={"quantity": 1},
    )
    stored = api(server, owner, "GET", f"/api/wishlists/{wishlist_id}")
    assert stored["name"] == name and stored["description"] == description, stored
    active = [str(item["id"]) for item in stored["items"] if not item["is_archived"]]
    assert active == item_ids, stored
    return ComfortData(
        seeded=Seeded(
            wishlist_id=wishlist_id,
            public_token=str(wishlist["share_token"]),
            item_ids=item_ids,
            owner_token=server.owner_token,
            viewer_token=server.viewer_token,
        ),
        locale=locale,
        texts=texts,
        invite_token=str(wishlist["invite_token"]),
        archived_item_id=archived,
        reserved_item_id=reserved,
        wishlist_name=name,
        wishlist_description=description,
    )


def open_path(
    browser: CdpBrowser,
    pages: list[CdpPage],
    server: BrowserServer,
    path: str,
    *,
    token: str | None = None,
    viewport: tuple[int, int] = (412, VIEWPORT_HEIGHT),
    real_htmx: bool = False,
) -> CdpPage:
    """Open a server-rendered ``path`` with an optional session cookie (locale from profile)."""
    browser.ensure_alive()
    page = browser.new_page(viewport, use_real_htmx=real_htmx)
    pages.append(page)
    page.clear_cookies()
    if token is not None:
        page.set_cookie("session_id", token, server.base_url)
    page.navigate(f"{server.base_url}{path}")
    return page


# --- page-side measurements ------------------------------------------------------------------

_JS_COMMON = """
  const shown = el => {
    if (el.closest('[hidden]')) return false;
    const style = getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden') return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const label = el => el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') +
    (typeof el.className === 'string' && el.className.trim()
      ? '.' + el.className.trim().split(/\\s+/).join('.') : '');
  const NON_CONTENT = new Set(['SCRIPT', 'STYLE', 'HEAD', 'META', 'LINK', 'TITLE', 'NOSCRIPT']);
"""

GEOMETRY_JS = (
    "(() => {"
    + _JS_COMMON
    + """
  const vw = window.innerWidth;
  const all = Array.from(document.body.querySelectorAll('*'))
    .filter(el => !NON_CONTENT.has(el.tagName) && shown(el));
  const offscreen = all.filter(el => {
    const r = el.getBoundingClientRect();
    return r.right > vw + 1 || r.left < -1;
  }).slice(0, 6).map(el => {
    const r = el.getBoundingClientRect();
    return `${label(el)} [${Math.round(r.left)}..${Math.round(r.right)}]`;
  });
  const NO_BOX = new Set(['INPUT', 'SELECT', 'TEXTAREA', 'OPTION']);
  const clipped = all.filter(el => !NO_BOX.has(el.tagName) && el.children.length === 0 &&
    el.textContent.trim() && getComputedStyle(el).display !== 'inline' &&
    el.scrollWidth > el.clientWidth + 1).slice(0, 6).map(
    el => `${label(el)} "${el.textContent.trim().slice(0, 24)}" ` +
      `scroll ${el.scrollWidth} > box ${el.clientWidth}`);
  const TARGETS = 'button, a[href], select, summary, ' +
    'input:not([type=hidden]):not([type=checkbox]):not([type=radio]):not([readonly])';
  const undersized = all.filter(el => el.matches(TARGETS)).filter(el => {
    const r = el.getBoundingClientRect();
    return r.width < 43.5 || r.height < 43.5;
  }).slice(0, 12).map(el => {
    const r = el.getBoundingClientRect();
    return `${label(el)} ${Math.round(r.width)}x${Math.round(r.height)}`;
  });
  return {scrollWidth: document.documentElement.scrollWidth, innerWidth: vw,
    offscreen, clipped, undersized};
})()"""
)

CONTRAST_JS = (
    "(() => {"
    + _JS_COMMON
    + """
  const parse = value => {
    const m = value.match(/rgba?\\(([^)]+)\\)/);
    if (!m) return null;
    const p = m[1].split(',').map(x => parseFloat(x));
    return {r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1};
  };
  const over = (top, under) => ({
    r: top.r * top.a + under.r * (1 - top.a), g: top.g * top.a + under.g * (1 - top.a),
    b: top.b * top.a + under.b * (1 - top.a), a: 1});
  const background = el => {
    const layers = [];
    for (let node = el; node; node = node.parentElement) {
      const c = parse(getComputedStyle(node).backgroundColor);
      if (c && c.a > 0) layers.push(c);
      if (c && c.a === 1) break;
    }
    let result = {r: 255, g: 255, b: 255, a: 1};
    for (const layer of layers.reverse()) result = over(layer, result);
    return result;
  };
  const lum = c => {
    const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
    return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
  };
  const failures = [];
  for (const el of document.body.querySelectorAll('*')) {
    if (NON_CONTENT.has(el.tagName) || el.disabled || !shown(el)) continue;
    const own = Array.from(el.childNodes).some(
      n => n.nodeType === 3 && n.textContent.trim());
    if (!own) continue;
    const style = getComputedStyle(el);
    const fg = parse(style.color);
    if (!fg) continue;
    const bg = background(el);
    const text = over(fg, bg);
    const a = lum(text) + 0.05, b = lum(bg) + 0.05;
    const ratio = Math.max(a, b) / Math.min(a, b);
    const size = parseFloat(style.fontSize);
    const large = size >= 24 || (size >= 18.66 && parseInt(style.fontWeight, 10) >= 700);
    if (ratio < (large ? 3 : 4.5)) {
      failures.push(`${label(el)} ${ratio.toFixed(2)} "${el.textContent.trim().slice(0, 24)}"`);
    }
  }
  return failures.slice(0, 8);
})()"""
)


def wait_for_width(page: CdpPage, width: int) -> None:
    """Resize the tab and wait (bounded) until the page sees the new inner width."""
    page.set_viewport(width, VIEWPORT_HEIGHT)
    page.wait_for(f"viewport {width}px applied", f"window.innerWidth === {width}")


def width_problems(
    page: CdpPage,
    width: int,
    *,
    fit: bool = True,
    text: bool = True,
    targets: bool = False,
) -> list[str]:
    """Measure the page at ``width`` and describe every violation of A1, A2 and A4."""
    wait_for_width(page, width)
    result = page.evaluate(GEOMETRY_JS)
    problems: list[str] = []
    if fit and result["scrollWidth"] > result["innerWidth"]:
        problems.append(
            f"A1 horizontal scroll: scrollWidth {result['scrollWidth']} > "
            f"innerWidth {result['innerWidth']}"
        )
    if fit and result["offscreen"]:
        problems.append(f"A1 elements outside the viewport: {result['offscreen']}")
    if text and result["clipped"]:
        problems.append(f"A2 text wider than its box: {result['clipped']}")
    if targets and result["undersized"]:
        problems.append(f"A4 targets under 44 px: {result['undersized']}")
    return problems


def assert_screen_fits(
    page: CdpPage,
    label: str,
    widths: Sequence[int] = WIDTHS,
    *,
    fit: bool = True,
    text: bool = True,
    targets: bool = False,
) -> None:
    """Assert A1/A2 (and optionally A4) at every width; one message lists all violations."""
    report: list[str] = []
    for width in widths:
        report.extend(
            f"{label} @{width}px: {problem}"
            for problem in width_problems(page, width, fit=fit, text=text, targets=targets)
        )
    assert not report, "\n".join(report) + f"\n{page.snapshot()}"


def assert_texts_present(page: CdpPage, label: str, expected: Sequence[str]) -> None:
    """Assert A2: every fixture string is reachable in full in the text or in a field value."""
    missing = page.evaluate(
        f"""((expected) => {{
          const text = document.body.innerText;
          const values = Array.from(document.querySelectorAll('input, textarea'), e => e.value);
          return expected.filter(s => !text.includes(s) && !values.some(v => v.includes(s)));
        }})({json.dumps(list(expected))})"""
    )
    assert not missing, f"{label}: long text is cut or missing: {missing}\n{page.snapshot()}"


def assert_contrast_and_focus(page: CdpPage, label: str) -> None:
    """A8: no text below WCAG AA and a visible focus outline after ``Tab``."""
    failures = page.evaluate(CONTRAST_JS)
    assert not failures, f"{label}: text below WCAG AA contrast: {failures}"
    page.evaluate("document.activeElement && document.activeElement.blur()")
    page.press_key("Tab")
    focus = page.evaluate(
        """(() => {
          const el = document.activeElement;
          if (!el || el === document.body) return null;
          const s = getComputedStyle(el);
          return {tag: el.tagName, style: s.outlineStyle, width: parseFloat(s.outlineWidth)};
        })()"""
    )
    assert focus is not None, f"{label}: Tab moved focus nowhere\n{page.snapshot()}"
    assert focus["style"] != "none" and focus["width"] > 0, f"{label}: no focus outline {focus}"


REACHABLE_JS = (
    "((selector) => {"
    + _JS_COMMON
    + """
  const el = document.querySelector(selector);
  if (!el || !shown(el)) return 'missing or hidden';
  el.scrollIntoView({block: 'center'});
  const r = el.getBoundingClientRect();
  if (r.left < -1 || r.right > window.innerWidth + 1) {
    return `outside the viewport [${Math.round(r.left)}..${Math.round(r.right)}]`;
  }
  const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
  if (hit && (hit === el || el.contains(hit))) return '';
  return `covered by ${hit ? label(hit) : 'nothing'}`;
})"""
)


def assert_reachable(page: CdpPage, label: str, selector: str, widths: Sequence[int]) -> None:
    """A3: the primary action is visible, inside the viewport and not covered at every width."""
    report = []
    for width in widths:
        wait_for_width(page, width)
        verdict = page.evaluate(f"{REACHABLE_JS}({json.dumps(selector)})")
        if verdict:
            report.append(f"{label} @{width}px: {selector} {verdict}")
    assert not report, "\n".join(report) + f"\n{page.snapshot()}"


def catalog_text(key: str, locale: str, problems: list[str]) -> str:
    """Catalog text of a key that Step 4 adds; a missing key is reported, not raised."""
    from wishenka.i18n import CATALOG

    table: dict[str, str] = CATALOG["ru" if locale == "ru" else "en"]
    text = table.get(key)
    if text is None:
        problems.append(f"catalog key {key!r} is missing for locale {locale!r}")
        return key
    return str(text)


DIALOG_JS = (
    "((selector) => {"
    + _JS_COMMON
    + """
  const dialog = document.querySelector(selector);
  if (!dialog) return {placement: ['dialog is missing'], content: []};
  const sheet = dialog.querySelector('.modal-sheet') || dialog;
  const vw = window.innerWidth;
  const placement = [];
  const content = [];
  const box = sheet.getBoundingClientRect();
  if (box.left < -1 || box.right > vw + 1) {
    placement.push(`sheet leaves the viewport [${Math.round(box.left)}..${Math.round(box.right)}]`);
  }
  if (sheet.scrollWidth > sheet.clientWidth + 1) {
    content.push(`sheet scrolls sideways ${sheet.scrollWidth} > ${sheet.clientWidth}`);
  }
  const NO_BOX = new Set(['INPUT', 'SELECT', 'TEXTAREA', 'OPTION']);
  for (const el of sheet.querySelectorAll('*')) {
    if (NON_CONTENT.has(el.tagName) || !shown(el)) continue;
    const r = el.getBoundingClientRect();
    if (r.left < box.left - 1 || r.right > box.right + 1) {
      content.push(`${label(el)} leaves the sheet ` +
        `[${Math.round(r.left)}..${Math.round(r.right)}]`);
    } else if (!NO_BOX.has(el.tagName) && el.children.length === 0 && el.textContent.trim() &&
        getComputedStyle(el).display !== 'inline' && el.scrollWidth > el.clientWidth + 1) {
      content.push(`${label(el)} "${el.textContent.trim().slice(0, 24)}" ` +
        `text scroll ${el.scrollWidth} > box ${el.clientWidth}`);
    }
  }
  return {placement: placement.slice(0, 4), content: content.slice(0, 6)};
})"""
)


def dialog_problems(
    page: CdpPage,
    label: str,
    selector: str,
    part: str,
    widths: Sequence[int] = WIDTHS,
) -> list[str]:
    """Violations of an open dialog: ``part`` is ``placement`` (sheet in the viewport) or
    ``content`` (text and fields stay inside the sheet)."""
    report: list[str] = []
    for width in widths:
        wait_for_width(page, width)
        found = page.evaluate(f"{DIALOG_JS}({json.dumps(selector)})")
        report.extend(f"{label} @{width}px: {problem}" for problem in found[part])
    return report
