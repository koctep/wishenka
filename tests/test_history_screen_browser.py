"""Failing browser repro for WISHENKA-292: a convenient viewing-history screen.

Spec: ``ai-tasks/WISHENKA-292/20-architecture.md`` ("Test strategy for Step 3"). The hooks used
here (``ul.history-list``, ``li.history-card``, ``.history-confirm`` ...) are the design contract
shared with Step 4. History is seeded through the real ``POST /api/history/{id}``; failures,
delays and fixed timestamps are forced by a page-side ``window.fetch`` wrapper installed before
the Mini App boots (``window.__hx``). Every seeded fixture is asserted over the API first, so a
red run cannot come from a broken setup.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest

from tests.browser_cdp import CdpBrowser, CdpPage
from tests.browser_helpers import assert_clean_console
from tests.conftest import OWNER_TELEGRAM_ID, VIEWER_TELEGRAM_ID, BrowserServer
from tests.test_home_overview_browser import _open_home, _set_user_locale
from wishenka.i18n import SupportedLocale, t

pytestmark = [pytest.mark.timeout(45), pytest.mark.browser]

LOCALES: list[SupportedLocale] = ["en", "ru"]
ROWS = "li.history-card, .history-item"
WAIT = 3.0
NAV_HISTORY = ".home-top-nav button.home-nav-action"

# Fetch wrapper (installed before the page scripts run). Modes: real | reject | 500 | stub | hold.
HX_PRELOAD = """(() => {
  const real = window.fetch.bind(window);
  window.__hx = {deletes: 0, historyMode: 'real', deleteMode: 'real', stub: [],
    release: null, releaseDelete: null};
  const json = (body, status) => new Response(JSON.stringify(body),
    {status, headers: {'content-type': 'application/json'}});
  window.fetch = async (input, options = {}) => {
    const url = new URL(typeof input === 'string' ? input : input.url, location.href);
    const method = (options.method || 'GET').toUpperCase();
    const hx = window.__hx;
    if (url.pathname === '/api/history' && method === 'GET') {
      if (hx.historyMode === 'reject') throw new TypeError('offline');
      if (hx.historyMode === '500') return json({}, 500);
      if (hx.historyMode === 'stub') return json(hx.stub, 200);
      if (hx.historyMode === 'hold') {
        await new Promise(resolve => { hx.release = resolve; });
        hx.historyMode = 'real';
      }
    }
    if (url.pathname === '/api/history' && method === 'DELETE') {
      hx.deletes++;
      if (hx.deleteMode === '500') return json({}, 500);
      if (hx.deleteMode === 'hold') {
        await new Promise(resolve => { hx.releaseDelete = resolve; });
        hx.deleteMode = 'real';
      }
    }
    return real(input, options);
  };
})();"""

ROW_TITLES_JS = f"""Array.from(document.querySelectorAll({json.dumps(ROWS)}), row =>
  (row.querySelector('.history-title') || row.querySelector('button')).innerText.trim())"""


# --- API helpers -------------------------------------------------------------------------------


def _api(server: BrowserServer, token: str, method: str, path: str, **kwargs: Any) -> Any:
    response = httpx.request(
        method,
        f"{server.base_url}{path}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
        **kwargs,
    )
    response.raise_for_status()
    return response.json()


def _seed_history(server: BrowserServer, token: str, names: list[str]) -> list[int]:
    """Create one wishlist per name and record a view of each, in order (last is newest).

    The user row must exist before a view can be recorded, so it is created first.
    """
    owner = token == server.owner_token
    telegram_id, first_name = (
        (OWNER_TELEGRAM_ID, "Owner") if owner else (VIEWER_TELEGRAM_ID, "Viewer")
    )
    _set_user_locale(server, token, telegram_id, first_name, "en")
    ids: list[int] = []
    for name in names:
        created = _api(server, token, "POST", "/api/wishlists", json={"name": name})
        ids.append(int(created["id"]))
        # The newest view must head the history before the next one is recorded; a
        # sub-second tie is observed to reorder entries (~1 in 13 runs), so re-record.
        for _ in range(10):
            _api(server, token, "POST", f"/api/history/{created['id']}")
            if _history(server, token)[0]["id"] == created["id"]:
                break
            time.sleep(0.02)
        else:
            raise AssertionError(f"view of wishlist {created['id']} never became the newest")
    return ids


def _history(server: BrowserServer, token: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = _api(server, token, "GET", "/api/history")
    return result


def _assert_seeded(server: BrowserServer, token: str, names: list[str]) -> None:
    """Fixture guard: history is visible over the API, newest first."""
    assert [entry["name"] for entry in _history(server, token)] == list(reversed(names))


def _wait_until(description: str, predicate: Callable[[], bool], timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, f"timed out waiting for: {description}"
        time.sleep(0.05)


# --- page helpers ------------------------------------------------------------------------------


def _home(
    browser: CdpBrowser,
    pages: list[CdpPage],
    server: BrowserServer,
    locale: SupportedLocale,
    *,
    viewport: tuple[int, int] = (412, 800),
) -> CdpPage:
    """Open Home as the owner with the fetch wrapper installed (locale persisted first)."""
    _set_user_locale(server, server.owner_token, OWNER_TELEGRAM_ID, "Owner", locale)
    return _open_home(
        browser,
        pages,
        server,
        server.owner_token,
        locale,
        viewport=viewport,
        preload_script=HX_PRELOAD,
    )


def _hx(page: CdpPage, **settings: Any) -> None:
    page.evaluate(f"Object.assign(window.__hx, {json.dumps(settings)})")


def _go_history(page: CdpPage, locale: SupportedLocale, *, timeout: float = 5.0) -> None:
    page.click(NAV_HISTORY)
    title = json.dumps(t("miniapp.history.title", locale))
    page.wait_for(
        "history screen",
        f"document.querySelector('#app h1')?.innerText === {title}",
        timeout=timeout,
    )


def _wait_rows(page: CdpPage, count: int, *, timeout: float = 5.0) -> None:
    page.wait_for(
        f"{count} history rows",
        f"document.querySelectorAll({json.dumps(ROWS)}).length === {count}",
        timeout=timeout,
    )


def _history_screen(
    browser: CdpBrowser,
    pages: list[CdpPage],
    server: BrowserServer,
    locale: SupportedLocale,
    rows: int,
    *,
    viewport: tuple[int, int] = (412, 800),
    timeout: float = 5.0,
) -> CdpPage:
    page = _home(browser, pages, server, locale, viewport=viewport)
    _go_history(page, locale, timeout=timeout)
    _wait_rows(page, rows, timeout=timeout)
    return page


def _clear_by_label(page: CdpPage, locale: SupportedLocale) -> bool:
    """Click the control whose text is the Clear label (works before and after the redesign)."""
    label = json.dumps(t("miniapp.history.clear", locale))
    return bool(
        page.evaluate(f"""(() => {{
          const clear = Array.from(document.querySelectorAll('#app button'))
            .find(b => b.innerText.trim() === {label});
          if (!clear) return false;
          clear.click();
          return true;
        }})()""")
    )


def _open_confirm(page: CdpPage, locale: SupportedLocale) -> None:
    """First click on Clear must open the confirmation group and send no DELETE."""
    assert _clear_by_label(page, locale), "Clear control is missing"
    page.wait_for(
        "first Clear click effect",
        "window.__hx.deletes > 0 || !!document.querySelector('.history-confirm')",
        timeout=WAIT,
    )
    state = page.evaluate(
        "({deletes: window.__hx.deletes, confirm: !!document.querySelector('.history-confirm')})"
    )
    assert state == {"deletes": 0, "confirm": True}, (
        f"first click on Clear must only open the confirmation: {state}"
    )


def _has_clear(page: CdpPage, locale: SupportedLocale) -> bool:
    label = json.dumps(t("miniapp.history.clear", locale))
    return bool(
        page.evaluate(f"""!!document.querySelector('.history-clear') ||
          Array.from(document.querySelectorAll('#app button'))
            .some(b => b.innerText.trim() === {label})""")
    )


def _long_names() -> list[str]:
    return [
        "Very long family birthday wishlist title to verify narrow screen wrapping cleanly",
        "Очень длинное название списка подарков для проверки переноса текста на узком экране",
        "W" * 80,
    ]


# --- red: structure, time, open ----------------------------------------------------------------


@pytest.mark.parametrize("locale", LOCALES)
def test_history_renders_scannable_cards_newest_first(
    locale: SupportedLocale,
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    names = ["Alpha list", "Bravo list", "Charlie list"]
    _set_user_locale(
        wishlist_server, wishlist_server.owner_token, OWNER_TELEGRAM_ID, "Owner", locale
    )
    _seed_history(wishlist_server, wishlist_server.owner_token, names)
    _assert_seeded(wishlist_server, wishlist_server.owner_token, names)
    page = _history_screen(chromium_browser, _browser_pages, wishlist_server, locale, 3)
    data = page.evaluate("""(() => ({
      lists: document.querySelectorAll('ul.history-list').length,
      cards: Array.from(document.querySelectorAll('ul.history-list > li.history-card'), card => {
        const open = card.querySelector('button.history-open');
        const time = card.querySelector('time.history-time[datetime]');
        return {
          title: card.querySelector('h2.history-title')?.innerText.trim() ?? null,
          datetime: time ? time.getAttribute('datetime') : null,
          absolute: time ? time.getAttribute('title') : null,
          aria: open ? open.getAttribute('aria-label') : null,
          openText: open ? open.innerText.trim() : null,
        };
      }),
    }))()""")
    expected = list(reversed(names))
    assert data["lists"] == 1, data
    assert [card["title"] for card in data["cards"]] == expected, data
    open_label = t("miniapp.home.open_wishlist", locale)
    for card in data["cards"]:
        assert card["datetime"] and not re.search("invalid", str(card["datetime"]), re.I), card
        assert card["absolute"], card
        assert card["openText"] == open_label, card
        assert card["aria"] and card["title"] in card["aria"], card
    assert_clean_console(page)


def test_open_button_opens_the_wishlist_and_records_the_view(
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    names = ["Older list", "Newer list"]
    token = wishlist_server.owner_token
    _seed_history(wishlist_server, token, names)
    _assert_seeded(wishlist_server, token, names)
    page = _history_screen(chromium_browser, _browser_pages, wishlist_server, "en", 2)
    page.click("li.history-card:nth-child(2) button.history-open")
    page.wait_for("opened list", "document.querySelector('#app h1')?.innerText === 'Older list'")
    _wait_until(
        "view recorded",
        lambda: _history(wishlist_server, token)[0]["name"] == "Older list",
    )


@pytest.mark.parametrize("locale", LOCALES)
def test_time_is_locale_aware_relative_recent_absolute_old_and_never_invalid(
    locale: SupportedLocale,
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    now = datetime.now(UTC)
    ages = {
        "Five minutes": now - timedelta(minutes=5),
        "Three days": now - timedelta(days=3),
        "Forty days": now - timedelta(days=40),
    }
    stub: list[dict[str, Any]] = [
        {
            "id": 9000 + index,
            "name": name,
            "description": None,
            "event_title": None,
            "event_date": None,
            "viewed_at": moment.isoformat(),
            "is_favorite": False,
            "role": "owner",
        }
        for index, (name, moment) in enumerate(ages.items())
    ]
    for index, bad in enumerate(["not-a-date", None]):
        stub.append({**stub[0], "id": 9100 + index, "name": f"Bad {index}", "viewed_at": bad})
    page = _home(chromium_browser, _browser_pages, wishlist_server, locale)
    _hx(page, historyMode="stub", stub=stub)
    _go_history(page, locale)
    _wait_rows(page, 5)
    cards = page.evaluate("""Array.from(document.querySelectorAll('li.history-card'), card => ({
      title: card.querySelector('.history-title')?.innerText.trim() ?? null,
      text: card.innerText,
      datetime: card.querySelector('time')?.getAttribute('datetime') ?? null,
      timeText: card.querySelector('time')?.innerText.trim() ?? null,
      absolute: card.querySelector('time')?.getAttribute('title') ?? null,
    }))""")
    assert [card["title"] for card in cards] == list(ages) + ["Bad 0", "Bad 1"], cards
    prefix = t("miniapp.history.viewed_at", locale, date="X").split("X")[0].strip()
    five, three, forty = cards[0], cards[1], cards[2]
    for card, moment in zip(cards[:3], ages.values(), strict=True):
        assert card["datetime"], card
        parsed = page.evaluate(f"Date.parse({json.dumps(card['datetime'])})")
        assert abs(parsed - moment.timestamp() * 1000) < 1000, card
        assert card["absolute"], card
        assert prefix in card["text"], card
    recent = {"en": ("5 minutes ago", "3 days ago"), "ru": ("5 минут назад", "3 дня назад")}[locale]
    assert recent[0] in five["text"], five
    assert recent[1] in three["text"], three
    assert not re.search("ago|назад", forty["text"]), forty
    assert re.search(r"\b20\d\d\b", forty["text"]), forty
    for bad in cards[3:]:
        assert bad["datetime"] is None, bad
        assert not re.search("invalid|nan", bad["text"], re.I), bad


# --- red: deliberate clear ---------------------------------------------------------------------


@pytest.mark.parametrize("locale", LOCALES)
def test_first_clear_click_opens_confirmation_without_deleting(
    locale: SupportedLocale,
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    names = ["One", "Two"]
    token = wishlist_server.owner_token
    _set_user_locale(wishlist_server, token, OWNER_TELEGRAM_ID, "Owner", locale)
    _seed_history(wishlist_server, token, names)
    _assert_seeded(wishlist_server, token, names)
    page = _history_screen(chromium_browser, _browser_pages, wishlist_server, locale, 2)
    _open_confirm(page, locale)
    group = page.evaluate("""(() => {
      const group = document.querySelector('.history-confirm');
      return {
        role: group.getAttribute('role'), text: group.innerText.trim(),
        cancel: group.querySelector('.history-confirm-cancel')?.innerText.trim() ?? null,
        yes: group.querySelector('.history-confirm-yes')?.innerText.trim() ?? null,
        focusOnCancel: document.activeElement?.matches('.history-confirm-cancel') ?? false,
      };
    })()""")
    assert group["role"] == "group", group
    assert group["cancel"] and group["yes"] and group["cancel"] != group["yes"], group
    assert len(group["text"]) > len(group["cancel"]) + len(group["yes"]), group
    assert group["focusOnCancel"], group
    assert len(_history(wishlist_server, token)) == 2


def test_cancel_keeps_history_and_sends_no_request(
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    names = ["One", "Two"]
    token = wishlist_server.owner_token
    _seed_history(wishlist_server, token, names)
    _assert_seeded(wishlist_server, token, names)
    page = _history_screen(chromium_browser, _browser_pages, wishlist_server, "en", 2)
    _open_confirm(page, "en")
    page.click(".history-confirm-cancel")
    state = page.evaluate(f"""({{
      deletes: window.__hx.deletes, confirm: !!document.querySelector('.history-confirm'),
      rows: document.querySelectorAll({json.dumps(ROWS)}).length,
      clearFocused: document.activeElement?.matches('.history-clear') ?? false,
    }})""")
    assert state == {"deletes": 0, "confirm": False, "rows": 2, "clearFocused": True}, state
    assert len(_history(wishlist_server, token)) == 2


@pytest.mark.parametrize("locale", LOCALES)
def test_confirm_sends_exactly_one_delete_and_shows_cleared_empty_state(
    locale: SupportedLocale,
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    names = ["One", "Two"]
    token = wishlist_server.owner_token
    _set_user_locale(wishlist_server, token, OWNER_TELEGRAM_ID, "Owner", locale)
    _seed_history(wishlist_server, token, names)
    _assert_seeded(wishlist_server, token, names)
    page = _history_screen(chromium_browser, _browser_pages, wishlist_server, locale, 2)
    _open_confirm(page, locale)
    page.click(".history-confirm-yes")
    cleared = json.dumps(t("miniapp.history.cleared", locale))
    page.wait_for(
        "cleared empty state",
        f"!!document.querySelector('.history-empty') && "
        f"document.getElementById('status').innerText === {cleared}",
    )
    assert page.evaluate("window.__hx.deletes") == 1
    assert _history(wishlist_server, token) == []
    assert page.evaluate("document.activeElement?.matches('h1')") is True


def test_clearing_state_disables_both_buttons_and_blocks_duplicates(
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    names = ["One", "Two"]
    token = wishlist_server.owner_token
    _seed_history(wishlist_server, token, names)
    _assert_seeded(wishlist_server, token, names)
    page = _history_screen(chromium_browser, _browser_pages, wishlist_server, "en", 2)
    _hx(page, deleteMode="hold")
    _open_confirm(page, "en")
    page.click(".history-confirm-yes")
    page.wait_for("DELETE pending", "window.__hx.deletes === 1 && !!window.__hx.releaseDelete")
    state = page.evaluate("""(() => {
      document.querySelector('.history-confirm-yes').click();
      const group = document.querySelector('.history-confirm');
      return {
        busy: group.getAttribute('aria-busy'),
        yes: document.querySelector('.history-confirm-yes').disabled,
        cancel: document.querySelector('.history-confirm-cancel').disabled,
        deletes: window.__hx.deletes,
      };
    })()""")
    page.evaluate("window.__hx.releaseDelete()")
    assert state == {"busy": "true", "yes": True, "cancel": True, "deletes": 1}, state


def test_clear_failure_is_announced_keeps_list_and_retry_succeeds(
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    names = ["One", "Two"]
    token = wishlist_server.owner_token
    _seed_history(wishlist_server, token, names)
    _assert_seeded(wishlist_server, token, names)
    page = _history_screen(chromium_browser, _browser_pages, wishlist_server, "en", 2)
    _hx(page, deleteMode="500")
    _open_confirm(page, "en")
    page.click(".history-confirm-yes")
    page.wait_for("clear failure announced", "!!document.querySelector('[role=alert]')")
    failed = page.evaluate(f"""({{
      alert: document.querySelector('[role=alert]').innerText.trim(),
      titles: {ROW_TITLES_JS},
      status: document.getElementById('status').innerText,
      confirm: !!document.querySelector('.history-confirm'),
      yesEnabled: !document.querySelector('.history-confirm-yes')?.disabled,
    }})""")
    assert failed["alert"] == t("miniapp.history.clear_failed", "en"), failed
    assert failed["titles"] == ["Two", "One"], failed
    assert failed["status"] != t("miniapp.history.cleared", "en"), failed
    assert failed["confirm"] and failed["yesEnabled"], failed
    assert len(_history(wishlist_server, token)) == 2
    _hx(page, deleteMode="real")
    page.click(".history-confirm-yes")
    cleared = json.dumps(t("miniapp.history.cleared", "en"))
    page.wait_for(
        "retry cleared",
        f"!!document.querySelector('.history-empty') && "
        f"document.getElementById('status').innerText === {cleared}",
    )
    assert page.evaluate("window.__hx.deletes") == 2
    assert _history(wishlist_server, token) == []


def test_escape_closes_confirmation_and_restores_focus_to_clear(
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    names = ["One", "Two"]
    token = wishlist_server.owner_token
    _seed_history(wishlist_server, token, names)
    _assert_seeded(wishlist_server, token, names)
    page = _history_screen(chromium_browser, _browser_pages, wishlist_server, "en", 2)
    _open_confirm(page, "en")
    assert page.evaluate("!!document.querySelector('.history-confirm')")
    page.press_key("Escape")
    page.wait_for("confirmation closed", "!document.querySelector('.history-confirm')", WAIT)
    state = page.evaluate("""({
      deletes: window.__hx.deletes,
      focusOnClear: document.activeElement === document.querySelector('.history-clear'),
    })""")
    assert state == {"deletes": 0, "focusOnClear": True}, state
    assert len(_history(wishlist_server, token)) == 2


def test_clear_sits_below_the_list_as_a_quiet_secondary_action(
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    names = ["One", "Two", "Three"]
    token = wishlist_server.owner_token
    _seed_history(wishlist_server, token, names)
    _assert_seeded(wishlist_server, token, names)
    page = _history_screen(chromium_browser, _browser_pages, wishlist_server, "en", 3)
    data = page.evaluate("""(() => {
      const cards = Array.from(document.querySelectorAll('li.history-card'));
      const last = cards[cards.length - 1];
      const clear = document.querySelector('.history-clear');
      const open = document.querySelector('.history-open');
      if (!last || !clear || !open) return {missing: true};
      const clearCss = getComputedStyle(clear);
      const cardBg = getComputedStyle(last).backgroundColor;
      return {
        missing: false,
        after: !!(last.compareDocumentPosition(clear) & Node.DOCUMENT_POSITION_FOLLOWING),
        below: clear.getBoundingClientRect().top >= last.getBoundingClientRect().bottom,
        inFooter: !!clear.closest('.history-footer'),
        quiet: clearCss.backgroundColor === 'rgba(0, 0, 0, 0)' ||
          clearCss.backgroundColor === cardBg,
        lighter: clearCss.backgroundColor !== getComputedStyle(open).backgroundColor,
      };
    })()""")
    assert data == {
        "missing": False,
        "after": True,
        "below": True,
        "inFooter": True,
        "quiet": True,
        "lighter": True,
    }, data


@pytest.mark.parametrize("state", ["empty", "loading", "error"])
def test_clear_is_absent_in_empty_loading_and_error_states(
    state: str,
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    token = wishlist_server.owner_token
    if state != "empty":
        _seed_history(wishlist_server, token, ["One"])
    page = _home(chromium_browser, _browser_pages, wishlist_server, "en")
    _hx(page, historyMode={"empty": "real", "loading": "hold", "error": "reject"}[state])
    _go_history(page, "en")
    if state == "loading":
        page.wait_for("GET held", "!!window.__hx.release")
        assert page.evaluate("document.getElementById('status').innerText") == t(
            "nav.loading", "en"
        )
    elif state == "error":
        page.wait_for(
            "error shown",
            "!!document.querySelector('.history-error') || "
            "document.getElementById('status').innerText.trim() !== ''",
        )
        assert page.evaluate("!!document.querySelector('.history-retry')"), "no Retry in error"
    else:
        page.wait_for("empty shown", "!!document.querySelector('#app section p, .history-empty')")
        assert page.evaluate("!!document.querySelector('.history-empty')"), "no empty state"
    assert not _has_clear(page, "en")
    if state == "loading":
        page.evaluate("window.__hx.release()")


# --- red: states -------------------------------------------------------------------------------


@pytest.mark.parametrize("locale", LOCALES)
def test_empty_state_explains_and_offers_a_way_to_home(
    locale: SupportedLocale,
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    page = _home(chromium_browser, _browser_pages, wishlist_server, locale)
    _go_history(page, locale)
    page.wait_for("empty state", "!!document.querySelector('#app section p, .history-empty')")
    data = page.evaluate("""(() => {
      const empty = document.querySelector('.history-empty');
      if (!empty) return null;
      const action = empty.querySelector('.history-empty-action, button');
      const hint = empty.querySelector('.empty-hint');
      return {
        text: empty.innerText,
        hint: hint ? hint.innerText.trim() : '',
        notice: empty.querySelector('.empty-notice')?.innerText.trim() ?? '',
        tag: action ? action.tagName : null,
        isHook: !!empty.querySelector('.history-empty-action'),
        height: action ? action.getBoundingClientRect().height : 0,
      };
    })()""")
    assert data is not None, "history empty state (.history-empty) is missing"
    assert t("miniapp.history.empty", locale) in data["text"], data
    assert data["hint"] and data["hint"] != data["notice"], data
    assert data["isHook"] and data["tag"] == "BUTTON" and data["height"] >= 44, data
    page.click(".history-empty-action")
    home = json.dumps(t("miniapp.home.title", locale))
    page.wait_for("home reached", f"document.querySelector('#app h1')?.innerText === {home}")


@pytest.mark.parametrize("mode", ["reject", "500"])
def test_load_failure_shows_alert_and_retry_recovers(
    mode: str,
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    names = ["One", "Two"]
    token = wishlist_server.owner_token
    _seed_history(wishlist_server, token, names)
    _assert_seeded(wishlist_server, token, names)
    page = _home(chromium_browser, _browser_pages, wishlist_server, "en")
    _hx(page, historyMode=mode)
    _go_history(page, "en")
    page.wait_for(
        "load failure shown",
        "!!document.querySelector('.history-error') || "
        "document.getElementById('status').innerText.trim() !== ''",
    )
    data = page.evaluate("""({
      role: document.querySelector('.history-error')?.getAttribute('role') ?? null,
      text: document.querySelector('.history-error')?.innerText.trim() ?? null,
      retry: !!document.querySelector('button.history-retry'),
      back: Array.from(document.querySelectorAll('#app button')).some(
        b => b.innerText.trim() === 'Back'),
    })""")
    assert data["role"] == "alert", data
    assert data["text"] == t("miniapp.history.load_failed", "en"), data
    assert data["retry"] and data["back"], data
    _hx(page, historyMode="real")
    page.click(".history-retry")
    _wait_rows(page, 2)
    assert page.evaluate(ROW_TITLES_JS) == ["Two", "One"]
    assert page.evaluate("!document.querySelector('.history-error')")


def test_loading_state_is_busy_announced_and_has_no_clear(
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    names = ["One", "Two"]
    token = wishlist_server.owner_token
    _seed_history(wishlist_server, token, names)
    _assert_seeded(wishlist_server, token, names)
    page = _home(chromium_browser, _browser_pages, wishlist_server, "en")
    _hx(page, historyMode="hold")
    _go_history(page, "en")
    page.wait_for("GET /api/history held", "!!window.__hx.release")
    pending = page.evaluate("""({
      busy: document.querySelector('#app section')?.getAttribute('aria-busy') ?? null,
      status: document.getElementById('status').innerText,
      clear: !!document.querySelector('.history-clear'),
    })""")
    page.evaluate("window.__hx.release()")
    assert pending == {"busy": "true", "status": t("nav.loading", "en"), "clear": False}, pending
    _wait_rows(page, 2)
    assert page.evaluate("document.querySelector('#app section')?.getAttribute('aria-busy')") in (
        None,
        "false",
    )


# --- red: narrow viewport and accessibility ----------------------------------------------------


@pytest.mark.parametrize("locale", LOCALES)
@pytest.mark.parametrize("width", [320, 375])
def test_narrow_viewport_has_no_overflow_overlap_or_small_targets(
    locale: SupportedLocale,
    width: int,
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    names = _long_names()
    token = wishlist_server.owner_token
    _set_user_locale(wishlist_server, token, OWNER_TELEGRAM_ID, "Owner", locale)
    _seed_history(wishlist_server, token, names)
    _assert_seeded(wishlist_server, token, names)
    page = _history_screen(
        chromium_browser, _browser_pages, wishlist_server, locale, 3, viewport=(width, 800)
    )
    data = page.evaluate("""(() => {
      const root = document.documentElement;
      const controls = Array.from(document.querySelectorAll('#app button, #app a'), el => {
        const r = el.getBoundingClientRect();
        return {text: el.innerText.trim().slice(0, 30), left: r.left, right: r.right,
          top: r.top, bottom: r.bottom, width: r.width, height: r.height};
      }).filter(c => c.width && c.height);
      const overlaps = controls.some((a, i) => controls.slice(i + 1).some(b =>
        a.left < b.right - 0.5 && b.left < a.right - 0.5 &&
        a.top < b.bottom - 0.5 && b.top < a.bottom - 0.5));
      const cards = Array.from(document.querySelectorAll('li.history-card'));
      return {
        cards: cards.length,
        pageOverflow: root.scrollWidth > root.clientWidth,
        clipped: cards.filter(c => c.scrollWidth > c.clientWidth + 1).length,
        titleClipped: cards.filter(c => {
          const title = c.querySelector('.history-title');
          return !title || title.scrollWidth > title.clientWidth + 1;
        }).length,
        small: controls.filter(c => c.height < 44 || c.width < 44).map(c => c.text),
        outside: controls.filter(c => c.left < 0 || c.right > innerWidth + 1).length,
        overlaps,
      };
    })()""")
    assert data == {
        "cards": 3,
        "pageOverflow": False,
        "clipped": 0,
        "titleClipped": 0,
        "small": [],
        "outside": 0,
        "overlaps": False,
    }, data


def test_keyboard_flow_focus_indicators_and_heading_structure(
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    names = ["One", "Two"]
    token = wishlist_server.owner_token
    _seed_history(wishlist_server, token, names)
    _assert_seeded(wishlist_server, token, names)
    page = _history_screen(chromium_browser, _browser_pages, wishlist_server, "en", 2)
    headings = page.evaluate("""({
      h1: document.querySelectorAll('#app h1').length,
      h2: document.querySelectorAll('li.history-card h2').length,
    })""")
    assert headings == {"h1": 1, "h2": 2}, headings
    indicator = """(() => {
      const el = document.activeElement;
      const css = getComputedStyle(el);
      return {focusVisible: el.matches(':focus-visible'),
        indicator: (css.outlineStyle !== 'none' && parseFloat(css.outlineWidth) > 0) ||
          css.boxShadow !== 'none'};
    })()"""

    def tab_to(selector: str) -> dict[str, Any]:
        for _ in range(10):
            page.press_key("Tab")
            if page.evaluate(f"document.activeElement?.matches({json.dumps(selector)})"):
                result: dict[str, Any] = page.evaluate(indicator)
                return result
        raise AssertionError(f"Tab never reached {selector}\n{page.snapshot()}")

    assert tab_to(".history-open") == {"focusVisible": True, "indicator": True}
    page.press_key("Enter")
    page.wait_for("opened list", "document.querySelector('#app h1')?.innerText === 'Two'")

    second = _history_screen(chromium_browser, _browser_pages, wishlist_server, "en", 2)
    page = second
    assert tab_to(".history-clear") == {"focusVisible": True, "indicator": True}
    page.press_key("Enter")
    page.wait_for("confirmation", "!!document.querySelector('.history-confirm')", WAIT)
    assert page.evaluate("document.activeElement?.matches('.history-confirm-cancel')") is True
    assert page.evaluate(indicator) == {"focusVisible": True, "indicator": True}
    assert tab_to(".history-confirm-yes") == {"focusVisible": True, "indicator": True}


# --- positive controls: must pass on the baseline and after the redesign ----------------------


def test_control_history_keeps_twenty_newest_first(
    wishlist_server: BrowserServer,
) -> None:
    names = [f"List {index:02d}" for index in range(21)]
    token = wishlist_server.owner_token
    _seed_history(wishlist_server, token, names)
    assert [entry["name"] for entry in _history(wishlist_server, token)] == list(
        reversed(names[1:])
    )


def test_control_deleted_list_is_hidden_and_cannot_be_recorded(
    wishlist_server: BrowserServer,
    tmp_path: Path,
) -> None:
    names = ["Keep me", "Delete me"]
    token = wishlist_server.owner_token
    ids = _seed_history(wishlist_server, token, names)
    _assert_seeded(wishlist_server, token, names)
    with sqlite3.connect(tmp_path / "browser.db") as connection:
        stored = connection.execute("SELECT status FROM wl_lists WHERE id = ?", (ids[1],))
        value = str(stored.fetchone()[0])
        deleted = "DELETED" if value.isupper() else "deleted"
        connection.execute("UPDATE wl_lists SET status = ? WHERE id = ?", (deleted, ids[1]))
        connection.commit()
    assert [entry["name"] for entry in _history(wishlist_server, token)] == ["Keep me"]
    response = httpx.post(
        f"{wishlist_server.base_url}/api/history/{ids[1]}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    assert response.status_code == 404


def test_control_opening_an_entry_moves_it_to_the_top_and_navigation_works(
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    names = ["Older list", "Newer list"]
    token = wishlist_server.owner_token
    _seed_history(wishlist_server, token, names)
    _assert_seeded(wishlist_server, token, names)
    page = _history_screen(chromium_browser, _browser_pages, wishlist_server, "en", 2, timeout=45)
    assert page.evaluate(ROW_TITLES_JS) == ["Newer list", "Older list"]
    opened = page.evaluate("""(() => {
      const row = Array.from(document.querySelectorAll('li.history-card'))
        .find(card => card.querySelector('h2')?.innerText.trim() === 'Older list');
      const control = row?.querySelector('button.history-open');
      if (!control) return false;
      control.click();
      return true;
    })()""")
    assert opened
    page.wait_for(
        "opened list",
        "document.querySelector('#app h1')?.innerText === 'Older list'",
        timeout=45,
    )

    def _older_list_is_first() -> bool:
        try:
            name = _history(wishlist_server, token)[0]["name"]
        except httpx.HTTPError:
            return False
        return bool(name == "Older list")

    _wait_until("view recorded", _older_list_is_first, timeout=45)
    page.navigate(f"{wishlist_server.base_url}/")
    _go_history(page, "en", timeout=45)
    _wait_rows(page, 2, timeout=45)
    assert page.evaluate(ROW_TITLES_JS) == ["Older list", "Newer list"]
    page.evaluate("""Array.from(document.querySelectorAll('#app button'))
      .find(b => b.innerText.trim() === 'Back').click()""")
    home = json.dumps(t("miniapp.home.title", "en"))
    page.wait_for("home", f"document.querySelector('#app h1')?.innerText === {home}", timeout=45)
    assert_clean_console(page)


def test_control_clear_scope_api_contract_and_payload_shape(
    wishlist_server: BrowserServer,
) -> None:
    owner = wishlist_server.owner_token
    viewer = wishlist_server.viewer_token
    _set_user_locale(wishlist_server, owner, OWNER_TELEGRAM_ID, "Owner", "en")
    _set_user_locale(wishlist_server, viewer, VIEWER_TELEGRAM_ID, "Viewer", "en")
    own = _seed_history(wishlist_server, owner, ["Owner list"])
    theirs = _seed_history(wishlist_server, viewer, ["Viewer list"])
    viewer_wl = _api(wishlist_server, viewer, "GET", f"/api/wishlists/{theirs[0]}")
    _api(wishlist_server, owner, "GET", f"/api/public/wishlists/{viewer_wl['share_token']}/view")
    _api(wishlist_server, owner, "POST", f"/api/favorites/{theirs[0]}")
    _api(wishlist_server, owner, "POST", f"/api/history/{theirs[0]}")
    entry = _history(wishlist_server, owner)[0]
    assert set(entry) == {
        "id",
        "name",
        "description",
        "event_title",
        "event_date",
        "viewed_at",
        "is_favorite",
        "role",
    }
    assert _api(wishlist_server, owner, "DELETE", "/api/history") == {"status": "cleared"}
    assert _history(wishlist_server, owner) == []
    assert [e["name"] for e in _history(wishlist_server, viewer)] == ["Viewer list"]
    wishlists = _api(wishlist_server, owner, "GET", "/api/wishlists")
    assert [w["id"] for w in wishlists] == own
    favorites = _api(wishlist_server, owner, "GET", "/api/favorites")
    assert [f["id"] for f in favorites] == theirs


def test_control_history_exposes_no_reservation_data(
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    owner = wishlist_server.owner_token
    viewer = wishlist_server.viewer_token
    _set_user_locale(wishlist_server, owner, OWNER_TELEGRAM_ID, "Owner", "en")
    _set_user_locale(wishlist_server, viewer, VIEWER_TELEGRAM_ID, "Viewer", "en")
    created = _api(wishlist_server, owner, "POST", "/api/wishlists", json={"name": "Gift list"})
    item = _api(
        wishlist_server,
        owner,
        "POST",
        f"/api/wishlists/{created['id']}/items",
        json={"title": "Secret Espresso Machine", "quantity": 1},
    )
    _api(
        wishlist_server,
        viewer,
        "POST",
        f"/api/public/wishlists/{created['share_token']}/items/{item['id']}/reservations",
        json={"quantity": 1},
    )
    _api(wishlist_server, owner, "POST", f"/api/history/{created['id']}")
    payload = json.dumps(_history(wishlist_server, owner))
    assert not re.search("reserv|purchas|Viewer|Espresso", payload, re.I), payload
    page = _history_screen(chromium_browser, _browser_pages, wishlist_server, "en", 1)
    text = page.evaluate("document.getElementById('app').innerText")
    assert "Gift list" in text
    assert not re.search("reserv|purchas|Viewer|Espresso", text, re.I), text
