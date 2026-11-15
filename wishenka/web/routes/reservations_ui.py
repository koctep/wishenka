"""Read-only home card and the caller's reservations cabinet.

Writes stay on the five promise routes. This module groups and sorts.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import HTMLResponse

from wishenka.auth.dependencies import get_current_user
from wishenka.auth.models import AuthenticatedUser
from wishenka.web.templates import templates
from wishenka.wishlists.models import ReservationStatus
from wishenka.wishlists.schemas import MyReservationItemDTO, UserReservationsSummaryDTO
from wishenka.wishlists.service import WishlistService

router = APIRouter(tags=["reservations-ui"])

User = Annotated[AuthenticatedUser, Depends(get_current_user)]

_BOOKED = "Забронировано"
_BOUGHT = "Куплено"
_NOTICES = frozenset({"shortage", "refused"})


@dataclass(frozen=True)
class CabinetRow:
    """One occupying promise on the caller's cabinet."""

    reservation_id: int
    wish_item_id: int
    wishlist_id: int
    item_title: str
    quantity: int
    status_label: str
    for_name: str
    wish_archived: bool
    list_archived: bool
    wish_received: bool
    offer_actions: bool
    change_ceiling: int
    wish_href: str


@dataclass(frozen=True)
class CabinetGroup:
    """One wishlist section of the caller's cabinet."""

    wishlist_id: int
    title: str
    event_title: str | None
    event_date: str | None
    list_archived: bool
    rows: tuple[CabinetRow, ...]


async def _read[T](request: Request, action: Callable[[WishlistService], Awaitable[T]]) -> T:
    """Run a read on the full snapshot, or on an injected in-memory service."""
    injected = getattr(request.app.state, "wishlist_service", None)
    if injected is not None:
        return await action(injected)
    return cast(T, await request.app.state.wishlist_store.execute(action))


def _event_day(value: datetime | None) -> str | None:
    """Return the UTC calendar day, or none when the list has no event date."""
    if value is None:
        return None
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return aware.astimezone(UTC).date().isoformat()


def _row(item: MyReservationItemDTO) -> CabinetRow:
    """Project one promise. Actions exist for an archived or received wish on an active list."""
    purchased = item.status == ReservationStatus.PURCHASED
    return CabinetRow(
        reservation_id=item.reservation_id,
        wish_item_id=item.wish_item_id,
        wishlist_id=item.wishlist_id,
        item_title=item.item_title,
        quantity=item.reserved_quantity,
        status_label=_BOUGHT if purchased else _BOOKED,
        for_name=item.recipient_name,
        wish_archived=item.is_item_archived,
        list_archived=item.is_wishlist_archived,
        wish_received=item.is_fully_received,
        offer_actions=(item.is_item_archived or item.is_fully_received)
        and not item.is_wishlist_archived,
        change_ceiling=item.change_ceiling,
        wish_href=f"/web/wishlists/{item.wishlist_id}#item-card-{item.wish_item_id}",
    )


def _groups(items: list[MyReservationItemDTO]) -> tuple[CabinetGroup, ...]:
    """Group by wishlist, casefold then id, and order rows by time then id."""
    by_list: dict[int, list[MyReservationItemDTO]] = {}
    for item in items:
        by_list.setdefault(item.wishlist_id, []).append(item)
    groups: list[CabinetGroup] = []
    for wishlist_id, rows in by_list.items():
        ordered = sorted(rows, key=lambda row: (row.created_at, row.reservation_id))
        first = ordered[0]
        event_title = first.event_title.strip() if first.event_title else ""
        groups.append(
            CabinetGroup(
                wishlist_id=wishlist_id,
                title=first.wishlist_title,
                event_title=event_title or None,
                event_date=_event_day(first.event_date),
                list_archived=first.is_wishlist_archived,
                rows=tuple(_row(item) for item in ordered),
            )
        )
    groups.sort(key=lambda group: (group.title.casefold(), group.wishlist_id))
    return tuple(groups)


def _remainder(items: list[MyReservationItemDTO], reservation_id: int | None) -> int:
    """Return the free units on the wish behind one of the caller's promises."""
    if reservation_id is None:
        return 0
    for item in items:
        if item.reservation_id == reservation_id:
            return max(0, item.change_ceiling - item.reserved_quantity)
    return 0


def _list_context(
    items: list[MyReservationItemDTO],
    notice: str | None,
    reservation_id: int | None,
) -> dict[str, Any]:
    """Build the list partial. An unknown notice is omitted."""
    kind = notice if notice in _NOTICES else None
    return {
        "groups": _groups(items),
        "notice_kind": kind,
        "free_remainder": _remainder(items, reservation_id) if kind == "shortage" else 0,
    }


async def _load_items(request: Request, user_id: int) -> list[MyReservationItemDTO]:
    """Load the caller's occupying promises."""

    async def load(service: WishlistService) -> list[MyReservationItemDTO]:
        return await service.get_user_reservations(user_id=user_id)

    return await _read(request, load)


@router.get("/web/reservations/card", response_class=HTMLResponse)
async def reservations_card(request: Request, current_user: User) -> Response:
    """Return the home card fragment. The badge is the distinct-wish count."""

    async def load(service: WishlistService) -> UserReservationsSummaryDTO:
        return await service.get_user_reservations_summary(user_id=current_user.telegram_id)

    summary = await _read(request, load)
    return templates.TemplateResponse(
        request=request,
        name="partials/reservations_card.html",
        context={"distinct_count": summary.total_distinct_items},
    )


@router.get("/web/reservations/list", response_class=HTMLResponse)
async def reservations_list(
    request: Request,
    current_user: User,
    notice: Annotated[str | None, Query()] = None,
    reservation_id: Annotated[int | None, Query()] = None,
) -> Response:
    """Return the cabinet list partial for a refresh."""
    items = await _load_items(request, current_user.telegram_id)
    return templates.TemplateResponse(
        request=request,
        name="partials/reservations_list.html",
        context=_list_context(items, notice, reservation_id),
    )


@router.get("/web/reservations", response_class=HTMLResponse)
async def reservations_page(request: Request, current_user: User) -> Response:
    """Return the cabinet page for the identified caller."""
    items = await _load_items(request, current_user.telegram_id)
    context = _list_context(items, None, None)
    context["viewer_identified"] = True
    return templates.TemplateResponse(
        request=request,
        name="reservations_cabinet.html",
        context=context,
    )
