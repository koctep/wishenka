"""Verification and regression tests for WISHENKA-63.

Verifies:
1. Anonymous `get_wishlist_by_public_token(..., current_user=None)` returns
   the giver view: shared remainder, `is_recipient` false, empty personal fields.
2. Anonymous `GET /share/{public_token}` shows the availability line and no
   book control.
3. `WishlistService()` and `WishlistService(store=None)` raise `ValueError`,
   while `WishlistService.in_memory()` constructs an isolated test instance.
4. The legacy public list omits the remainder. `/view` returns the giver
   projection for an anonymous caller, a recipient-safe view for the recipient,
   and the filled giver view for an identified gifter.
5. On a collaborative list, the item recipient never sees reservation data.
   An anonymous public-token lookup sees the shared remainder.
6. Structured observability logs record public projection modes without
   leaking public or invite capability tokens.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from wishenka.auth.models import AuthenticatedUser, TelegramUser
from wishenka.auth.session import SessionTokenService
from wishenka.config import Settings
from wishenka.users.store import UserStore
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


@asynccontextmanager
async def _stored(
    tmp_path: Path, filename: str, people: tuple[tuple[int, str], ...]
) -> AsyncIterator[WishlistService]:
    """Store-backed service with the people the shared rules may reference."""
    url = f"sqlite+aiosqlite:///{tmp_path / filename}"
    store = WishlistStore(url)
    users = UserStore(url)
    await store.initialize()
    try:
        for user_id, name in people:
            await users.upsert_user(TelegramUser(id=user_id, first_name=name))
        yield WishlistService(store=store)
    finally:
        await users.dispose()
        await store.dispose()


def test_public_token_anonymous_returns_recipient_dto(tmp_path: Path) -> None:
    """Anonymous public-token lookup returns the giver view with an empty promise."""
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
            assert isinstance(projected, WishItemGifterViewDTO)
            assert projected.is_recipient is False
            assert projected.available_quantity == 1
            assert projected.is_fully_reserved is False
            assert projected.is_reserved_by_me is False
            assert projected.my_reserved_quantity == 0
            assert projected.my_reservation_id is None
            assert projected.my_reservation_status is None
        finally:
            await store.dispose()

    asyncio.run(scenario())


def test_public_share_html_anonymous_hides_reservation_availability(tmp_path: Path) -> None:
    """Anonymous share shows the free remainder and offers no book control."""
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
        response = client.get(
            f"/share/{public_token}",
            headers={"Accept-Language": "ru"},
        )
        assert response.status_code == 200
        html = response.text
        assert "Board Game" in html
        assert "Доступно: 1 из 2" in html
        assert "Забронировать" not in html
        assert "Забронировано вами" not in html


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
        assert anon_item["is_recipient"] is False
        assert anon_item["available_quantity"] == 1
        assert anon_item["is_fully_reserved"] is False
        assert anon_item["is_reserved_by_me"] is False

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


def test_collaborative_recipient_and_admin_never_see_reservations(tmp_path: Path) -> None:
    """Owner, admin, and item recipient on collaborative list receive safe views."""
    owner = _make_user(101, "Alice")
    admin = _make_user(102, "Carol")
    gifter = _make_user(202, "Bob")

    async def scenario() -> None:
        async with _stored(
            tmp_path,
            "collab.db",
            ((101, "Alice"), (102, "Carol"), (202, "Bob")),
        ) as service:
            await _collaborative_views(service, owner, admin, gifter)

    asyncio.run(scenario())


async def _collaborative_views(
    service: WishlistService,
    owner: AuthenticatedUser,
    admin: AuthenticatedUser,
    gifter: AuthenticatedUser,
) -> None:
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

    anon_view = await service.get_wishlist_by_public_token(str(wl.public_token), None)
    anon_item = anon_view.items[0]
    assert isinstance(anon_item, WishItemGifterViewDTO)
    assert anon_item.is_recipient is False
    assert anon_item.available_quantity == 0
    assert anon_item.is_fully_reserved is True
    assert anon_item.is_reserved_by_me is False

    admin_auth_view = await service.get_wishlist_view(wl.id, admin)
    admin_pub_view = await service.get_wishlist_by_public_token(str(wl.public_token), admin)
    assert isinstance(admin_auth_view.items[0], WishItemRecipientViewDTO)
    assert isinstance(admin_pub_view.items[0], WishItemRecipientViewDTO)

    gifter_view = await service.get_wishlist_by_public_token(str(wl.public_token), gifter)
    assert isinstance(gifter_view.items[0], WishItemGifterViewDTO)
    assert gifter_view.items[0].available_quantity == 0
    assert gifter_view.items[0].is_fully_reserved is True


def test_public_projection_observability_logs_without_leaking_tokens(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify structured logs for public projection modes never leak public or invite tokens."""
    owner = _make_user(101, "Alice")
    gifter = _make_user(202, "Bob")
    missing_token = "missing-capability-token-999"

    async def scenario() -> tuple[str, str]:
        async with _stored(tmp_path, "projection.db", ((101, "Alice"), (202, "Bob"))) as service:
            return await _projection_tokens(service, owner, gifter, missing_token, caplog)

    pub_token, inv_token = asyncio.run(scenario())
    _assert_projection_logs(caplog, pub_token, inv_token, missing_token)


async def _projection_tokens(
    service: WishlistService,
    owner: AuthenticatedUser,
    gifter: AuthenticatedUser,
    missing_token: str,
    caplog: pytest.LogCaptureFixture,
) -> tuple[str, str]:
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


def _assert_projection_logs(
    caplog: pytest.LogCaptureFixture,
    pub_token: str,
    inv_token: str,
    missing_token: str,
) -> None:
    resolved_records = [
        r for r in caplog.records if getattr(r, "event", None) == "public_wishlist_resolved"
    ]
    assert [getattr(r, "projection_mode", None) for r in resolved_records] == [
        "anonymous_gifter",
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
