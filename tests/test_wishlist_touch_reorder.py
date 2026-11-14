"""Failing repro for WISHENKA-109: touch-friendly drag reordering of wishes.

The owner must be able to reorder wishes with a finger (Telegram mobile). The
drag handle moves into the always-visible card summary, ``/static/wishlist.js``
gains pointer-event drag code and Telegram integration, and ``miniapp.css``
gains touch rules and drop-indicator classes.

Groups A, C and D are red on the current code; group B and the marked guards
are green by design and protect behaviour that must survive the change.

The remaining script and stylesheet checks are string/regex inspections only (Telegram SDK
tokens, ``-webkit-touch-callout``, guards). Gesture behaviour and computed styles are covered by
the browser tests of WISHENKA-110 (``test_wishlist_*_browser.py``); the string checks they
replaced were removed.

No network and no browser: only ``TestClient`` requests and text inspection.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from wishenka.auth.models import AuthenticatedUser
from wishenka.auth.session import SessionTokenService
from wishenka.config import Settings
from wishenka.web.app import create_app
from wishenka.wishlists.service import WishlistService

pytestmark = pytest.mark.timeout(30)

OWNER_ID = 101

EXPECTED_EXTERNAL_SCRIPTS = {
    "https://telegram.org/js/telegram-web-app.js",
    "https://unpkg.com/htmx.org@1.9.12",
    "https://unpkg.com/htmx.org@1.9.12/dist/ext/json-enc.js",
}

# Telegram SDK tokens stay string checks: the SDK is out of the browser tests' scope
# (WISHENKA-110, item 19); remove with WISHENKA-143. Gesture tokens (pointer events, Escape,
# visibilitychange, htmx:beforeSwap, class names, submitReorder ...) are covered by the browser
# tests in ``test_wishlist_touch_reorder_browser.py``.
SDK_TOKENS = [
    "disableVerticalSwipes",
    "enableVerticalSwipes",
    "isVersionAtLeast",
    "HapticFeedback",
]

# ``-webkit-touch-callout`` is iOS-only and cannot be seen in computed styles of desktop Chromium;
# touch-action, user-select and the 44px size are checked as computed styles in the browser tests.
HANDLE_DECLARATIONS = ["-webkit-touch-callout: none"]


@dataclass(frozen=True)
class Seeded:
    """Seeded wishlist identifiers and ready-made request headers."""

    client: TestClient
    wishlist_id: int
    public_token: str
    item_ids: list[int]
    owner_headers: dict[str, str]


@pytest.fixture
def seeded(tmp_path: Path) -> Iterator[Seeded]:
    """Create an app on isolated SQLite with an owner wishlist holding two wishes."""
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'wishlist_touch_reorder.db'}",
        secret_key="wishlist-touch-reorder-test-secret",
    )
    app = create_app(settings)
    sessions = SessionTokenService(settings.secret_key)
    service: WishlistService = app.state.domain_service
    owner = AuthenticatedUser(
        telegram_id=OWNER_ID,
        first_name="Alice",
        username=None,
        auth_method="session_token",
    )

    async def seed() -> tuple[int, str, list[int]]:
        wl = await service.create_wishlist(owner=owner, title="Touch Reorder Wishlist")
        first = await service.add_wish_item(wishlist_id=wl.id, actor=owner, title="Item Alpha")
        second = await service.add_wish_item(wishlist_id=wl.id, actor=owner, title="Item Beta")
        return wl.id, str(wl.public_token), [first.id, second.id]

    with TestClient(app) as client:
        wl_id, token, item_ids = asyncio.run(seed())
        headers = {
            "Authorization": f"Bearer {sessions.create_token(OWNER_ID, 'Alice')}",
            "HX-Request": "true",
        }
        yield Seeded(client, wl_id, token, item_ids, headers)


def fetch_page(seeded: Seeded, page: str) -> BeautifulSoup:
    """Fetch the owner or share page, asserting the seed rendered (smoke check)."""
    if page == "owner":
        url = f"/web/wishlists/{seeded.wishlist_id}"
        resp = seeded.client.get(url, headers=seeded.owner_headers)
    else:
        resp = seeded.client.get(f"/share/{seeded.public_token}")
    assert resp.status_code == 200
    soup = BeautifulSoup(resp.text, "html.parser")
    assert len(soup.select(".item-card-summary")) == len(seeded.item_ids)
    return soup


def fetch_static(seeded: Seeded, name: str) -> str:
    """Fetch a static asset as text, asserting it is served."""
    resp = seeded.client.get(f"/static/{name}")
    assert resp.status_code == 200
    return str(resp.text)


def strip_js_comments(source: str) -> str:
    """Remove ``/* */`` and ``//`` comments (good enough for this code base)."""
    without_blocks = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"(?m)(?<![:'\"])//.*$", "", without_blocks)


def css_declarations(css: str, selector: str) -> str | None:
    """Join the declarations of every rule whose selector list names ``selector``.

    Return ``None`` when no rule has ``selector`` as one entry of its list.
    """
    bodies: list[str] = []
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        selectors = [part.strip() for part in match.group(1).split(",")]
        if selector in selectors:
            bodies.append(match.group(2))
    if not bodies:
        return None
    return " ".join(" ".join(body.split()) for body in bodies)


# --- A. Owner markup: handle moves into the summary (red) ----------------------


def test_owner_summary_contains_single_drag_handle(seeded: Seeded) -> None:
    """Each summary holds exactly one handle that is no-toggle and aria-hidden.

    Red today: the handle lives in ``.item-actions`` inside the details.
    """
    soup = fetch_page(seeded, "owner")
    for summary in soup.select(".item-card-summary"):
        handles = summary.select(".item-drag-handle")
        assert len(handles) == 1, f"expected one handle in summary, got {len(handles)}"
        handle = handles[0]
        assert handle.has_attr("data-no-toggle")
        assert handle.get("aria-hidden") == "true"


def test_owner_details_has_no_drag_handle(seeded: Seeded) -> None:
    """The handle is moved, not duplicated: none remains inside the details.

    Red today: the handle is rendered inside ``.item-card-details``.
    """
    soup = fetch_page(seeded, "owner")
    for details in soup.select(".item-card-details"):
        assert not details.select(".item-drag-handle")


# --- B. Markup and safety guards (green by design) -----------------------------


def test_share_page_has_no_handle_or_draggable(seeded: Seeded) -> None:
    """Guard (green by design): the public share page offers no reordering UI."""
    soup = fetch_page(seeded, "share")
    assert not soup.select(".item-drag-handle")
    assert not soup.select("[draggable]")


def test_owner_cards_keep_draggable_and_move_buttons(seeded: Seeded) -> None:
    """Guard (green by design): mouse drag, step buttons and a11y contract stay."""
    soup = fetch_page(seeded, "owner")
    cards = soup.select(".item-card")
    assert len(cards) == len(seeded.item_ids)
    for card in cards:
        assert card.get("draggable") == "true"
        for selector in (".btn-move-up", ".btn-move-down"):
            button = card.select_one(selector)
            assert button is not None, f"missing {selector}"
            assert button.get("aria-label")
        summary = card.select_one(".item-card-summary")
        assert summary is not None
        assert summary.get("role") == "button"
        assert summary.get("tabindex") == "0"
        assert summary.get("aria-expanded") == "false"


def test_no_new_third_party_scripts(seeded: Seeded) -> None:
    """Guard (green by design): no new external script, no sortable library."""
    soup = fetch_page(seeded, "owner")
    external = {str(s["src"]) for s in soup.find_all("script", src=True)}
    local = {src for src in external if src.startswith("/")}
    assert external - local == EXPECTED_EXTERNAL_SCRIPTS
    assert not any("sortable" in src.lower() for src in external)


# --- C. /static/wishlist.js tokens (red; string checks only) -------------------


@pytest.mark.parametrize("token", SDK_TOKENS)
def test_wishlist_script_contains_sdk_token(seeded: Seeded, token: str) -> None:
    """wishlist.js contains the Telegram SDK token required by the touch-drag design.

    This is a string check: it proves the token is present, not that the SDK integration
    behaves correctly (out of scope of the browser tests, WISHENKA-143).
    """
    body = fetch_static(seeded, "wishlist.js")
    assert token in body, f"wishlist.js lacks {token!r}"


def test_wishlist_script_has_single_reorder_submit_point(seeded: Seeded) -> None:
    """Guard (green by design): one non-comment ``htmx.ajax(`` call in the script.

    Mouse and touch drags must share one submit path, so the number of real
    ``htmx.ajax(`` calls (comments stripped) stays at exactly one.
    """
    body = strip_js_comments(fetch_static(seeded, "wishlist.js"))
    assert body.count("htmx.ajax(") == 1


# --- D. /static/miniapp.css rules (red except the guard) -----------------------


@pytest.mark.parametrize("declaration", HANDLE_DECLARATIONS)
def test_css_drag_handle_declares_touch_rules(seeded: Seeded, declaration: str) -> None:
    """``.item-drag-handle`` rule carries the iOS-only touch declaration (no browser check)."""
    block = css_declarations(fetch_static(seeded, "miniapp.css"), ".item-drag-handle")
    assert block is not None, "no .item-drag-handle rule"
    assert declaration in block, f".item-drag-handle lacks {declaration!r}: {block!r}"


def test_css_summary_does_not_block_touch_scroll(seeded: Seeded) -> None:
    """Guard (green by design): ``.item-card-summary`` must never get ``touch-action: none``.

    A touch-action lock on the whole summary would block list scrolling and
    expanding by tap; only the handle may lock it.
    """
    css = fetch_static(seeded, "miniapp.css")
    block = css_declarations(css, ".item-card-summary")
    assert block is not None, "no .item-card-summary rule"
    assert "touch-action: none" not in block
