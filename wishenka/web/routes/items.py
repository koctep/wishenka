"""RESTful wish items endpoints with multi-quantity accounting, RBAC, and Surprise Invariant."""

import logging
from collections.abc import Awaitable, Callable
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request, status

from wishenka.auth.dependencies import get_current_user, get_optional_current_user
from wishenka.auth.models import AuthenticatedUser
from wishenka.items.schemas import CreateItemDTO, ReorderItemsDTO, UpdateItemDTO
from wishenka.web.dependencies import WishlistReadRepo, WishlistRepo
from wishenka.wishlists.exceptions import (
    CannotReduceQuantityBelowReservedError,
    InventoryBusyError,
    ItemNotFoundError,
    NothingRemainingError,
    PermissionDeniedError,
    WishlistArchivedError,
    WishlistDeletedError,
    WishlistNotFoundError,
)
from wishenka.wishlists.repo_ops import RepoWishlistOps
from wishenka.wishlists.repository import WishlistRepository
from wishenka.wishlists.schemas import (
    WishItemGifterViewDTO,
    WishItemRecipientViewDTO,
)
from wishenka.wishlists.service import WishlistService, project_wish_item

router = APIRouter(prefix="/api/wishlists/{wishlist_id}/items", tags=["items"])
logger = logging.getLogger("wishenka.web.items")

User = Annotated[AuthenticatedUser, Depends(get_current_user)]
OptionalUser = Annotated[AuthenticatedUser | None, Depends(get_optional_current_user)]


async def execute[T](
    request: Request,
    action: Callable[[Any], Awaitable[T]],
    *,
    repo: WishlistRepository | None = None,
    item_id: int | None = None,
) -> T:
    """Run an item operation against WishlistRepository or execute_wish."""
    operation = getattr(request.scope.get("endpoint"), "__name__", "")
    try:
        if item_id is not None:
            result = cast(
                T,
                await request.app.state.wishlist_store.execute_wish(
                    action,
                    item_id=item_id,
                    operation_name=operation or "wish_inventory",
                ),
            )
        elif repo is not None:
            result = await action(RepoWishlistOps(repo))
        else:
            raise RuntimeError("WishlistRepository dependency is required")
        return result
    except InventoryBusyError as exc:
        busy_context: dict[str, object] = {
            "event": "item_inventory_busy",
            "operation": operation,
        }
        if item_id is not None:
            busy_context["item_id"] = item_id
        logger.warning(
            "Item operation busy: %s",
            operation,
            extra=busy_context,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except (WishlistNotFoundError, WishlistDeletedError, ItemNotFoundError) as exc:
        logger.warning(
            "Item operation not found: %s (%s)",
            operation,
            exc,
            extra={"event": "item_not_found", "operation": operation},
        )
        raise HTTPException(status_code=404, detail="Resource not found") from exc
    except PermissionDeniedError as exc:
        logger.warning(
            "Item operation permission denied: %s",
            operation,
            extra={"event": "item_permission_denied", "operation": operation},
        )
        raise HTTPException(status_code=403, detail="Forbidden") from exc
    except (
        WishlistArchivedError,
        CannotReduceQuantityBelowReservedError,
        NothingRemainingError,
    ) as exc:
        logger.warning(
            "Item operation conflict: %s (%s)",
            operation,
            exc,
            extra={"event": "item_conflict", "operation": operation},
        )
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        logger.warning(
            "Item operation validation error: %s (%s)",
            operation,
            exc,
            extra={"event": "item_validation_error", "operation": operation},
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=WishItemRecipientViewDTO | WishItemGifterViewDTO,
)
async def create_item(
    wishlist_id: int,
    payload: CreateItemDTO,
    user: User,
    request: Request,
    repo: WishlistRepo,
) -> WishItemRecipientViewDTO | WishItemGifterViewDTO:
    """Create a new wish item with auto-incremented display_order."""

    async def action(svc: Any) -> WishItemRecipientViewDTO | WishItemGifterViewDTO:
        item = await svc.add_wish_item(
            wishlist_id=wishlist_id,
            actor=user,
            title=payload.title,
            description=payload.description,
            link=payload.link,
            image_url=payload.image_url,
            price=payload.price,
            currency=payload.currency,
            quantity=payload.quantity,
            priority=payload.priority,
            category=payload.category,
            recipient_user_id=payload.recipient_user_id,
            recipient_name=payload.recipient_name,
        )
        return project_wish_item(item, user)

    return await execute(request, action, repo=repo)


@router.get(
    "",
    response_model=list[WishItemRecipientViewDTO | WishItemGifterViewDTO],
)
async def list_items(
    wishlist_id: int,
    request: Request,
    user: OptionalUser,
    repo: WishlistReadRepo,
    include_archived: bool = False,
) -> list[WishItemRecipientViewDTO | WishItemGifterViewDTO]:
    """List wishlist items sorted by display_order adhering to Surprise Invariant."""

    async def action(
        svc: Any,
    ) -> list[WishItemRecipientViewDTO | WishItemGifterViewDTO]:
        return cast(
            list[WishItemRecipientViewDTO | WishItemGifterViewDTO],
            await svc.list_wish_items(
                wishlist_id=wishlist_id,
                actor=user,
                include_archived=include_archived,
            ),
        )

    return await execute(request, action, repo=repo)


@router.put(
    "/reorder",
    response_model=list[WishItemRecipientViewDTO | WishItemGifterViewDTO],
)
async def reorder_items(
    wishlist_id: int,
    payload: ReorderItemsDTO,
    user: User,
    request: Request,
    repo: WishlistRepo,
) -> list[WishItemRecipientViewDTO | WishItemGifterViewDTO]:
    """Atomically reorder active wishlist items."""

    async def action(
        svc: Any,
    ) -> list[WishItemRecipientViewDTO | WishItemGifterViewDTO]:
        return cast(
            list[WishItemRecipientViewDTO | WishItemGifterViewDTO],
            await svc.reorder_wish_items(
                wishlist_id=wishlist_id,
                actor=user,
                item_ids=payload.item_ids,
            ),
        )

    return await execute(request, action, repo=repo)


@router.get(
    "/{item_id}",
    response_model=WishItemRecipientViewDTO | WishItemGifterViewDTO,
)
async def get_item(
    wishlist_id: int,
    item_id: int,
    request: Request,
    user: OptionalUser,
    repo: WishlistReadRepo,
) -> WishItemRecipientViewDTO | WishItemGifterViewDTO:
    """Get single wish item view projected for the caller."""

    async def action(svc: Any) -> WishItemRecipientViewDTO | WishItemGifterViewDTO:
        return cast(
            WishItemRecipientViewDTO | WishItemGifterViewDTO,
            await svc.get_wish_item(
                wishlist_id=wishlist_id,
                item_id=item_id,
                actor=user,
            ),
        )

    return await execute(request, action, repo=repo)


@router.patch(
    "/{item_id}",
    response_model=WishItemRecipientViewDTO | WishItemGifterViewDTO,
)
async def update_item(
    wishlist_id: int,
    item_id: int,
    payload: UpdateItemDTO,
    user: User,
    request: Request,
) -> WishItemRecipientViewDTO | WishItemGifterViewDTO:
    """Update wish item properties enforcing Reduction Lock invariant."""

    async def action(svc: WishlistService) -> WishItemRecipientViewDTO | WishItemGifterViewDTO:
        item = await svc.update_wish_item(
            item_id=item_id,
            actor=user,
            title=payload.title,
            description=payload.description,
            link=payload.link,
            image_url=payload.image_url,
            price=payload.price,
            currency=payload.currency,
            quantity=payload.quantity,
            priority=payload.priority,
            category=payload.category,
            recipient_user_id=payload.recipient_user_id,
            recipient_name=payload.recipient_name,
            wishlist_id=wishlist_id,
        )
        return project_wish_item(item, user)

    return await execute(request, action, item_id=item_id)


@router.post(
    "/{item_id}/archive",
    response_model=WishItemRecipientViewDTO | WishItemGifterViewDTO,
)
async def archive_item(
    wishlist_id: int,
    item_id: int,
    user: User,
    request: Request,
    repo: WishlistRepo,
) -> WishItemRecipientViewDTO | WishItemGifterViewDTO:
    """Safely archive a wish item, preserving existing reservations."""

    async def action(svc: Any) -> WishItemRecipientViewDTO | WishItemGifterViewDTO:
        return cast(
            WishItemRecipientViewDTO | WishItemGifterViewDTO,
            await svc.archive_wish_item(
                wishlist_id=wishlist_id,
                item_id=item_id,
                actor=user,
            ),
        )

    return await execute(request, action, repo=repo)


@router.post(
    "/{item_id}/restore",
    response_model=WishItemRecipientViewDTO | WishItemGifterViewDTO,
)
async def restore_item(
    wishlist_id: int,
    item_id: int,
    user: User,
    request: Request,
    repo: WishlistRepo,
) -> WishItemRecipientViewDTO | WishItemGifterViewDTO:
    """Restore an archived wish item, appending it to the end of the active list."""

    async def action(svc: Any) -> WishItemRecipientViewDTO | WishItemGifterViewDTO:
        return cast(
            WishItemRecipientViewDTO | WishItemGifterViewDTO,
            await svc.restore_wish_item(
                wishlist_id=wishlist_id,
                item_id=item_id,
                actor=user,
            ),
        )

    return await execute(request, action, repo=repo)
