"""Failing repro for WISHENKA-108: wishlist page script lives in a static file.

The expand/collapse toggle and drag-and-drop reordering must be served from
``/static/wishlist.js`` instead of the inline script in ``base.html``; cards must
carry no inline ``on*`` handlers; and ``#items-list`` must declare its wishlist id
via ``data-wishlist-id`` instead of the script parsing ``window.location``.

No network and no browser: only ``TestClient`` requests and HTML/text inspection.
"""

from __future__ import annotations

import asyncio
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
EXCLUSION_SELECTOR = "a, button, input, select, textarea, [data-no-toggle]"
PAGES = ["owner", "share"]


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
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'wishlist_static_script.db'}",
        secret_key="wishlist-static-script-test-secret",
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
        wl = await service.create_wishlist(owner=owner, title="Static Script Wishlist")
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


def fetch_page(seeded: Seeded, page: str, query: str = "") -> BeautifulSoup:
    """Fetch the owner or share page, asserting the seed rendered (smoke check)."""
    if page == "owner":
        url = f"/web/wishlists/{seeded.wishlist_id}{query}"
        resp = seeded.client.get(url, headers=seeded.owner_headers)
    else:
        resp = seeded.client.get(f"/share/{seeded.public_token}{query}")
    assert resp.status_code == 200
    soup = BeautifulSoup(resp.text, "html.parser")
    assert len(soup.select(".item-card-summary")) == len(seeded.item_ids)
    return soup


def inline_scripts(soup: BeautifulSoup) -> str:
    """Return the joined text of all inline (src-less) script elements."""
    return "\n".join(s.get_text() for s in soup.find_all("script") if not s.get("src"))


# --- A. Inline code removed from base.html -------------------------------------


@pytest.mark.parametrize("page", PAGES)
def test_inline_script_no_longer_holds_toggle_or_dnd(seeded: Seeded, page: str) -> None:
    """Toggle and DnD code must be gone from the inline script."""
    inline = inline_scripts(fetch_page(seeded, page))
    for marker in ("toggleWishCard", "dragstart", "dragover", "window.location", "/items/reorder"):
        assert marker not in inline, f"inline script still contains {marker!r}"


@pytest.mark.parametrize("page", PAGES)
def test_page_loads_wishlist_script_deferred_after_htmx(seeded: Seeded, page: str) -> None:
    """Head must reference /static/wishlist.js with defer, after the htmx script."""
    soup = fetch_page(seeded, page)
    scripts = soup.find_all("script", src=True)
    srcs = [str(s["src"]) for s in scripts]
    assert "/static/wishlist.js" in srcs, f"wishlist.js not referenced; scripts: {srcs}"
    tag = scripts[srcs.index("/static/wishlist.js")]
    assert tag.has_attr("defer")
    htmx_idx = next(i for i, src in enumerate(srcs) if "htmx.org" in src)
    assert srcs.index("/static/wishlist.js") > htmx_idx


# --- B. Static file ------------------------------------------------------------


def test_static_wishlist_script_content(seeded: Seeded) -> None:
    """GET /static/wishlist.js serves the toggle and DnD behaviour."""
    resp = seeded.client.get("/static/wishlist.js")
    assert resp.status_code == 200
    assert "javascript" in resp.headers["content-type"]
    body = resp.text
    for marker in (
        "toggleWishCard",
        EXCLUSION_SELECTOR,
        "'Enter'",
        "' '",
        ".item-card-summary",
        "dragstart",
        "dragover",
        "drop",
        "dragend",
        "/items/reorder",
    ):
        assert marker in body, f"wishlist.js lacks {marker!r}"
    assert "wishlistId" in body or "data-wishlist-id" in body
    assert "location.pathname" not in body
    assert "window.location" not in body


# --- C. item_card without inline handlers --------------------------------------


@pytest.mark.parametrize("page", PAGES)
def test_cards_have_no_inline_event_handlers(seeded: Seeded, page: str) -> None:
    """No element carries on* attributes; summary keeps its accessibility contract."""
    soup = fetch_page(seeded, page)
    offenders = [
        f"<{tag.name}> {attr}"
        for tag in soup.find_all(True)
        for attr in tag.attrs
        if attr.lower().startswith("on")
    ]
    assert not offenders, f"inline handlers remain: {offenders}"
    for summary in soup.select(".item-card-summary"):
        assert summary.get("role") == "button"
        assert summary.get("tabindex") == "0"
        assert summary.get("aria-expanded") == "false"
        assert summary.get("aria-controls")


# --- D. Explicit wishlist id ---------------------------------------------------


@pytest.mark.parametrize("page", PAGES)
def test_items_list_declares_wishlist_id(seeded: Seeded, page: str) -> None:
    """#items-list carries data-wishlist-id equal to the wishlist id."""
    section = fetch_page(seeded, page).select_one("#items-list")
    assert section is not None
    assert section.get("data-wishlist-id") == str(seeded.wishlist_id)


def test_items_list_wishlist_id_independent_of_query(seeded: Seeded) -> None:
    """The declared id does not change with the page address query."""
    section = fetch_page(seeded, "owner", "?x=1").select_one("#items-list")
    assert section is not None
    assert section.get("data-wishlist-id") == str(seeded.wishlist_id)


def test_guard_no_swap_replaces_items_list_container(seeded: Seeded) -> None:
    """Guard (green by design, not red): nothing replaces #items-list itself.

    The data attribute survives only while the container is never swapped out, so
    no ``hx-target="#items-list"`` may use ``outerHTML``/``delete`` (``none`` is
    allowed) and list fragments must not re-emit ``id="items-list"``.
    """
    soup = fetch_page(seeded, "owner")
    targeting = soup.select('[hx-target="#items-list"]')
    assert targeting, "expected elements targeting #items-list"
    for el in targeting:
        assert el.get("hx-swap") not in {"outerHTML", "delete"}

    first, second = seeded.item_ids
    wl = seeded.wishlist_id
    reorder = seeded.client.post(
        f"/web/wishlists/{wl}/items/reorder",
        data={"item_ids": [str(second), str(first)]},
        headers=seeded.owner_headers,
    )
    move = seeded.client.post(
        f"/web/wishlists/{wl}/items/{second}/move?direction=up",
        headers=seeded.owner_headers,
    )
    for resp in (reorder, move):
        assert resp.status_code == 200
        assert 'id="items-list"' not in resp.text
