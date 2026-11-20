"""Red tests for the receipt dialog routes of the Mini App (WISHENKA-24, plan T-2).

Today ``GET`` and ``POST /web/wishlists/{id}/items/{item}/receipt`` do not exist (HTTP 404),
``wishenka.web.routes.receipts_ui`` and the partial ``item_receipt_modal.html`` are missing. The
tests assert the behaviour of ``ai-tasks/WISHENKA-24/20-architecture.md`` (routes, refusal table,
OOB fragments, logging). Production symbols are imported inside the tests.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI

from tests.receipt_support import (
    CO_AUTHOR,
    CO_AUTHOR_ID,
    GIFTER_ID,
    OTHER_GIFTER_ID,
    OWNER,
    OWNER_ID,
    STRANGER_ID,
    AppEnv,
    app_env,
    attr_of,
    db_path_of,
    item_received,
    new_symbol,
)
from tests.receipt_ui_support import (
    BOOKING_WORDS,
    GENERIC_FAILURE,
    REFUSAL_HEADER,
    SENTENCES,
    XSS_TITLE,
    Wish,
    assert_all_top_level_oob,
    assert_no_booking_leak,
    domain,
    hx,
    modal_url,
    on_attributes,
    oob,
    oob_list,
    parse,
    receive,
    render_partial,
    run,
    seed_booked,
    seed_list,
    text_of,
    top_level,
    ui_module,
    utc_days_around,
)
from wishenka.wishlists.exceptions import InventoryBusyError, PermissionDeniedError

pytestmark = pytest.mark.timeout(30)

_UI_LOGGER = "wishenka.web.receipts_ui"
_ALLOWED_EXTRAS = {"wishlist_id", "item_id", "actor_id", "reason", "http_status"}
_ATTEMPT_EVENTS = {"receipt_recorded_http", "receipt_refused", "receipt_inventory_busy"}
_STANDARD = set(logging.LogRecord("n", 0, "p", 0, "m", (), None).__dict__) | {"message", "asctime"}


@pytest.fixture
def env(tmp_path: Path) -> Iterator[AppEnv]:
    """Open create_app on an isolated SQLite file with bearer sessions."""
    with app_env(tmp_path) as opened:
        yield opened


def _get(env: AppEnv, wishlist_id: int, item_id: int, user_id: int = OWNER_ID) -> Any:
    client, sessions, _app = env
    return client.get(modal_url(wishlist_id, item_id), headers=hx(sessions, user_id))


def _post(
    env: AppEnv, wishlist_id: int, item_id: int, quantity: str, user_id: int = OWNER_ID
) -> Any:
    client, sessions, _app = env
    return client.post(
        modal_url(wishlist_id, item_id),
        data={"quantity": quantity},
        headers=hx(sessions, user_id),
    )


def _feedback(soup: Any) -> str:
    return text_of(soup.select_one("#receipt-feedback"))


def _sentence_of(soup: Any) -> str:
    """The refusal sentence: the plain OOB feedback fragment, else the re-rendered dialog's."""
    for element in top_level(soup):
        if element.get("id") == "receipt-feedback":
            return text_of(element)
    dialog = oob(soup, "item-receipt-modal")
    return text_of(dialog.select_one("#receipt-feedback"))


def _patch_execute(
    monkeypatch: pytest.MonkeyPatch, replacement: Callable[[Callable[..., Any]], Any]
) -> None:
    """Replace ``receipts_ui._execute`` by ``replacement(original)``."""
    module = ui_module()
    original = attr_of(module, "_execute")
    monkeypatch.setattr(module, "_execute", replacement(original))


def _busy_execute(_original: Callable[..., Any]) -> Callable[..., Any]:
    async def busy(*_args: object, **_kwargs: object) -> None:
        raise InventoryBusyError()

    return busy


# --- GET: the dialog ----------------------------------------------------------------------------


@pytest.mark.parametrize("title", ["Kettle", XSS_TITLE])
def test_get_modal_content_for_member(env: AppEnv, title: str) -> None:
    """U-1 to U-3, N-4: dialog texts, bound label, alert region, no inline code, escaped title."""
    _client, _sessions, app = env
    wishlist_id, (item_id, *_rest) = seed_list(app, [Wish(title, 5)])

    response = _get(env, wishlist_id, item_id)

    assert response.status_code == 200, response.text
    soup = parse(response.text)
    root = soup.select_one("#item-receipt-modal")
    assert root is not None and root.get("role") == "dialog"
    assert root.has_attr("data-receipt-modal")
    assert text_of(root.select_one("h2")) == "Отметить получение"
    assert text_of(soup.select_one(".receipt-wish")) == title
    assert "Осталось: 5" in text_of(root)
    select = root.select_one("select[name=quantity]")
    assert select is not None, response.text
    assert [o.get("value") for o in select.select("option")] == ["1", "2", "3", "4", "5"]
    selected = [o.get("value") for o in select.select("option[selected]")]
    assert selected == ["1"]
    label = root.select_one(f"label[for='{select.get('id')}']")
    assert label is not None and text_of(label) == "Сколько штук получено"
    summary = soup.select_one("[data-receipt-summary]")
    assert text_of(summary) == "Будет отмечено получено: 1 шт. из 5 оставшихся"
    assert "Ошибку можно будет исправить или отменить в разделе «Подаренные»." in text_of(root)
    buttons = [text_of(b) for b in root.select("button")]
    assert "Отметить полученным" in buttons and "Отмена" in buttons
    feedback = root.select_one("#receipt-feedback")
    assert feedback is not None and feedback.get("role") == "alert"
    form = root.select_one("form[data-receipt-form]")
    assert form is not None and form.get("action") == modal_url(wishlist_id, item_id)
    assert form.get("hx-post") is None and form.get("hx-get") is None
    assert on_attributes(soup) == []
    assert soup.find("script") is None
    assert [tag.name for tag in soup.find_all(True) if tag.has_attr("style")] == []
    if title == XSS_TITLE:
        assert XSS_TITLE not in response.text
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text


def test_get_modal_busy_is_503_with_header(env: AppEnv, monkeypatch: pytest.MonkeyPatch) -> None:
    """U-9: a busy snapshot read gives 503, ``X-Receipt-Refusal: busy`` and a blocked dialog."""
    _client, _sessions, app = env
    wishlist_id, (item_id, *_rest) = seed_list(app)
    _patch_execute(monkeypatch, _busy_execute)

    response = _get(env, wishlist_id, item_id)

    assert response.status_code == 503, response.text
    assert response.headers.get(REFUSAL_HEADER) == "busy"
    soup = parse(response.text)
    assert _feedback(soup) == SENTENCES["busy"]
    assert soup.select_one("form") is None
    for word in ("занято", "занят"):
        assert word not in response.text.lower()


def test_modal_template_oob_switch(env: AppEnv) -> None:
    """Design: ``oob`` makes the dialog root an ``outerHTML`` OOB swap; ``blocked`` has no form."""
    context: dict[str, Any] = {
        "wishlist_id": 1,
        "item_id": 2,
        "item_title": "Kettle",
        "remaining": 3,
        "feedback": "",
        "blocked": False,
        "selected": 1,
    }
    default = parse(render_partial("partials/item_receipt_modal.html", **context))
    root = default.select_one("#item-receipt-modal")
    assert root is not None and not root.has_attr("hx-swap-oob")
    assert default.select_one("form[data-receipt-form]") is not None

    switched = parse(render_partial("partials/item_receipt_modal.html", **context, oob=True))
    swapped_root = switched.select_one("#item-receipt-modal")
    assert swapped_root is not None and swapped_root.get("hx-swap-oob") == "outerHTML"

    blocked = parse(
        render_partial(
            "partials/item_receipt_modal.html", **{**context, "blocked": True, "feedback": "Нет"}
        )
    )
    assert blocked.select_one("form") is None
    assert blocked.select_one("[data-modal-close]") is not None
    assert text_of(blocked.select_one("#receipt-feedback")) == "Нет"
    assert on_attributes(default) == [] and on_attributes(blocked) == []


def test_get_modal_remaining_one_has_no_choice(env: AppEnv) -> None:
    """U-3: one unit left gives a hidden quantity of 1, no select and the short summary."""
    _client, _sessions, app = env
    wishlist_id, (item_id, *_rest) = seed_list(app, [Wish("Kettle", 3)])
    receive(app, item_id, 2)

    response = _get(env, wishlist_id, item_id)

    assert response.status_code == 200, response.text
    soup = parse(response.text)
    assert soup.select_one("select") is None
    hidden = soup.select_one("form input[type=hidden][name=quantity]")
    assert hidden is not None and hidden.get("value") == "1"
    assert text_of(soup.select_one("[data-receipt-summary]")) == "Будет отмечено получено: 1 шт."
    assert "Осталось: 1" in text_of(soup)


def test_get_modal_large_quantity_renders_stepper_not_large_select(env: AppEnv) -> None:
    """WISHENKA-161: remaining > 20 renders numeric input + stepper instead of a large select."""
    _client, _sessions, app = env
    wishlist_id, (item_id, *_rest) = seed_list(app, [Wish("Tiles", 500)])

    response = _get(env, wishlist_id, item_id)

    assert response.status_code == 200, response.text
    soup = parse(response.text)
    assert soup.select_one("select") is None
    assert len(soup.select("option")) == 0
    qty = soup.select_one('form input[type="number"][name="quantity"][data-receipt-quantity]')
    assert qty is not None
    assert qty.get("min") == "1"
    assert qty.get("max") == "500"
    assert qty.get("data-remaining") == "500"
    steps = soup.select("form [data-receipt-step]")
    assert [s.get("data-receipt-step") for s in steps] == ["-1", "1"]
    assert on_attributes(soup) == []


@pytest.mark.parametrize(("remaining", "expect_select"), [(20, True), (21, False)])
def test_get_modal_select_max_boundary(env: AppEnv, remaining: int, expect_select: bool) -> None:
    """WISHENKA-222: RECEIPT_SELECT_MAX=20 renders select at 20 and numeric stepper at 21."""
    _client, _sessions, app = env
    wishlist_id, (item_id, *_rest) = seed_list(app, [Wish("Tiles", remaining)])

    response = _get(env, wishlist_id, item_id)

    assert response.status_code == 200, response.text
    soup = parse(response.text)
    select = soup.select_one('form select[name="quantity"][data-receipt-quantity]')
    qty_input = soup.select_one('form input[type="number"][name="quantity"][data-receipt-quantity]')
    steps = soup.select("form [data-receipt-step]")
    if expect_select:
        assert select is not None
        assert select.get("data-remaining") == str(remaining)
        options = select.select("option")
        assert [o.get("value") for o in options] == [str(i) for i in range(1, remaining + 1)]
        assert qty_input is None
        assert steps == []
    else:
        assert select is None
        assert len(soup.select("option")) == 0
        assert qty_input is not None
        assert qty_input.get("min") == "1"
        assert qty_input.get("max") == str(remaining)
        assert qty_input.get("data-remaining") == str(remaining)
        assert [s.get("data-receipt-step") for s in steps] == ["-1", "1"]
    assert on_attributes(soup) == []


def test_get_modal_has_no_booking_data(env: AppEnv) -> None:
    """U-20, N-1: promises, giver names and ids never reach the dialog."""
    _client, _sessions, app = env
    wishlist_id, item_id = seed_booked(app)

    response = _get(env, wishlist_id, item_id)

    assert response.status_code == 200, response.text
    assert "Осталось: 10" in text_of(parse(response.text))
    assert_no_booking_leak(response.text)
    for giver_id in (GIFTER_ID, OTHER_GIFTER_ID):
        assert re.search(rf"(?<!\d){giver_id}(?!\d)", response.text) is None


def _blocked_case(app: FastAPI, case: str) -> tuple[int, int, int, int, str, bool]:
    """Prepare a stale-dialog case; returns list, item, user, status, reason, title shown."""
    wishlist_id, (item_id, *_rest) = seed_list(app, [Wish("Secret Kettle", 2)])
    service = domain(app)
    user_id = OWNER_ID
    if case == "wish_archived":
        run(service.archive_wish_item(wishlist_id, item_id, OWNER))
        return wishlist_id, item_id, user_id, 409, "wish_archived", True
    if case == "nothing_remaining":
        receive(app, item_id, 2)
        return wishlist_id, item_id, user_id, 409, "nothing_remaining", True
    if case == "list_archived":
        run(service.archive_wishlist(wishlist_id, OWNER))
        return wishlist_id, item_id, user_id, 409, "wishlist_not_active", True
    if case == "list_deleted":
        run(service.delete_wishlist(wishlist_id, OWNER))
        return wishlist_id, item_id, user_id, 404, "wishlist_not_active", False
    if case == "forbidden":
        return wishlist_id, item_id, STRANGER_ID, 403, "forbidden", False
    return wishlist_id, item_id + 1000, user_id, 404, "not_found", False


@pytest.mark.parametrize(
    "case",
    ["wish_archived", "nothing_remaining", "list_archived", "list_deleted", "forbidden", "unknown"],
)
def test_get_modal_refusals_blocked_state(env: AppEnv, case: str) -> None:
    """U-8, U-20: contract status, header, sentence, no form, «Закрыть»; no title for strangers."""
    _client, _sessions, app = env
    wishlist_id, item_id, user_id, status, reason, title_shown = _blocked_case(app, case)

    response = _get(env, wishlist_id, item_id, user_id)

    assert response.status_code == status, response.text
    assert response.headers.get(REFUSAL_HEADER) == reason
    soup = parse(response.text)
    assert _feedback(soup) == SENTENCES[reason]
    assert soup.select_one("form") is None
    close = soup.select_one("[data-modal-close]")
    assert close is not None and text_of(close) == "Закрыть"
    wish = soup.select_one(".receipt-wish")
    if title_shown:
        assert wish is not None and text_of(wish) == "Secret Kettle"
    elif case in {"forbidden", "unknown"}:
        assert wish is None, response.text
        assert "Secret Kettle" not in response.text
    if case == "nothing_remaining":
        top = parse(response.text)
        assert oob_list(top) is not None
        assert oob(top, "gifted-items-section").get("hx-swap-oob") == "outerHTML"
        assert "Secret Kettle" in text_of(oob(top, "gifted-items-section"))


# --- POST: success ------------------------------------------------------------------------------


@pytest.mark.parametrize("title", ["Kettle", XSS_TITLE])
def test_post_partial_receipt_fragments(env: AppEnv, title: str) -> None:
    """U-5, U-6, DoD 2, 7: 201 with OOB close, notice, card and gifted section (escaped title)."""
    _client, _sessions, app = env
    wishlist_id, (item_id, *_rest) = seed_list(app, [Wish(title, 5)])
    before = datetime.now(UTC)

    response = _post(env, wishlist_id, item_id, "2")

    after = datetime.now(UTC)
    assert response.status_code == 201, response.text
    assert REFUSAL_HEADER not in response.headers
    soup = parse(response.text)
    assert_all_top_level_oob(soup, response.text)
    close = oob(soup, "item-modal-container")
    assert close.get("hx-swap-oob") == "innerHTML" and text_of(close) == ""
    notice = oob(soup, "list-notice")
    assert notice.get("hx-swap-oob") == "innerHTML"
    assert text_of(notice) == f"Отмечено получено: 2 шт. («{title}»)"
    card = oob(soup, f"item-card-{item_id}")
    assert card.get("hx-swap-oob") == "true"
    assert "Осталось 3 из 5" in text_of(card.select_one(".item-badges"))
    gifted = oob(soup, "gifted-items-section")
    assert gifted.get("hx-swap-oob") == "outerHTML"
    gifted_text = text_of(gifted)
    assert "Получено: 2 из 5" in gifted_text
    day = re.search(r"(\d{2}\.\d{2}\.\d{4}) — 2 шт\.", gifted_text)
    assert day is not None, gifted_text
    assert day.group(1) in utc_days_around((before, after))
    assert soup.find("script") is None
    if title == XSS_TITLE:
        assert XSS_TITLE not in response.text
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text
    lowered = response.text.lower()
    for word in BOOKING_WORDS:
        assert word not in lowered, word
    assert item_received(db_path_of(app), item_id) == 2


def test_post_full_receipt_removes_card_and_fixes_flags(env: AppEnv) -> None:
    """U-6: the list is re-rendered out of band: no card, right first/last flags, empty text."""
    _client, _sessions, app = env
    wishlist_id, (first, second, third) = seed_list(
        app, [Wish("Alpha", 5), Wish("Beta", 1), Wish("Gamma", 2)]
    )

    response = _post(env, wishlist_id, first, "5")

    assert response.status_code == 201, response.text
    soup = parse(response.text)
    assert_all_top_level_oob(soup, response.text)
    items = oob_list(soup)
    assert items.select_one(f"#item-card-{first}") is None
    assert soup.find(id=f"item-card-{first}") is None, "removed card must not be emitted anywhere"
    up = items.select_one(f"#item-card-{second} .btn-move-up")
    down = items.select_one(f"#item-card-{second} .btn-move-down")
    assert up is not None and up.has_attr("disabled")
    assert down is not None and not down.has_attr("disabled")
    last_down = items.select_one(f"#item-card-{third} .btn-move-down")
    last_up = items.select_one(f"#item-card-{third} .btn-move-up")
    assert last_down is not None and last_down.has_attr("disabled")
    assert last_up is not None and not last_up.has_attr("disabled")
    assert "Получено: 5 из 5" in text_of(oob(soup, "gifted-items-section"))
    assert text_of(oob(soup, "list-notice")) == "Отмечено получено: 5 шт. («Alpha»)"

    _post(env, wishlist_id, second, "1")
    last = _post(env, wishlist_id, third, "2")
    assert last.status_code == 201, last.text
    emptied = oob_list(parse(last.text))
    assert "В этом списке желаний пока нет подарков." in text_of(emptied)
    assert emptied.select_one(".item-card") is None


def test_post_co_author_and_recipient_views(env: AppEnv) -> None:
    """UA-5, U-20: a co-author gets a gifter-view card, the wish recipient no booking markup."""
    _client, _sessions, app = env
    wishlist_id, (for_others, for_co_author) = seed_list(
        app,
        [Wish("For everybody", 4), Wish("For Carl", 4, recipient_user_id=CO_AUTHOR_ID)],
        members=(CO_AUTHOR,),
    )
    shown = run(domain(app).list_wish_items(wishlist_id=wishlist_id, actor=CO_AUTHOR))
    assert {item.id: item.is_recipient for item in shown} == {
        for_others: False,
        for_co_author: True,
    }

    gifter_view = _post(env, wishlist_id, for_others, "1", CO_AUTHOR_ID)
    assert gifter_view.status_code == 201, gifter_view.text
    card = oob(parse(gifter_view.text), f"item-card-{for_others}")
    assert card.select_one(".item-giver") is not None
    assert "Осталось 3 из 4" in text_of(card.select_one(".item-badges"))

    recipient_view = _post(env, wishlist_id, for_co_author, "1", CO_AUTHOR_ID)
    assert recipient_view.status_code == 201, recipient_view.text
    own = oob(parse(recipient_view.text), f"item-card-{for_co_author}")
    assert own.select_one(".item-giver") is None
    assert "Осталось 3 из 4" in text_of(own.select_one(".item-badges"))
    for word in ("Забронировано", "Доступно", "Свободно"):
        assert word not in text_of(own)


# --- POST: refusals -----------------------------------------------------------------------------


def _refusal_classes() -> list[tuple[str, str]]:
    """``(case id, exception class name)`` of every row of the JSON route's table."""
    return [
        ("quantity_invalid", "QuantityInvalidError"),
        ("above_remaining", "QuantityAboveRemainingError"),
        ("wish_archived", "WishArchivedError"),
        ("list_archived", "WishlistArchivedError"),
        ("list_deleted", "WishlistDeletedError"),
        ("nothing_remaining", "NothingRemainingError"),
        ("forbidden", "PermissionDeniedError"),
        ("item_not_found", "ItemNotFoundError"),
        ("list_not_found", "WishlistNotFoundError"),
    ]


def _json_row(class_name: str) -> tuple[int, str]:
    """HTTP status and reason of the JSON route for one exception class."""
    table = new_symbol("wishenka.web.routes.receipts", "_REFUSALS")
    for error_type, http_status, reason, _message in table:
        if error_type.__name__ == class_name:
            return int(http_status), str(reason)
    raise AssertionError(f"{class_name} is not in receipts._REFUSALS")


def _refusal_request(
    app: FastAPI, case: str, wishlist_id: int, item_id: int
) -> tuple[int, int, str, int]:
    """Prepare a refused POST; returns list id, item id, quantity text and user id."""
    service = domain(app)
    quantity, user_id, target_list, target_item = "1", OWNER_ID, wishlist_id, item_id
    if case == "quantity_invalid":
        quantity = "0"
    elif case == "above_remaining":
        quantity = "99"
    elif case == "wish_archived":
        run(service.archive_wish_item(wishlist_id, item_id, OWNER))
    elif case == "list_archived":
        run(service.archive_wishlist(wishlist_id, OWNER))
    elif case == "list_deleted":
        run(service.delete_wishlist(wishlist_id, OWNER))
    elif case == "nothing_remaining":
        receive(app, item_id, 10)
    elif case == "forbidden":
        user_id = GIFTER_ID
    elif case == "item_not_found":
        target_item = item_id + 1000
    else:
        target_list = wishlist_id + 1000
    return target_list, target_item, quantity, user_id


@pytest.mark.parametrize(("case", "class_name"), _refusal_classes(), ids=lambda v: str(v))
def test_post_refusals_by_reason(env: AppEnv, case: str, class_name: str) -> None:
    """U-8, DoD 3: status, marker, sentence and fragments per reason; no English, no booking."""
    _client, _sessions, app = env
    wishlist_id, item_id = seed_booked(app)
    status, reason = _json_row(class_name)
    target_list, target_item, quantity, user_id = _refusal_request(app, case, wishlist_id, item_id)
    table = new_symbol("wishenka.web.routes.receipts", "_REFUSALS")
    english = [message for _t, _s, _r, message in table]

    response = _post(env, target_list, target_item, quantity, user_id)

    assert response.status_code == status, response.text
    assert response.headers.get(REFUSAL_HEADER) == reason
    soup = parse(response.text)
    assert _sentence_of(soup) == SENTENCES[reason].format(n=10)
    for message in english:
        assert message not in response.text
    assert_no_booking_leak(response.text)
    assert item_received(db_path_of(app), item_id) == (100 if case == "nothing_remaining" else 90)
    assert_all_top_level_oob(soup, response.text)
    ids = {el.get("id") for el in top_level(soup)}
    if case == "above_remaining":
        assert f"item-card-{item_id}" in ids, "card with current data expected"
        dialog = oob(soup, "item-receipt-modal")
        assert dialog.get("hx-swap-oob") == "outerHTML"
        assert [o.get("value") for o in dialog.select("option")] == [str(n) for n in range(1, 11)]
        assert "Осталось: 10" in text_of(dialog)
    elif case == "nothing_remaining":
        assert oob_list(soup) is not None
        assert "gifted-items-section" in ids
        dialog = oob(soup, "item-receipt-modal")
        assert dialog.select_one("form") is None
        assert text_of(dialog.select_one("[data-modal-close]")) == "Закрыть"
    else:
        assert ids == {"receipt-feedback"}, f"unexpected fragments: {ids}"
        assert oob(soup, "receipt-feedback").get("hx-swap-oob") == "innerHTML"


@pytest.mark.parametrize("effect_error", [InventoryBusyError, PermissionDeniedError])
@pytest.mark.parametrize("case", ["above_remaining", "nothing_remaining"])
def test_post_refusal_effect_read_failure_degrades(
    env: AppEnv,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    effect_error: type[Exception],
) -> None:
    """Design: a failing effect read keeps status, header and sentence; no extra fragments."""
    _client, _sessions, app = env
    wishlist_id, item_id = seed_booked(app)
    target_list, target_item, quantity, user_id = _refusal_request(app, case, wishlist_id, item_id)
    calls = {"count": 0}

    def patched(original: Callable[..., Any]) -> Callable[..., Any]:
        async def execute(request: Any, action: Callable[..., Any]) -> Any:
            calls["count"] += 1
            if calls["count"] == 1:
                return await original(request, action)
            raise effect_error()

        return execute

    _patch_execute(monkeypatch, patched)
    reason = "quantity_above_remaining" if case == "above_remaining" else "nothing_remaining"

    response = _post(env, target_list, target_item, quantity, user_id)

    assert response.status_code == 409, response.text
    assert response.headers.get(REFUSAL_HEADER) == reason
    assert calls["count"] >= 2, "the refusal effect must be read in a second action"
    soup = parse(response.text)
    assert _sentence_of(soup) == SENTENCES[reason].format(n=10)
    ids = {el.get("id") for el in top_level(soup)}
    assert ids == {"receipt-feedback"}, f"degraded response must be the plain sentence: {ids}"
    assert not [e for e in top_level(soup) if e.get("hx-swap-oob") == "innerHTML:#items-list"]


@pytest.mark.parametrize("value", ["abc", "", "0", "-1", "3.0"])
def test_post_non_integer_quantity_is_quantity_invalid(env: AppEnv, value: str) -> None:
    """U-8: a bad quantity text is the closed ``quantity_invalid`` refusal, never a 422."""
    _client, _sessions, app = env
    wishlist_id, (item_id, *_rest) = seed_list(app)

    response = _post(env, wishlist_id, item_id, value)

    assert response.status_code == 400, response.text
    assert response.headers.get(REFUSAL_HEADER) == "quantity_invalid"
    assert text_of(oob(parse(response.text), "receipt-feedback")) == SENTENCES["quantity_invalid"]
    assert item_received(db_path_of(app), item_id) == 0


def test_post_busy_is_503_and_changes_nothing(env: AppEnv, monkeypatch: pytest.MonkeyPatch) -> None:
    """U-9: busy gives 503, the marker ``busy``, the neutral sentence; nothing is stored."""
    _client, _sessions, app = env
    wishlist_id, (item_id, *_rest) = seed_list(app)
    _patch_execute(monkeypatch, _busy_execute)

    response = _post(env, wishlist_id, item_id, "1")

    assert response.status_code == 503, response.text
    assert response.headers.get(REFUSAL_HEADER) == "busy"
    soup = parse(response.text)
    assert text_of(oob(soup, "receipt-feedback")) == SENTENCES["busy"]
    for word in ("занято", "занят"):
        assert word not in response.text.lower()
    assert item_received(db_path_of(app), item_id) == 0


def test_post_unauthenticated_and_csrf(env: AppEnv) -> None:
    """N-3: 401 without credentials, 403 for a cookie session without the CSRF header."""
    client, sessions, app = env
    wishlist_id, (item_id, *_rest) = seed_list(app)
    url = modal_url(wishlist_id, item_id)

    anonymous = client.post(url, data={"quantity": "1"})
    assert anonymous.status_code == 401, anonymous.text

    client.cookies.set("session_id", sessions.create_token(OWNER_ID, "Alice"))
    origin = {"Origin": "http://testserver", "HX-Request": "true"}
    refused = client.post(url, data={"quantity": "1"}, headers=origin)
    assert refused.status_code == 403, refused.text
    assert item_received(db_path_of(app), item_id) == 0
    csrf = client.get("/api/auth/csrf").json()["csrf_token"]
    accepted = client.post(url, data={"quantity": "1"}, headers={**origin, "X-CSRF-Token": csrf})
    assert accepted.status_code == 201, accepted.text
    assert item_received(db_path_of(app), item_id) == 1


# --- the shared refusal table -------------------------------------------------------------------


def test_ui_reason_table_matches_json_route() -> None:
    """Decision 3: every reason of ``receipts._REFUSALS`` (and busy) has a Russian UI sentence."""
    table = new_symbol("wishenka.web.routes.receipts", "_REFUSALS")
    sentences = attr_of(ui_module(), "_SENTENCES")
    reasons = {str(row[2]) for row in table} | {"busy"}
    missing = sorted(reasons - set(sentences))
    assert missing == [], f"reasons without a UI sentence: {missing}"
    for reason in reasons:
        text = str(sentences[reason])
        assert re.search(r"[А-Яа-яЁё]", text), f"{reason}: sentence is not Russian: {text!r}"
    english = {str(row[3]) for row in table}
    assert not english & {str(sentences[reason]) for reason in reasons}


# --- logging ------------------------------------------------------------------------------------


def _ui_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == _UI_LOGGER]


def _extras(record: logging.LogRecord) -> dict[str, Any]:
    return {k: v for k, v in record.__dict__.items() if k not in _STANDARD}


def test_ui_logging_once_per_outcome(
    env: AppEnv, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """N-7, DoD 16: one record per outcome on the UI logger, the 22 field set, nothing private."""
    _client, _sessions, app = env
    wishlist_id, item_id = seed_booked(app)
    caplog.set_level(logging.DEBUG)

    def step(label: str, send: Callable[[], Any], expected_status: int) -> list[logging.LogRecord]:
        caplog.clear()
        response = send()
        assert response.status_code == expected_status, f"{label}: {response.text}"
        return _ui_records(caplog)

    opened = step("open", lambda: _get(env, wishlist_id, item_id), 200)
    accepted = step("accepted", lambda: _post(env, wishlist_id, item_id, "7"), 201)
    above = step("above", lambda: _post(env, wishlist_id, item_id, "99"), 409)
    receive(app, item_id, 3)
    nothing = step("nothing", lambda: _post(env, wishlist_id, item_id, "1"), 409)
    stale_open = step("stale open", lambda: _get(env, wishlist_id, item_id), 409)
    _patch_execute(monkeypatch, _busy_execute)
    busy = step("busy", lambda: _post(env, wishlist_id, item_id, "1"), 503)

    expectations: list[tuple[str, list[logging.LogRecord], str, int, str | None]] = [
        ("open", opened, "ui_receipt_form_opened", logging.INFO, None),
        ("accepted", accepted, "receipt_recorded_http", logging.INFO, None),
        ("above", above, "receipt_refused", logging.WARNING, "quantity_above_remaining"),
        ("nothing", nothing, "receipt_refused", logging.WARNING, "nothing_remaining"),
        ("stale open", stale_open, "ui_receipt_form_refused", logging.WARNING, "nothing_remaining"),
        ("busy", busy, "receipt_inventory_busy", logging.WARNING, None),
    ]
    for label, records, event, level, reason in expectations:
        assert len(records) == 1, f"{label}: expected one UI record, got {len(records)}"
        record = records[0]
        assert getattr(record, "event", None) == event, label
        assert record.levelno == level, label
        extras = {k: v for k, v in _extras(record).items() if k != "event"}
        allowed = _ALLOWED_EXTRAS | ({"remaining_quantity"} if reason else set())
        assert set(extras) <= allowed, f"{label}: unexpected fields {sorted(set(extras) - allowed)}"
        assert {"wishlist_id", "item_id", "actor_id"} <= set(extras), label
        assert extras["wishlist_id"] == wishlist_id and extras["actor_id"] == OWNER_ID
        if reason:
            assert extras.get("reason") == reason, label
        if event in {"receipt_refused", "ui_receipt_form_refused"}:
            assert extras["http_status"] == 409
            assert "remaining_quantity" in extras
        else:
            assert "remaining_quantity" not in extras, label
        assert event in _ATTEMPT_EVENTS | {"ui_receipt_form_opened", "ui_receipt_form_refused"}
    assert getattr(above[0], "remaining_quantity", None) == 3
    assert getattr(nothing[0], "remaining_quantity", None) == 0

    blob = " ".join(
        f"{r.getMessage()} {_extras(r)}"
        for records in (opened, accepted, above, nothing, stale_open, busy)
        for r in records
    )
    for forbidden in ("operation", "user_id", "Kettle", "Greta", "Oleg", "Alice"):
        assert forbidden not in blob, f"{forbidden!r} logged: {blob}"
    assert re.search(r"(?<![\w])(7|99|37|41)(?!\d)", blob) is None, blob
    for mark in ("notification", "outbox", "push"):
        assert mark not in blob.lower()
    for sentence in (GENERIC_FAILURE, *SENTENCES.values()):
        assert sentence.split(" Осталось")[0] not in blob
