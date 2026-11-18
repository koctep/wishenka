"""HTMX UI endpoints for wish item quick-add, live link preview, and detailed editing."""

from __future__ import annotations

import html
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Annotated, Any, NoReturn, cast

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse
from markupsafe import Markup

from wishenka.auth.dependencies import get_current_user, get_optional_current_user
from wishenka.auth.models import AuthenticatedUser
from wishenka.currency import DEFAULT_CURRENCY
from wishenka.i18n import DEFAULT_LOCALE, SupportedLocale, t
from wishenka.i18n.dependencies import LocaleDep
from wishenka.items.classifier import UniversalInputClassifier
from wishenka.items.models import InputType, ItemPriority
from wishenka.items.parser import extract_domain
from wishenka.items.service import ItemPreviewService
from wishenka.web.gifted_view import (
    RECEIPT_REFUSAL_HEADER,
    GiftedRow,
    nothing_remaining_text,
    oob_text,
    read_gifted_rows,
)
from wishenka.web.templates import templates
from wishenka.wishlists.exceptions import (
    CannotReduceQuantityBelowReservedError,
    InventoryBusyError,
    ItemNotFoundError,
    NothingRemainingError,
    PermissionDeniedError,
    WishlistArchivedError,
    WishlistDeletedError,
    WishlistError,
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


def _editor_card_flags() -> dict[str, bool]:
    """Flags for a card rendered after an identified active-list check (a list member)."""
    return {"viewer_identified": True, "wishlist_active": True, "is_member": True}


def _ensure_member_and_active(wishlist: Wishlist, user: AuthenticatedUser) -> None:
    """Validate that caller is a member of the wishlist and that the wishlist is active."""
    ctx = WishlistAccessPolicy.resolve_context(user, wishlist)
    if not ctx.is_member:
        raise PermissionDeniedError("Caller is not a member of this wishlist")
    if wishlist.status == WishlistStatus.ARCHIVED:
        raise WishlistArchivedError(f"Wishlist {wishlist.id} is archived")
    if wishlist.status == WishlistStatus.DELETED:
        raise WishlistDeletedError(f"Wishlist {wishlist.id} is deleted")


def _collaborative_members(
    wishlist: Wishlist, locale: SupportedLocale = DEFAULT_LOCALE
) -> list[dict[str, Any]]:
    """Build list of collaborative wishlist members for recipient selection."""
    if not wishlist.is_collaborative:
        return []
    owner_label = wishlist.owner_name or t(
        "web.common.member_fallback", locale, id=wishlist.owner_id
    )
    members: list[dict[str, Any]] = [
        {
            "user_id": wishlist.owner_id,
            "display_name": t("web.common.owner_suffix", locale, name=owner_label),
        }
    ]
    for member in wishlist.members:
        if member.user_id != wishlist.owner_id:
            members.append(
                {
                    "user_id": member.user_id,
                    "display_name": t("web.common.member_fallback", locale, id=member.user_id),
                }
            )
    return members


_RETARGET_MODAL_HEADERS = {
    "HX-Retarget": "#item-modal-container",
    "HX-Reswap": "innerHTML",
}

# Domain errors that modal/UI handlers translate: archived -> 409, all others -> 404.
_DOMAIN_ERRORS = (
    WishlistNotFoundError,
    WishlistDeletedError,
    ItemNotFoundError,
    PermissionDeniedError,
    WishlistArchivedError,
)


def _oob_modal_notice(message: str, status_code: int) -> HTMLResponse:
    """Close any open item modal and display an escaped notice in ``#list-notice``."""
    content = f"{oob_text('item-modal-container')}\n{oob_text('list-notice', message)}"
    return HTMLResponse(content=content, status_code=status_code)


def _modal_domain_error_response(
    exc: Exception,
    locale: SupportedLocale,
    *,
    wishlist_id: int | None = None,
    item_id: int | None = None,
    actor_id: int | None = None,
    operation: str = "modal",
) -> HTMLResponse:
    """Return an OOB HTML error notice for archived or missing modal resources."""
    is_archived = isinstance(exc, WishlistArchivedError)
    status_code = status.HTTP_409_CONFLICT if is_archived else status.HTTP_404_NOT_FOUND
    logger.warning(
        "Modal %s failed with %s (wishlist=%s, item=%s, status=%s)",
        operation,
        type(exc).__name__,
        wishlist_id,
        item_id,
        status_code,
        extra={
            "event": "ui_modal_domain_error",
            "operation": operation,
            "error_type": type(exc).__name__,
            "status_code": status_code,
            "wishlist_id": wishlist_id,
            "item_id": item_id,
            "actor_id": actor_id,
            "user_id": actor_id,
        },
    )
    if is_archived:
        return _oob_modal_notice(
            t("web.item.archived_wishlist_error", locale),
            status.HTTP_409_CONFLICT,
        )
    return _oob_modal_notice(
        t("web.item.resource_not_found", locale),
        status.HTTP_404_NOT_FOUND,
    )


def _render_edit_modal_error(
    request: Request,
    *,
    wishlist_id: int,
    form_data: dict[str, Any],
    locked_quantity: int,
    is_collaborative: bool,
    collaborative_members: list[dict[str, Any]],
    error_message: str,
    status_code: int,
    is_edit: bool = True,
) -> Response:
    """Render the edit modal with an error banner and retarget to ``#item-modal-container``."""
    return templates.TemplateResponse(
        request=request,
        name="partials/item_edit_modal.html",
        context={
            "is_edit": is_edit,
            "wishlist_id": wishlist_id,
            "form": form_data,
            "locked_quantity": locked_quantity,
            "min_quantity": max(1, locked_quantity),
            "is_collaborative": is_collaborative,
            "collaborative_members": collaborative_members,
            "error_message": error_message,
        },
        status_code=status_code,
        headers=_RETARGET_MODAL_HEADERS,
    )


def _parse_optional_int(raw: str | None, locale: SupportedLocale = DEFAULT_LOCALE) -> int | None:
    """Parse an optional form string into an integer or None."""
    if raw is None or not raw.strip():
        return None
    try:
        return int(raw.strip())
    except ValueError as exc:
        raise ValueError(t("web.item.invalid_numeric", locale)) from exc


def _parse_priority(raw: str | None, locale: SupportedLocale = DEFAULT_LOCALE) -> ItemPriority:
    """Parse item priority string into ItemPriority enum."""
    if not raw or not raw.strip():
        return ItemPriority.MEDIUM
    try:
        return ItemPriority(raw.strip().lower())
    except ValueError as exc:
        raise ValueError(t("web.item.invalid_priority", locale)) from exc


@router.get("", response_class=HTMLResponse)
async def view_wishlist_detail(
    wishlist_id: int,
    request: Request,
    current_user: OptionalUser,
    locale: LocaleDep,
) -> Response:
    """Render main TMA wishlist detail page with RBAC-gated Quick Add Bar and edit triggers."""

    async def action(
        svc: WishlistService,
    ) -> tuple[WishlistDetailViewDTO, bool, bool, bool, bool, list[GiftedRow] | None]:
        wl = await svc.get_wishlist_by_id(wishlist_id)
        dto = await svc.get_wishlist_view(wishlist_id, current_user)
        ctx = WishlistAccessPolicy.resolve_context(current_user, wl)
        can_edit_wishlist = WishlistAccessPolicy.can_add_or_edit_item(ctx, wl)
        can_view_gifted = WishlistAccessPolicy.can_view_gifted(ctx, wl)
        gifted = (
            await read_gifted_rows(svc, wishlist_id, current_user, locale)
            if can_view_gifted
            else None
        )
        return (
            dto,
            can_edit_wishlist,
            wl.status == WishlistStatus.ACTIVE,
            ctx.is_member,
            can_view_gifted,
            gifted,
        )

    try:
        (
            dto,
            can_edit_wishlist,
            wishlist_active,
            is_member,
            can_view_gifted,
            gifted_rows,
        ) = await _execute(request, action)
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
            "viewer_identified": current_user is not None,
            "wishlist_active": wishlist_active,
            "is_member": is_member,
            "can_view_gifted": can_view_gifted,
            "gifted_rows": gifted_rows,
            "locale": locale,
        },
    )


@router.post("/items/preview", response_class=HTMLResponse)
async def preview_item_input(
    wishlist_id: int,
    request: Request,
    user: User,
    locale: LocaleDep,
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
    locale: LocaleDep,
    raw_input: Annotated[str, Form()] = "",
    title: Annotated[str | None, Form()] = None,
    link: Annotated[str | None, Form()] = None,
    price: Annotated[str | None, Form()] = None,
    currency: Annotated[str, Form()] = DEFAULT_CURRENCY,
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
        logger.warning(
            "Quick add validation failed (empty_title) in wishlist %s",
            wishlist_id,
            extra={
                "event": "ui_item_quick_add_validation_error",
                "reason": "empty_title",
                "status_code": status.HTTP_400_BAD_REQUEST,
                "wishlist_id": wishlist_id,
                "actor_id": user.telegram_id,
                "user_id": user.telegram_id,
            },
        )
        return _oob_modal_notice(t("web.item.empty_title", locale), status.HTTP_400_BAD_REQUEST)

    try:
        parsed_price = _parse_optional_int(price, locale)
        parsed_recipient_uid = _parse_optional_int(recipient_user_id, locale)
        parsed_priority = _parse_priority(priority, locale)
    except ValueError as exc:
        logger.warning(
            "Quick add validation failed (parse_error) in wishlist %s",
            wishlist_id,
            extra={
                "event": "ui_item_quick_add_validation_error",
                "reason": "parse_error",
                "status_code": status.HTTP_400_BAD_REQUEST,
                "wishlist_id": wishlist_id,
                "actor_id": user.telegram_id,
                "user_id": user.telegram_id,
            },
        )
        return _oob_modal_notice(str(exc), status.HTTP_400_BAD_REQUEST)
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
            currency=(currency or DEFAULT_CURRENCY).strip() or DEFAULT_CURRENCY,
            quantity=quantity,
            priority=parsed_priority,
            category=clean_cat,
            recipient_user_id=parsed_recipient_uid,
            recipient_name=clean_recip_name,
        )
        return project_wish_item(item, user)

    try:
        projected_item = await _execute(request, action)
    except (
        WishlistNotFoundError,
        WishlistDeletedError,
        PermissionDeniedError,
        WishlistArchivedError,
    ) as exc:
        return _modal_domain_error_response(
            exc,
            locale,
            wishlist_id=wishlist_id,
            actor_id=user.telegram_id,
            operation="quick_add",
        )
    except ValueError as exc:
        logger.warning(
            "Quick add validation failed (domain_validation) in wishlist %s",
            wishlist_id,
            extra={
                "event": "ui_item_quick_add_validation_error",
                "reason": "domain_validation",
                "status_code": status.HTTP_400_BAD_REQUEST,
                "wishlist_id": wishlist_id,
                "actor_id": user.telegram_id,
                "user_id": user.telegram_id,
            },
        )
        return _oob_modal_notice(str(exc), status.HTTP_400_BAD_REQUEST)

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
            "locale": locale,
            **_editor_card_flags(),
        }
    )
    placeholder = html.escape(t("web.item.quick_add_placeholder", locale), quote=True)
    oob_html = (
        f'<div id="quick-add-preview-target" hx-swap-oob="innerHTML"></div>\n'
        f'<input type="text" id="quick-add-input" name="raw_input" value="" '
        f'placeholder="{placeholder}" autocomplete="off" '
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
    locale: LocaleDep,
    raw_input: str | None = None,
    title: str | None = None,
    link: str | None = None,
    price: int | None = None,
    currency: str = DEFAULT_CURRENCY,
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
        return wl.is_collaborative, _collaborative_members(wl, locale)

    try:
        is_collaborative, collaborative_members = await _execute(request, action)
    except (
        WishlistNotFoundError,
        WishlistDeletedError,
        PermissionDeniedError,
        WishlistArchivedError,
    ) as exc:
        return _modal_domain_error_response(
            exc,
            locale,
            wishlist_id=wishlist_id,
            actor_id=user.telegram_id,
            operation="new_item_modal",
        )

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
        "currency": currency or DEFAULT_CURRENCY,
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
    locale: LocaleDep,
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
            "currency": item.currency or DEFAULT_CURRENCY,
            "quantity": item.quantity,
            "priority": item.priority.value,
            "category": item.category or "",
            "image_url": item.image_url or "",
            "recipient_user_id": item.recipient_user_id,
            "recipient_name": item.recipient_name or "",
        }
        return safe_form, locked_qty, wl.is_collaborative, _collaborative_members(wl, locale)

    try:
        form_data, locked_quantity, is_collaborative, collaborative_members = await _execute(
            request, action
        )
    except _DOMAIN_ERRORS as exc:
        return _modal_domain_error_response(
            exc,
            locale,
            wishlist_id=wishlist_id,
            item_id=item_id,
            actor_id=user.telegram_id,
            operation="edit_item_modal",
        )

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
    locale: LocaleDep,
    title: Annotated[str, Form()] = "",
    link: Annotated[str | None, Form()] = None,
    price: Annotated[str | None, Form()] = None,
    currency: Annotated[str, Form()] = DEFAULT_CURRENCY,
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
    clean_link = link.strip() if link is not None else None
    clean_desc = description.strip() if description is not None else None
    clean_image = image_url.strip() if image_url is not None else None
    clean_cat = category.strip() if category is not None else None
    clean_recip_name = recipient_name.strip() if recipient_name is not None else None
    clean_currency = (currency or DEFAULT_CURRENCY).strip() or DEFAULT_CURRENCY

    submitted_form: dict[str, Any] = {
        "id": item_id,
        "title": clean_title,
        "description": clean_desc or "",
        "link": clean_link or "",
        "price": price.strip() if price and price.strip() else None,
        "currency": clean_currency,
        "quantity": quantity,
        "priority": (priority or "medium").strip().lower() or "medium",
        "category": clean_cat or "",
        "image_url": clean_image or "",
        "recipient_user_id": recipient_user_id.strip() if recipient_user_id else None,
        "recipient_name": clean_recip_name or "",
    }

    validation_error: str | None = None
    parsed_price: int | None = None
    parsed_recipient_uid: int | None = None
    parsed_priority = ItemPriority.MEDIUM
    if not clean_title:
        validation_error = t("web.item.empty_title", locale)
    else:
        try:
            parsed_price = _parse_optional_int(price, locale)
            parsed_recipient_uid = _parse_optional_int(recipient_user_id, locale)
            parsed_priority = _parse_priority(priority, locale)
        except ValueError as exc:
            validation_error = str(exc)

    if validation_error is not None:
        logger.warning(
            "Item edit validation failed (form) for item %s in wishlist %s",
            item_id,
            wishlist_id,
            extra={
                "event": "ui_item_edit_validation_error",
                "stage": "form",
                "status_code": status.HTTP_400_BAD_REQUEST,
                "wishlist_id": wishlist_id,
                "item_id": item_id,
                "actor_id": user.telegram_id,
                "user_id": user.telegram_id,
            },
        )
        return _render_edit_modal_error(
            request,
            wishlist_id=wishlist_id,
            form_data=submitted_form,
            locked_quantity=0,
            is_collaborative=False,
            collaborative_members=[],
            error_message=validation_error,
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    submitted_form["price"] = parsed_price
    submitted_form["recipient_user_id"] = parsed_recipient_uid
    submitted_form["priority"] = parsed_priority.value

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
        collaborative_members_snapshot = _collaborative_members(wl, locale)

        updated = await svc.update_wish_item(
            item_id=item_id,
            actor=user,
            title=clean_title,
            description=clean_desc,
            link=clean_link,
            image_url=clean_image,
            price=parsed_price,
            currency=(currency or DEFAULT_CURRENCY).strip() or DEFAULT_CURRENCY,
            quantity=quantity,
            priority=parsed_priority,
            category=clean_cat,
            recipient_user_id=parsed_recipient_uid,
            recipient_name=clean_recip_name,
            wishlist_id=wishlist_id,
        )
        return project_wish_item(updated, user)

    try:
        injected = getattr(request.app.state, "wishlist_service", None)
        if injected is not None:
            projected_item = await action(injected)
        else:
            projected_item = await request.app.state.wishlist_store.execute_wish(
                action,
                item_id=item_id,
                operation_name="submit_edit_item",
            )
    except InventoryBusyError:
        logger.warning(
            "Item edit was not saved because the wish was busy (item %s)",
            item_id,
            extra={
                "event": "ui_item_edit_busy",
                "wishlist_id": wishlist_id,
                "item_id": item_id,
            },
        )
        return _render_edit_modal_error(
            request,
            wishlist_id=wishlist_id,
            form_data=submitted_form,
            locked_quantity=locked_quantity_snapshot,
            is_collaborative=is_collaborative_snapshot,
            collaborative_members=collaborative_members_snapshot,
            error_message=t("web.item.edit_busy_error", locale),
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
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
        error_msg = t(
            "web.item.quantity_below_reserved",
            locale,
            count=locked_quantity_snapshot,
        )
        return _render_edit_modal_error(
            request,
            wishlist_id=wishlist_id,
            form_data=submitted_form,
            locked_quantity=locked_quantity_snapshot,
            is_collaborative=is_collaborative_snapshot,
            collaborative_members=collaborative_members_snapshot,
            error_message=error_msg,
            status_code=status.HTTP_409_CONFLICT,
        )
    except _DOMAIN_ERRORS as exc:
        return _modal_domain_error_response(
            exc,
            locale,
            wishlist_id=wishlist_id,
            item_id=item_id,
            actor_id=user.telegram_id,
            operation="submit_edit_item",
        )
    except ValueError as exc:
        logger.warning(
            "Item edit validation failed (domain) for item %s in wishlist %s",
            item_id,
            wishlist_id,
            extra={
                "event": "ui_item_edit_validation_error",
                "stage": "domain",
                "status_code": status.HTTP_400_BAD_REQUEST,
                "wishlist_id": wishlist_id,
                "item_id": item_id,
                "actor_id": user.telegram_id,
                "user_id": user.telegram_id,
            },
        )
        return _render_edit_modal_error(
            request,
            wishlist_id=wishlist_id,
            form_data=submitted_form,
            locked_quantity=locked_quantity_snapshot,
            is_collaborative=is_collaborative_snapshot,
            collaborative_members=collaborative_members_snapshot,
            error_message=str(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

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
            "locale": locale,
            **_editor_card_flags(),
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
    locale: SupportedLocale = DEFAULT_LOCALE,
) -> str:
    """Render the archived items section as an out-of-band outerHTML swap."""
    return templates.get_template("partials/archived_items_section.html").render(
        {
            "request": request,
            "wishlist_id": wishlist_id,
            "archived_items": archived_items,
            "can_edit_wishlist": True,
            "oob": True,
            "locale": locale,
        }
    )


def _items_list_html(
    request: Request,
    wishlist_id: int,
    items: list[WishItemRecipientViewDTO | WishItemGifterViewDTO],
    locale: SupportedLocale = DEFAULT_LOCALE,
) -> str:
    """Render the active items list partial for the editor view."""
    return templates.get_template("partials/items_list.html").render(
        {
            "request": request,
            "wishlist_id": wishlist_id,
            "items": items,
            "can_edit_wishlist": True,
            "locale": locale,
            **_editor_card_flags(),
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


async def _nothing_remaining_response(
    request: Request,
    wishlist_id: int,
    user: AuthenticatedUser,
    locale: SupportedLocale = DEFAULT_LOCALE,
) -> HTMLResponse:
    """Stale archive or restore of a fully received wish: 409 with out-of-band fragments only.

    Every top-level element carries ``hx-swap-oob`` so nothing lands in the card or list target.
    The refreshed list, archive and gifted sections are one extra read; a failed read degrades
    to the dialog close and the notice.
    """

    async def action(
        svc: WishlistService,
    ) -> tuple[
        list[WishItemRecipientViewDTO | WishItemGifterViewDTO],
        list[WishItemRecipientViewDTO],
        list[GiftedRow] | None,
    ]:
        items = await svc.list_wish_items(wishlist_id=wishlist_id, actor=user)
        view = await svc.get_wishlist_view(wishlist_id, user)
        return items, view.archived_items, await read_gifted_rows(svc, wishlist_id, user, locale)

    parts: list[str] = [
        oob_text("item-modal-container"),
        oob_text("list-notice", nothing_remaining_text(locale)),
    ]
    try:
        items, archived, gifted = await _execute(request, action)
    except WishlistError:
        pass
    else:
        list_html = _items_list_html(request, wishlist_id, items, locale)
        parts.append(
            Markup('<div hx-swap-oob="innerHTML:#items-list">{}</div>').format(Markup(list_html))
        )
        parts.append(_archived_section_html(request, wishlist_id, archived, locale))
        parts.append(
            templates.get_template("partials/gifted_items_section.html").render(
                {"request": request, "gifted_rows": gifted, "oob": True, "locale": locale}
            )
        )
    return HTMLResponse(
        content="\n".join(parts),
        status_code=status.HTTP_409_CONFLICT,
        headers={RECEIPT_REFUSAL_HEADER: "nothing_remaining"},
    )


# Marker of the stale reorder 400 (read by wishlist.js); a closed value, not a receipt reason.
REORDER_REFUSAL_HEADER = "X-Reorder-Refusal"


async def _reordered_response(
    request: Request,
    wishlist_id: int,
    user: AuthenticatedUser,
    reorder: Callable[[list[int]], list[int]],
    locale: SupportedLocale = DEFAULT_LOCALE,
) -> HTMLResponse:
    """Apply a reorder computed from the current order and render the new list."""

    async def action(
        svc: WishlistService,
    ) -> list[WishItemRecipientViewDTO | WishItemGifterViewDTO]:
        wl = await svc.get_wishlist_by_id(wishlist_id)
        _ensure_member_and_active(wl, user)
        current = await svc.list_wish_items(wishlist_id=wishlist_id, actor=user)
        current_ids = [it.id for it in current]
        new_ids = reorder(current_ids)
        if new_ids != current_ids:
            await svc.reorder_wish_items(wishlist_id=wishlist_id, actor=user, item_ids=new_ids)
        return await svc.list_wish_items(wishlist_id=wishlist_id, actor=user)

    try:
        items = await _execute(request, action)
    except _DOMAIN_ERRORS as exc:
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
            headers={REORDER_REFUSAL_HEADER: "stale_order"},
        ) from exc
    return HTMLResponse(content=_items_list_html(request, wishlist_id, items, locale))


@router.post("/items/reorder", response_class=HTMLResponse)
async def reorder_items_ui(
    wishlist_id: int,
    request: Request,
    user: User,
    locale: LocaleDep,
    item_ids: Annotated[list[int], Form()],
) -> Response:
    """Persist a full manual order of active items and return the re-rendered list."""
    response = await _reordered_response(
        request, wishlist_id, user, lambda _current: item_ids, locale
    )
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
    locale: LocaleDep,
    direction: Annotated[str, Query(pattern="^(up|down)$")],
) -> Response:
    """Move one item a single step up or down and return the re-rendered list."""

    def compute(current: list[int]) -> list[int]:
        if item_id not in current:
            raise ItemNotFoundError(f"Item {item_id} not found")
        idx = current.index(item_id)
        target = idx - 1 if direction == "up" else idx + 1
        result = list(current)
        if 0 <= target < len(result):
            result[idx], result[target] = result[target], result[idx]
        return result

    response = await _reordered_response(request, wishlist_id, user, compute, locale)
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
    locale: LocaleDep,
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
    except _DOMAIN_ERRORS as exc:
        return _modal_domain_error_response(
            exc,
            locale,
            wishlist_id=wishlist_id,
            item_id=item_id,
            actor_id=user.telegram_id,
            operation="archive_confirm",
        )

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
            "has_received": item.received_quantity > 0,
        },
    )


@router.post("/items/{item_id}/archive", response_class=HTMLResponse)
async def archive_item_ui(
    wishlist_id: int,
    item_id: int,
    request: Request,
    user: User,
    locale: LocaleDep,
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
    except NothingRemainingError:
        return await _nothing_remaining_response(request, wishlist_id, user, locale)
    except _DOMAIN_ERRORS as exc:
        return _modal_domain_error_response(
            exc,
            locale,
            wishlist_id=wishlist_id,
            item_id=item_id,
            actor_id=user.telegram_id,
            operation="archive_item",
        )

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
        f"{_archived_section_html(request, wishlist_id, archived, locale)}"
    )
    return HTMLResponse(content=oob_html, status_code=status.HTTP_200_OK)


@router.post("/items/{item_id}/restore", response_class=HTMLResponse)
async def restore_item_ui(
    wishlist_id: int,
    item_id: int,
    request: Request,
    user: User,
    locale: LocaleDep,
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
    except NothingRemainingError:
        return await _nothing_remaining_response(request, wishlist_id, user, locale)
    except _DOMAIN_ERRORS as exc:
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
            "locale": locale,
            **_editor_card_flags(),
        }
    )
    return HTMLResponse(
        content=(
            f"{card_html}\n"
            '<div id="empty-items-placeholder" hx-swap-oob="delete"></div>\n'
            f"{_archived_section_html(request, wishlist_id, archived, locale)}"
        )
    )
