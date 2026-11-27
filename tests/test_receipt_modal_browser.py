"""Browser tests for the receipt dialog and the stale-state handling (WISHENKA-24, B-1 to B-6).

Real Chromium over CDP, real ``receipt.js`` / ``wishlist.js`` / markup / CSS served by the
application; external scripts are replaced by offline stubs and the htmx stub does NOT process
``hx-*`` attributes, so the tests start htmx flows by calling ``htmx.ajax`` themselves (the stub
was extended in WISHENKA-24 with ``beforeSwap`` details, ``responseError``, ``swap: 'none'`` and
out-of-band swaps). The real ``hx-get`` of the card button is covered by markup tests.

STEP 3: red until Step 4 adds ``receipt.js``, the routes and the ``wishlist.js`` changes.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import pytest

from tests.browser_cdp import CdpPage, PageWaitTimeout
from tests.browser_helpers import (
    Seeded,
    archive_item_rest,
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
from tests.receipt_ui_support import (
    GENERIC_FAILURE,
    REORDER_NOTICE,
    SENTENCES,
    STALE_CARD_TEXT,
    ui_module,
)
from wishenka.wishlists.exceptions import InventoryBusyError

pytestmark = [pytest.mark.timeout(45), pytest.mark.browser]

SeedFactory = Callable[..., Seeded]
PageFactory = Callable[..., CdpPage]

DIALOG = "#item-receipt-modal"
FEEDBACK = "#receipt-feedback"
CONFIRM = f"{DIALOG} .btn-receipt-confirm"
CANCEL = f"{DIALOG} .btn-modal-close"
SELECT = f"{DIALOG} [data-receipt-quantity]"
SUMMARY = f"{DIALOG} [data-receipt-summary]"


def _assert_script_loaded(page: CdpPage) -> None:
    """The page requested ``/static/receipt.js`` and the server answered 200."""
    served = {r.path: r.status for r in page.requests}
    assert served.get("/static/receipt.js") == 200, f"receipt.js not loaded; requests: {served}"


def _text(page: CdpPage, selector: str) -> str:
    value = page.evaluate(
        f"(() => {{ const e = document.querySelector({js_str(selector)});"
        " return e ? e.textContent.replace(/\\s+/g, ' ').trim() : null; })()"
    )
    return "" if value is None else str(value)


def _feedback_is(text: str) -> str:
    """JS predicate: the feedback region holds exactly ``text``."""
    return f"document.querySelector({js_str(FEEDBACK)}).textContent.trim() === {js_str(text)}"


def _choose(page: CdpPage, value: int) -> None:
    """Pick a quantity in the dialog select the way a user does (value plus ``change``)."""
    page.evaluate(
        f"(() => {{ const s = document.querySelector({js_str(SELECT)}); s.value = '{value}';"
        " s.dispatchEvent(new Event('change', {bubbles: true})); })()"
    )


def _click(page: CdpPage, selector: str) -> None:
    scroll_to(page, selector)
    page.click(selector)


def _wait_until(page: CdpPage, description: str, predicate: str, timeout: float = 6.0) -> None:
    """Like ``wait_for`` but tolerant of a page that is reloading (bounded by ``timeout``)."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            if page.evaluate(predicate):
                return
        except PageWaitTimeout:
            raise
        except AssertionError:
            pass  # the execution context is replaced while the page reloads
        if time.monotonic() >= deadline:
            raise PageWaitTimeout(f"timed out after {timeout:g}s waiting for: {description}")
        time.sleep(0.05)


def _owner_page(
    seed_wishlist: SeedFactory,
    wishlist_page: PageFactory,
    titles: list[str],
    quantities: list[int],
) -> tuple[Seeded, CdpPage]:
    seeded = seed_wishlist(titles, quantities=quantities)
    page = wishlist_page(seeded, accept_language="ru")
    _assert_script_loaded(page)
    return seeded, page


def _no_external(page: CdpPage) -> None:
    assert page.external_requests == [], f"external requests: {page.external_requests}"


# --- B-1: summary, focus, dismissal ----------------------------------------------------------


def test_summary_updates_and_dismiss_changes_nothing(
    seed_wishlist: SeedFactory, wishlist_page: PageFactory
) -> None:
    """U-3, N-4: summary follows the select; Cancel and Escape close without a request."""
    seeded, page = _owner_page(seed_wishlist, wishlist_page, ["Kettle"], [5])
    item = seeded.item_ids[0]
    page.click(title(item))
    page.click(f"#item-card-{item} .btn-receipt-item")
    open_receipt_dialog(page, seeded, item)

    page.wait_for(
        "focus moves into the dialog", f"document.activeElement.matches({js_str(SELECT)})"
    )
    assert _text(page, SUMMARY) == "Будет отмечено получено: 1 шт. из 5 оставшихся"
    _choose(page, 3)
    page.wait_for(
        "summary shows 3",
        f"document.querySelector({js_str(SUMMARY)}).textContent.trim()"
        " === 'Будет отмечено получено: 3 шт. из 5 оставшихся'",
    )
    order = page.evaluate(
        f"Array.from(document.querySelectorAll({js_str(DIALOG)} + ' select, ' + {js_str(DIALOG)}"
        " + ' button')).map((e) => [e.tagName, e.className, e.tabIndex])"
    )
    assert [row[0] for row in order] == ["SELECT", "BUTTON", "BUTTON"], order
    assert "btn-receipt-confirm" in order[1][1] and "btn-modal-close" in order[2][1]
    assert all(row[2] >= 0 for row in order), f"controls must be keyboard reachable: {order}"

    _click(page, CANCEL)
    page.wait_for("dialog closed by Cancel", f"!document.querySelector({js_str(DIALOG)})")
    assert _text(page, "#item-modal-container") == ""
    page.wait_for(
        "focus returned to the card summary",
        f"document.activeElement === document.querySelector({js_str(summary(item))})",
    )

    page.click(f"#item-card-{item} .btn-receipt-item")
    open_receipt_dialog(page, seeded, item)
    page.press_key("Escape")
    page.wait_for("dialog closed by Escape", f"!document.querySelector({js_str(DIALOG)})")
    page.wait_for(
        "focus returned after Escape",
        f"document.activeElement === document.querySelector({js_str(summary(item))})",
    )
    assert posts_to(page, "/receipt") == [], "dismissal must not send a request"
    assert [c for c in page.ajax_calls() if c["verb"] == "POST"] == []
    _no_external(page)
    assert_clean_console(page)


# --- B-2: partial and full receipt update the page ---------------------------------------------


def test_partial_and_full_receipt_update_page(
    seed_wishlist: SeedFactory, wishlist_page: PageFactory
) -> None:
    """U-5, U-6: only ``quantity`` is posted; card, notice and section update without reload."""
    seeded, page = _owner_page(seed_wishlist, wishlist_page, ["Kettle", "Mug"], [5, 1])
    kettle, mug = seeded.item_ids
    open_receipt_dialog(page, seeded, kettle)
    _choose(page, 2)
    focus(page, CONFIRM)
    page.press_key("Enter")

    page.wait_for("dialog closed after the receipt", f"!document.querySelector({js_str(DIALOG)})")
    settle(page)
    posts = posts_to(page, "/receipt")
    assert [p.post_data for p in posts] == ["quantity=2"], [p.post_data for p in posts]
    page.wait_for(
        "card shows the remaining quantity",
        f"(document.querySelector('#item-card-{kettle} .badge-received') || {{}})"
        ".textContent?.trim() === 'Осталось 3 из 5'",
    )
    assert _text(page, "#list-notice") == "Отмечено получено: 2 шт. («Kettle»)"
    entry = _text(page, f"#gifted-item-{kettle}")
    assert "Получено: 2 из 5" in entry, entry
    assert _text(page, "#gifted-items-section summary") == "Подаренные (1)"

    open_receipt_dialog(page, seeded, mug)
    assert page.evaluate(f"document.querySelector({js_str(SELECT)})") is None
    _click(page, CONFIRM)
    page.wait_for("full receipt removes the card", f"!document.getElementById('item-card-{mug}')")
    settle(page)
    assert [p.post_data for p in posts_to(page, "/receipt")] == ["quantity=2", "quantity=1"]
    assert page.order() == [kettle]
    assert _text(page, "#gifted-items-section summary") == "Подаренные (2)"
    assert _text(page, "#list-notice") == "Отмечено получено: 1 шт. («Mug»)"
    _no_external(page)
    assert_clean_console(page)


# --- B-3: in-flight guard ----------------------------------------------------------------------

_GATE_JS = """
(() => {
  const original = window.fetch.bind(window);
  window.__gated = [];
  window.__release = null;
  window.fetch = (input, init) => {
    if (init && init.method === 'POST' && String(input).includes('/receipt')) {
      window.__gated.push(String(input));
      return new Promise((resolve, reject) => {
        window.__release = () => original(input, init).then(resolve, reject);
      });
    }
    return original(input, init);
  };
})()
"""


# [submit button disabled, button or form marked ``aria-busy="true"``]
_BUSY_STATE_JS = (
    f"(() => {{ const b = document.querySelector({js_str(CONFIRM)});"
    f" const f = document.querySelector({js_str(DIALOG)} + ' form');"
    " return [b.disabled,"
    " b.getAttribute('aria-busy') === 'true' || f.getAttribute('aria-busy') === 'true']; })()"
)


def test_second_tap_sends_no_second_request(
    seed_wishlist: SeedFactory, wishlist_page: PageFactory
) -> None:
    """U-4, DoD 4: while one request is in flight, clicks and a second submit send nothing."""
    seeded, page = _owner_page(seed_wishlist, wishlist_page, ["Kettle"], [5])
    item = seeded.item_ids[0]
    open_receipt_dialog(page, seeded, item)
    _choose(page, 2)
    page.evaluate(_GATE_JS)
    page.set_bearer("bad-token")

    _click(page, CONFIRM)
    page.wait_for("first request is in flight", "window.__gated.length === 1")
    page.click(CONFIRM)
    page.click(CONFIRM)
    page.evaluate(f"document.querySelector({js_str(DIALOG)} + ' form').requestSubmit()")

    assert page.evaluate("window.__gated.length") == 1, "a second request was started"
    posts = [c for c in page.ajax_calls() if c["verb"] == "POST"]
    assert len(posts) == 1, f"htmx.ajax POST calls: {posts}"
    assert posts_to(page, "/receipt") == [], "no network request before the gate opens"
    state = page.evaluate(_BUSY_STATE_JS)
    assert state == [True, True], f"submit button must be disabled and the dialog busy: {state}"

    page.evaluate("window.__release()")
    page.wait_for(
        "generic failure is shown",
        _feedback_is(GENERIC_FAILURE),
    )
    settle(page)
    assert len(posts_to(page, "/receipt")) == 1
    after = page.evaluate(_BUSY_STATE_JS)
    assert after == [False, False], f"button must be usable again: {after}"
    assert page.evaluate(f"document.querySelector({js_str(SELECT)}).value") == "2", (
        "the chosen quantity must survive a failed attempt"
    )
    _no_external(page)
    assert_clean_console(page)


# --- B-4: refusal, then generic failure -----------------------------------------------------------


def test_refusal_then_generic_failure_replaces_sentence(
    wishlist_server: BrowserServer, seed_wishlist: SeedFactory, wishlist_page: PageFactory
) -> None:
    """U-8: a lost race shows the sentence with N; a later failure replaces it."""
    seeded, page = _owner_page(seed_wishlist, wishlist_page, ["Kettle"], [5])
    item = seeded.item_ids[0]
    open_receipt_dialog(page, seeded, item)
    _choose(page, 5)
    record_receipt(wishlist_server.base_url, seeded, item, 4)

    _click(page, CONFIRM)
    expected = SENTENCES["quantity_above_remaining"].format(n=1)
    page.wait_for(
        "refusal sentence with N",
        _feedback_is(expected),
    )
    assert page.evaluate(f"!!document.querySelector({js_str(DIALOG)})"), "dialog must stay open"
    assert page.evaluate(f"document.querySelector({js_str(CONFIRM)}).disabled") is False

    page.set_bearer("bad-token")
    _click(page, CONFIRM)
    page.wait_for(
        "generic failure replaces the refusal sentence",
        _feedback_is(GENERIC_FAILURE),
    )
    assert expected not in _text(page, FEEDBACK)

    page.press_key("Escape")
    page.set_bearer(seeded.owner_token)
    open_receipt_dialog(page, seeded, item)
    page.set_bearer("bad-token")
    _click(page, CONFIRM)
    page.wait_for(
        "first-attempt failure shows the generic sentence",
        _feedback_is(GENERIC_FAILURE),
    )
    _no_external(page)
    assert_clean_console(page)


def test_busy_keeps_dialog_and_chosen_quantity(
    seed_wishlist: SeedFactory, wishlist_page: PageFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """U-9: a busy answer keeps the dialog and the chosen quantity; the next attempt succeeds."""
    seeded, page = _owner_page(seed_wishlist, wishlist_page, ["Kettle"], [5])
    item = seeded.item_ids[0]
    open_receipt_dialog(page, seeded, item)
    _choose(page, 3)
    module = ui_module()
    original = attr_of(module, "_execute")
    state = {"busy": True}

    async def flaky(request: object, action: object) -> object:
        if state["busy"]:
            state["busy"] = False
            raise InventoryBusyError()
        result: object = await original(request, action)
        return result

    monkeypatch.setattr(module, "_execute", flaky)

    _click(page, CONFIRM)
    page.wait_for(
        "busy sentence",
        _feedback_is(SENTENCES["busy"]),
    )
    kept = page.evaluate(
        f"(() => {{ const s = document.querySelector({js_str(SELECT)});"
        f" const b = document.querySelector({js_str(CONFIRM)});"
        " return [s.value, b.disabled]; })()"
    )
    assert kept == ["3", False], f"chosen quantity must stay and the button be enabled: {kept}"

    _click(page, CONFIRM)
    page.wait_for("dialog closes after the retry", f"!document.querySelector({js_str(DIALOG)})")
    page.wait_for(
        "card shows the remaining quantity",
        f"(document.querySelector('#item-card-{item} .badge-received') || {{}})"
        ".textContent?.trim() === 'Осталось 2 из 5'",
    )
    assert len(posts_to(page, "/receipt")) == 2
    _no_external(page)
    assert_clean_console(page)


_BEFORE_SWAP_JS = """
(() => {
  const make = (headers) => ({
    target: document.body,
    xhr: headers === null ? undefined : {
      status: 409,
      getResponseHeader: (name) => {
        const wanted = String(name).toLowerCase();
        const key = Object.keys(headers).find((k) => k.toLowerCase() === wanted);
        return key === undefined ? null : headers[key];
      },
    },
    shouldSwap: false,
    isError: true,
  });
  const run = (headers) => {
    const detail = make(headers);
    document.body.dispatchEvent(
      new CustomEvent('htmx:beforeSwap', {bubbles: true, cancelable: true, detail}),
    );
    return [detail.shouldSwap, detail.isError];
  };
  const result = {};
  const bare = {target: document.body};
  document.body.dispatchEvent(
    new CustomEvent('htmx:beforeSwap', {bubbles: true, cancelable: true, detail: bare}),
  );
  result.bare = Object.keys(bare);
  REASONS.forEach((reason) => { result[reason] = run({'X-Receipt-Refusal': reason}); });
  result.unknown = run({'X-Receipt-Refusal': 'stale_order'});
  result.other = run({'X-Receipt-Refusal': 'something_else'});
  result.reorder = run({'X-Reorder-Refusal': 'stale_order'});
  result.none = run({});
  return result;
})()
"""


def test_before_swap_override_is_guarded_and_closed(
    seed_wishlist: SeedFactory, wishlist_page: PageFactory
) -> None:
    """Decision 4: only a closed receipt reason re-enables a swap; a missing ``xhr`` is ignored."""
    _seeded, page = _owner_page(seed_wishlist, wishlist_page, ["Kettle"], [5])
    reasons = sorted(SENTENCES)

    result = page.evaluate(_BEFORE_SWAP_JS.replace("REASONS", repr(reasons)))

    assert result["bare"] == ["target"], f"a detail without xhr must stay untouched: {result}"
    for reason in reasons:
        assert result[reason] == [True, False], f"{reason}: {result[reason]}"
    for case in ("unknown", "other", "reorder", "none"):
        assert result[case] == [False, True], f"{case}: {result[case]}"
    _no_external(page)
    assert_clean_console(page)


# --- B-5: stale giver card ------------------------------------------------------------------------

_AFTER_REQUEST_JS = """
(() => {
  const button = document.querySelector(%s);
  button.dispatchEvent(new CustomEvent('htmx:afterRequest', {
    bubbles: true,
    detail: {elt: button, xhr: {status: 200, responseText: ''}},
  }));
})()
"""


def test_stale_giver_card_is_neutral(
    wishlist_server: BrowserServer, seed_wishlist: SeedFactory, share_page: PageFactory
) -> None:
    """U-19: a refresh of a received wish ends in a neutral text; a valid refresh still swaps."""
    seeded = seed_wishlist(["Gone", "Stays"], quantities=[1, 3])
    gone, stays = seeded.item_ids
    page = share_page(seeded, as_user="viewer", accept_language="ru")
    _assert_script_loaded(page)
    button = f"#item-card-{gone} form button[type=submit]"
    assert page.evaluate(f"!!document.querySelector({js_str(button)})"), "giver form missing"
    record_receipt(wishlist_server.base_url, seeded, gone, 1)

    page.evaluate(_AFTER_REQUEST_JS % js_str(button))

    page.wait_for(
        "neutral replacement of the stale card",
        f"document.body.innerText.includes({js_str(STALE_CARD_TEXT)})",
    )
    body = str(page.evaluate("document.body.innerText"))
    assert '{"detail"' not in body and "Item not found" not in body, body
    assert page.evaluate(f"document.getElementById('item-card-{gone}')") is None
    assert page.evaluate("document.querySelectorAll('.item-card-unavailable').length") == 1

    page.click(title(stays))
    page.evaluate(f"window.__oldCard = document.getElementById('item-card-{stays}')")
    page.evaluate(_AFTER_REQUEST_JS % js_str(f"#item-card-{stays} form button[type=submit]"))
    page.wait_for(
        "valid refresh swaps the card",
        f"document.getElementById('item-card-{stays}') !== window.__oldCard",
    )
    state = page.card_state(stays)
    assert state == {"expanded": "true", "hidden": False}, f"expansion lost: {state}"
    _no_external(page)
    assert_clean_console(page)


# --- B-6: stale reorder ---------------------------------------------------------------


def test_stale_reorder_keeps_list_and_shows_notice(
    wishlist_server: BrowserServer, seed_wishlist: SeedFactory, wishlist_page: PageFactory
) -> None:
    """U-11: a stale reorder never swaps ``#items-list``; notice shown, then the page reloads."""
    seeded, page = _owner_page(seed_wishlist, wishlist_page, ["A", "B", "C"], [1, 1, 1])
    first, second, third = seeded.item_ids
    page.evaluate("window.__beforeReload = true")
    archive_item_rest(wishlist_server.base_url, seeded, third)
    path = f"/web/wishlists/{seeded.wishlist_id}/items/reorder"

    page.evaluate(
        f"void window.htmx.ajax('POST', {js_str(path)}, {{target: '#items-list', swap: 'innerHTML',"
        f" values: {{item_ids: [{second}, {first}, {third}]}}}})"
    )

    page.wait_for(
        "stale reorder notice",
        f"document.querySelector('#list-notice') && "
        f"document.querySelector('#list-notice').textContent.trim() === {js_str(REORDER_NOTICE)}",
    )
    assert page.order() == [first, second, third], "#items-list must not be replaced"
    listed = _text(page, "#items-list")
    assert "Invalid item order" not in listed and '{"detail"' not in listed

    _wait_until(page, "page reloaded", "window.__beforeReload === undefined")
    page.wait_for(
        "reloaded list is current",
        "document.querySelectorAll('#items-list .item-card').length === 2",
    )
    assert page.order() == [first, second]
    _no_external(page)
    assert_clean_console(page)


def test_unmarked_error_neither_shows_notice_nor_reloads(
    seed_wishlist: SeedFactory, wishlist_page: PageFactory
) -> None:
    """Archiving a wish that is not on the list shows the list notice and does not reload.

    The Russian owner page shows «Желание или вишлист больше недоступны.», the archive
    dialog closes, and the remaining cards stay in the same order. The page does not reload.
    The check does not listen for ``htmx:responseError``.
    """
    seeded, page = _owner_page(seed_wishlist, wishlist_page, ["A", "B"], [1, 1])
    first, second = seeded.item_ids
    notice = "Желание или вишлист больше недоступны."
    page.evaluate("window.__beforeReload = true")
    confirm = f"/web/wishlists/{seeded.wishlist_id}/items/{first}/archive-confirm"
    page.evaluate(
        f"void window.htmx.ajax('GET', {js_str(confirm)},"
        " {target: '#item-modal-container', swap: 'innerHTML'})"
    )
    page.wait_for("archive confirm opened", "!!document.querySelector('#item-archive-modal')")

    path = f"/web/wishlists/{seeded.wishlist_id}/items/999999/archive"
    page.evaluate(
        f"void window.htmx.ajax('POST', {js_str(path)}, {{target: '#items-list', swap: 'none'}})"
    )
    page.wait_for(
        "missing-wish notice and closed dialog",
        "(() => { const notice = document.querySelector('#list-notice');"
        " const modal = document.getElementById('item-modal-container');"
        f" return !!notice && notice.textContent.trim() === {js_str(notice)}"
        " && !document.querySelector('#item-archive-modal')"
        " && !!modal && modal.innerHTML.trim() === ''; })()",
    )

    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        assert page.evaluate("window.__beforeReload === true"), "the page must not reload"
        assert _text(page, "#list-notice") == notice, "the missing-wish notice must stay"
        time.sleep(0.1)
    assert page.order() == [first, second], "the list must stay in the same order"
    _no_external(page)
    assert_clean_console(page)
