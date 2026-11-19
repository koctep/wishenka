"""Automated tests for reservation observability, structured logging, and caplog contracts."""

import logging

import pytest

from wishenka.auth.models import AuthenticatedUser
from wishenka.wishlists.exceptions import (
    InsufficientQuantityError,
    SelfReservationError,
)
from wishenka.wishlists.schemas import WishItemRecipientViewDTO
from wishenka.wishlists.service import WishlistService

pytestmark = pytest.mark.timeout(10)


def make_user(telegram_id: int, first_name: str) -> AuthenticatedUser:
    """Helper to build test AuthenticatedUser instance."""
    return AuthenticatedUser(
        telegram_id=telegram_id,
        first_name=first_name,
        auth_method="session_token",
    )


class TestReservationObservability:
    """Validate structured logging emission for reservation mutations and zero surprise leaks."""

    @pytest.mark.asyncio
    async def test_item_reserved_observability_event(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """create_reservation must emit structured item_reserved INFO log with context."""
        service = WishlistService.in_memory()
        owner = make_user(1001, "Alice")
        gifter = make_user(2001, "Bob")

        wl = await service.create_wishlist(owner=owner, title="Birthday Wishlist")
        item = await service.add_wish_item(
            wishlist_id=wl.id,
            actor=owner,
            title="Noise Cancelling Headphones",
            quantity=3,
        )

        with caplog.at_level(logging.INFO, logger="wishenka.wishlists"):
            res = await service.create_reservation(item_id=item.id, user=gifter, quantity=2)

        records = [
            r
            for r in caplog.records
            if r.name == "wishenka.wishlists" and getattr(r, "event", None) == "item_reserved"
        ]
        assert len(records) == 1
        rec = records[0]
        assert rec.levelname == "INFO"
        assert getattr(rec, "wishlist_id", None) == wl.id
        assert getattr(rec, "item_id", None) == item.id
        assert getattr(rec, "user_id", None) == gifter.telegram_id
        assert getattr(rec, "reservation_id", None) == res.id
        assert getattr(rec, "quantity", None) == 2

    @pytest.mark.asyncio
    async def test_reservation_purchased_observability_event(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """mark_reservation_purchased must emit structured reservation_purchased INFO log."""
        service = WishlistService.in_memory()
        owner = make_user(1001, "Alice")
        gifter = make_user(2001, "Bob")

        wl = await service.create_wishlist(owner=owner, title="Birthday Wishlist")
        item = await service.add_wish_item(
            wishlist_id=wl.id,
            actor=owner,
            title="Coffee Grinder",
            quantity=1,
        )
        res = await service.create_reservation(item_id=item.id, user=gifter, quantity=1)

        with caplog.at_level(logging.INFO, logger="wishenka.wishlists"):
            purchased_res = await service.mark_reservation_purchased(
                reservation_id=res.id,
                user=gifter,
            )

        assert purchased_res.id == res.id
        records = [
            r
            for r in caplog.records
            if r.name == "wishenka.wishlists"
            and getattr(r, "event", None) == "reservation_purchased"
        ]
        assert len(records) == 1
        rec = records[0]
        assert rec.levelname == "INFO"
        assert getattr(rec, "wishlist_id", None) == wl.id
        assert getattr(rec, "item_id", None) == item.id
        assert getattr(rec, "user_id", None) == gifter.telegram_id
        assert getattr(rec, "reservation_id", None) == res.id
        assert getattr(rec, "quantity", None) == 1

    @pytest.mark.asyncio
    async def test_reservation_reverted_observability_event(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """revert_reservation_to_active must emit structured reservation_reverted INFO log."""
        service = WishlistService.in_memory()
        owner = make_user(1001, "Alice")
        gifter = make_user(2001, "Bob")

        wl = await service.create_wishlist(owner=owner, title="Birthday Wishlist")
        item = await service.add_wish_item(
            wishlist_id=wl.id,
            actor=owner,
            title="Espresso Scale",
            quantity=1,
        )
        res = await service.create_reservation(item_id=item.id, user=gifter, quantity=1)
        await service.mark_reservation_purchased(reservation_id=res.id, user=gifter)

        with caplog.at_level(logging.INFO, logger="wishenka.wishlists"):
            reverted_res = await service.revert_reservation_to_active(
                reservation_id=res.id,
                user=gifter,
            )

        assert reverted_res.id == res.id
        records = [
            r
            for r in caplog.records
            if r.name == "wishenka.wishlists"
            and getattr(r, "event", None) == "reservation_reverted"
        ]
        assert len(records) == 1
        rec = records[0]
        assert rec.levelname == "INFO"
        assert getattr(rec, "wishlist_id", None) == wl.id
        assert getattr(rec, "item_id", None) == item.id
        assert getattr(rec, "user_id", None) == gifter.telegram_id
        assert getattr(rec, "reservation_id", None) == res.id
        assert getattr(rec, "quantity", None) == 1

    @pytest.mark.asyncio
    async def test_reservation_cancelled_observability_event(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """cancel_reservation must emit structured reservation_cancelled INFO log."""
        service = WishlistService.in_memory()
        owner = make_user(1001, "Alice")
        gifter = make_user(2001, "Bob")

        wl = await service.create_wishlist(owner=owner, title="Birthday Wishlist")
        item = await service.add_wish_item(
            wishlist_id=wl.id,
            actor=owner,
            title="Smart Lamp",
            quantity=2,
        )
        res = await service.create_reservation(item_id=item.id, user=gifter, quantity=2)

        with caplog.at_level(logging.INFO, logger="wishenka.wishlists"):
            cancelled_res = await service.cancel_reservation(
                reservation_id=res.id,
                user=gifter,
            )

        assert cancelled_res.id == res.id
        records = [
            r
            for r in caplog.records
            if r.name == "wishenka.wishlists"
            and getattr(r, "event", None) == "reservation_cancelled"
        ]
        assert len(records) == 1
        rec = records[0]
        assert rec.levelname == "INFO"
        assert getattr(rec, "wishlist_id", None) == wl.id
        assert getattr(rec, "item_id", None) == item.id
        assert getattr(rec, "user_id", None) == gifter.telegram_id
        assert getattr(rec, "reservation_id", None) == res.id
        assert getattr(rec, "quantity", None) == 2

    @pytest.mark.asyncio
    async def test_reservation_quantity_updated_observability_event(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """update_reservation_quantity must emit reservation_quantity_updated INFO log."""
        service = WishlistService.in_memory()
        owner = make_user(1001, "Alice")
        gifter = make_user(2001, "Bob")

        wl = await service.create_wishlist(owner=owner, title="Birthday Wishlist")
        item = await service.add_wish_item(
            wishlist_id=wl.id,
            actor=owner,
            title="Ceramic Mugs",
            quantity=6,
        )
        res = await service.create_reservation(item_id=item.id, user=gifter, quantity=2)

        with caplog.at_level(logging.INFO, logger="wishenka.wishlists"):
            updated_res = await service.update_reservation_quantity(
                reservation_id=res.id,
                user=gifter,
                new_quantity=4,
            )

        assert updated_res.quantity == 4
        records = [
            r
            for r in caplog.records
            if r.name == "wishenka.wishlists"
            and getattr(r, "event", None) == "reservation_quantity_updated"
        ]
        assert len(records) == 1
        rec = records[0]
        assert rec.levelname == "INFO"
        assert getattr(rec, "wishlist_id", None) == wl.id
        assert getattr(rec, "item_id", None) == item.id
        assert getattr(rec, "user_id", None) == gifter.telegram_id
        assert getattr(rec, "reservation_id", None) == res.id
        assert getattr(rec, "quantity", None) == 4
        assert getattr(rec, "old_quantity", None) == 2

    @pytest.mark.asyncio
    async def test_item_fulfilled_observability_event(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """record_item_fulfillment must emit structured item_fulfilled INFO log with context."""
        service = WishlistService.in_memory()
        owner = make_user(1001, "Alice")

        wl = await service.create_wishlist(owner=owner, title="Wedding Registry")
        item = await service.add_wish_item(
            wishlist_id=wl.id,
            actor=owner,
            title="Cookware Set",
            quantity=3,
        )

        with caplog.at_level(logging.INFO, logger="wishenka.wishlists"):
            fulfilled_item = await service.record_item_fulfillment(
                item_id=item.id,
                actor=owner,
                received_quantity=2,
            )

        assert fulfilled_item.received_quantity == 2
        records = [
            r
            for r in caplog.records
            if r.name == "wishenka.wishlists" and getattr(r, "event", None) == "item_fulfilled"
        ]
        assert len(records) == 1
        rec = records[0]
        assert rec.levelname == "INFO"
        assert getattr(rec, "wishlist_id", None) == wl.id
        assert getattr(rec, "item_id", None) == item.id
        assert getattr(rec, "user_id", None) == owner.telegram_id
        assert getattr(rec, "quantity", None) == 2
        assert getattr(rec, "received_quantity", None) == 2
        assert getattr(rec, "total_quantity", None) == 3

    @pytest.mark.asyncio
    async def test_self_reservation_blocked_warning_event(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Self-reservation attempt by recipient must emit self_reservation_blocked WARNING."""
        service = WishlistService.in_memory()
        owner = make_user(1001, "Alice")
        recipient = make_user(2002, "Bob")

        wl = await service.create_wishlist(owner=owner, title="Party Wishlist")
        await service.add_member(wishlist_id=wl.id, actor=owner, user_id=recipient.telegram_id)
        item = await service.add_wish_item(
            wishlist_id=wl.id,
            actor=owner,
            title="Secret Surprise",
            quantity=1,
            recipient_user_id=recipient.telegram_id,
        )

        with (
            caplog.at_level(logging.WARNING, logger="wishenka.wishlists"),
            pytest.raises(SelfReservationError),
        ):
            await service.create_reservation(item_id=item.id, user=recipient, quantity=1)

        records = [
            r
            for r in caplog.records
            if r.name == "wishenka.wishlists"
            and getattr(r, "event", None) == "self_reservation_blocked"
        ]
        assert len(records) == 1
        rec = records[0]
        assert rec.levelname == "WARNING"
        assert getattr(rec, "wishlist_id", None) == wl.id
        assert getattr(rec, "item_id", None) == item.id
        assert getattr(rec, "user_id", None) == recipient.telegram_id
        assert getattr(rec, "recipient_user_id", None) == recipient.telegram_id

    @pytest.mark.asyncio
    async def test_insufficient_quantity_blocked_warning_events(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Exceeding available balance must emit insufficient_quantity_blocked WARNING."""
        service = WishlistService.in_memory()
        owner = make_user(1001, "Alice")
        gifter = make_user(3003, "Charlie")

        wl = await service.create_wishlist(owner=owner, title="Gadgets")
        item = await service.add_wish_item(
            wishlist_id=wl.id,
            actor=owner,
            title="USB Cable",
            quantity=3,
        )

        # 1. Attempt to create reservation exceeding available quantity (requested 4 > 3)
        with (
            caplog.at_level(logging.WARNING, logger="wishenka.wishlists"),
            pytest.raises(InsufficientQuantityError),
        ):
            await service.create_reservation(item_id=item.id, user=gifter, quantity=4)

        records = [
            r
            for r in caplog.records
            if r.name == "wishenka.wishlists"
            and getattr(r, "event", None) == "insufficient_quantity_blocked"
        ]
        assert len(records) == 1
        rec1 = records[0]
        assert rec1.levelname == "WARNING"
        assert getattr(rec1, "wishlist_id", None) == wl.id
        assert getattr(rec1, "item_id", None) == item.id
        assert getattr(rec1, "user_id", None) == gifter.telegram_id
        assert getattr(rec1, "requested_quantity", None) == 4
        assert getattr(rec1, "available_quantity", None) == 3

        caplog.clear()

        # 2. Reserve 2 units (available balance becomes 1)
        res = await service.create_reservation(item_id=item.id, user=gifter, quantity=2)

        # 3. Attempt to increase reservation from 2 to 4 (delta 2 > available 1)
        with (
            caplog.at_level(logging.WARNING, logger="wishenka.wishlists"),
            pytest.raises(InsufficientQuantityError),
        ):
            await service.update_reservation_quantity(
                reservation_id=res.id,
                user=gifter,
                new_quantity=4,
            )

        records2 = [
            r
            for r in caplog.records
            if r.name == "wishenka.wishlists"
            and getattr(r, "event", None) == "insufficient_quantity_blocked"
        ]
        assert len(records2) == 1
        rec2 = records2[0]
        assert rec2.levelname == "WARNING"
        assert getattr(rec2, "wishlist_id", None) == wl.id
        assert getattr(rec2, "item_id", None) == item.id
        assert getattr(rec2, "reservation_id", None) == res.id
        assert getattr(rec2, "user_id", None) == gifter.telegram_id
        assert getattr(rec2, "delta", None) == 2
        assert getattr(rec2, "available_quantity", None) == 1

    @pytest.mark.asyncio
    async def test_zero_surprise_leaks_in_recipient_audit_trails(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Surprise Invariant: Recipient interactions must never leak reservation details."""
        service = WishlistService.in_memory()
        owner = make_user(1001, "Alice")
        gifter1 = make_user(2001, "Bob")
        gifter2 = make_user(2002, "Charlie")

        wl = await service.create_wishlist(owner=owner, title="Surprise Wishlist")
        item = await service.add_wish_item(
            wishlist_id=wl.id,
            actor=owner,
            title="Drone",
            quantity=2,
        )

        # Gifters create and purchase reservations
        res1 = await service.create_reservation(item_id=item.id, user=gifter1, quantity=1)
        await service.mark_reservation_purchased(reservation_id=res1.id, user=gifter1)
        await service.create_reservation(item_id=item.id, user=gifter2, quantity=1)

        caplog.clear()

        # Recipient accesses their wishlist view
        with caplog.at_level(logging.DEBUG, logger="wishenka.wishlists"):
            detail_dto = await service.get_wishlist_view(wishlist_id=wl.id, current_user=owner)

        # Recipient queries their own reservations cabinet
        with caplog.at_level(logging.DEBUG, logger="wishenka.wishlists"):
            my_res = await service.get_user_reservations(user_id=owner.telegram_id)
            summary = await service.get_user_reservations_summary(user_id=owner.telegram_id)

        # 1. Projected items obey strict WishItemRecipientViewDTO schema without reservation leaks
        assert len(detail_dto.items) == 1
        item_view = detail_dto.items[0]
        assert isinstance(item_view, WishItemRecipientViewDTO)
        assert item_view.is_recipient is True
        for forbidden_attr in (
            "available_quantity",
            "is_fully_reserved",
            "is_reserved_by_me",
            "my_reserved_quantity",
            "my_reservation_status",
            "my_reservation_id",
            "reservations",
        ):
            assert not hasattr(item_view, forbidden_attr)

        # 2. Assert recipient's own reservations cabinet returns empty
        assert len(my_res) == 0
        assert summary.total_active_reservations == 0
        assert summary.total_distinct_items == 0

        # 3. Assert zero surprise leaks in recipient audit trails / logs
        recipient_records = [
            r
            for r in caplog.records
            if r.name == "wishenka.wishlists" and getattr(r, "user_id", None) == owner.telegram_id
        ]
        for r in recipient_records:
            # Ensure no gifter telegram IDs or reservation references leak into recipient logs
            for forbidden_id in (gifter1.telegram_id, gifter2.telegram_id):
                assert str(forbidden_id) not in r.getMessage()
            assert not hasattr(r, "reservation_id")
            assert not hasattr(r, "gifter_id")
