"""Shared helpers for the wishlist browser tests (WISHENKA-110).

Real code (not a stub): pure functions over the ``CdpPage`` interface plus the ``Seeded``
container returned by the ``seed_wishlist`` fixture. They add the diagnostic detail required by
requirement 26 (expected vs actual order, ``aria-expanded`` / ``hidden``, requests, console).
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from urllib.parse import parse_qs

from tests.browser_cdp import CdpPage, RecordedRequest, TouchPoint

# Mirror of CLICK_SUPPRESS_MS in wishenka/web/static/wishlist.js (the constant is private to the
# script's IIFE and cannot be read from the page); the margin covers timer granularity.
CLICK_SUPPRESS_MS = 400
CLICK_SUPPRESS_MARGIN_MS = 50

CONSOLE_PROBLEM_TYPES = ("warning", "error", "exception")

CLEAN_GESTURE_STATE: dict[str, object] = {
    "dragging": 0,
    "drops": 0,
    "body": False,
    "html": False,
    "transforms": [],
}


@dataclass(frozen=True)
class Seeded:
    """A wishlist created through the application REST API for one test.

    Attributes:
        wishlist_id: Numeric wishlist id.
        public_token: Share token for ``/share/<token>``.
        item_ids: Item ids as strings in display order (same type as ``CdpPage.order()``).
        owner_token: Bearer session token of the owner.
        viewer_token: Bearer session token of a second, non-owner user.
    """

    wishlist_id: int
    public_token: str
    item_ids: list[str]
    owner_token: str
    viewer_token: str


def card(item_id: str) -> str:
    """Selector of a card."""
    return f"#item-card-{item_id}"


def summary(item_id: str) -> str:
    """Selector of a card summary."""
    return f"#item-card-{item_id} .item-card-summary"


def title(item_id: str) -> str:
    """Selector of a card title; a safe click target inside the summary (not excluded)."""
    return f"#item-card-{item_id} .item-title"


def handle(item_id: str) -> str:
    """Selector of a card drag handle."""
    return f"#item-card-{item_id} .item-drag-handle"


def js_str(value: str) -> str:
    """Quote ``value`` as a JS string literal (selectors contain only safe characters)."""
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def center(page: CdpPage, selector: str) -> tuple[float, float]:
    """Viewport centre of the first element matching ``selector``."""
    point = page.evaluate(
        f"(() => {{ const r = document.querySelector({js_str(selector)}).getBoundingClientRect();"
        " return [r.left + r.width / 2, r.top + r.height / 2]; })()"
    )
    return float(point[0]), float(point[1])


def point_in(page: CdpPage, selector: str, y_fraction: float) -> tuple[float, float]:
    """Point at the horizontal middle of the element and ``y_fraction`` of its height."""
    rect = page.evaluate(
        f"(() => {{ const r = document.querySelector({js_str(selector)}).getBoundingClientRect();"
        " return [r.left + r.width / 2, r.top, r.height]; })()"
    )
    return float(rect[0]), float(rect[1]) + float(rect[2]) * y_fraction


def focus(page: CdpPage, selector: str) -> None:
    """Move keyboard focus to the element and verify it took focus."""
    focused = page.evaluate(
        f"(() => {{ const e = document.querySelector({js_str(selector)}); e.focus();"
        " return document.activeElement === e; })()"
    )
    assert focused, f"{selector} did not take focus\n{page.snapshot()}"


def settle(page: CdpPage) -> None:
    """Wait (bounded) until every request issued through the htmx stub has completed."""
    page.wait_for("htmx stub requests settled", "(window.__ajaxPending || 0) === 0")


def reorder_requests(page: CdpPage) -> list[RecordedRequest]:
    """Network POSTs to a ``/items/reorder`` resource."""
    return [r for r in page.requests if r.method == "POST" and r.path.endswith("/items/reorder")]


def reorder_ajax_calls(page: CdpPage) -> list[dict[str, object]]:
    """``htmx.ajax`` calls aimed at a ``/items/reorder`` resource."""
    return [
        c
        for c in page.ajax_calls()
        if str(c.get("url", "")).split("?")[0].endswith("/items/reorder")
    ]


def request_item_ids(request: RecordedRequest) -> list[str]:
    """``item_ids`` fields of a form-encoded reorder request body."""
    return parse_qs(request.post_data or "").get("item_ids", [])


def assert_order(page: CdpPage, expected: list[str], why: str = "") -> None:
    """Assert the DOM order and show both orders on failure."""
    actual = page.order()
    assert actual == expected, (
        f"{why or 'DOM order'}: expected {expected}, actual {actual}\n{page.snapshot()}"
    )


def assert_cards(page: CdpPage, item_ids: list[str], expanded: Collection[str]) -> None:
    """Assert ``aria-expanded`` and ``hidden`` of every card and that the two agree."""
    for item_id in item_ids:
        state = page.card_state(item_id)
        want_open = item_id in expanded
        assert state == {
            "expanded": "true" if want_open else "false",
            "hidden": not want_open,
        }, (
            f"card {item_id}: expected {'expanded' if want_open else 'collapsed'}, "
            f"actual {state}\n{page.snapshot()}"
        )


def assert_no_reorder_sent(page: CdpPage) -> None:
    """Assert that nothing was sent to the reorder resource (network and htmx stub)."""
    assert reorder_ajax_calls(page) == [], f"htmx.ajax reorder calls\n{page.snapshot()}"
    assert reorder_requests(page) == [], f"reorder POSTs\n{page.snapshot()}"


def assert_clean_console(page: CdpPage) -> None:
    """Assert there are no console warnings, errors or uncaught exceptions."""
    problems = [e for e in page.console if e.type in CONSOLE_PROBLEM_TYPES]
    assert problems == [], f"unexpected console output: {problems}\n{page.snapshot()}"


def gesture_state(page: CdpPage) -> dict[str, object]:
    """Visual and state leftovers of a touch gesture (all must be cleared after it ends)."""
    state = page.evaluate(
        "({dragging: document.querySelectorAll('.is-touch-dragging').length,"
        " drops: document.querySelectorAll('.drop-before, .drop-after').length,"
        " body: document.body.classList.contains('is-touch-reordering'),"
        " html: document.documentElement.classList.contains('is-touch-reordering'),"
        " transforms: Array.from(document.querySelectorAll('.item-card'),"
        " (c) => c.style.transform).filter(Boolean)})"
    )
    assert isinstance(state, dict)
    return state


def assert_gesture_clean(page: CdpPage) -> None:
    """Assert that no touch-gesture class, body flag or transform is left behind."""
    state = gesture_state(page)
    assert state == CLEAN_GESTURE_STATE, f"gesture state not clean: {state}\n{page.snapshot()}"


def record_pointer_ids(page: CdpPage) -> None:
    """Remember the id of the latest ``pointerdown`` in ``window.__lastPointerId``."""
    page.evaluate(
        "document.addEventListener('pointerdown', (e) => { window.__lastPointerId = e.pointerId; },"
        " true)"
    )


def begin_touch_drag(
    page: CdpPage, source_id: str, target_id: str, y_fraction: float, *, steps: int = 4
) -> TouchPoint:
    """Start a touch gesture on a handle and move over a target, leaving the finger down.

    Returns:
        The last finger position.
    """
    start_x, start_y = center(page, handle(source_id))
    end_x, end_y = point_in(page, card(target_id), y_fraction)
    page.touch_start([(1, start_x, start_y)])
    last: TouchPoint = (1, start_x, start_y)
    for step in range(1, steps + 1):
        fraction = step / steps
        last = (
            1,
            start_x + (end_x - start_x) * fraction,
            start_y + (end_y - start_y) * fraction,
        )
        page.touch_move([last])
    return last


def wait_gesture_active(page: CdpPage, source_id: str) -> None:
    """Wait (bounded) until the card is visibly being dragged."""
    page.wait_for(
        "card is-touch-dragging",
        f"document.querySelector({js_str(card(source_id))}).classList.contains('is-touch-dragging')",
    )


def retarget_touch_drag(
    page: CdpPage, finger: TouchPoint, target_id: str, y_fraction: float
) -> TouchPoint:
    """Re-aim the finger at the target using the layout as it is now.

    Activating a drag collapses an expanded dragged card (``.is-touch-dragging`` hides its
    details), which shifts the cards below it up; coordinates computed before the gesture may then
    miss every card. Call this after ``wait_gesture_active`` and before ``touch_end``.

    Returns:
        The new finger position.
    """
    end_x, end_y = point_in(page, card(target_id), y_fraction)
    moved: TouchPoint = (finger[0], end_x, end_y)
    page.touch_move([moved])
    return moved


def wait_suppression_window_over(page: CdpPage) -> None:
    """Wait (bounded, by the page clock) until the post-gesture click suppression has expired."""
    now = float(page.evaluate("performance.now()"))
    until = now + CLICK_SUPPRESS_MS + CLICK_SUPPRESS_MARGIN_MS
    page.wait_for("click suppression window elapsed", f"performance.now() > {until}", timeout=3.0)
