"""Red tests for the received marker in the giver's cabinet (WISHENKA-24, plan T-5).

Covers U-17, U-18 and DoD 9: a promise on a wish the owner received shows the neutral marker, the
link to the wish is dropped, nothing about quantities or other givers is revealed. Today the
cabinet row has neither the marker nor a link rule.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from bs4 import Tag

from tests.receipt_support import (
    GIFTER_ID,
    OWNER,
    AppEnv,
    app_env,
    bearer,
)
from tests.receipt_ui_support import (
    CABINET_MARKER,
    Wish,
    domain,
    parse,
    receive,
    run,
    seed_list,
    text_of,
)

pytestmark = pytest.mark.timeout(30)

_CABINET = "/web/reservations"
_LIST = "/web/reservations/list"
_ACTION_LABELS = ("Изменить", "Отменить бронь", "Куплено", "Вернуть в бронь")


@pytest.fixture
def env(tmp_path: Path) -> Iterator[AppEnv]:
    """Open create_app on an isolated SQLite file with bearer sessions."""
    with app_env(tmp_path) as opened:
        yield opened


def _promise(env: AppEnv, wishlist_id: int, item_id: int, quantity: int) -> int:
    client, sessions, _app = env
    response = client.post(
        f"/api/wishlists/{wishlist_id}/items/{item_id}/reservations",
        json={"quantity": quantity},
        headers=bearer(sessions, GIFTER_ID, "Greta"),
    )
    assert response.status_code == 201, response.text
    return int(response.json()["reservation_id"])


def _act(env: AppEnv, wishlist_id: int, item_id: int, reservation_id: int, action: str) -> None:
    client, sessions, _app = env
    response = client.post(
        f"/api/wishlists/{wishlist_id}/items/{item_id}/reservations/{reservation_id}/{action}",
        headers=bearer(sessions, GIFTER_ID, "Greta"),
    )
    assert response.status_code == 200, response.text


def _rows(env: AppEnv, url: str = _CABINET) -> dict[str, Tag]:
    """Cabinet rows of the giver keyed by wish title."""
    client, sessions, _app = env
    response = client.get(url, headers=bearer(sessions, GIFTER_ID, "Greta"))
    assert response.status_code == 200, response.text
    soup = parse(response.text)
    return {
        text_of(row.select_one(".reservation-item")): row for row in soup.select(".reservation-row")
    }


def _marker(row: Tag) -> Tag | None:
    return row.select_one(".reservation-wish-received")


def _link(row: Tag) -> Tag | None:
    for anchor in row.select("a"):
        if text_of(anchor) == "К желанию":
            return anchor
    return None


@pytest.mark.parametrize("url", [_CABINET, _LIST])
def test_marker_for_fully_received_wish_with_actions_and_no_link(env: AppEnv, url: str) -> None:
    """U-17, U-18: marker, no link to the wish, actions of an active list stay."""
    _client, _sessions, app = env
    wishlist_id, (item_id, *_rest) = seed_list(app, [Wish("Kettle", 2)])
    _promise(env, wishlist_id, item_id, 2)
    receive(app, item_id, 2)

    row = _rows(env, url)["Kettle"]

    marker = _marker(row)
    assert marker is not None, "no received marker in the cabinet row"
    assert text_of(marker) == CABINET_MARKER
    assert _link(row) is None, "link to the wish must be dropped for a received wish"
    assert row.select_one("form[hx-patch]") is not None
    labels = {text_of(b) for b in row.select("button")}
    assert "Отменить бронь" in labels


def test_marker_and_bought_status_for_purchased_promise(env: AppEnv) -> None:
    """U-17: a purchased promise keeps «Куплено» and gets the marker, no internal status word."""
    _client, _sessions, app = env
    wishlist_id, (item_id, *_rest) = seed_list(app, [Wish("Kettle", 2)])
    reservation_id = _promise(env, wishlist_id, item_id, 2)
    _act(env, wishlist_id, item_id, reservation_id, "purchase")
    receive(app, item_id, 2)

    row = _rows(env)["Kettle"]

    marker = _marker(row)
    assert marker is not None and text_of(marker) == CABINET_MARKER
    assert text_of(row.select_one(".reservation-status")) == "Куплено"
    assert "completed" not in row.get_text().lower()
    assert _link(row) is None


def test_partly_received_wish_has_no_marker_and_keeps_link(env: AppEnv) -> None:
    """U-17: while units remain there is no marker and the link stays (positive control inside)."""
    _client, _sessions, app = env
    wishlist_id, (partly, full) = seed_list(app, [Wish("Kettle", 5), Wish("Mug", 1)])
    _promise(env, wishlist_id, partly, 2)
    _promise(env, wishlist_id, full, 1)
    receive(app, partly, 1)
    receive(app, full, 1)

    rows = _rows(env)

    assert _marker(rows["Mug"]) is not None, "positive control: fully received wish"
    assert _marker(rows["Kettle"]) is None
    link = _link(rows["Kettle"])
    assert link is not None
    assert link.get("href") == f"/web/wishlists/{wishlist_id}#item-card-{partly}"


def test_archived_list_shows_marker_without_actions(env: AppEnv) -> None:
    """U-17: on an archived list the marker stays, there are no action forms or buttons."""
    _client, _sessions, app = env
    wishlist_id, (item_id, *_rest) = seed_list(app, [Wish("Kettle", 2)])
    _promise(env, wishlist_id, item_id, 2)
    receive(app, item_id, 2)
    run(domain(app).archive_wishlist(wishlist_id, OWNER))

    row = _rows(env)["Kettle"]

    marker = _marker(row)
    assert marker is not None and text_of(marker) == CABINET_MARKER
    assert row.select_one(".reservation-list-archived") is not None
    assert row.select("form") == []
    labels = {text_of(b) for b in row.select("button")}
    assert not labels & set(_ACTION_LABELS), labels
    assert _link(row) is None


def test_closed_promise_has_no_row(env: AppEnv) -> None:
    """U-17: a cancelled promise is not listed, receipt or not (positive control inside)."""
    _client, _sessions, app = env
    wishlist_id, (kept, dropped) = seed_list(app, [Wish("Kettle", 2), Wish("Mug", 2)])
    _promise(env, wishlist_id, kept, 2)
    reservation_id = _promise(env, wishlist_id, dropped, 2)
    _act(env, wishlist_id, dropped, reservation_id, "cancel")
    receive(app, kept, 2)
    receive(app, dropped, 2)

    rows = _rows(env)

    assert set(rows) == {"Kettle"}
    assert _marker(rows["Kettle"]) is not None, "positive control: marker on the open promise"


def test_marker_text_is_neutral(env: AppEnv) -> None:
    """U-17, DoD 9: no digit, quantity word, excess or other-giver wording in the marker."""
    _client, _sessions, app = env
    wishlist_id, (item_id, *_rest) = seed_list(app, [Wish("Kettle", 5)])
    _promise(env, wishlist_id, item_id, 2)
    receive(app, item_id, 5)

    marker = _marker(_rows(env)["Kettle"])

    assert marker is not None
    text = text_of(marker)
    assert text == CABINET_MARKER
    assert re.search(r"\d", text) is None
    for word in ("шт", "остал", "получено:", "излиш", "друг", "больше", "сверх"):
        assert word not in text.lower(), word
