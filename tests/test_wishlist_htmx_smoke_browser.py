"""Offline browser smoke test with real vendored htmx, cookie session, and CSRF (WISHENKA-145).

Exercises the real declarative ``hx-post`` move button, real ``htmx.org@1.9.12`` + ``json-enc``,
``session_id`` cookie authentication, ``GET /api/auth/csrf``, ``htmx:configRequest`` attaching
``X-CSRF-Token``, server-side ``BrowserSecurityMiddleware`` origin + HMAC validation, DOM swap of
``#items-list``, and persistence across reload.
"""

import json
from collections.abc import Callable

import pytest

from tests.browser_cdp import CdpPage
from tests.browser_helpers import Seeded, assert_clean_console, js_str, title

pytestmark = [pytest.mark.timeout(45), pytest.mark.browser]

TITLES = ["Alpha", "Beta", "Gamma"]

SeedFactory = Callable[..., Seeded]
PageFactory = Callable[..., CdpPage]


def test_real_htmx_move_button_with_cookie_and_csrf(
    seed_wishlist: SeedFactory, wishlist_page: PageFactory
) -> None:
    """Clicking ``.btn-move-down`` with real htmx, cookie session, and CSRF reorders items."""
    seeded = seed_wishlist(TITLES)
    first, second, third = seeded.item_ids

    page = wishlist_page(seeded, auth_mode="cookie", use_real_htmx=True)

    assert page.external_requests == [], f"external requests: {page.external_requests}"
    assert page.evaluate("window.htmx && window.htmx.version") == "1.9.12"
    assert page.order() == [first, second, third]

    page.wait_for("CSRF token from /api/auth/csrf", "Boolean(window.csrfToken)")
    csrf_requests = [r for r in page.requests if r.method == "GET" and r.path == "/api/auth/csrf"]
    assert len(csrf_requests) == 1, f"expected 1 CSRF request, got {csrf_requests}"
    assert csrf_requests[0].status == 200

    # Expand the first card so .btn-move-down inside .item-card-details is visible and clickable.
    page.click(title(first))
    move_selector = f"#item-card-{first} .btn-move-down"
    page.wait_for(
        "move-down button visible",
        f"(() => {{ const el = document.querySelector({js_str(move_selector)});"
        " return Boolean(el && el.getBoundingClientRect().height > 0); })()",
    )
    page.click(move_selector)

    expected_order = [second, first, third]
    expected_json = js_str(json.dumps(expected_order, separators=(",", ":")))
    page.wait_for(
        "DOM order updated by htmx swap",
        "JSON.stringify(Array.from(document.querySelectorAll('.item-card')).map("
        f"el => el.id.replace('item-card-', ''))) === {expected_json}",
    )
    assert page.order() == expected_order

    move_path = f"/web/wishlists/{seeded.wishlist_id}/items/{first}/move"
    move_requests = [r for r in page.requests if r.method == "POST" and r.path == move_path]
    assert len(move_requests) == 1, f"expected 1 move POST, got {move_requests}"
    assert move_requests[0].status == 200

    # Reload the page and confirm the reordered list persisted in the database.
    current_url = str(page.evaluate("window.location.href"))
    page.navigate(current_url)
    assert page.order() == expected_order

    assert page.external_requests == [], f"external requests: {page.external_requests}"
    assert_clean_console(page)
