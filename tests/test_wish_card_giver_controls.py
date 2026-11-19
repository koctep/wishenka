"""Red repro for giver controls on the wish card (WISHENKA-19).

The checks assert the accepted card: one giver block in the summary, the
personal-list owner kept silent, and an expanded refresh that clears
``hidden`` on the new details. They fail on the current template and on the
current personal-list owner rule. Promise writes go through the existing API.
"""

from __future__ import annotations

import asyncio
import re
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any, NamedTuple

import pytest
from bs4 import BeautifulSoup, Tag
from fastapi import FastAPI
from fastapi.testclient import TestClient

from wishenka.auth.models import AuthenticatedUser, TelegramUser
from wishenka.auth.session import SessionTokenService
from wishenka.config import Settings
from wishenka.web.app import create_app
from wishenka.wishlists.exceptions import InventoryBusyError
from wishenka.wishlists.service import WishlistService

pytestmark = pytest.mark.timeout(30)

_OWNER_ID = 101
_FRIEND_ID = 202
_OTHER_ID = 303
_SQLITE_PREFIX = "sqlite+aiosqlite:///"
_GIVER_LABELS = (
    "Доступно",
    "Забронировано",
    "Забронировать",
    "Изменить",
    "Отменить бронь",
    "Куплено",
    "Вернуть в бронь",
)
_RECIPIENT_NOTICE_BANNED = (
    "Бронь не изменилась",
    "Свободно",
    *_GIVER_LABELS,
)
_ARIA_READ = re.compile(
    r"""(?:var|let|const)\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*[^;]*?"""
    r"""getAttribute\(\s*['"]aria-expanded['"]\s*\)"""
)
_HIDDEN_CLEAR = re.compile(r"""\.hidden\s*=\s*false|removeAttribute\(\s*['"]hidden['"]\s*\)""")
_SET_EXPANDED_TRUE = re.compile(
    r"""setAttribute\(\s*['"]aria-expanded['"]\s*,\s*['"]true['"]\s*\)"""
)


class SeededWish(NamedTuple):
    """One personal list and the wish the card tests render."""

    wishlist_id: int
    item_id: int
    public_token: str


class CollaborativeWishes(NamedTuple):
    """Three collaborative wishes viewed by one caller."""

    wishlist_id: int
    for_caller: int
    for_other: int
    display_name: int


def make_user(telegram_id: int, first_name: str) -> AuthenticatedUser:
    """Create a bearer test user."""
    return AuthenticatedUser(
        telegram_id=telegram_id,
        first_name=first_name,
        auth_method="session_token",
    )


def auth_header(sessions: SessionTokenService, user_id: int, name: str) -> dict[str, str]:
    """Build an Authorization header for a session token."""
    token = sessions.create_token(user_id, name)
    return {"Authorization": f"Bearer {token}", "Accept-Language": "ru"}


def reservations_url(wishlist_id: int, item_id: int) -> str:
    """Return the existing promise collection for one wish."""
    return f"/api/wishlists/{wishlist_id}/items/{item_id}/reservations"


def _db_path(app: FastAPI) -> str:
    """Return the temporary SQLite file for this app."""
    return str(app.state.settings.database_url).removeprefix(_SQLITE_PREFIX)


def reservation_rows(app: FastAPI, item_id: int) -> list[tuple[int, int, str, int]]:
    """Return id, quantity, status, and gifter id for one wish."""
    with sqlite3.connect(_db_path(app)) as conn:
        fetched = conn.execute(
            "SELECT id, quantity, status, user_id "
            "FROM wl_reservations WHERE wish_item_id = ? ORDER BY id",
            (item_id,),
        ).fetchall()
    return [(int(row[0]), int(row[1]), str(row[2]), int(row[3])) for row in fetched]


def wish_quantity(app: FastAPI, item_id: int) -> int:
    """Return the requested quantity stored for one wish."""
    with sqlite3.connect(_db_path(app)) as conn:
        row = conn.execute(
            "SELECT quantity FROM wl_items WHERE id = ?",
            (item_id,),
        ).fetchone()
    assert row is not None
    return int(row[0])


@pytest.fixture
def test_app(tmp_path: Path) -> Iterator[tuple[TestClient, SessionTokenService, FastAPI]]:
    """Open create_app on a temporary SQLite file with bearer sessions."""
    database = tmp_path / "wish_card_giver_controls.db"
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{database}",
        secret_key="wish-card-giver-controls-test-secret",
    )
    app = create_app(settings)
    sessions = SessionTokenService(settings.secret_key)
    with TestClient(app) as client:
        yield client, sessions, app


def seed_personal(
    service: WishlistService,
    *,
    quantity: int,
    title: str = "Headphones",
    recipient_name: str | None = None,
    member_ids: tuple[int, ...] = (),
) -> SeededWish:
    """Create a personal list and one wish through the domain service."""
    owner = make_user(_OWNER_ID, "Alice")

    async def create() -> SeededWish:
        wishlist = await service.create_wishlist(owner=owner, title="Alice Birthday")
        for member_id in member_ids:
            await service.add_member(
                wishlist_id=wishlist.id,
                actor=owner,
                user_id=member_id,
            )
        item = await service.add_wish_item(
            wishlist_id=wishlist.id,
            actor=owner,
            title=title,
            quantity=quantity,
            recipient_name=recipient_name,
        )
        return SeededWish(wishlist.id, item.id, str(wishlist.public_token))

    return asyncio.run(create())


def seed_collaborative(service: WishlistService, user_store: Any = None) -> CollaborativeWishes:
    """Create a collaborative list with three wishes for one caller."""
    owner = make_user(_OWNER_ID, "Alice")

    async def create() -> CollaborativeWishes:
        wishlist = await service.create_wishlist(owner=owner, title="Shared holiday")
        for member_id in (_FRIEND_ID, _OTHER_ID):
            if user_store is not None:
                await user_store.upsert_user(
                    TelegramUser(id=member_id, first_name=f"User {member_id}", language_code="ru")
                )
            await service.add_member(
                wishlist_id=wishlist.id,
                actor=owner,
                user_id=member_id,
            )
        for_caller = await service.add_wish_item(
            wishlist_id=wishlist.id,
            actor=owner,
            title="Mug",
            quantity=1,
            recipient_user_id=_FRIEND_ID,
        )
        for_other = await service.add_wish_item(
            wishlist_id=wishlist.id,
            actor=owner,
            title="Kettle",
            quantity=1,
            recipient_user_id=_OTHER_ID,
        )
        named = await service.add_wish_item(
            wishlist_id=wishlist.id,
            actor=owner,
            title="Scarf",
            quantity=1,
            recipient_name="Bob",
        )
        return CollaborativeWishes(wishlist.id, for_caller.id, for_other.id, named.id)

    return asyncio.run(create())


def list_html(client: TestClient, wishlist_id: int, headers: dict[str, str]) -> str:
    """Return the wishlist page for an identified viewer."""
    response = client.get(f"/web/wishlists/{wishlist_id}", headers=headers)
    assert response.status_code == 200, response.text
    return str(response.text)


def share_html(
    client: TestClient,
    public_token: str,
    headers: dict[str, str] | None = None,
) -> str:
    """Return the public share page."""
    effective_headers = {"Accept-Language": "ru"} if headers is None else headers
    response = client.get(f"/share/{public_token}", headers=effective_headers)
    assert response.status_code == 200, response.text
    return str(response.text)


def card_html(
    client: TestClient,
    wishlist_id: int,
    item_id: int,
    headers: dict[str, str] | None = None,
    **params: str,
) -> str:
    """Return the existing card partial."""
    response = client.get(
        f"/wishlists/{wishlist_id}/items/{item_id}/card",
        headers=headers,
        params=params,
    )
    assert response.status_code == 200, response.text
    return str(response.text)


def create_promise(
    client: TestClient,
    wishlist_id: int,
    item_id: int,
    headers: dict[str, str],
    quantity: int = 1,
) -> int:
    """Create a promise through the existing route and return its id."""
    response = client.post(
        reservations_url(wishlist_id, item_id),
        json={"quantity": quantity},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert isinstance(body, dict)
    return int(body["reservation_id"])


def visible_text(node: Tag) -> str:
    """Return rendered text with whitespace collapsed."""
    return " ".join(node.get_text(" ", strip=True).split())


def parse_html(html: str) -> BeautifulSoup:
    """Parse one served page."""
    return BeautifulSoup(html, "html.parser")


def card_tag(html: str, item_id: int) -> Tag:
    """Return the wish card element."""
    found = parse_html(html).find(id=f"item-card-{item_id}")
    assert isinstance(found, Tag), f"missing item card {item_id}"
    return found


def region(card: Tag, class_name: str) -> Tag:
    """Return the summary or details element of a card."""
    found = card.select_one(f".{class_name}")
    assert isinstance(found, Tag), f"missing .{class_name}"
    return found


def labels_in(text: str, labels: tuple[str, ...] = _GIVER_LABELS) -> list[str]:
    """Return giver labels that appear in text."""
    return [label for label in labels if label in text]


def same_url(actual: object, expected: str) -> bool:
    """Compare an HTMX URL without its query string."""
    if not isinstance(actual, str):
        return False
    return actual.split("?", 1)[0].rstrip("/") == expected.rstrip("/")


def posts_to(root: Tag, url: str) -> list[Tag]:
    """Return elements whose hx-post is exactly one route."""
    return [element for element in root.find_all(True) if same_url(element.get("hx-post"), url)]


def find_labeled(root: Tag, label: str) -> Tag | None:
    """Return the button or link whose visible text is the label."""
    for element in root.find_all(["button", "a"]):
        if visible_text(element) == label:
            return element
    return None


def attr_from(element: Tag, name: str) -> str | None:
    """Return an attribute from the element or an ancestor inside the card."""
    current: Tag | None = element
    while isinstance(current, Tag):
        raw = current.get(name)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        element_id = current.get("id")
        if isinstance(element_id, str) and element_id.startswith("item-card-"):
            break
        parent = current.parent
        current = parent if isinstance(parent, Tag) else None
    return None


def marked_no_toggle(element: Tag) -> bool:
    """Return whether the control, not the whole summary, opts out of toggle."""
    current: Tag | None = element
    while isinstance(current, Tag):
        classes: Any = current.get("class") or []
        if "item-card-summary" in classes and current is not element:
            return False
        if current.has_attr("data-no-toggle"):
            return True
        parent = current.parent
        current = parent if isinstance(parent, Tag) else None
    return False


def form_attr_gaps(element: Tag) -> list[str]:
    """Return missing JSON-enc, swap, and no-toggle marks on a book control."""
    gaps: list[str] = []
    host = element.find_parent("form")
    swap = element.get("hx-swap")
    if not isinstance(swap, str) and isinstance(host, Tag):
        swap = host.get("hx-swap")
    if swap != "none":
        gaps.append('book control missing hx-swap="none"')
    extension = element.get("hx-ext")
    if not isinstance(extension, str) and isinstance(host, Tag):
        extension = host.get("hx-ext")
    if extension != "json-enc" and attr_from(element, "hx-ext") != "json-enc":
        gaps.append('book control missing hx-ext="json-enc"')
    if not marked_no_toggle(element):
        gaps.append("book control is missing data-no-toggle")
    return gaps


def select_facts(select: Tag) -> tuple[list[int], list[int]]:
    """Return option values and the values marked selected."""
    values: list[int] = []
    selected: list[int] = []
    for option in select.find_all("option"):
        raw = option.get("value")
        if not isinstance(raw, str):
            continue
        number = int(raw)
        values.append(number)
        if option.has_attr("selected"):
            selected.append(number)
    return values, selected


def posts_quantity_one(element: Tag) -> bool:
    """Return whether a single-unit book control submits quantity 1."""
    vals = attr_from(element, "hx-vals") or ""
    if re.search(r'"quantity"\s*:\s*1\b', vals):
        return True
    host = element if element.name == "form" else element.find_parent("form")
    scope = host if isinstance(host, Tag) else element
    if scope.find("select", attrs={"name": "quantity"}) is not None:
        return False
    hidden = scope.find("input", attrs={"name": "quantity"})
    return isinstance(hidden, Tag) and hidden.get("value") == "1"


def book_control_gaps(card: Tag, prefix: str, remainder: int) -> list[str]:
    """Return missing book-control facts for a wish with a free remainder."""
    summary = region(card, "item-card-summary")
    details = region(card, "item-card-details")
    summary_text = visible_text(summary)
    gaps: list[str] = []
    if "Забронировать" not in summary_text:
        gaps.append("summary missing «Забронировать»")
    booked = visible_text(card).count("Забронировать")
    if booked != 1:
        gaps.append(f"«Забронировать» appears {booked} times")
    if "Забронировать" in visible_text(details):
        gaps.append("details repeat the book control")
    availability = f"Доступно: {remainder} из {remainder}"
    if remainder > 1 and availability not in summary_text:
        gaps.append(f"summary missing «{availability}»")
    select = card.find("select", attrs={"name": "quantity"})
    if remainder == 1:
        if isinstance(select, Tag):
            gaps.append("quantity select is present for one free unit")
    elif not isinstance(select, Tag) or select.find_parent(class_="item-card-summary") is None:
        gaps.append("summary missing quantity select")
    else:
        values, selected = select_facts(select)
        ceiling = list(range(1, remainder + 1))
        if values != ceiling or selected != [1] or 0 in values:
            gaps.append(f"quantity select values {values} selected {selected}, want {ceiling} at 1")
    posts = posts_to(summary, prefix)
    if len(posts) != 1:
        gaps.append(f"create POST count is {len(posts)}")
    else:
        gaps.extend(form_attr_gaps(posts[0]))
        if remainder == 1 and not posts_quantity_one(posts[0]):
            gaps.append("book control does not send quantity 1")
        if remainder > 1:
            host = posts[0] if posts[0].name == "form" else posts[0].find_parent("form")
            scope = host if isinstance(host, Tag) else posts[0]
            if not isinstance(select, Tag) or select.find_parent("form") is not scope:
                gaps.append("quantity select is outside the book form")
    return gaps


def own_line_text(root: Tag) -> str | None:
    """Return the own-booking line without the action buttons beside it."""
    node = root.find(string=lambda value: isinstance(value, str) and "Забронировано вами" in value)
    if node is None or not isinstance(node.parent, Tag):
        return None
    line = " ".join(str(node).split())
    current: Tag | None = node.parent
    while isinstance(current, Tag) and current is not root:
        text = visible_text(current)
        if any(label in text for label in ("Изменить", "Отменить бронь", "Вернуть в бронь")):
            break
        if len(text) > 120:
            break
        line = text
        parent = current.parent
        current = parent if isinstance(parent, Tag) else None
    return line


def inline_script(html: str) -> str:
    """Return inline scripts from a served page."""
    parts: list[str] = []
    for node in parse_html(html).find_all("script"):
        if node.get("src"):
            continue
        parts.append(node.get_text())
    return "\n".join(parts)


def _brace_contents(text: str, open_index: int) -> str:
    """Return the inside of the brace that starts at open_index."""
    depth = 0
    for index in range(open_index, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[open_index + 1 : index]
    return ""


def _restores_open_details(after_swap: str, flag: str) -> bool:
    """Return whether an expanded card clears hidden and a collapsed card does not.

    Copying ``aria-expanded`` onto the new summary is not enough: the new
    details are rendered with ``hidden``. The clear has to sit in the branch
    for the saved expanded flag, or in ``hidden = !flag``.
    """
    word = rf"\b{re.escape(flag)}\b"
    conditional_clear = False
    for match in re.finditer(r"if\s*\(([^)]*)\)\s*\{", after_swap):
        if re.search(word, match.group(1)) is None:
            continue
        block = _brace_contents(after_swap, match.end() - 1)
        if _HIDDEN_CLEAR.search(block):
            conditional_clear = True
    single = re.search(rf"if\s*\(([^)]*\b{re.escape(flag)}\b[^)]*)\)\s*([^{{;\n]+)", after_swap)
    if single is not None and _HIDDEN_CLEAR.search(single.group(2)):
        conditional_clear = True
    negated = re.search(rf"\.hidden\s*=\s*!\s*{word}", after_swap)
    ternary = re.search(rf"\.hidden\s*=\s*{word}\s*\?\s*false\s*:\s*true", after_swap)
    if negated is not None or ternary is not None:
        conditional_clear = True
    sets_true = _SET_EXPANDED_TRUE.search(after_swap) is not None or re.search(
        rf"""setAttribute\(\s*['"]aria-expanded['"]\s*,\s*[^;]*{word}""",
        after_swap,
    )
    return conditional_clear and sets_true is not None


def assert_expanded_refresh_clears_hidden(script: str) -> None:
    """Require the served app script to reopen details after a successful card swap."""
    assert "swapWishCard" in script, "could not read swapWishCard in served app.js"
    swap_at = script.find("outerHTML")
    assert swap_at != -1, "served page has no outerHTML refresh; expanded details stay hidden"
    reads = list(_ARIA_READ.finditer(script, 0, swap_at))
    assert reads, "refresh must read aria-expanded before outerHTML"
    flag = reads[-1].group(1)
    assert _restores_open_details(script[swap_at:], flag), (
        "copying aria-expanded leaves .item-card-details hidden"
    )


def test_identified_friend_sees_book_control_and_quantity_ceiling(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """A friend sees one book control and a selector that stops at the remainder."""
    client, sessions, app = test_app
    seeded = seed_personal(app.state.domain_service, quantity=3)
    headers = auth_header(sessions, _FRIEND_ID, "Bob")
    prefix = reservations_url(seeded.wishlist_id, seeded.item_id)
    pages = {
        "list": list_html(client, seeded.wishlist_id, headers),
        "share": share_html(client, seeded.public_token, headers),
    }
    gaps = [
        f"{name}: {gap}"
        for name, html in pages.items()
        for gap in book_control_gaps(card_tag(html, seeded.item_id), prefix, 3)
    ]
    assert gaps == [], gaps


def test_single_free_unit_has_no_quantity_select(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """One free unit is booked without a quantity selector."""
    client, sessions, app = test_app
    seeded = seed_personal(app.state.domain_service, quantity=1)
    headers = auth_header(sessions, _FRIEND_ID, "Bob")
    html = list_html(client, seeded.wishlist_id, headers)
    prefix = reservations_url(seeded.wishlist_id, seeded.item_id)
    gaps = book_control_gaps(card_tag(html, seeded.item_id), prefix, 1)
    assert gaps == [], gaps


def test_personal_owner_display_name_hides_giver_facts(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """A personal-list owner with only a display name sees no giver facts."""
    client, sessions, app = test_app
    seeded = seed_personal(
        app.state.domain_service,
        quantity=2,
        recipient_name="Бабушка",
    )
    headers = auth_header(sessions, _OWNER_ID, "Alice")
    html = list_html(client, seeded.wishlist_id, headers)
    present = labels_in(visible_text(card_tag(html, seeded.item_id)))
    assert present == [], present


def test_personal_owner_display_name_cannot_promise(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """That owner is the recipient, so create is refused and stores nothing."""
    client, sessions, app = test_app
    seeded = seed_personal(
        app.state.domain_service,
        quantity=2,
        recipient_name="Бабушка",
    )
    headers = auth_header(sessions, _OWNER_ID, "Alice")
    response = client.post(
        reservations_url(seeded.wishlist_id, seeded.item_id),
        json={"quantity": 1},
        headers=headers,
    )
    assert response.status_code == 403, response.text
    assert response.json() == {"detail": "Cannot promise this wish"}
    assert reservation_rows(app, seeded.item_id) == []


def test_collaborative_list_decides_recipient_per_wish(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """A display name does not make the caller the recipient of that wish."""
    client, sessions, app = test_app
    seeded = seed_collaborative(app.state.domain_service, app.state.user_store)
    headers = auth_header(sessions, _FRIEND_ID, "Bob")
    html = list_html(client, seeded.wishlist_id, headers)
    silent = labels_in(visible_text(card_tag(html, seeded.for_caller)))
    assert silent == [], silent
    gaps: list[str] = []
    for item_id, label in (
        (seeded.for_other, "wish for someone else"),
        (seeded.display_name, "display name matching the caller"),
    ):
        summary = visible_text(region(card_tag(html, item_id), "item-card-summary"))
        if "Забронировать" not in summary:
            gaps.append(f"{label} summary missing «Забронировать»")
    assert gaps == [], gaps


def test_own_line_and_availability_show_together(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """The own line stays beside the availability line in the summary."""
    client, sessions, app = test_app
    seeded = seed_personal(app.state.domain_service, quantity=3)
    headers = auth_header(sessions, _FRIEND_ID, "Bob")
    create_promise(client, seeded.wishlist_id, seeded.item_id, headers, quantity=1)
    card = card_tag(list_html(client, seeded.wishlist_id, headers), seeded.item_id)
    summary = visible_text(region(card, "item-card-summary"))
    details = visible_text(region(card, "item-card-details"))
    problems: list[str] = []
    if "Забронировано вами (1)" not in summary:
        problems.append("summary missing «Забронировано вами (1)»")
    if "Доступно: 2 из 3" not in summary:
        problems.append("summary missing «Доступно: 2 из 3»")
    if "Забронировано вами (1)" in details or "Доступно: 2 из 3" in details:
        problems.append("details repeat the giver lines")
    assert problems == [], problems


def test_single_bought_promise_shows_bought_and_undo(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """The only occupying promise, once bought, shows «Куплено» and undo."""
    client, sessions, app = test_app
    seeded = seed_personal(app.state.domain_service, quantity=1)
    headers = auth_header(sessions, _FRIEND_ID, "Bob")
    prefix = reservations_url(seeded.wishlist_id, seeded.item_id)
    reservation_id = create_promise(client, seeded.wishlist_id, seeded.item_id, headers)
    purchased = client.post(f"{prefix}/{reservation_id}/purchase", headers=headers)
    assert purchased.status_code == 200, purchased.text
    summary = region(
        card_tag(list_html(client, seeded.wishlist_id, headers), seeded.item_id),
        "item-card-summary",
    )
    line = own_line_text(summary)
    problems: list[str] = []
    if line is None or "Забронировано вами (1)" not in line:
        problems.append("summary missing «Забронировано вами (1)»")
    if line is None or "Куплено" not in line:
        problems.append("single bought promise is missing «Куплено»")
    undo_url = f"{prefix}/{reservation_id}/undo-purchase"
    undo = find_labeled(summary, "Вернуть в бронь")
    if undo is None or not same_url(undo.get("hx-post"), undo_url):
        problems.append(f"missing «Вернуть в бронь» POST {undo_url}")
    if posts_to(summary, f"{prefix}/{reservation_id}/purchase"):
        problems.append("bought promise still posts purchase")
    assert problems == [], problems


def test_several_occupying_promises_are_not_labeled_bought(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """Several occupying promises keep the sum unlabeled and target the latest id."""
    client, sessions, app = test_app
    seeded = seed_personal(app.state.domain_service, quantity=6)
    headers = auth_header(sessions, _FRIEND_ID, "Bob")
    prefix = reservations_url(seeded.wishlist_id, seeded.item_id)
    earlier_id = create_promise(client, seeded.wishlist_id, seeded.item_id, headers, quantity=1)
    latest_id = create_promise(client, seeded.wishlist_id, seeded.item_id, headers, quantity=2)
    purchased = client.post(f"{prefix}/{latest_id}/purchase", headers=headers)
    assert purchased.status_code == 200, purchased.text
    summary = region(
        card_tag(list_html(client, seeded.wishlist_id, headers), seeded.item_id),
        "item-card-summary",
    )
    line = own_line_text(summary)
    problems: list[str] = []
    if line is None or "Забронировано вами (3)" not in line:
        problems.append("summary missing «Забронировано вами (3)»")
    elif "Куплено" in line:
        problems.append("combined quantity is labeled bought")
    change = find_labeled(summary, "Изменить")
    if change is None or not same_url(change.get("hx-patch"), f"{prefix}/{latest_id}"):
        problems.append(f"missing «Изменить» PATCH {prefix}/{latest_id}")
    cancel = find_labeled(summary, "Отменить бронь")
    cancel_url = f"{prefix}/{latest_id}/cancel"
    if cancel is None or not same_url(cancel.get("hx-post"), cancel_url):
        problems.append(f"missing «Отменить бронь» POST {cancel_url}")
    undo = find_labeled(summary, "Вернуть в бронь")
    undo_url = f"{prefix}/{latest_id}/undo-purchase"
    if undo is None or not same_url(undo.get("hx-post"), undo_url):
        problems.append(f"missing «Вернуть в бронь» POST {undo_url}")
    select = summary.find("select", attrs={"name": "quantity"})
    if not isinstance(select, Tag):
        problems.append("missing change select")
    else:
        values, selected = select_facts(select)
        if values != [1, 2, 3, 4, 5] or selected != [2]:
            problems.append(
                f"change select values {values} selected {selected}, want 1..5 selected 2"
            )
    earlier_patch = f"{prefix}/{earlier_id}"
    if any(same_url(element.get("hx-patch"), earlier_patch) for element in summary.find_all(True)):
        problems.append("change targets an earlier promise")
    assert problems == [], problems


def test_anonymous_share_shows_availability_without_a_book_control(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """An anonymous share summary shows the remainder and no book control."""
    client, _sessions, app = test_app
    seeded = seed_personal(app.state.domain_service, quantity=2)
    card = card_tag(share_html(client, seeded.public_token), seeded.item_id)
    summary = visible_text(region(card, "item-card-summary"))
    problems: list[str] = []
    if "Доступно: 2 из 2" not in summary:
        problems.append("summary missing «Доступно: 2 из 2»")
    if "Забронировать" in summary:
        problems.append("anonymous summary has «Забронировать»")
    assert problems == [], problems


def test_shortage_leaves_the_last_promise(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """A 409 keeps the other gifter's promise and the summary says it is booked."""
    client, sessions, app = test_app
    seeded = seed_personal(app.state.domain_service, quantity=1, title="Lamp")
    bob = auth_header(sessions, _FRIEND_ID, "Bob")
    cara = auth_header(sessions, _OTHER_ID, "Cara")
    create_promise(client, seeded.wishlist_id, seeded.item_id, bob)
    before = reservation_rows(app, seeded.item_id)
    quantity_before = wish_quantity(app, seeded.item_id)
    refused = client.post(
        reservations_url(seeded.wishlist_id, seeded.item_id),
        json={"quantity": 1},
        headers=cara,
    )
    assert refused.status_code == 409, refused.text
    assert "Bob" not in refused.text
    assert reservation_rows(app, seeded.item_id) == before
    assert wish_quantity(app, seeded.item_id) == quantity_before
    page = list_html(client, seeded.wishlist_id, cara)
    summary = visible_text(region(card_tag(page, seeded.item_id), "item-card-summary"))
    problems: list[str] = []
    if "Забронировано вами" in summary:
        problems.append("summary names a holder who is not the viewer")
    if "Забронировать" in summary:
        problems.append("book control is visible when nothing is free")
    if "Забронировано" not in summary:
        problems.append("summary missing «Забронировано»")
    assert problems == [], problems


def test_busy_inventory_does_not_look_like_a_booking(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A busy wish returns 503, writes nothing, and leaves the book control."""
    client, sessions, app = test_app
    seeded = seed_personal(app.state.domain_service, quantity=2)
    headers = auth_header(sessions, _FRIEND_ID, "Bob")

    async def busy(*_args: object, **_kwargs: object) -> None:
        raise InventoryBusyError()

    monkeypatch.setattr(app.state.wishlist_store, "execute_wish", busy)
    before = reservation_rows(app, seeded.item_id)
    response = client.post(
        reservations_url(seeded.wishlist_id, seeded.item_id),
        json={"quantity": 1},
        headers=headers,
    )
    assert response.status_code == 503, response.text
    detail = str(response.json().get("detail", ""))
    assert "Bob" not in detail
    assert reservation_rows(app, seeded.item_id) == before
    html = list_html(client, seeded.wishlist_id, headers)
    card = card_tag(html, seeded.item_id)
    summary = visible_text(region(card, "item-card-summary"))
    problems: list[str] = []
    if detail and detail in visible_text(card):
        problems.append("503 body is shown on the card")
    if "Забронировано вами" in summary:
        problems.append("busy create looks like a booking")
    if "Забронировать" not in summary:
        problems.append("book control did not remain")
    assert problems == [], problems


def test_cancel_restores_a_create_not_a_patch(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """After the only promise is cancelled, booking creates a new promise."""
    client, sessions, app = test_app
    seeded = seed_personal(app.state.domain_service, quantity=1)
    headers = auth_header(sessions, _FRIEND_ID, "Bob")
    prefix = reservations_url(seeded.wishlist_id, seeded.item_id)
    reservation_id = create_promise(client, seeded.wishlist_id, seeded.item_id, headers)
    cancelled = client.post(f"{prefix}/{reservation_id}/cancel", headers=headers)
    assert cancelled.status_code == 200, cancelled.text
    rows = reservation_rows(app, seeded.item_id)
    assert rows == [(reservation_id, 1, "cancelled", _FRIEND_ID)]
    card = card_tag(list_html(client, seeded.wishlist_id, headers), seeded.item_id)
    summary = region(card, "item-card-summary")
    patches = [
        element
        for element in card.find_all(True)
        if same_url(element.get("hx-patch"), f"{prefix}/{reservation_id}")
        or (
            isinstance(element.get("hx-patch"), str)
            and f"/{reservation_id}" in str(element.get("hx-patch"))
        )
    ]
    problems: list[str] = []
    if "Забронировать" not in visible_text(summary) or len(posts_to(summary, prefix)) != 1:
        problems.append(
            f"after cancel, «Забронировать» must POST the collection, not PATCH /{reservation_id}"
        )
    if patches:
        problems.append(f"card still PATCHes cancelled promise {reservation_id}")
    assert problems == [], problems


def test_archive_title_row_has_no_giver_controls(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """The archived title row does not gain giver controls."""
    client, sessions, app = test_app
    seeded = seed_personal(app.state.domain_service, quantity=1, title="Vase")
    headers = auth_header(sessions, _OWNER_ID, "Alice")
    archived = client.post(
        f"/api/wishlists/{seeded.wishlist_id}/items/{seeded.item_id}/archive",
        headers=headers,
    )
    assert archived.status_code == 200, archived.text
    section = parse_html(list_html(client, seeded.wishlist_id, headers)).find(
        id="archived-items-section"
    )
    assert isinstance(section, Tag), "missing archived section"
    row = section.find(id=f"archived-item-{seeded.item_id}")
    assert isinstance(row, Tag), "missing archived title row"
    text = visible_text(row)
    assert "Vase" in text
    assert labels_in(text) == []


def test_expanded_refresh_clears_hidden_on_details(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """A successful refresh keeps an expanded card open, details included."""
    client, sessions, app = test_app
    seeded = seed_personal(app.state.domain_service, quantity=1)
    headers = auth_header(sessions, _FRIEND_ID, "Bob")
    html = list_html(client, seeded.wishlist_id, headers)
    assert "/static/app.js" in html
    app_js = client.get("/static/app.js")
    assert app_js.status_code == 200, app_js.text
    assert_expanded_refresh_clears_hidden(app_js.text)


def test_recipient_notice_refresh_has_no_booking_sentence(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """A recipient refresh omits notice text and every booking sentence."""
    client, sessions, app = test_app
    seeded = seed_personal(
        app.state.domain_service,
        quantity=2,
        recipient_name="Бабушка",
    )
    headers = auth_header(sessions, _OWNER_ID, "Alice")
    problems: list[str] = []
    for notice in ("refused", "shortage"):
        body = card_html(
            client,
            seeded.wishlist_id,
            seeded.item_id,
            headers,
            notice=notice,
        )
        present = labels_in(body, _RECIPIENT_NOTICE_BANNED)
        if present:
            problems.append(f"notice={notice}: {present}")
    assert problems == [], problems


def test_gifter_refusal_notice_names_no_holder(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """A gifter refusal says the booking did not change and names nobody."""
    client, sessions, app = test_app
    seeded = seed_personal(app.state.domain_service, quantity=3, title="Blanket")
    cara = auth_header(sessions, _OTHER_ID, "Cara")
    bob = auth_header(sessions, _FRIEND_ID, "Bob")
    create_promise(client, seeded.wishlist_id, seeded.item_id, cara, quantity=1)
    body = card_html(
        client,
        seeded.wishlist_id,
        seeded.item_id,
        bob,
        notice="refused",
    )
    problems: list[str] = []
    if "Бронь не изменилась." not in body:
        problems.append("missing «Бронь не изменилась.»")
    if "Cara" in body:
        problems.append("notice names another gifter")
    assert problems == [], problems


def test_personal_owner_mutations_are_not_found(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """A personal-list owner cannot change, cancel, buy, or undo a promise."""
    client, sessions, app = test_app
    seeded = seed_personal(
        app.state.domain_service,
        quantity=2,
        recipient_name="Бабушка",
    )
    friend = auth_header(sessions, _FRIEND_ID, "Bob")
    owner = auth_header(sessions, _OWNER_ID, "Alice")
    prefix = reservations_url(seeded.wishlist_id, seeded.item_id)
    reservation_id = create_promise(client, seeded.wishlist_id, seeded.item_id, friend)
    attempts = (
        ("cancel", "POST", f"{prefix}/{reservation_id}/cancel", None),
        ("change", "PATCH", f"{prefix}/{reservation_id}", {"quantity": 1}),
        ("purchase", "POST", f"{prefix}/{reservation_id}/purchase", None),
        ("undo", "POST", f"{prefix}/{reservation_id}/undo-purchase", None),
    )
    problems: list[str] = []
    for label, method, url, payload in attempts:
        if payload is None:
            response = client.request(method, url, headers=owner)
        else:
            response = client.request(method, url, headers=owner, json=payload)
        if response.status_code != 404 or response.json() != {"detail": "Resource not found"}:
            problems.append(f"{label} -> {response.status_code} {response.text}")
    assert problems == [], problems
