"""Verification and regression tests for WISHENKA-63.

Verifies:
1. Anonymous `get_wishlist_by_public_token(..., current_user=None)` returns
   `WishItemRecipientViewDTO` without reservation availability fields.
2. Anonymous `GET /share/{public_token}` does not render reservation counts or
   availability status in the HTML.
3. `WishlistService()` and `WishlistService(store=None)` raise `ValueError`,
   while `WishlistService.in_memory()` constructs an isolated test instance.
4. Public JSON endpoints (`/api/public/wishlists/{token}` and
   `/api/public/wishlists/{token}/view`) enforce recipient-safe views for
   anonymous and recipient callers while preserving gifter views.
5. Collaborative wishlist owners, admins, and item recipients never see
   reservation data across authenticated or public-token lookups.
6. Structured observability logs record public projection modes without
   leaking public or invite capability tokens.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from wishenka.auth.models import AuthenticatedUser
from wishenka.auth.session import SessionTokenService
from wishenka.config import Settings
from wishenka.web.app import create_app
from wishenka.wishlists.exceptions import WishlistNotFoundError
from wishenka.wishlists.models import WishItemRecipientViewDTO, WishlistRole
from wishenka.wishlists.schemas import WishItemGifterViewDTO
from wishenka.wishlists.service import WishlistService
from wishenka.wishlists.store import WishlistStore

pytestmark = pytest.mark.timeout(30)


def _make_user(telegram_id: int, first_name: str) -> AuthenticatedUser:
    return AuthenticatedUser(
        telegram_id=telegram_id,
        first_name=first_name,
        username=None,
        auth_method="session_token",
    )


def test_public_token_anonymous_returns_recipient_dto(tmp_path: Path) -> None:
    """Anonymous get_wishlist_by_public_token must return WishItemRecipientViewDTO."""
    store = WishlistStore(f"sqlite+aiosqlite:///{tmp_path / 'repro_service.db'}")
    service = WishlistService(store=store)
    owner = _make_user(101, "Alice")
    gifter = _make_user(202, "Bob")

    async def scenario() -> None:
        await store.initialize()
        try:
            wl = await service.create_wishlist(owner=owner, title="Birthday")
            item = await service.add_wish_item(
                wishlist_id=wl.id,
                actor=owner,
                title="Headphones",
                quantity=2,
            )
            await service.create_reservation(item_id=item.id, user=gifter, quantity=1)

            view = await service.get_wishlist_by_public_token(
                str(wl.public_token),
                current_user=None,
            )
            assert len(view.items) == 1
            projected = view.items[0]
            assert isinstance(projected, WishItemRecipientViewDTO)
            assert projected.is_recipient is True
            assert not hasattr(projected, "available_quantity")
            assert not hasattr(projected, "is_fully_reserved")
        finally:
            await store.dispose()

    asyncio.run(scenario())


def test_public_share_html_anonymous_hides_reservation_availability(tmp_path: Path) -> None:
    """Anonymous GET /share/{public_token} must not disclose reservation availability."""
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'repro_share.db'}",
        secret_key="repro-share-secret",
    )
    app = create_app(settings)
    owner = _make_user(101, "Alice")
    gifter = _make_user(202, "Bob")

    with TestClient(app) as client:
        service: WishlistService = app.state.domain_service

        async def seed() -> str:
            wl = await service.create_wishlist(owner=owner, title="Birthday")
            item = await service.add_wish_item(
                wishlist_id=wl.id,
                actor=owner,
                title="Board Game",
                quantity=2,
            )
            await service.create_reservation(item_id=item.id, user=gifter, quantity=1)
            return str(wl.public_token)

        public_token = asyncio.run(seed())
        response = client.get(f"/share/{public_token}")
        assert response.status_code == 200
        html = response.text
        assert "Board Game" in html
        assert "giver-available" not in html
        assert "item-giver" not in html


def test_wishlist_service_requires_store_unless_in_memory(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """WishlistService() and WishlistService(store=None) must raise ValueError."""
    with caplog.at_level(logging.ERROR, logger="wishenka.wishlists"):
        with pytest.raises(ValueError, match="store"):
            WishlistService()

        with pytest.raises(ValueError, match="store"):
            WishlistService(store=None)

    error_records = [
        r for r in caplog.records if getattr(r, "event", None) == "wishlist_service_store_required"
    ]
    assert len(error_records) == 2

    caplog.clear()
    with caplog.at_level(logging.DEBUG, logger="wishenka.wishlists"):
        in_memory_service = WishlistService.in_memory()
    assert isinstance(in_memory_service, WishlistService)
    assert any(
        getattr(r, "event", None) == "wishlist_service_in_memory_created" for r in caplog.records
    )


def test_public_api_endpoints_anonymous_recipient_and_gifter_views(tmp_path: Path) -> None:
    """Verify anonymous, recipient, and gifter views on public JSON endpoints."""
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'repro_api_views.db'}",
        secret_key="repro-api-secret",
    )
    app = create_app(settings)
    sessions = SessionTokenService(settings.secret_key)
    owner = _make_user(101, "Alice")
    gifter = _make_user(202, "Bob")
    owner_headers = {"Authorization": f"Bearer {sessions.create_token(101, 'Alice')}"}
    gifter_headers = {"Authorization": f"Bearer {sessions.create_token(202, 'Bob')}"}

    with TestClient(app) as client:
        service: WishlistService = app.state.domain_service

        async def seed() -> str:
            wl = await service.create_wishlist(owner=owner, title="Birthday")
            item = await service.add_wish_item(
                wishlist_id=wl.id,
                actor=owner,
                title="Espresso Machine",
                quantity=2,
            )
            await service.create_reservation(item_id=item.id, user=gifter, quantity=1)
            return str(wl.public_token)

        token = asyncio.run(seed())

        # 1. Legacy public endpoint: /api/public/wishlists/{token}
        pub_resp = client.get(f"/api/public/wishlists/{token}")
        assert pub_resp.status_code == 200
        pub_data = pub_resp.json()
        assert "members" not in pub_data
        assert "share_token" not in pub_data
        assert "invite_token" not in pub_data
        assert len(pub_data["items"]) == 1
        pub_item = pub_data["items"][0]
        assert pub_item["title"] == "Espresso Machine"
        assert pub_item["remaining_quantity"] == 2
        assert pub_item["is_active"] is True
        assert "available_quantity" not in pub_item
        assert "is_fully_reserved" not in pub_item
        assert "is_reserved_by_me" not in pub_item

        # 2. Anonymous /api/public/wishlists/{token}/view
        anon_resp = client.get(f"/api/public/wishlists/{token}/view")
        assert anon_resp.status_code == 200
        anon_data = anon_resp.json()
        assert anon_data["identified"] is False
        assert len(anon_data["items"]) == 1
        anon_item = anon_data["items"][0]
        assert anon_item["is_recipient"] is True
        assert "available_quantity" not in anon_item
        assert "is_fully_reserved" not in anon_item

        # 3. Recipient /api/public/wishlists/{token}/view
        rec_resp = client.get(f"/api/public/wishlists/{token}/view", headers=owner_headers)
        assert rec_resp.status_code == 200
        rec_data = rec_resp.json()
        assert rec_data["identified"] is True
        rec_item = rec_data["items"][0]
        assert rec_item["is_recipient"] is True
        assert "available_quantity" not in rec_item
        assert "is_fully_reserved" not in rec_item

        # 4. Gifter /api/public/wishlists/{token}/view
        gift_resp = client.get(f"/api/public/wishlists/{token}/view", headers=gifter_headers)
        assert gift_resp.status_code == 200
        gift_data = gift_resp.json()
        assert gift_data["identified"] is True
        gift_item = gift_data["items"][0]
        assert gift_item["is_recipient"] is False
        assert gift_item["available_quantity"] == 1
        assert gift_item["my_reserved_quantity"] == 1


def test_collaborative_recipient_and_admin_never_see_reservations() -> None:
    """Owner, admin, and item recipient on collaborative list receive safe views."""
    service = WishlistService.in_memory()
    owner = _make_user(101, "Alice")
    admin = _make_user(102, "Carol")
    gifter = _make_user(202, "Bob")

    async def scenario() -> None:
        wl = await service.create_wishlist(
            owner=owner,
            title="Wedding",
        )
        await service.add_member(
            wishlist_id=wl.id,
            actor=owner,
            user_id=admin.telegram_id,
            role=WishlistRole.ADMIN,
        )

        item_for_admin = await service.add_wish_item(
            wishlist_id=wl.id,
            actor=admin,
            title="Toaster",
            quantity=1,
            recipient_user_id=admin.telegram_id,
        )
        await service.create_reservation(item_id=item_for_admin.id, user=gifter, quantity=1)

        # Anonymous public-token view
        anon_view = await service.get_wishlist_by_public_token(str(wl.public_token), None)
        assert isinstance(anon_view.items[0], WishItemRecipientViewDTO)

        # Item recipient (admin) via authenticated and public views
        admin_auth_view = await service.get_wishlist_view(wl.id, admin)
        admin_pub_view = await service.get_wishlist_by_public_token(str(wl.public_token), admin)
        assert isinstance(admin_auth_view.items[0], WishItemRecipientViewDTO)
        assert isinstance(admin_pub_view.items[0], WishItemRecipientViewDTO)

        # Non-recipient gifter sees GifterViewDTO
        gifter_view = await service.get_wishlist_by_public_token(str(wl.public_token), gifter)
        assert isinstance(gifter_view.items[0], WishItemGifterViewDTO)
        assert gifter_view.items[0].available_quantity == 0
        assert gifter_view.items[0].is_fully_reserved is True

    asyncio.run(scenario())


def test_public_projection_observability_logs_without_leaking_tokens(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify structured logs for public projection modes never leak public or invite tokens."""
    service = WishlistService.in_memory()
    owner = _make_user(101, "Alice")
    gifter = _make_user(202, "Bob")
    missing_token = "missing-capability-token-999"

    async def scenario() -> tuple[str, str]:
        wl = await service.create_wishlist(owner=owner, title="Anniversary")
        item = await service.add_wish_item(
            wishlist_id=wl.id,
            actor=owner,
            title="Watch",
            quantity=1,
        )
        await service.create_reservation(item_id=item.id, user=gifter, quantity=1)
        public_token = str(wl.public_token)
        invite_token = str(wl.invite_token)

        caplog.clear()
        with caplog.at_level(logging.INFO, logger="wishenka.wishlists"):
            await service.get_wishlist_by_public_token(public_token, None)
            await service.get_wishlist_by_public_token(public_token, owner)
            await service.get_wishlist_by_public_token(public_token, gifter)
            with pytest.raises(WishlistNotFoundError):
                await service.get_wishlist_by_public_token(missing_token, None)

        return public_token, invite_token

    pub_token, inv_token = asyncio.run(scenario())

    resolved_records = [
        r for r in caplog.records if getattr(r, "event", None) == "public_wishlist_resolved"
    ]
    assert [getattr(r, "projection_mode", None) for r in resolved_records] == [
        "anonymous_safe",
        "recipient_safe",
        "gifter",
    ]
    assert [getattr(r, "identified", None) for r in resolved_records] == [
        False,
        True,
        True,
    ]
    not_found_records = [
        r for r in caplog.records if getattr(r, "event", None) == "public_token_not_found"
    ]
    assert len(not_found_records) == 1
    assert not_found_records[0].levelno == logging.WARNING

    for record in caplog.records:
        for secret in (pub_token, inv_token, missing_token):
            assert secret not in record.getMessage()
            assert secret not in str(record.__dict__)
