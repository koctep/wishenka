"""Browser repro for WISHENKA-296 (Step 3): a wishlist exists only after an explicit "Create".

Real Chromium against the real Mini App and server, plain browser (no Telegram bridge), cookie
session. Today a tap on "Create wishlist" sends ``POST /api/wishlists`` with ``{}`` at once and
there is no form, so leaving the "flow" (reload, in-app navigation) leaves an empty list behind
(the reported bug) and every form interaction fails at the first step. The tests assert the
designed behavior (``20-architecture.md`` D-2, D-3, D-5, D-6, browser cases 1-10): a form with
Create and Cancel, inline validation that keeps what was typed, one guarded request for any mix
of taps and Enter, failure and 422 mapping, a staleness guard for the home screen and layout at
narrow widths in both languages.

Test mechanics: field values are set through ``evaluate`` (assign ``value`` and dispatch
``input``); Enter is real implicit submission via ``CdpPage.press_key("Enter")`` on the focused
title input.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Literal

import pytest

from tests.browser_cdp import CdpBrowser, CdpPage
from tests.browser_screens import (
    api,
    assert_contrast_and_focus,
    assert_reachable,
    open_miniapp,
    provision_user,
    width_problems,
)
from tests.conftest import OWNER_TELEGRAM_ID, BrowserServer
from wishenka.i18n import CATALOG

pytestmark = [pytest.mark.timeout(45), pytest.mark.browser]

WAIT = 3.0
HOME_CREATE = ".home-create-btn"
FORM = ".wishlist-create-form"
SUBMIT = ".create-submit-btn"
CANCEL = ".create-cancel-btn"
LIST_TITLE = "#app .list-title"
MAX_TITLE = 255

# Fetch wrapper installed before the Mini App boots: counts requests by kind and forces,
# holds or fakes answers (modes: real | hold | 500 | 422name | 422tooLong | 422date | 422unknown).
PRELOAD = """(() => {
  const real = window.fetch.bind(window);
  const state = {counts: {create: 0, home: 0, detail: 0}, mode: {}, waiters: {},
    lastCreateBody: null};
  state.release = key => (state.waiters[key] || []).splice(0).forEach(resolve => resolve());
  state.errors = [];
  window.addEventListener('error', event => state.errors.push(String(event.message)));
  window.addEventListener('unhandledrejection', event => state.errors.push(String(event.reason)));
  window.__t = state;
  const classify = (method, path) => {
    if (method === 'POST' && path === '/api/wishlists') return 'create';
    if (method === 'GET' && path === '/api/wishlists') return 'home';
    if (method === 'GET' && /^\\/api\\/wishlists\\/\\d+$/.test(path)) return 'detail';
    return null;
  };
  const invalid = loc => new Response(JSON.stringify({detail: [{loc, msg: 'bad', type: 'x'}]}),
    {status: 422, headers: {'content-type': 'application/json'}});
  const tooLong = new Response(JSON.stringify({detail: [{loc: ['body', 'name'],
    msg: 'too long', type: 'wishlist_name_too_long', ctx: {max_length: 255}}]}),
    {status: 422, headers: {'content-type': 'application/json'}});
  window.fetch = async (input, options = {}) => {
    const url = new URL(typeof input === 'string' ? input : input.url, location.href);
    const key = classify((options.method || 'GET').toUpperCase(), url.pathname);
    if (!key) return real(input, options);
    state.counts[key] += 1;
    if (key === 'create') state.lastCreateBody = options.body || null;
    const mode = state.mode[key] || 'real';
    if (mode === '500') {
      return new Response('{}', {status: 500, headers: {'content-type': 'application/json'}});
    }
    if (mode === '422name') return invalid(['body', 'name']);
    if (mode === '422tooLong') return tooLong;
    if (mode === '422date') return invalid(['body', 'event_date']);
    if (mode === '422unknown') return invalid(['body', 'description']);
    if (mode === 'hold') {
      await new Promise(resolve => (state.waiters[key] = state.waiters[key] || []).push(resolve));
    }
    return real(input, options);
  };
})();"""

OpenHome = Callable[..., CdpPage]


def _table(locale: str) -> dict[str, str]:
    return CATALOG["ru" if locale == "ru" else "en"]


def _text(locale: str, key: str, **params: object) -> str:
    """Catalog text; a key Step 4 has not added yet reads as a marker, not an error."""
    template = _table(locale).get(key, f"<missing catalog key {key}>")
    for name, value in params.items():
        template = template.replace("{" + name + "}", str(value))
    return template


def _create_text(locale: str, key: str, **params: object) -> str:
    return _text(locale, "miniapp.create." + key, **params)


@pytest.fixture
def open_home(
    chromium_browser: CdpBrowser,
    wishlist_server: BrowserServer,
    _browser_pages: list[CdpPage],
) -> OpenHome:
    """Factory ``open_home(locale, width=412, query="") -> CdpPage`` on the owner's home screen.

    The owner has no wishlist. The fetch wrapper ``window.__t`` is installed before the app boots.
    """

    def factory(locale: Literal["en", "ru"], width: int = 412, query: str = "") -> CdpPage:
        server = wishlist_server
        provision_user(server, server.owner_token, OWNER_TELEGRAM_ID, "Owner", locale)
        return open_miniapp(
            chromium_browser,
            _browser_pages,
            server,
            server.owner_token,
            locale,
            viewport=(width, 800),
            query=query,
            preload_script=PRELOAD,
        )

    return factory


# --- helpers ----------------------------------------------------------------------------------


def _lists(server: BrowserServer) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = api(server, server.owner_token, "GET", "/api/wishlists")
    return result


def _settle_home(page: CdpPage, locale: str) -> None:
    title = json.dumps(_text(locale, "miniapp.home.title"))
    page.wait_for(
        "home settled",
        f"document.querySelector('#app h1')?.innerText === {title} "
        "&& document.getElementById('status')?.innerText === '' "
        "&& document.querySelectorAll('.wishlist-section').length >= 3",
    )


def _open_form(page: CdpPage) -> None:
    page.click(HOME_CREATE)
    page.wait_for(
        "creation form (a tap on Create must open a form, not create a list)",
        f"!!document.querySelector({json.dumps(FORM)})",
        timeout=WAIT,
    )


def _set(page: CdpPage, name: str, value: str) -> None:
    """Type a value into a form field: assign it and dispatch ``input`` like the browser does."""
    stored = page.evaluate(
        f"""(() => {{
      const input = document.querySelector('{FORM} input[name="{name}"]');
      if (!input) return null;
      input.value = {json.dumps(value)};
      input.dispatchEvent(new Event('input', {{bubbles: true}}));
      return input.value;
    }})()"""
    )
    assert stored == value, f"field {name!r} did not take {value[:30]!r}: got {stored!r}"


def _values(page: CdpPage) -> dict[str, str]:
    result: dict[str, str] = page.evaluate(
        f"""Object.fromEntries(Array.from(
      document.querySelectorAll('{FORM} input'), i => [i.name, i.value]))"""
    )
    return result


def _counts(page: CdpPage) -> dict[str, int]:
    result: dict[str, int] = page.evaluate("window.__t.counts")
    return result


def _status(page: CdpPage) -> dict[str, Any]:
    result: dict[str, Any] = page.evaluate(
        """(() => { const s = document.getElementById('status');
          return {text: s.innerText, kind: s.getAttribute('data-kind'),
            live: s.getAttribute('aria-live')}; })()"""
    )
    return result


def _mode(page: CdpPage, key: str, mode: str) -> None:
    page.evaluate(f"window.__t.mode[{json.dumps(key)}] = {json.dumps(mode)}")


def _wait_count(page: CdpPage, key: str, count: int) -> None:
    page.wait_for(f"{count} {key} request(s)", f"window.__t.counts.{key} >= {count}", timeout=WAIT)


def _active(page: CdpPage) -> dict[str, Any]:
    result: dict[str, Any] = page.evaluate(
        """(() => { const a = document.activeElement;
          return {tag: a.tagName, name: a.getAttribute('name'), cls: a.getAttribute('class'),
            text: a.innerText || ''}; })()"""
    )
    return result


def _sleep(page: CdpPage, milliseconds: int = 300) -> None:
    page.evaluate(f"new Promise(r => setTimeout(r, {milliseconds}))", await_promise=True)


def _error_text(page: CdpPage, name: str) -> str | None:
    result: str | None = page.evaluate(
        f"document.getElementById('create-error-{name}')?.innerText ?? null"
    )
    return result


# --- 1 nothing is created before confirmation (the reported bug) ------------------------------


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_tapping_create_then_reloading_creates_nothing(
    locale: Literal["en", "ru"], open_home: OpenHome, wishlist_server: BrowserServer
) -> None:
    """The reported scenario with today's means: tap Create, leave by reload, find a new list."""
    page = open_home(locale)
    before = len(_lists(wishlist_server))
    page.click(HOME_CREATE)
    page.wait_for(
        "form or list opened",
        f"!!document.querySelector({json.dumps(FORM)}) || !!document.querySelector('{LIST_TITLE}')",
        timeout=WAIT,
    )

    page.navigate(f"{wishlist_server.base_url}/")
    _settle_home(page, locale)

    after = _lists(wishlist_server)
    assert len(after) == before, (
        f"tapping Create and leaving left {len(after) - before} new list(s): {after}"
    )


def test_tapping_create_then_navigating_in_app_creates_nothing(
    open_home: OpenHome, wishlist_server: BrowserServer
) -> None:
    page = open_home("en")
    page.click(HOME_CREATE)
    page.wait_for(
        "form or list opened",
        f"!!document.querySelector({json.dumps(FORM)}) || !!document.querySelector('{LIST_TITLE}')",
        timeout=WAIT,
    )
    page.evaluate("showHistory()", await_promise=True)
    page.evaluate("showHome()", await_promise=True)
    _settle_home(page, "en")

    assert _lists(wishlist_server) == []
    assert _counts(page)["create"] == 0


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_create_button_opens_the_form_without_any_request(
    locale: Literal["en", "ru"], open_home: OpenHome, wishlist_server: BrowserServer
) -> None:
    page = open_home(locale)
    _open_form(page)

    state = page.evaluate(
        f"""({{
      h1: document.querySelector('#app h1').innerText,
      create: window.__t.counts.create,
      inputs: Array.from(document.querySelectorAll('{FORM} input'), i => i.name),
      submit: document.querySelector('{SUBMIT}')?.innerText,
      cancel: document.querySelector('{CANCEL}')?.innerText,
      sections: document.querySelectorAll('.wishlist-section').length,
    }})"""
    )
    assert state["h1"] == _create_text(locale, "title")
    assert state["create"] == 0
    assert state["inputs"] == ["name", "description", "event_title", "event_date"]
    assert state["submit"] == _create_text(locale, "submit")
    assert state["cancel"] == _text(locale, "miniapp.wishlist_settings.cancel")
    assert state["sections"] == 0, "home sections must not be shown under the form"
    assert _lists(wishlist_server) == []


@pytest.mark.parametrize("how", ["cancel", "reload", "navigate_home", "in_app_home", "back"])
def test_leaving_the_empty_form_creates_nothing(
    how: str, open_home: OpenHome, wishlist_server: BrowserServer
) -> None:
    page = open_home("en")
    _open_form(page)

    if how == "cancel":
        page.click(CANCEL)
    elif how == "reload":
        page.evaluate("location.reload()")
        page.wait_for("page reloaded", "!document.querySelector('.wishlist-create-form')")
    elif how == "navigate_home":
        page.navigate(f"{wishlist_server.base_url}/")
    elif how == "in_app_home":
        page.evaluate("showHome()", await_promise=True)
    else:
        page.evaluate("history.pushState({}, '', '/?step=2'); history.back()")
        page.wait_for("back navigation done", "location.search === ''", timeout=WAIT)
    if how != "back":
        # The form pushes no history entry, so a same-document back leaves the screen as it is.
        _settle_home(page, "en")

    assert _lists(wishlist_server) == [], "leaving without confirming must create nothing"
    if how in {"cancel", "in_app_home"}:
        assert _counts(page)["create"] == 0
    if how == "cancel":
        assert page.evaluate("document.activeElement === document.querySelector('#app h1')"), (
            "after Cancel the focus must land on the home heading"
        )


@pytest.mark.parametrize("how", ["cancel", "reload"])
def test_partly_filled_form_creates_nothing_and_reopens_empty(
    how: str, open_home: OpenHome, wishlist_server: BrowserServer
) -> None:
    page = open_home("en")
    _open_form(page)
    _set(page, "name", "Half typed")
    _set(page, "description", "Some text")

    if how == "cancel":
        page.click(CANCEL)
    else:
        page.navigate(f"{wishlist_server.base_url}/")
    _settle_home(page, "en")
    assert _lists(wishlist_server) == []

    _open_form(page)
    assert set(_values(page).values()) == {""}, "a cancelled form must not leave a draft"
    assert _lists(wishlist_server) == []


# --- 2 explicit, valid confirmation -----------------------------------------------------------


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_valid_create_makes_one_list_opens_it_and_home_lists_it(
    locale: Literal["en", "ru"], open_home: OpenHome, wishlist_server: BrowserServer
) -> None:
    page = open_home(locale)
    _open_form(page)
    _set(page, "name", "  Birthday  ")
    _set(page, "description", "At home")
    _set(page, "event_title", "Turns 30")
    _set(page, "event_date", "2030-05-01T10:00")
    page.click(SUBMIT)
    page.wait_for("the new list opens", f"!!document.querySelector('{LIST_TITLE}')", timeout=WAIT)

    assert page.evaluate(f"document.querySelector('{LIST_TITLE}').innerText") == "Birthday"
    lists = _lists(wishlist_server)
    assert [item["name"] for item in lists] == ["Birthday"]
    assert lists[0]["description"] == "At home"
    assert lists[0]["event_title"] == "Turns 30"
    assert str(lists[0]["event_date"]).startswith("2030-05-01T10:00")
    assert lists[0]["status"] == "active" and lists[0]["role"] == "owner"
    assert _counts(page)["create"] == 1

    page.click(".list-back-btn")
    _settle_home(page, locale)
    titles = page.evaluate(
        "Array.from(document.querySelectorAll('.wishlist-card-title'), c => c.innerText)"
    )
    assert "Birthday" in titles, titles


def test_optional_fields_may_stay_empty(
    open_home: OpenHome, wishlist_server: BrowserServer
) -> None:
    page = open_home("en")
    _open_form(page)
    _set(page, "name", "Just a title")
    page.click(SUBMIT)
    page.wait_for("the new list opens", f"!!document.querySelector('{LIST_TITLE}')", timeout=WAIT)
    lists = _lists(wishlist_server)
    assert [item["name"] for item in lists] == ["Just a title"]
    assert lists[0]["event_date"] is None


# --- 3 validation keeps what was typed --------------------------------------------------------


@pytest.mark.parametrize(
    ("locale", "title", "error"),
    [
        ("en", "", "error_title_required"),
        ("ru", "   ", "error_title_required"),
        ("en", "x" * (MAX_TITLE + 1), "error_title_too_long"),
        ("ru", "ж" * (MAX_TITLE + 1), "error_title_too_long"),
    ],
    ids=["en-empty", "ru-blank", "en-256", "ru-256"],
)
def test_invalid_title_shows_an_inline_error_keeps_values_and_sends_nothing(
    locale: Literal["en", "ru"],
    title: str,
    error: str,
    open_home: OpenHome,
    wishlist_server: BrowserServer,
) -> None:
    page = open_home(locale)
    _open_form(page)
    _set(page, "name", title)
    _set(page, "description", "keep me")
    _set(page, "event_title", "Party")
    page.evaluate(
        """(() => { window.__seen = [];
      new MutationObserver(() => window.__seen.push(document.getElementById('status').innerText))
        .observe(document.getElementById('status'), {childList: true, characterData: true,
          subtree: true}); })()"""
    )
    page.click(SUBMIT)
    page.wait_for(
        "inline title error", "!!document.getElementById('create-error-name')", timeout=WAIT
    )

    expected = _create_text(locale, error, max=MAX_TITLE)
    assert _error_text(page, "name") == expected
    state = page.evaluate(
        f"""(() => {{
      const input = document.querySelector('{FORM} input[name="name"]');
      const error = document.getElementById('create-error-name');
      return {{
        invalid: input.getAttribute('aria-invalid'),
        describedby: input.getAttribute('aria-describedby'),
        role: error.getAttribute('role'),
        focused: document.activeElement === input,
        seen: window.__seen,
      }};
    }})()"""
    )
    assert state["invalid"] == "true"
    assert "create-error-name" in str(state["describedby"]).split()
    assert state["role"] == "alert"
    assert state["focused"], "the first invalid field must receive the focus"
    assert _create_text(locale, "pending") not in state["seen"], "no 'Creating...' flash"
    assert _values(page)["name"] == title
    assert _values(page)["description"] == "keep me"
    assert _values(page)["event_title"] == "Party"
    assert _counts(page)["create"] == 0
    assert _lists(wishlist_server) == []


def test_fixing_the_title_clears_the_error_and_the_submit_succeeds(
    open_home: OpenHome, wishlist_server: BrowserServer
) -> None:
    page = open_home("en")
    _open_form(page)
    _set(page, "name", "   ")
    page.click(SUBMIT)
    page.wait_for("inline error", "!!document.getElementById('create-error-name')", timeout=WAIT)

    _set(page, "name", "Fixed")
    cleared = page.evaluate(
        f"""(() => {{
      const error = document.getElementById('create-error-name');
      const input = document.querySelector('{FORM} input[name="name"]');
      return (!error || !error.innerText) && input.getAttribute('aria-invalid') !== 'true';
    }})()"""
    )
    assert cleared, "editing the field must clear its error"
    page.click(SUBMIT)
    page.wait_for("the new list opens", f"!!document.querySelector('{LIST_TITLE}')", timeout=WAIT)
    assert [item["name"] for item in _lists(wishlist_server)] == ["Fixed"]


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_five_digit_year_gives_a_date_error_without_a_request_or_exception(
    locale: Literal["en", "ru"], open_home: OpenHome, wishlist_server: BrowserServer
) -> None:
    page = open_home(locale)
    _open_form(page)
    _set(page, "name", "Birthday")
    _set(page, "event_date", "20000-01-01T00:00")
    page.click(SUBMIT)
    page.wait_for(
        "inline date error", "!!document.getElementById('create-error-event_date')", timeout=WAIT
    )

    assert _error_text(page, "event_date") == _create_text(locale, "error_date_invalid")
    assert _values(page)["name"] == "Birthday"
    assert _counts(page)["create"] == 0
    assert page.evaluate("window.__t.errors") == [], "no uncaught error is allowed"
    assert _lists(wishlist_server) == []


@pytest.mark.parametrize(
    ("mode", "field", "error"),
    [
        ("422name", "name", "error_title_required"),
        ("422date", "event_date", "error_date_invalid"),
    ],
)
def test_server_422_is_mapped_to_the_field_and_keeps_the_values(
    mode: str, field: str, error: str, open_home: OpenHome
) -> None:
    page = open_home("en")
    _open_form(page)
    _set(page, "name", "Birthday")
    _set(page, "description", "keep me")
    _mode(page, "create", mode)
    page.click(SUBMIT)
    page.wait_for(
        f"inline {field} error", f"!!document.getElementById('create-error-{field}')", timeout=WAIT
    )

    assert _error_text(page, field) == _create_text("en", error)
    assert _values(page)["name"] == "Birthday"
    assert _values(page)["description"] == "keep me"
    assert _active(page)["name"] == field, "the focus goes to the first invalid field"
    assert _status(page)["text"] == "", "a mapped 422 leaves no stale 'Creating...' status"
    assert page.evaluate("document.querySelector('#app .list-title')") is None
    submit = page.evaluate(f"document.querySelector('{SUBMIT}').disabled")
    assert submit is False, "Create must be usable again"


def test_server_422_with_an_unknown_location_is_a_generic_failure(open_home: OpenHome) -> None:
    page = open_home("en")
    _open_form(page)
    _set(page, "name", "Birthday")
    _mode(page, "create", "422unknown")
    page.click(SUBMIT)
    message = json.dumps(_text("en", "miniapp.home.create_failed"))
    page.wait_for(
        "generic failure",
        f"document.getElementById('status').innerText === {message}",
        timeout=WAIT,
    )
    assert page.evaluate("document.querySelectorAll('.settings-field-error').length") == 0
    assert _values(page)["name"] == "Birthday"


# --- 4 double submit --------------------------------------------------------------------------


def test_enter_and_tap_burst_sends_exactly_one_post(
    open_home: OpenHome, wishlist_server: BrowserServer
) -> None:
    """Replaces ``test_create_wishlist_burst_sends_a_single_post`` for the confirming Create."""
    page = open_home("en")
    _open_form(page)
    _set(page, "name", "Birthday")
    _mode(page, "create", "hold")

    page.evaluate(f"document.querySelector('{FORM} input[name=\"name\"]').focus()")
    page.press_key("Enter")
    _wait_count(page, "create", 1)
    page.evaluate(
        f"(() => {{ const b = document.querySelector('{SUBMIT}'); b.click(); b.click();"
        " b.click(); })()"
    )
    page.press_key("Enter")
    page.press_key("Enter")
    held = page.evaluate(
        f"""({{
      create: window.__t.counts.create,
      submitDisabled: document.querySelector('{SUBMIT}').disabled,
      cancelDisabled: document.querySelector('{CANCEL}').disabled,
      busy: document.querySelector('{SUBMIT}').getAttribute('aria-busy'),
      readonly: Array.from(document.querySelectorAll('{FORM} input'), i => i.readOnly),
    }})"""
    )
    assert held["create"] == 1, f"taps and Enter while held sent {held['create']} requests"
    assert held["submitDisabled"] and held["cancelDisabled"] and held["busy"] == "true"
    assert held["readonly"] == [True] * 4, "inputs are read-only while the request is held"

    page.evaluate("window.__t.release('create')")
    page.wait_for("the new list opens", f"!!document.querySelector('{LIST_TITLE}')", timeout=WAIT)
    assert _counts(page)["create"] == 1
    assert len(_lists(wishlist_server)) == 1


def test_real_tap_burst_sends_exactly_one_post(
    open_home: OpenHome, wishlist_server: BrowserServer
) -> None:
    page = open_home("en")
    _open_form(page)
    _set(page, "name", "Birthday")
    _mode(page, "create", "hold")
    page.click(SUBMIT)
    _wait_count(page, "create", 1)
    page.evaluate(
        f"(() => {{ const b = document.querySelector('{SUBMIT}'); b.click(); b.click(); }})()"
    )
    page.evaluate("window.__t.release('create')")
    page.wait_for("the new list opens", f"!!document.querySelector('{LIST_TITLE}')", timeout=WAIT)
    assert _counts(page)["create"] == 1
    assert len(_lists(wishlist_server)) == 1


def test_a_blank_title_never_flashes_the_pending_status(open_home: OpenHome) -> None:
    page = open_home("en")
    _open_form(page)
    page.evaluate(
        """(() => { window.__seen = [];
      new MutationObserver(() => window.__seen.push(document.getElementById('status').innerText))
        .observe(document.getElementById('status'), {childList: true, characterData: true,
          subtree: true}); })()"""
    )
    page.evaluate(f"document.querySelector('{FORM} input[name=\"name\"]').focus()")
    page.press_key("Enter")
    page.wait_for("inline error", "!!document.getElementById('create-error-name')", timeout=WAIT)
    assert _create_text("en", "pending") not in page.evaluate("window.__seen")
    assert _counts(page)["create"] == 0


# --- 5 failure and retry ----------------------------------------------------------------------


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_failed_creation_keeps_the_form_and_a_retry_creates_exactly_one_list(
    locale: Literal["en", "ru"], open_home: OpenHome, wishlist_server: BrowserServer
) -> None:
    page = open_home(locale)
    _open_form(page)
    _set(page, "name", "Birthday")
    _set(page, "description", "keep me")
    _mode(page, "create", "500")
    page.click(SUBMIT)
    message = json.dumps(_text(locale, "miniapp.home.create_failed"))
    page.wait_for(
        "failure text", f"document.getElementById('status').innerText === {message}", timeout=WAIT
    )

    state = _status(page)
    assert state["kind"] == "error" and state["live"] == "assertive", state
    assert _values(page) == {
        "name": "Birthday",
        "description": "keep me",
        "event_title": "",
        "event_date": "",
    }
    assert _lists(wishlist_server) == []
    enabled = page.evaluate(
        f"""({{
      submit: !document.querySelector('{SUBMIT}').disabled,
      cancel: !document.querySelector('{CANCEL}').disabled,
      focused: document.activeElement === document.querySelector('{SUBMIT}'),
      readonly: document.querySelectorAll('{FORM} input[readonly]').length,
    }})"""
    )
    assert enabled == {"submit": True, "cancel": True, "focused": True, "readonly": 0}, enabled

    _mode(page, "create", "real")
    page.click(SUBMIT)
    page.wait_for("the new list opens", f"!!document.querySelector('{LIST_TITLE}')", timeout=WAIT)
    assert [item["name"] for item in _lists(wishlist_server)] == ["Birthday"]
    assert _counts(page)["create"] == 2


def test_list_load_failure_after_a_committed_creation_returns_home_without_a_second_list(
    open_home: OpenHome, wishlist_server: BrowserServer
) -> None:
    page = open_home("en")
    _open_form(page)
    _set(page, "name", "Birthday")
    _mode(page, "detail", "500")
    page.click(SUBMIT)
    message = json.dumps(_text("en", "miniapp.list.load_failed"))
    page.wait_for(
        "list load failure",
        f"document.getElementById('status').innerText === {message}",
        timeout=WAIT,
    )

    state = page.evaluate(
        """({
      h1: document.querySelector('#app h1').innerText,
      focusedH1: document.activeElement === document.querySelector('#app h1'),
      form: !!document.querySelector('.wishlist-create-form'),
      titles: Array.from(document.querySelectorAll('.wishlist-card-title'), c => c.innerText),
    })"""
    )
    assert state["h1"] == _text("en", "miniapp.home.title")
    assert state["focusedH1"] and not state["form"]
    assert "Birthday" in state["titles"]
    assert _status(page)["kind"] == "error"
    assert _counts(page)["create"] == 1
    assert len(_lists(wishlist_server)) == 1


# --- 6 home render staleness guard ------------------------------------------------------------


def test_create_during_a_slow_home_load_shows_only_the_form(open_home: OpenHome) -> None:
    page = open_home("en")
    _open_form(page)
    _mode(page, "home", "hold")
    page.click(CANCEL)
    _wait_count(page, "home", 2)
    page.click(HOME_CREATE)
    page.wait_for("form", f"!!document.querySelector({json.dumps(FORM)})", timeout=WAIT)
    page.evaluate("window.__t.release('home')")
    _sleep(page)

    state = page.evaluate(
        f"""({{
      form: !!document.querySelector({json.dumps(FORM)}),
      sections: document.querySelectorAll('.wishlist-section').length,
      status: document.getElementById('status').innerText,
    }})"""
    )
    assert state == {"form": True, "sections": 0, "status": ""}, state


def test_two_overlapping_home_loads_render_one_set_of_sections(open_home: OpenHome) -> None:
    page = open_home("en")
    baseline = page.evaluate("document.querySelectorAll('.wishlist-section').length")
    _open_form(page)
    _mode(page, "home", "hold")
    page.click(CANCEL)
    _wait_count(page, "home", 2)
    page.click(HOME_CREATE)
    page.wait_for("form", f"!!document.querySelector({json.dumps(FORM)})", timeout=WAIT)
    page.click(CANCEL)
    _wait_count(page, "home", 3)
    page.evaluate("window.__t.release('home')")
    _mode(page, "home", "real")
    _settle_home(page, "en")
    _sleep(page)

    sections = page.evaluate("document.querySelectorAll('.wishlist-section').length")
    assert sections == baseline, f"stale loads appended extra sections: {sections} vs {baseline}"


# --- 7 deep link and entry points -------------------------------------------------------------


def test_deep_link_opens_home_without_a_form_and_creates_nothing(
    open_home: OpenHome, wishlist_server: BrowserServer
) -> None:
    """Regression guard for D9 (green today and after): ``startapp=create`` only focuses."""
    page = open_home("en", query="startapp=create")
    assert page.evaluate(f"!!document.querySelector({json.dumps(FORM)})") is False
    assert page.evaluate("document.querySelector('#app h1').innerText") == _text(
        "en", "miniapp.home.title"
    )
    assert _lists(wishlist_server) == []


# --- 8 layout, touch targets, accessibility ---------------------------------------------------


@pytest.mark.parametrize(("locale", "width"), [("en", 320), ("ru", 320), ("en", 412), ("ru", 412)])
def test_form_fits_the_narrow_screen_with_large_targets_and_a_visible_error(
    locale: Literal["en", "ru"], width: int, open_home: OpenHome
) -> None:
    page = open_home(locale, width)
    _open_form(page)
    _set(page, "name", "W" * (MAX_TITLE + 1))
    _set(page, "description", "D" * 200)
    page.click(SUBMIT)
    page.wait_for("inline error", "!!document.getElementById('create-error-name')", timeout=WAIT)

    problems = width_problems(page, width, targets=True)
    assert not problems, f"{problems}\n{page.snapshot()}"
    heights = page.evaluate(
        f"Array.from(document.querySelectorAll('{FORM} input, {FORM} button'),"
        " e => Math.round(e.getBoundingClientRect().height))"
    )
    assert len(heights) == 6 and all(h >= 44 for h in heights), heights
    assert_reachable(page, f"create form {locale}", SUBMIT, [width])
    assert_reachable(page, f"create form {locale}", CANCEL, [width])


def test_form_has_readable_text_and_a_visible_focus_ring(open_home: OpenHome) -> None:
    page = open_home("en")
    _open_form(page)
    assert_contrast_and_focus(page, "create form")


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_accessibility_tree_names_the_fields_and_exposes_the_error(
    locale: Literal["en", "ru"], open_home: OpenHome
) -> None:
    page = open_home(locale)
    _open_form(page)
    page.evaluate(f"document.querySelector('{FORM} input[name=\"name\"]').focus()")
    page.press_key("Enter")
    page.wait_for("inline error", "!!document.getElementById('create-error-name')", timeout=WAIT)

    error = _create_text(locale, "error_title_required")
    nodes = page._send("Accessibility.getFullAXTree")["nodes"]  # noqa: SLF001
    live = [n for n in nodes if not n.get("ignored")]
    boxes = [
        n
        for n in live
        if n.get("role", {}).get("value") == "textbox"
        and _create_text(locale, "field_title") in str(n.get("name", {}).get("value", ""))
    ]
    assert boxes, "the title field must be a textbox named by its label (with '(required)')"
    properties = {p["name"]: p["value"].get("value") for p in boxes[0].get("properties", [])}
    assert properties.get("required") is True
    assert str(properties.get("invalid")) in {"true", "True"}
    assert error in str(boxes[0].get("description", {}).get("value", "")), (
        "the error must be linked through aria-describedby"
    )
    alerts = [n for n in live if n.get("role", {}).get("value") == "alert"]
    by_id = {n["nodeId"]: n for n in nodes}

    def alert_text(node: dict[str, Any]) -> str:
        own = str(node.get("name", {}).get("value", ""))
        below = (alert_text(by_id[c]) for c in node.get("childIds", []) if c in by_id)
        return " ".join([own, *below])

    assert any(error in alert_text(n) for n in alerts), "an alert must carry the error text"
    headings = [n for n in live if n.get("role", {}).get("value") == "heading"]
    assert any(
        _create_text(locale, "title") == str(n.get("name", {}).get("value", "")) for n in headings
    )
    buttons = {
        str(n.get("name", {}).get("value", ""))
        for n in live
        if n.get("role", {}).get("value") == "button"
    }
    assert {_create_text(locale, "submit"), _text(locale, "miniapp.wishlist_settings.cancel")} <= (
        buttons
    )


def test_tab_order_follows_the_visual_order(open_home: OpenHome) -> None:
    page = open_home("en")
    _open_form(page)
    page.evaluate("document.activeElement.blur(); document.querySelector('#app h1').focus()")
    order: list[str] = []
    # A datetime-local input has several native tab stops (month, day, year, ...): collapse them.
    for _ in range(14):
        page.press_key("Tab")
        stop = page.evaluate(
            "document.activeElement.getAttribute('name') || "
            f"(document.activeElement.matches('{SUBMIT}') ? 'submit' : "
            f"document.activeElement.matches('{CANCEL}') ? 'cancel' : 'other')"
        )
        if not order or order[-1] != stop:
            order.append(stop)
        if stop == "cancel":
            break
    assert order == [
        "name",
        "description",
        "event_title",
        "event_date",
        "submit",
        "cancel",
    ], order


# --- WISHENKA-320 name contract ---------------------------------------------------------------


def _wait_name_decision(page: CdpPage) -> None:
    page.wait_for(
        "create name decision",
        "!!document.getElementById('create-error-name') || window.__t.counts.create > 0",
        timeout=WAIT,
    )


@pytest.mark.parametrize("locale", ["en", "ru"])
@pytest.mark.parametrize(
    ("label", "title"),
    [("zwsp", "\u200b"), ("marks-and-spaces", " \u200b \u2060 \ufeff ")],
)
def test_invisible_only_name_shows_the_required_message_and_creates_nothing(
    locale: Literal["en", "ru"],
    label: str,
    title: str,
    open_home: OpenHome,
    wishlist_server: BrowserServer,
) -> None:
    page = open_home(locale)
    _open_form(page)
    _set(page, "name", title)
    _set(page, "description", "keep me")
    page.click(SUBMIT)
    _wait_name_decision(page)

    assert _counts(page)["create"] == 0, f"invisible-only name {label} must not be posted"
    assert _error_text(page, "name") == _create_text(locale, "error_title_required")
    assert _values(page)["name"] == title
    assert _values(page)["description"] == "keep me"
    assert _lists(wishlist_server) == []


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_too_long_error_type_uses_the_too_long_catalog_string(
    locale: Literal["en", "ru"], open_home: OpenHome, wishlist_server: BrowserServer
) -> None:
    page = open_home(locale)
    _open_form(page)
    _set(page, "name", "Birthday")
    _mode(page, "create", "422tooLong")
    page.click(SUBMIT)
    page.wait_for(
        "inline title error", "!!document.getElementById('create-error-name')", timeout=WAIT
    )

    required = _create_text(locale, "error_title_required")
    too_long = _create_text(locale, "error_title_too_long", max=MAX_TITLE)
    assert _error_text(page, "name") == too_long, (
        "422 type wishlist_name_too_long must use the too-long catalog string; "
        f"shown={_error_text(page, 'name')!r} required={required!r}"
    )
    assert _values(page)["name"] == "Birthday"
    assert page.evaluate("document.querySelector('#app .list-title')") is None
    assert _lists(wishlist_server) == []


def test_edge_bom_stays_in_the_submitted_name(
    open_home: OpenHome, wishlist_server: BrowserServer
) -> None:
    """The POST body keeps an edge U+FEFF. A second trim would drop it."""
    page = open_home("en")
    _open_form(page)
    _set(page, "name", "  \ufeffHi  ")
    page.click(SUBMIT)
    _wait_name_decision(page)

    body = json.loads(page.evaluate("window.__t.lastCreateBody"))
    assert body["name"] == "\ufeffHi"
    assert [item["name"] for item in _lists(wishlist_server)] == ["\ufeffHi"]
