"""Red tests for the receipt script and the page wiring (WISHENKA-24, plan T-6).

No browser, no network: ``TestClient`` requests plus text inspection of the static scripts.
Behaviour of the scripts is proven in ``test_receipt_modal_browser.py``; these checks pin what a
browser test cannot see: the file is served and loaded after ``wishlist.js``, the inline script of
``base.html`` is untouched (N-2), the two refusal marker namespaces never meet, the closed reason
set mirrors ``receipts._REFUSALS`` and the new handlers guard a missing ``xhr``.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator
from pathlib import Path

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

pytestmark = pytest.mark.timeout(30)

# WISHENKA-123 updates the inline script to guard CSRF initialization while preserving the
# receipt separation invariant.
# WISHENKA-61 updates the inline script to attach and reuse Idempotency-Key on reservations.
# Pin the reviewed version until the script is externalized.
INLINE_SCRIPT_SHA256 = "e83466996e59b5b79ab32a736e1ef7abf8cb271230d4c1aaa0a4afe17e5d3d8f"
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


def test_inline_script_is_unchanged_and_free_of_receipt_code(env: AppEnv) -> None:
    """Guard: green today. N-2: the inline script of ``base.html`` is byte-for-byte unchanged."""
    soup, _wishlist_id, _item = _owner_page(env)
    inline = [tag.get_text() for tag in soup.find_all("script") if not tag.get("src")]
    assert len(inline) == 1, f"expected exactly one inline script, found {len(inline)}"
    assert "receipt" not in inline[0].lower()
    digest = hashlib.sha256(inline[0].encode("utf-8")).hexdigest()
    assert digest == INLINE_SCRIPT_SHA256, "the inline script of base.html changed"


def test_single_ajax_call_in_each_script(env: AppEnv) -> None:
    """Decision 5: ``receipt.js`` has exactly one ``htmx.ajax(`` call; ``wishlist.js`` keeps one."""
    wishlist = strip_js_comments(_static(env, "wishlist.js"))
    assert wishlist.count("htmx.ajax(") == 1, "wishlist.js must keep exactly one htmx.ajax call"
    receipt = strip_js_comments(_static(env, "receipt.js"))
    assert receipt.count("htmx.ajax(") == 1


def test_pages_and_partials_carry_no_inline_handlers(env: AppEnv) -> None:
    """N-2: the owner page (with receipts) and the receipt dialog have no ``on*`` attribute."""
    client, sessions, _app = env
    soup, wishlist_id, item_id = _owner_page(env)
    assert on_attributes(soup) == []
    dialog = client.get(modal_url(wishlist_id, item_id), headers=hx(sessions))
    assert dialog.status_code == 200, "receipt dialog route missing"
    assert on_attributes(parse(dialog.text)) == []


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
    assert "Желание больше недоступно. Обновите страницу." in wishlist
    assert "Список изменился. Обновляем." in wishlist
    receipt = strip_js_comments(_static(env, "receipt.js"))
    for forbidden in ("innerHTML", "eval(", "console."):
        assert forbidden not in receipt, f"receipt.js contains {forbidden!r}"
