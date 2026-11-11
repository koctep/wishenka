"""Authenticated wishlist management and public sharing endpoints."""

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from wishenka.auth.dependencies import get_current_user
from wishenka.auth.models import AuthenticatedUser
from wishenka.wishlists.exceptions import (
    InvalidInviteTokenError,
    PermissionDeniedError,
    WishlistArchivedError,
    WishlistDeletedError,
    WishlistNotFoundError,
)
from wishenka.wishlists.models import Wishlist, WishlistRole, WishlistStatus
from wishenka.wishlists.policy import WishlistAccessPolicy
from wishenka.wishlists.service import WishlistService

router = APIRouter()
logger = logging.getLogger("wishenka.web.wishlists")
User = Annotated[AuthenticatedUser, Depends(get_current_user)]


class WishlistInput(BaseModel):
    """Editable optional wishlist details."""

    name: str | None = None
    description: str | None = None
    event_title: str | None = None
    event_date: datetime | None = None


async def execute[T](request: Request, action: Callable[[WishlistService], Awaitable[T]]) -> T:
    """Run an operation against the configured transactional or injected test service."""
    operation = getattr(request.scope.get("endpoint"), "__name__", "")
    try:
        injected = getattr(request.app.state, "wishlist_service", None)
        if injected is not None:
            result = await action(injected)
        else:
            result = cast(T, await request.app.state.wishlist_store.execute(action))
        if operation in {"create_wishlist", "update_wishlist", "change_status", "reset_share"}:
            logger.info(
                "Wishlist mutation committed: %s",
                operation,
                extra={"event": "wishlist_mutation_committed", "operation": operation},
            )
        return result
    except (WishlistNotFoundError, WishlistDeletedError, PermissionDeniedError) as exc:
        if isinstance(exc, PermissionDeniedError):
            logger.warning(
                "Wishlist operation permission denied: %s",
                operation,
                extra={"event": "wishlist_permission_denied", "operation": operation},
            )
        raise HTTPException(status_code=404, detail="Wishlist not found") from exc
    except WishlistArchivedError as exc:
        logger.warning(
            "Wishlist operation on archived list rejected: %s",
            operation,
            extra={"event": "wishlist_archived_mutation_blocked", "operation": operation},
        )
        raise HTTPException(status_code=409, detail="Wishlist is archived") from exc


def require_member(wishlist: Wishlist, user: AuthenticatedUser, manager: bool = False) -> None:
    """Reject non-members and non-managers without revealing whether a list exists."""
    ctx = WishlistAccessPolicy.resolve_context(user, wishlist)
    if not (ctx.is_admin if manager else ctx.is_member):
        logger.warning(
            "Access denied for user %s on wishlist %s (required_manager=%s)",
            user.telegram_id,
            wishlist.id,
            manager,
            extra={
                "event": "wishlist_access_denied",
                "wishlist_id": wishlist.id,
                "user_id": user.telegram_id,
                "required_manager": manager,
            },
        )
        raise HTTPException(status_code=404, detail="Wishlist not found")


def projection(wishlist: Wishlist, user: AuthenticatedUser | None, public: bool) -> dict[str, Any]:
    """Return only fields permitted for the caller, never reservation data publicly."""
    result: dict[str, Any] = {
        "id": wishlist.id,
        "name": wishlist.title,
        "description": wishlist.description,
        "event_title": wishlist.event_title,
        "event_date": wishlist.event_date,
        "status": wishlist.status.value,
        "items": [],
    }
    for item in wishlist.items:
        result["items"].append(
            {
                "id": item.id,
                "title": item.title,
                "description": item.description,
                "link": item.link,
                "image_url": item.image_url,
                "price": item.price,
                "currency": item.currency,
                "quantity": item.quantity,
                "received_quantity": item.received_quantity,
                "priority": item.priority.value,
                "category": item.category,
                "is_archived": item.is_archived,
                "recipient_name": item.recipient_name,
            }
        )
    if not public and user is not None:
        ctx = WishlistAccessPolicy.resolve_context(user, wishlist)
        result["role"] = ctx.role.value if ctx.role else None
        result["members"] = member_projection(wishlist)
        if ctx.is_admin:
            result["share_token"] = wishlist.public_token
            result["invite_token"] = wishlist.invite_token
    return result


@router.post("/api/wishlists", status_code=201)
async def create_wishlist(request: Request, body: WishlistInput, user: User) -> dict[str, Any]:
    async def action(service: WishlistService) -> dict[str, Any]:
        wl = await service.create_wishlist(
            owner=user,
            title=body.name or "",
            description=body.description,
            event_title=body.event_title,
            event_date=body.event_date,
        )
        logger.info(
            "Wishlist created: id=%s by user=%s",
            wl.id,
            user.telegram_id,
            extra={
                "event": "wishlist_created",
                "wishlist_id": wl.id,
                "user_id": user.telegram_id,
            },
        )
        return projection(wl, user, False)

    return await execute(request, action)


@router.get("/api/wishlists")
async def list_wishlists(
    request: Request, user: User, include_archived: bool = False
) -> list[dict[str, Any]]:
    async def action(service: WishlistService) -> list[dict[str, Any]]:
        return [
            projection(wl, user, False)
            for wl in service._wishlists.values()
            if WishlistAccessPolicy.resolve_context(user, wl).is_member
            and wl.status != WishlistStatus.DELETED
            and (include_archived or wl.status == WishlistStatus.ACTIVE)
        ]

    return await execute(request, action)


@router.get("/api/wishlists/{wishlist_id}")
async def get_wishlist(request: Request, wishlist_id: int, user: User) -> dict[str, Any]:
    async def action(service: WishlistService) -> dict[str, Any]:
        wl = await service.get_wishlist_by_id(wishlist_id)
        require_member(wl, user)
        return projection(wl, user, False)

    return await execute(request, action)


@router.patch("/api/wishlists/{wishlist_id}")
async def update_wishlist(
    request: Request, wishlist_id: int, body: WishlistInput, user: User
) -> dict[str, Any]:
    async def action(service: WishlistService) -> dict[str, Any]:
        wl = await service.get_wishlist_by_id(wishlist_id)
        require_member(wl, user, manager=True)
        if wl.status != WishlistStatus.ACTIVE:
            logger.warning(
                "Wishlist update rejected: wishlist %s is archived",
                wishlist_id,
                extra={
                    "event": "wishlist_archived_mutation_blocked",
                    "wishlist_id": wishlist_id,
                    "user_id": user.telegram_id,
                },
            )
            raise HTTPException(status_code=409, detail="Wishlist is archived")
        for key, value in body.model_dump(exclude_unset=True).items():
            setattr(
                wl, "title" if key == "name" else key, value if key != "name" else (value or "")
            )
        logger.info(
            "Wishlist updated: id=%s by user=%s",
            wishlist_id,
            user.telegram_id,
            extra={
                "event": "wishlist_updated",
                "wishlist_id": wishlist_id,
                "user_id": user.telegram_id,
            },
        )
        return projection(wl, user, False)

    return await execute(request, action)


@router.post("/api/wishlists/{wishlist_id}/{operation}")
async def change_status(
    request: Request, wishlist_id: int, operation: str, user: User
) -> dict[str, Any]:
    async def action(service: WishlistService) -> dict[str, Any]:
        wl = await service.get_wishlist_by_id(wishlist_id)
        require_member(wl, user, manager=True)
        if operation == "archive" and wl.status == WishlistStatus.ACTIVE:
            wl = await service.archive_wishlist(wishlist_id, user)
        elif operation == "restore" and wl.status == WishlistStatus.ARCHIVED:
            wl = await service.unarchive_wishlist(wishlist_id, user)
        elif operation not in {"archive", "restore"}:
            raise HTTPException(status_code=404, detail="Not found")
        else:
            logger.warning(
                "Invalid wishlist state transition: id=%s operation=%s status=%s",
                wishlist_id,
                operation,
                wl.status.value,
                extra={
                    "event": "wishlist_state_transition_invalid",
                    "wishlist_id": wishlist_id,
                    "operation": operation,
                    "status": wl.status.value,
                    "user_id": user.telegram_id,
                },
            )
            raise HTTPException(status_code=409, detail="Invalid wishlist state")
        logger.info(
            "Wishlist status changed: id=%s operation=%s new_status=%s by user=%s",
            wishlist_id,
            operation,
            wl.status.value,
            user.telegram_id,
            extra={
                "event": "wishlist_status_changed",
                "wishlist_id": wishlist_id,
                "operation": operation,
                "new_status": wl.status.value,
                "user_id": user.telegram_id,
            },
        )
        return projection(wl, user, False)

    return await execute(request, action)


@router.post("/api/wishlists/{wishlist_id}/share/reset")
async def reset_share(request: Request, wishlist_id: int, user: User) -> dict[str, Any]:
    async def action(service: WishlistService) -> dict[str, Any]:
        wl = await service.get_wishlist_by_id(wishlist_id)
        require_member(wl, user, manager=True)
        if wl.status != WishlistStatus.ACTIVE:
            logger.warning(
                "Share token reset rejected: wishlist %s is archived",
                wishlist_id,
                extra={
                    "event": "wishlist_archived_mutation_blocked",
                    "wishlist_id": wishlist_id,
                    "user_id": user.telegram_id,
                },
            )
            raise HTTPException(status_code=409, detail="Wishlist is archived")
        old = wl.public_token
        for _ in range(5):
            await service.regenerate_public_token(wishlist_id, user)
            if wl.public_token != old:
                break
        else:
            logger.warning(
                "Failed to generate unique sharing link for wishlist %s",
                wishlist_id,
                extra={
                    "event": "share_token_generation_failed",
                    "wishlist_id": wishlist_id,
                    "user_id": user.telegram_id,
                },
            )
            raise HTTPException(status_code=503, detail="Could not generate sharing link")
        logger.info(
            "Wishlist share token reset: id=%s by user=%s",
            wishlist_id,
            user.telegram_id,
            extra={
                "event": "wishlist_share_token_reset",
                "wishlist_id": wishlist_id,
                "user_id": user.telegram_id,
            },
        )
        return projection(wl, user, False)

    return await execute(request, action)


@router.get("/api/public/wishlists/{token}")
async def public_wishlist(request: Request, token: str) -> dict[str, Any]:
    async def action(service: WishlistService) -> dict[str, Any]:
        wl = next((w for w in service._wishlists.values() if w.public_token == token), None)
        if wl is None or wl.status == WishlistStatus.DELETED:
            logger.warning(
                "Public wishlist lookup failed: token not found or deleted",
                extra={"event": "public_wishlist_not_found"},
            )
            raise HTTPException(status_code=404, detail="Wishlist not found")
        logger.info(
            "Public wishlist viewed: id=%s",
            wl.id,
            extra={"event": "public_wishlist_viewed", "wishlist_id": wl.id},
        )
        return projection(wl, None, True)

    return await execute(request, action)


def member_projection(wishlist: Wishlist) -> list[dict[str, Any]]:
    """Expose roles without trusting client-supplied names or reservation data."""
    members = [
        {"user_id": wishlist.owner_id, "display_name": f"User {wishlist.owner_id}", "role": "owner"}
    ]
    members.extend(
        {
            "user_id": member.user_id,
            "display_name": f"User {member.user_id}",
            "role": member.role.value,
        }
        for member in wishlist.members
        if member.user_id != wishlist.owner_id
    )
    return members


class RoleInput(BaseModel):
    """Allowed role change values."""

    role: Literal["admin", "member"]


@router.get("/api/wishlists/{wishlist_id}/members")
async def list_members(request: Request, wishlist_id: int, user: User) -> list[dict[str, Any]]:
    async def action(service: WishlistService) -> list[dict[str, Any]]:
        wl = await service.get_wishlist_by_id(wishlist_id)
        require_member(wl, user)
        return member_projection(wl)

    return await execute(request, action)


@router.patch("/api/wishlists/{wishlist_id}/members/{user_id}/role")
async def set_role(
    request: Request, wishlist_id: int, user_id: int, body: RoleInput, user: User
) -> dict[str, str]:
    async def action(service: WishlistService) -> dict[str, str]:
        wl = await service.get_wishlist_by_id(wishlist_id)
        require_member(wl, user, manager=True)
        if wl.owner_id != user.telegram_id or user_id == wl.owner_id:
            logger.warning(
                "Unauthorized role change attempt by user %s on wishlist %s for member %s",
                user.telegram_id,
                wishlist_id,
                user_id,
                extra={
                    "event": "role_change_denied",
                    "wishlist_id": wishlist_id,
                    "actor_id": user.telegram_id,
                    "target_user_id": user_id,
                },
            )
            raise HTTPException(status_code=404, detail="Member not found")
        if wl.status != WishlistStatus.ACTIVE:
            logger.warning(
                "Role change rejected: wishlist %s is archived",
                wishlist_id,
                extra={
                    "event": "wishlist_archived_mutation_blocked",
                    "wishlist_id": wishlist_id,
                    "user_id": user.telegram_id,
                },
            )
            raise HTTPException(status_code=409, detail="Wishlist is archived")
        target = next((m for m in wl.members if m.user_id == user_id), None)
        if target is None:
            logger.warning(
                "Role change failed: member %s not found on wishlist %s",
                user_id,
                wishlist_id,
                extra={
                    "event": "member_not_found",
                    "wishlist_id": wishlist_id,
                    "target_user_id": user_id,
                },
            )
            raise HTTPException(status_code=404, detail="Member not found")
        target.role = WishlistRole(body.role)
        logger.info(
            "Member role updated: member %s role changed to %s on wishlist %s by user %s",
            user_id,
            target.role.value,
            wishlist_id,
            user.telegram_id,
            extra={
                "event": "member_role_updated",
                "wishlist_id": wishlist_id,
                "target_user_id": user_id,
                "new_role": target.role.value,
                "actor_id": user.telegram_id,
            },
        )
        return {"role": target.role.value}

    return await execute(request, action)


@router.delete("/api/wishlists/{wishlist_id}/members/{user_id}")
async def delete_member(
    request: Request, wishlist_id: int, user_id: int, user: User
) -> dict[str, str]:
    async def action(service: WishlistService) -> dict[str, str]:
        wl = await service.get_wishlist_by_id(wishlist_id)
        require_member(wl, user, manager=True)
        if wl.status != WishlistStatus.ACTIVE:
            logger.warning(
                "Member removal rejected: wishlist %s is archived",
                wishlist_id,
                extra={
                    "event": "wishlist_archived_mutation_blocked",
                    "wishlist_id": wishlist_id,
                    "user_id": user.telegram_id,
                },
            )
            raise HTTPException(status_code=409, detail="Wishlist is archived")
        target = next((m for m in wl.members if m.user_id == user_id), None)
        if target is None or target.role != WishlistRole.MEMBER or user_id == wl.owner_id:
            logger.warning(
                "Invalid member removal attempted by user %s on wishlist %s for member %s",
                user.telegram_id,
                wishlist_id,
                user_id,
                extra={
                    "event": "member_removal_denied",
                    "wishlist_id": wishlist_id,
                    "actor_id": user.telegram_id,
                    "target_user_id": user_id,
                },
            )
            raise HTTPException(status_code=404, detail="Member not found")
        await service.remove_member(wishlist_id, user, user_id)
        logger.info(
            "Member removed: user %s removed from wishlist %s by user %s",
            user_id,
            wishlist_id,
            user.telegram_id,
            extra={
                "event": "member_removed",
                "wishlist_id": wishlist_id,
                "target_user_id": user_id,
                "actor_id": user.telegram_id,
            },
        )
        return {"status": "removed"}

    return await execute(request, action)


@router.post("/api/wishlists/{wishlist_id}/invite/reset")
async def reset_invite(request: Request, wishlist_id: int, user: User) -> dict[str, str]:
    async def action(service: WishlistService) -> dict[str, str]:
        wl = await service.get_wishlist_by_id(wishlist_id)
        require_member(wl, user, manager=True)
        if wl.status != WishlistStatus.ACTIVE:
            logger.warning(
                "Invite token reset rejected: wishlist %s is archived",
                wishlist_id,
                extra={
                    "event": "wishlist_archived_mutation_blocked",
                    "wishlist_id": wishlist_id,
                    "user_id": user.telegram_id,
                },
            )
            raise HTTPException(status_code=409, detail="Wishlist is archived")
        token = await service.regenerate_invite_token(wishlist_id, user)
        logger.info(
            "Invite token reset for wishlist %s by user %s",
            wishlist_id,
            user.telegram_id,
            extra={
                "event": "invite_token_reset",
                "wishlist_id": wishlist_id,
                "user_id": user.telegram_id,
            },
        )
        return {"invite_token": token}

    return await execute(request, action)


def find_invitation(service: WishlistService, token: str) -> Wishlist:
    """Resolve an active invite without exposing whether a token previously existed."""
    if not token or len(token) > 128:
        logger.warning(
            "Invitation lookup rejected: token empty or length exceeded",
            extra={"event": "invitation_token_malformed"},
        )
        raise HTTPException(status_code=404, detail="Invitation not found")
    wl = next((w for w in service._wishlists.values() if w.invite_token == token), None)
    if (
        wl is None
        or wl.status != WishlistStatus.ACTIVE
        or (wl.invite_token_expires_at and wl.invite_token_expires_at <= datetime.now(UTC))
    ):
        logger.warning(
            "Invitation lookup rejected: token not found, inactive or expired",
            extra={"event": "invitation_token_invalid_or_expired"},
        )
        raise HTTPException(status_code=404, detail="Invitation not found")
    return wl


@router.get("/api/invitations/preview")
async def preview_invite(request: Request) -> dict[str, str]:
    async def action(service: WishlistService) -> dict[str, str]:
        wl = find_invitation(service, request.headers.get("x-invite-token", ""))
        logger.info(
            "Invitation preview accessed for wishlist %s",
            wl.id,
            extra={"event": "invitation_previewed", "wishlist_id": wl.id},
        )
        return {"name": wl.title, "access": "member"}

    return await execute(request, action)


@router.post("/api/invitations/accept")
async def accept_invite(request: Request, user: User) -> dict[str, Any]:
    async def action(service: WishlistService) -> dict[str, Any]:
        token = request.headers.get("x-invite-token", "")
        wl = find_invitation(service, token)
        ctx = WishlistAccessPolicy.resolve_context(user, wl)
        if ctx.is_member:
            logger.info(
                "User %s is already a member of wishlist %s",
                user.telegram_id,
                wl.id,
                extra={
                    "event": "invitation_already_member",
                    "wishlist_id": wl.id,
                    "user_id": user.telegram_id,
                },
            )
            return {"wishlist_id": wl.id, "role": ctx.role.value if ctx.role else "member"}
        try:
            member = await service.join_by_invite(token, user)
        except (InvalidInviteTokenError, WishlistArchivedError, WishlistDeletedError):
            logger.warning(
                "Invitation join failed for user %s on wishlist %s",
                user.telegram_id,
                wl.id,
                extra={
                    "event": "invitation_join_failed",
                    "wishlist_id": wl.id,
                    "user_id": user.telegram_id,
                },
            )
            raise HTTPException(status_code=404, detail="Invitation not found") from None
        logger.info(
            "User %s accepted invitation to wishlist %s with role %s",
            user.telegram_id,
            wl.id,
            member.role.value,
            extra={
                "event": "invitation_accepted",
                "wishlist_id": wl.id,
                "user_id": user.telegram_id,
                "role": member.role.value,
            },
        )
        return {"wishlist_id": wl.id, "role": member.role.value}

    return await execute(request, action)
