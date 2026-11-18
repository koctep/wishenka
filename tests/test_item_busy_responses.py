"""Regression coverage for retryable busy responses on item edits."""

import asyncio
from collections.abc import Iterator
from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from fastapi import FastAPI

from tests.receipt_support import (
    GIFTER,
    GIFTER_ID,
    OWNER_ID,
    AppEnv,
    app_env,
    bearer,
    seed_wish,
)
from wishenka.auth.models import TelegramUser
from wishenka.i18n.locale import SupportedLocale
from wishenka.wishlists.exceptions import InventoryBusyError
from wishenka.wishlists.service import WishlistService

pytestmark = pytest.mark.timeout(30)


@pytest.fixture
def test_app(tmp_path: Path) -> Iterator[AppEnv]:
    """Provide an isolated application with a real SQLite store."""
    with app_env(tmp_path) as env:
        yield env


def _seed(service: WishlistService) -> tuple[int, int]:
    async def create() -> tuple[int, int]:
        wishlist_id, item_id = await seed_wish(service, quantity=5, title="Original")
        await service.create_reservation(item_id=item_id, user=GIFTER, quantity=1)
        return wishlist_id, item_id

    return asyncio.run(create())


def _make_busy(monkeypatch: pytest.MonkeyPatch, app: FastAPI) -> None:
    async def busy(*_args: object, **_kwargs: object) -> None:
        raise InventoryBusyError()

    monkeypatch.setattr(app.state.wishlist_store, "execute_wish", busy)


def test_item_api_busy_response_hides_gifter(
    test_app: AppEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, sessions, app = test_app
    wishlist_id, item_id = _seed(app.state.domain_service)
    _make_busy(monkeypatch, app)

    response = client.patch(
        f"/api/wishlists/{wishlist_id}/items/{item_id}",
        json={"title": "Updated"},
        headers=bearer(sessions, OWNER_ID),
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "The wish was busy and the attempt changed nothing"}
    assert str(GIFTER_ID) not in response.text
    assert "gifter" not in response.text.lower()


def _set_owner_locale(app: FastAPI, locale: SupportedLocale) -> None:
    async def apply() -> None:
        await app.state.user_store.upsert_user(
            TelegramUser(id=OWNER_ID, first_name="Owner", language_code=locale)
        )
        await app.state.user_store.set_locale(OWNER_ID, locale)

    asyncio.run(apply())


@pytest.mark.parametrize(
    ("locale", "expected_alert"),
    [
        pytest.param(
            None,
            "The wish was busy, the edit was not saved, and it can be submitted again.",
            id="en-default",
        ),
        pytest.param(
            "ru",
            "Желание было занято, изменения не сохранены — попробуйте отправить снова.",
            id="ru",
        ),
    ],
)
def test_item_edit_busy_renders_submitted_fields(
    test_app: AppEnv,
    monkeypatch: pytest.MonkeyPatch,
    locale: SupportedLocale | None,
    expected_alert: str,
) -> None:
    client, sessions, app = test_app
    wishlist_id, item_id = _seed(app.state.domain_service)
    if locale is not None:
        _set_owner_locale(app, locale)
    _make_busy(monkeypatch, app)
    path = f"/web/wishlists/{wishlist_id}/items/{item_id}/edit"
    values = {
        "title": "A distinctive gift",
        "link": "https://example.com/gift",
        "price": "7654",
        "currency": "USD",
        "quantity": "4",
        "description": "Keep this description",
        "image_url": "https://example.com/image.png",
        "priority": "high",
        "category": "Books",
    }

    response = client.post(path, data=values, headers=bearer(sessions, OWNER_ID))

    assert response.status_code == 503
    assert "text/html" in response.headers["content-type"]
    soup = BeautifulSoup(response.text, "html.parser")
    assert soup.select_one("#item-edit-sheet") is not None
    form = soup.select_one("#item-detailed-form")
    assert form is not None and form.get("hx-post") == path
    alert = soup.select_one('[role="alert"]')
    assert alert is not None
    assert alert.get_text(strip=True) == expected_alert
    assert str(GIFTER_ID) not in response.text
    assert "gifter" not in response.text.lower()
    assert "дарител" not in alert.get_text(strip=True).lower()
    for name in ("title", "link", "price", "quantity", "image_url", "category"):
        field = form.select_one(f'[name="{name}"]')
        assert field is not None and field.get("value") == values[name]
    description = form.select_one('[name="description"]')
    assert description is not None and description.get_text(strip=True) == values["description"]
    for name in ("currency", "priority"):
        selected = form.select_one(f'[name="{name}"] option[selected]')
        assert selected is not None and selected.get("value") == values[name]

    persisted = client.get(
        f"/api/wishlists/{wishlist_id}/items/{item_id}", headers=bearer(sessions, OWNER_ID)
    )
    assert persisted.status_code == 200
    assert persisted.json()["title"] == "Original"
