"""View models of the «Подаренные» section and constants shared by the receipt page routes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from markupsafe import Markup

from wishenka.auth.models import AuthenticatedUser
from wishenka.wishlists.exceptions import WishlistError
from wishenka.wishlists.schemas import GiftedItemDTO
from wishenka.wishlists.service import WishlistService

RECEIPT_REFUSAL_HEADER = "X-Receipt-Refusal"
NOTHING_REMAINING_TEXT = "Это желание уже полностью получено."


def oob_text(element_id: str, text: str = "") -> Markup:
    """One out-of-band ``innerHTML`` element; ``text`` is escaped (never interpolated raw)."""
    return Markup('<div id="{}" hx-swap-oob="innerHTML">{}</div>').format(element_id, text)


@dataclass(frozen=True)
class GiftedAct:
    """One receipt act as shown in the section."""

    day: str
    quantity: int
    approximate: bool


@dataclass(frozen=True)
class GiftedRow:
    """One received wish as shown in the section; carries no promise or giver data."""

    item_id: int
    title: str
    price: str | None
    recipient_name: str | None
    received: int
    requested: int
    acts: tuple[GiftedAct, ...]


def utc_day(value: datetime) -> str:
    """Return the UTC calendar day as ``dd.mm.yyyy``; a naive value means UTC."""
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return aware.astimezone(UTC).strftime("%d.%m.%Y")


def build_gifted_rows(items: list[GiftedItemDTO]) -> list[GiftedRow]:
    """Project gifted DTOs to rows, keeping the service order (it is the display order)."""
    return [
        GiftedRow(
            item_id=item.id,
            title=item.title,
            price=None if item.price is None else f"{item.price} {item.currency or 'RUB'}",
            recipient_name=item.recipient_name,
            received=item.received_quantity,
            requested=item.quantity,
            acts=tuple(
                GiftedAct(utc_day(act.received_at), act.quantity, act.is_approximate)
                for act in item.receipts
            ),
        )
        for item in items
    ]


async def read_gifted_rows(
    svc: WishlistService, wishlist_id: int, user: AuthenticatedUser | None
) -> list[GiftedRow] | None:
    """Read the gifted rows of a list; a domain error gives ``None`` (fail-soft, U-15)."""
    try:
        return build_gifted_rows(await svc.list_gifted_items(wishlist_id, user))
    except WishlistError:
        return None
