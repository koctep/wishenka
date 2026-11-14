"""Browser tests for wish card expansion on the wishlist and share pages (WISHENKA-110).

Covers Definition of Done items 1-6 and 22 against the real ``wishlist.js``, the real markup and
CSS, in headless Chromium. External scripts (htmx, json-enc, Telegram SDK) are replaced by offline
stubs on the network boundary; the htmx stub does NOT process ``hx-*`` attributes.

STEP 3: these tests are structurally red until the CDP driver (``tests/browser_cdp.py``) and the
fixtures in ``tests/conftest.py`` are implemented in Step 4; they fail with ``NotImplementedError``.
"""

from collections.abc import Callable

import pytest

from tests.browser_cdp import CdpPage
from tests.browser_helpers import (
    Seeded,
    assert_cards,
    assert_clean_console,
    focus,
    js_str,
    settle,
    summary,
    title,
)

pytestmark = [pytest.mark.timeout(45), pytest.mark.browser]

TITLES = ["Alpha", "Beta", "Gamma"]

SeedFactory = Callable[..., Seeded]
PageFactory = Callable[..., CdpPage]


def _details(item_id: str) -> str:
    return f"#item-card-{item_id} .item-card-details"


# --- 22: offline page with real assets ------------------------------------------------------


@pytest.mark.parametrize("kind", ["owner", "share"])
def test_page_loads_offline_with_real_assets(
    kind: str, seed_wishlist: SeedFactory, wishlist_page: PageFactory, share_page: PageFactory
) -> None:
    """No external network; the real wishlist.js and CSS come from the app; htmx is the stub."""
    seeded = seed_wishlist(TITLES)
    page = wishlist_page(seeded) if kind == "owner" else share_page(seeded)

    assert page.external_requests == [], f"external requests: {page.external_requests}"
    served = {r.path: r.status for r in page.requests}
    assert served.get("/static/wishlist.js") == 200, f"requests: {served}"
    assert served.get("/static/miniapp.css") == 200, f"requests: {served}"
    assert page.evaluate("window.htmx && window.htmx.version") == "stub"
    assert page.evaluate("document.querySelectorAll('.item-card-summary').length") == len(TITLES)
    assert_clean_console(page)


# --- 1: click toggles both ways -----------------------------------------------------------------


def test_click_toggles_card_both_ways(
    seed_wishlist: SeedFactory, wishlist_page: PageFactory
) -> None:
    """A click expands (aria-expanded=true, hidden removed) and a second click collapses."""
    seeded = seed_wishlist(TITLES)
    page = wishlist_page(seeded)
    first = seeded.item_ids[0]
    assert_cards(page, seeded.item_ids, expanded=set())

    page.click(title(first))
    assert_cards(page, seeded.item_ids, expanded={first})
    assert page.evaluate(f"document.querySelector({js_str(_details(first))}).hidden") is False

    page.click(title(first))
    assert_cards(page, seeded.item_ids, expanded=set())
    assert page.evaluate(f"document.querySelector({js_str(_details(first))}).hidden") is True
    assert_clean_console(page)


# --- 2: keyboard ------------------------------------------------------------------------------


@pytest.mark.parametrize("key", ["Enter", "Space"])
def test_enter_and_space_toggle(
    key: str, seed_wishlist: SeedFactory, wishlist_page: PageFactory
) -> None:
    """Enter and Space on the focused summary toggle the card like a click."""
    seeded = seed_wishlist(TITLES)
    page = wishlist_page(seeded)
    first = seeded.item_ids[0]

    focus(page, summary(first))
    page.press_key(key)
    assert_cards(page, seeded.item_ids, expanded={first})
    page.press_key(key)
    assert_cards(page, seeded.item_ids, expanded=set())
    assert_clean_console(page)


def test_space_default_prevented_and_page_does_not_scroll(
    seed_wishlist: SeedFactory, wishlist_page: PageFactory
) -> None:
    """Space is default-prevented by the script, so a tall page does not scroll."""
    seeded = seed_wishlist(TITLES)
    page = wishlist_page(seeded)
    first = seeded.item_ids[0]
    page.evaluate(
        "(() => { const spacer = document.createElement('div'); spacer.style.height = '4000px';"
        " document.body.appendChild(spacer); window.scrollTo(0, 0);"
        " window.__keydowns = [];"
        " window.addEventListener('keydown', (e) =>"
        " window.__keydowns.push({key: e.key, prevented: e.defaultPrevented})); })()"
    )

    focus(page, summary(first))
    page.press_key("Space")

    keydowns = page.evaluate("window.__keydowns")
    assert keydowns == [{"key": " ", "prevented": True}], f"keydowns: {keydowns}"
    assert page.evaluate("window.scrollY") == 0
    assert_cards(page, seeded.item_ids, expanded={first})


@pytest.mark.parametrize("key", ["a", "Escape", "ArrowDown"])
def test_other_keys_do_not_toggle(
    key: str, seed_wishlist: SeedFactory, wishlist_page: PageFactory
) -> None:
    """Keys other than Enter and Space leave the card as it was."""
    seeded = seed_wishlist(TITLES)
    page = wishlist_page(seeded)

    focus(page, summary(seeded.item_ids[0]))
    page.press_key(key)

    assert_cards(page, seeded.item_ids, expanded=set())
    assert_clean_console(page)


# --- 3: consistency across several cards ------------------------------------------------------


def test_toggle_one_card_leaves_others_untouched(
    seed_wishlist: SeedFactory, wishlist_page: PageFactory
) -> None:
    """After every action aria-expanded and hidden agree on all three cards; others stay put."""
    seeded = seed_wishlist(TITLES)
    page = wishlist_page(seeded)
    a, b, c = seeded.item_ids

    page.click(title(a))
    assert_cards(page, seeded.item_ids, expanded={a})
    page.click(title(b))
    assert_cards(page, seeded.item_ids, expanded={a, b})
    page.click(title(a))
    assert_cards(page, seeded.item_ids, expanded={b})
    focus(page, summary(c))
    page.press_key("Enter")
    assert_cards(page, seeded.item_ids, expanded={b, c})
    page.click(title(b))
    page.click(title(c))
    assert_cards(page, seeded.item_ids, expanded=set())
    assert_clean_console(page)


# --- 4: nested interactive controls do not toggle ------------------------------------------------

# NOTE (criterion 4): the requirements mention labels, but the real TOGGLE_EXCLUSION in wishlist.js
# is `a, button, input, select, textarea, [data-no-toggle]` and has no `label`. These cases assert
# the set that exists in the code; no label case is asserted. The discrepancy is reported in the
# step summary (requirement wording vs. code), not encoded as an expectation here.

_PROBE_STYLE = "display:inline-block;width:60px;height:24px"
_INSERT_PROBE = (
    "(() => {{ const holder = document.querySelector({holder});"
    " holder.insertAdjacentHTML('beforeend', {html}); }})()"
)


def _probe(html: str) -> str:
    return _INSERT_PROBE.format(
        holder=js_str(".item-card-summary .item-summary-text"), html=js_str(html)
    )


# case id -> (page kind, selector to click, setup JS or None)
NESTED_CASES: dict[str, tuple[str, str, str | None]] = {
    "drag-handle": ("owner", ".item-card .item-drag-handle", None),
    "giver-block-text": ("viewer-share", ".item-card .giver-available", None),
    "select": ("viewer-share", ".item-card .item-giver select", None),
    "reserve-button": ("viewer-share", ".item-card .item-giver button[type=submit]", None),
    "link": (
        "owner",
        "#probe",
        _probe(f'<a id="probe" href="#x" style="{_PROBE_STYLE}">probe</a>'),
    ),
    "input": ("owner", "#probe", _probe(f'<input id="probe" style="{_PROBE_STYLE}">')),
    "textarea": (
        "owner",
        "#probe",
        _probe(f'<textarea id="probe" style="{_PROBE_STYLE}"></textarea>'),
    ),
}


@pytest.mark.parametrize("case", list(NESTED_CASES))
def test_nested_controls_do_not_toggle(
    case: str, seed_wishlist: SeedFactory, wishlist_page: PageFactory, share_page: PageFactory
) -> None:
    """Clicking a nested control from the exclusion set never toggles the card."""
    kind, selector, setup = NESTED_CASES[case]
    seeded = seed_wishlist(TITLES, quantities=[3, 1, 1])
    page = wishlist_page(seeded) if kind == "owner" else share_page(seeded, as_user="viewer")
    # A native form submit would navigate away; the button must only be proven not to toggle.
    page.evaluate("document.addEventListener('submit', (e) => e.preventDefault())")
    if setup is not None:
        page.evaluate(setup)
    assert page.evaluate(f"document.querySelectorAll({js_str(selector)}).length") >= 1, (
        f"control for case {case!r} is not on the page\n{page.snapshot()}"
    )

    page.click(selector)

    assert_cards(page, seeded.item_ids, expanded=set())


# --- 5: toggling after an htmx card swap -------------------------------------------------------


def test_toggle_works_after_htmx_swap(
    seed_wishlist: SeedFactory, wishlist_page: PageFactory
) -> None:
    """Delegated handlers keep working on cards that htmx put in place after the first load.

    The offline htmx stub does not process ``hx-*`` attributes, so the swap that the
    "move down" button would trigger is started explicitly through ``window.htmx.ajax``.
    """
    seeded = seed_wishlist(TITLES)
    page = wishlist_page(seeded)
    a, b, c = seeded.item_ids
    page.evaluate(f"window.__oldCard = document.querySelector({js_str('#item-card-' + a)})")

    page.evaluate(
        f"window.htmx.ajax('POST', '/web/wishlists/{seeded.wishlist_id}/items/{a}/move"
        "?direction=down', {target: '#items-list', swap: 'innerHTML'})"
    )
    settle(page)
    page.wait_for("list replaced by htmx", "!document.contains(window.__oldCard)")
    assert page.order() == [b, a, c], f"order after move: {page.order()}\n{page.snapshot()}"

    page.click(title(a))
    assert_cards(page, seeded.item_ids, expanded={a})
    focus(page, summary(b))
    page.press_key("Enter")
    assert_cards(page, seeded.item_ids, expanded={a, b})
    focus(page, summary(c))
    page.press_key("Space")
    assert_cards(page, seeded.item_ids, expanded={a, b, c})
    assert_clean_console(page)


# --- 6: share page ----------------------------------------------------------------------------


@pytest.mark.parametrize("action", ["click", "Enter", "Space"])
def test_share_page_toggles_cards(
    action: str, seed_wishlist: SeedFactory, share_page: PageFactory
) -> None:
    """An anonymous visitor of /share/<token> expands and collapses cards."""
    seeded = seed_wishlist(TITLES)
    page = share_page(seeded)
    first = seeded.item_ids[0]

    def act() -> None:
        if action == "click":
            page.click(title(first))
        else:
            focus(page, summary(first))
            page.press_key(action)

    act()
    assert_cards(page, seeded.item_ids, expanded={first})
    act()
    assert_cards(page, seeded.item_ids, expanded=set())
    assert_clean_console(page)
