"""Authenticated wishlist management and public sharing endpoints."""

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from wishenka.auth.dependencies import get_current_user, get_optional_current_user
from wishenka.auth.models import AuthenticatedUser
from wishenka.wishlists.exceptions import (
    PermissionDeniedError,
    WishlistArchivedError,
    WishlistDeletedError,
    WishlistNotFoundError,
)
from wishenka.wishlists.models import Wishlist, WishlistStatus
from wishenka.wishlists.policy import WishlistAccessPolicy
from wishenka.wishlists.service import WishlistService

router = APIRouter()
logger = logging.getLogger("wishenka.web.wishlists")
User = Annotated[AuthenticatedUser, Depends(get_current_user)]
OptionalUser = Annotated[AuthenticatedUser | None, Depends(get_optional_current_user)]


class WishlistInput(BaseModel):
    """Editable optional wishlist details."""

    name: str | None = None
    description: str | None = None
    event_title: str | None = None
    event_date: datetime | None = None


async def execute[T](request: Request, action: Callable[[WishlistService], Awaitable[T]]) -> T:
    """Run an operation against the configured transactional or injected test service."""
    try:
        injected = getattr(request.app.state, "wishlist_service", None)
        if injected is not None:
            result = await action(injected)
        else:
            result = cast(T, await request.app.state.wishlist_store.execute(action))
        operation = getattr(request.scope.get("endpoint"), "__name__", "")
        if operation in {"create_wishlist", "update_wishlist", "change_status", "reset_share"}:
            logger.info(
                "Wishlist mutation committed: %s",
                operation,
                extra={"event": "wishlist_mutation_committed", "operation": operation},
            )
        return result
    except (WishlistNotFoundError, WishlistDeletedError, PermissionDeniedError) as exc:
        raise HTTPException(status_code=404, detail="Wishlist not found") from exc
    except WishlistArchivedError as exc:
        raise HTTPException(status_code=409, detail="Wishlist is archived") from exc


def require_member(wishlist: Wishlist, user: AuthenticatedUser, manager: bool = False) -> None:
    """Reject non-members and non-managers without revealing whether a list exists."""
    ctx = WishlistAccessPolicy.resolve_context(user, wishlist)
    if not (ctx.is_admin if manager else ctx.is_member):
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
        if ctx.is_admin:
            result["share_token"] = wishlist.public_token
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
            raise HTTPException(status_code=409, detail="Wishlist is archived")
        for key, value in body.model_dump(exclude_unset=True).items():
            setattr(
                wl, "title" if key == "name" else key, value if key != "name" else (value or "")
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
            raise HTTPException(status_code=409, detail="Invalid wishlist state")
        return projection(wl, user, False)

    return await execute(request, action)


@router.post("/api/wishlists/{wishlist_id}/share/reset")
async def reset_share(request: Request, wishlist_id: int, user: User) -> dict[str, Any]:
    async def action(service: WishlistService) -> dict[str, Any]:
        wl = await service.get_wishlist_by_id(wishlist_id)
        require_member(wl, user, manager=True)
        if wl.status != WishlistStatus.ACTIVE:
            raise HTTPException(status_code=409, detail="Wishlist is archived")
        old = wl.public_token
        for _ in range(5):
            await service.regenerate_public_token(wishlist_id, user)
            if wl.public_token != old:
                break
        else:
            raise HTTPException(status_code=503, detail="Could not generate sharing link")
        return projection(wl, user, False)

    return await execute(request, action)


@router.get("/api/public/wishlists/{token}")
async def public_wishlist(request: Request, token: str, user: OptionalUser) -> dict[str, Any]:
    async def action(service: WishlistService) -> dict[str, Any]:
        wl = next((w for w in service._wishlists.values() if w.public_token == token), None)
        if wl is None or wl.status == WishlistStatus.DELETED:
            raise HTTPException(status_code=404, detail="Wishlist not found")
        return projection(wl, user, True)

    return await execute(request, action)
