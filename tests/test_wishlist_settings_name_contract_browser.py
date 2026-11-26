"""Browser coverage for the WISHENKA-320 settings name contract.

The owner opens a list and saves settings in Russian and English. An invisible-only,
blank, or too-long name must not be sent, and the typed value stays with the catalog
message. An accepted name is submitted already normalized, including an edge U+FEFF.
A stored empty name still shows the untitled label and is not rewritten by opening it.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Literal

import pytest

from tests.browser_cdp import CdpBrowser, CdpPage
from tests.browser_helpers import scroll_to
from tests.browser_screens import open_miniapp, provision_user
from tests.conftest import OWNER_TELEGRAM_ID, BrowserServer
from tests.test_wishlist_detail_browser import _mock_detail
from wishenka.i18n import CATALOG

pytestmark = [pytest.mark.timeout(45), pytest.mark.browser]

WAIT = 3.0
FORM = ".wishlist-settings-form"
MAX_TITLE = 255
BOM = "\ufeff"
ZWSP = "\u200b"


def _table(locale: str) -> dict[str, str]:
    return CATALOG["ru" if locale == "ru" else "en"]


def _text(locale: str, key: str, **params: object) -> str:
    template = _table(locale).get(key, f"<missing catalog key {key}>")
    for name, value in params.items():
        template = template.replace("{" + name + "}", str(value))
    return template


def _open_settings(
    locale: Literal["en", "ru"],
    seed_wishlist: Callable[..., Any],
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    pages: list[CdpPage],
    *,
    name: str | None = None,
) -> CdpPage:
    seeded = seed_wishlist(["Camera"])
    provision_user(wishlist_server, seeded.owner_token, OWNER_TELEGRAM_ID, "Owner", locale)
    page = open_miniapp(
        chromium_browser,
        pages,
        wishlist_server,
        seeded.owner_token,
        locale,
        viewport=(412, 800),
    )
    _mock_detail(page, seeded.wishlist_id)
    if name is not None:
        page.evaluate(f"window.detail.name = {json.dumps(name)}")
    page.click(".wishlist-card-open")
    page.wait_for("settings form", f"!!document.querySelector({json.dumps(FORM)})", timeout=WAIT)
    return page


def _set(page: CdpPage, name: str, value: str) -> None:
    stored = page.evaluate(
        f"""(() => {{
          const input = document.querySelector({json.dumps(FORM + ' input[name="' + name + '"]')});
          if (!input) return null;
          input.value = {json.dumps(value)};
          input.dispatchEvent(new Event('input', {{bubbles: true}}));
          return input.value;
        }})()"""
    )
    assert stored == value, f"field {name!r} did not take the value"


def _patches(page: CdpPage) -> list[dict[str, Any]]:
    calls = page.evaluate("window.detailCalls.filter(call => call.method === 'PATCH')")
    assert isinstance(calls, list)
    return calls


def _save(page: CdpPage) -> None:
    scroll_to(page, ".settings-save-btn")
    page.click(".settings-save-btn")
    page.wait_for(
        "settings name decision",
        "!!document.querySelector('.wishlist-settings-form .settings-field-error')"
        " || (window.detailCalls || []).some(call => call.method === 'PATCH')",
        timeout=WAIT,
    )


def _field_error(page: CdpPage) -> str:
    text = page.evaluate(
        "document.querySelector('.wishlist-settings-form .settings-field-error')?.innerText || ''"
    )
    return str(text)


@pytest.mark.parametrize("locale", ["en", "ru"])
@pytest.mark.parametrize(
    ("label", "title", "message"),
    [
        ("empty", "", "required"),
        ("spaces", "   ", "required"),
        ("zwsp", ZWSP, "required"),
        ("too-long", "n" * (MAX_TITLE + 1), "too_long"),
    ],
)
def test_invalid_settings_name_is_not_saved(
    locale: Literal["en", "ru"],
    label: str,
    title: str,
    message: str,
    seed_wishlist: Callable[..., Any],
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    page = _open_settings(locale, seed_wishlist, wishlist_server, chromium_browser, _browser_pages)
    _set(page, "name", title)
    _set(page, "description", "keep me")
    _save(page)

    expected = _text(
        locale,
        "miniapp.create.error_title_required"
        if message == "required"
        else "miniapp.create.error_title_too_long",
        max=MAX_TITLE,
    )
    assert _patches(page) == [], f"{label} must not be saved"
    assert _field_error(page) == expected
    kept = page.evaluate(
        f"document.querySelector({json.dumps(FORM + ' input[name="name"]')}).value"
    )
    assert kept == title
    assert (
        page.evaluate(
            f"document.querySelector({json.dumps(FORM + ' input[name="description"]')}).value"
        )
        == "keep me"
    )


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_accepted_settings_name_keeps_an_edge_bom(
    locale: Literal["en", "ru"],
    seed_wishlist: Callable[..., Any],
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    page = _open_settings(locale, seed_wishlist, wishlist_server, chromium_browser, _browser_pages)
    _set(page, "name", f"  {BOM}Hi  ")
    _set(page, "description", "d" * (MAX_TITLE + 1))
    _set(page, "event_title", "e" * (MAX_TITLE + 1))
    _save(page)

    patches = _patches(page)
    assert len(patches) == 1
    body = json.loads(str(patches[0]["body"]))
    assert body["name"] == f"{BOM}Hi"
    assert body["description"] == "d" * (MAX_TITLE + 1)
    assert body["event_title"] == "e" * (MAX_TITLE + 1)


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_settings_details_have_no_maxlength(
    locale: Literal["en", "ru"],
    seed_wishlist: Callable[..., Any],
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    page = _open_settings(locale, seed_wishlist, wishlist_server, chromium_browser, _browser_pages)
    lengths = page.evaluate(
        f"""(() => {{
          const form = document.querySelector({json.dumps(FORM)});
          return ['description', 'event_title'].map(name => {{
            const input = form.querySelector('input[name="' + name + '"]');
            return input.getAttribute('maxlength');
          }});
        }})()"""
    )
    assert lengths == [None, None]
    _set(page, "description", "d" * (MAX_TITLE + 1))
    _set(page, "event_title", "e" * (MAX_TITLE + 1))
    _save(page)
    body = json.loads(str(_patches(page)[0]["body"]))
    assert body["description"] == "d" * (MAX_TITLE + 1)
    assert body["event_title"] == "e" * (MAX_TITLE + 1)


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_empty_stored_name_shows_the_untitled_label(
    locale: Literal["en", "ru"],
    seed_wishlist: Callable[..., Any],
    wishlist_server: BrowserServer,
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
) -> None:
    page = _open_settings(
        locale, seed_wishlist, wishlist_server, chromium_browser, _browser_pages, name=""
    )
    heading = page.evaluate("document.querySelector('#app h1').innerText")
    assert heading == _text(locale, "miniapp.common.untitled_wishlist")
    assert _patches(page) == []
    assert page.evaluate("window.detail.name") == ""
