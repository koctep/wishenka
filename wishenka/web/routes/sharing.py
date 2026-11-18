"""HTMX views and FastAPI endpoints for wishlist sharing and collaboration."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse

from wishenka.auth.dependencies import get_current_user, get_optional_current_user
from wishenka.auth.models import AuthenticatedUser
from wishenka.i18n import t
from wishenka.i18n.dependencies import LocaleDep
from wishenka.web.templates import templates
from wishenka.wishlists.exceptions import (
    InvalidInviteTokenError,
    PermissionDeniedError,
    WishlistArchivedError,
    WishlistDeletedError,
    WishlistNotFoundError,
)
from wishenka.wishlists.models import WishlistRole, WishlistStatus
from wishenka.wishlists.policy import WishlistAccessPolicy
from wishenka.wishlists.schemas import WishItemGifterViewDTO
from wishenka.wishlists.service import WishlistService

router = APIRouter()
logger = logging.getLogger("wishenka.web.sharing")

CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
OptionalUser = Annotated[AuthenticatedUser | None, Depends(get_optional_current_user)]


def _get_service(request: Request) -> WishlistService:
    service = getattr(request.app.state, "wishlist_service", None)
    if service is None:
        service = getattr(request.app.state, "domain_service", None)
    if service is None:
        raise RuntimeError("Wishlist service not initialized")
    return cast(WishlistService, service)


@router.get("/share/{public_token}", response_class=HTMLResponse)
async def view_public_share(
    request: Request,
    public_token: str,
    current_user: OptionalUser,
    locale: LocaleDep,
) -> Response:
    """Render public wishlist page with Surprise Invariant enforcement."""
    service = _get_service(request)
    try:
        dto = await service.get_wishlist_by_public_token(public_token, current_user)
    except (WishlistNotFoundError, WishlistDeletedError) as exc:
        logger.warning(
            "Public share lookup failed: %s",
            exc,
            extra={"event": "wishlist_shared_view_failed"},
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wishlist not found",
        ) from exc

    is_recipient = any(getattr(item, "is_recipient", False) for item in dto.items) or (
        not dto.is_collaborative and dto.user_role == WishlistRole.OWNER
    )

    logger.info(
        "Wishlist shared view accessed: wishlist_id=%s is_recipient=%s is_collab=%s",
        dto.id,
        is_recipient,
        dto.is_collaborative,
        extra={
            "event": "wishlist_shared_view",
            "wishlist_id": dto.id,
            "is_recipient": is_recipient,
            "is_collaborative": dto.is_collaborative,
        },
    )

    return templates.TemplateResponse(
        request=request,
        name="share_wishlist.html",
        context={
            "wishlist": dto,
            "items": dto.items,
            "viewer_identified": current_user is not None,
            "wishlist_active": dto.status == WishlistStatus.ACTIVE,
            "locale": locale,
        },
    )


@router.get("/wishlists/{wishlist_id}/items/{item_id}/card", response_class=HTMLResponse)
async def get_item_card_partial(
    request: Request,
    wishlist_id: int,
    item_id: int,
    current_user: OptionalUser,
    locale: LocaleDep,
    notice: Annotated[str | None, Query()] = None,
    is_first: bool = False,
    is_last: bool = False,
) -> Response:
    """Render single item card HTMX partial adhering to Surprise Invariant."""
    service = _get_service(request)
    try:
        wishlist = await service.get_wishlist_by_id(wishlist_id)
        dto = await service.get_wishlist_view(wishlist_id, current_user)
    except (WishlistNotFoundError, WishlistDeletedError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wishlist not found",
        ) from exc

    item = next((i for i in dto.items if i.id == item_id), None)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )

    context_user = WishlistAccessPolicy.resolve_context(current_user, wishlist)
    visible_notice = notice if isinstance(item, WishItemGifterViewDTO) else None
    return templates.TemplateResponse(
        request=request,
        name="partials/item_card.html",
        context={
            "item": item,
            "wishlist_id": wishlist_id,
            "wishlist": dto,
            "viewer_identified": current_user is not None,
            "wishlist_active": wishlist.status == WishlistStatus.ACTIVE,
            "can_edit_wishlist": WishlistAccessPolicy.can_add_or_edit_item(context_user, wishlist),
            "is_member": context_user.is_member,
            "notice": visible_notice,
            "is_first": is_first,
            "is_last": is_last,
            "locale": locale,
        },
    )


@router.get("/invite/{invite_token}", response_class=HTMLResponse)
async def preview_invite(
    request: Request,
    invite_token: str,
    locale: LocaleDep,
) -> Response:
    """Render collaborator invitation preview or friendly error card."""
    service = _get_service(request)
    wl = await service.get_wishlist_by_invite_token(invite_token)
    now = datetime.now(UTC)

    if wl is None:
        logger.info(
            "Invite preview accessed: wishlist_id=None status=not_found",
            extra={
                "event": "invite_preview_accessed",
                "wishlist_id": None,
                "status": "not_found",
            },
        )
        return templates.TemplateResponse(
            request=request,
            name="invite_preview.html",
            context={
                "is_valid": False,
                "error": t("web.invite.invalid_or_expired", locale),
                "wishlist": None,
                "token": invite_token,
                "locale": locale,
            },
            status_code=status.HTTP_200_OK,
        )

    if wl.invite_token_expires_at is not None and wl.invite_token_expires_at < now:
        logger.info(
            "Invite preview accessed: wishlist_id=%s status=expired",
            wl.id,
            extra={
                "event": "invite_preview_accessed",
                "wishlist_id": wl.id,
                "status": "expired",
            },
        )
        return templates.TemplateResponse(
            request=request,
            name="invite_preview.html",
            context={
                "is_valid": False,
                "error": t("web.invite.invalid_or_expired", locale),
                "wishlist": None,
                "token": invite_token,
                "locale": locale,
            },
            status_code=status.HTTP_200_OK,
        )

    logger.info(
        "Invite preview accessed: wishlist_id=%s status=valid",
        wl.id,
        extra={
            "event": "invite_preview_accessed",
            "wishlist_id": wl.id,
            "status": "valid",
        },
    )
    return templates.TemplateResponse(
        request=request,
        name="invite_preview.html",
        context={
            "is_valid": True,
            "error": None,
            "wishlist": wl,
            "token": invite_token,
            "locale": locale,
        },
    )


@router.post("/invite/{invite_token}/join", response_class=HTMLResponse)
async def join_invite(
    request: Request,
    invite_token: str,
    user: CurrentUser,
    locale: LocaleDep,
) -> Response:
    """Accept invitation to join collaborative wishlist."""
    service = _get_service(request)
    try:
        member = await service.join_by_invite(invite_token, user)
    except (InvalidInviteTokenError, WishlistDeletedError, WishlistArchivedError) as exc:
        logger.warning(
            "Join wishlist failed for user %s: %s",
            user.telegram_id,
            exc,
            extra={
                "event": "invite_join_failed",
                "user_id": user.telegram_id,
            },
        )
        return templates.TemplateResponse(
            request=request,
            name="invite_preview.html",
            context={
                "is_valid": False,
                "error": t("web.invite.invalid_or_expired", locale),
                "wishlist": None,
                "token": invite_token,
                "locale": locale,
            },
            status_code=status.HTTP_200_OK,
        )

    role_val = member.role.value if hasattr(member.role, "value") else str(member.role)
    logger.info(
        "User joined wishlist via invite: wishlist_id=%s user_id=%s role=%s",
        member.wishlist_id,
        user.telegram_id,
        role_val,
        extra={
            "event": "invite_joined",
            "wishlist_id": member.wishlist_id,
            "user_id": user.telegram_id,
            "role": role_val,
        },
    )

    redirect_url = f"/share/{member.wishlist.public_token}" if member.wishlist else "/"
    return HTMLResponse(
        content=(
            "<div class='join-success p-4 bg-green-50 text-green-800 rounded'>"
            f"{t('web.invite.join_success', locale)}</div>"
        ),
        status_code=status.HTTP_200_OK,
        headers={"HX-Redirect": redirect_url},
    )


@router.get("/wishlists/{wishlist_id}/members/partial", response_class=HTMLResponse)
async def get_members_partial(
    request: Request,
    wishlist_id: int,
    user: CurrentUser,
    locale: LocaleDep,
) -> Response:
    """Render collaborator member list partial."""
    service = _get_service(request)
    try:
        wl = await service.get_wishlist_by_id(wishlist_id)
        members = await service.get_members(wishlist_id, user)
    except (WishlistNotFoundError, WishlistDeletedError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wishlist not found",
        ) from exc
    except PermissionDeniedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        ) from exc

    ctx = WishlistAccessPolicy.resolve_context(user, wl)
    return templates.TemplateResponse(
        request=request,
        name="partials/member_list.html",
        context={
            "wishlist_id": wl.id,
            "owner_id": wl.owner_id,
            "owner_name": wl.owner_name,
            "members": members,
            "is_owner": ctx.is_owner,
            "locale": locale,
        },
    )


@router.delete("/wishlists/{wishlist_id}/members/{user_id}/partial", response_class=HTMLResponse)
async def remove_member_partial(
    request: Request,
    wishlist_id: int,
    user_id: int,
    user: CurrentUser,
    locale: LocaleDep,
) -> Response:
    """Remove collaborator and return updated member list partial."""
    service = _get_service(request)
    try:
        wl = await service.get_wishlist_by_id(wishlist_id)
    except (WishlistNotFoundError, WishlistDeletedError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wishlist not found",
        ) from exc

    if wl.owner_id != user.telegram_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only owner can remove members",
        )

    try:
        await service.remove_member(wishlist_id, user, user_id)
        members = await service.get_members(wishlist_id, user)
    except PermissionDeniedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        ) from exc

    logger.info(
        "Member removed from wishlist: wishlist_id=%s removed_user_id=%s removed_by=%s",
        wishlist_id,
        user_id,
        user.telegram_id,
        extra={
            "event": "member_removed",
            "wishlist_id": wishlist_id,
            "removed_user_id": user_id,
            "removed_by": user.telegram_id,
        },
    )

    return templates.TemplateResponse(
        request=request,
        name="partials/member_list.html",
        context={
            "wishlist_id": wl.id,
            "owner_id": wl.owner_id,
            "owner_name": wl.owner_name,
            "members": members,
            "is_owner": True,
            "locale": locale,
        },
    )


@router.get("/wishlists/{wishlist_id}/share-modal", response_class=HTMLResponse)
async def get_share_modal(
    request: Request,
    wishlist_id: int,
    user: CurrentUser,
    locale: LocaleDep,
) -> Response:
    """Render share modal partial for owner."""
    service = _get_service(request)
    try:
        wl = await service.get_wishlist_by_id(wishlist_id)
    except (WishlistNotFoundError, WishlistDeletedError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wishlist not found",
        ) from exc

    if wl.owner_id != user.telegram_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only owner can access share modal",
        )

    return templates.TemplateResponse(
        request=request,
        name="partials/share_modal.html",
        context={
            "wishlist_id": wl.id,
            "public_token": wl.public_token,
            "invite_token": wl.invite_token,
            "locale": locale,
        },
    )


@router.post("/wishlists/{wishlist_id}/invite/regenerate", response_class=HTMLResponse)
async def regenerate_invite_token(
    request: Request,
    wishlist_id: int,
    user: CurrentUser,
    locale: LocaleDep,
) -> Response:
    """Regenerate invite token and return updated share modal partial."""
    service = _get_service(request)
    try:
        wl = await service.get_wishlist_by_id(wishlist_id)
    except (WishlistNotFoundError, WishlistDeletedError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wishlist not found",
        ) from exc

    if wl.owner_id != user.telegram_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only owner can regenerate invite token",
        )

    try:
        new_token = await service.regenerate_invite_token(wishlist_id, user)
    except PermissionDeniedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        ) from exc

    logger.info(
        "Invite token regenerated: wishlist_id=%s user_id=%s",
        wishlist_id,
        user.telegram_id,
        extra={
            "event": "invite_regenerated",
            "wishlist_id": wishlist_id,
            "user_id": user.telegram_id,
        },
    )

    return templates.TemplateResponse(
        request=request,
        name="partials/share_modal.html",
        context={
            "wishlist_id": wl.id,
            "public_token": wl.public_token,
            "invite_token": new_token,
            "locale": locale,
        },
    )
