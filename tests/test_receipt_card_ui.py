"""Red tests for the owner card, archive dialog and stale responses (WISHENKA-24, plan T-3).

Covers U-1, U-7, U-10, U-11, U-19 and U-21 at the markup level: owner badge and details, the
«Получено» button, the archive texts, the stale archive and restore bodies, the giver guard and
the stale reorder marker. Tests marked "guard" are green today by design and keep the existing
behaviour fixed; every other test is red until Step 4.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.receipt_support import (
    CO_AUTHOR,
    CO_AUTHOR_ID,
    GIFTER_ID,
    OWNER,
    OWNER_ID,
    AppEnv,
    app_env,
    db_path_of,
    sql_exec,
)
from tests.receipt_ui_support import (
    BOOKING_WORDS,
    NOTHING_REMAINING_TEXT,
    REFUSAL_HEADER,
    REORDER_HEADER,
    XSS_TITLE,
    Wish,
    assert_all_top_level_oob,
    assert_no_booking_leak,
    domain,
    hx,
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
)
from wishenka.wishlists.models import ReservationStatus
from wishenka.wishlists.schemas import WishItemGifterViewDTO

pytestmark = pytest.mark.timeout(30)

ARCHIVE_EXTRA = (
    "Архивируется только неполученная часть: полученные штуки останутся в разделе «Подаренные»."
)


@pytest.fixture
def env(tmp_path: Path) -> Iterator[AppEnv]:
    """Open create_app on an isolated SQLite file with bearer sessions."""
    with app_env(tmp_path) as opened:
        yield opened


def _page(env: AppEnv, wishlist_id: int, user_id: int | None = OWNER_ID) -> Any:
    client, sessions, _app = env
    headers = {} if user_id is None else hx(sessions, user_id)
    return client.get(f"/web/wishlists/{wishlist_id}", headers=headers)


def _web(wishlist_id: int, item_id: int, suffix: str) -> str:
    return f"/web/wishlists/{wishlist_id}/items/{item_id}/{suffix}"


# --- U-7: owner badge and details ---------------------------------------------------------------


def test_owner_badge_and_details_after_partial_receipt(env: AppEnv) -> None:
    """U-7: «Осталось 3 из 5» replaces ×5 for a member; three detail spans (page and card route)."""
    client, sessions, app = env
    wishlist_id, (item_id, *_rest) = seed_list(app, [Wish("Kettle", 5)])
    receive(app, item_id, 2)
    card_route = client.get(
        f"/wishlists/{wishlist_id}/items/{item_id}/card", headers=hx(sessions, OWNER_ID)
    )
    page = _page(env, wishlist_id)

    for label, response in (("page", page), ("card route", card_route)):
        assert response.status_code == 200, label
        card = parse(response.text).select_one(f"#item-card-{item_id}")
        assert card is not None, label
        badge = card.select_one(".item-badges .badge-quantity.badge-received")
        assert badge is not None, f"{label}: owner badge missing"
        assert text_of(badge) == "Осталось 3 из 5", label
        assert "×5" not in text_of(card.select_one(".item-badges")), label
        assert text_of(card.select_one(".item-quantity-requested")) == "Запрошено: 5", label
        assert text_of(card.select_one(".item-quantity-received")) == "Получено: 2", label
        assert text_of(card.select_one(".item-quantity-remaining")) == "Осталось: 3", label
        assert card.select_one(".item-quantity") is None, label


def test_card_without_receipts_is_unchanged(env: AppEnv) -> None:
    """Guard: green today. Nothing received keeps ×M and «Количество: M» (U-7 last sentence)."""
    _client, _sessions, app = env
    wishlist_id, (item_id, *_rest) = seed_list(app, [Wish("Kettle", 5)])

    card = parse(_page(env, wishlist_id).text).select_one(f"#item-card-{item_id}")

    assert card is not None
    assert text_of(card.select_one(".badge-quantity")) == "×5"
    assert card.select_one(".badge-received") is None
    assert text_of(card.select_one(".item-quantity")) == "Количество: 5"
    assert card.select_one(".item-quantity-requested") is None


def test_giver_and_share_viewers_keep_multiplier(env: AppEnv) -> None:
    """Guard: green today. U-21: giver, anonymous and share viewers never see «Осталось»."""
    client, sessions, app = env
    wishlist_id, (item_id, *_rest) = seed_list(app, [Wish("Kettle", 5)])
    receive(app, item_id, 2)
    token = str(run(domain(app).get_wishlist_by_id(wishlist_id)).public_token)
    views = {
        "giver page": _page(env, wishlist_id, GIFTER_ID),
        "anonymous page": _page(env, wishlist_id, None),
        "giver card": client.get(
            f"/wishlists/{wishlist_id}/items/{item_id}/card", headers=hx(sessions, GIFTER_ID)
        ),
        "share": client.get(f"/share/{token}"),
    }

    for label, response in views.items():
        assert response.status_code == 200, label
        card = parse(response.text).select_one(f"#item-card-{item_id}")
        assert card is not None, label
        assert text_of(card.select_one(".badge-quantity")) == "×5", label
        assert card.select_one(".badge-received") is None, label
        assert card.select_one(".item-quantity-received") is None, label
        assert "Осталось" not in text_of(card), label
        assert "Получено" not in text_of(card), label


def test_owner_card_has_no_booking_data(env: AppEnv) -> None:
    """U-7, U-20: with open promises the owner card shows received data only (page, card route)."""
    client, sessions, app = env
    wishlist_id, item_id = seed_booked(app)

    page = _page(env, wishlist_id)
    card_route = client.get(
        f"/wishlists/{wishlist_id}/items/{item_id}/card", headers=hx(sessions, OWNER_ID)
    )

    for label, response in (("page", page), ("card route", card_route)):
        assert response.status_code == 200, label
        card = parse(response.text).select_one(f"#item-card-{item_id}")
        assert card is not None, label
        badge = card.select_one(".item-badges .badge-received")
        assert badge is not None and text_of(badge) == "Осталось 10 из 100", f"{label}: {badge}"
        assert text_of(card.select_one(".item-quantity-received")) == "Получено: 90", label
        assert_no_booking_leak(text_of(card))
        assert_no_booking_leak(str(card), numbers=False)
        assert card.select_one(".item-giver") is None, label


def test_list_notice_region_for_members_only(env: AppEnv) -> None:
    """DoD 8, 14: members get an empty polite status region for notices; others get none."""
    _client, _sessions, app = env
    wishlist_id, _ids = seed_list(app, [Wish("Kettle", 5)])

    notice = parse(_page(env, wishlist_id).text).select_one("#list-notice")

    assert notice is not None, "no #list-notice region on the member page"
    assert notice.get("role") == "status" and notice.get("aria-live") == "polite"
    assert text_of(notice) == ""
    for user_id in (GIFTER_ID, None):
        soup = parse(_page(env, wishlist_id, user_id).text)
        assert soup.select_one("#list-notice") is None, f"user {user_id}"


# --- U-1: the receipt button --------------------------------------------------------------------


def test_receipt_button_for_members_on_active_list(env: AppEnv) -> None:
    """U-1: member cards carry the native «Получено» button with the dialog request."""
    _client, _sessions, app = env
    wishlist_id, (first, second) = seed_list(
        app, [Wish("Kettle", 5), Wish("Mug", 1)], members=(CO_AUTHOR,)
    )
    receive(app, first, 2)

    for user_id in (OWNER_ID, CO_AUTHOR_ID):
        soup = parse(_page(env, wishlist_id, user_id).text)
        for item_id in (first, second):
            button = soup.select_one(f"#item-card-{item_id} .item-actions .btn-receipt-item")
            assert button is not None, f"user {user_id}: no button on card {item_id}"
            assert button.name == "button" and button.get("type") == "button"
            assert text_of(button) == "Получено"
            assert button.get("hx-get") == _web(wishlist_id, item_id, "receipt")
            assert button.get("hx-target") == "#item-modal-container"
            assert button.get("hx-swap") == "innerHTML"
            assert button.has_attr("data-no-toggle")
            assert on_attributes(parse(str(button))) == []


def test_receipt_button_absent_for_giver_anonymous_share_and_archived_list(env: AppEnv) -> None:
    """U-1: no button for a giver, anonymous or share viewer, or on an archived list."""
    client, _sessions, app = env
    wishlist_id, _ids = seed_list(app, [Wish("Kettle", 5)])
    token = str(run(domain(app).get_wishlist_by_id(wishlist_id)).public_token)
    owner_page = parse(_page(env, wishlist_id).text)
    assert owner_page.select_one(".btn-receipt-item") is not None, "positive control: owner"

    for label, response in (
        ("giver", _page(env, wishlist_id, GIFTER_ID)),
        ("anonymous", _page(env, wishlist_id, None)),
        ("share", client.get(f"/share/{token}")),
    ):
        assert response.status_code == 200, label
        assert parse(response.text).select_one(".btn-receipt-item") is None, label

    run(domain(app).archive_wishlist(wishlist_id, OWNER))
    archived = _page(env, wishlist_id)
    assert archived.status_code == 200
    assert parse(archived.text).select_one(".btn-receipt-item") is None


# --- U-10: archive dialog, archive section, restore ----------------------------------------------


def test_archive_confirm_text_only_for_received_part(env: AppEnv) -> None:
    """U-10: the archive dialog explains that only the unreceived part is archived."""
    client, sessions, app = env
    wishlist_id, (partly, untouched) = seed_list(app, [Wish("Kettle", 5), Wish("Mug", 2)])
    receive(app, partly, 2)

    with_receipt = client.get(_web(wishlist_id, partly, "archive-confirm"), headers=hx(sessions))
    without = client.get(_web(wishlist_id, untouched, "archive-confirm"), headers=hx(sessions))

    assert with_receipt.status_code == 200 and without.status_code == 200
    assert ARCHIVE_EXTRA in text_of(parse(with_receipt.text))
    assert "Архивируется только неполученная часть" not in without.text


def test_restore_returns_remaining_and_leaves_gifted_data(env: AppEnv) -> None:
    """U-10, DoD 8: the restored card shows the remaining quantity; gifted data is unchanged."""
    client, sessions, app = env
    wishlist_id, (item_id, *_rest) = seed_list(app, [Wish("Kettle", 5)])
    receive(app, item_id, 2)
    run(domain(app).archive_wish_item(wishlist_id, item_id, OWNER))
    archived_page = parse(_page(env, wishlist_id).text)
    row = archived_page.select_one(f"#archived-item-{item_id} .archived-item-remaining")
    assert row is not None and text_of(row) == "Осталось 3"

    response = client.post(_web(wishlist_id, item_id, "restore"), headers=hx(sessions))

    assert response.status_code == 200, response.text
    soup = parse(response.text)
    card = soup.select_one(f"#item-card-{item_id}")
    assert card is not None
    assert "Осталось 3 из 5" in text_of(card.select_one(".item-badges"))
    assert soup.select_one("#gifted-items-section") is None
    after = parse(_page(env, wishlist_id).text)
    entry = after.select_one(f"#gifted-item-{item_id}")
    assert entry is not None and "Получено: 2 из 5" in text_of(entry)


@pytest.mark.parametrize("action", ["archive", "restore"])
def test_stale_archive_and_restore_of_received_wish_is_oob_409(env: AppEnv, action: str) -> None:
    """U-10: a stale archive or restore answers 409 with the marker and an OOB-only body."""
    client, sessions, app = env
    wishlist_id, (received_id, other_id) = seed_list(app, [Wish(XSS_TITLE, 2), Wish("Mug", 3)])
    receive(app, received_id, 2)
    if action == "restore":
        sql_exec(
            db_path_of(app), "UPDATE wl_items SET is_archived = 1 WHERE id = ?", (received_id,)
        )

    response = client.post(_web(wishlist_id, received_id, action), headers=hx(sessions))

    assert response.status_code == 409, response.text
    assert response.headers.get(REFUSAL_HEADER) == "nothing_remaining"
    soup = parse(response.text)
    assert_all_top_level_oob(soup, response.text)
    notice = oob(soup, "list-notice")
    assert notice.get("hx-swap-oob") == "innerHTML"
    assert text_of(notice) == NOTHING_REMAINING_TEXT
    assert oob(soup, "item-modal-container").get("hx-swap-oob") == "innerHTML"
    items = oob_list(soup)
    assert items.select_one(f"#item-card-{other_id}") is not None
    assert items.select_one(f"#item-card-{received_id}") is None
    assert oob(soup, "archived-items-section").get("hx-swap-oob") == "outerHTML"
    assert oob(soup, "gifted-items-section").get("hx-swap-oob") == "outerHTML"
    assert soup.find("script") is None
    assert XSS_TITLE not in response.text
    for word in BOOKING_WORDS:
        assert word not in response.text.lower(), word


# --- U-19: the giver guard ----------------------------------------------------------------------


def _giver_dto(**overrides: Any) -> WishItemGifterViewDTO:
    base: dict[str, Any] = {
        "id": 7,
        "title": "Kettle",
        "quantity": 2,
        "received_quantity": 2,
        "remaining_quantity": 0,
        "is_fully_received": True,
        "available_quantity": 1,
        "is_fully_reserved": False,
        "is_reserved_by_me": True,
        "my_reserved_quantity": 1,
        "my_reservation_id": 11,
        "my_reservation_status": ReservationStatus.ACTIVE,
        "my_latest_reservation_quantity": 1,
        "my_occupying_reservation_count": 1,
        "is_recipient": False,
    }
    return WishItemGifterViewDTO(**{**base, **overrides})


def test_giver_card_fully_received_has_no_booking_controls() -> None:
    """U-19: the giver card of a fully received wish renders no booking control (guard in P1)."""
    context: dict[str, Any] = {
        "wishlist_id": 3,
        "viewer_identified": True,
        "wishlist_active": True,
    }
    stale = parse(render_partial("partials/item_card.html", item=_giver_dto(), **context))
    labels = [text_of(el) for el in stale.select("button, input[type=submit]")]
    for label in ("Забронировать", "Изменить", "Отменить бронь", "Куплено", "Вернуть в бронь"):
        assert label not in labels, f"stale giver card still renders {label!r}: {labels}"
    assert [el.name for el in stale.find_all(True, attrs={"hx-post": True})] == []
    assert [el.name for el in stale.find_all(True, attrs={"hx-patch": True})] == []

    free = _giver_dto(is_reserved_by_me=False, my_reservation_id=None, my_reserved_quantity=0)
    unreserved = parse(render_partial("partials/item_card.html", item=free, **context))
    assert unreserved.select_one("form[hx-post]") is None
    assert "Забронировать" not in [text_of(el) for el in unreserved.select("button")]


# --- U-11: the stale reorder marker -------------------------------------------------------------


def test_stale_reorder_has_distinct_marker_header(env: AppEnv) -> None:
    """U-11: the reorder 400 keeps its JSON body, gets ``X-Reorder-Refusal``, no receipt marker."""
    client, sessions, app = env
    wishlist_id, (first, second, *_rest) = seed_list(
        app, [Wish("A", 1), Wish("B", 1), Wish("C", 1)]
    )

    response = client.post(
        f"/web/wishlists/{wishlist_id}/items/reorder",
        data={"item_ids": [str(second), str(first)]},
        headers=hx(sessions),
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid item order"}
    assert response.headers.get(REORDER_HEADER) == "stale_order"
    assert REFUSAL_HEADER not in response.headers
