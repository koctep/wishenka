"""HTMX UI endpoints for wish item quick-add, live link preview, and detailed editing."""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Annotated, Any, NoReturn, cast

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse

from wishenka.auth.dependencies import get_current_user, get_optional_current_user
from wishenka.auth.models import AuthenticatedUser
from wishenka.items.classifier import UniversalInputClassifier
from wishenka.items.models import InputType, ItemPriority
from wishenka.items.parser import extract_domain
from wishenka.items.service import ItemPreviewService
from wishenka.web.templates import templates
from wishenka.wishlists.exceptions import (
    CannotReduceQuantityBelowReservedError,
    ItemNotFoundError,
    PermissionDeniedError,
    WishlistArchivedError,
    WishlistDeletedError,
    WishlistNotFoundError,
)
from wishenka.wishlists.models import Wishlist, WishlistStatus
from wishenka.wishlists.policy import WishlistAccessPolicy
from wishenka.wishlists.schemas import (
    WishItemGifterViewDTO,
    WishItemRecipientViewDTO,
    WishlistDetailViewDTO,
)
from wishenka.wishlists.service import WishlistService, project_wish_item

router = APIRouter(prefix="/web/wishlists/{wishlist_id}", tags=["items-ui"])
logger = logging.getLogger("wishenka.web.items_ui")

User = Annotated[AuthenticatedUser, Depends(get_current_user)]
OptionalUser = Annotated[AuthenticatedUser | None, Depends(get_optional_current_user)]


async def _execute[T](request: Request, action: Callable[[WishlistService], Awaitable[T]]) -> T:
    """Execute a domain operation inside transactional storage or injected test service."""
    injected = getattr(request.app.state, "wishlist_service", None)
    if injected is not None:
        return await action(injected)
    return cast(T, await request.app.state.wishlist_store.execute(action))


def _ensure_member_and_active(wishlist: Wishlist, user: AuthenticatedUser) -> None:
    """Validate that caller is a member of the wishlist and that the wishlist is active."""
    ctx = WishlistAccessPolicy.resolve_context(user, wishlist)
    if not ctx.is_member:
        raise PermissionDeniedError("Caller is not a member of this wishlist")
    if wishlist.status == WishlistStatus.ARCHIVED:
        raise WishlistArchivedError(f"Wishlist {wishlist.id} is archived")
    if wishlist.status == WishlistStatus.DELETED:
        raise WishlistDeletedError(f"Wishlist {wishlist.id} is deleted")


def _collaborative_members(wishlist: Wishlist) -> list[dict[str, Any]]:
    """Build list of collaborative wishlist members for recipient selection."""
    if not wishlist.is_collaborative:
        return []
    owner_label = wishlist.owner_name or f"Участник #{wishlist.owner_id}"
    members: list[dict[str, Any]] = [
        {"user_id": wishlist.owner_id, "display_name": f"{owner_label} (Владелец)"}
    ]
    for member in wishlist.members:
        if member.user_id != wishlist.owner_id:
            members.append(
                {
                    "user_id": member.user_id,
                    "display_name": f"Участник #{member.user_id}",
                }
            )
    return members


def _parse_optional_int(raw: str | None) -> int | None:
    """Parse an optional form string into an integer or None."""
    if raw is None or not raw.strip():
        return None
    try:
        return int(raw.strip())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid numeric value",
        ) from exc


def _parse_priority(raw: str | None) -> ItemPriority:
    """Parse item priority string into ItemPriority enum."""
    if not raw or not raw.strip():
        return ItemPriority.MEDIUM
    try:
        return ItemPriority(raw.strip().lower())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid priority value",
        ) from exc


@router.get("", response_class=HTMLResponse)
async def view_wishlist_detail(
    wishlist_id: int,
    request: Request,
    current_user: OptionalUser,
) -> Response:
    """Render main TMA wishlist detail page with RBAC-gated Quick Add Bar and edit triggers."""

    async def action(svc: WishlistService) -> tuple[WishlistDetailViewDTO, bool]:
        wl = await svc.get_wishlist_by_id(wishlist_id)
        dto = await svc.get_wishlist_view(wishlist_id, current_user)
        ctx = WishlistAccessPolicy.resolve_context(current_user, wl)
        can_edit_wishlist = WishlistAccessPolicy.can_add_or_edit_item(ctx, wl)
        return dto, can_edit_wishlist

    try:
        dto, can_edit_wishlist = await _execute(request, action)
    except (WishlistNotFoundError, WishlistDeletedError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wishlist not found",
        ) from exc

    return templates.TemplateResponse(
        request=request,
        name="wishlist_detail.html",
        context={
            "wishlist": dto,
            "wishlist_id": dto.id,
            "items": dto.items,
            "can_edit_wishlist": can_edit_wishlist,
        },
    )


@router.post("/items/preview", response_class=HTMLResponse)
async def preview_item_input(
    wishlist_id: int,
    request: Request,
    user: User,
    raw_input: Annotated[str, Form()] = "",
) -> Response:
    """Classify universal input and render live URL preview card or empty response."""

    async def verify_access(svc: WishlistService) -> None:
        wl = await svc.get_wishlist_by_id(wishlist_id)
        _ensure_member_and_active(wl, user)

    try:
        await _execute(request, verify_access)
    except (WishlistNotFoundError, WishlistDeletedError, PermissionDeniedError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wishlist not found",
        ) from exc
    except WishlistArchivedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Wishlist is archived",
        ) from exc

    start_time = time.perf_counter()
    classification = UniversalInputClassifier.classify(raw_input)
    if classification.input_type == InputType.PLAIN_TEXT:
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.info(
            "Quick add preview classified as plain text for wishlist %s",
            wishlist_id,
            extra={
                "event": "ui_item_quick_add_preview",
                "wishlist_id": wishlist_id,
                "actor_id": user.telegram_id,
                "user_id": user.telegram_id,
                "input_type": InputType.PLAIN_TEXT.value,
                "domain": None,
                "is_fallback": False,
                "store_name": None,
                "duration_ms": duration_ms,
            },
        )
        return HTMLResponse(content="", status_code=status.HTTP_200_OK)

    preview_service: ItemPreviewService = (
        getattr(request.app.state, "item_preview_service", None) or ItemPreviewService()
    )
    preview = await preview_service.fetch_preview(raw_input)
    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
    domain = extract_domain(preview.url or classification.normalized_url)
    logger.info(
        "Quick add URL preview rendered for wishlist %s (domain=%s, store=%s, fallback=%s)",
        wishlist_id,
        domain,
        preview.store_name,
        preview.is_fallback,
        extra={
            "event": "ui_item_quick_add_preview",
            "wishlist_id": wishlist_id,
            "actor_id": user.telegram_id,
            "user_id": user.telegram_id,
            "input_type": preview.input_type.value,
            "domain": domain,
            "is_fallback": preview.is_fallback,
            "store_name": preview.store_name,
            "duration_ms": duration_ms,
        },
    )
    return templates.TemplateResponse(
        request=request,
        name="partials/item_preview_card.html",
        context={
            "preview": preview,
            "wishlist_id": wishlist_id,
            "raw_input": raw_input,
        },
    )


@router.post("/items/quick", response_class=HTMLResponse)
async def quick_add_item(
    wishlist_id: int,
    request: Request,
    user: User,
    raw_input: Annotated[str, Form()] = "",
    title: Annotated[str | None, Form()] = None,
    link: Annotated[str | None, Form()] = None,
    price: Annotated[str | None, Form()] = None,
    currency: Annotated[str, Form()] = "RUB",
    image_url: Annotated[str | None, Form()] = None,
    store_name: Annotated[str | None, Form()] = None,
    description: Annotated[str | None, Form()] = None,
    quantity: Annotated[int, Form()] = 1,
    priority: Annotated[str, Form()] = "medium",
    category: Annotated[str | None, Form()] = None,
    recipient_user_id: Annotated[str | None, Form()] = None,
    recipient_name: Annotated[str | None, Form()] = None,
) -> Response:
    """Create a wish item from Quick Add Bar or modal and return card with OOB resets."""
    effective_title = title.strip() if title and title.strip() else raw_input.strip()
    if not effective_title:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Название желания не может быть пустым",
        )

    parsed_price = _parse_optional_int(price)
    parsed_recipient_uid = _parse_optional_int(recipient_user_id)
    parsed_priority = _parse_priority(priority)
    clean_link = link.strip() if link and link.strip() else None
    clean_image = image_url.strip() if image_url and image_url.strip() else None
    clean_desc = description.strip() if description and description.strip() else None
    clean_cat = category.strip() if category and category.strip() else None
    clean_recip_name = recipient_name.strip() if recipient_name and recipient_name.strip() else None

    async def action(
        svc: WishlistService,
    ) -> WishItemRecipientViewDTO | WishItemGifterViewDTO:
        wl = await svc.get_wishlist_by_id(wishlist_id)
        _ensure_member_and_active(wl, user)
        item = await svc.add_wish_item(
            wishlist_id=wishlist_id,
            actor=user,
            title=effective_title,
            description=clean_desc,
            link=clean_link,
            image_url=clean_image,
            store_name=store_name.strip() if store_name and store_name.strip() else None,
            price=parsed_price,
            currency=(currency or "RUB").strip() or "RUB",
            quantity=quantity,
            priority=parsed_priority,
            category=clean_cat,
            recipient_user_id=parsed_recipient_uid,
            recipient_name=clean_recip_name,
        )
        return project_wish_item(item, user)

    try:
        projected_item = await _execute(request, action)
    except (WishlistNotFoundError, WishlistDeletedError, PermissionDeniedError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wishlist not found",
        ) from exc
    except WishlistArchivedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Wishlist is archived",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    logger.info(
        "Wish item %s quick-added to wishlist %s by actor %s",
        projected_item.id,
        wishlist_id,
        user.telegram_id,
        extra={
            "event": "ui_item_quick_add_success",
            "wishlist_id": wishlist_id,
            "item_id": projected_item.id,
            "actor_id": user.telegram_id,
            "user_id": user.telegram_id,
            "has_link": bool(projected_item.link),
            "price": projected_item.price,
            "quantity": projected_item.quantity,
        },
    )

    card_html = templates.get_template("partials/item_card.html").render(
        {
            "request": request,
            "item": projected_item,
            "wishlist_id": wishlist_id,
            "can_edit_wishlist": True,
        }
    )
    oob_html = (
        f'<div id="quick-add-preview-target" hx-swap-oob="innerHTML"></div>\n'
        f'<input type="text" id="quick-add-input" name="raw_input" value="" '
        f'placeholder="Вставьте ссылку или название желания..." autocomplete="off" '
        f'hx-post="/web/wishlists/{wishlist_id}/items/preview" '
        f'hx-trigger="input changed delay:500ms, paste" '
        f'hx-target="#quick-add-preview-target" hx-swap="innerHTML" '
        f'hx-swap-oob="true" />\n'
        f'<div id="empty-items-placeholder" hx-swap-oob="delete"></div>\n'
        f'<div id="item-modal-container" hx-swap-oob="innerHTML"></div>'
    )
    return HTMLResponse(
        content=f"{card_html}\n{oob_html}",
        status_code=status.HTTP_201_CREATED,
    )


@router.get("/items/new", response_class=HTMLResponse)
async def get_new_item_modal(
    wishlist_id: int,
    request: Request,
    user: User,
    raw_input: str | None = None,
    title: str | None = None,
    link: str | None = None,
    price: int | None = None,
    currency: str = "RUB",
    image_url: str | None = None,
    description: str | None = None,
    quantity: int = 1,
    priority: str = "medium",
    category: str | None = None,
) -> Response:
    """Render detailed item creation modal prepopulated from Quick Add or preview metadata."""

    async def action(svc: WishlistService) -> tuple[bool, list[dict[str, Any]]]:
        wl = await svc.get_wishlist_by_id(wishlist_id)
        _ensure_member_and_active(wl, user)
        return wl.is_collaborative, _collaborative_members(wl)

    try:
        is_collaborative, collaborative_members = await _execute(request, action)
    except (WishlistNotFoundError, WishlistDeletedError, PermissionDeniedError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wishlist not found",
        ) from exc
    except WishlistArchivedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Wishlist is archived",
        ) from exc

    resolved_title = title.strip() if title and title.strip() else ""
    resolved_link = link.strip() if link and link.strip() else ""
    if not resolved_title and raw_input and raw_input.strip():
        classification = UniversalInputClassifier.classify(raw_input)
        if classification.input_type == InputType.PLAIN_TEXT:
            resolved_title = classification.residual_text or raw_input.strip()
        else:
            if not resolved_link and classification.normalized_url:
                resolved_link = classification.normalized_url
            resolved_title = classification.residual_text or ""

    form_data: dict[str, Any] = {
        "id": None,
        "title": resolved_title,
        "link": resolved_link,
        "price": price,
        "currency": currency or "RUB",
        "quantity": max(1, quantity),
        "description": description or "",
        "image_url": image_url or "",
        "priority": priority or "medium",
        "category": category or "",
        "recipient_user_id": None,
        "recipient_name": "",
    }

    logger.info(
        "Item creation modal opened in wishlist %s by actor %s",
        wishlist_id,
        user.telegram_id,
        extra={
            "event": "ui_item_edit_opened",
            "wishlist_id": wishlist_id,
            "item_id": None,
            "actor_id": user.telegram_id,
            "user_id": user.telegram_id,
            "mode": "create",
            "locked_quantity": 0,
            "is_collaborative": is_collaborative,
        },
    )

    return templates.TemplateResponse(
        request=request,
        name="partials/item_edit_modal.html",
        context={
            "is_edit": False,
            "wishlist_id": wishlist_id,
            "form": form_data,
            "locked_quantity": 0,
            "min_quantity": 1,
            "is_collaborative": is_collaborative,
            "collaborative_members": collaborative_members,
            "error_message": None,
        },
    )


@router.get("/items/{item_id}/edit", response_class=HTMLResponse)
async def get_edit_item_modal(
    wishlist_id: int,
    item_id: int,
    request: Request,
    user: User,
) -> Response:
    """Render detailed item edit modal enforcing Reduction Lock and Surprise Invariant."""

    async def action(
        svc: WishlistService,
    ) -> tuple[dict[str, Any], int, bool, list[dict[str, Any]]]:
        wl = await svc.get_wishlist_by_id(wishlist_id)
        _ensure_member_and_active(wl, user)
        item = svc._items.get(item_id)
        if item is None or item.wishlist_id != wishlist_id:
            raise ItemNotFoundError(f"Item {item_id} not found")
        locked_qty = item.reserved_quantity + item.received_quantity
        # Surprise Invariant: Never expose item.reservations or gifter identities
        safe_form: dict[str, Any] = {
            "id": item.id,
            "title": item.title,
            "description": item.description or "",
            "link": item.link or "",
            "price": item.price,
            "currency": item.currency or "RUB",
            "quantity": item.quantity,
            "priority": item.priority.value,
            "category": item.category or "",
            "image_url": item.image_url or "",
            "recipient_user_id": item.recipient_user_id,
            "recipient_name": item.recipient_name or "",
        }
        return safe_form, locked_qty, wl.is_collaborative, _collaborative_members(wl)

    try:
        form_data, locked_quantity, is_collaborative, collaborative_members = await _execute(
            request, action
        )
    except (
        WishlistNotFoundError,
        WishlistDeletedError,
        ItemNotFoundError,
        PermissionDeniedError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found",
        ) from exc
    except WishlistArchivedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Wishlist is archived",
        ) from exc

    logger.info(
        "Item edit modal opened for item %s in wishlist %s (locked_quantity=%s)",
        item_id,
        wishlist_id,
        locked_quantity,
        extra={
            "event": "ui_item_edit_opened",
            "wishlist_id": wishlist_id,
            "item_id": item_id,
            "actor_id": user.telegram_id,
            "user_id": user.telegram_id,
            "mode": "edit",
            "locked_quantity": locked_quantity,
            "is_collaborative": is_collaborative,
        },
    )
    if locked_quantity > 0:
        logger.info(
            "Reduction Lock rendered for item %s in wishlist %s (locked_quantity=%s)",
            item_id,
            wishlist_id,
            locked_quantity,
            extra={
                "event": "ui_reduction_lock_rendered",
                "wishlist_id": wishlist_id,
                "item_id": item_id,
                "actor_id": user.telegram_id,
                "user_id": user.telegram_id,
                "locked_quantity": locked_quantity,
            },
        )

    return templates.TemplateResponse(
        request=request,
        name="partials/item_edit_modal.html",
        context={
            "is_edit": True,
            "wishlist_id": wishlist_id,
            "form": form_data,
            "locked_quantity": locked_quantity,
            "min_quantity": max(1, locked_quantity),
            "is_collaborative": is_collaborative,
            "collaborative_members": collaborative_members,
            "error_message": None,
        },
    )


@router.post("/items/{item_id}/edit", response_class=HTMLResponse)
async def submit_edit_item(
    wishlist_id: int,
    item_id: int,
    request: Request,
    user: User,
    title: Annotated[str, Form()] = "",
    link: Annotated[str | None, Form()] = None,
    price: Annotated[str | None, Form()] = None,
    currency: Annotated[str, Form()] = "RUB",
    quantity: Annotated[int, Form()] = 1,
    description: Annotated[str | None, Form()] = None,
    image_url: Annotated[str | None, Form()] = None,
    priority: Annotated[str, Form()] = "medium",
    category: Annotated[str | None, Form()] = None,
    recipient_user_id: Annotated[str | None, Form()] = None,
    recipient_name: Annotated[str | None, Form()] = None,
) -> Response:
    """Save item edits or re-render modal with 409 Conflict if Reduction Lock is violated."""
    clean_title = title.strip()
    if not clean_title:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Название желания не может быть пустым",
        )

    parsed_price = _parse_optional_int(price)
    parsed_recipient_uid = _parse_optional_int(recipient_user_id)
    parsed_priority = _parse_priority(priority)
    clean_link = link.strip() if link is not None else None
    clean_desc = description.strip() if description is not None else None
    clean_image = image_url.strip() if image_url is not None else None
    clean_cat = category.strip() if category is not None else None
    clean_recip_name = recipient_name.strip() if recipient_name is not None else None

    submitted_form: dict[str, Any] = {
        "id": item_id,
        "title": clean_title,
        "description": clean_desc or "",
        "link": clean_link or "",
        "price": parsed_price,
        "currency": (currency or "RUB").strip() or "RUB",
        "quantity": quantity,
        "priority": parsed_priority.value,
        "category": clean_cat or "",
        "image_url": clean_image or "",
        "recipient_user_id": parsed_recipient_uid,
        "recipient_name": clean_recip_name or "",
    }

    locked_quantity_snapshot = 0
    is_collaborative_snapshot = False
    collaborative_members_snapshot: list[dict[str, Any]] = []

    async def action(
        svc: WishlistService,
    ) -> WishItemRecipientViewDTO | WishItemGifterViewDTO:
        nonlocal locked_quantity_snapshot, is_collaborative_snapshot, collaborative_members_snapshot
        wl = await svc.get_wishlist_by_id(wishlist_id)
        _ensure_member_and_active(wl, user)
        existing = svc._items.get(item_id)
        if existing is None or existing.wishlist_id != wishlist_id:
            raise ItemNotFoundError(f"Item {item_id} not found")
        locked_quantity_snapshot = existing.reserved_quantity + existing.received_quantity
        is_collaborative_snapshot = wl.is_collaborative
        collaborative_members_snapshot = _collaborative_members(wl)

        updated = await svc.update_wish_item(
            item_id=item_id,
            actor=user,
            title=clean_title,
            description=clean_desc,
            link=clean_link,
            image_url=clean_image,
            price=parsed_price,
            currency=(currency or "RUB").strip() or "RUB",
            quantity=quantity,
            priority=parsed_priority,
            category=clean_cat,
            recipient_user_id=parsed_recipient_uid,
            recipient_name=clean_recip_name,
            wishlist_id=wishlist_id,
        )
        return project_wish_item(updated, user)

    try:
        projected_item = await _execute(request, action)
    except CannotReduceQuantityBelowReservedError:
        logger.warning(
            "UI Reduction Lock rejected quantity=%s (locked=%s) for item %s in wishlist %s",
            quantity,
            locked_quantity_snapshot,
            item_id,
            wishlist_id,
            extra={
                "event": "ui_reduction_lock_rejected",
                "wishlist_id": wishlist_id,
                "item_id": item_id,
                "actor_id": user.telegram_id,
                "user_id": user.telegram_id,
                "requested_quantity": quantity,
                "locked_quantity": locked_quantity_snapshot,
            },
        )
        error_msg = (
            f"Нельзя указать количество меньше забронированного дарителями объема "
            f"({locked_quantity_snapshot} шт.)."
        )
        return templates.TemplateResponse(
            request=request,
            name="partials/item_edit_modal.html",
            context={
                "is_edit": True,
                "wishlist_id": wishlist_id,
                "form": submitted_form,
                "locked_quantity": locked_quantity_snapshot,
                "min_quantity": max(1, locked_quantity_snapshot),
                "is_collaborative": is_collaborative_snapshot,
                "collaborative_members": collaborative_members_snapshot,
                "error_message": error_msg,
            },
            status_code=status.HTTP_409_CONFLICT,
        )
    except (
        WishlistNotFoundError,
        WishlistDeletedError,
        ItemNotFoundError,
        PermissionDeniedError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found",
        ) from exc
    except WishlistArchivedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Wishlist is archived",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    has_recipient = bool(parsed_recipient_uid is not None or clean_recip_name)
    logger.info(
        "Item %s in wishlist %s updated via UI by actor %s",
        item_id,
        wishlist_id,
        user.telegram_id,
        extra={
            "event": "ui_item_edit_saved",
            "wishlist_id": wishlist_id,
            "item_id": item_id,
            "actor_id": user.telegram_id,
            "user_id": user.telegram_id,
            "quantity": projected_item.quantity,
            "has_recipient": has_recipient,
        },
    )

    card_html = templates.get_template("partials/item_card.html").render(
        {
            "request": request,
            "item": projected_item,
            "wishlist_id": wishlist_id,
            "can_edit_wishlist": True,
        }
    )
    close_modal_oob = '<div id="item-modal-container" hx-swap-oob="innerHTML"></div>'
    return HTMLResponse(
        content=f"{card_html}\n{close_modal_oob}",
        status_code=status.HTTP_200_OK,
    )


def _archived_section_html(
    request: Request,
    wishlist_id: int,
    archived_items: list[WishItemRecipientViewDTO],
) -> str:
    """Render the archived items section as an out-of-band outerHTML swap."""
    return templates.get_template("partials/archived_items_section.html").render(
        {
            "request": request,
            "wishlist_id": wishlist_id,
            "archived_items": archived_items,
            "can_edit_wishlist": True,
            "oob": True,
        }
    )


def _items_list_html(
    request: Request,
    wishlist_id: int,
    items: list[WishItemRecipientViewDTO | WishItemGifterViewDTO],
) -> str:
    """Render the active items list partial for the editor view."""
    return templates.get_template("partials/items_list.html").render(
        {
            "request": request,
            "wishlist_id": wishlist_id,
            "items": items,
            "can_edit_wishlist": True,
        }
    )


def _raise_http(exc: Exception) -> NoReturn:
    """Translate domain exceptions into HTTP errors without leaking details."""
    if isinstance(exc, WishlistArchivedError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Wishlist is archived",
        ) from exc
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Resource not found",
    ) from exc


_NOT_FOUND_ERRORS = (
    WishlistNotFoundError,
    WishlistDeletedError,
    ItemNotFoundError,
    PermissionDeniedError,
    WishlistArchivedError,
)


async def _reordered_response(
    request: Request,
    wishlist_id: int,
    user: AuthenticatedUser,
    reorder: Callable[[WishlistService, list[int]], list[int]],
) -> HTMLResponse:
    """Apply a reorder computed from the current order and render the new list."""

    async def action(
        svc: WishlistService,
    ) -> list[WishItemRecipientViewDTO | WishItemGifterViewDTO]:
        wl = await svc.get_wishlist_by_id(wishlist_id)
        _ensure_member_and_active(wl, user)
        current = await svc.list_wish_items(wishlist_id=wishlist_id, actor=user)
        new_ids = reorder(svc, [it.id for it in current])
        if new_ids != [it.id for it in current]:
            await svc.reorder_wish_items(wishlist_id=wishlist_id, actor=user, item_ids=new_ids)
        return await svc.list_wish_items(wishlist_id=wishlist_id, actor=user)

    try:
        items = await _execute(request, action)
    except _NOT_FOUND_ERRORS as exc:
        _raise_http(exc)
    except ValueError as exc:
        logger.warning(
            "Invalid reorder rejected in wishlist %s for actor %s",
            wishlist_id,
            user.telegram_id,
            extra={
                "event": "ui_items_reorder_rejected",
                "wishlist_id": wishlist_id,
                "actor_id": user.telegram_id,
                "user_id": user.telegram_id,
                "reason": "invalid_permutation",
            },
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid item order",
        ) from exc
    return HTMLResponse(content=_items_list_html(request, wishlist_id, items))


@router.post("/items/reorder", response_class=HTMLResponse)
async def reorder_items_ui(
    wishlist_id: int,
    request: Request,
    user: User,
    item_ids: Annotated[list[int], Form()],
) -> Response:
    """Persist a full manual order of active items and return the re-rendered list."""
    response = await _reordered_response(request, wishlist_id, user, lambda _svc, _cur: item_ids)
    logger.info(
        "Items in wishlist %s reordered via UI by actor %s",
        wishlist_id,
        user.telegram_id,
        extra={
            "event": "ui_items_reordered",
            "wishlist_id": wishlist_id,
            "actor_id": user.telegram_id,
            "user_id": user.telegram_id,
            "item_count": len(item_ids),
        },
    )
    return response


@router.post("/items/{item_id}/move", response_class=HTMLResponse)
async def move_item_ui(
    wishlist_id: int,
    item_id: int,
    request: Request,
    user: User,
    direction: Annotated[str, Query(pattern="^(up|down)$")],
) -> Response:
    """Move one item a single step up or down and return the re-rendered list."""

    def compute(_svc: WishlistService, current: list[int]) -> list[int]:
        if item_id not in current:
            raise ItemNotFoundError(f"Item {item_id} not found")
        idx = current.index(item_id)
        target = idx - 1 if direction == "up" else idx + 1
        result = list(current)
        if 0 <= target < len(result):
            result[idx], result[target] = result[target], result[idx]
        return result

    response = await _reordered_response(request, wishlist_id, user, compute)
    logger.info(
        "Item %s in wishlist %s moved %s via UI by actor %s",
        item_id,
        wishlist_id,
        direction,
        user.telegram_id,
        extra={
            "event": "ui_item_moved",
            "wishlist_id": wishlist_id,
            "item_id": item_id,
            "actor_id": user.telegram_id,
            "user_id": user.telegram_id,
            "direction": direction,
        },
    )
    return response


@router.get("/items/{item_id}/archive-confirm", response_class=HTMLResponse)
async def archive_confirm_ui(
    wishlist_id: int,
    item_id: int,
    request: Request,
    user: User,
) -> Response:
    """Render the archive confirmation modal without exposing gifter identities."""

    async def action(svc: WishlistService) -> tuple[Any, bool, bool]:
        wl = await svc.get_wishlist_by_id(wishlist_id)
        _ensure_member_and_active(wl, user)
        ctx = WishlistAccessPolicy.resolve_context(user, wl)
        if not WishlistAccessPolicy.can_add_or_edit_item(ctx, wl):
            raise PermissionDeniedError("Caller cannot archive items")
        item = next((it for it in wl.items if it.id == item_id), None)
        if item is None:
            raise ItemNotFoundError(f"Item {item_id} not found")
        has_locked = item.reserved_quantity + item.received_quantity > 0
        return item, has_locked, wl.warn_on_delete_reserved

    try:
        item, has_locked, warn_pref = await _execute(request, action)
    except _NOT_FOUND_ERRORS as exc:
        _raise_http(exc)

    show_warning = has_locked and warn_pref
    logger.info(
        "Archive confirmation opened for item %s in wishlist %s by actor %s",
        item_id,
        wishlist_id,
        user.telegram_id,
        extra={
            "event": "ui_item_archive_confirm_opened",
            "wishlist_id": wishlist_id,
            "item_id": item_id,
            "actor_id": user.telegram_id,
            "user_id": user.telegram_id,
            "has_active_reservations": has_locked,
            "gifter_warning_shown": show_warning,
        },
    )
    return templates.TemplateResponse(
        request=request,
        name="partials/item_archive_modal.html",
        context={
            "item": {"id": item.id, "title": item.title},
            "wishlist_id": wishlist_id,
            "show_gifter_warning": show_warning,
            "warn_on_delete_reserved": warn_pref,
        },
    )


@router.post("/items/{item_id}/archive", response_class=HTMLResponse)
async def archive_item_ui(
    wishlist_id: int,
    item_id: int,
    request: Request,
    user: User,
    warn_on_delete_reserved: Annotated[list[str] | None, Form()] = None,
) -> Response:
    """Safely archive wish item via HTMX UI, updating list, modal and archive section."""
    warn_pref: bool | None = None
    if warn_on_delete_reserved:
        warn_pref = warn_on_delete_reserved[-1].strip().lower() in {"true", "1", "on", "yes"}

    async def action(svc: WishlistService) -> list[WishItemRecipientViewDTO]:
        wl = await svc.get_wishlist_by_id(wishlist_id)
        _ensure_member_and_active(wl, user)
        await svc.archive_wish_item(
            wishlist_id=wishlist_id,
            item_id=item_id,
            actor=user,
            warn_on_delete_reserved=warn_pref,
        )
        view = await svc.get_wishlist_view(wishlist_id, user)
        return view.archived_items

    try:
        archived = await _execute(request, action)
    except _NOT_FOUND_ERRORS as exc:
        _raise_http(exc)

    logger.info(
        "Item %s in wishlist %s archived via UI by actor %s",
        item_id,
        wishlist_id,
        user.telegram_id,
        extra={
            "event": "ui_item_archived",
            "wishlist_id": wishlist_id,
            "item_id": item_id,
            "actor_id": user.telegram_id,
            "user_id": user.telegram_id,
            "warn_on_delete_reserved": warn_pref,
        },
    )

    oob_html = (
        f'<div id="item-card-{item_id}" hx-swap-oob="delete"></div>\n'
        '<div id="item-modal-container" hx-swap-oob="innerHTML"></div>\n'
        f"{_archived_section_html(request, wishlist_id, archived)}"
    )
    return HTMLResponse(content=oob_html, status_code=status.HTTP_200_OK)


@router.post("/items/{item_id}/restore", response_class=HTMLResponse)
async def restore_item_ui(
    wishlist_id: int,
    item_id: int,
    request: Request,
    user: User,
) -> Response:
    """Restore an archived item: card appended to list, archive section updated OOB."""

    async def action(
        svc: WishlistService,
    ) -> tuple[WishItemRecipientViewDTO | WishItemGifterViewDTO, list[WishItemRecipientViewDTO]]:
        wl = await svc.get_wishlist_by_id(wishlist_id)
        _ensure_member_and_active(wl, user)
        restored = await svc.restore_wish_item(
            wishlist_id=wishlist_id,
            item_id=item_id,
            actor=user,
        )
        view = await svc.get_wishlist_view(wishlist_id, user)
        return restored, view.archived_items

    try:
        restored_item, archived = await _execute(request, action)
    except _NOT_FOUND_ERRORS as exc:
        _raise_http(exc)

    logger.info(
        "Item %s in wishlist %s restored via UI by actor %s",
        item_id,
        wishlist_id,
        user.telegram_id,
        extra={
            "event": "ui_item_restored",
            "wishlist_id": wishlist_id,
            "item_id": item_id,
            "actor_id": user.telegram_id,
            "user_id": user.telegram_id,
            "display_order": restored_item.display_order,
        },
    )

    card_html = templates.get_template("partials/item_card.html").render(
        {
            "request": request,
            "item": restored_item,
            "wishlist_id": wishlist_id,
            "can_edit_wishlist": True,
            "is_last": True,
        }
    )
    return HTMLResponse(
        content=(
            f"{card_html}\n"
            '<div id="empty-items-placeholder" hx-swap-oob="delete"></div>\n'
            f"{_archived_section_html(request, wishlist_id, archived)}"
        )
    )
