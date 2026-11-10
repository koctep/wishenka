"""Tests for WISHENKA-6: Wishlist role models, permissions, lifecycle, and tokens."""

import logging
from datetime import UTC, datetime, timedelta

import pytest

from wishenka.auth.models import AuthenticatedUser
from wishenka.wishlists.exceptions import (
    InvalidInviteTokenError,
    PermissionDeniedError,
    SelfReservationError,
    WishlistArchivedError,
    WishlistDeletedError,
    WishlistNotFoundError,
)
from wishenka.wishlists.models import (
    Reservation,
    ReservationStatus,
    WishItem,
    Wishlist,
    WishlistMember,
    WishlistRole,
    WishlistStatus,
)
from wishenka.wishlists.policy import UserWishlistContext, WishlistAccessPolicy
from wishenka.wishlists.schemas import (
    WishItemGifterViewDTO,
    WishItemRecipientViewDTO,
    WishlistDetailViewDTO,
)
from wishenka.wishlists.service import WishlistService

pytestmark = pytest.mark.timeout(10)


# ============================================================================
# Helpers & Fixtures
# ============================================================================


def make_user(telegram_id: int, first_name: str, username: str | None = None) -> AuthenticatedUser:
    """Create test AuthenticatedUser instance."""
    return AuthenticatedUser(
        telegram_id=telegram_id,
        first_name=first_name,
        username=username,
        auth_method="session_token",
    )


# ============================================================================
# 1. Role Model Permissions (RBAC & Privilege Matrix)
# ============================================================================


class TestRoleModelPermissions:
    """Validate permissions across Owner, Admin, Member, and Gifter roles."""

    def test_owner_permissions_matrix(self) -> None:
        """Owner has full control over settings, members, roles, lifecycle, and items."""
        owner = make_user(1001, "Alice")
        wishlist = Wishlist(
            id=1,
            owner_id=owner.telegram_id,
            title="Alice's Birthday",
            status=WishlistStatus.ACTIVE,
            public_token="pub_token_owner_test",
            invite_token="inv_token_owner_test",
            members=[],
        )

        ctx: UserWishlistContext = WishlistAccessPolicy.resolve_context(owner, wishlist)

        assert ctx.is_owner is True
        assert ctx.is_admin is True
        assert ctx.is_member is True
        assert ctx.role == WishlistRole.OWNER

        assert WishlistAccessPolicy.can_view_wishlist(owner, wishlist) is True
        assert WishlistAccessPolicy.can_edit_settings(ctx, wishlist) is True
        assert WishlistAccessPolicy.can_manage_members(ctx, wishlist) is True
        assert WishlistAccessPolicy.can_change_member_role(ctx, wishlist) is True
        assert WishlistAccessPolicy.can_archive(ctx, wishlist) is True
        assert WishlistAccessPolicy.can_delete(ctx, wishlist) is True
        assert WishlistAccessPolicy.can_transfer_ownership(ctx, wishlist) is True
        assert WishlistAccessPolicy.can_add_or_edit_item(ctx, wishlist) is True

    def test_admin_permissions_matrix(self) -> None:
        """Admin can manage settings, items, and members, but CANNOT delete or change roles."""
        admin = make_user(1002, "Bob")
        wishlist = Wishlist(
            id=1,
            owner_id=1001,
            title="Shared Family Wishlist",
            status=WishlistStatus.ACTIVE,
            public_token="pub_token_admin_test",
            invite_token="inv_token_admin_test",
            members=[
                WishlistMember(
                    id=10, wishlist_id=1, user_id=admin.telegram_id, role=WishlistRole.ADMIN
                )
            ],
        )

        ctx: UserWishlistContext = WishlistAccessPolicy.resolve_context(admin, wishlist)

        assert ctx.is_owner is False
        assert ctx.is_admin is True
        assert ctx.is_member is True
        assert ctx.role == WishlistRole.ADMIN

        # Permitted operations
        assert WishlistAccessPolicy.can_view_wishlist(admin, wishlist) is True
        assert WishlistAccessPolicy.can_edit_settings(ctx, wishlist) is True
        assert WishlistAccessPolicy.can_manage_members(ctx, wishlist) is True
        assert WishlistAccessPolicy.can_archive(ctx, wishlist) is True
        assert WishlistAccessPolicy.can_add_or_edit_item(ctx, wishlist) is True

        # Restricted operations
        assert WishlistAccessPolicy.can_delete(ctx, wishlist) is False
        assert WishlistAccessPolicy.can_transfer_ownership(ctx, wishlist) is False
        assert WishlistAccessPolicy.can_change_member_role(ctx, wishlist) is False

    def test_member_permissions_matrix(self) -> None:
        """Member can view and add/edit items, but CANNOT modify settings or manage members."""
        member = make_user(1003, "Charlie")
        wishlist = Wishlist(
            id=1,
            owner_id=1001,
            title="Shared Family Wishlist",
            status=WishlistStatus.ACTIVE,
            public_token="pub_token_member_test",
            invite_token="inv_token_member_test",
            members=[
                WishlistMember(
                    id=11, wishlist_id=1, user_id=member.telegram_id, role=WishlistRole.MEMBER
                )
            ],
        )

        ctx: UserWishlistContext = WishlistAccessPolicy.resolve_context(member, wishlist)

        assert ctx.is_owner is False
        assert ctx.is_admin is False
        assert ctx.is_member is True
        assert ctx.role == WishlistRole.MEMBER

        assert WishlistAccessPolicy.can_view_wishlist(member, wishlist) is True
        assert WishlistAccessPolicy.can_add_or_edit_item(ctx, wishlist) is True

        # Restricted operations
        assert WishlistAccessPolicy.can_edit_settings(ctx, wishlist) is False
        assert WishlistAccessPolicy.can_manage_members(ctx, wishlist) is False
        assert WishlistAccessPolicy.can_change_member_role(ctx, wishlist) is False
        assert WishlistAccessPolicy.can_archive(ctx, wishlist) is False
        assert WishlistAccessPolicy.can_delete(ctx, wishlist) is False
        assert WishlistAccessPolicy.can_transfer_ownership(ctx, wishlist) is False

    def test_gifter_permissions_matrix(self) -> None:
        """Anonymous or non-member gifter can view and reserve, but cannot edit or manage."""
        gifter = make_user(2001, "Dave")
        wishlist = Wishlist(
            id=1,
            owner_id=1001,
            title="Public Wishlist",
            status=WishlistStatus.ACTIVE,
            public_token="pub_token_gifter_test",
            invite_token="inv_token_gifter_test",
            members=[],
        )

        ctx: UserWishlistContext = WishlistAccessPolicy.resolve_context(gifter, wishlist)
        anonymous_ctx: UserWishlistContext = WishlistAccessPolicy.resolve_context(None, wishlist)

        for context in (ctx, anonymous_ctx):
            assert context.is_owner is False
            assert context.is_admin is False
            assert context.is_member is False
            assert context.role is None
            assert WishlistAccessPolicy.can_edit_settings(context, wishlist) is False
            assert WishlistAccessPolicy.can_manage_members(context, wishlist) is False
            assert WishlistAccessPolicy.can_archive(context, wishlist) is False
            assert WishlistAccessPolicy.can_delete(context, wishlist) is False
            assert WishlistAccessPolicy.can_add_or_edit_item(context, wishlist) is False

        assert WishlistAccessPolicy.can_view_wishlist(gifter, wishlist) is True
        assert WishlistAccessPolicy.can_view_wishlist(None, wishlist) is True

    @pytest.mark.asyncio
    async def test_service_enforces_role_authorization_failures(self) -> None:
        """Service layer rejects unauthorized operations with PermissionDeniedError."""
        service = WishlistService()
        owner = make_user(1001, "Alice")
        admin = make_user(1002, "Bob")
        member = make_user(1003, "Charlie")

        wishlist = await service.create_wishlist(
            owner=owner,
            title="Anniversary Celebration",
            description="Our shared list",
        )
        await service.add_member(
            wishlist_id=wishlist.id,
            actor=owner,
            user_id=admin.telegram_id,
            role=WishlistRole.ADMIN,
        )
        await service.add_member(
            wishlist_id=wishlist.id,
            actor=owner,
            user_id=member.telegram_id,
            role=WishlistRole.MEMBER,
        )

        # Member cannot update settings
        with pytest.raises(PermissionDeniedError):
            await service.update_wishlist_settings(
                wishlist_id=wishlist.id,
                actor=member,
                title="Hacked Title",
            )

        # Admin cannot delete wishlist
        with pytest.raises(PermissionDeniedError):
            await service.delete_wishlist(
                wishlist_id=wishlist.id,
                actor=admin,
            )

        # Admin cannot transfer ownership
        with pytest.raises(PermissionDeniedError):
            await service.transfer_ownership(
                wishlist_id=wishlist.id,
                actor=admin,
                new_owner_id=member.telegram_id,
            )


# ============================================================================
# 2. Surprise Invariant & Zero-Leak Projections
# ============================================================================


class TestSurpriseInvariantZeroLeak:
    """Validate Surprise Invariant zero-leak projections and reservation rules."""

    def test_recipient_contextual_identification(self) -> None:
        """Surprise invariant identifies recipient in both personal and collaborative lists."""
        owner = make_user(1001, "Alice")
        collaborator = make_user(1002, "Bob")
        gifter = make_user(2001, "Gifter Dave")

        wishlist = Wishlist(
            id=1,
            owner_id=owner.telegram_id,
            title="Shared Celebration",
            status=WishlistStatus.ACTIVE,
            public_token="pub_tok",
            invite_token="inv_tok",
        )

        # Item intended for Alice
        item_for_alice = WishItem(
            id=50,
            wishlist_id=wishlist.id,
            wishlist=wishlist,
            recipient_user_id=owner.telegram_id,
            title="Alice's Dream Watch",
            quantity=1,
            is_archived=False,
        )

        # Item intended for Bob
        item_for_bob = WishItem(
            id=51,
            wishlist_id=wishlist.id,
            wishlist=wishlist,
            recipient_user_id=collaborator.telegram_id,
            title="Bob's Coffee Machine",
            quantity=1,
            is_archived=False,
        )

        # Item with external recipient (Grandmother Nina)
        item_for_nina = WishItem(
            id=52,
            wishlist_id=wishlist.id,
            wishlist=wishlist,
            recipient_user_id=None,
            recipient_name="Бабушка Нина",
            title="Tea Set",
            quantity=1,
            is_archived=False,
        )

        # Alice is recipient for item 50, but NOT item 51 or 52
        assert WishlistAccessPolicy.is_recipient(owner, item_for_alice) is True
        assert WishlistAccessPolicy.is_recipient(owner, item_for_bob) is False
        assert WishlistAccessPolicy.is_recipient(owner, item_for_nina) is False

        # Bob is recipient for item 51, but NOT item 50 or 52
        assert WishlistAccessPolicy.is_recipient(collaborator, item_for_alice) is False
        assert WishlistAccessPolicy.is_recipient(collaborator, item_for_bob) is True
        assert WishlistAccessPolicy.is_recipient(collaborator, item_for_nina) is False

        # Gifter is never recipient
        assert WishlistAccessPolicy.is_recipient(gifter, item_for_alice) is False
        assert WishlistAccessPolicy.is_recipient(gifter, item_for_bob) is False
        assert WishlistAccessPolicy.is_recipient(gifter, item_for_nina) is False

    def test_recipient_cannot_reserve_own_gift(self) -> None:
        """Recipient cannot reserve an item meant for them, even if Owner or Admin."""
        owner = make_user(1001, "Alice")
        collaborator = make_user(1002, "Bob")

        wishlist = Wishlist(
            id=1,
            owner_id=owner.telegram_id,
            status=WishlistStatus.ACTIVE,
            public_token="pub_tok",
            invite_token="inv_tok",
        )
        item_for_owner = WishItem(
            id=10,
            wishlist_id=wishlist.id,
            wishlist=wishlist,
            recipient_user_id=owner.telegram_id,
            title="Surprise Gift",
            quantity=1,
            is_archived=False,
        )

        owner_ctx = WishlistAccessPolicy.resolve_context(owner, wishlist)
        collab_ctx = WishlistAccessPolicy.resolve_context(collaborator, wishlist)

        # Owner is recipient: CANNOT reserve
        assert (
            WishlistAccessPolicy.can_reserve_item(user=owner, ctx=owner_ctx, item=item_for_owner)
            is False
        )
        # Collaborator is NOT recipient: CAN reserve
        assert (
            WishlistAccessPolicy.can_reserve_item(
                user=collaborator, ctx=collab_ctx, item=item_for_owner
            )
            is True
        )

    @pytest.mark.asyncio
    async def test_zero_leak_projection_omits_reservation_data(self) -> None:
        """Surprise Invariant: Recipient view DTO completely strips reservation details."""
        service = WishlistService()
        recipient_user = make_user(1001, "Alice")
        gifter_user = make_user(2001, "Dave")

        wishlist = await service.create_wishlist(
            owner=recipient_user,
            title="Alice Birthday",
            description="My wishes",
        )
        item = await service.add_wish_item(
            wishlist_id=wishlist.id,
            actor=recipient_user,
            title="Wireless Headphones",
            quantity=1,
            recipient_user_id=recipient_user.telegram_id,
        )

        # Gifter reserves the item
        await service.create_reservation(
            item_id=item.id,
            user=gifter_user,
            quantity=1,
        )

        # 1. Project for Recipient (Alice)
        recipient_view: WishlistDetailViewDTO = await service.get_wishlist_view(
            wishlist_id=wishlist.id,
            current_user=recipient_user,
        )
        assert len(recipient_view.items) == 1
        item_view = recipient_view.items[0]

        # Recipient view MUST be an instance of WishItemRecipientViewDTO
        assert isinstance(item_view, WishItemRecipientViewDTO)
        assert item_view.is_recipient is True

        dumped_recipient = item_view.model_dump()
        # Zero-leak check: Reservation fields MUST NOT exist in serialized output
        assert "reservations" not in dumped_recipient
        assert "reserved_quantity" not in dumped_recipient
        assert "available_quantity" not in dumped_recipient
        assert "is_reserved_by_me" not in dumped_recipient
        assert "my_reserved_quantity" not in dumped_recipient
        assert "is_fully_reserved" not in dumped_recipient

        # 2. Project for Gifter (Dave)
        gifter_view: WishlistDetailViewDTO = await service.get_wishlist_view(
            wishlist_id=wishlist.id,
            current_user=gifter_user,
        )
        gifter_item_view = gifter_view.items[0]

        # Gifter view MUST be an instance of WishItemGifterViewDTO
        assert isinstance(gifter_item_view, WishItemGifterViewDTO)
        assert gifter_item_view.is_recipient is False

        dumped_gifter = gifter_item_view.model_dump()
        # Gifter view MUST contain availability and booking status
        assert "available_quantity" in dumped_gifter
        assert dumped_gifter["available_quantity"] == 0
        assert dumped_gifter["is_fully_reserved"] is True
        assert dumped_gifter["is_reserved_by_me"] is True
        assert dumped_gifter["my_reserved_quantity"] == 1


# ============================================================================
# 3. Lifecycle Transitions (States, Collaboration, Event Modes)
# ============================================================================


class TestLifecycleTransitions:
    """Validate transitions: Personal <-> Collaborative, Ongoing vs Event, and State Machine."""

    @pytest.mark.asyncio
    async def test_personal_to_collaborative_transitions_based_on_members(self) -> None:
        """Personal wishlist becomes collaborative when a collaborator joins, reverts if alone."""
        service = WishlistService()
        owner = make_user(1001, "Alice")
        member = make_user(1002, "Bob")

        wishlist = await service.create_wishlist(owner=owner, title="Living Room Remodel")
        assert wishlist.is_collaborative is False

        # Add member -> transitions to collaborative
        await service.add_member(
            wishlist_id=wishlist.id,
            actor=owner,
            user_id=member.telegram_id,
            role=WishlistRole.MEMBER,
        )
        updated = await service.get_wishlist_by_id(wishlist.id)
        assert updated.is_collaborative is True

        # Remove member -> transitions back to personal
        await service.remove_member(
            wishlist_id=wishlist.id,
            actor=owner,
            user_id=member.telegram_id,
        )
        reverted = await service.get_wishlist_by_id(wishlist.id)
        assert reverted.is_collaborative is False

    def test_ongoing_vs_event_based_lifecycle(self) -> None:
        """Event wishlist keeps metadata and does NOT auto-archive when date passes."""
        past_date = datetime.now(UTC) - timedelta(days=5)

        event_wishlist = Wishlist(
            id=10,
            owner_id=1001,
            title="Graduation Party 2026",
            event_title="Graduation",
            event_date=past_date,
            status=WishlistStatus.ACTIVE,
            public_token="pub_event",
            invite_token="inv_event",
        )

        assert event_wishlist.event_title == "Graduation"
        assert event_wishlist.event_date is not None
        # Passing event date NEVER auto-archives
        assert event_wishlist.status == WishlistStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_active_to_archived_lifecycle_blocks_mutations_and_reservations(self) -> None:
        """Archiving a wishlist locks item additions and prevents new reservations."""
        service = WishlistService()
        owner = make_user(1001, "Alice")
        gifter = make_user(2001, "Dave")

        wishlist = await service.create_wishlist(owner=owner, title="Summer Trips")
        item = await service.add_wish_item(
            wishlist_id=wishlist.id,
            actor=owner,
            title="Tent",
            quantity=1,
            recipient_user_id=None,
        )

        # Archive wishlist
        await service.archive_wishlist(wishlist_id=wishlist.id, actor=owner)
        archived_wl = await service.get_wishlist_by_id(wishlist.id)
        assert archived_wl.status == WishlistStatus.ARCHIVED

        # Attempting to add an item fails
        with pytest.raises(WishlistArchivedError):
            await service.add_wish_item(
                wishlist_id=wishlist.id,
                actor=owner,
                title="Sleeping Bag",
                quantity=1,
            )

        # Attempting to reserve an item fails
        with pytest.raises(WishlistArchivedError):
            await service.create_reservation(
                item_id=item.id,
                user=gifter,
                quantity=1,
            )

        # Unarchive restores ACTIVE status and allows reservation
        await service.unarchive_wishlist(wishlist_id=wishlist.id, actor=owner)
        active_wl = await service.get_wishlist_by_id(wishlist.id)
        assert active_wl.status == WishlistStatus.ACTIVE

        res: Reservation = await service.create_reservation(
            item_id=item.id, user=gifter, quantity=1
        )
        assert res.status == ReservationStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_deleted_lifecycle_invalidates_tokens_and_cancels_reservations(self) -> None:
        """Soft-deleting a wishlist cancels all active reservations and blocks access."""
        service = WishlistService()
        owner = make_user(1001, "Alice")
        gifter = make_user(2001, "Dave")

        wishlist = await service.create_wishlist(owner=owner, title="Temporary List")
        item = await service.add_wish_item(
            wishlist_id=wishlist.id,
            actor=owner,
            title="Book",
            quantity=1,
        )
        res: Reservation = await service.create_reservation(
            item_id=item.id, user=gifter, quantity=1
        )
        assert res.status == ReservationStatus.ACTIVE

        # Delete wishlist
        await service.delete_wishlist(wishlist_id=wishlist.id, actor=owner)

        # Accessing by public token or id raises WishlistNotFoundError or WishlistDeletedError
        with pytest.raises((WishlistNotFoundError, WishlistDeletedError)):
            await service.get_wishlist_by_public_token(wishlist.public_token)

        # Reservation is cancelled
        reservation_status = await service.get_reservation_status(res.id)
        assert reservation_status == ReservationStatus.CANCELLED


# ============================================================================
# 4. Sharing Tokens (Public and Invite Links, Revocation, Expiration)
# ============================================================================


class TestSharingTokens:
    """Validate public link access, invite token join flow, expiration, and regeneration."""

    @pytest.mark.asyncio
    async def test_public_token_provides_read_and_gifter_access_without_exposing_invite(
        self,
    ) -> None:
        """Public token gives Gifter view and keeps invite token secret."""
        service = WishlistService()
        owner = make_user(1001, "Alice")
        wishlist = await service.create_wishlist(owner=owner, title="Public Wishlist")

        assert len(wishlist.public_token) >= 16
        assert len(wishlist.invite_token) >= 24

        # Anonymous gifter fetches via public token
        dto: WishlistDetailViewDTO = await service.get_wishlist_by_public_token(
            public_token=wishlist.public_token,
            current_user=None,
        )
        assert dto.title == "Public Wishlist"
        assert dto.public_token == wishlist.public_token
        # Invite token MUST NOT be leaked to public gifters
        assert dto.invite_token is None

    @pytest.mark.asyncio
    async def test_invite_token_joins_as_member_never_admin(self) -> None:
        """Joining via invite token always assigns Member role, never Admin."""
        service = WishlistService()
        owner = make_user(1001, "Alice")
        joiner = make_user(3001, "Charlie")

        wishlist = await service.create_wishlist(owner=owner, title="Collaborative List")

        joined_member = await service.join_by_invite(
            invite_token=wishlist.invite_token,
            user=joiner,
        )
        assert joined_member.wishlist_id == wishlist.id
        assert joined_member.user_id == joiner.telegram_id
        assert joined_member.role == WishlistRole.MEMBER

    @pytest.mark.asyncio
    async def test_invite_token_expiration(self) -> None:
        """Expired invite token is rejected with InvalidInviteTokenError."""
        service = WishlistService()
        owner = make_user(1001, "Alice")
        joiner = make_user(3002, "Eve")

        # Create wishlist with expired invite token
        wishlist = await service.create_wishlist(
            owner=owner,
            title="Past Event",
            invite_token_expires_in=timedelta(seconds=-10),
        )

        with pytest.raises(InvalidInviteTokenError):
            await service.join_by_invite(
                invite_token=wishlist.invite_token,
                user=joiner,
            )

    @pytest.mark.asyncio
    async def test_token_regeneration_invalidates_old_tokens(self) -> None:
        """Regenerating public or invite tokens invalidates old tokens immediately."""
        service = WishlistService()
        owner = make_user(1001, "Alice")
        joiner = make_user(3003, "Frank")

        wishlist = await service.create_wishlist(owner=owner, title="Token Rotation List")
        old_public = wishlist.public_token
        old_invite = wishlist.invite_token

        # Regenerate public token
        new_public = await service.regenerate_public_token(wishlist_id=wishlist.id, actor=owner)
        assert new_public != old_public

        # Old public token must fail
        with pytest.raises(WishlistNotFoundError):
            await service.get_wishlist_by_public_token(old_public)

        # New public token must succeed
        pub_dto = await service.get_wishlist_by_public_token(new_public)
        assert pub_dto.id == wishlist.id

        # Regenerate invite token
        new_invite = await service.regenerate_invite_token(wishlist_id=wishlist.id, actor=owner)
        assert new_invite != old_invite

        # Old invite token must fail
        with pytest.raises(InvalidInviteTokenError):
            await service.join_by_invite(old_invite, joiner)

        # New invite token must succeed
        member = await service.join_by_invite(new_invite, joiner)
        assert member.user_id == joiner.telegram_id


# ============================================================================
# 5. Audit Logging and Observability
# ============================================================================


class TestWishlistAuditLogging:
    """Validate audit logs for security, lifecycle, and surprise invariant events."""

    @pytest.mark.asyncio
    async def test_wishlist_creation_audit_logging(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Wishlist creation emits structured INFO log with format and time type."""
        service = WishlistService()
        owner = make_user(1001, "Alice")
        event_dt = datetime(2027, 5, 20, 12, 0, tzinfo=UTC)

        with caplog.at_level(logging.INFO, logger="wishenka.wishlists"):
            wl = await service.create_wishlist(
                owner=owner,
                title="Birthday 2027",
                event_date=event_dt,
            )

        records = [
            r
            for r in caplog.records
            if r.name == "wishenka.wishlists"
            and r.levelname == "INFO"
            and getattr(r, "event", None) == "wishlist_created"
        ]
        assert len(records) == 1
        rec = records[0]
        assert getattr(rec, "wishlist_id", None) == wl.id
        assert getattr(rec, "owner_id", None) == 1001
        assert getattr(rec, "format", None) == "personal"
        assert getattr(rec, "time_type", None) == "event"
        assert getattr(rec, "event_date", None) == event_dt.isoformat()

    @pytest.mark.asyncio
    async def test_member_management_and_invite_join_logging(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Member role assignment, invite join, and removal emit structured INFO audit logs."""
        service = WishlistService()
        owner = make_user(1001, "Alice")
        joiner = make_user(2002, "Bob")
        member_c = make_user(3003, "Charlie")

        wl = await service.create_wishlist(owner=owner, title="Audit List")

        with caplog.at_level(logging.INFO, logger="wishenka.wishlists"):
            # 1. Join via invite
            await service.join_by_invite(invite_token=wl.invite_token, user=joiner)
            # 2. Add / change member role
            await service.add_member(
                wishlist_id=wl.id,
                actor=owner,
                user_id=member_c.telegram_id,
                role=WishlistRole.ADMIN,
            )
            # 3. Remove member
            await service.remove_member(
                wishlist_id=wl.id,
                actor=owner,
                user_id=member_c.telegram_id,
            )

        events = [
            (getattr(r, "event", None), r.levelname)
            for r in caplog.records
            if r.name == "wishenka.wishlists"
        ]
        assert ("member_joined", "INFO") in events
        assert ("member_role_assigned", "INFO") in events
        assert ("member_removed", "INFO") in events

        join_rec = next(r for r in caplog.records if getattr(r, "event", None) == "member_joined")
        assert getattr(join_rec, "user_id", None) == 2002
        assert getattr(join_rec, "role", None) == "member"
        assert getattr(join_rec, "wishlist_id", None) == wl.id

    @pytest.mark.asyncio
    async def test_token_regeneration_logging_no_leak(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Regenerating tokens logs event and actor without leaking raw token strings."""
        service = WishlistService()
        owner = make_user(1001, "Alice")
        wl = await service.create_wishlist(owner=owner, title="Security List")

        with caplog.at_level(logging.INFO, logger="wishenka.wishlists"):
            new_public = await service.regenerate_public_token(wishlist_id=wl.id, actor=owner)
            new_invite = await service.regenerate_invite_token(wishlist_id=wl.id, actor=owner)

        records = [
            r
            for r in caplog.records
            if r.name == "wishenka.wishlists"
            and getattr(r, "event", None)
            in ("public_token_regenerated", "invite_token_regenerated")
        ]
        assert len(records) == 2

        # Verify sensitive token strings are NEVER logged in message or attributes
        for rec in records:
            assert new_public not in rec.getMessage()
            assert new_invite not in rec.getMessage()
            assert getattr(rec, "actor_id", None) == 1001
            assert getattr(rec, "wishlist_id", None) == wl.id

    @pytest.mark.asyncio
    async def test_lifecycle_state_transitions_logging(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Lifecycle transitions (archive, unarchive, delete, transfer) emit audit logs."""
        service = WishlistService()
        owner = make_user(1001, "Alice")
        collaborator = make_user(2002, "Bob")
        wl = await service.create_wishlist(owner=owner, title="Lifecycle Audit")
        await service.add_member(
            wishlist_id=wl.id,
            actor=owner,
            user_id=collaborator.telegram_id,
            role=WishlistRole.ADMIN,
        )

        with caplog.at_level(logging.INFO, logger="wishenka.wishlists"):
            # Archive
            await service.archive_wishlist(wishlist_id=wl.id, actor=owner)
            # Unarchive
            await service.unarchive_wishlist(wishlist_id=wl.id, actor=owner)
            # Transfer ownership
            await service.transfer_ownership(
                wishlist_id=wl.id,
                actor=owner,
                new_owner_id=collaborator.telegram_id,
            )
            # Delete
            await service.delete_wishlist(wishlist_id=wl.id, actor=collaborator)

        records = [
            r
            for r in caplog.records
            if r.name == "wishenka.wishlists"
            and getattr(r, "event", None) in ("wishlist_status_changed", "ownership_transferred")
        ]

        # 3 status changes + 1 ownership transfer
        assert len(records) == 4
        # Archive
        assert getattr(records[0], "from_status", None) == "active"
        assert getattr(records[0], "to_status", None) == "archived"
        # Unarchive
        assert getattr(records[1], "from_status", None) == "archived"
        assert getattr(records[1], "to_status", None) == "active"
        # Transfer
        assert getattr(records[2], "event", None) == "ownership_transferred"
        assert getattr(records[2], "previous_owner_id", None) == 1001
        assert getattr(records[2], "new_owner_id", None) == 2002
        # Delete
        assert getattr(records[3], "from_status", None) == "active"
        assert getattr(records[3], "to_status", None) == "deleted"

    @pytest.mark.asyncio
    async def test_reservation_audit_logging(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Reservation action emits structured INFO audit log with item, gifter, and quantity."""
        service = WishlistService()
        owner = make_user(1001, "Alice")
        gifter = make_user(3003, "Dave")
        wl = await service.create_wishlist(owner=owner, title="Gifts")
        item = await service.add_wish_item(
            wishlist_id=wl.id,
            actor=owner,
            title="Earphones",
            quantity=2,
        )

        with caplog.at_level(logging.INFO, logger="wishenka.wishlists"):
            res = await service.create_reservation(item_id=item.id, user=gifter, quantity=1)

        records = [
            r
            for r in caplog.records
            if r.name == "wishenka.wishlists"
            and getattr(r, "event", None) in ("item_reserved", "reservation_created")
        ]
        assert len(records) == 1
        rec = records[0]
        assert getattr(rec, "reservation_id", None) == res.id
        assert getattr(rec, "item_id", None) == item.id
        assert getattr(rec, "quantity", None) == 1
        assert getattr(rec, "gifter_id", None) == 3003

    @pytest.mark.asyncio
    async def test_warning_logging_on_access_denial_and_surprise_invariant(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Access violations and surprise invariant breaches emit WARNING level logs."""
        service = WishlistService()
        owner = make_user(1001, "Alice")
        member = make_user(2002, "Bob")
        wl = await service.create_wishlist(owner=owner, title="Protected List")
        await service.add_member(
            wishlist_id=wl.id,
            actor=owner,
            user_id=member.telegram_id,
            role=WishlistRole.MEMBER,
        )
        item = await service.add_wish_item(
            wishlist_id=wl.id,
            actor=owner,
            title="Surprise Trip",
            quantity=1,
            recipient_user_id=member.telegram_id,
        )

        with caplog.at_level(logging.WARNING, logger="wishenka.wishlists"):
            # 1. Access denial: member attempts to delete wishlist
            with pytest.raises(PermissionDeniedError):
                await service.delete_wishlist(wishlist_id=wl.id, actor=member)

            # 2. Surprise invariant violation: recipient attempts self-reservation
            with pytest.raises(SelfReservationError):
                await service.create_reservation(item_id=item.id, user=member, quantity=1)

            # 3. Invalid invite token
            with pytest.raises(InvalidInviteTokenError):
                await service.join_by_invite(invite_token="non_existent_token", user=member)

        warning_records = [
            r for r in caplog.records if r.name == "wishenka.wishlists" and r.levelname == "WARNING"
        ]
        warning_events = [getattr(r, "event", None) for r in warning_records]

        assert "access_denied" in warning_events
        assert (
            "self_reservation_blocked" in warning_events
            or "surprise_invariant_violation_attempt" in warning_events
        )
        assert "invalid_invite_token" in warning_events
