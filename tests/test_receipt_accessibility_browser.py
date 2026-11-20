"""Browser accessibility, focus, state, and mobile UX tests for the receipt dialog (WISHENKA-161).

Real Chromium over CDP at mobile viewport (390x844) with real ``receipt.js`` / markup / CSS.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from tests.browser_cdp import CdpPage
from tests.browser_helpers import (
    Seeded,
    assert_clean_console,
    focus,
    js_str,
    open_receipt_dialog,
    posts_to,
    record_receipt,
    scroll_to,
    settle,
    summary,
    title,
)
from tests.conftest import BrowserServer
from tests.receipt_support import attr_of
from tests.receipt_ui_support import SENTENCES, ui_module
from wishenka.wishlists.exceptions import InventoryBusyError
from wishenka.wishlists.service import WishlistService

pytestmark = [pytest.mark.timeout(45), pytest.mark.browser]

SeedFactory = Callable[..., Seeded]
PageFactory = Callable[..., CdpPage]

MOBILE_VIEWPORT = (390, 844)
DIALOG = "#item-receipt-modal"
FEEDBACK = "#receipt-feedback"
CONFIRM = f"{DIALOG} .btn-receipt-confirm"
CANCEL = f"{DIALOG} .btn-modal-close"
QTY = f"{DIALOG} [data-receipt-quantity]"
SUMMARY = f"{DIALOG} [data-receipt-summary]"


def _mobile_owner_page(
    seed_wishlist: SeedFactory,
    wishlist_page: PageFactory,
    titles: list[str],
    quantities: list[int],
) -> tuple[Seeded, CdpPage]:
    seeded = seed_wishlist(titles, quantities=quantities)
    page = wishlist_page(seeded, accept_language="ru", viewport=MOBILE_VIEWPORT)
    served = {r.path: r.status for r in page.requests}
    assert served.get("/static/receipt.js") == 200, f"receipt.js not loaded; requests: {served}"
    return seeded, page


def _click(page: CdpPage, selector: str) -> None:
    scroll_to(page, selector)
    page.click(selector)


def _no_external(page: CdpPage) -> None:
    assert page.external_requests == [], f"external requests: {page.external_requests}"


def test_modal_semantics_background_isolation_and_tab_trap(
    seed_wishlist: SeedFactory, wishlist_page: PageFactory
) -> None:
    """WISHENKA-161: modal has aria-modal, isolates background siblings, and traps Tab/Shift+Tab."""
    seeded, page = _mobile_owner_page(seed_wishlist, wishlist_page, ["Kettle"], [5])
    item = seeded.item_ids[0]
    page.click(title(item))
    page.click(f"#item-card-{item} .btn-receipt-item")
    open_receipt_dialog(page, seeded, item)

    assert (
        page.evaluate(f"document.querySelector({js_str(DIALOG)}).getAttribute('aria-modal')")
        == "true"
    )
    isolated = page.evaluate(
        "['#items-list', '#quick-add-bar', 'nav.top-nav'].map((sel) => {"
        "  const el = document.querySelector(sel);"
        "  return el ? {sel, inert: el.inert, hidden: el.getAttribute('aria-hidden')} : null;"
        "})"
    )
    assert isolated == [
        {"sel": "#items-list", "inert": True, "hidden": "true"},
        {"sel": "#quick-add-bar", "inert": True, "hidden": "true"},
        {"sel": "nav.top-nav", "inert": True, "hidden": "true"},
    ], f"background elements must be isolated while dialog is open: {isolated}"

    focus(page, QTY)
    seen: list[str] = []
    for _ in range(4):
        page.press_key("Tab")
        active = page.evaluate(
            f"(() => {{ const a = document.activeElement;"
            f" const d = document.querySelector({js_str(DIALOG)});"
            " return {inDialog: !!d && d.contains(a),"
            " cls: a ? a.className : '', tag: a ? a.tagName : ''}; })()"
        )
        assert active["inDialog"] is True, f"Tab escaped dialog: {active} (seen={seen})"
        seen.append(str(active["cls"] or active["tag"]))

    focus(page, QTY)
    page.press_key("Shift+Tab")
    wrapped_back = page.evaluate(
        f"(() => {{ const a = document.activeElement;"
        f" const d = document.querySelector({js_str(DIALOG)});"
        " return {inDialog: !!d && d.contains(a),"
        " isClose: !!a && a.classList.contains('btn-modal-close')}; })()"
    )
    assert wrapped_back == {"inDialog": True, "isClose": True}, (
        f"Shift+Tab from first control must wrap to last dialog control: {wrapped_back}"
    )

    page.press_key("Escape")
    page.wait_for("dialog closed", f"!document.querySelector({js_str(DIALOG)})")
    restored = page.evaluate(
        "['#items-list', '#quick-add-bar', 'nav.top-nav'].map((sel) => {"
        "  const el = document.querySelector(sel);"
        "  return el ? {sel, inert: el.inert, hidden: el.getAttribute('aria-hidden')} : null;"
        "})"
    )
    assert restored == [
        {"sel": "#items-list", "inert": False, "hidden": None},
        {"sel": "#quick-add-bar", "inert": False, "hidden": None},
        {"sel": "nav.top-nav", "inert": False, "hidden": None},
    ], f"background isolation must be cleared on close: {restored}"
    _no_external(page)
    assert_clean_console(page)


def test_focus_return_partial_full_and_refusal(
    wishlist_server: BrowserServer,
    seed_wishlist: SeedFactory,
    wishlist_page: PageFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WISHENKA-161: focus returns on partial/full receipt and stays in dialog on refusal."""
    seeded, page = _mobile_owner_page(seed_wishlist, wishlist_page, ["Kettle", "Mug"], [5, 1])
    kettle, mug = seeded.item_ids

    # 1. Partial receipt returns focus to updated wish card summary
    page.click(title(kettle))
    page.click(f"#item-card-{kettle} .btn-receipt-item")
    open_receipt_dialog(page, seeded, kettle)
    _click(page, CONFIRM)
    page.wait_for("dialog closed after partial", f"!document.querySelector({js_str(DIALOG)})")
    settle(page)
    page.wait_for(
        "focus returns to updated wish card summary",
        f"document.activeElement === document.querySelector({js_str(summary(kettle))})",
    )
    assert page.evaluate("document.querySelector('#items-list').inert") is False

    # 2. In-dialog refusal (503 busy, then 409 quantity_above_remaining) keeps focus on feedback
    module = ui_module()
    original = attr_of(module, "_execute")
    state = {"busy": True}

    async def flaky(request: object, action: object) -> object:
        if state["busy"]:
            state["busy"] = False
            raise InventoryBusyError()
        result: object = await original(request, action)
        return result

    page.click(title(kettle))
    page.click(f"#item-card-{kettle} .btn-receipt-item")
    open_receipt_dialog(page, seeded, kettle)

    monkeypatch.setattr(module, "_execute", flaky)
    _click(page, CONFIRM)
    page.wait_for(
        "busy refusal shown",
        f"document.querySelector({js_str(FEEDBACK)}).textContent.trim()"
        f" === {js_str(SENTENCES['busy'])}",
    )
    page.wait_for(
        "focus stays inside dialog on feedback after 503 refusal",
        f"document.activeElement === document.querySelector({js_str(FEEDBACK)})",
    )

    page.evaluate(
        f"(() => {{ const s = document.querySelector({js_str(QTY)}); s.value = '4';"
        " s.dispatchEvent(new Event('change', {bubbles: true})); })()"
    )
    record_receipt(wishlist_server.base_url, seeded, kettle, 3)
    _click(page, CONFIRM)
    expected_race = SENTENCES["quantity_above_remaining"].format(n=1)
    page.wait_for(
        "race refusal shown",
        f"document.querySelector({js_str(FEEDBACK)}).textContent.trim()"
        f" === {js_str(expected_race)}",
    )
    page.wait_for(
        "focus stays inside dialog on feedback after 409 OOB refusal",
        f"document.activeElement === document.querySelector({js_str(FEEDBACK)})",
    )
    page.press_key("Escape")
    page.wait_for("dialog closed", f"!document.querySelector({js_str(DIALOG)})")

    # 3. Full receipt moves focus to #list-notice (not document.body)
    page.click(title(mug))
    page.click(f"#item-card-{mug} .btn-receipt-item")
    open_receipt_dialog(page, seeded, mug)
    _click(page, CONFIRM)
    page.wait_for("full receipt removes card", f"!document.getElementById('item-card-{mug}')")
    settle(page)
    page.wait_for(
        "focus moves to #list-notice after full receipt",
        "document.activeElement === document.querySelector('#list-notice')",
    )
    assert page.evaluate("document.querySelector('#items-list').inert") is False
    _no_external(page)
    assert_clean_console(page)


def test_gifted_section_open_state_preserved(
    seed_wishlist: SeedFactory, wishlist_page: PageFactory
) -> None:
    """WISHENKA-161: expanding 'Подаренные' is preserved across receipt OOB updates."""
    seeded, page = _mobile_owner_page(seed_wishlist, wishlist_page, ["Kettle", "Mug"], [5, 2])
    kettle, mug = seeded.item_ids

    # First receipt with 'Подаренные' collapsed -> stays collapsed
    open_receipt_dialog(page, seeded, kettle)
    _click(page, CONFIRM)
    page.wait_for("dialog closed", f"!document.querySelector({js_str(DIALOG)})")
    settle(page)
    page.wait_for(
        "gifted section populated",
        "!!document.querySelector('#gifted-items-section details.gifted-items-details')",
    )
    assert (
        page.evaluate(
            "document.querySelector('#gifted-items-section details.gifted-items-details').open"
        )
        is False
    )

    # Expand 'Подаренные' and record another receipt -> stays open
    page.evaluate(
        "document.querySelector('#gifted-items-section details.gifted-items-details').open = true"
    )
    open_receipt_dialog(page, seeded, mug)
    _click(page, CONFIRM)
    page.wait_for("dialog closed", f"!document.querySelector({js_str(DIALOG)})")
    settle(page)
    page.wait_for(
        "gifted section updated with second entry",
        f"!!document.querySelector('#gifted-item-{mug}')",
    )
    assert (
        page.evaluate(
            "document.querySelector('#gifted-items-section details.gifted-items-details').open"
        )
        is True
    ), "expanded 'Подаренные' section must stay open after OOB update"
    _no_external(page)
    assert_clean_console(page)


def test_large_quantity_stepper_updates_summary_and_submits(
    seed_wishlist: SeedFactory, wishlist_page: PageFactory
) -> None:
    """WISHENKA-161: remaining > 20 uses numeric input + stepper and submits chosen quantity."""
    seeded, page = _mobile_owner_page(seed_wishlist, wishlist_page, ["Tiles"], [500])
    item = seeded.item_ids[0]
    open_receipt_dialog(page, seeded, item)

    assert page.evaluate(f"document.querySelector({js_str(DIALOG)} + ' select')") is None
    assert page.evaluate(f"document.querySelectorAll({js_str(DIALOG)} + ' option').length") == 0
    assert page.evaluate(f"document.querySelector({js_str(QTY)}).type") == "number"
    assert page.evaluate(f"document.querySelector({js_str(QTY)}).max") == "500"

    _click(page, f"{DIALOG} [data-receipt-step='1']")
    page.wait_for(
        "summary updates to 2 after + step",
        f"document.querySelector({js_str(SUMMARY)}).textContent.trim()"
        " === 'Будет отмечено получено: 2 шт. из 500 оставшихся'",
    )

    page.evaluate(
        f"(() => {{ const inp = document.querySelector({js_str(QTY)}); inp.value = '42';"
        " inp.dispatchEvent(new Event('input', {bubbles: true})); })()"
    )
    page.wait_for(
        "summary updates to 42 after input",
        f"document.querySelector({js_str(SUMMARY)}).textContent.trim()"
        " === 'Будет отмечено получено: 42 шт. из 500 оставшихся'",
    )

    _click(page, CONFIRM)
    page.wait_for("dialog closed", f"!document.querySelector({js_str(DIALOG)})")
    settle(page)
    assert [p.post_data for p in posts_to(page, "/receipt")] == ["quantity=42"]
    page.wait_for(
        "card shows 458 of 500 remaining",
        f"(document.querySelector('#item-card-{item} .badge-received') || {{}})"
        ".textContent?.trim() === 'Осталось 458 из 500'",
    )
    _no_external(page)
    assert_clean_console(page)


def test_large_quantity_out_of_range_validation_and_clamping(
    seed_wishlist: SeedFactory, wishlist_page: PageFactory
) -> None:
    """WISHENKA-222: out-of-range inputs fail validity, block submit, and clamp on change."""
    seeded, page = _mobile_owner_page(seed_wishlist, wishlist_page, ["Tiles"], [500])
    item = seeded.item_ids[0]
    open_receipt_dialog(page, seeded, item)

    cases = [
        ("0", "rangeUnderflow", "1"),
        ("501", "rangeOverflow", "500"),
    ]
    for bad_value, validity_flag, clamped_value in cases:
        page.evaluate(
            f"(() => {{ const inp = document.querySelector({js_str(QTY)});"
            f" inp.value = {js_str(bad_value)};"
            " inp.dispatchEvent(new Event('input', {bubbles: true})); })()"
        )
        validity = page.evaluate(
            f"(() => {{ const inp = document.querySelector({js_str(QTY)});"
            " return {"
            " valid: inp.checkValidity(),"
            f" flag: Boolean(inp.validity.{validity_flag})"
            " }; })()"
        )
        assert validity == {"valid": False, "flag": True}, (
            f"expected invalid {validity_flag} for {bad_value!r}, got {validity}"
        )

        # Click confirm without focusing/blurring the input so change does not clamp first.
        page.evaluate(f"document.querySelector({js_str(CONFIRM)}).click()")
        settle(page)
        assert posts_to(page, "/receipt") == [], (
            f"out-of-range value {bad_value!r} must not submit a receipt"
        )
        assert page.evaluate(f"document.querySelector({js_str(DIALOG)}) !== null") is True

        page.evaluate(
            f"(() => {{ const inp = document.querySelector({js_str(QTY)});"
            " inp.dispatchEvent(new Event('change', {bubbles: true})); })()"
        )
        page.wait_for(
            f"summary clamps {bad_value} to {clamped_value}",
            f"document.querySelector({js_str(SUMMARY)}).textContent.trim()"
            f" === 'Будет отмечено получено: {clamped_value} шт. из 500 оставшихся'",
        )
        after_clamp = page.evaluate(
            f"(() => {{ const inp = document.querySelector({js_str(QTY)});"
            " return { value: inp.value, valid: inp.checkValidity() }; })()"
        )
        assert after_clamp == {"value": clamped_value, "valid": True}

    _no_external(page)
    assert_clean_console(page)


def test_mobile_touch_targets_and_quick_add_overlay(
    seed_wishlist: SeedFactory, wishlist_page: PageFactory
) -> None:
    """WISHENKA-161: dialog controls are >= 44px and layer above #quick-add-bar at 390x844."""
    seeded, page = _mobile_owner_page(seed_wishlist, wishlist_page, ["Tiles"], [500])
    item = seeded.item_ids[0]
    open_receipt_dialog(page, seeded, item)

    assert page.evaluate("!!document.querySelector('#quick-add-bar')") is True
    boxes = page.evaluate(
        f"Array.from(document.querySelectorAll({js_str(DIALOG)} + ' [data-receipt-quantity], '"
        f" + {js_str(DIALOG)} + ' .btn-step, '"
        f" + {js_str(DIALOG)} + ' .btn-receipt-confirm, '"
        f" + {js_str(DIALOG)} + ' .btn-modal-close')).map((el) => {{"
        "  const r = el.getBoundingClientRect();"
        "  const cx = r.left + r.width / 2;"
        "  const cy = r.top + r.height / 2;"
        "  const hit = document.elementFromPoint(cx, cy);"
        "  return {"
        "    cls: el.className || el.tagName,"
        "    w: r.width,"
        "    h: r.height,"
        "    hitInSelf: !!hit && (el === hit || el.contains(hit))"
        "  };"
        "})"
    )
    assert len(boxes) >= 5, f"expected stepper + input + confirm + cancel controls: {boxes}"
    for box in boxes:
        assert box["w"] >= 44 and box["h"] >= 44, f"touch target < 44px: {box}"
        assert box["hitInSelf"] is True, f"control obscured by overlay/quick-add-bar: {box}"
    _no_external(page)
    assert_clean_console(page)


def _open_gifted_modal(page: CdpPage, button_selector: str) -> None:
    """Click a gifted-section edit/cancel button and load its modal via htmx.ajax."""
    scroll_to(page, button_selector)
    url = page.evaluate(f"document.querySelector({js_str(button_selector)}).getAttribute('hx-get')")
    assert isinstance(url, str) and url, f"missing hx-get on {button_selector}"
    page.click(button_selector)
    page.evaluate(
        f"void window.htmx.ajax('GET', {js_str(url)},"
        " {target: '#item-modal-container', swap: 'innerHTML'})"
    )
    settle(page)
    page.wait_for("receipt dialog opened", f"!!document.querySelector({js_str(DIALOG)})")


def _assert_modal_isolation_and_trap(page: CdpPage) -> None:
    """Assert aria-modal, background inert/aria-hidden, Tab trap, and Shift+Tab wrap."""
    assert (
        page.evaluate(f"document.querySelector({js_str(DIALOG)}).getAttribute('aria-modal')")
        == "true"
    )
    isolated = page.evaluate(
        "['#items-list', '#quick-add-bar', 'nav.top-nav'].map((sel) => {"
        "  const el = document.querySelector(sel);"
        "  return el ? {sel, inert: el.inert, hidden: el.getAttribute('aria-hidden')} : null;"
        "})"
    )
    assert isolated == [
        {"sel": "#items-list", "inert": True, "hidden": "true"},
        {"sel": "#quick-add-bar", "inert": True, "hidden": "true"},
        {"sel": "nav.top-nav", "inert": True, "hidden": "true"},
    ], f"background elements must be isolated while dialog is open: {isolated}"

    first_sel = f"{DIALOG} button, {DIALOG} input"
    focus(page, first_sel)
    for _ in range(4):
        page.press_key("Tab")
        active = page.evaluate(
            f"(() => {{ const a = document.activeElement;"
            f" const d = document.querySelector({js_str(DIALOG)});"
            " return {inDialog: !!d && d.contains(a),"
            " cls: a ? a.className : '', tag: a ? a.tagName : ''}; })()"
        )
        assert active["inDialog"] is True, f"Tab escaped dialog: {active}"

    focus(page, first_sel)
    page.press_key("Shift+Tab")
    wrapped_back = page.evaluate(
        f"(() => {{ const a = document.activeElement;"
        f" const d = document.querySelector({js_str(DIALOG)});"
        " return {inDialog: !!d && d.contains(a),"
        " isClose: !!a && a.classList.contains('btn-modal-close')}; })()"
    )
    assert wrapped_back == {"inDialog": True, "isClose": True}, (
        f"Shift+Tab from first control must wrap to last dialog control: {wrapped_back}"
    )


def test_edit_modal_touch_targets_and_stepper(
    wishlist_server: BrowserServer,
    seed_wishlist: SeedFactory,
    wishlist_page: PageFactory,
) -> None:
    """WISHENKA-221: edit modal has .quantity-control steppers, >= 44px targets, and submits."""
    seeded = seed_wishlist(["Tiles"], quantities=[10])
    item = seeded.item_ids[0]
    record_receipt(wishlist_server.base_url, seeded, item, 3)

    page = wishlist_page(seeded, accept_language="ru", viewport=MOBILE_VIEWPORT)
    served = {r.path: r.status for r in page.requests}
    assert served.get("/static/receipt.js") == 200, f"receipt.js not loaded; requests: {served}"

    _click(page, "#gifted-items-section details.gifted-items-details > summary")
    _open_gifted_modal(page, f"#gifted-item-{item} .btn-receipt-edit")

    structure = page.evaluate(
        f"(() => {{ const d = document.querySelector({js_str(DIALOG)});"
        " const qc = d ? d.querySelector('.quantity-control') : null;"
        " return {"
        "   hasControl: !!qc,"
        "   hasDec: !!(qc && qc.querySelector('.btn-decrement[data-receipt-step=\"-1\"]')),"
        "   hasInput: !!(qc && qc.querySelector('#receipt-edit-quantity[data-receipt-quantity]')),"
        "   hasInc: !!(qc && qc.querySelector('.btn-increment[data-receipt-step=\"1\"]'))"
        " }; })()"
    )
    assert structure == {
        "hasControl": True,
        "hasDec": True,
        "hasInput": True,
        "hasInc": True,
    }, (
        "edit modal must use .quantity-control with steppers and [data-receipt-quantity]: "
        f"{structure}"
    )

    boxes = page.evaluate(
        f"Array.from(document.querySelectorAll({js_str(DIALOG)} + ' [data-receipt-quantity], '"
        f" + {js_str(DIALOG)} + ' .btn-step, '"
        f" + {js_str(DIALOG)} + ' .btn-receipt-confirm, '"
        f" + {js_str(DIALOG)} + ' .btn-modal-close')).map((el) => {{"
        "  const r = el.getBoundingClientRect();"
        "  const cx = r.left + r.width / 2;"
        "  const cy = r.top + r.height / 2;"
        "  const hit = document.elementFromPoint(cx, cy);"
        "  return {"
        "    cls: el.className || el.tagName,"
        "    w: r.width,"
        "    h: r.height,"
        "    hitInSelf: !!hit && (el === hit || el.contains(hit))"
        "  };"
        "})"
    )
    assert len(boxes) >= 5, f"expected stepper + input + confirm + cancel controls: {boxes}"
    for box in boxes:
        assert box["w"] >= 44 and box["h"] >= 44, f"touch target < 44px: {box}"
        assert box["hitInSelf"] is True, f"control obscured by overlay/quick-add-bar: {box}"

    _click(page, f"{DIALOG} [data-receipt-step='1']")
    page.wait_for(
        "edit quantity incremented to 4",
        f"document.querySelector({js_str(QTY)}).value === '4'",
    )
    _click(page, f"{DIALOG} [data-receipt-step='-1']")
    page.wait_for(
        "edit quantity decremented to 3",
        f"document.querySelector({js_str(QTY)}).value === '3'",
    )
    _click(page, f"{DIALOG} [data-receipt-step='1']")
    _click(page, CONFIRM)
    page.wait_for("dialog closed", f"!document.querySelector({js_str(DIALOG)})")
    settle(page)
    assert [p.post_data for p in posts_to(page, "/edit")] == ["quantity=4"]
    _no_external(page)
    assert_clean_console(page)


def test_edit_and_cancel_modal_accessibility_and_focus_restoration(
    wishlist_server: BrowserServer,
    seed_wishlist: SeedFactory,
    wishlist_page: PageFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WISHENKA-221: edit/cancel modal isolation, trap, refusal focus, and gifted focus return."""
    seeded = seed_wishlist(["Kettle", "Mug"], quantities=[5, 2])
    kettle, mug = seeded.item_ids
    record_receipt(wishlist_server.base_url, seeded, kettle, 1)
    record_receipt(wishlist_server.base_url, seeded, mug, 2)

    page = wishlist_page(seeded, accept_language="ru", viewport=MOBILE_VIEWPORT)
    served = {r.path: r.status for r in page.requests}
    assert served.get("/static/receipt.js") == 200, f"receipt.js not loaded; requests: {served}"

    _click(page, "#gifted-items-section details.gifted-items-details > summary")

    # 1. Edit modal: aria-modal, background isolation, Tab/Shift+Tab, Escape focus return
    edit_btn = f"#gifted-item-{kettle} .btn-receipt-edit"
    _open_gifted_modal(page, edit_btn)
    _assert_modal_isolation_and_trap(page)
    page.press_key("Escape")
    page.wait_for("edit dialog closed", f"!document.querySelector({js_str(DIALOG)})")
    page.wait_for(
        "focus returns to triggering edit button on Escape",
        f"document.activeElement === document.querySelector({js_str(edit_btn)})",
    )

    # 2. Edit modal: 409 refusal keeps focus on #receipt-feedback; valid submit focuses #gifted-item
    _open_gifted_modal(page, edit_btn)
    record_receipt(wishlist_server.base_url, seeded, kettle, 3)
    page.evaluate(
        "(() => { const inp = document.querySelector('#receipt-edit-quantity'); inp.value = '4';"
        " inp.dispatchEvent(new Event('change', {bubbles: true})); })()"
    )
    _click(page, CONFIRM)
    expected_race = SENTENCES["quantity_above_remaining"].format(n=2)
    page.wait_for(
        "edit race refusal shown",
        f"document.querySelector({js_str(FEEDBACK)}).textContent.trim()"
        f" === {js_str(expected_race)}",
    )
    page.wait_for(
        "focus stays inside edit dialog on #receipt-feedback after 409 refusal",
        f"document.activeElement === document.querySelector({js_str(FEEDBACK)})",
    )
    page.evaluate(
        "(() => { const inp = document.querySelector('#receipt-edit-quantity'); inp.value = '2';"
        " inp.dispatchEvent(new Event('change', {bubbles: true})); })()"
    )
    _click(page, CONFIRM)
    page.wait_for("edit dialog closed after submit", f"!document.querySelector({js_str(DIALOG)})")
    settle(page)
    assert (
        page.evaluate(
            "document.querySelector('#gifted-items-section details.gifted-items-details').open"
        )
        is True
    )
    page.wait_for(
        "focus returns to #gifted-item after edit OOB replacement",
        f"document.activeElement === document.querySelector('#gifted-item-{kettle}')",
    )

    # 3. Cancel modal: aria-modal, isolation, Tab/Shift+Tab, Escape focus return, refusal feedback
    cancel_btn = f"#gifted-item-{kettle} .btn-receipt-cancel"
    _open_gifted_modal(page, cancel_btn)
    _assert_modal_isolation_and_trap(page)
    page.press_key("Escape")
    page.wait_for("cancel dialog closed", f"!document.querySelector({js_str(DIALOG)})")
    page.wait_for(
        "focus returns to triggering cancel button on Escape",
        f"document.activeElement === document.querySelector({js_str(cancel_btn)})",
    )

    original_cancel = WishlistService.cancel_item_receipt
    busy_state = {"fail": True}

    async def flaky_cancel(
        self: WishlistService,
        item_id: int,
        receipt_id: int,
        user: object,
        *,
        wishlist_id: int | None = None,
    ) -> object:
        if busy_state["fail"]:
            busy_state["fail"] = False
            raise InventoryBusyError()
        return await original_cancel(
            self,
            item_id,
            receipt_id,
            user,  # type: ignore[arg-type]
            wishlist_id=wishlist_id,
        )

    monkeypatch.setattr(WishlistService, "cancel_item_receipt", flaky_cancel)
    _open_gifted_modal(page, cancel_btn)
    _click(page, CONFIRM)
    page.wait_for(
        "cancel busy refusal shown",
        f"document.querySelector({js_str(FEEDBACK)}).textContent.trim()"
        f" === {js_str(SENTENCES['busy'])}",
    )
    page.wait_for(
        "focus stays inside cancel dialog on #receipt-feedback after 503 refusal",
        f"document.activeElement === document.querySelector({js_str(FEEDBACK)})",
    )

    # 4. Partial cancel (Kettle still has 2nd receipt) -> focus returns to #gifted-item-{kettle}
    _click(page, CONFIRM)
    page.wait_for(
        "cancel dialog closed after partial cancel", f"!document.querySelector({js_str(DIALOG)})"
    )
    settle(page)
    assert (
        page.evaluate(
            "document.querySelector('#gifted-items-section details.gifted-items-details').open"
        )
        is True
    )
    page.wait_for(
        "focus returns to #gifted-item after partial cancel OOB replacement",
        f"document.activeElement === document.querySelector('#gifted-item-{kettle}')",
    )

    # 5. Full cancel of Kettle (Mug remains) -> focus returns to details > summary, stays open
    _open_gifted_modal(page, f"#gifted-item-{kettle} .btn-receipt-cancel")
    _click(page, CONFIRM)
    page.wait_for(
        "kettle removed from gifted section",
        f"!document.querySelector('#gifted-item-{kettle}')",
    )
    settle(page)
    assert (
        page.evaluate(
            "document.querySelector('#gifted-items-section details.gifted-items-details').open"
        )
        is True
    )
    page.wait_for(
        "focus returns to gifted section summary when item is removed",
        "document.activeElement === document.querySelector("
        "'#gifted-items-section details.gifted-items-details > summary')",
    )

    # 6. Full cancel of last gifted item (Mug) -> focus returns to #list-notice
    _open_gifted_modal(page, f"#gifted-item-{mug} .btn-receipt-cancel")
    _click(page, CONFIRM)
    page.wait_for(
        "mug removed from gifted section",
        f"!document.querySelector('#gifted-item-{mug}')",
    )
    settle(page)
    page.wait_for(
        "focus returns to #list-notice when last gifted item is cancelled",
        "document.activeElement === document.querySelector('#list-notice')",
    )
    _no_external(page)
    assert_clean_console(page)
