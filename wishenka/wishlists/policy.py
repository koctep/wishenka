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
    def can_restore_deleted(ctx: UserWishlistContext, wishlist: Wishlist) -> bool:
        """Only Owner can view or restore a soft-deleted wishlist."""
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
    def is_recipient_id(user_id: int | None, item: WishItem) -> bool:
        """Return whether the Telegram id must not see booking facts for the wish.

        On a personal list the owner receives every wish, including one that
        only has a display name. A display name is never compared to a user.
        On a collaborative list the recipient is ``recipient_user_id`` only.
        """
        if user_id is None:
            return False
        wishlist = item.wishlist
        if wishlist is not None and not wishlist.is_collaborative and wishlist.owner_id == user_id:
            return True
        return item.recipient_user_id is not None and item.recipient_user_id == user_id

    @staticmethod
    def is_recipient(user: AuthenticatedUser | None, item: WishItem) -> bool:
        """Return whether this caller must not see booking facts for the wish."""
        return WishlistAccessPolicy.is_recipient_id(
            None if user is None else user.telegram_id, item
        )

    @staticmethod
    def can_view_gifted(ctx: UserWishlistContext, wishlist: Wishlist) -> bool:
        """Only a member of a non-deleted wishlist may read the gifted section."""
        return ctx.is_member and wishlist.status != WishlistStatus.DELETED

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

    @staticmethod
    def can_favorite(
        user: AuthenticatedUser | None,
        wishlist: Wishlist,
        *,
        has_share_access: bool = False,
    ) -> bool:
        """Check if user can favorite the wishlist (non-owner, non-deleted, member or share)."""
        if user is None:
            return False
        if wishlist.status == WishlistStatus.DELETED:
            return False
        if wishlist.owner_id == user.telegram_id:
            return False
        ctx = WishlistAccessPolicy.resolve_context(user, wishlist)
        return ctx.is_member or has_share_access

    @staticmethod
    def can_view_history(
        user: AuthenticatedUser | None,
        wishlist: Wishlist,
        *,
        has_share_access: bool = False,
    ) -> bool:
        """Check if user can record or view the wishlist in Viewing History."""
        if user is None:
            return False
        if wishlist.status == WishlistStatus.DELETED:
            return False
        ctx = WishlistAccessPolicy.resolve_context(user, wishlist)
        return ctx.is_owner or ctx.is_member or has_share_access
