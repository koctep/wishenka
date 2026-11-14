"""Browser tests for mouse (native HTML5 drag-and-drop) reordering (WISHENKA-110).

Covers Definition of Done items 7-11 against the real ``wishlist.js``. The htmx stub records every
``htmx.ajax`` call and forwards it to the real server, so the request content and the saved
order are both checked.

STEP 3: structurally red (``NotImplementedError`` from the stubbed driver and fixtures) until
Step 4 implements them.
"""

from collections.abc import Callable

import pytest

from tests.browser_cdp import CdpPage
from tests.browser_helpers import (
    Seeded,
    assert_clean_console,
    assert_no_reorder_sent,
    assert_order,
    card,
    js_str,
    reorder_ajax_calls,
    reorder_requests,
    request_item_ids,
    settle,
)

pytestmark = [pytest.mark.timeout(45), pytest.mark.browser]

TITLES = ["Alpha", "Beta", "Gamma"]
UPPER_HALF = 0.25
LOWER_HALF = 0.75

SeedFactory = Callable[..., Seeded]
PageFactory = Callable[..., CdpPage]


def _expected(ids: list[str], permutation: list[int]) -> list[str]:
    return [ids[index] for index in permutation]


# --- 7: before or after the target midpoint -------------------------------------------------


@pytest.mark.parametrize(
    ("source", "target", "fraction", "permutation"),
    [
        (0, 2, UPPER_HALF, [1, 0, 2]),
        (0, 2, LOWER_HALF, [1, 2, 0]),
        (2, 0, UPPER_HALF, [2, 0, 1]),
        (2, 0, LOWER_HALF, [0, 2, 1]),
    ],
    ids=[
        "first-onto-third-top",
        "first-onto-third-bottom",
        "last-onto-first-top",
        "last-onto-first-bottom",
    ],
)
def test_mouse_drop_before_or_after_target_midpoint(
    source: int,
    target: int,
    fraction: float,
    permutation: list[int],
    seed_wishlist: SeedFactory,
    wishlist_page: PageFactory,
) -> None:
    """Dropping on the upper half inserts before the target, on the lower half after it."""
    seeded = seed_wishlist(TITLES)
    page = wishlist_page(seeded)
    ids = seeded.item_ids

    page.mouse_drag(card(ids[source]), card(ids[target]), y_fraction=fraction)
    settle(page)

    assert_order(page, _expected(ids, permutation), "DOM order after mouse drop")
    assert_clean_console(page)


# --- 8: exactly one request with the full new order -----------------------------------------


def test_mouse_drop_sends_exactly_one_request_with_full_order(
    seed_wishlist: SeedFactory, wishlist_page: PageFactory
) -> None:
    """One htmx.ajax call and one POST carry all ids in the new DOM order; the order is saved."""
    seeded = seed_wishlist(TITLES)
    page = wishlist_page(seeded)
    ids = seeded.item_ids
    expected = _expected(ids, [1, 2, 0])

    page.mouse_drag(card(ids[0]), card(ids[2]), y_fraction=LOWER_HALF)
    settle(page)

    calls = reorder_ajax_calls(page)
    assert len(calls) == 1, f"htmx.ajax reorder calls: {calls}\n{page.snapshot()}"
    call = calls[0]
    assert call["verb"] == "POST", call
    assert call["url"] == f"/web/wishlists/{seeded.wishlist_id}/items/reorder", call
    values = call["values"]
    assert isinstance(values, dict)
    assert values["item_ids"] == expected, f"ajax item_ids {values['item_ids']} != {expected}"

    posts = reorder_requests(page)
    assert len(posts) == 1, f"reorder POSTs: {posts}\n{page.snapshot()}"
    assert posts[0].path == f"/web/wishlists/{seeded.wishlist_id}/items/reorder", posts[0]
    assert request_item_ids(posts[0]) == expected, (
        f"body item_ids {request_item_ids(posts[0])} != {expected}\n{page.snapshot()}"
    )
    assert_order(page, expected, "DOM order after the swap")

    page.navigate(str(page.evaluate("location.href")))
    assert_order(page, expected, "order saved on the server (after reload)")


def test_reorder_uses_data_wishlist_id_not_location(
    seed_wishlist: SeedFactory, wishlist_page: PageFactory
) -> None:
    """The request address comes from #items-list[data-wishlist-id] at drop time."""
    seeded = seed_wishlist(TITLES)
    page = wishlist_page(seeded)
    ids = seeded.item_ids
    other = seeded.wishlist_id + 1000
    page.evaluate(
        f"document.getElementById('items-list').setAttribute('data-wishlist-id', '{other}')"
    )

    page.mouse_drag(card(ids[0]), card(ids[1]), y_fraction=LOWER_HALF)
    settle(page)

    expected_path = f"/web/wishlists/{other}/items/reorder"
    calls = reorder_ajax_calls(page)
    assert [c["url"] for c in calls] == [expected_path], f"{calls}\n{page.snapshot()}"
    assert [r.path for r in reorder_requests(page)] == [expected_path], page.snapshot()


# --- 9: negative cases ------------------------------------------------------------------------


@pytest.mark.parametrize("where", ["self", "outside"])
def test_drop_on_self_or_outside_list_is_a_no_op(
    where: str, seed_wishlist: SeedFactory, wishlist_page: PageFactory
) -> None:
    """Dropping on the dragged card or outside the list sends nothing and warns about nothing."""
    seeded = seed_wishlist(TITLES)
    page = wishlist_page(seeded)
    ids = seeded.item_ids

    if where == "self":
        page.mouse_drag(card(ids[0]), card(ids[0]), y_fraction=0.5)
    else:
        page.drop_outside(card(ids[0]), (1.0, 1.0))

    assert_no_reorder_sent(page)
    assert_order(page, ids, "DOM order after a no-op drop")
    assert page.console.warnings() == [], f"warnings: {page.console.warnings()}"
    assert_clean_console(page)
    # The page still works: a real gesture afterwards reorders.
    page.mouse_drag(card(ids[0]), card(ids[2]), y_fraction=LOWER_HALF)
    settle(page)
    assert_order(page, _expected(ids, [1, 2, 0]), "DOM order after a real gesture")


SKIP_CASES = {
    "id-missing": (
        "document.getElementById('items-list').removeAttribute('data-wishlist-id')",
        "is not numeric",
    ),
    "id-not-numeric": (
        "document.getElementById('items-list').setAttribute('data-wishlist-id', 'abc')",
        "is not numeric",
    ),
    "htmx-missing": ("delete window.htmx", "is not loaded"),
}


@pytest.mark.parametrize("case", list(SKIP_CASES))
def test_reorder_skipped_with_exactly_one_warning(
    case: str, seed_wishlist: SeedFactory, wishlist_page: PageFactory
) -> None:
    """Without a numeric list id or window.htmx: no request, card stays, exactly one warning."""
    setup, cause = SKIP_CASES[case]
    seeded = seed_wishlist(TITLES)
    page = wishlist_page(seeded)
    ids = seeded.item_ids
    page.evaluate(setup)

    page.mouse_drag(card(ids[0]), card(ids[2]), y_fraction=LOWER_HALF)

    assert_no_reorder_sent(page)
    assert_order(page, ids, "DOM order after a skipped reorder")
    warnings = page.console.warnings()
    assert len(warnings) == 1, f"expected exactly one warning, got {warnings}\n{page.snapshot()}"
    assert "reorder skipped" in warnings[0].text, warnings[0].text
    assert cause in warnings[0].text, warnings[0].text
    errors = [e for e in page.console if e.type in ("error", "exception")]
    assert errors == [], f"console errors: {errors}"


# --- 10: repeated gestures, nothing sticks ----------------------------------------------------


def test_repeated_reorder_without_reload(
    seed_wishlist: SeedFactory, wishlist_page: PageFactory
) -> None:
    """Two gestures in a row each send one request; no-op drops do not leave a stuck state."""
    seeded = seed_wishlist(TITLES)
    page = wishlist_page(seeded)
    first, second, third = seeded.item_ids

    page.mouse_drag(card(first), card(third), y_fraction=LOWER_HALF)
    settle(page)
    assert_order(page, [second, third, first], "after gesture 1")
    assert len(reorder_requests(page)) == 1

    page.mouse_drag(card(first), card(second), y_fraction=UPPER_HALF)
    settle(page)
    assert_order(page, [first, second, third], "after gesture 2")
    assert len(reorder_requests(page)) == 2
    assert_clean_console(page)

    # Drop on itself, then drag released outside (only dragend fires): neither may stick.
    page.mouse_drag(card(second), card(second), y_fraction=0.5)
    page.drop_outside(card(second), (1.0, 1.0))
    assert len(reorder_requests(page)) == 2, f"requests: {reorder_requests(page)}"
    page.mouse_drag(card(first), card(third), y_fraction=LOWER_HALF)
    settle(page)
    assert_order(page, [second, third, first], "after gesture 3 following no-op drops")
    assert len(reorder_requests(page)) == 3
    assert_clean_console(page)


# --- 11: share page cannot reorder ------------------------------------------------------------


def test_share_page_has_no_handle_and_cannot_reorder(
    seed_wishlist: SeedFactory, share_page: PageFactory
) -> None:
    """On /share/<token> there is no handle, no draggable card, and drag events do nothing."""
    seeded = seed_wishlist(TITLES)
    page = share_page(seeded)
    ids = seeded.item_ids

    assert page.evaluate("document.querySelectorAll('.item-drag-handle').length") == 0
    assert page.evaluate("document.querySelectorAll('[draggable=\"true\"]').length") == 0
    page.evaluate(
        "(() => {"
        f" const src = document.querySelector({js_str(card(ids[0]))});"
        f" const dst = document.querySelector({js_str(card(ids[2]))});"
        " const dt = new DataTransfer();"
        " src.dispatchEvent(new DragEvent('dragstart', {bubbles: true, dataTransfer: dt}));"
        " const r = dst.getBoundingClientRect();"
        " dst.dispatchEvent(new DragEvent('dragover', {bubbles: true, cancelable: true,"
        " dataTransfer: dt, clientY: r.top + r.height * 0.75}));"
        " dst.dispatchEvent(new DragEvent('drop', {bubbles: true, cancelable: true,"
        " dataTransfer: dt, clientY: r.top + r.height * 0.75}));"
        " src.dispatchEvent(new DragEvent('dragend', {bubbles: true}));"
        " })()"
    )

    assert_no_reorder_sent(page)
    assert_order(page, ids, "DOM order on the share page")
    assert_clean_console(page)
