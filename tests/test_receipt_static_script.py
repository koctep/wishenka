"""Red tests for the receipt script and the page wiring (WISHENKA-24, plan T-6).

No browser, no network: ``TestClient`` requests plus text inspection of the static scripts.
Behaviour of the scripts is proven in ``test_receipt_modal_browser.py``; these checks pin what a
browser test cannot see: the file is served and loaded after ``wishlist.js``, the inline script of
``base.html`` is untouched (N-2), the two refusal marker namespaces never meet, the closed reason
set mirrors ``receipts._REFUSALS`` and the new handlers guard a missing ``xhr``.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from bs4 import BeautifulSoup

from tests.receipt_support import AppEnv, app_env, new_symbol
from tests.receipt_ui_support import (
    REFUSAL_HEADER,
    REORDER_HEADER,
    Wish,
    domain,
    hx,
    modal_url,
    on_attributes,
    parse,
    receive,
    run,
    seed_list,
)
from tests.test_wishlist_touch_reorder import strip_js_comments
from wishenka.items.models import InputType
from wishenka.items.schemas import ItemPreviewDTO
from wishenka.items.service import ItemPreviewService

pytestmark = pytest.mark.timeout(30)

GUARD = re.compile(r"typeof\s+[\w.]*getResponseHeader\s*(?:!==?|===?)\s*['\"]function['\"]")
REASON_LIKE = re.compile(r"['\"]([a-z]+(?:_[a-z]+)+)['\"]")


@pytest.fixture
def env(tmp_path: Path) -> Iterator[AppEnv]:
    """Open create_app on an isolated SQLite file with bearer sessions."""
    with app_env(tmp_path) as opened:
        yield opened


def _owner_page(env: AppEnv) -> tuple[BeautifulSoup, int, int]:
    client, sessions, app = env
    wishlist_id, (item_id, *_rest) = seed_list(app, [Wish("Kettle", 5)])
    receive(app, item_id, 2)
    response = client.get(f"/web/wishlists/{wishlist_id}", headers=hx(sessions))
    assert response.status_code == 200, response.text
    return parse(response.text), wishlist_id, item_id


def _static(env: AppEnv, name: str) -> str:
    client, _sessions, _app = env
    response = client.get(f"/static/{name}")
    assert response.status_code == 200, f"/static/{name} is not served ({response.status_code})"
    return str(response.text)


def _handler_source(source: str, event: str) -> str:
    """Source of the ``event`` listeners (each up to the next ``addEventListener``)."""
    pieces: list[str] = []
    for match in re.finditer(rf"addEventListener\(\s*['\"]{re.escape(event)}['\"]", source):
        rest = source[match.start() :]
        following = rest.find("addEventListener(", 1)
        pieces.append(rest if following == -1 else rest[:following])
    assert pieces, f"no {event!r} listener found"
    return "\n".join(pieces)


def test_receipt_script_is_served_as_javascript(env: AppEnv) -> None:
    """N-2: ``/static/receipt.js`` exists and is JavaScript."""
    client, _sessions, _app = env
    response = client.get("/static/receipt.js")
    assert response.status_code == 200, "receipt.js is not served"
    assert "javascript" in response.headers["content-type"]


@pytest.mark.parametrize("kind", ["owner", "share"])
def test_pages_load_receipt_script_deferred_after_wishlist_script(env: AppEnv, kind: str) -> None:
    """N-2: ``<script src="/static/receipt.js" defer>`` follows htmx and ``wishlist.js``."""
    client, _sessions, app = env
    soup, wishlist_id, _item = _owner_page(env)
    if kind == "share":
        token = str(run(domain(app).get_wishlist_by_id(wishlist_id)).public_token)
        soup = parse(client.get(f"/share/{token}").text)
    tags = soup.find_all("script", src=True)
    sources = [str(tag["src"]) for tag in tags]
    assert "/static/receipt.js" in sources, f"receipt.js not referenced; scripts: {sources}"
    tag = tags[sources.index("/static/receipt.js")]
    assert tag.has_attr("defer")
    assert sources.index("/static/receipt.js") > sources.index("/static/wishlist.js")
    assert sources.index("/static/receipt.js") > next(
        i for i, src in enumerate(sources) if "htmx.org" in src
    )


def test_base_has_no_inline_scripts_and_loads_app_script_deferred(env: AppEnv) -> None:
    """WISHENKA-140: ``base.html`` has zero inline scripts and loads ``/static/app.js`` deferred."""
    soup, _wishlist_id, _item = _owner_page(env)
    inline = [tag.get_text() for tag in soup.find_all("script") if not tag.get("src")]
    assert inline == [], f"expected zero inline scripts, found {len(inline)}"

    tags = soup.find_all("script", src=True)
    sources = [str(tag["src"]) for tag in tags]
    assert "/static/app.js" in sources, f"app.js not referenced; scripts: {sources}"
    app_idx = sources.index("/static/app.js")
    assert tags[app_idx].has_attr("defer")
    htmx_idx = next(i for i, src in enumerate(sources) if "htmx.org" in src)
    assert app_idx > htmx_idx
    assert app_idx < sources.index("/static/wishlist.js")
    assert app_idx < sources.index("/static/receipt.js")

    app_js = strip_js_comments(_static(env, "app.js"))
    assert "/receipt" not in app_js.lower()


def test_single_ajax_call_in_each_script(env: AppEnv) -> None:
    """Decision 5: ``receipt.js`` has exactly one ``htmx.ajax(`` call; ``wishlist.js`` keeps one."""
    wishlist = strip_js_comments(_static(env, "wishlist.js"))
    assert wishlist.count("htmx.ajax(") == 1, "wishlist.js must keep exactly one htmx.ajax call"
    receipt = strip_js_comments(_static(env, "receipt.js"))
    assert receipt.count("htmx.ajax(") == 1


def test_pages_and_partials_carry_no_inline_handlers(
    env: AppEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Owner page, settings page, receipt dialog, and modal/preview partials have no ``on*``."""
    client, sessions, _app = env
    soup, wishlist_id, item_id = _owner_page(env)
    assert on_attributes(soup) == []

    settings_resp = client.get("/settings", headers=hx(sessions))
    assert settings_resp.status_code == 200, f"/settings returned {settings_resp.status_code}"
    settings_soup = parse(settings_resp.text)
    assert on_attributes(settings_soup) == [], "/settings has inline on* attributes"
    settings_inline = [
        tag.get_text() for tag in settings_soup.find_all("script") if not tag.get("src")
    ]
    assert settings_inline == [], "/settings has inline <script> tags"
    settings_tags = settings_soup.find_all("script", src=True)
    settings_sources = [str(tag["src"]) for tag in settings_tags]
    assert "/static/settings.js" in settings_sources
    assert settings_tags[settings_sources.index("/static/settings.js")].has_attr("defer")
    assert "javascript" in client.get("/static/settings.js").headers["content-type"]

    for url in (
        modal_url(wishlist_id, item_id),
        f"/web/wishlists/{wishlist_id}/items/{item_id}/edit",
        f"/web/wishlists/{wishlist_id}/items/{item_id}/archive-confirm",
    ):
        resp = client.get(url, headers=hx(sessions))
        assert resp.status_code == 200, f"{url} returned {resp.status_code}"
        assert on_attributes(parse(resp.text)) == [], f"{url} has inline on* attributes"

    async def mock_fetch_preview(
        self: ItemPreviewService,
        raw_input: str,
        http_client: httpx.AsyncClient | None = None,
    ) -> ItemPreviewDTO:
        return ItemPreviewDTO(
            input_type=InputType.EXPLICIT_URL,
            url="https://example.com/gift",
            title="Gift",
            description="Nice gift",
            image_url=None,
            price=100,
            currency="RUB",
            store_name="Example",
            is_fallback=False,
        )

    monkeypatch.setattr(ItemPreviewService, "fetch_preview", mock_fetch_preview)
    preview = client.post(
        f"/web/wishlists/{wishlist_id}/items/preview",
        data={"raw_input": "https://example.com/gift"},
        headers=hx(sessions),
    )
    assert preview.status_code == 200, preview.text
    assert on_attributes(parse(preview.text)) == []


def test_marker_namespaces_never_meet(env: AppEnv) -> None:
    """Decision 4 and 11: receipt.js reads only the receipt marker, wishlist.js the reorder one."""
    wishlist = strip_js_comments(_static(env, "wishlist.js"))
    assert REORDER_HEADER in wishlist, "wishlist.js does not read the reorder marker"
    assert REFUSAL_HEADER not in wishlist
    receipt = strip_js_comments(_static(env, "receipt.js"))
    assert REFUSAL_HEADER in receipt, "receipt.js does not read the receipt marker"
    assert REORDER_HEADER not in receipt and "stale_order" not in receipt


def test_closed_reason_set_mirrors_the_refusal_table(env: AppEnv) -> None:
    """Decision 4: receipt.js lists exactly the ``_REFUSALS`` reasons plus ``busy``."""
    table = new_symbol("wishenka.web.routes.receipts", "_REFUSALS")
    reasons = {str(row[2]) for row in table}
    source = strip_js_comments(_static(env, "receipt.js"))
    for reason in sorted(reasons | {"busy"}):
        assert re.search(rf"['\"]{reason}['\"]", source), f"reason {reason!r} missing in receipt.js"
    extra = sorted(set(REASON_LIKE.findall(source)) - reasons)
    assert extra == [], f"receipt.js carries reason-like values outside the table: {extra}"


def test_new_handlers_guard_a_missing_xhr(env: AppEnv) -> None:
    """Design: the new beforeSwap and responseError handlers check ``getResponseHeader`` first."""
    wishlist = _handler_source(strip_js_comments(_static(env, "wishlist.js")), "htmx:responseError")
    assert GUARD.search(wishlist), "wishlist.js responseError handler lacks the guard"
    receipt = _handler_source(strip_js_comments(_static(env, "receipt.js")), "htmx:beforeSwap")
    assert GUARD.search(receipt), "receipt.js beforeSwap handler lacks the getResponseHeader guard"


def test_receipt_script_hygiene_and_wishlist_additions(env: AppEnv) -> None:
    """N-2: no ``innerHTML``, ``eval`` or console output; the wrapper and stale handler exist."""
    wishlist = strip_js_comments(_static(env, "wishlist.js"))
    assert "window.swapWishCard" in wishlist, "wishlist.js has no swapWishCard wrapper"
    assert "data-i18n-item-unavailable" in wishlist
    assert "data-i18n-list-changed" in wishlist
    receipt = strip_js_comments(_static(env, "receipt.js"))
    for forbidden in ("innerHTML", "eval(", "console."):
        assert forbidden not in receipt, f"receipt.js contains {forbidden!r}"
