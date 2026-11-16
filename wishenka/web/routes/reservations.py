"""Authenticated promise actions for one wish.

A recipient receives a fixed refusal. A gifter receives the promise that
just changed, plus the existing wish view.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request, status

from wishenka.auth.dependencies import get_current_user
from wishenka.auth.models import AuthenticatedUser
from wishenka.wishlists.exceptions import (
    InsufficientQuantityError,
    InventoryBusyError,
    ItemNotFoundError,
    PermissionDeniedError,
    ReservationError,
    ReservationNotFoundError,
    SelfReservationError,
    WishlistArchivedError,
    WishlistDeletedError,
    WishlistNotFoundError,
)
from wishenka.wishlists.schemas import PromiseActionDTO, ReservationQuantityDTO
from wishenka.wishlists.service import (
    RESERVATION_QUANTITY_MIN_ERROR,
    WishlistService,
    project_reservation_action,
)

router = APIRouter(
    prefix="/api/wishlists/{wishlist_id}/items/{item_id}/reservations",
    tags=["reservations"],
)
logger = logging.getLogger("wishenka.web.reservations")

User = Annotated[AuthenticatedUser, Depends(get_current_user)]


def _request_scope(
    operation: str,
    *,
    item_id: int | None,
    reservation_id: int | None,
) -> dict[str, object]:
    """Path ids for a promise action. Absent ids are omitted."""
    scope: dict[str, object] = {"operation": operation}
    if item_id is not None:
        scope["item_id"] = item_id
    if reservation_id is not None:
        scope["reservation_id"] = reservation_id
    return scope


def _log_refused(
    operation: str,
    http_status: int,
    *,
    item_id: int | None,
    reservation_id: int | None,
) -> None:
    """Log a fixed 403 or 404 without a gifter id or an existence flag."""
    logger.warning(
        "Reservation action refused: %s",
        operation,
        extra={
            "event": "reservation_action_refused",
            "http_status": http_status,
            **_request_scope(
                operation,
                item_id=item_id,
                reservation_id=reservation_id,
            ),
        },
    )


def _log_completed(operation: str, result: PromiseActionDTO) -> None:
    """Log one completed promise without the gifter or the wish graph."""
    logger.info(
        "Reservation action completed: %s item %s reservation %s status %s",
        operation,
        result.wish_item_id,
        result.reservation_id,
        result.status,
        extra={
            "event": "reservation_action_completed",
            "operation": operation,
            "item_id": result.wish_item_id,
            "reservation_id": result.reservation_id,
            "status": str(result.status),
        },
    )


async def execute[T](
    request: Request,
    action: Callable[[WishlistService], Awaitable[T]],
    *,
    item_id: int | None = None,
    reservation_id: int | None = None,
) -> T:
    """Run one promise action through the existing wish transaction."""
    operation = getattr(request.scope.get("endpoint"), "__name__", "")
    try:
        injected = getattr(request.app.state, "wishlist_service", None)
        if injected is not None:
            result = await action(injected)
        else:
            # The store accepts one wish key. Both path ids stay on the log.
            result = cast(
                T,
                await request.app.state.wishlist_store.execute_wish(
                    action,
                    item_id=None if reservation_id is not None else item_id,
                    reservation_id=reservation_id,
                    operation_name=operation or "wish_inventory",
                ),
            )
    except InventoryBusyError as exc:
        logger.warning(
            "Reservation operation busy: %s",
            operation,
            extra={
                "event": "reservation_inventory_busy",
                **_request_scope(
                    operation,
                    item_id=item_id,
                    reservation_id=reservation_id,
                ),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except SelfReservationError as exc:
        _log_refused(
            operation,
            status.HTTP_403_FORBIDDEN,
            item_id=item_id,
            reservation_id=reservation_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot promise this wish",
        ) from exc
    except (
        ReservationNotFoundError,
        ItemNotFoundError,
        WishlistNotFoundError,
        WishlistDeletedError,
    ) as exc:
        _log_refused(
            operation,
            status.HTTP_404_NOT_FOUND,
            item_id=item_id,
            reservation_id=reservation_id,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found",
        ) from exc
    except PermissionDeniedError as exc:
        logger.warning(
            "Reservation operation forbidden: %s",
            operation,
            extra={
                "event": "reservation_permission_denied",
                **_request_scope(
                    operation,
                    item_id=item_id,
                    reservation_id=reservation_id,
                ),
            },
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden") from exc
    except (InsufficientQuantityError, ReservationError, WishlistArchivedError) as exc:
        logger.warning(
            "Reservation operation conflict: %s",
            operation,
            extra={
                "event": "reservation_conflict",
                **_request_scope(
                    operation,
                    item_id=item_id,
                    reservation_id=reservation_id,
                ),
            },
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        logger.warning(
            "Reservation operation validation error: %s",
            operation,
            extra={
                "event": "reservation_validation_error",
                **_request_scope(
                    operation,
                    item_id=item_id,
                    reservation_id=reservation_id,
                ),
            },
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if isinstance(result, PromiseActionDTO):
        _log_completed(operation, result)
    return result


@router.post("", status_code=status.HTTP_201_CREATED, response_model=PromiseActionDTO)
async def create_reservation(
    wishlist_id: int,
    item_id: int,
    payload: ReservationQuantityDTO,
    user: User,
    request: Request,
) -> PromiseActionDTO:
    """Promise a positive number of units of a wish the caller does not receive."""
    if payload.quantity < 1:
        logger.warning(
            "Reservation operation validation error: %s",
            "create_reservation",
            extra={
                "event": "reservation_validation_error",
                **_request_scope("create_reservation", item_id=item_id, reservation_id=None),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=RESERVATION_QUANTITY_MIN_ERROR,
        )

    async def action(svc: WishlistService) -> PromiseActionDTO:
        reservation = await svc.create_reservation(
            item_id,
            user,
            payload.quantity,
            wishlist_id=wishlist_id,
        )
        return project_reservation_action(reservation, user)

    return await execute(request, action, item_id=item_id)


@router.patch("/{reservation_id}", response_model=PromiseActionDTO)
async def update_reservation_quantity(
    wishlist_id: int,
    item_id: int,
    reservation_id: int,
    payload: ReservationQuantityDTO,
    user: User,
    request: Request,
) -> PromiseActionDTO:
    """Raise or lower one intended or purchased promise owned by the caller."""

    async def action(svc: WishlistService) -> PromiseActionDTO:
        reservation = await svc.update_reservation_quantity(
            reservation_id,
            user,
            payload.quantity,
            wishlist_id=wishlist_id,
            item_id=item_id,
        )
        return project_reservation_action(reservation, user)

    return await execute(
        request,
        action,
        item_id=item_id,
        reservation_id=reservation_id,
    )


@router.post("/{reservation_id}/cancel", response_model=PromiseActionDTO)
async def cancel_reservation(
    wishlist_id: int,
    item_id: int,
    reservation_id: int,
    user: User,
    request: Request,
) -> PromiseActionDTO:
    """Cancel one promise owned by the caller and free its units."""

    async def action(svc: WishlistService) -> PromiseActionDTO:
        reservation = await svc.cancel_reservation(
            reservation_id,
            user,
            wishlist_id=wishlist_id,
            item_id=item_id,
        )
        return project_reservation_action(reservation, user)

    return await execute(
        request,
        action,
        item_id=item_id,
        reservation_id=reservation_id,
    )


@router.post("/{reservation_id}/purchase", response_model=PromiseActionDTO)
async def purchase_reservation(
    wishlist_id: int,
    item_id: int,
    reservation_id: int,
    user: User,
    request: Request,
) -> PromiseActionDTO:
    """Mark one intended promise owned by the caller as purchased."""

    async def action(svc: WishlistService) -> PromiseActionDTO:
        reservation = await svc.mark_reservation_purchased(
            reservation_id,
            user,
            wishlist_id=wishlist_id,
            item_id=item_id,
        )
        return project_reservation_action(reservation, user)

    return await execute(
        request,
        action,
        item_id=item_id,
        reservation_id=reservation_id,
    )


@router.post("/{reservation_id}/undo-purchase", response_model=PromiseActionDTO)
async def undo_reservation_purchase(
    wishlist_id: int,
    item_id: int,
    reservation_id: int,
    user: User,
    request: Request,
) -> PromiseActionDTO:
    """Return one purchased promise owned by the caller to intended."""

    async def action(svc: WishlistService) -> PromiseActionDTO:
        reservation = await svc.revert_reservation_to_active(
            reservation_id,
            user,
            wishlist_id=wishlist_id,
            item_id=item_id,
        )
        return project_reservation_action(reservation, user)

    return await execute(
        request,
        action,
        item_id=item_id,
        reservation_id=reservation_id,
    )
