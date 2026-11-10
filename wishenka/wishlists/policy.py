"""Pure access control policy and permission enforcement for wishlists and items."""

from dataclasses import dataclass

from wishenka.auth.models import AuthenticatedUser
from wishenka.wishlists.models import (
    WishItem,
    Wishlist,
    WishlistRole,
    WishlistStatus,
)


@dataclass(frozen=True)
class UserWishlistContext:
    """Computed authorization context of a user relative to a specific wishlist."""

    is_owner: bool
    is_admin: bool
    is_member: bool
    role: WishlistRole | None


class WishlistAccessPolicy:
    """Pure domain policy enforcing RBAC and Surprise Invariant rules."""

    @staticmethod
    def resolve_context(user: AuthenticatedUser | None, wishlist: Wishlist) -> UserWishlistContext:
        """Resolve user role within the wishlist."""
        if user is None:
            return UserWishlistContext(
                is_owner=False,
                is_admin=False,
                is_member=False,
                role=None,
            )

        if wishlist.owner_id == user.telegram_id:
            return UserWishlistContext(
                is_owner=True,
                is_admin=True,
                is_member=True,
                role=WishlistRole.OWNER,
            )

        member = next((m for m in wishlist.members if m.user_id == user.telegram_id), None)
        if member is not None:
            return UserWishlistContext(
                is_owner=False,
                is_admin=(member.role == WishlistRole.ADMIN),
                is_member=True,
                role=member.role,
            )

        return UserWishlistContext(
            is_owner=False,
            is_admin=False,
            is_member=False,
            role=None,
        )

    @staticmethod
    def can_view_wishlist(user: AuthenticatedUser | None, wishlist: Wishlist) -> bool:
        """Check if user can view wishlist contents."""
        return wishlist.status != WishlistStatus.DELETED

    @staticmethod
    def can_edit_settings(ctx: UserWishlistContext, wishlist: Wishlist) -> bool:
        """Only Owner or Admin can update wishlist metadata; blocked when archived/deleted."""
        if wishlist.status != WishlistStatus.ACTIVE:
            return False
        return ctx.is_owner or ctx.is_admin

    @staticmethod
    def can_manage_members(ctx: UserWishlistContext, wishlist: Wishlist) -> bool:
        """Owner and Admin can invite/remove regular members in active wishlists."""
        if wishlist.status != WishlistStatus.ACTIVE:
            return False
        return ctx.is_owner or ctx.is_admin

    @staticmethod
    def can_change_member_role(ctx: UserWishlistContext, wishlist: Wishlist) -> bool:
        """Only Owner can promote to Admin or demote Admin in active wishlists."""
        if wishlist.status != WishlistStatus.ACTIVE:
            return False
        return ctx.is_owner

    @staticmethod
    def can_archive(ctx: UserWishlistContext, wishlist: Wishlist) -> bool:
        """Owner and Admin can toggle archive status for non-deleted wishlists."""
        if wishlist.status == WishlistStatus.DELETED:
            return False
        return ctx.is_owner or ctx.is_admin

    @staticmethod
    def can_delete(ctx: UserWishlistContext, wishlist: Wishlist) -> bool:
        """Only Owner can delete the wishlist."""
        return ctx.is_owner

    @staticmethod
    def can_transfer_ownership(ctx: UserWishlistContext, wishlist: Wishlist) -> bool:
        """Only current Owner can transfer ownership in active wishlists."""
        if wishlist.status != WishlistStatus.ACTIVE:
            return False
        return ctx.is_owner

    @staticmethod
    def can_add_or_edit_item(ctx: UserWishlistContext, wishlist: Wishlist) -> bool:
        """Owner, Admin, and Member can add and edit items in active wishlists."""
        if wishlist.status != WishlistStatus.ACTIVE:
            return False
        return ctx.is_member

    @staticmethod
    def is_recipient(user: AuthenticatedUser | None, item: WishItem) -> bool:
        """Surprise Invariant: Check if current user is the recipient of this item."""
        if user is None:
            return False

        if item.recipient_user_id is not None:
            return item.recipient_user_id == user.telegram_id

        # External named recipient (e.g. "Бабушка Нина")
        if item.recipient_name and item.recipient_name.strip():
            return False

        # Personal wishlist fallback: owner is implicit recipient
        if item.wishlist is not None and not item.wishlist.is_collaborative:
            return item.wishlist.owner_id == user.telegram_id

        return False

    @staticmethod
    def can_reserve_item(
        user: AuthenticatedUser | None, ctx: UserWishlistContext, item: WishItem
    ) -> bool:
        """Check if user is allowed to reserve units of this item."""
        if item.wishlist is not None and item.wishlist.status != WishlistStatus.ACTIVE:
            return False
        if item.is_archived:
            return False
        return not WishlistAccessPolicy.is_recipient(user, item)
