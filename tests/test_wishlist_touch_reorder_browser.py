"""Browser tests for touch reordering with Pointer Events (WISHENKA-110, WISHENKA-109 scenarios).

Covers Definition of Done items 12-18 and the computed-style replacements of item 28 against the
real ``wishlist.js`` and the real application CSS (without it the dragged card sits under the
finger and no target is found). Gestures are driven through ``Input.dispatchTouchEvent``.

Out of scope on purpose (item 19, WISHENKA-143): autoscroll, Telegram SDK stub call order and
degradation, ``warnSdk``, real devices.

STEP 3: structurally red (``NotImplementedError`` from the stubbed driver and fixtures) until
Step 4 implements them.
"""

from collections.abc import Callable

import pytest

from tests.browser_cdp import CdpPage
from tests.browser_helpers import (
    Seeded,
    assert_cards,
    assert_clean_console,
    assert_gesture_clean,
    assert_no_reorder_sent,
    assert_order,
    begin_touch_drag,
    card,
    center,
    handle,
    js_str,
    record_pointer_ids,
    reorder_ajax_calls,
    reorder_requests,
    request_item_ids,
    settle,
    title,
    wait_gesture_active,
    wait_suppression_window_over,
)

pytestmark = [pytest.mark.timeout(45), pytest.mark.browser]

TITLES = ["Alpha", "Beta", "Gamma"]
UPPER_HALF = 0.25
LOWER_HALF = 0.75

SeedFactory = Callable[..., Seeded]
PageFactory = Callable[..., CdpPage]


def _touch_page(
    seed_wishlist: SeedFactory,
    wishlist_page: PageFactory,
    *,
    viewport: tuple[int, int] = (412, 800),
) -> tuple[Seeded, CdpPage]:
    seeded = seed_wishlist(TITLES)
    page = wishlist_page(seeded, viewport=viewport)
    page.enable_touch()
    return seeded, page


# --- 12: drag by the handle ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fraction", "expanded", "permutation"),
    [(UPPER_HALF, False, [1, 0, 2]), (LOWER_HALF, False, [1, 2, 0]), (LOWER_HALF, True, [1, 2, 0])],
    ids=["top-half", "bottom-half", "expanded-card"],
)
def test_touch_drag_handle_reorders(
    fraction: float,
    expanded: bool,
    permutation: list[int],
    seed_wishlist: SeedFactory,
    wishlist_page: PageFactory,
) -> None:
    """Dragging the handle onto a card shows feedback, then reorders with one correct request."""
    viewport = (412, 1000) if expanded else (412, 800)
    seeded, page = _touch_page(seed_wishlist, wishlist_page, viewport=viewport)
    ids = seeded.item_ids
    if expanded:
        page.click(title(ids[0]))
        assert_cards(page, ids, expanded={ids[0]})
    expected = [ids[index] for index in permutation]

    begin_touch_drag(page, ids[0], ids[2], fraction)
    wait_gesture_active(page, ids[0])
    indicator = "drop-after" if fraction > 0.5 else "drop-before"
    page.wait_for(
        f"target card has {indicator}",
        f"document.querySelector({js_str(card(ids[2]))}).classList.contains('{indicator}')",
    )
    page.touch_end()
    settle(page)

    assert_order(page, expected, "DOM order after touch drop")
    calls = reorder_ajax_calls(page)
    assert len(calls) == 1, f"htmx.ajax reorder calls: {calls}\n{page.snapshot()}"
    values = calls[0]["values"]
    assert isinstance(values, dict)
    assert values["item_ids"] == expected, f"ajax item_ids {values['item_ids']} != {expected}"
    posts = reorder_requests(page)
    assert len(posts) == 1, f"reorder POSTs: {posts}\n{page.snapshot()}"
    assert request_item_ids(posts[0]) == expected, f"body {posts[0].post_data}\n{page.snapshot()}"
    assert_gesture_clean(page)
    assert_clean_console(page)


def test_expanded_card_stays_expanded_after_cancelled_touch_drag(
    seed_wishlist: SeedFactory, wishlist_page: PageFactory
) -> None:
    """An expanded card dragged and cancelled stays expanded; nothing is sent."""
    seeded, page = _touch_page(seed_wishlist, wishlist_page, viewport=(412, 1000))
    ids = seeded.item_ids
    page.click(title(ids[0]))
    assert_cards(page, ids, expanded={ids[0]})

    begin_touch_drag(page, ids[0], ids[2], LOWER_HALF)
    wait_gesture_active(page, ids[0])
    page.touch_cancel()
    page.touch_end()

    assert_cards(page, ids, expanded={ids[0]})
    assert_no_reorder_sent(page)
    assert_order(page, ids, "DOM order after cancel")
    assert_gesture_clean(page)
    assert_clean_console(page)


def test_expanded_card_drag_preserves_details_and_list_positions(
    seed_wishlist: SeedFactory, wishlist_page: PageFactory
) -> None:
    """Dragging an expanded card keeps details visible in dimmed state without shifting siblings."""
    seeded, page = _touch_page(seed_wishlist, wishlist_page, viewport=(412, 1000))
    ids = seeded.item_ids
    page.click(title(ids[0]))
    assert_cards(page, ids, expanded={ids[0]})

    def _measure_layout() -> tuple[str, dict[str, float]]:
        raw = page.evaluate(
            f"(() => {{"
            f" const c0 = document.querySelector({js_str(card(ids[0]))});"
            f" const d0 = c0.querySelector('.item-card-details');"
            f" const c1 = document.querySelector({js_str(card(ids[1]))});"
            f" const c2 = document.querySelector({js_str(card(ids[2]))});"
            f" return {{"
            f"  card0Height: c0.getBoundingClientRect().height,"
            f"  detailsDisplay: getComputedStyle(d0).display,"
            f"  detailsHeight: d0.getBoundingClientRect().height,"
            f"  card0Opacity: parseFloat(getComputedStyle(c0).opacity),"
            f"  card1Top: c1.getBoundingClientRect().top,"
            f"  card2Top: c2.getBoundingClientRect().top"
            f" }};"
            f"}})()"
        )
        assert isinstance(raw, dict)
        display = raw["detailsDisplay"]
        assert isinstance(display, str)
        nums: dict[str, float] = {}
        for key in ("card0Height", "detailsHeight", "card0Opacity", "card1Top", "card2Top"):
            val = raw[key]
            assert isinstance(val, (int, float)), f"{key}={val!r}"
            nums[key] = float(val)
        return display, nums

    before_display, before = _measure_layout()
    assert before_display != "none", before
    assert before["detailsHeight"] > 0, before

    begin_touch_drag(page, ids[0], ids[2], LOWER_HALF)
    wait_gesture_active(page, ids[0])

    during_display, during = _measure_layout()
    assert during_display != "none", f"details hidden during drag: {during_display}, {during}"
    assert during["detailsHeight"] > 0, f"details collapsed during drag: {during}"
    assert abs(during["card0Height"] - before["card0Height"]) <= 1.0, (
        "dragged card height changed: "
        f"before={before['card0Height']}, during={during['card0Height']}"
    )
    assert abs(during["card1Top"] - before["card1Top"]) <= 1.0, (
        f"card[1] shifted vertically: before={before['card1Top']}, during={during['card1Top']}"
    )
    assert abs(during["card2Top"] - before["card2Top"]) <= 1.0, (
        f"card[2] shifted vertically: before={before['card2Top']}, during={during['card2Top']}"
    )
    assert during["card0Opacity"] < 1.0, f"dragged card not dimmed: {during}"

    page.touch_cancel()
    page.touch_end()

    _, after = _measure_layout()
    assert abs(after["card1Top"] - before["card1Top"]) <= 1.0, (
        f"card[1] shifted after cancel: before={before['card1Top']}, after={after['card1Top']}"
    )
    assert abs(after["card2Top"] - before["card2Top"]) <= 1.0, (
        f"card[2] shifted after cancel: before={before['card2Top']}, after={after['card2Top']}"
    )
    assert_cards(page, ids, expanded={ids[0]})
    assert_no_reorder_sent(page)
    assert_order(page, ids, "DOM order after cancel")
    assert_gesture_clean(page)
    assert_clean_console(page)


# --- 13: taps ---------------------------------------------------------------------------------


def test_tap_on_summary_toggles_tap_on_handle_does_nothing(
    seed_wishlist: SeedFactory, wishlist_page: PageFactory
) -> None:
    """A tap on the summary toggles the card; a tap on the handle does nothing and sends nothing."""
    seeded, page = _touch_page(seed_wishlist, wishlist_page)
    ids = seeded.item_ids

    page.touch_tap(title(ids[0]))
    assert_cards(page, ids, expanded={ids[0]})
    page.touch_tap(title(ids[0]))
    assert_cards(page, ids, expanded=set())

    page.touch_tap(handle(ids[1]))
    assert_cards(page, ids, expanded=set())
    assert_no_reorder_sent(page)
    assert_order(page, ids, "DOM order after a handle tap")
    assert_gesture_clean(page)
    assert_clean_console(page)


# --- 14: every cancel path ---------------------------------------------------------------------

CANCEL_PATHS = [
    "pointercancel",
    "lostpointercapture",
    "escape",
    "blur",
    "visibilitychange",
    "htmx-beforeSwap",
]


@pytest.mark.parametrize("path", CANCEL_PATHS)
def test_touch_cancel_paths_send_nothing(
    path: str, seed_wishlist: SeedFactory, wishlist_page: PageFactory
) -> None:
    """Each cancel path ends the gesture: no request, original order, no leftover feedback."""
    seeded, page = _touch_page(seed_wishlist, wishlist_page)
    ids = seeded.item_ids
    record_pointer_ids(page)
    expected = ids

    begin_touch_drag(page, ids[0], ids[2], LOWER_HALF)
    wait_gesture_active(page, ids[0])

    if path == "pointercancel":
        page.touch_cancel()
    elif path == "lostpointercapture":
        page.evaluate(
            f"document.querySelector({js_str(handle(ids[0]))})"
            ".releasePointerCapture(window.__lastPointerId)"
        )
        # lostpointercapture may be dispatched asynchronously: wait (bounded) for the cleanup.
        page.wait_for(
            "gesture cleaned after capture loss",
            "document.querySelectorAll('.is-touch-dragging').length === 0",
        )
    elif path == "escape":
        page.press_key("Escape")
    elif path == "blur":
        page.dispatch_window_event("blur")
    elif path == "visibilitychange":
        page.dispatch_window_event("visibilitychange")
    else:
        # The offline htmx stub fires htmx:beforeSwap with detail.target before replacing the
        # list, as htmx does. The move request is real, so the DOM follows the server's order.
        # Step 4: the stub must define ``window.htmx`` as a configurable/deletable property
        # (``window.htmx = ...``, not ``var``), so the "htmx missing" skip case can delete it.
        page.evaluate(
            f"window.htmx.ajax('POST', '/web/wishlists/{seeded.wishlist_id}/items/{ids[0]}/move"
            "?direction=down', {target: '#items-list', swap: 'innerHTML'})"
        )
        settle(page)
        expected = [ids[1], ids[0], ids[2]]

    assert_gesture_clean(page)
    page.touch_end()

    assert_no_reorder_sent(page)
    assert_order(page, expected, f"DOM order after cancel by {path}")
    assert_gesture_clean(page)
    assert_clean_console(page)


# --- 15: second finger ------------------------------------------------------------------------


def test_second_finger_does_not_start_second_gesture(
    seed_wishlist: SeedFactory, wishlist_page: PageFactory
) -> None:
    """A second finger during a gesture cancels it; no second gesture, no request."""
    seeded, page = _touch_page(seed_wishlist, wishlist_page)
    ids = seeded.item_ids

    first = begin_touch_drag(page, ids[0], ids[2], LOWER_HALF)
    wait_gesture_active(page, ids[0])
    second_x, second_y = center(page, handle(ids[1]))
    second = (2, second_x, second_y)
    page.touch_start([first, second])
    page.touch_move([first, (2, second_x, second_y + 20)])
    page.touch_end()

    assert_no_reorder_sent(page)
    assert_order(page, ids, "DOM order after a second finger")
    assert_gesture_clean(page)
    assert_clean_console(page)


# --- 16: Escape ---------------------------------------------------------------------------------


@pytest.mark.parametrize("phase", ["armed", "active"])
def test_escape_cancels_armed_and_active_gesture(
    phase: str, seed_wishlist: SeedFactory, wishlist_page: PageFactory
) -> None:
    """Escape before and after the movement threshold cancels without saving."""
    seeded, page = _touch_page(seed_wishlist, wishlist_page)
    ids = seeded.item_ids

    if phase == "armed":
        x, y = center(page, handle(ids[0]))
        page.touch_start([(1, x, y)])
        page.touch_move([(1, x, y + 1)])  # below the 4 px threshold: still armed
    else:
        begin_touch_drag(page, ids[0], ids[2], LOWER_HALF)
        wait_gesture_active(page, ids[0])

    page.press_key("Escape")
    assert_gesture_clean(page)
    page.touch_end()

    assert_no_reorder_sent(page)
    assert_order(page, ids, "DOM order after Escape")
    assert_gesture_clean(page)
    assert_clean_console(page)


# --- 17: vertical swipe outside the handle ----------------------------------------------------


def test_vertical_swipe_outside_handle_scrolls_not_reorders(
    seed_wishlist: SeedFactory, wishlist_page: PageFactory
) -> None:
    """A vertical swipe on the card text scrolls the page and reorders nothing.

    Whether a synthesized touch swipe scrolls in headless Chromium is verified in Step 4. If it
    does not, the ``scrollY`` assertion is weakened there to "no gesture, no request", with the
    reason recorded in the roadmap.
    """
    seeded = seed_wishlist([f"Wish {n}" for n in range(8)])
    page = wishlist_page(seeded, viewport=(412, 500))
    page.enable_touch()
    ids = seeded.item_ids
    assert page.evaluate("document.documentElement.scrollHeight > window.innerHeight"), (
        f"page is not scrollable\n{page.snapshot()}"
    )
    start_x, start_y = center(page, title(ids[0]))
    # The start point must be on the card text, inside the viewport and not under the fixed
    # quick-add bar, otherwise the swipe cannot scroll for reasons unrelated to the code.
    hit = page.evaluate(
        f"(() => {{ const e = document.elementFromPoint({start_x}, {start_y});"
        f" return !!e && e.closest({js_str(title(ids[0]))}) !== null; }})()"
    )
    assert hit, f"swipe start ({start_x}, {start_y}) is not on the visible title\n{page.snapshot()}"

    page.touch_start([(1, start_x, start_y)])
    for step in range(1, 5):
        page.touch_move([(1, start_x, start_y - 40 * step)])
    page.touch_end()

    page.wait_for("page scrolled", "window.scrollY > 0")
    assert_order(page, ids, "DOM order after a vertical swipe")
    assert_no_reorder_sent(page)
    assert_gesture_clean(page)
    assert_clean_console(page)


# --- 18: one request per gesture, click suppression ------------------------------------------


def test_one_request_per_gesture(seed_wishlist: SeedFactory, wishlist_page: PageFactory) -> None:
    """A complete gesture produces exactly one htmx.ajax call and one network POST."""
    seeded, page = _touch_page(seed_wishlist, wishlist_page)
    ids = seeded.item_ids

    page.touch_drag(handle(ids[0]), card(ids[2]), LOWER_HALF)
    settle(page)

    assert len(page.ajax_calls()) == 1, f"ajax calls: {page.ajax_calls()}\n{page.snapshot()}"
    assert len(reorder_requests(page)) == 1, f"reorder POSTs: {reorder_requests(page)}"
    assert_clean_console(page)


@pytest.mark.parametrize("ending", ["drop", "cancel"])
def test_next_tap_after_suppression_window_toggles(
    ending: str, seed_wishlist: SeedFactory, wishlist_page: PageFactory
) -> None:
    """After the click-suppression window a tap on a summary is not swallowed (user-visible)."""
    seeded, page = _touch_page(seed_wishlist, wishlist_page)
    ids = seeded.item_ids

    if ending == "drop":
        page.touch_drag(handle(ids[0]), card(ids[2]), LOWER_HALF)
        settle(page)
    else:
        begin_touch_drag(page, ids[0], ids[2], LOWER_HALF)
        wait_gesture_active(page, ids[0])
        page.touch_cancel()
        page.touch_end()
    wait_suppression_window_over(page)

    page.touch_tap(title(ids[1]))

    assert_cards(page, ids, expanded={ids[1]})
    assert_clean_console(page)


# --- 28/29: computed styles instead of CSS text checks ---------------------------------------


def test_handle_and_feedback_computed_styles(
    seed_wishlist: SeedFactory, wishlist_page: PageFactory
) -> None:
    """Handle and drag feedback are visible in computed styles, not just in CSS source text."""
    seeded, page = _touch_page(seed_wishlist, wishlist_page)
    ids = seeded.item_ids

    style = page.evaluate(
        f"(() => {{ const h = document.querySelector({js_str(handle(ids[0]))});"
        " const s = getComputedStyle(h); const r = h.getBoundingClientRect();"
        " return {touchAction: s.touchAction, userSelect: s.userSelect,"
        " width: r.width, height: r.height}; })()"
    )
    assert style["touchAction"] == "none", style
    assert style["userSelect"] == "none", style
    assert style["width"] >= 44 and style["height"] >= 44, style

    begin_touch_drag(page, ids[0], ids[2], LOWER_HALF)
    wait_gesture_active(page, ids[0])
    page.wait_for(
        "drop-after on target",
        f"document.querySelector({js_str(card(ids[2]))}).classList.contains('drop-after')",
    )
    feedback = page.evaluate(
        f"({{dragOpacity: parseFloat(getComputedStyle(document.querySelector("
        f"{js_str(card(ids[0]))})).opacity),"
        f" targetShadow: getComputedStyle("
        f"document.querySelector({js_str(card(ids[2]))})).boxShadow}})"
    )
    assert feedback["dragOpacity"] < 1, feedback
    assert feedback["targetShadow"] not in ("", "none"), feedback
    page.touch_cancel()
    page.touch_end()
    assert_gesture_clean(page)
