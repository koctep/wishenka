"""Automated test suite for WISHENKA-14 TMA & HTMX UI endpoints and templates.

Tests Telegram Mini App (TMA) and HTMX UI endpoints and templates for:
- Quick Add Bar universal input preview (plain text, rich marketplace URL, anti-bot fallback)
- Quick Add form submission with HTMX out-of-band swaps and XSS escaping
- Detailed Add modal prepopulation from preview metadata
- Detailed Edit modal with Reduction Lock UI constraints and Surprise Invariant protection
- Detailed Edit submission with Reduction Lock enforcement (HTTP 409) and form state preservation
- Collaborative wishlist recipient targeting UI (`recipient_user_id` & `recipient_name`)
- Role-based access isolation for guests, anonymous users, and archived wishlists
- Safe item archive and restore lifecycle via HTMX UI
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from wishenka.auth.models import AuthenticatedUser
from wishenka.auth.session import SessionTokenService
from wishenka.config import Settings
from wishenka.items.models import InputType
from wishenka.items.schemas import ItemPreviewDTO
from wishenka.items.service import ItemPreviewService
from wishenka.web.app import create_app
from wishenka.wishlists.models import WishlistRole
from wishenka.wishlists.schemas import WishItemGifterViewDTO
from wishenka.wishlists.service import WishlistService

pytestmark = pytest.mark.timeout(30)


def make_user(telegram_id: int, first_name: str, username: str | None = None) -> AuthenticatedUser:
    """Create a test AuthenticatedUser instance."""
    return AuthenticatedUser(
        telegram_id=telegram_id,
        first_name=first_name,
        username=username,
        auth_method="session_token",
    )


def auth_header(
    sessions: SessionTokenService,
    user_id: int,
    name: str = "User",
) -> dict[str, str]:
    """Generate Authorization header with valid session bearer token."""
    return {"Authorization": f"Bearer {sessions.create_token(user_id, name)}"}


@pytest.fixture
def test_app(tmp_path: Path) -> Iterator[tuple[TestClient, SessionTokenService, FastAPI]]:
    """Initialize TestClient and SessionTokenService with an isolated SQLite database."""
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'wish_items_tma_ui.db'}",
        secret_key="wish-items-tma-ui-test-secret",
    )
    app = create_app(settings)
    sessions = SessionTokenService(settings.secret_key)
    with TestClient(app) as client:
        yield client, sessions, app


# ============================================================================
# Scenario 1: Plain text input in Quick Add Preview does not trigger URL card
# ============================================================================


def test_quick_add_preview_plain_text(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """POST /web/wishlists/{id}/items/preview with plain text returns empty preview."""
    client, sessions, app = test_app
    service: WishlistService = app.state.domain_service
    owner = make_user(101, "Alice")
    owner_headers = auth_header(sessions, 101, "Alice") | {"HX-Request": "true"}

    wl = asyncio.run(service.create_wishlist(owner=owner, title="Alice's Birthday"))

    # Typing plain text into Quick Add Bar preview endpoint does not render URL preview card
    preview_resp = client.post(
        f"/web/wishlists/{wl.id}/items/preview",
        data={"raw_input": "Настольная игра Catan"},
        headers=owner_headers,
    )
    assert preview_resp.status_code == 200
    assert "text/html" in preview_resp.headers["content-type"]
    assert "item-preview-card" not in preview_resp.text

    # Owner views main wishlist UI page and sees the Quick Add Bar
    page_resp = client.get(f"/web/wishlists/{wl.id}", headers=owner_headers)
    assert page_resp.status_code == 200
    assert "text/html" in page_resp.headers["content-type"]
    assert "quick-add-bar" in page_resp.text
    assert "quick-add-input" in page_resp.text


# ============================================================================
# Scenario 2: Marketplace URL input in Quick Add Preview returns rich card
# ============================================================================


def test_quick_add_preview_marketplace_url_success(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /web/wishlists/{id}/items/preview with marketplace URL renders rich preview card."""
    client, sessions, app = test_app
    service: WishlistService = app.state.domain_service
    owner = make_user(101, "Alice")
    owner_headers = auth_header(sessions, 101, "Alice") | {"HX-Request": "true"}

    wl = asyncio.run(service.create_wishlist(owner=owner, title="Tech Wishlist"))

    async def mock_fetch_preview(
        self: ItemPreviewService,
        raw_input: str,
        client: httpx.AsyncClient | None = None,
    ) -> ItemPreviewDTO:
        return ItemPreviewDTO(
            input_type=InputType.EXPLICIT_URL,
            url="https://www.ozon.ru/product/sony-wh-1000xm5-12345",
            title="Беспроводные наушники Sony WH-1000XM5",
            description="Наушники с шумоподавлением",
            image_url="https://cdn.ozon.ru/multimedia/sony-xm5.jpg",
            price=29990,
            currency="RUB",
            store_name="Ozon",
            is_fallback=False,
        )

    monkeypatch.setattr(ItemPreviewService, "fetch_preview", mock_fetch_preview)

    resp = client.post(
        f"/web/wishlists/{wl.id}/items/preview",
        data={"raw_input": "https://www.ozon.ru/product/sony-wh-1000xm5-12345?utm_source=share"},
        headers=owner_headers,
    )
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    html = resp.text
    assert "Беспроводные наушники Sony WH-1000XM5" in html
    assert "Ozon" in html
    assert "29990" in html or "29 990" in html
    assert "https://cdn.ozon.ru/multimedia/sony-xm5.jpg" in html
    assert "Подробнее" in html


# ============================================================================
# Scenario 3: Anti-bot / timeout on URL preview renders graceful fallback card
# ============================================================================


def test_quick_add_preview_anti_bot_fallback(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /web/wishlists/{id}/items/preview degrades gracefully on anti-bot block."""
    client, sessions, app = test_app
    service: WishlistService = app.state.domain_service
    owner = make_user(101, "Alice")
    owner_headers = auth_header(sessions, 101, "Alice") | {"HX-Request": "true"}

    wl = asyncio.run(service.create_wishlist(owner=owner, title="Fallback Wishlist"))

    async def mock_fetch_preview_fallback(
        self: ItemPreviewService,
        raw_input: str,
        client: httpx.AsyncClient | None = None,
    ) -> ItemPreviewDTO:
        return ItemPreviewDTO(
            input_type=InputType.EXPLICIT_URL,
            url="https://market.yandex.ru/product--coffee-machine/98765",
            title=None,
            store_name="Яндекс Маркет",
            is_fallback=True,
            fallback_reason="anti_bot_challenge",
        )

    monkeypatch.setattr(ItemPreviewService, "fetch_preview", mock_fetch_preview_fallback)

    resp = client.post(
        f"/web/wishlists/{wl.id}/items/preview",
        data={"raw_input": "https://market.yandex.ru/product--coffee-machine/98765"},
        headers=owner_headers,
    )
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    html = resp.text
    assert "Яндекс Маркет" in html
    assert "https://market.yandex.ru/product--coffee-machine/98765" in html
    # Fallback prompts user to enter a title or open details without 500 error
    assert any(phrase in html.lower() for phrase in ("название", "вручную", "подробнее", "title"))


# ============================================================================
# Scenario 4: Quick Add submit creates item, updates DOM with OOB swaps, escapes XSS
# ============================================================================


def test_quick_add_submit_success(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """POST /web/wishlists/{id}/items/quick creates item, updates DOM, and escapes XSS."""
    client, sessions, app = test_app
    service: WishlistService = app.state.domain_service
    owner = make_user(101, "Alice")
    owner_headers = auth_header(sessions, 101, "Alice") | {"HX-Request": "true"}

    wl = asyncio.run(service.create_wishlist(owner=owner, title="Quick Submit Wishlist"))

    # 1. Plain text quick add with XSS attempt in title
    xss_title = 'Кроссовки <script>alert("xss")</script>'
    resp = client.post(
        f"/web/wishlists/{wl.id}/items/quick",
        data={"raw_input": xss_title},
        headers=owner_headers,
    )
    assert resp.status_code in (200, 201)
    assert "text/html" in resp.headers["content-type"]
    html = resp.text
    assert "item-card-" in html
    # Verify XSS is escaped (no raw <script> tag in rendered card)
    assert '<script>alert("xss")</script>' not in html
    assert "&lt;script&gt;" in html
    # Verify HTMX Out-of-Band swaps clear input and preview container
    assert "hx-swap-oob" in html
    assert "quick-add-preview-target" in html
    assert "quick-add-input" in html

    # 2. Enriched quick add from preview fields
    resp_enriched = client.post(
        f"/web/wishlists/{wl.id}/items/quick",
        data={
            "raw_input": "https://ozon.ru/product/555",
            "title": "Кофемолка электрическая",
            "link": "https://ozon.ru/product/555",
            "price": "4500",
            "currency": "RUB",
            "image_url": "https://cdn.ozon.ru/grinder.jpg",
        },
        headers=owner_headers,
    )
    assert resp_enriched.status_code in (200, 201)
    assert "Кофемолка электрическая" in resp_enriched.text
    assert "4500" in resp_enriched.text

    # Verify both items were persisted in the database
    items = asyncio.run(service.list_wish_items(wishlist_id=wl.id, actor=owner))
    assert len(items) == 2
    assert items[1].title == "Кофемолка электрическая"
    assert items[1].price == 4500
    assert items[1].link == "https://ozon.ru/product/555"


# ============================================================================
# Scenario 5: Detailed Add Modal GET prepopulates fields from Quick Add / Preview
# ============================================================================


def test_detailed_add_modal_get_prepopulated(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """GET /web/wishlists/{id}/items/new renders creation modal prepopulated with preview params."""
    client, sessions, app = test_app
    service: WishlistService = app.state.domain_service
    owner = make_user(101, "Alice")
    owner_headers = auth_header(sessions, 101, "Alice") | {"HX-Request": "true"}

    wl = asyncio.run(service.create_wishlist(owner=owner, title="Prepopulated Modal List"))

    resp = client.get(
        f"/web/wishlists/{wl.id}/items/new",
        params={
            "title": "Набор винных бокалов",
            "link": "https://ozon.ru/product/glasses-777",
            "price": 3490,
            "currency": "RUB",
            "image_url": "https://cdn.ozon.ru/glasses.jpg",
        },
        headers=owner_headers,
    )
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    html = resp.text
    assert "Набор винных бокалов" in html
    assert "https://ozon.ru/product/glasses-777" in html
    assert "3490" in html
    assert "https://cdn.ozon.ru/glasses.jpg" in html
    assert 'min="1"' in html


# ============================================================================
# Scenario 6: Detailed Edit Modal GET renders Reduction Lock & Surprise Invariant
# ============================================================================


def test_detailed_edit_modal_get_reduction_lock(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """GET /web/wishlists/{id}/items/{item_id}/edit enforces min=locked_quantity and hides buyer."""
    client, sessions, app = test_app
    service: WishlistService = app.state.domain_service
    owner = make_user(101, "Alice")
    gifter = make_user(202, "SecretGifterBob")
    owner_headers = auth_header(sessions, 101, "Alice") | {"HX-Request": "true"}

    async def seed() -> tuple[int, int]:
        wl = await service.create_wishlist(owner=owner, title="Reduction Lock List")
        item = await service.add_wish_item(
            wishlist_id=wl.id,
            actor=owner,
            title="Хрустальные бокалы",
            quantity=5,
            price=6000,
        )
        await service.create_reservation(item_id=item.id, user=gifter, quantity=3)
        return wl.id, item.id

    wl_id, item_id = asyncio.run(seed())

    resp = client.get(
        f"/web/wishlists/{wl_id}/items/{item_id}/edit",
        headers=owner_headers,
    )
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    html = resp.text
    assert "Хрустальные бокалы" in html
    # Reduction lock sets minimum allowed quantity to 3
    assert 'min="3"' in html
    assert "Забронировано дарителями: 3 шт." in html or "3 шт." in html
    # Surprise Invariant: Gifter's name and Telegram ID must NEVER appear in HTML
    assert "SecretGifterBob" not in html
    assert "202" not in html


# ============================================================================
# Scenario 7: Detailed Edit POST enforces Reduction Lock (409) & saves valid edits
# ============================================================================


def test_detailed_edit_submit_reduction_lock_enforcement(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """POST /web/wishlists/{id}/items/{item_id}/edit rejects quantity < locked with 409."""
    client, sessions, app = test_app
    service: WishlistService = app.state.domain_service
    owner = make_user(101, "Alice")
    gifter = make_user(202, "Bob")
    owner_headers = auth_header(sessions, 101, "Alice") | {"HX-Request": "true"}

    async def seed() -> tuple[int, int]:
        wl = await service.create_wishlist(owner=owner, title="Edit Enforcement List")
        item = await service.add_wish_item(
            wishlist_id=wl.id,
            actor=owner,
            title="Сервиз чайный",
            quantity=5,
            price=5000,
        )
        await service.create_reservation(item_id=item.id, user=gifter, quantity=3)
        return wl.id, item.id

    wl_id, item_id = asyncio.run(seed())

    # 1. Attempt to reduce quantity to 2 (below locked_quantity=3) -> 409 Conflict
    resp_conflict = client.post(
        f"/web/wishlists/{wl_id}/items/{item_id}/edit",
        data={
            "title": "Сервиз чайный фарфоровый",
            "link": "https://ozon.ru/product/tea-set",
            "price": "5500",
            "currency": "RUB",
            "quantity": "2",
            "description": "Цвет: слоновая кость",
            "priority": "high",
        },
        headers=owner_headers,
    )
    assert resp_conflict.status_code == 409
    assert "text/html" in resp_conflict.headers["content-type"]
    conflict_html = resp_conflict.text
    # Preserves user-submitted fields so nothing is lost
    assert "Сервиз чайный фарфоровый" in conflict_html
    assert "Цвет: слоновая кость" in conflict_html
    assert any(
        word in conflict_html.lower() for word in ("забронирован", "нельзя", "меньше", "количеств")
    )

    # 2. Valid update with quantity=4 (>= locked_quantity=3) -> 200 OK
    resp_ok = client.post(
        f"/web/wishlists/{wl_id}/items/{item_id}/edit",
        data={
            "title": "Сервиз чайный фарфоровый",
            "link": "https://ozon.ru/product/tea-set",
            "price": "5500",
            "currency": "RUB",
            "quantity": "4",
            "description": "Цвет: слоновая кость",
            "priority": "high",
        },
        headers=owner_headers,
    )
    assert resp_ok.status_code == 200
    assert "text/html" in resp_ok.headers["content-type"]
    ok_html = resp_ok.text
    assert f"item-card-{item_id}" in ok_html
    assert "Сервиз чайный фарфоровый" in ok_html
    assert "item-modal-container" in ok_html
    assert "hx-swap-oob" in ok_html

    # Verify DB persistence
    updated_item = asyncio.run(
        service.get_wish_item(wishlist_id=wl_id, item_id=item_id, actor=owner)
    )
    assert updated_item.title == "Сервиз чайный фарфоровый"
    assert updated_item.quantity == 4
    assert updated_item.price == 5500


# ============================================================================
# Scenario 8: Collaborative wishlist recipient targeting UI
# ============================================================================


def test_collaborative_recipient_targeting_ui(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """Recipient targeting fields appear in collaborative wishlists and hide in personal ones."""
    client, sessions, app = test_app
    service: WishlistService = app.state.domain_service
    alice = make_user(101, "Alice")
    alice_headers = auth_header(sessions, 101, "Alice") | {"HX-Request": "true"}

    async def seed() -> tuple[int, int, int]:
        personal_wl = await service.create_wishlist(owner=alice, title="Personal List")
        collab_wl = await service.create_wishlist(owner=alice, title="Family Holidays")
        await service.add_member(
            wishlist_id=collab_wl.id,
            actor=alice,
            user_id=102,
            role=WishlistRole.MEMBER,
        )
        collab_item = await service.add_wish_item(
            wishlist_id=collab_wl.id,
            actor=alice,
            title="Семейный плед",
            quantity=1,
        )
        return personal_wl.id, collab_wl.id, collab_item.id

    personal_wl_id, collab_wl_id, collab_item_id = asyncio.run(seed())

    # 1. Personal wishlist modal hides recipient selector
    resp_personal = client.get(
        f"/web/wishlists/{personal_wl_id}/items/new",
        headers=alice_headers,
    )
    assert resp_personal.status_code == 200
    assert 'name="recipient_user_id"' not in resp_personal.text

    # 2. Collaborative wishlist modal renders recipient selector with members and external name
    resp_collab = client.get(
        f"/web/wishlists/{collab_wl_id}/items/{collab_item_id}/edit",
        headers=alice_headers,
    )
    assert resp_collab.status_code == 200
    collab_html = resp_collab.text
    assert 'name="recipient_user_id"' in collab_html
    assert 'name="recipient_name"' in collab_html
    assert "102" in collab_html

    # 3. Updating item with recipient_user_id=102 persists recipient assignment
    resp_assign = client.post(
        f"/web/wishlists/{collab_wl_id}/items/{collab_item_id}/edit",
        data={
            "title": "Подарок для Боба",
            "quantity": "1",
            "currency": "RUB",
            "priority": "medium",
            "recipient_user_id": "102",
        },
        headers=alice_headers,
    )
    assert resp_assign.status_code == 200
    updated = asyncio.run(
        service.get_wish_item(wishlist_id=collab_wl_id, item_id=collab_item_id, actor=alice)
    )
    assert updated.recipient_user_id == 102


# ============================================================================
# Scenario 9: Guest, anonymous, and archived wishlist access denied to item UI
# ============================================================================


def test_guest_and_anonymous_access_denied_to_item_ui(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """Guests and anonymous users never see Quick Add Bar or edit buttons and cannot mutate UI."""
    client, sessions, app = test_app
    service: WishlistService = app.state.domain_service
    owner = make_user(101, "Alice")
    owner_headers = auth_header(sessions, 101, "Alice")
    guest_headers = auth_header(sessions, 999, "GuestStranger")

    async def seed() -> tuple[int, str, int]:
        wl = await service.create_wishlist(owner=owner, title="Protected Wishlist")
        item = await service.add_wish_item(
            wishlist_id=wl.id,
            actor=owner,
            title="Protected Item",
            quantity=2,
        )
        return wl.id, str(wl.public_token), item.id

    wl_id, public_token, item_id = asyncio.run(seed())

    # 1. Owner views main wishlist UI page and sees Quick Add Bar and edit button
    owner_page = client.get(f"/web/wishlists/{wl_id}", headers=owner_headers)
    assert owner_page.status_code == 200
    assert "quick-add-bar" in owner_page.text
    assert f"/web/wishlists/{wl_id}/items/{item_id}/edit" in owner_page.text

    # 2. Public share page for anonymous and guest users does NOT show Quick Add Bar or edit UI
    for headers in ({}, guest_headers):
        share_resp = client.get(f"/share/{public_token}", headers=headers)
        assert share_resp.status_code == 200
        assert "quick-add-bar" not in share_resp.text
        assert f"/web/wishlists/{wl_id}/items/{item_id}/edit" not in share_resp.text

    # 3. Guest and anonymous users are denied access to all item UI endpoints
    for headers in ({}, guest_headers):
        assert client.post(
            f"/web/wishlists/{wl_id}/items/preview",
            data={"raw_input": "Test"},
            headers=headers,
        ).status_code in (401, 403, 404)
        assert client.post(
            f"/web/wishlists/{wl_id}/items/quick",
            data={"raw_input": "Test"},
            headers=headers,
        ).status_code in (401, 403, 404)
        assert client.get(
            f"/web/wishlists/{wl_id}/items/new",
            headers=headers,
        ).status_code in (401, 403, 404)
        assert client.get(
            f"/web/wishlists/{wl_id}/items/{item_id}/edit",
            headers=headers,
        ).status_code in (401, 403, 404)
        assert client.post(
            f"/web/wishlists/{wl_id}/items/{item_id}/edit",
            data={"title": "Hacked", "quantity": "2", "currency": "RUB", "priority": "medium"},
            headers=headers,
        ).status_code in (401, 403, 404)
        assert client.post(
            f"/web/wishlists/{wl_id}/items/{item_id}/archive",
            headers=headers,
        ).status_code in (401, 403, 404)

    # 4. Archiving the wishlist hides Quick Add Bar even for owner and rejects mutations with 409
    asyncio.run(service.archive_wishlist(wishlist_id=wl_id, actor=owner))
    archived_page = client.get(f"/web/wishlists/{wl_id}", headers=owner_headers)
    assert archived_page.status_code == 200
    assert "quick-add-bar" not in archived_page.text

    assert (
        client.post(
            f"/web/wishlists/{wl_id}/items/quick",
            data={"raw_input": "New Item on Archived"},
            headers=owner_headers,
        ).status_code
        == 409
    )


# ============================================================================
# Scenario 10: Item archive and restore via HTMX UI preserves reservations
# ============================================================================


def test_item_archive_and_restore_via_ui(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """Archiving and restoring an item via HTMX UI updates DOM and preserves reservations."""
    client, sessions, app = test_app
    service: WishlistService = app.state.domain_service
    owner = make_user(101, "Alice")
    gifter = make_user(303, "Dana")
    owner_headers = auth_header(sessions, 101, "Alice") | {"HX-Request": "true"}

    async def seed() -> tuple[int, int]:
        wl = await service.create_wishlist(owner=owner, title="Archive UI List")
        item = await service.add_wish_item(
            wishlist_id=wl.id,
            actor=owner,
            title="Коллекционный винил",
            quantity=2,
            price=4200,
        )
        await service.create_reservation(item_id=item.id, user=gifter, quantity=1)
        return wl.id, item.id

    wl_id, item_id = asyncio.run(seed())

    # 1. Owner archives item via UI endpoint
    archive_resp = client.post(
        f"/web/wishlists/{wl_id}/items/{item_id}/archive",
        headers=owner_headers,
    )
    assert archive_resp.status_code == 200
    assert "text/html" in archive_resp.headers["content-type"]
    arch_html = archive_resp.text
    assert f'id="item-card-{item_id}"' in arch_html
    assert "hx-swap-oob" in arch_html
    assert "delete" in arch_html
    assert "item-modal-container" in arch_html

    # Verify item is archived in DB and gifter's reservation is preserved
    archived_view = asyncio.run(
        service.get_wish_item(wishlist_id=wl_id, item_id=item_id, actor=gifter)
    )
    assert isinstance(archived_view, WishItemGifterViewDTO)
    assert archived_view.is_archived is True
    assert archived_view.my_reserved_quantity == 1

    # 2. Owner restores item via UI endpoint
    restore_resp = client.post(
        f"/web/wishlists/{wl_id}/items/{item_id}/restore",
        headers=owner_headers,
    )
    assert restore_resp.status_code == 200
    assert "text/html" in restore_resp.headers["content-type"]
    restore_html = restore_resp.text
    assert f'id="item-card-{item_id}"' in restore_html
    assert "Коллекционный винил" in restore_html

    # Verify item is active again and reservation is still intact
    restored_view = asyncio.run(
        service.get_wish_item(wishlist_id=wl_id, item_id=item_id, actor=gifter)
    )
    assert isinstance(restored_view, WishItemGifterViewDTO)
    assert restored_view.is_archived is False
    assert restored_view.my_reserved_quantity == 1


# ============================================================================
# Scenario 11: Observability structured events and context attributes
# ============================================================================


def test_tma_ui_observability_events_and_attributes(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify structured logs and context attributes for all TMA item UI lifecycle events."""
    client, sessions, app = test_app
    service: WishlistService = app.state.domain_service
    owner = make_user(101, "Alice")
    gifter = make_user(202, "SecretBob")
    owner_headers = auth_header(sessions, 101, "Alice") | {"HX-Request": "true"}

    async def seed() -> int:
        wl = await service.create_wishlist(owner=owner, title="Observability List")
        await service.add_member(
            wishlist_id=wl.id,
            actor=owner,
            user_id=102,
            role=WishlistRole.MEMBER,
        )
        return wl.id

    wl_id = asyncio.run(seed())

    async def mock_fetch_preview(
        self: ItemPreviewService,
        raw_input: str,
        client: httpx.AsyncClient | None = None,
    ) -> ItemPreviewDTO:
        return ItemPreviewDTO(
            input_type=InputType.EXPLICIT_URL,
            url="https://www.ozon.ru/product/camera-999",
            title="Камера Fujifilm",
            price=85000,
            currency="RUB",
            store_name="Ozon",
            is_fallback=False,
        )

    monkeypatch.setattr(ItemPreviewService, "fetch_preview", mock_fetch_preview)

    with caplog.at_level(logging.INFO, logger="wishenka.web.items_ui"):
        # 1. Plain text preview
        assert (
            client.post(
                f"/web/wishlists/{wl_id}/items/preview",
                data={"raw_input": "Книга по архитектуре"},
                headers=owner_headers,
            ).status_code
            == 200
        )

        # 2. URL preview
        assert (
            client.post(
                f"/web/wishlists/{wl_id}/items/preview",
                data={"raw_input": "https://www.ozon.ru/product/camera-999"},
                headers=owner_headers,
            ).status_code
            == 200
        )

        # 3. Quick add submit
        quick_resp = client.post(
            f"/web/wishlists/{wl_id}/items/quick",
            data={
                "raw_input": "https://www.ozon.ru/product/camera-999",
                "title": "Камера Fujifilm",
                "link": "https://www.ozon.ru/product/camera-999",
                "price": "85000",
                "currency": "RUB",
                "quantity": "3",
            },
            headers=owner_headers,
        )
        assert quick_resp.status_code == 201

        items = asyncio.run(service.list_wish_items(wishlist_id=wl_id, actor=owner))
        item_id = items[0].id

        # Seed a reservation so Reduction Lock is active (locked_quantity = 2)
        asyncio.run(service.create_reservation(item_id=item_id, user=gifter, quantity=2))

        # 4. Open new item modal (mode="create")
        assert (
            client.get(
                f"/web/wishlists/{wl_id}/items/new",
                headers=owner_headers,
            ).status_code
            == 200
        )

        # 5. Open edit modal with active Reduction Lock (mode="edit")
        assert (
            client.get(
                f"/web/wishlists/{wl_id}/items/{item_id}/edit",
                headers=owner_headers,
            ).status_code
            == 200
        )

        # 6. Trigger Reduction Lock rejection (409)
        assert (
            client.post(
                f"/web/wishlists/{wl_id}/items/{item_id}/edit",
                data={
                    "title": "Камера Fujifilm X100V",
                    "quantity": "1",
                    "currency": "RUB",
                    "priority": "high",
                },
                headers=owner_headers,
            ).status_code
            == 409
        )

        # 7. Save valid edit with recipient targeting
        assert (
            client.post(
                f"/web/wishlists/{wl_id}/items/{item_id}/edit",
                data={
                    "title": "Камера Fujifilm X100V",
                    "quantity": "3",
                    "currency": "RUB",
                    "priority": "high",
                    "recipient_user_id": "102",
                },
                headers=owner_headers,
            ).status_code
            == 200
        )

        # 8. Archive and restore via UI
        assert (
            client.post(
                f"/web/wishlists/{wl_id}/items/{item_id}/archive",
                headers=owner_headers,
            ).status_code
            == 200
        )
        assert (
            client.post(
                f"/web/wishlists/{wl_id}/items/{item_id}/restore",
                headers=owner_headers,
            ).status_code
            == 200
        )

    events = [r for r in caplog.records if "event" in r.__dict__]
    by_event: dict[str, list[logging.LogRecord]] = {}
    for rec in events:
        by_event.setdefault(rec.__dict__["event"], []).append(rec)

    # Verify ui_item_quick_add_preview (plain text & URL)
    assert len(by_event.get("ui_item_quick_add_preview", [])) == 2
    plain_rec, url_rec = by_event["ui_item_quick_add_preview"]
    assert plain_rec.__dict__["wishlist_id"] == wl_id
    assert plain_rec.__dict__["actor_id"] == 101
    assert plain_rec.__dict__["input_type"] == InputType.PLAIN_TEXT.value
    assert plain_rec.__dict__["domain"] is None
    assert plain_rec.__dict__["is_fallback"] is False
    assert isinstance(plain_rec.__dict__["duration_ms"], float)

    assert url_rec.__dict__["wishlist_id"] == wl_id
    assert url_rec.__dict__["actor_id"] == 101
    assert url_rec.__dict__["input_type"] == InputType.EXPLICIT_URL.value
    assert url_rec.__dict__["domain"] == "ozon.ru"
    assert url_rec.__dict__["is_fallback"] is False
    assert isinstance(url_rec.__dict__["duration_ms"], float)

    # Verify ui_item_quick_add_success
    quick_rec = by_event["ui_item_quick_add_success"][0]
    assert quick_rec.__dict__["wishlist_id"] == wl_id
    assert quick_rec.__dict__["item_id"] == item_id
    assert quick_rec.__dict__["actor_id"] == 101
    assert quick_rec.__dict__["has_link"] is True

    # Verify ui_item_edit_opened (create & edit modes)
    assert len(by_event.get("ui_item_edit_opened", [])) == 2
    create_open_rec, edit_open_rec = by_event["ui_item_edit_opened"]
    assert create_open_rec.__dict__["wishlist_id"] == wl_id
    assert create_open_rec.__dict__["item_id"] is None
    assert create_open_rec.__dict__["actor_id"] == 101
    assert create_open_rec.__dict__["mode"] == "create"
    assert create_open_rec.__dict__["locked_quantity"] == 0

    assert edit_open_rec.__dict__["wishlist_id"] == wl_id
    assert edit_open_rec.__dict__["item_id"] == item_id
    assert edit_open_rec.__dict__["actor_id"] == 101
    assert edit_open_rec.__dict__["mode"] == "edit"
    assert edit_open_rec.__dict__["locked_quantity"] == 2

    # Verify ui_reduction_lock_rendered
    lock_render_rec = by_event["ui_reduction_lock_rendered"][0]
    assert lock_render_rec.__dict__["wishlist_id"] == wl_id
    assert lock_render_rec.__dict__["item_id"] == item_id
    assert lock_render_rec.__dict__["actor_id"] == 101
    assert lock_render_rec.__dict__["locked_quantity"] == 2

    # Verify ui_reduction_lock_rejected
    lock_reject_rec = by_event["ui_reduction_lock_rejected"][0]
    assert lock_reject_rec.levelno == logging.WARNING
    assert lock_reject_rec.__dict__["wishlist_id"] == wl_id
    assert lock_reject_rec.__dict__["item_id"] == item_id
    assert lock_reject_rec.__dict__["actor_id"] == 101
    assert lock_reject_rec.__dict__["requested_quantity"] == 1
    assert lock_reject_rec.__dict__["locked_quantity"] == 2

    # Verify ui_item_edit_saved
    saved_rec = by_event["ui_item_edit_saved"][0]
    assert saved_rec.__dict__["wishlist_id"] == wl_id
    assert saved_rec.__dict__["item_id"] == item_id
    assert saved_rec.__dict__["actor_id"] == 101
    assert saved_rec.__dict__["quantity"] == 3
    assert saved_rec.__dict__["has_recipient"] is True

    # Verify ui_item_archived & ui_item_restored
    arch_rec = by_event["ui_item_archived"][0]
    assert arch_rec.__dict__["wishlist_id"] == wl_id
    assert arch_rec.__dict__["item_id"] == item_id
    assert arch_rec.__dict__["actor_id"] == 101

    rest_rec = by_event["ui_item_restored"][0]
    assert rest_rec.__dict__["wishlist_id"] == wl_id
    assert rest_rec.__dict__["item_id"] == item_id
    assert rest_rec.__dict__["actor_id"] == 101


# ============================================================================
# Scenario 12: Observability privacy invariants (zero token/query/gifter leak)
# ============================================================================


def test_tma_ui_observability_privacy_invariants(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify UI logs never leak raw URLs with sensitive query params, tokens, or gifter info."""
    client, sessions, app = test_app
    service: WishlistService = app.state.domain_service
    owner = make_user(101, "Alice")
    gifter = make_user(777888, "SuperSecretGifterName")
    bearer_token = sessions.create_token(101, "Alice")
    owner_headers = {"Authorization": f"Bearer {bearer_token}", "HX-Request": "true"}

    async def seed() -> tuple[int, str, str]:
        wl = await service.create_wishlist(owner=owner, title="Privacy Audit List")
        return wl.id, str(wl.public_token), str(wl.invite_token)

    wl_id, public_token, invite_token = asyncio.run(seed())
    sensitive_url = (
        "https://market.yandex.ru/product--secret-gift/12345"
        "?partner_token=SECRET_QUERY_TOKEN_999&utm_campaign=private_campaign_xyz"
    )

    async def mock_fetch_preview(
        self: ItemPreviewService,
        raw_input: str,
        client: httpx.AsyncClient | None = None,
    ) -> ItemPreviewDTO:
        return ItemPreviewDTO(
            input_type=InputType.EXPLICIT_URL,
            url=sensitive_url,
            title="Секретный гаджет",
            price=12000,
            currency="RUB",
            store_name="Яндекс Маркет",
            is_fallback=False,
        )

    monkeypatch.setattr(ItemPreviewService, "fetch_preview", mock_fetch_preview)

    with caplog.at_level(logging.DEBUG, logger="wishenka"):
        client.post(
            f"/web/wishlists/{wl_id}/items/preview",
            data={"raw_input": sensitive_url},
            headers=owner_headers,
        )
        client.post(
            f"/web/wishlists/{wl_id}/items/quick",
            data={
                "raw_input": sensitive_url,
                "title": "Секретный гаджет",
                "link": sensitive_url,
                "price": "12000",
                "currency": "RUB",
                "quantity": "3",
            },
            headers=owner_headers,
        )
        items = asyncio.run(service.list_wish_items(wishlist_id=wl_id, actor=owner))
        item_id = items[0].id

        # Create gifter reservation outside UI log capture, then inspect UI logs for recipient
        asyncio.run(service.create_reservation(item_id=item_id, user=gifter, quantity=2))
        caplog.clear()

        client.get(f"/web/wishlists/{wl_id}/items/{item_id}/edit", headers=owner_headers)
        client.post(
            f"/web/wishlists/{wl_id}/items/{item_id}/edit",
            data={"title": "Секретный гаджет", "quantity": "1", "currency": "RUB"},
            headers=owner_headers,
        )
        client.post(
            f"/web/wishlists/{wl_id}/items/{item_id}/edit",
            data={"title": "Секретный гаджет", "quantity": "3", "currency": "RUB"},
            headers=owner_headers,
        )
        client.post(f"/web/wishlists/{wl_id}/items/{item_id}/archive", headers=owner_headers)
        client.post(f"/web/wishlists/{wl_id}/items/{item_id}/restore", headers=owner_headers)

    forbidden_substrings = (
        "SECRET_QUERY_TOKEN_999",
        "private_campaign_xyz",
        sensitive_url,
        public_token,
        invite_token,
        bearer_token,
        "wish-items-tma-ui-test-secret",
        "SuperSecretGifterName",
        "777888",
    )

    for record in caplog.records:
        serialized = f"{record.getMessage()} {record.__dict__}"
        for forbidden in forbidden_substrings:
            assert forbidden not in serialized, (
                f"Leaked sensitive value '{forbidden}' in log record: {serialized}"
            )
