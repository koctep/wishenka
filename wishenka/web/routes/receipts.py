"""Authenticated gift receipt command and the gifted-wishes read for list authors.

Results and refusals carry no promise or giver field. Refusals use one closed table of
machine codes with fixed messages that state no number except the remaining quantity.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from wishenka.auth.dependencies import get_current_user
from wishenka.auth.models import AuthenticatedUser
from wishenka.web.idempotency import (
    build_replay_response,
    compute_request_hash,
    parse_idempotency_key,
    retention_hours_from_request,
    serialize_dto_response,
)
from wishenka.wishlists.exceptions import (
    IdempotencyConflictError,
    InventoryBusyError,
    ItemNotFoundError,
    NothingRemainingError,
    PermissionDeniedError,
    QuantityAboveRemainingError,
    QuantityInvalidError,
    WishArchivedError,
    WishlistArchivedError,
    WishlistDeletedError,
    WishlistNotFoundError,
)
from wishenka.wishlists.schemas import GiftedItemDTO, ReceiptRequestDTO, ReceiptResultDTO
from wishenka.wishlists.service import WishlistService, recipient_view

router = APIRouter(prefix="/api/wishlists/{wishlist_id}", tags=["receipts"])
logger = logging.getLogger("wishenka.web.receipts")

User = Annotated[AuthenticatedUser, Depends(get_current_user)]

_NOT_ACTIVE = "The wishlist is not active"
_NOT_FOUND = "Resource not found"
# Exception class -> (HTTP status, reason, fixed message). Order is the match order.
_REFUSALS: tuple[tuple[type[Exception], int, str, str], ...] = (
    (
        QuantityInvalidError,
        status.HTTP_400_BAD_REQUEST,
        "quantity_invalid",
        "Quantity must be a whole number of at least 1",
    ),
    (
        QuantityAboveRemainingError,
        status.HTTP_409_CONFLICT,
        "quantity_above_remaining",
        "Quantity is above the remaining quantity",
    ),
    (WishArchivedError, status.HTTP_409_CONFLICT, "wish_archived", "The wish is archived"),
    (WishlistArchivedError, status.HTTP_409_CONFLICT, "wishlist_not_active", _NOT_ACTIVE),
    (WishlistDeletedError, status.HTTP_404_NOT_FOUND, "wishlist_not_active", _NOT_ACTIVE),
    (
        NothingRemainingError,
        status.HTTP_409_CONFLICT,
        "nothing_remaining",
        "Nothing remains to receive",
    ),
    (PermissionDeniedError, status.HTTP_403_FORBIDDEN, "forbidden", "Forbidden"),
    (ItemNotFoundError, status.HTTP_404_NOT_FOUND, "not_found", _NOT_FOUND),
    (WishlistNotFoundError, status.HTTP_404_NOT_FOUND, "not_found", _NOT_FOUND),
)


def _refusal(
    exc: Exception, operation: str, context: dict[str, int | None]
) -> HTTPException | None:
    """Map a domain error to the closed refusal, or ``None`` when it is not one of them."""
    for error_type, http_status, reason, message in _REFUSALS:
        if isinstance(exc, error_type):
            detail: dict[str, Any] = {"reason": reason, "message": message}
            fields: dict[str, Any] = {
                "event": "receipt_refused",
                "operation": operation,
                **context,
                "reason": reason,
                "http_status": http_status,
            }
            if isinstance(exc, QuantityAboveRemainingError | NothingRemainingError):
                detail["remaining_quantity"] = exc.remaining_quantity
                fields["remaining_quantity"] = exc.remaining_quantity
            logger.warning("Receipt operation refused: %s", operation, extra=fields)
            return HTTPException(status_code=http_status, detail=detail)
    return None


def _busy(exc: InventoryBusyError, operation: str, context: dict[str, int | None]) -> HTTPException:
    """Retryable 503 with the wording of the promise routes."""
    logger.warning(
        "Receipt operation busy: %s",
        operation,
        extra={"event": "receipt_inventory_busy", "operation": operation, **context},
    )
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={"reason": "busy", "message": str(exc)},
    )


async def _run[T](
    request: Request,
    action: Callable[[WishlistService], Awaitable[T]],
    user: AuthenticatedUser,
    *,
    wishlist_id: int,
    item_id: int | None = None,
    idempotency_key: str | None = None,
    request_hash: str | None = None,
    response_status: int = status.HTTP_201_CREATED,
) -> T | Response:
    """Run one action: a single-wish transaction for a command, a full snapshot for a read."""
    operation = getattr(request.scope.get("endpoint"), "__name__", "")
    context = {"wishlist_id": wishlist_id, "item_id": item_id, "actor_id": user.telegram_id}
    try:
        injected = getattr(request.app.state, "wishlist_service", None)
        if injected is not None:
            return await action(injected)
        store = request.app.state.wishlist_store
        if item_id is None:
            return cast(T, await store.execute(action))
        if idempotency_key is not None:
            if request_hash is None:
                raise ValueError("Idempotent execution requires request_hash")

            async def serialized_action(svc: WishlistService) -> tuple[int, str, str]:
                dto = await action(svc)
                return serialize_dto_response(cast(ReceiptResultDTO, dto), response_status)

            outcome = await store.execute_wish_idempotent(
                serialized_action,
                actor_id=user.telegram_id,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                retention_hours=retention_hours_from_request(request),
                item_id=item_id,
                operation_name="record_item_fulfillment",
                require_member=True,
            )
            return build_replay_response(outcome.status_code, outcome.content_type, outcome.body)
        return cast(
            T,
            await store.execute_wish(
                action, item_id=item_id, operation_name="record_item_fulfillment"
            ),
        )
    except InventoryBusyError as exc:
        raise _busy(exc, operation, context) from exc
    except IdempotencyConflictError as exc:
        logger.warning(
            "Receipt idempotency conflict: %s",
            operation,
            extra={"event": "receipt_idempotency_conflict", **context},
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"reason": "idempotency_conflict", "message": str(exc)},
        ) from exc
    except (
        QuantityInvalidError,
        QuantityAboveRemainingError,
        WishArchivedError,
        WishlistArchivedError,
        WishlistDeletedError,
        NothingRemainingError,
        PermissionDeniedError,
        ItemNotFoundError,
        WishlistNotFoundError,
    ) as exc:
        refused = _refusal(exc, operation, context)
        assert refused is not None  # every class above is in the table
        raise refused from exc


@router.post(
    "/items/{item_id}/receipts",
    status_code=status.HTTP_201_CREATED,
    response_model=ReceiptResultDTO,
)
async def record_receipt(
    wishlist_id: int,
    item_id: int,
    payload: ReceiptRequestDTO,
    user: User,
    request: Request,
) -> ReceiptResultDTO | Response:
    """Record that a list author received some units of a wish."""
    idempotency_key = parse_idempotency_key(request)

    async def action(svc: WishlistService) -> ReceiptResultDTO:
        item = await svc.record_item_fulfillment(
            item_id, user, payload.quantity, wishlist_id=wishlist_id
        )
        return ReceiptResultDTO(
            item=recipient_view(item),
            received_now=payload.quantity,
            received_quantity=item.received_quantity,
            remaining_quantity=item.remaining_quantity,
            is_fully_received=item.is_fully_received,
        )

    request_hash = (
        compute_request_hash(
            "record_receipt",
            {"wishlist_id": wishlist_id, "item_id": item_id},
            {"quantity": payload.quantity},
        )
        if idempotency_key is not None
        else None
    )
    result = await _run(
        request,
        action,
        user,
        wishlist_id=wishlist_id,
        item_id=item_id,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_status=status.HTTP_201_CREATED,
    )
    logger.info(
        "Receipt recorded for item %s",
        item_id,
        extra={"event": "receipt_recorded_http", "item_id": item_id},
    )
    return result


@router.get("/gifted", response_model=list[GiftedItemDTO])
async def list_gifted(wishlist_id: int, user: User, request: Request) -> list[GiftedItemDTO]:
    """Return the received wishes of a list for its authors."""

    async def action(svc: WishlistService) -> list[GiftedItemDTO]:
        return await svc.list_gifted_items(wishlist_id, user)

    return cast(list[GiftedItemDTO], await _run(request, action, user, wishlist_id=wishlist_id))
