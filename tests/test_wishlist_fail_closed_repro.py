"""Failing repro tests for WISHENKA-159: fail-closed wishlist context guards.

Verifies that wish item mutation operations fail closed with
``WishlistNotFoundError`` (and perform zero state mutations) when
``item.wishlist`` is ``None``.
"""

from __future__ import annotations

import pytest

from tests.receipt_support import place_item, place_wishlist
from wishenka.auth.models import AuthenticatedUser
from wishenka.wishlists.exceptions import WishlistNotFoundError
from wishenka.wishlists.models import WishItem
from wishenka.wishlists.service import WishlistService

pytestmark = pytest.mark.timeout(30)


def _make_user(telegram_id: int, first_name: str) -> AuthenticatedUser:
    """Create a test AuthenticatedUser instance."""
    return AuthenticatedUser(
        telegram_id=telegram_id,
        first_name=first_name,
        username=None,
        auth_method="session_token",
    )


async def _seed_detached_item(
    *,
    recipient_user_id: int | None = None,
    with_receipt: bool = False,
) -> tuple[WishlistService, WishItem, AuthenticatedUser, AuthenticatedUser]:
    """Create an in-memory service with a wish item whose ``wishlist`` is detached."""
    service = WishlistService.in_memory()
    owner = _make_user(1001, "Owner")
    stranger = _make_user(2002, "Stranger")

    wishlist = place_wishlist(service, owner, "Birthday")
    item = place_item(
        service,
        wishlist,
        "Original Gift",
        quantity=3,
        recipient_user_id=recipient_user_id,
    )
    if with_receipt:
        await service.record_item_fulfillment(item.id, owner, received_quantity=1)
        item.receipts[0].id = 1

    service._items[item.id].wishlist = None
    return service, item, owner, stranger


async def test_update_wish_item_fails_closed_when_wishlist_missing() -> None:
    """update_wish_item must raise WishlistNotFoundError and not mutate item."""
    service, item, _owner, stranger = await _seed_detached_item()

    with pytest.raises(WishlistNotFoundError):
        await service.update_wish_item(item.id, stranger, title="Hacked Title")

    assert item.title == "Original Gift"


async def test_create_reservation_fails_closed_when_wishlist_missing() -> None:
    """create_reservation must raise WishlistNotFoundError and not create a reservation."""
    service, item, owner, _stranger = await _seed_detached_item(recipient_user_id=1001)

    with pytest.raises(WishlistNotFoundError):
        await service.create_reservation(item.id, owner, quantity=1)

    assert item.reserved_quantity == 0
    assert service._reservations == {}


async def test_record_item_fulfillment_fails_closed_when_wishlist_missing() -> None:
    """record_item_fulfillment must raise WishlistNotFoundError and not record receipt."""
    service, item, _owner, stranger = await _seed_detached_item()

    with pytest.raises(WishlistNotFoundError):
        await service.record_item_fulfillment(item.id, stranger, received_quantity=1)

    assert item.received_quantity == 0
    assert item.receipts == []


async def test_cancel_item_receipt_fails_closed_when_wishlist_missing() -> None:
    """cancel_item_receipt must raise WishlistNotFoundError and keep receipt intact."""
    service, item, _owner, stranger = await _seed_detached_item(with_receipt=True)

    with pytest.raises(WishlistNotFoundError):
        await service.cancel_item_receipt(item.id, receipt_id=1, actor=stranger)

    assert item.received_quantity == 1
    assert len(item.receipts) == 1


async def test_correct_item_receipt_fails_closed_when_wishlist_missing() -> None:
    """correct_item_receipt must raise WishlistNotFoundError and keep receipt quantity."""
    service, item, _owner, stranger = await _seed_detached_item(with_receipt=True)

    with pytest.raises(WishlistNotFoundError):
        await service.correct_item_receipt(item.id, receipt_id=1, actor=stranger, new_quantity=2)

    assert item.received_quantity == 1
    assert item.receipts[0].quantity == 1
