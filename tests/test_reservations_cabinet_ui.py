"""Red repro for the reservations cabinet (WISHENKA-20).

The checks assert the accepted home card and cabinet. They fail while
``/web/reservations`` is not served. Promise writes go through the existing
API. No Telegram, no second process, and no live lock.
"""

from __future__ import annotations

import asyncio
import re
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

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
_CARD_URL = "/web/reservations/card"
_CABINET_URL = "/web/reservations"
_LIST_URL = "/web/reservations/list"
_CABINET_TITLE = "Мои бронирования"
_EMPTY_COPY = "Нет бронирований"
_WISH_LINK = "К желанию"
_ARCHIVED_WISH = "Желание в архиве"
_ARCHIVED_LIST = "Вишлист в архиве"
_BOOKED = "Забронировано"
_BOUGHT = "Куплено"
_BUSY_SENTENCE = "Желание занято, бронь не изменилась. Повторите попытку."
_ACTION_LABELS = ("Изменить", "Отменить бронь", _BOUGHT, "Вернуть в бронь")
_EVENT_DAY = "15.03.2026"
_EVENT_TITLE = "Пикник"


class WishDraft(NamedTuple):
    """One wish to add while seeding a list."""

    title: str
    quantity: int = 1
    recipient_name: str | None = None
    recipient_user_id: int | None = None


class SeededList(NamedTuple):
    """A list created through the domain service."""

    wishlist_id: int
    public_token: str
    item_ids: tuple[int, ...]


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


def promise_url(wishlist_id: int, item_id: int, reservation_id: int, suffix: str = "") -> str:
    """Return one existing promise route."""
    base = f"{reservations_url(wishlist_id, item_id)}/{reservation_id}"
    return f"{base}{suffix}"


def wish_href(wishlist_id: int, item_id: int) -> str:
    """Return the cabinet link that opens one wish card."""
    return f"/web/wishlists/{wishlist_id}#item-card-{item_id}"


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


@pytest.fixture
def test_app(tmp_path: Path) -> Iterator[tuple[TestClient, SessionTokenService, FastAPI]]:
    """Open create_app on a temporary SQLite file with bearer sessions."""
    database = tmp_path / "reservations_cabinet_ui.db"
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{database}",
        secret_key="reservations-cabinet-ui-test-secret",
    )
    app = create_app(settings)
    sessions = SessionTokenService(settings.secret_key)
    with TestClient(app) as client:

        async def _seed_users() -> None:
            for uid in (_OWNER_ID, _FRIEND_ID, _OTHER_ID, 404, 505):
                await app.state.user_store.upsert_user(
                    TelegramUser(id=uid, first_name=f"User{uid}", language_code="ru")
                )

        asyncio.run(_seed_users())
        yield client, sessions, app


def seed_list(
    service: WishlistService,
    *,
    title: str,
    wishes: tuple[WishDraft, ...],
    owner_id: int = _OWNER_ID,
    owner_name: str = "Alice",
    event_title: str | None = None,
    event_date: datetime | None = None,
    member_ids: tuple[int, ...] = (),
) -> SeededList:
    """Create one list and its wishes through the domain service."""
    owner = make_user(owner_id, owner_name)

    async def create() -> SeededList:
        wishlist = await service.create_wishlist(
            owner=owner,
            title=title,
            event_title=event_title,
            event_date=event_date,
        )
        for member_id in member_ids:
            await service.add_member(
                wishlist_id=wishlist.id,
                actor=owner,
                user_id=member_id,
            )
        item_ids: list[int] = []
        for wish in wishes:
            item = await service.add_wish_item(
                wishlist_id=wishlist.id,
                actor=owner,
                title=wish.title,
                quantity=wish.quantity,
                recipient_name=wish.recipient_name,
                recipient_user_id=wish.recipient_user_id,
            )
            item_ids.append(item.id)
        return SeededList(wishlist.id, str(wishlist.public_token), tuple(item_ids))

    return asyncio.run(create())


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


def post_ok(client: TestClient, url: str, headers: dict[str, str]) -> None:
    """POST an existing promise route that should succeed."""
    response = client.post(url, headers=headers)
    assert response.status_code == 200, response.text


def archive_item(
    client: TestClient,
    wishlist_id: int,
    item_id: int,
    headers: dict[str, str],
) -> None:
    """Archive one wish through the existing item route."""
    response = client.post(
        f"/api/wishlists/{wishlist_id}/items/{item_id}/archive",
        headers=headers,
    )
    assert response.status_code == 200, response.text


def archive_list(client: TestClient, wishlist_id: int, headers: dict[str, str]) -> None:
    """Archive one list through the existing wishlist route."""
    response = client.post(f"/api/wishlists/{wishlist_id}/archive", headers=headers)
    assert response.status_code == 200, response.text


def delete_list(service: WishlistService, wishlist_id: int) -> None:
    """Delete one list through the domain service."""
    owner = make_user(_OWNER_ID, "Alice")

    async def remove() -> None:
        await service.delete_wishlist(wishlist_id, owner)

    asyncio.run(remove())


def visible_text(node: BeautifulSoup | Tag) -> str:
    """Return rendered text with scripts removed and whitespace collapsed."""
    cloned = BeautifulSoup(str(node), "html.parser")
    for script in cloned.find_all("script"):
        script.decompose()
    return " ".join(cloned.get_text(" ", strip=True).split())


def parse_html(html: str) -> BeautifulSoup:
    """Parse one served page or fragment."""
    return BeautifulSoup(html, "html.parser")


def has_number(text: str, number: int) -> bool:
    """Return whether text contains number as a whole integer."""
    return re.search(rf"(?<!\d){number}(?!\d)", text) is not None


def has_reservation_path(html: str, reservation_id: int) -> bool:
    """Return whether html links one reservation id."""
    return re.search(rf"/reservations/{reservation_id}(?!\d)", html) is not None


def same_path(actual: object, expected: str) -> bool:
    """Compare a URL without its query string."""
    if not isinstance(actual, str):
        return False
    return actual.split("?", 1)[0].rstrip("/") == expected.rstrip("/")


def find_labeled(root: BeautifulSoup | Tag, label: str) -> Tag | None:
    """Return the button or link whose visible text is the label."""
    for element in root.find_all(["button", "a"]):
        if visible_text(element) == label:
            return element
    return None


def _in_row(element: Tag, row: Tag) -> bool:
    """Return whether element is still inside row."""
    current: Tag | None = element
    while isinstance(current, Tag):
        if current is row:
            return True
        parent = current.parent
        current = parent if isinstance(parent, Tag) else None
    return False


def attr_in_row(element: Tag, row: Tag, name: str) -> str | None:
    """Return an attribute from the element or an ancestor inside the row."""
    current: Tag | None = element
    while isinstance(current, Tag) and _in_row(current, row):
        raw = current.get(name)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        parent = current.parent
        current = parent if isinstance(parent, Tag) else None
    return None


def page_or_problem(
    response: object,
    url: str,
) -> tuple[list[str], BeautifulSoup | None]:
    """Return a status problem, or the parsed document when the route exists."""
    status = getattr(response, "status_code", None)
    body = getattr(response, "text", "")
    if status != 200:
        return [f"{url} returned {status}, want 200"], None
    return [], parse_html(str(body))


def cabinet_node(soup: BeautifulSoup) -> tuple[Tag | None, list[str]]:
    """Return the refresh target, or a problem when it is missing."""
    found = soup.find(id="reservations-cabinet")
    if isinstance(found, Tag):
        return found, []
    return None, ["missing #reservations-cabinet"]


def groups_of(soup: BeautifulSoup) -> list[Tag]:
    """Return cabinet groups in document order."""
    return [node for node in soup.select(".reservation-group") if isinstance(node, Tag)]


def rows_of(root: BeautifulSoup | Tag) -> list[Tag]:
    """Return promise rows in document order."""
    return [node for node in root.select(".reservation-row") if isinstance(node, Tag)]


def group_named(soup: BeautifulSoup, title: str) -> Tag | None:
    """Return the group whose text contains one exact list title."""
    for group in groups_of(soup):
        if title in visible_text(group):
            return group
    return None


def group_names(soup: BeautifulSoup) -> list[str]:
    """Return known list titles in group order."""
    known = ("Апельсин", "апельсин", "ягоды")
    names: list[str] = []
    for group in groups_of(soup):
        text = visible_text(group)
        hits = [title for title in known if title in text]
        names.append("+".join(hits))
    return names


def row_with_quantity(
    root: BeautifulSoup | Tag,
    quantity: int,
    blocked: tuple[int, ...] = (),
) -> Tag | None:
    """Return the row whose visible text contains quantity and not blocked."""
    for row in rows_of(root):
        text = visible_text(row)
        if has_number(text, quantity) and not any(has_number(text, item) for item in blocked):
            return row
    return None


def row_for_reservation(root: BeautifulSoup | Tag, reservation_id: int) -> Tag | None:
    """Return the row that posts or patches one reservation id."""
    for row in rows_of(root):
        if has_reservation_path(str(row), reservation_id):
            return row
    return None


def option_values(row: Tag) -> list[int] | None:
    """Return quantity option values, or None when the select is missing."""
    select = row.find("select", attrs={"name": "quantity"})
    if not isinstance(select, Tag):
        return None
    values: list[int] = []
    for option in select.find_all("option"):
        raw = option.get("value")
        if isinstance(raw, str) and raw.strip().isdigit():
            values.append(int(raw))
    return values


def link_gaps(row: Tag, wishlist_id: int, item_id: int) -> list[str]:
    """Return problems for the wish link on one row."""
    expected = wish_href(wishlist_id, item_id)
    link = find_labeled(row, _WISH_LINK)
    if link is None:
        return [f"missing «{_WISH_LINK}» {expected}"]
    href = link.get("href")
    if href != expected:
        return [f"«{_WISH_LINK}» href is {href!r}, want {expected}"]
    return []


def action_gaps(row: Tag, label: str, attr: str, url: str, *, json_enc: bool) -> list[str]:
    """Return problems for one labeled promise action."""
    element = find_labeled(row, label)
    if element is None:
        return [f"missing «{label}»"]
    gaps: list[str] = []
    actual = attr_in_row(element, row, attr)
    if not same_path(actual, url):
        gaps.append(f"«{label}» {attr} is {actual!r}, want {url}")
    if attr_in_row(element, row, "hx-swap") != "none":
        gaps.append(f"«{label}» missing hx-swap none")
    if json_enc and attr_in_row(element, row, "hx-ext") != "json-enc":
        gaps.append(f"«{label}» missing hx-ext json-enc")
    return gaps


def source_between(source: str, start_marker: str, end_marker: str) -> str:
    """Return the source slice from start_marker up to end_marker."""
    start = source.find(start_marker)
    if start < 0:
        return ""
    end = source.find(end_marker, start + len(start_marker))
    if end < 0:
        return ""
    return source[start:end]


def _skip_js_string(text: str, start: int) -> int:
    """Return the index just after a JS string that starts at start."""
    quote = text[start]
    index = start + 1
    while index < len(text):
        if text[index] == "\\":
            index += 2
            continue
        if text[index] == quote:
            return index + 1
        index += 1
    return len(text)


def brace_body(text: str, open_index: int) -> str:
    """Return the inside of the brace at open_index, skipping JS strings."""
    if open_index >= len(text) or text[open_index] != "{":
        return ""
    depth = 0
    index = open_index
    while index < len(text):
        char = text[index]
        if char in {"'", '"', "`"}:
            index = _skip_js_string(text, index)
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[open_index + 1 : index]
        index += 1
    return ""


def reservation_row_block(script: str) -> str:
    """Return the listener branch that refreshes a cabinet row."""
    start = script.find(".reservation-row")
    if start < 0:
        return ""
    rest = script[start:]
    search = 0
    while True:
        brace = rest.find("{", search)
        if brace < 0:
            return ""
        body = brace_body(rest, brace)
        if "/web/reservations/list" in body or "data-reservation-busy" in body:
            return body
        search = brace + 1


def home_script_problems(source: str) -> list[str]:
    """Return problems in the home, public, and invitation scripts."""
    home = source_between(source, "async function showHome(", "function settingsForm(")
    public = source_between(source, "async function publicView(", "async function invitationView(")
    invite = source_between(source, "async function invitationView(", "async function bootstrap(")
    problems: list[str] = []
    if not home:
        problems.append("miniapp.js is missing showHome")
        return problems
    if _CARD_URL not in home:
        problems.append("showHome does not request /web/reservations/card")
    if "node(" not in home:
        problems.append("showHome does not insert the card with node()")
    forbidden = ("innerHTML", "insertAdjacentHTML", "createContextualFragment")
    if any(token in home for token in forbidden):
        problems.append("showHome assigns the card fragment as HTML")
    if _CARD_URL in public or _CARD_URL in invite:
        problems.append("publicView or invitationView requests the reservations card")
    return problems


def refresh_script_problems(script: str) -> list[str]:
    """Return problems in the cabinet branch of the base listener."""
    block = reservation_row_block(script)
    if not block:
        return ["base.html has no .reservation-row refresh branch"]
    problems: list[str] = []
    if _LIST_URL not in block:
        problems.append("row refresh does not fetch GET /web/reservations/list")
    if "/items/" in block or "createContextualFragment" in block or "innerHTML" in block:
        problems.append("row refresh writes the wish card or response HTML")
    if "insertAdjacentHTML" in block:
        problems.append("row refresh inserts the response as HTML")
    busy = ""
    marker = block.find("503")
    if marker >= 0:
        brace = block.find("{", marker)
        if brace >= 0:
            busy = brace_body(block, brace)
    if ("data-i18n-busy-error" not in block and _BUSY_SENTENCE not in block) or (
        "data-reservation-busy" not in block
    ):
        problems.append("503 branch does not show the fixed busy sentence")
    if not busy or _LIST_URL in busy or "reservations-cabinet" in busy:
        problems.append("503 replaces #reservations-cabinet")
    return problems


def base_script(client: TestClient, wishlist_id: int, headers: dict[str, str]) -> str:
    """Return inline scripts from a page that extends base.html."""
    response = client.get(f"/web/wishlists/{wishlist_id}", headers=headers)
    assert response.status_code == 200, response.text
    parts: list[str] = []
    for node in parse_html(response.text).find_all("script"):
        if node.get("src"):
            continue
        parts.append(node.get_text())
    return "\n".join(parts)


def static_script(client: TestClient, path: str) -> str:
    """Return one served static script."""
    response = client.get(path)
    assert response.status_code == 200, response.text
    body = response.text
    assert isinstance(body, str)
    return body


def test_home_card_counts_distinct_wishes(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """Two purchased promises on one wish count once; a cancelled wish does not."""
    client, sessions, app = test_app
    seeded = seed_list(
        app.state.domain_service,
        title="Alice Birthday",
        wishes=(
            WishDraft("Headphones", quantity=4),
            WishDraft("Cancelled mug", quantity=1),
        ),
    )
    bob = auth_header(sessions, _FRIEND_ID, "Bob")
    wish_id, cancelled_id = seeded.item_ids
    prefix = reservations_url(seeded.wishlist_id, wish_id)
    first = create_promise(client, seeded.wishlist_id, wish_id, bob, quantity=1)
    second = create_promise(client, seeded.wishlist_id, wish_id, bob, quantity=2)
    post_ok(client, f"{prefix}/{first}/purchase", bob)
    post_ok(client, f"{prefix}/{second}/purchase", bob)
    dropped = create_promise(client, seeded.wishlist_id, cancelled_id, bob, quantity=1)
    post_ok(client, f"{reservations_url(seeded.wishlist_id, cancelled_id)}/{dropped}/cancel", bob)
    stored = reservation_rows(app, wish_id)
    assert stored == [
        (first, 1, "purchased", _FRIEND_ID),
        (second, 2, "purchased", _FRIEND_ID),
    ]

    response = client.get(_CARD_URL, headers=bob)
    problems, soup = page_or_problem(response, _CARD_URL)
    if soup is not None:
        text = visible_text(soup)
        badge = soup.select_one(".reservations-badge")
        badge_text = visible_text(badge) if isinstance(badge, Tag) else ""
        hrefs = [tag.get("href") for tag in soup.find_all("a") if isinstance(tag, Tag)]
        if _CABINET_TITLE not in text:
            problems.append("card missing «Мои бронирования»")
        if badge_text != "1":
            problems.append(
                f"badge is {badge_text!r}, want 1 "
                "(two purchased promises count once, units are 3, cancelled does not count)"
            )
        if not any(same_path(href, _CABINET_URL) for href in hrefs):
            problems.append(f"card links {hrefs}, want {_CABINET_URL}")
    problems.extend(home_script_problems(static_script(client, "/static/miniapp.js")))
    assert problems == [], problems


def test_empty_cabinet(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """An identified caller with no occupying promise sees a zero badge and an empty page."""
    client, sessions, _app = test_app
    bob = auth_header(sessions, _FRIEND_ID, "Bob")
    card = client.get(_CARD_URL, headers=bob)
    page = client.get(_CABINET_URL, headers=bob)
    problems, card_soup = page_or_problem(card, _CARD_URL)
    page_problems, page_soup = page_or_problem(page, _CABINET_URL)
    problems.extend(page_problems)
    if card_soup is not None:
        badge = card_soup.select_one(".reservations-badge")
        badge_text = visible_text(badge) if isinstance(badge, Tag) else ""
        if badge_text != "0":
            problems.append(f"empty badge is {badge_text!r}, want 0")
    if page_soup is not None:
        title = page_soup.title.get_text(strip=True) if page_soup.title else ""
        headings = [visible_text(tag) for tag in page_soup.find_all("h1")]
        text = visible_text(page_soup)
        if title != _CABINET_TITLE and _CABINET_TITLE not in headings:
            problems.append(f"page title is {title!r}, want «{_CABINET_TITLE}»")
        if _EMPTY_COPY not in text:
            problems.append("empty cabinet missing «Нет бронирований»")
        if groups_of(page_soup):
            problems.append("empty cabinet renders a reservation group")
    assert problems == [], problems


def test_anonymous_gets_neither(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """A caller with no session gets 401, and public pages do not show the cabinet."""
    client, _sessions, app = test_app
    seeded = seed_list(
        app.state.domain_service,
        title="Public list",
        wishes=(WishDraft("Mug", quantity=1),),
    )
    share = client.get(f"/share/{seeded.public_token}")
    shell = client.get("/")
    assert share.status_code == 200, share.text
    assert shell.status_code == 200, shell.text
    assert _CABINET_TITLE not in share.text
    assert _CABINET_TITLE not in shell.text

    problems: list[str] = []
    for url in (_CARD_URL, _CABINET_URL, _LIST_URL):
        response = client.get(url)
        if response.status_code != 401:
            problems.append(f"{url} returned {response.status_code}, want 401")
        if _CABINET_TITLE in response.text or _EMPTY_COPY in response.text:
            problems.append(f"{url} shows cabinet copy to an anonymous caller")
        if "reservations-badge" in response.text:
            problems.append(f"{url} shows a badge to an anonymous caller")
    assert problems == [], problems


def test_groups_only_the_callers_promises(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """Groups follow casefold then id, and other gifters are absent."""
    client, sessions, app = test_app
    members = (_FRIEND_ID, _OTHER_ID)
    berries = seed_list(
        app.state.domain_service,
        title="ягоды",
        member_ids=members,
        wishes=(
            WishDraft("Шапка", quantity=60, recipient_name="Нина"),
            WishDraft("Шарф", quantity=1, recipient_name="Нина"),
        ),
    )
    plain = seed_list(
        app.state.domain_service,
        title="апельсин",
        member_ids=members,
        wishes=(WishDraft("Ваза", quantity=20, recipient_name="Нина"),),
    )
    event = seed_list(
        app.state.domain_service,
        title="Апельсин",
        member_ids=members,
        event_title=_EVENT_TITLE,
        event_date=datetime(2026, 3, 15, 12, 0, tzinfo=UTC),
        wishes=(WishDraft("Торт", quantity=20, recipient_name="Нина"),),
    )
    seed_list(
        app.state.domain_service,
        title="Манго",
        wishes=(WishDraft("Никто", quantity=1),),
    )
    bob = auth_header(sessions, _FRIEND_ID, "Bob")
    alice = auth_header(sessions, _OWNER_ID, "Alice")
    cara = auth_header(sessions, _OTHER_ID, "Cara")
    hat, scarf = berries.item_ids
    earlier = create_promise(client, berries.wishlist_id, hat, bob, quantity=11)
    later = create_promise(client, berries.wishlist_id, hat, bob, quantity=12)
    post_ok(client, promise_url(berries.wishlist_id, hat, later, "/purchase"), bob)
    create_promise(client, berries.wishlist_id, hat, alice, quantity=13)
    create_promise(client, berries.wishlist_id, hat, cara, quantity=14)
    cancelled = create_promise(client, berries.wishlist_id, scarf, bob, quantity=1)
    post_ok(client, promise_url(berries.wishlist_id, scarf, cancelled, "/cancel"), bob)
    create_promise(client, plain.wishlist_id, plain.item_ids[0], bob, quantity=15)
    create_promise(client, event.wishlist_id, event.item_ids[0], bob, quantity=16)
    assert [row[2] for row in reservation_rows(app, hat)] == [
        "active",
        "purchased",
        "active",
        "active",
    ]

    response = client.get(_CABINET_URL, headers=bob)
    problems, soup = page_or_problem(response, _CABINET_URL)
    if soup is None:
        assert problems == [], problems
        return
    root, missing = cabinet_node(soup)
    problems.extend(missing)
    scope = root if root is not None else soup
    text = visible_text(scope)
    raw = str(scope)
    expected = ["апельсин", "Апельсин", "ягоды"]
    if group_names(soup) != expected:
        problems.append(
            f"groups are {group_names(soup)}, want {expected} "
            "(casefold, then wishlist id; я sorts last)"
        )
    berries_group = group_named(soup, "ягоды")
    plain_group = group_named(soup, "апельсин")
    event_group = group_named(soup, "Апельсин")
    if berries_group is None or plain_group is None or event_group is None:
        problems.append("missing one wishlist group")
    else:
        berry_rows = rows_of(berries_group)
        if len(berry_rows) != 2:
            problems.append(f"ягоды has {len(berry_rows)} rows, want the two occupying promises")
        elif not has_number(visible_text(berry_rows[0]), 11) or not has_number(
            visible_text(berry_rows[1]), 12
        ):
            problems.append("rows are not ordered by created_at then reservation id")
        event_text = visible_text(event_group)
        if _EVENT_TITLE not in event_text or _EVENT_DAY not in event_text:
            problems.append("event group missing the event title or UTC date")
        for quiet in (plain_group, berries_group):
            quiet_text = visible_text(quiet)
            if _EVENT_TITLE in quiet_text or _EVENT_DAY in quiet_text:
                problems.append("a list without an event shows the event title or date")
    for label in (_BOOKED, _BOUGHT, "Нина"):
        if label not in text:
            problems.append(f"cabinet missing {label}")
    if not all(has_number(text, number) for number in (11, 12, 15, 16)):
        problems.append("cabinet missing one of Bob's quantities")
    for banned in ("Alice", "Cara", "Recipient", "Шарф", "Манго"):
        if banned in text or banned in raw:
            problems.append(f"cabinet shows {banned}")
    for number in (13, 14, 60):
        if has_number(text, number):
            problems.append(f"cabinet shows quantity {number}")
    assert earlier != later
    assert problems == [], problems


def test_personal_owner_and_collaborative_recipient(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """A personal row names the owner; a collaborative row names only the real recipient."""
    client, sessions, app = test_app
    personal = seed_list(
        app.state.domain_service,
        title="Personal",
        wishes=(WishDraft("Кружка", quantity=1, recipient_name="Нина"),),
    )
    shared = seed_list(
        app.state.domain_service,
        title="Shared",
        member_ids=(_FRIEND_ID, _OTHER_ID),
        wishes=(
            WishDraft("Чашка", quantity=1, recipient_user_id=_OWNER_ID),
            WishDraft("Шарф", quantity=1, recipient_name="Кузен"),
            WishDraft(
                "Плед",
                quantity=1,
                recipient_user_id=_OTHER_ID,
                recipient_name="Нина",
            ),
        ),
    )
    bob = auth_header(sessions, _FRIEND_ID, "Bob")
    alice = auth_header(sessions, _OWNER_ID, "Alice")
    cup = personal.item_ids[0]
    for_alice, display_only, for_cara = shared.item_ids
    create_promise(client, personal.wishlist_id, cup, bob)
    create_promise(client, shared.wishlist_id, for_alice, bob)
    create_promise(client, shared.wishlist_id, display_only, bob)
    create_promise(client, shared.wishlist_id, for_cara, bob)

    alice_card = client.get(_CARD_URL, headers=alice)
    alice_page = client.get(_CABINET_URL, headers=alice)
    bob_page = client.get(_CABINET_URL, headers=bob)
    problems, alice_card_soup = page_or_problem(alice_card, _CARD_URL)
    page_problems, alice_soup = page_or_problem(alice_page, _CABINET_URL)
    problems.extend(page_problems)
    bob_problems, bob_soup = page_or_problem(bob_page, _CABINET_URL)
    problems.extend(bob_problems)
    if alice_card_soup is not None:
        badge = alice_card_soup.select_one(".reservations-badge")
        badge_text = visible_text(badge) if isinstance(badge, Tag) else ""
        card_text = visible_text(alice_card_soup)
        if badge_text != "0":
            problems.append(f"owner badge is {badge_text!r}, want 0")
        if "Bob" in card_text or "Кружка" in card_text:
            problems.append("owner card shows another person's promise")
    if alice_soup is not None:
        text = visible_text(alice_soup)
        for banned in ("Bob", "Кружка", "Чашка", "Шарф", "Плед"):
            if banned in text:
                problems.append(f"owner cabinet shows {banned}")
    if bob_soup is not None:
        text = visible_text(bob_soup)
        raw = str(bob_soup)
        cara_label = f"Участник #{_OTHER_ID}"
        for required in ("Кружка", "Чашка", "Шарф", "Плед", "Кузен", "Alice", cara_label):
            if required not in text:
                problems.append(f"Bob's cabinet missing {required}")
        if "Нина" in text or "Нина" in raw or "Recipient" in text:
            problems.append("Bob's cabinet uses a display name or Recipient")
        if f"Участник #{_OWNER_ID}" in text:
            problems.append("owner label fell back to a participant id")
        named = {
            "Кружка": "Alice",
            "Чашка": "Alice",
            "Шарф": "Кузен",
            "Плед": cara_label,
        }
        for title, who in named.items():
            matched = [row for row in rows_of(bob_soup) if title in visible_text(row)]
            if len(matched) != 1:
                problems.append(f"expected one row for {title}")
                continue
            row_text = visible_text(matched[0])
            if who not in row_text:
                problems.append(f"{title} does not name {who}")
            if title == "Шарф" and "Alice" in row_text:
                problems.append("display-name row names the list owner")
            if title == "Плед" and "Нина" in row_text:
                problems.append("designated member row uses someone else's display name")
    assert problems == [], problems


def test_active_wish_offers_only_the_link(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """While giver controls remain, every promise row offers only the wish link."""
    client, sessions, app = test_app
    seeded = seed_list(
        app.state.domain_service,
        title="Open list",
        wishes=(WishDraft("Лампа", quantity=30),),
    )
    bob = auth_header(sessions, _FRIEND_ID, "Bob")
    item_id = seeded.item_ids[0]
    create_promise(client, seeded.wishlist_id, item_id, bob, quantity=11)
    create_promise(client, seeded.wishlist_id, item_id, bob, quantity=12)
    response = client.get(_CABINET_URL, headers=bob)
    problems, soup = page_or_problem(response, _CABINET_URL)
    if soup is None:
        assert problems == [], problems
        return
    rows = rows_of(soup)
    if len(rows) != 2:
        problems.append(f"active wish has {len(rows)} rows, want 2")
    for quantity in (11, 12):
        row = row_with_quantity(soup, quantity, blocked=(12 if quantity == 11 else 11,))
        if row is None:
            problems.append(f"missing row for quantity {quantity}")
            continue
        problems.extend(link_gaps(row, seeded.wishlist_id, item_id))
        rendered = visible_text(row)
        for label in _ACTION_LABELS:
            if label in rendered:
                problems.append(f"active row shows «{label}»")
        if "/reservations/" in str(row):
            problems.append("active row contains a reservation write URL")
    assert problems == [], problems


def test_archived_wish_on_active_list_offers_each_promise(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """An archived wish on an active list offers each promise's own actions."""
    client, sessions, app = test_app
    seeded = seed_list(
        app.state.domain_service,
        title="Still open",
        wishes=(WishDraft("Ваза", quantity=5),),
    )
    bob = auth_header(sessions, _FRIEND_ID, "Bob")
    cara = auth_header(sessions, _OTHER_ID, "Cara")
    owner = auth_header(sessions, _OWNER_ID, "Alice")
    item_id = seeded.item_ids[0]
    earlier = create_promise(client, seeded.wishlist_id, item_id, bob, quantity=1)
    later = create_promise(client, seeded.wishlist_id, item_id, bob, quantity=2)
    cara_id = create_promise(client, seeded.wishlist_id, item_id, cara, quantity=1)
    post_ok(client, promise_url(seeded.wishlist_id, item_id, later, "/purchase"), bob)
    archive_item(client, seeded.wishlist_id, item_id, owner)
    # Free remainder is 1. Ceiling is this promise's quantity plus that remainder.
    response = client.get(_CABINET_URL, headers=bob)
    problems, soup = page_or_problem(response, _CABINET_URL)
    if soup is None:
        assert problems == [], problems
        return
    rows = rows_of(soup)
    if len(rows) != 2:
        problems.append(f"archived wish has {len(rows)} rows, want both of Bob's promises")
    expected = {
        earlier: (1, list(range(1, 3)), False),
        later: (2, list(range(1, 4)), True),
    }
    for reservation_id, (quantity, ceiling, purchased) in expected.items():
        row = row_for_reservation(soup, reservation_id)
        if row is None:
            problems.append(f"missing row for reservation {reservation_id}")
            continue
        rendered = visible_text(row)
        raw = str(row)
        if not has_number(rendered, quantity):
            problems.append(f"row {reservation_id} missing quantity {quantity}")
        if _ARCHIVED_WISH not in rendered:
            problems.append(f"row {reservation_id} missing «{_ARCHIVED_WISH}»")
        if _ARCHIVED_LIST in rendered:
            problems.append(f"active list row {reservation_id} says the list is archived")
        problems.extend(link_gaps(row, seeded.wishlist_id, item_id))
        problems.extend(
            action_gaps(
                row,
                "Изменить",
                "hx-patch",
                promise_url(seeded.wishlist_id, item_id, reservation_id),
                json_enc=True,
            )
        )
        problems.extend(
            action_gaps(
                row,
                "Отменить бронь",
                "hx-post",
                promise_url(seeded.wishlist_id, item_id, reservation_id, "/cancel"),
                json_enc=False,
            )
        )
        if purchased:
            problems.extend(
                action_gaps(
                    row,
                    "Вернуть в бронь",
                    "hx-post",
                    promise_url(seeded.wishlist_id, item_id, reservation_id, "/undo-purchase"),
                    json_enc=False,
                )
            )
            if find_labeled(row, _BOUGHT) is not None:
                problems.append("purchased row still offers «Куплено»")
        else:
            problems.extend(
                action_gaps(
                    row,
                    _BOUGHT,
                    "hx-post",
                    promise_url(seeded.wishlist_id, item_id, reservation_id, "/purchase"),
                    json_enc=False,
                )
            )
            if find_labeled(row, "Вернуть в бронь") is not None:
                problems.append("intended row offers «Вернуть в бронь»")
        if option_values(row) != ceiling:
            problems.append(f"row {reservation_id} options {option_values(row)}, want {ceiling}")
        if "Cara" in rendered or has_reservation_path(raw, cara_id):
            problems.append("row names the other gifter")
        other = later if reservation_id == earlier else earlier
        if has_reservation_path(raw, other):
            problems.append(f"row {reservation_id} was rewritten to {other}")
    assert problems == [], problems


def test_archived_list_refuses_the_four(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """An archived list keeps the row, hides the four actions, and the writes stay 409."""
    client, sessions, app = test_app
    seeded = seed_list(
        app.state.domain_service,
        title="Closed",
        wishes=(WishDraft("Книга", quantity=1),),
    )
    bob = auth_header(sessions, _FRIEND_ID, "Bob")
    owner = auth_header(sessions, _OWNER_ID, "Alice")
    item_id = seeded.item_ids[0]
    reservation_id = create_promise(client, seeded.wishlist_id, item_id, bob, quantity=1)
    archive_list(client, seeded.wishlist_id, owner)
    before = reservation_rows(app, item_id)
    prefix = reservations_url(seeded.wishlist_id, item_id)
    calls = (
        ("patch", f"{prefix}/{reservation_id}", {"quantity": 1}),
        ("post", f"{prefix}/{reservation_id}/cancel", None),
        ("post", f"{prefix}/{reservation_id}/purchase", None),
        ("post", f"{prefix}/{reservation_id}/undo-purchase", None),
    )
    detail = ""
    for method, url, payload in calls:
        kwargs: dict[str, object] = {"headers": bob}
        if payload is not None:
            kwargs["json"] = payload
        response = getattr(client, method)(url, **kwargs)
        assert response.status_code == 409, response.text
        detail = str(response.json().get("detail", ""))
        assert detail
        assert "Bob" not in detail
    assert reservation_rows(app, item_id) == before

    page = client.get(_CABINET_URL, headers=bob)
    problems, soup = page_or_problem(page, _CABINET_URL)
    if soup is not None:
        text = visible_text(soup)
        if _ARCHIVED_LIST not in text:
            problems.append("archived list row missing «Вишлист в архиве»")
        if "Книга" not in text or _BOOKED not in text:
            problems.append("archived list dropped the occupying promise")
        for label in _ACTION_LABELS:
            if label in text:
                problems.append(f"archived list still shows «{label}»")
        if detail in page.text:
            problems.append("cabinet echoes the 409 detail")
        if find_labeled(soup, _WISH_LINK) is None:
            problems.append("archived list row missing «К желанию»")
    assert problems == [], problems


def test_deleted_list_leaves_the_cabinet(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """Deleting a list cancels its promises, drops the group, and drops the wish from the badge."""
    client, sessions, app = test_app
    kept = seed_list(
        app.state.domain_service,
        title="Оставить",
        wishes=(WishDraft("Лампа", quantity=1),),
    )
    dropped = seed_list(
        app.state.domain_service,
        title="Удалить",
        wishes=(WishDraft("Ваза", quantity=1),),
    )
    bob = auth_header(sessions, _FRIEND_ID, "Bob")
    create_promise(client, kept.wishlist_id, kept.item_ids[0], bob)
    removed = create_promise(client, dropped.wishlist_id, dropped.item_ids[0], bob)
    delete_list(app.state.domain_service, dropped.wishlist_id)
    assert reservation_rows(app, dropped.item_ids[0]) == [
        (removed, 1, "cancelled", _FRIEND_ID),
    ]
    assert reservation_rows(app, kept.item_ids[0])[0][2] == "active"

    card = client.get(_CARD_URL, headers=bob)
    page = client.get(_CABINET_URL, headers=bob)
    problems, card_soup = page_or_problem(card, _CARD_URL)
    page_problems, page_soup = page_or_problem(page, _CABINET_URL)
    problems.extend(page_problems)
    if card_soup is not None:
        badge = card_soup.select_one(".reservations-badge")
        badge_text = visible_text(badge) if isinstance(badge, Tag) else ""
        if badge_text != "1":
            problems.append(f"badge after delete is {badge_text!r}, want 1")
    if page_soup is not None:
        text = visible_text(page_soup)
        groups = groups_of(page_soup)
        if "Лампа" not in text or "Оставить" not in text:
            problems.append("cabinet dropped the promise on the list that remains")
        if "Ваза" in text or "Удалить" in text or has_reservation_path(str(page_soup), removed):
            problems.append("deleted list still appears in the cabinet")
        if len(groups) != 1:
            problems.append(f"groups after delete: {len(groups)}")
    assert problems == [], problems


def test_success_refresh_hides_the_other_gifter(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """A successful refresh replaces the list and does not reveal the other gifter."""
    client, sessions, app = test_app
    seeded = seed_list(
        app.state.domain_service,
        title="Refresh",
        wishes=(WishDraft("Наушники", quantity=15),),
    )
    bob = auth_header(sessions, _FRIEND_ID, "Bob")
    cara = auth_header(sessions, _OTHER_ID, "Cara")
    owner = auth_header(sessions, _OWNER_ID, "Alice")
    item_id = seeded.item_ids[0]
    bob_id = create_promise(client, seeded.wishlist_id, item_id, bob, quantity=6)
    cara_id = create_promise(client, seeded.wishlist_id, item_id, cara, quantity=8)
    archive_item(client, seeded.wishlist_id, item_id, owner)

    page = client.get(_CABINET_URL, headers=bob)
    partial = client.get(_LIST_URL, headers=bob)
    problems, soup = page_or_problem(page, _CABINET_URL)
    list_problems, list_soup = page_or_problem(partial, _LIST_URL)
    problems.extend(list_problems)
    if soup is not None:
        row = row_with_quantity(soup, 6)
        if row is None:
            problems.append("cabinet missing Bob's archived row")
        else:
            controls = [
                element
                for element in row.find_all(True)
                if element.get("hx-post") or element.get("hx-patch")
            ]
            if not controls:
                problems.append("archived row has no promise control")
            elif any(attr_in_row(element, row, "hx-swap") != "none" for element in controls):
                problems.append("archived row does not use hx-swap none")
    if list_soup is not None:
        text = visible_text(list_soup)
        raw = str(list_soup)
        if not has_number(text, 6) or _BOOKED not in text:
            problems.append("list partial missing Bob's quantity or status")
        if "Cara" in text or "Cara" in raw or has_reservation_path(raw, cara_id):
            problems.append("list partial reveals the other gifter")
        if has_number(text, 8):
            problems.append("list partial shows the other gifter's quantity")
    problems.extend(refresh_script_problems(base_script(client, seeded.wishlist_id, owner)))
    assert bob_id != cara_id
    assert problems == [], problems


def test_busy_response_does_not_look_saved(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTP 503 leaves the stored promise and does not paint a new cabinet status."""
    client, sessions, app = test_app
    seeded = seed_list(
        app.state.domain_service,
        title="Busy",
        wishes=(WishDraft("Плед", quantity=1),),
    )
    bob = auth_header(sessions, _FRIEND_ID, "Bob")
    owner = auth_header(sessions, _OWNER_ID, "Alice")
    item_id = seeded.item_ids[0]
    reservation_id = create_promise(client, seeded.wishlist_id, item_id, bob, quantity=1)
    before = reservation_rows(app, item_id)

    async def busy(*_args: object, **_kwargs: object) -> None:
        raise InventoryBusyError()

    monkeypatch.setattr(app.state.wishlist_store, "execute_wish", busy)
    response = client.post(
        promise_url(seeded.wishlist_id, item_id, reservation_id, "/cancel"),
        headers=bob,
    )
    monkeypatch.undo()
    assert response.status_code == 503, response.text
    detail = str(response.json().get("detail", ""))
    assert "Bob" not in detail
    assert "Alice" not in detail
    assert reservation_rows(app, item_id) == before

    page = client.get(_CABINET_URL, headers=bob)
    problems, soup = page_or_problem(page, _CABINET_URL)
    if soup is not None:
        text = visible_text(soup)
        if _BOOKED not in text or "Плед" not in text:
            problems.append("busy cabinet no longer shows the unchanged promise")
        if detail and detail in page.text:
            problems.append("cabinet shows the 503 detail")
        root, missing = cabinet_node(soup)
        problems.extend(missing)
        if root is not None and "reservations-cabinet" not in str(soup):
            problems.append("busy response replaced the cabinet")
    problems.extend(refresh_script_problems(base_script(client, seeded.wishlist_id, owner)))
    assert problems == [], problems
