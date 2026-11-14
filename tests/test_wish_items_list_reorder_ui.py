"""Automated failing repro test suite for WISHENKA-15 vertical wish list UI.

Tests Telegram Mini App (TMA) and HTMX UI endpoints and templates for:
- Vertical wish list compact card anatomy and inline expansion drawer
- Manual priority ordering via directional Move Up/Down buttons and batch reorder
- Safe archiving confirmation modal and per-wishlist gifter warning preference
- Archived items collapsible section and one-tap restoration to active list tail
- Role-based access control (RBAC), XSS escaping, and Surprise Invariant enforcement
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from wishenka.auth.models import AuthenticatedUser
from wishenka.auth.session import SessionTokenService
from wishenka.config import Settings
from wishenka.items.models import ItemPriority
from wishenka.web.app import create_app
from wishenka.wishlists.models import WishlistRole
from wishenka.wishlists.schemas import WishItemGifterViewDTO
from wishenka.wishlists.service import WishlistService

pytestmark = pytest.mark.timeout(30)


def make_user(
    telegram_id: int,
    first_name: str,
    username: str | None = None,
) -> AuthenticatedUser:
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
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'wish_items_list_reorder_ui.db'}",
        secret_key="wish-items-list-reorder-ui-test-secret",
    )
    app = create_app(settings)
    sessions = SessionTokenService(settings.secret_key)
    with TestClient(app) as client:
        yield client, sessions, app


# ============================================================================
# 1. Vertical list compact summary and inline expanded card anatomy + XSS
# ============================================================================


def test_vertical_list_compact_and_inline_expanded_card_anatomy(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """Verify compact summary badges, inline details drawer, and share_wishlist XSS safety."""
    client, sessions, app = test_app
    service: WishlistService = app.state.domain_service
    alice = make_user(101, "Alice <script>alert('owner')</script>")
    alice_headers = auth_header(sessions, 101, "Alice") | {"HX-Request": "true"}

    async def seed() -> tuple[int, str, int, int]:
        wl = await service.create_wishlist(
            owner=alice,
            title='Holiday List <script>alert("title")</script>',
            description='Description <script>alert("desc")</script>',
        )
        await service.add_member(
            wishlist_id=wl.id,
            actor=alice,
            user_id=102,
            role=WishlistRole.MEMBER,
        )
        item_rich = await service.add_wish_item(
            wishlist_id=wl.id,
            actor=alice,
            title="Кофемашина DeLonghi",
            description="Цвет: серебристый\nДавление: 15 бар",
            link="https://www.ozon.ru/product/delonghi-111",
            image_url="https://cdn.ozon.ru/delonghi.jpg",
            store_name="Ozon",
            price=45000,
            currency="RUB",
            quantity=1,
            priority=ItemPriority.HIGH,
            category="Техника",
            recipient_user_id=102,
            recipient_name="Боб",
        )
        item_fallback = await service.add_wish_item(
            wishlist_id=wl.id,
            actor=alice,
            title="Набор хрустальных бокалов",
            description="Для белого вина",
            link=None,
            image_url=None,
            price=3500,
            currency="RUB",
            quantity=6,
            priority=ItemPriority.LOW,
            category="Дом",
        )
        return wl.id, str(wl.public_token), item_rich.id, item_fallback.id

    wl_id, public_token, item_rich_id, item_fallback_id = asyncio.run(seed())

    # 1. Owner views wishlist detail page
    resp = client.get(f"/web/wishlists/{wl_id}", headers=alice_headers)
    assert resp.status_code == 200
    html = resp.text

    # Compact summary structure and inline toggle attributes
    assert "item-card-summary" in html
    assert 'aria-expanded="false"' in html
    assert 'src="/static/wishlist.js"' in html
    assert "onclick" not in html
    static_js = client.get("/static/wishlist.js")
    assert static_js.status_code == 200
    assert "toggleWishCard" in static_js.text
    assert f'id="item-card-{item_rich_id}"' in html
    assert f'id="item-card-{item_fallback_id}"' in html

    # Thumbnail image and placeholder fallback
    assert "https://cdn.ozon.ru/delonghi.jpg" in html
    assert "item-thumbnail-placeholder" in html

    # Title, price, and compact metadata badges
    assert "item-title" in html
    assert "Кофемашина DeLonghi" in html
    assert "45000" in html
    assert "3500" in html
    assert "badge-category" in html
    assert "Техника" in html
    assert "Дом" in html
    assert "badge-priority-high" in html
    assert "badge-priority-low" in html
    assert "badge-quantity" in html
    assert "6" in html
    assert "badge-recipient" in html
    assert "Боб" in html
    assert "badge-store" in html
    assert "Ozon" in html

    # Inline details drawer (.item-card-details), external link safety, and editor controls
    assert "item-card-details" in html
    assert "Цвет: серебристый" in html
    assert "Давление: 15 бар" in html
    assert 'target="_blank"' in html
    assert 'rel="noopener noreferrer"' in html
    assert "data-no-toggle" in html
    assert "btn-move-up" in html
    assert "btn-move-down" in html
    assert "btn-archive-confirm" in html
    assert "item-drag-handle" in html

    # 2. Public share page escapes XSS in wishlist title, owner name, and description
    share_resp = client.get(f"/share/{public_token}")
    assert share_resp.status_code == 200
    share_html = share_resp.text
    assert '<script>alert("title")</script>' not in share_html
    assert "<script>alert('owner')</script>" not in share_html
    assert '<script>alert("desc")</script>' not in share_html
    assert "&lt;script&gt;" in share_html
    assert "item-card-summary" in share_html
    assert "item-card-details" in share_html


# ============================================================================
# 2. Manual reordering via Move Up / Move Down and batch reorder
# ============================================================================


def test_manual_reordering_move_up_down_and_batch_reorder(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """Verify Move Up/Down boundary states, HTMX move & batch reorder, and persistence."""
    client, sessions, app = test_app
    service: WishlistService = app.state.domain_service
    owner = make_user(101, "Alice")
    owner_headers = auth_header(sessions, 101, "Alice") | {"HX-Request": "true"}

    async def seed() -> tuple[int, str, int, int, int]:
        wl = await service.create_wishlist(owner=owner, title="Reorder Wishlist")
        item_a = await service.add_wish_item(wishlist_id=wl.id, actor=owner, title="Item Alpha")
        item_b = await service.add_wish_item(wishlist_id=wl.id, actor=owner, title="Item Beta")
        item_c = await service.add_wish_item(wishlist_id=wl.id, actor=owner, title="Item Gamma")
        return wl.id, str(wl.public_token), item_a.id, item_b.id, item_c.id

    wl_id, public_token, id_a, id_b, id_c = asyncio.run(seed())

    # 1. Verify initial order [A, B, C] and disabled boundary buttons
    initial_page = client.get(f"/web/wishlists/{wl_id}", headers=owner_headers)
    assert initial_page.status_code == 200
    init_html = initial_page.text
    assert init_html.index(f'id="item-card-{id_a}"') < init_html.index(f'id="item-card-{id_b}"')
    assert init_html.index(f'id="item-card-{id_b}"') < init_html.index(f'id="item-card-{id_c}"')
    assert "btn-move-up" in init_html
    assert "btn-move-down" in init_html
    assert "disabled" in init_html

    # 2. Move item C up -> [A, C, B]
    move_up_resp = client.post(
        f"/web/wishlists/{wl_id}/items/{id_c}/move?direction=up",
        headers=owner_headers,
    )
    assert move_up_resp.status_code == 200
    up_html = move_up_resp.text
    assert up_html.index(f'id="item-card-{id_a}"') < up_html.index(f'id="item-card-{id_c}"')
    assert up_html.index(f'id="item-card-{id_c}"') < up_html.index(f'id="item-card-{id_b}"')

    # 3. Move item A down -> [C, A, B]
    move_down_resp = client.post(
        f"/web/wishlists/{wl_id}/items/{id_a}/move?direction=down",
        headers=owner_headers,
    )
    assert move_down_resp.status_code == 200
    down_html = move_down_resp.text
    assert down_html.index(f'id="item-card-{id_c}"') < down_html.index(f'id="item-card-{id_a}"')
    assert down_html.index(f'id="item-card-{id_a}"') < down_html.index(f'id="item-card-{id_b}"')

    # 4. Batch reorder via POST /items/reorder -> [B, C, A]
    reorder_resp = client.post(
        f"/web/wishlists/{wl_id}/items/reorder",
        data={"item_ids": [str(id_b), str(id_c), str(id_a)]},
        headers=owner_headers,
    )
    assert reorder_resp.status_code == 200
    reorder_html = reorder_resp.text
    assert reorder_html.index(f'id="item-card-{id_b}"') < reorder_html.index(
        f'id="item-card-{id_c}"'
    )
    assert reorder_html.index(f'id="item-card-{id_c}"') < reorder_html.index(
        f'id="item-card-{id_a}"'
    )

    # 5. Verify custom order [B, C, A] persists on detail view and public share view
    detail_after = client.get(f"/web/wishlists/{wl_id}", headers=owner_headers)
    assert detail_after.status_code == 200
    assert detail_after.text.index(f'id="item-card-{id_b}"') < detail_after.text.index(
        f'id="item-card-{id_c}"'
    )
    assert detail_after.text.index(f'id="item-card-{id_c}"') < detail_after.text.index(
        f'id="item-card-{id_a}"'
    )

    share_after = client.get(f"/share/{public_token}")
    assert share_after.status_code == 200
    assert share_after.text.index(f'id="item-card-{id_b}"') < share_after.text.index(
        f'id="item-card-{id_c}"'
    )
    assert share_after.text.index(f'id="item-card-{id_c}"') < share_after.text.index(
        f'id="item-card-{id_a}"'
    )

    # 6. Invalid permutation (missing item ID) is rejected and does not corrupt order
    bad_reorder = client.post(
        f"/web/wishlists/{wl_id}/items/reorder",
        data={"item_ids": [str(id_b), str(id_c)]},
        headers=owner_headers,
    )
    assert bad_reorder.status_code in (400, 422)

    persisted_items = asyncio.run(service.list_wish_items(wishlist_id=wl_id, actor=owner))
    assert [it.id for it in persisted_items] == [id_b, id_c, id_a]


# ============================================================================
# 3. Safe archive confirmation modal and gifter warning preference
# ============================================================================


def test_safe_archive_confirmation_modal_and_gifter_warning_preference(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """Verify archive confirmation modal, gifter warning toggle, and Surprise Invariant."""
    client, sessions, app = test_app
    service: WishlistService = app.state.domain_service
    owner = make_user(101, "Alice")
    gifter = make_user(777, "SecretGifterBob", username="secret_bob_usr")
    owner_headers = auth_header(sessions, 101, "Alice") | {"HX-Request": "true"}

    async def seed() -> tuple[int, int, int, int]:
        wl = await service.create_wishlist(owner=owner, title="Safe Archive Wishlist")
        item_unreserved = await service.add_wish_item(
            wishlist_id=wl.id,
            actor=owner,
            title="Unreserved Book",
            quantity=1,
        )
        item_reserved_1 = await service.add_wish_item(
            wishlist_id=wl.id,
            actor=owner,
            title="Reserved Headphones",
            quantity=2,
        )
        item_reserved_2 = await service.add_wish_item(
            wishlist_id=wl.id,
            actor=owner,
            title="Reserved Smart Watch",
            quantity=1,
        )
        await service.create_reservation(item_id=item_reserved_1.id, user=gifter, quantity=1)
        await service.create_reservation(item_id=item_reserved_2.id, user=gifter, quantity=1)
        return wl.id, item_unreserved.id, item_reserved_1.id, item_reserved_2.id

    wl_id, unres_id, res1_id, res2_id = asyncio.run(seed())

    # 1. Unreserved item renders #item-archive-modal without #archive-gifter-warning
    confirm_unres = client.get(
        f"/web/wishlists/{wl_id}/items/{unres_id}/archive-confirm",
        headers=owner_headers,
    )
    assert confirm_unres.status_code == 200
    assert 'id="item-archive-modal"' in confirm_unres.text
    assert 'id="archive-gifter-warning"' not in confirm_unres.text
    assert 'name="warn_on_delete_reserved"' in confirm_unres.text

    # 2. Reserved item with warn_on_delete_reserved=True renders #archive-gifter-warning
    #    while strictly protecting gifter identity (Surprise Invariant)
    confirm_res1 = client.get(
        f"/web/wishlists/{wl_id}/items/{res1_id}/archive-confirm",
        headers=owner_headers,
    )
    assert confirm_res1.status_code == 200
    res1_html = confirm_res1.text
    assert 'id="item-archive-modal"' in res1_html
    assert 'id="archive-gifter-warning"' in res1_html
    assert "SecretGifterBob" not in res1_html
    assert "secret_bob_usr" not in res1_html
    assert "777" not in res1_html

    # 3. Archiving item_reserved_1 with warn_on_delete_reserved=false persists preference
    archive_resp = client.post(
        f"/web/wishlists/{wl_id}/items/{res1_id}/archive",
        data={"warn_on_delete_reserved": "false"},
        headers=owner_headers,
    )
    assert archive_resp.status_code == 200

    # 4. Subsequent archive-confirm on another reserved item omits #archive-gifter-warning
    confirm_res2 = client.get(
        f"/web/wishlists/{wl_id}/items/{res2_id}/archive-confirm",
        headers=owner_headers,
    )
    assert confirm_res2.status_code == 200
    assert 'id="item-archive-modal"' in confirm_res2.text
    assert 'id="archive-gifter-warning"' not in confirm_res2.text


# ============================================================================
# 4. Archived items section and one-tap restoration
# ============================================================================


def test_archived_items_section_and_one_tap_restoration(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """Verify #archived-items-section OOB updates and one-tap restoration to active tail."""
    client, sessions, app = test_app
    service: WishlistService = app.state.domain_service
    owner = make_user(101, "Alice")
    member = make_user(102, "CollaboratorBob")
    gifter = make_user(303, "GifterDana")
    owner_headers = auth_header(sessions, 101, "Alice") | {"HX-Request": "true"}
    member_headers = auth_header(sessions, 102, "CollaboratorBob") | {"HX-Request": "true"}

    async def seed() -> tuple[int, int, int]:
        wl = await service.create_wishlist(owner=owner, title="Archive Section Wishlist")
        await service.add_member(
            wishlist_id=wl.id,
            actor=owner,
            user_id=member.telegram_id,
            role=WishlistRole.MEMBER,
        )
        item_first = await service.add_wish_item(
            wishlist_id=wl.id,
            actor=owner,
            title="Виниловый проигрыватель",
            quantity=2,
            price=18000,
        )
        item_second = await service.add_wish_item(
            wishlist_id=wl.id,
            actor=owner,
            title="Пластинка Pink Floyd",
            quantity=1,
            price=4500,
        )
        await service.create_reservation(item_id=item_first.id, user=gifter, quantity=1)
        return wl.id, item_first.id, item_second.id

    wl_id, item1_id, item2_id = asyncio.run(seed())

    # 1. Archive item_first and verify OOB removal + OOB #archived-items-section update
    arch_resp = client.post(
        f"/web/wishlists/{wl_id}/items/{item1_id}/archive",
        headers=owner_headers,
    )
    assert arch_resp.status_code == 200
    arch_html = arch_resp.text
    assert f'id="item-card-{item1_id}"' in arch_html
    assert "hx-swap-oob" in arch_html
    assert 'id="archived-items-section"' in arch_html
    assert (
        f'id="archived-item-{item1_id}"' in arch_html
        or f'id="archived-item-card-{item1_id}"' in arch_html
    )
    assert "Виниловый проигрыватель" in arch_html

    # 2. Both OWNER and MEMBER see #archived-items-section on GET /web/wishlists/{wl_id}
    for headers in (owner_headers, member_headers):
        page_resp = client.get(f"/web/wishlists/{wl_id}", headers=headers)
        assert page_resp.status_code == 200
        assert 'id="archived-items-section"' in page_resp.text
        assert "Виниловый проигрыватель" in page_resp.text
        assert f"/web/wishlists/{wl_id}/items/{item1_id}/restore" in page_resp.text

    # 3. Restore item_first via POST /restore -> appended to tail of active list (after item_second)
    restore_resp = client.post(
        f"/web/wishlists/{wl_id}/items/{item1_id}/restore",
        headers=member_headers,
    )
    assert restore_resp.status_code == 200
    restore_html = restore_resp.text
    assert f'id="item-card-{item1_id}"' in restore_html
    assert 'id="archived-items-section"' in restore_html
    assert "hx-swap-oob" in restore_html

    # Verify item_first is now active at the tail of display_order (after item_second)
    # and its gifter reservation remains intact
    active_items = asyncio.run(service.list_wish_items(wishlist_id=wl_id, actor=owner))
    assert [it.id for it in active_items] == [item2_id, item1_id]

    gifter_view = asyncio.run(
        service.get_wish_item(wishlist_id=wl_id, item_id=item1_id, actor=gifter)
    )
    assert isinstance(gifter_view, WishItemGifterViewDTO)
    assert gifter_view.is_archived is False
    assert gifter_view.my_reserved_quantity == 1


# ============================================================================
# 5. RBAC isolation and archived wishlist conflict (409)
# ============================================================================


def test_rbac_and_surprise_invariant_on_reorder_and_archive(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """Verify RBAC 404 for non-members, guest view isolation, and 409 on archived wishlist."""
    client, sessions, app = test_app
    service: WishlistService = app.state.domain_service
    owner = make_user(101, "Alice")
    secret_gifter = make_user(777, "SecretGifterBob", username="secret_bob")
    owner_headers = auth_header(sessions, 101, "Alice") | {"HX-Request": "true"}
    stranger_headers = auth_header(sessions, 999, "StrangerGuest") | {"HX-Request": "true"}

    async def seed() -> tuple[int, str, int, int, int]:
        wl = await service.create_wishlist(owner=owner, title="RBAC Wishlist")
        item1 = await service.add_wish_item(wishlist_id=wl.id, actor=owner, title="First Wish")
        item2 = await service.add_wish_item(wishlist_id=wl.id, actor=owner, title="Second Wish")
        item_arch = await service.add_wish_item(
            wishlist_id=wl.id,
            actor=owner,
            title="Secret Archived Wish",
        )
        await service.create_reservation(item_id=item1.id, user=secret_gifter, quantity=1)
        await service.archive_wish_item(wishlist_id=wl.id, item_id=item_arch.id, actor=owner)
        await service.reorder_wish_items(
            wishlist_id=wl.id,
            actor=owner,
            item_ids=[item2.id, item1.id],
        )
        return wl.id, str(wl.public_token), item1.id, item2.id, item_arch.id

    wl_id, public_token, item1_id, item2_id, _arch_id = asyncio.run(seed())

    # 0. Owner detail view respects Surprise Invariant (never exposes gifter identity or count)
    owner_page = client.get(f"/web/wishlists/{wl_id}", headers=owner_headers)
    assert owner_page.status_code == 200
    assert "SecretGifterBob" not in owner_page.text
    assert "secret_bob" not in owner_page.text
    assert "777" not in owner_page.text

    # 1. Authenticated non-member (stranger) gets 404 on move, reorder, and archive-confirm
    assert (
        client.post(
            f"/web/wishlists/{wl_id}/items/{item1_id}/move?direction=up",
            headers=stranger_headers,
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/web/wishlists/{wl_id}/items/reorder",
            data={"item_ids": [str(item1_id), str(item2_id)]},
            headers=stranger_headers,
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/web/wishlists/{wl_id}/items/{item1_id}/archive-confirm",
            headers=stranger_headers,
        ).status_code
        == 404
    )

    # 2. Public share view shows custom order and inline expansion, but hides editor controls
    #    and archived items section
    share_resp = client.get(f"/share/{public_token}", headers=stranger_headers)
    assert share_resp.status_code == 200
    share_html = share_resp.text
    assert share_html.index(f'id="item-card-{item2_id}"') < share_html.index(
        f'id="item-card-{item1_id}"'
    )
    assert "item-card-summary" in share_html
    assert "item-card-details" in share_html
    assert 'id="archived-items-section"' not in share_html
    assert "Secret Archived Wish" not in share_html
    assert "btn-move-up" not in share_html
    assert "btn-move-down" not in share_html
    assert "item-drag-handle" not in share_html
    assert "btn-archive-confirm" not in share_html

    # 3. Archiving the wishlist blocks move, reorder, and archive-confirm with 409 Conflict
    asyncio.run(service.archive_wishlist(wishlist_id=wl_id, actor=owner))

    assert (
        client.post(
            f"/web/wishlists/{wl_id}/items/{item1_id}/move?direction=up",
            headers=owner_headers,
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/web/wishlists/{wl_id}/items/reorder",
            data={"item_ids": [str(item1_id), str(item2_id)]},
            headers=owner_headers,
        ).status_code
        == 409
    )
    assert (
        client.get(
            f"/web/wishlists/{wl_id}/items/{item1_id}/archive-confirm",
            headers=owner_headers,
        ).status_code
        == 409
    )
