"""Failing repro tests for WISHENKA-209 (Create Item modal validation state preservation).

Covers:
1. ``GET /web/wishlists/{id}/items/new`` renders ``#item-detailed-form`` with
   ``hx-post="/web/wishlists/{id}/items/new"`` (isolated from ``/items/quick``).
2. ``POST /web/wishlists/{id}/items/new`` with form-level validation failures
   (non-numeric price, empty title) returns HTTP 400 with ``HX-Retarget: #item-modal-container``
   and ``HX-Reswap: innerHTML``, keeps the modal in create mode with ``.alert-error``,
   and preserves all submitted form fields without emitting ``#list-notice`` OOB.
3. ``POST /web/wishlists/{id}/items/new`` with domain validation failure (invalid URL
   scheme) returns HTTP 400 with ``HX-Retarget``/``HX-Reswap``, ``.alert-error``, and
   preserved form values.
4. ``POST /web/wishlists/{id}/items/new`` on a collaborative wishlist with invalid input
   preserves ``#recipient-user-select`` options, the selected ``recipient_user_id``,
   and ``recipient_name``.
5. ``POST /web/wishlists/{id}/items/quick`` with invalid input continues to return
   HTTP 400 with ``#list-notice`` OOB error and ``#item-modal-container`` OOB clear.

STEP 3: red on current production code; expected to pass after Step 4.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path

import pytest
from bs4 import BeautifulSoup, Tag

from tests.receipt_support import (
    CO_AUTHOR_ID,
    OWNER,
    OWNER_ID,
    AppEnv,
    app_env,
    bearer,
    db_path_of,
    seed_users,
    sql_exec,
)
from wishenka.wishlists.models import WishlistRole
from wishenka.wishlists.service import WishlistService

pytestmark = pytest.mark.timeout(30)


@pytest.fixture
def test_app(tmp_path: Path) -> Iterator[AppEnv]:
    """Provide an isolated application with a real SQLite store."""
    with app_env(tmp_path) as env:
        yield env


def _seed_personal_wishlist(env: AppEnv) -> int:
    _, _, app = env

    async def _create() -> int:
        async def action(svc: WishlistService) -> int:
            wl = await svc.create_wishlist(owner=OWNER, title="Personal Wishes")
            return wl.id

        return int(await app.state.wishlist_store.execute(action))

    return asyncio.run(_create())


def _seed_collaborative_wishlist(env: AppEnv) -> int:
    _, _, app = env
    db = db_path_of(app)
    seed_users(db, OWNER_ID, CO_AUTHOR_ID)

    async def _create() -> int:
        async def action(svc: WishlistService) -> int:
            wl = await svc.create_wishlist(owner=OWNER, title="Team Wishes")
            await svc.add_member(
                wishlist_id=wl.id,
                actor=OWNER,
                user_id=CO_AUTHOR_ID,
                role=WishlistRole.MEMBER,
            )
            return wl.id

        return int(await app.state.wishlist_store.execute(action))

    wishlist_id = asyncio.run(_create())
    sql_exec(db, "UPDATE wl_lists SET is_collaborative = 1 WHERE id = ?", (wishlist_id,))
    return wishlist_id


def _assert_modal_error_headers(headers: object) -> None:
    assert headers["hx-retarget"] == "#item-modal-container"  # type: ignore[index]
    assert headers["hx-reswap"] == "innerHTML"  # type: ignore[index]


def _selected_option_value(select_tag: Tag | None) -> str | None:
    if select_tag is None:
        return None
    for option in select_tag.find_all("option"):
        if option.has_attr("selected"):
            return str(option.get("value", ""))
    return None


def test_get_new_item_modal_posts_to_dedicated_new_endpoint(test_app: AppEnv) -> None:
    """Create Item modal must submit to POST /items/new rather than /items/quick."""
    client, sessions, _ = test_app
    wishlist_id = _seed_personal_wishlist(test_app)

    response = client.get(
        f"/web/wishlists/{wishlist_id}/items/new",
        headers=bearer(sessions, OWNER_ID),
    )

    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    form = soup.select_one("#item-detailed-form")
    assert form is not None
    assert form.get("hx-post") == f"/web/wishlists/{wishlist_id}/items/new"


@pytest.mark.parametrize(
    ("title", "price"),
    [
        ("Espresso Machine", "abc"),
        ("   ", "1500"),
    ],
)
def test_submit_new_item_form_validation_error_preserves_state_in_modal(
    test_app: AppEnv,
    title: str,
    price: str,
) -> None:
    """Form-level 400 errors on POST /items/new must re-render the create modal with state."""
    client, sessions, _ = test_app
    wishlist_id = _seed_personal_wishlist(test_app)

    payload = {
        "title": title,
        "link": "https://shop.example.com/espresso",
        "price": price,
        "currency": "EUR",
        "quantity": "3",
        "description": "Stainless steel boiler",
        "image_url": "https://cdn.example.com/espresso.jpg",
        "priority": "high",
        "category": "Kitchen",
    }

    response = client.post(
        f"/web/wishlists/{wishlist_id}/items/new",
        data=payload,
        headers=bearer(sessions, OWNER_ID),
    )

    assert response.status_code == 400
    _assert_modal_error_headers(response.headers)

    soup = BeautifulSoup(response.text, "html.parser")
    assert soup.select_one("#list-notice") is None
    assert soup.select_one("#item-edit-sheet") is not None

    alert = soup.select_one(".alert-error")
    assert alert is not None and alert.get_text(strip=True)

    form = soup.select_one("#item-detailed-form")
    assert form is not None
    assert form.get("hx-post") == f"/web/wishlists/{wishlist_id}/items/new"

    title_input = soup.select_one("#item-title-input")
    link_input = soup.select_one("#item-link-input")
    price_input = soup.select_one("#item-price-input")
    qty_input = soup.select_one("#item-quantity-input")
    desc_input = soup.select_one("#item-description-input")
    img_input = soup.select_one("#item-image-url-input")
    cat_input = soup.select_one("#item-category-input")

    assert title_input is not None and title_input.get("value") == title.strip()
    assert link_input is not None and link_input.get("value") == payload["link"]
    assert price_input is not None and price_input.get("value") == price
    assert qty_input is not None and qty_input.get("value") == "3"
    assert desc_input is not None and desc_input.get_text() == payload["description"]
    assert img_input is not None and img_input.get("value") == payload["image_url"]
    assert cat_input is not None and cat_input.get("value") == payload["category"]
    assert _selected_option_value(soup.select_one("#item-currency-select")) == "EUR"
    assert _selected_option_value(soup.select_one("#item-priority-select")) == "high"


def test_submit_new_item_domain_validation_error_preserves_state_in_modal(
    test_app: AppEnv,
) -> None:
    """Domain ValueError (e.g. non-member recipient_user_id) on POST /items/new keeps modal open."""
    client, sessions, _ = test_app
    wishlist_id = _seed_personal_wishlist(test_app)

    payload = {
        "title": "Mechanical Keyboard",
        "link": "https://shop.example.com/kb",
        "price": "120",
        "currency": "USD",
        "quantity": "2",
        "description": "Tactile switches",
        "image_url": "https://cdn.example.com/kb.png",
        "priority": "low",
        "category": "Tech",
        "recipient_user_id": "999999",
    }

    response = client.post(
        f"/web/wishlists/{wishlist_id}/items/new",
        data=payload,
        headers=bearer(sessions, OWNER_ID),
    )

    assert response.status_code == 400
    _assert_modal_error_headers(response.headers)

    soup = BeautifulSoup(response.text, "html.parser")
    assert soup.select_one("#list-notice") is None
    assert soup.select_one("#item-edit-sheet") is not None

    alert = soup.select_one(".alert-error")
    assert alert is not None and alert.get_text(strip=True)

    title_input = soup.select_one("#item-title-input")
    link_input = soup.select_one("#item-link-input")
    price_input = soup.select_one("#item-price-input")
    assert title_input is not None and title_input.get("value") == "Mechanical Keyboard"
    assert link_input is not None and link_input.get("value") == "https://shop.example.com/kb"
    assert price_input is not None and price_input.get("value") == "120"
    assert _selected_option_value(soup.select_one("#item-currency-select")) == "USD"
    assert _selected_option_value(soup.select_one("#item-priority-select")) == "low"


def test_submit_new_item_collaborative_error_preserves_recipient_options_and_selection(
    test_app: AppEnv,
) -> None:
    """Collaborative wishlist create modal 400 must keep recipient options and selection."""
    client, sessions, _ = test_app
    wishlist_id = _seed_collaborative_wishlist(test_app)

    payload = {
        "title": "Board Game",
        "price": "not-a-number",
        "currency": "RUB",
        "quantity": "1",
        "priority": "medium",
        "recipient_user_id": str(CO_AUTHOR_ID),
        "recipient_name": "Team Gift",
    }

    response = client.post(
        f"/web/wishlists/{wishlist_id}/items/new",
        data=payload,
        headers=bearer(sessions, OWNER_ID),
    )

    assert response.status_code == 400
    _assert_modal_error_headers(response.headers)

    soup = BeautifulSoup(response.text, "html.parser")
    recipient_select = soup.select_one("#recipient-user-select")
    assert recipient_select is not None
    option_values = [str(opt.get("value", "")) for opt in recipient_select.find_all("option")]
    assert str(OWNER_ID) in option_values
    assert str(CO_AUTHOR_ID) in option_values
    assert _selected_option_value(recipient_select) == str(CO_AUTHOR_ID)

    recipient_name_input = soup.select_one("#recipient-name-input")
    assert recipient_name_input is not None
    assert recipient_name_input.get("value") == "Team Gift"


def test_quick_add_validation_error_remains_oob_list_notice(test_app: AppEnv) -> None:
    """Inline Quick Add bar 400 must still return #list-notice OOB and clear modal."""
    client, sessions, _ = test_app
    wishlist_id = _seed_personal_wishlist(test_app)

    response = client.post(
        f"/web/wishlists/{wishlist_id}/items/quick",
        data={"raw_input": "   "},
        headers=bearer(sessions, OWNER_ID),
    )

    assert response.status_code == 400
    soup = BeautifulSoup(response.text, "html.parser")
    assert soup.select_one("#list-notice") is not None
    assert soup.select_one("#item-modal-container") is not None
    assert soup.select_one("#item-edit-sheet") is None
