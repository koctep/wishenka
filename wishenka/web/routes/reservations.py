"""Authenticated promise actions for one wish.

A recipient receives a fixed refusal. A gifter receives the promise that
just changed, plus the existing wish view.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from wishenka.auth.dependencies import get_current_user
from wishenka.auth.models import AuthenticatedUser
from wishenka.notices.fence import delivery_lock, has_fence
from wishenka.web.idempotency import (
    build_replay_response,
    compute_request_hash,
    parse_idempotency_key,
    retention_hours_from_request,
    serialize_dto_response,
)
from wishenka.wishlists.exceptions import (
    IdempotencyConflictError,
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
    idempotency_key: str | None = None,
    actor_id: int | None = None,
    request_hash: str | None = None,
    response_status: int = status.HTTP_200_OK,
) -> T | Response:
    """Run one promise action through the existing wish transaction."""
    operation = getattr(request.scope.get("endpoint"), "__name__", "")
    try:
        if idempotency_key is not None:
            if actor_id is None or request_hash is None:
                raise ValueError("Idempotent execution requires actor_id and request_hash")

            async def serialized_action(svc: WishlistService) -> tuple[int, str, str]:
                dto = await action(svc)
                if isinstance(dto, PromiseActionDTO):
                    _log_completed(operation, dto)
                return serialize_dto_response(cast(PromiseActionDTO, dto), response_status)

            outcome = await request.app.state.wishlist_store.execute_wish_idempotent(
                serialized_action,
                actor_id=actor_id,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                retention_hours=retention_hours_from_request(request),
                item_id=None if reservation_id is not None else item_id,
                reservation_id=reservation_id,
                operation_name=operation or "wish_inventory",
                check_not_recipient=True,
            )
            return build_replay_response(outcome.status_code, outcome.content_type, outcome.body)
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
    except IdempotencyConflictError as exc:
        logger.warning(
            "Reservation idempotency conflict: %s",
            operation,
            extra={
                "event": "reservation_idempotency_conflict",
                "reason": "idempotency_conflict",
                **_request_scope(
                    operation,
                    item_id=item_id,
                    reservation_id=reservation_id,
                ),
            },
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (
        InsufficientQuantityError,
        ReservationError,
        WishlistArchivedError,
    ) as exc:
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
) -> PromiseActionDTO | Response:
    """Promise a positive number of units of a wish the caller does not receive."""
    idempotency_key = parse_idempotency_key(request)
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

    request_hash = (
        compute_request_hash(
            "create_reservation",
            {"wishlist_id": wishlist_id, "item_id": item_id},
            {"quantity": payload.quantity},
        )
        if idempotency_key is not None
        else None
    )
    return await execute(
        request,
        action,
        item_id=item_id,
        idempotency_key=idempotency_key,
        actor_id=user.telegram_id,
        request_hash=request_hash,
        response_status=status.HTTP_201_CREATED,
    )


@router.patch("/{reservation_id}", response_model=PromiseActionDTO)
async def update_reservation_quantity(
    wishlist_id: int,
    item_id: int,
    reservation_id: int,
    payload: ReservationQuantityDTO,
    user: User,
    request: Request,
) -> PromiseActionDTO | Response:
    """Raise or lower one intended or purchased promise owned by the caller."""
    idempotency_key = parse_idempotency_key(request)

    async def action(svc: WishlistService) -> PromiseActionDTO:
        reservation = await svc.update_reservation_quantity(
            reservation_id,
            user,
            payload.quantity,
            wishlist_id=wishlist_id,
            item_id=item_id,
        )
        return project_reservation_action(reservation, user)

    request_hash = (
        compute_request_hash(
            "update_reservation_quantity",
            {"wishlist_id": wishlist_id, "item_id": item_id, "reservation_id": reservation_id},
            {"quantity": payload.quantity},
        )
        if idempotency_key is not None
        else None
    )
    return await execute(
        request,
        action,
        item_id=item_id,
        reservation_id=reservation_id,
        idempotency_key=idempotency_key,
        actor_id=user.telegram_id,
        request_hash=request_hash,
    )


@router.post("/{reservation_id}/cancel", response_model=PromiseActionDTO)
async def cancel_reservation(
    wishlist_id: int,
    item_id: int,
    reservation_id: int,
    user: User,
    request: Request,
) -> PromiseActionDTO | Response:
    """Cancel one promise owned by the caller and free its units."""
    idempotency_key = parse_idempotency_key(request)

    async def action(svc: WishlistService) -> PromiseActionDTO:
        reservation = await svc.cancel_reservation(
            reservation_id,
            user,
            wishlist_id=wishlist_id,
            item_id=item_id,
        )
        return project_reservation_action(reservation, user)

    request_hash = (
        compute_request_hash(
            "cancel_reservation",
            {"wishlist_id": wishlist_id, "item_id": item_id, "reservation_id": reservation_id},
        )
        if idempotency_key is not None
        else None
    )
    return await execute(
        request,
        action,
        item_id=item_id,
        reservation_id=reservation_id,
        idempotency_key=idempotency_key,
        actor_id=user.telegram_id,
        request_hash=request_hash,
    )


@router.post("/{reservation_id}/complete", response_model=PromiseActionDTO)
async def complete_reservation(
    wishlist_id: int,
    item_id: int,
    reservation_id: int,
    user: User,
    request: Request,
) -> PromiseActionDTO | Response:
    """Complete the caller's purchased promise on a fully received wish."""
    idempotency_key = parse_idempotency_key(request)

    async def action(svc: WishlistService) -> PromiseActionDTO:
        reservation = await svc.complete_reservation(
            reservation_id, user, wishlist_id=wishlist_id, item_id=item_id
        )
        return project_reservation_action(reservation, user)

    request_hash = (
        compute_request_hash(
            "complete_reservation",
            {"wishlist_id": wishlist_id, "item_id": item_id, "reservation_id": reservation_id},
        )
        if idempotency_key is not None
        else None
    )
    store = getattr(request.app.state, "wishlist_store", None)

    async def run() -> PromiseActionDTO | Response:
        return await execute(
            request,
            action,
            item_id=item_id,
            reservation_id=reservation_id,
            idempotency_key=idempotency_key,
            actor_id=user.telegram_id,
            request_hash=request_hash,
        )

    if store is None:
        logger.error(
            "Receipt delivery coordination unavailable",
            extra={
                "event": "receipt_delivery_coordination_unavailable",
                "operation": "complete_reservation",
                "item_id": item_id,
                "reservation_id": reservation_id,
            },
        )
        raise HTTPException(status_code=503, detail="Receipt delivery coordination unavailable")
    try:
        async with delivery_lock(store.database_url, item_id, user.telegram_id):
            if await has_fence(store, item_id, user.telegram_id):
                logger.warning(
                    "Complete reservation deferred: unresolved receipt delivery fence",
                    extra={
                        "event": "reservation_complete_fence_blocked",
                        "operation": "complete_reservation",
                        "item_id": item_id,
                        "reservation_id": reservation_id,
                    },
                )
                raise HTTPException(status_code=503, detail="Receipt delivery is unresolved")
            return await run()
    except OSError as exc:
        logger.warning(
            "Complete reservation deferred: receipt delivery lock busy",
            extra={
                "event": "reservation_complete_lock_busy",
                "operation": "complete_reservation",
                "item_id": item_id,
                "reservation_id": reservation_id,
                "error_class": type(exc).__name__,
            },
        )
        raise HTTPException(status_code=503, detail="Receipt delivery is busy") from exc


@router.post("/{reservation_id}/purchase", response_model=PromiseActionDTO)
async def purchase_reservation(
    wishlist_id: int,
    item_id: int,
    reservation_id: int,
    user: User,
    request: Request,
) -> PromiseActionDTO | Response:
    """Mark one intended promise owned by the caller as purchased."""
    idempotency_key = parse_idempotency_key(request)

    async def action(svc: WishlistService) -> PromiseActionDTO:
        reservation = await svc.mark_reservation_purchased(
            reservation_id,
            user,
            wishlist_id=wishlist_id,
            item_id=item_id,
        )
        return project_reservation_action(reservation, user)

    request_hash = (
        compute_request_hash(
            "purchase_reservation",
            {"wishlist_id": wishlist_id, "item_id": item_id, "reservation_id": reservation_id},
        )
        if idempotency_key is not None
        else None
    )
    return await execute(
        request,
        action,
        item_id=item_id,
        reservation_id=reservation_id,
        idempotency_key=idempotency_key,
        actor_id=user.telegram_id,
        request_hash=request_hash,
    )


@router.post("/{reservation_id}/undo-purchase", response_model=PromiseActionDTO)
async def undo_reservation_purchase(
    wishlist_id: int,
    item_id: int,
    reservation_id: int,
    user: User,
    request: Request,
) -> PromiseActionDTO | Response:
    """Return one purchased promise owned by the caller to intended."""
    idempotency_key = parse_idempotency_key(request)

    async def action(svc: WishlistService) -> PromiseActionDTO:
        reservation = await svc.revert_reservation_to_active(
            reservation_id,
            user,
            wishlist_id=wishlist_id,
            item_id=item_id,
        )
        return project_reservation_action(reservation, user)

    request_hash = (
        compute_request_hash(
            "undo_reservation_purchase",
            {"wishlist_id": wishlist_id, "item_id": item_id, "reservation_id": reservation_id},
        )
        if idempotency_key is not None
        else None
    )
    return await execute(
        request,
        action,
        item_id=item_id,
        reservation_id=reservation_id,
        idempotency_key=idempotency_key,
        actor_id=user.telegram_id,
        request_hash=request_hash,
    )
