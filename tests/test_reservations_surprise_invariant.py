"""Automated failing repro suite for WISHENKA-17.

Tests reservation lifecycle, surprise invariant, and concurrency.
"""

import asyncio

import pytest

from wishenka.auth.models import AuthenticatedUser
from wishenka.wishlists.exceptions import (
    CannotReduceQuantityBelowReservedError,
    InsufficientQuantityError,
    SelfReservationError,
)
from wishenka.wishlists.models import (
    ReservationStatus,
    WishlistMember,
    WishlistRole,
)
from wishenka.wishlists.schemas import (
    MyReservationItemDTO,
    UserReservationsSummaryDTO,
    WishItemGifterViewDTO,
    WishItemRecipientViewDTO,
)
from wishenka.wishlists.service import WishlistService

pytestmark = pytest.mark.timeout(10)


def make_user(telegram_id: int, first_name: str, username: str | None = None) -> AuthenticatedUser:
    """Create test AuthenticatedUser instance."""
    return AuthenticatedUser(
        telegram_id=telegram_id,
        first_name=first_name,
        username=username,
        auth_method="session_token",
    )


# ============================================================================
# 1. Surprise Invariant & Recipient Zero-Leak Projections
# ============================================================================


class TestSurpriseInvariantIntegrity:
    """Verify zero-leak projection to recipient and strict self-reservation guards."""

    async def test_recipient_view_has_no_reservation_attributes(self) -> None:
        """Surprise Invariant: Recipient view must NOT expose reservation attributes."""
        service = WishlistService.in_memory()
        owner = make_user(1001, "Alice")
        gifter = make_user(2001, "Bob")

        wl = await service.create_wishlist(owner=owner, title="Alice's Wishlist")
        item = await service.add_wish_item(
            wishlist_id=wl.id,
            actor=owner,
            title="Noise Cancelling Headphones",
            quantity=1,
        )

        # Gifter creates a reservation
        res = await service.create_reservation(item_id=item.id, user=gifter, quantity=1)

        # Recipient view check
        recip_view = await service.get_wishlist_view(wl.id, current_user=owner)
        assert len(recip_view.items) == 1
        recip_item = recip_view.items[0]
        assert isinstance(recip_item, WishItemRecipientViewDTO)
        assert recip_item.is_recipient is True

        # Assert recipient schema has NO reservation leak
        forbidden_fields = {
            "available_quantity",
            "is_fully_reserved",
            "is_reserved_by_me",
            "my_reserved_quantity",
            "my_reservation_status",
            "my_reservation_id",
            "reservations",
        }
        for field_name in forbidden_fields:
            assert field_name not in WishItemRecipientViewDTO.model_fields
            assert not hasattr(recip_item, field_name)

        # Gifter view check: must expose availability AND my_reservation_status & my_reservation_id
        gifter_view = await service.get_wishlist_view(wl.id, current_user=gifter)
        assert len(gifter_view.items) == 1
        gifter_item = gifter_view.items[0]
        assert isinstance(gifter_item, WishItemGifterViewDTO)
        assert gifter_item.is_recipient is False
        assert gifter_item.is_reserved_by_me is True
        assert gifter_item.my_reserved_quantity == 1

        # Gifter must see their own reservation status and ID (Gaps identified in Architecture 1.3)
        assert hasattr(gifter_item, "my_reservation_status"), (
            "Gifter view must include my_reservation_status"
        )
        assert gifter_item.my_reservation_status == ReservationStatus.ACTIVE
        assert hasattr(gifter_item, "my_reservation_id"), (
            "Gifter view must include my_reservation_id"
        )
        assert gifter_item.my_reservation_id == res.id

    async def test_recipient_cannot_book_own_gift_raises_self_reservation_error(self) -> None:
        """Personal wishlist owner cannot reserve their own gift."""
        service = WishlistService.in_memory()
        owner = make_user(1001, "Alice")
        wl = await service.create_wishlist(owner=owner, title="Alice's Wishlist")
        item = await service.add_wish_item(
            wishlist_id=wl.id,
            actor=owner,
            title="Coffee Grinder",
            quantity=1,
        )

        with pytest.raises(SelfReservationError, match="Recipient cannot reserve"):
            await service.create_reservation(item_id=item.id, user=owner, quantity=1)

    async def test_coauthor_cannot_book_item_where_they_are_explicit_recipient(self) -> None:
        """In collaborative wishlist, assigned co-author recipient cannot reserve own item."""
        service = WishlistService.in_memory()
        owner = make_user(1001, "Alice")
        coauthor = make_user(1002, "Bob")
        gifter = make_user(2001, "Charlie")

        wl = await service.create_wishlist(owner=owner, title="Apartment Housewarming")
        wl.members.append(
            WishlistMember(
                id=1,
                wishlist_id=wl.id,
                user_id=coauthor.telegram_id,
                role=WishlistRole.MEMBER,
                wishlist=wl,
            )
        )
        wl.is_collaborative = True

        item = await service.add_wish_item(
            wishlist_id=wl.id,
            actor=owner,
            title="Blender for Bob",
            quantity=1,
            recipient_user_id=coauthor.telegram_id,
            recipient_name="Bob",
        )

        # Bob (recipient) attempts to reserve -> blocked
        with pytest.raises(SelfReservationError, match="Recipient cannot reserve"):
            await service.create_reservation(item_id=item.id, user=coauthor, quantity=1)

        # Charlie (third-party gifter) can reserve
        res = await service.create_reservation(item_id=item.id, user=gifter, quantity=1)
        assert res.user_id == gifter.telegram_id


# ============================================================================
# 2. Reservation Lifecycle & PURCHASED State Invariant
# ============================================================================


class TestReservationLifecycleAndPurchasedState:
    """Verify ACTIVE -> PURCHASED -> ACTIVE and CANCELLED lifecycle transitions."""

    async def test_mark_reservation_as_purchased_and_revert_to_active(self) -> None:
        """Gifter can mark reservation as PURCHASED and revert back to ACTIVE."""
        service = WishlistService.in_memory()
        owner = make_user(1001, "Alice")
        gifter = make_user(2001, "Bob")

        wl = await service.create_wishlist(owner=owner, title="Birthday")
        item = await service.add_wish_item(
            wishlist_id=wl.id, actor=owner, title="Keyboard", quantity=1
        )

        res = await service.create_reservation(item_id=item.id, user=gifter, quantity=1)
        assert res.status == ReservationStatus.ACTIVE

        # Transition ACTIVE -> PURCHASED
        res_purchased = await service.mark_reservation_purchased(reservation_id=res.id, user=gifter)
        assert res_purchased.status == ReservationStatus.PURCHASED

        # Transition PURCHASED -> ACTIVE
        res_active = await service.revert_reservation_to_active(reservation_id=res.id, user=gifter)
        assert res_active.status == ReservationStatus.ACTIVE

    async def test_purchased_reservation_retains_inventory_lock(self) -> None:
        """PURCHASED reservation must lock inventory; available quantity must not increase."""
        service = WishlistService.in_memory()
        owner = make_user(1001, "Alice")
        gifter1 = make_user(2001, "Bob")
        gifter2 = make_user(2002, "Charlie")
        gifter3 = make_user(2003, "Dave")

        wl = await service.create_wishlist(owner=owner, title="Birthday")
        item = await service.add_wish_item(
            wishlist_id=wl.id, actor=owner, title="Board Game", quantity=2
        )

        res1 = await service.create_reservation(item_id=item.id, user=gifter1, quantity=1)
        assert item.available_quantity == 1

        # Mark res1 as purchased
        await service.mark_reservation_purchased(reservation_id=res1.id, user=gifter1)

        # Inventory invariant: available_quantity MUST remain 1 (not restocked to 2!)
        assert item.reserved_quantity == 1
        assert item.available_quantity == 1

        # Gifter 2 reserves remaining 1 unit
        await service.create_reservation(item_id=item.id, user=gifter2, quantity=1)
        assert item.available_quantity == 0

        # Gifter 3 attempts to reserve -> rejected with InsufficientQuantityError
        with pytest.raises(InsufficientQuantityError):
            await service.create_reservation(item_id=item.id, user=gifter3, quantity=1)

    async def test_cancel_reservation_restocks_available_quantity(self) -> None:
        """Cancelling reservation in ACTIVE/PURCHASED immediately restocks available quantity."""
        service = WishlistService.in_memory()
        owner = make_user(1001, "Alice")
        gifter1 = make_user(2001, "Bob")
        gifter2 = make_user(2002, "Charlie")

        wl = await service.create_wishlist(owner=owner, title="Housewarming")
        item = await service.add_wish_item(
            wishlist_id=wl.id, actor=owner, title="Toaster", quantity=1
        )

        res = await service.create_reservation(item_id=item.id, user=gifter1, quantity=1)
        await service.mark_reservation_purchased(reservation_id=res.id, user=gifter1)
        assert item.available_quantity == 0

        # Gifter 1 cancels the purchased reservation
        cancelled_res = await service.cancel_reservation(reservation_id=res.id, user=gifter1)
        assert cancelled_res.status == ReservationStatus.CANCELLED
        assert item.available_quantity == 1

        # Gifter 2 can now reserve the restocked unit
        new_res = await service.create_reservation(item_id=item.id, user=gifter2, quantity=1)
        assert new_res.status == ReservationStatus.ACTIVE
        assert item.available_quantity == 0

    async def test_update_reservation_quantity_partial_adjustments(self) -> None:
        """Gifter can adjust reserved quantity up or down with immediate inventory recalculation."""
        service = WishlistService.in_memory()
        owner = make_user(1001, "Alice")
        gifter = make_user(2001, "Bob")

        wl = await service.create_wishlist(owner=owner, title="Party")
        item = await service.add_wish_item(
            wishlist_id=wl.id, actor=owner, title="Glasses", quantity=5
        )

        res = await service.create_reservation(item_id=item.id, user=gifter, quantity=2)
        assert item.available_quantity == 3

        # Increase reservation to 4
        updated_res = await service.update_reservation_quantity(
            reservation_id=res.id, user=gifter, new_quantity=4
        )
        assert updated_res.quantity == 4
        assert item.available_quantity == 1

        # Decrease reservation to 1
        updated_res2 = await service.update_reservation_quantity(
            reservation_id=res.id, user=gifter, new_quantity=1
        )
        assert updated_res2.quantity == 1
        assert item.available_quantity == 4

    async def test_update_reservation_quantity_rejects_insufficient_balance(self) -> None:
        """Attempting to increase reservation beyond balance raises InsufficientQuantityError."""
        service = WishlistService.in_memory()
        owner = make_user(1001, "Alice")
        gifter1 = make_user(2001, "Bob")
        gifter2 = make_user(2002, "Charlie")

        wl = await service.create_wishlist(owner=owner, title="Festival")
        item = await service.add_wish_item(
            wishlist_id=wl.id, actor=owner, title="Lanterns", quantity=3
        )

        res1 = await service.create_reservation(item_id=item.id, user=gifter1, quantity=1)
        await service.create_reservation(item_id=item.id, user=gifter2, quantity=1)
        # 1 unit remains available
        assert item.available_quantity == 1

        # Gifter 1 attempts to increase from 1 to 3 (requires +2, but only 1 available)
        with pytest.raises(InsufficientQuantityError):
            await service.update_reservation_quantity(
                reservation_id=res1.id, user=gifter1, new_quantity=3
            )


# ============================================================================
# 3. Concurrency & Overbooking Guards
# ============================================================================


class TestConcurrencyAndOverbookingGuards:
    """Verify concurrency coordinator prevents race conditions and overbooking."""

    async def test_concurrent_race_condition_prevented_by_coordinator(self) -> None:
        """Concurrent reservation attempts on remaining units serialize with zero overbooking."""
        service = WishlistService.in_memory()
        assert service.concurrency_coordinator is not None, (
            "WishlistService must have an ItemConcurrencyCoordinator"
        )

        owner = make_user(1001, "Alice")
        wl = await service.create_wishlist(owner=owner, title="Exclusive Concert")
        item = await service.add_wish_item(
            wishlist_id=wl.id, actor=owner, title="VIP Pass", quantity=3
        )

        # 10 gifters concurrently race to reserve 1 pass each
        gifters = [make_user(3000 + i, f"Gifter_{i}") for i in range(10)]

        results = await asyncio.gather(
            *[service.create_reservation(item_id=item.id, user=g, quantity=1) for g in gifters],
            return_exceptions=True,
        )

        successes = [r for r in results if not isinstance(r, Exception)]
        failures = [r for r in results if isinstance(r, InsufficientQuantityError)]

        # Invariant: exactly 3 succeed, exactly 7 fail with InsufficientQuantityError
        assert len(successes) == 3
        assert len(failures) == 7
        assert item.available_quantity == 0
        assert item.reserved_quantity == 3


# ============================================================================
# 4. Item Quantity Reduction Lock Invariant
# ============================================================================


class TestItemReductionLockWithReservations:
    """Author cannot reduce item desired quantity below active + purchased reservations."""

    async def test_cannot_reduce_item_quantity_below_active_plus_purchased_reservations(
        self,
    ) -> None:
        """Item quantity reduction blocked if quantity < active + purchased reservations."""
        service = WishlistService.in_memory()
        owner = make_user(1001, "Alice")
        gifter1 = make_user(2001, "Bob")
        gifter2 = make_user(2002, "Charlie")

        wl = await service.create_wishlist(owner=owner, title="Wedding Registry")
        item = await service.add_wish_item(
            wishlist_id=wl.id, actor=owner, title="Wine Glasses", quantity=6
        )

        # Gifter 1 reserves 2 units (ACTIVE)
        await service.create_reservation(item_id=item.id, user=gifter1, quantity=2)
        # Gifter 2 reserves 2 units and marks PURCHASED
        res2 = await service.create_reservation(item_id=item.id, user=gifter2, quantity=2)
        await service.mark_reservation_purchased(reservation_id=res2.id, user=gifter2)

        # Total occupied: 2 ACTIVE + 2 PURCHASED = 4 units
        # Author reduces quantity to 5 -> allowed
        updated_item = await service.update_wish_item(item_id=item.id, actor=owner, quantity=5)
        assert updated_item.quantity == 5

        # Author reduces quantity to 4 -> allowed
        updated_item = await service.update_wish_item(item_id=item.id, actor=owner, quantity=4)
        assert updated_item.quantity == 4

        # Author reduces quantity to 3 (below occupied 4, received=0) -> allowed (FR-5 / Q12)
        updated_item = await service.update_wish_item(item_id=item.id, actor=owner, quantity=3)
        assert updated_item.quantity == 3

        # Once 2 units are received, reducing below received_quantity=2 is blocked
        await service.record_item_fulfillment(item.id, owner, 2)
        with pytest.raises(CannotReduceQuantityBelowReservedError, match="units already received"):
            await service.update_wish_item(item_id=item.id, actor=owner, quantity=1)


# ============================================================================
# 5. My Reservations Aggregated Cabinet
# ============================================================================


class TestMyReservationsAggregatedCabinet:
    """Verify gifter aggregated 'My Reservations' queries, summary, and archived retention."""

    async def test_get_user_reservations_returns_active_and_purchased_items(self) -> None:
        """get_user_reservations returns all non-cancelled bookings of user across wishlists."""
        service = WishlistService.in_memory()
        owner1 = make_user(1001, "Alice")
        owner2 = make_user(1002, "Bob")
        gifter = make_user(2001, "Charlie")

        wl1 = await service.create_wishlist(owner=owner1, title="Alice's Birthday")
        item1 = await service.add_wish_item(
            wishlist_id=wl1.id, actor=owner1, title="Book", quantity=1
        )

        wl2 = await service.create_wishlist(owner=owner2, title="Bob's Housewarming")
        item2 = await service.add_wish_item(
            wishlist_id=wl2.id, actor=owner2, title="Plant", quantity=2
        )
        item3 = await service.add_wish_item(
            wishlist_id=wl2.id, actor=owner2, title="Mug", quantity=1
        )

        # Gifter reserves item1 and marks as PURCHASED
        res1 = await service.create_reservation(item_id=item1.id, user=gifter, quantity=1)
        await service.mark_reservation_purchased(reservation_id=res1.id, user=gifter)

        # Gifter reserves item2 (ACTIVE)
        res2 = await service.create_reservation(item_id=item2.id, user=gifter, quantity=2)

        # Gifter reserves item3 and cancels it (CANCELLED)
        res3 = await service.create_reservation(item_id=item3.id, user=gifter, quantity=1)
        await service.cancel_reservation(reservation_id=res3.id, user=gifter)

        # Query user reservations
        my_reservations = await service.get_user_reservations(user_id=gifter.telegram_id)

        # item1 (PURCHASED) + item2 (ACTIVE) expected; item3 (CANCELLED) excluded
        assert len(my_reservations) == 2

        res_ids = {r.reservation_id for r in my_reservations}
        assert res_ids == {res1.id, res2.id}

        # Check fields of DTO
        r1_dto = next(r for r in my_reservations if r.reservation_id == res1.id)
        assert isinstance(r1_dto, MyReservationItemDTO)
        assert r1_dto.item_title == "Book"
        assert r1_dto.wishlist_title == "Alice's Birthday"
        assert r1_dto.reserved_quantity == 1
        assert r1_dto.status == ReservationStatus.PURCHASED
        assert r1_dto.is_item_archived is False

    async def test_get_user_reservations_summary_counter(self) -> None:
        """get_user_reservations_summary returns active/purchased and distinct items counts."""
        service = WishlistService.in_memory()
        owner = make_user(1001, "Alice")
        gifter = make_user(2001, "Bob")

        wl = await service.create_wishlist(owner=owner, title="Party")
        item1 = await service.add_wish_item(
            wishlist_id=wl.id, actor=owner, title="Lamp", quantity=1
        )
        item2 = await service.add_wish_item(wishlist_id=wl.id, actor=owner, title="Rug", quantity=1)

        res1 = await service.create_reservation(item_id=item1.id, user=gifter, quantity=1)
        await service.create_reservation(item_id=item2.id, user=gifter, quantity=1)
        await service.mark_reservation_purchased(reservation_id=res1.id, user=gifter)

        summary = await service.get_user_reservations_summary(user_id=gifter.telegram_id)
        assert isinstance(summary, UserReservationsSummaryDTO)
        assert summary.user_id == gifter.telegram_id
        assert summary.total_active_reservations == 2  # 1 ACTIVE + 1 PURCHASED
        assert summary.total_distinct_items == 2

    async def test_archived_item_persists_in_my_reservations_with_flag(self) -> None:
        """Archiving an item by author keeps reservation in gifter cabinet with flag."""
        service = WishlistService.in_memory()
        owner = make_user(1001, "Alice")
        gifter = make_user(2001, "Bob")

        wl = await service.create_wishlist(owner=owner, title="Wishlist")
        item = await service.add_wish_item(
            wishlist_id=wl.id, actor=owner, title="Headphones", quantity=1
        )

        res = await service.create_reservation(item_id=item.id, user=gifter, quantity=1)

        # Author archives item
        item.is_archived = True

        # Gifter queries reservations
        my_reservations = await service.get_user_reservations(user_id=gifter.telegram_id)
        assert len(my_reservations) == 1
        r_dto = my_reservations[0]
        assert r_dto.reservation_id == res.id
        assert r_dto.is_item_archived is True

        # Gifter can still cancel or mark as purchased
        cancelled = await service.cancel_reservation(reservation_id=res.id, user=gifter)
        assert cancelled.status == ReservationStatus.CANCELLED
