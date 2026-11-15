"""Shared helpers for the WISHENKA-24 receipt screen tests (Mini App page layer).

Production symbols that do not exist yet are reached through ``new_symbol`` / ``ui_module`` /
``render_partial`` inside the test body, so a missing component is one readable red assertion and
never a collection error.
"""

from __future__ import annotations

import asyncio
import importlib
import re
from collections.abc import Awaitable, Sequence
from datetime import UTC, datetime
from types import ModuleType
from typing import Any, NamedTuple

from bs4 import BeautifulSoup, Tag
from fastapi import FastAPI
from jinja2 import TemplateNotFound

from tests.receipt_support import (
    GIFTER,
    OTHER_GIFTER,
    OWNER,
    OWNER_ID,
    seed_wish,
)
from wishenka.auth.models import AuthenticatedUser
from wishenka.auth.session import SessionTokenService
from wishenka.web.templates import templates
from wishenka.wishlists.service import WishlistService

UI_MODULE = "wishenka.web.routes.receipts_ui"
REFUSAL_HEADER = "X-Receipt-Refusal"
REORDER_HEADER = "X-Reorder-Refusal"

# Russian copy fixed by 20-architecture.md (routes table and copy table).
SENTENCES: dict[str, str] = {
    "quantity_invalid": "Укажите целое число не меньше 1.",
    "quantity_above_remaining": "Нельзя отметить больше, чем осталось. Осталось: {n}.",
    "nothing_remaining": "Это желание уже полностью получено.",
    "wish_archived": "Желание в архиве. Восстановите его, чтобы отметить получение.",
    "wishlist_not_active": "Вишлист не активен, отметить получение нельзя.",
    "forbidden": "У вас нет права отмечать получение в этом вишлисте.",
    "not_found": "Желание не найдено. Обновите страницу.",
    "busy": "Не удалось сохранить отметку сейчас. Повторите попытку.",
}
GENERIC_FAILURE = "Не удалось сохранить отметку. Повторите попытку."
NOTHING_REMAINING_TEXT = SENTENCES["nothing_remaining"]
STALE_CARD_TEXT = "Желание больше недоступно. Обновите страницу."
REORDER_NOTICE = "Список изменился. Обновляем."
EMPTY_LIST_TEXT = "В этом списке желаний пока нет подарков."
GIFTED_FAILURE = "Не удалось загрузить «Подаренные». Обновите страницу."
CABINET_MARKER = "Желание получено владельцем"
XSS_TITLE = "<script>alert(1)</script>"

# Words that must never appear in a new owner-side partial or response (U-20, N-1).
BOOKING_WORDS = ("занято", "занят", "забронир", "бронь", "даритель", "куплено")
# Giver names and numbers seeded as promises; none may be rendered on the owner path.
GIVER_NAMES = ("Greta", "Oleg")
BOOKED_NUMBERS = (37, 41)


def run[T](coro: Awaitable[T]) -> T:
    """Run a domain-service coroutine to completion (the app uses a file SQLite)."""

    async def runner() -> T:
        return await coro

    return asyncio.run(runner())


def domain(app: FastAPI) -> WishlistService:
    """Return the app's domain service."""
    service: WishlistService = app.state.domain_service
    return service


def hx(
    sessions: SessionTokenService, user_id: int = OWNER_ID, name: str = "Alice"
) -> dict[str, str]:
    """Bearer plus ``HX-Request`` headers of a Mini App page request."""
    token = sessions.create_token(user_id, name)
    return {"Authorization": f"Bearer {token}", "HX-Request": "true"}


def ui_module() -> ModuleType:
    """Import the receipts UI route module or fail with a readable assertion."""
    try:
        return importlib.import_module(UI_MODULE)
    except ImportError as exc:
        raise AssertionError(f"{UI_MODULE} does not exist yet ({exc})") from None


def render_partial(name: str, **context: Any) -> str:
    """Render a partial template directly; a missing template is a readable assertion."""
    try:
        template = templates.get_template(name)
    except TemplateNotFound:
        raise AssertionError(f"template {name} does not exist yet") from None
    return template.render(context)


class Wish(NamedTuple):
    """One wish to seed."""

    title: str = "Kettle"
    quantity: int = 5
    price: int | None = None
    recipient_name: str | None = None
    recipient_user_id: int | None = None


def seed_list(
    app: FastAPI,
    wishes: Sequence[Wish] = (Wish(),),
    *,
    members: Sequence[AuthenticatedUser] = (),
) -> tuple[int, list[int]]:
    """Create the owner's list with wishes; returns the list id and item ids in display order."""
    service = domain(app)

    async def create() -> tuple[int, list[int]]:
        wishlist = await service.create_wishlist(owner=OWNER, title="Alice Birthday")
        for member in members:
            await service.add_member(wishlist.id, OWNER, member.telegram_id)
        ids: list[int] = []
        for wish in wishes:
            item = await service.add_wish_item(
                wishlist_id=wishlist.id,
                actor=OWNER,
                title=wish.title,
                quantity=wish.quantity,
                price=wish.price,
                recipient_name=wish.recipient_name,
                recipient_user_id=wish.recipient_user_id,
            )
            ids.append(item.id)
        return wishlist.id, ids

    return run(create())


def seed_booked(app: FastAPI) -> tuple[int, int]:
    """One wish of 100 units, promises 37 and 41 by two givers, 90 already received.

    Remaining is 10, so the numbers 37 and 41 cannot appear as quantity options or as a
    remaining count: any rendering of them is a leak of booking data.
    """
    service = domain(app)

    async def create() -> tuple[int, int]:
        wishlist_id, item_id = await seed_wish(service, quantity=100, title="Kettle")
        await service.create_reservation(item_id=item_id, user=GIFTER, quantity=BOOKED_NUMBERS[0])
        await service.create_reservation(
            item_id=item_id, user=OTHER_GIFTER, quantity=BOOKED_NUMBERS[1]
        )
        await service.record_item_fulfillment(item_id, OWNER, 90)
        return wishlist_id, item_id

    return run(create())


def receive(app: FastAPI, item_id: int, quantity: int, actor: AuthenticatedUser = OWNER) -> None:
    """Record a receipt through the domain service."""
    run(domain(app).record_item_fulfillment(item_id, actor, quantity))


def promise(app: FastAPI, item_id: int, user: AuthenticatedUser, quantity: int) -> None:
    """Create a promise through the domain service."""
    run(domain(app).create_reservation(item_id=item_id, user=user, quantity=quantity))


def modal_url(wishlist_id: int, item_id: int) -> str:
    """Receipt dialog and POST path of one wish."""
    return f"/web/wishlists/{wishlist_id}/items/{item_id}/receipt"


def parse(html: str) -> BeautifulSoup:
    """Parse a page or a fragment response."""
    return BeautifulSoup(html, "html.parser")


def text_of(node: BeautifulSoup | Tag | None) -> str:
    """Whitespace-collapsed visible text with scripts removed."""
    assert node is not None, "element missing"
    cloned = BeautifulSoup(str(node), "html.parser")
    for script in cloned.find_all("script"):
        script.decompose()
    return " ".join(cloned.get_text(" ", strip=True).split())


def top_level(soup: BeautifulSoup) -> list[Tag]:
    """Top-level elements of a fragment response."""
    return [child for child in soup.children if isinstance(child, Tag)]


def assert_all_top_level_oob(soup: BeautifulSoup, body: str) -> None:
    """Every top-level node of an out-of-band response carries ``hx-swap-oob`` (no stray text)."""
    stray = [
        str(child).strip()
        for child in soup.children
        if not isinstance(child, Tag) and str(child).strip()
    ]
    assert stray == [], f"top-level text outside any OOB element: {stray}\n{body}"
    plain = [el.name for el in top_level(soup) if not el.has_attr("hx-swap-oob")]
    assert plain == [], f"top-level elements without hx-swap-oob: {plain}\n{body}"


def oob(soup: BeautifulSoup, element_id: str) -> Tag:
    """The top-level OOB element with this id (readable failure when missing)."""
    for element in top_level(soup):
        if element.get("id") == element_id and element.has_attr("hx-swap-oob"):
            return element
    ids = [(e.get("id"), e.get("hx-swap-oob")) for e in top_level(soup)]
    raise AssertionError(f"no top-level OOB element #{element_id}; top level: {ids}")


def oob_list(soup: BeautifulSoup) -> Tag:
    """The OOB element that replaces the contents of ``#items-list``."""
    for element in top_level(soup):
        if element.get("hx-swap-oob") == "innerHTML:#items-list":
            return element
    ids = [(e.get("id"), e.get("hx-swap-oob")) for e in top_level(soup)]
    raise AssertionError(f"no innerHTML:#items-list OOB element; top level: {ids}")


def on_attributes(soup: BeautifulSoup) -> list[str]:
    """``<tag> onxxx`` for every inline event handler attribute."""
    return [
        f"<{tag.name}> {attr}"
        for tag in soup.find_all(True)
        for attr in tag.attrs
        if attr.lower().startswith("on")
    ]


def assert_no_booking_leak(text: str, *, numbers: bool = True) -> None:
    """No giver name, id, booking word or booked number in an owner-side text."""
    lowered = text.lower()
    for word in BOOKING_WORDS:
        assert word not in lowered, f"booking word {word!r} in: {text[:400]}"
    for name in GIVER_NAMES:
        assert name not in text, f"giver name {name!r} in: {text[:400]}"
    if numbers:
        for number in BOOKED_NUMBERS:
            assert re.search(rf"(?<!\d){number}(?!\d)", text) is None, (
                f"booked number {number} in: {text[:400]}"
            )


def utc_days_around(call_time: tuple[datetime, datetime]) -> set[str]:
    """``dd.mm.yyyy`` of the UTC days between two instants (guards a midnight race)."""
    return {value.astimezone(UTC).strftime("%d.%m.%Y") for value in call_time}
