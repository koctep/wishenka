"""Red tests for the «Подаренные» section of the wishlist page (WISHENKA-24, plan T-4).

Covers U-12 to U-16 and DoD 5, 6: who sees the section, hidden when empty, archived lists,
separation from the archive, entry content and order, approximate dates, no controls, fail-soft
read. Today the page has no section markup at all.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from bs4 import Tag

from tests.receipt_support import (
    GIFTER,
    GIFTER_ID,
    OTHER_GIFTER,
    OWNER,
    OWNER_ID,
    STRANGER_ID,
    AppEnv,
    app_env,
    db_path_of,
    make_user,
    sql_exec,
    sql_rows,
)
from tests.receipt_ui_support import (
    BOOKING_WORDS,
    GIFTED_FAILURE,
    GIVER_NAMES,
    XSS_TITLE,
    Wish,
    domain,
    hx,
    on_attributes,
    parse,
    promise,
    receive,
    run,
    seed_list,
    text_of,
)
from wishenka.auth.models import TelegramUser
from wishenka.wishlists.exceptions import PermissionDeniedError
from wishenka.wishlists.models import WishlistRole
from wishenka.wishlists.service import WishlistService

pytestmark = pytest.mark.timeout(30)

ADMIN = make_user(606, "Boris")
MEMBER = make_user(707, "Mila")


@pytest.fixture
def env(tmp_path: Path) -> Iterator[AppEnv]:
    """Open create_app on an isolated SQLite file with bearer sessions."""
    with app_env(tmp_path) as opened:
        yield opened


def _page(env: AppEnv, wishlist_id: int, user_id: int | None = OWNER_ID) -> Any:
    client, sessions, _app = env
    headers = {} if user_id is None else hx(sessions, user_id)
    return client.get(f"/web/wishlists/{wishlist_id}", headers=headers)


def _section(env: AppEnv, wishlist_id: int, user_id: int | None = OWNER_ID) -> Tag:
    response = _page(env, wishlist_id, user_id)
    assert response.status_code == 200, response.text
    section = parse(response.text).select_one("#gifted-items-section")
    assert section is not None, f"user {user_id}: no #gifted-items-section on the page"
    return section


def _team(app: Any) -> tuple[int, list[int]]:
    """List with admin and member; wishes: partly received, fully received, untouched."""
    wishlist_id, ids = seed_list(
        app,
        [Wish("Kettle", 5), Wish("Mug", 1), Wish("Lamp", 2)],
        members=(),
    )
    service = domain(app)
    for user in (ADMIN, MEMBER):
        run(
            app.state.user_store.upsert_user(
                TelegramUser(
                    id=user.telegram_id,
                    first_name=user.first_name,
                    language_code="ru",
                )
            )
        )
    run(service.add_member(wishlist_id, OWNER, ADMIN.telegram_id, WishlistRole.ADMIN))
    run(service.add_member(wishlist_id, OWNER, MEMBER.telegram_id, WishlistRole.MEMBER))
    receive(app, ids[0], 2)
    receive(app, ids[1], 1)
    return wishlist_id, ids


def test_section_shown_to_owner_admin_member_with_count(env: AppEnv) -> None:
    """U-12, DoD 5: authors see «Подаренные (N)» with one entry per received wish."""
    _client, _sessions, app = env
    wishlist_id, ids = _team(app)

    for user_id in (OWNER_ID, ADMIN.telegram_id, MEMBER.telegram_id):
        section = _section(env, wishlist_id, user_id)
        summary = section.select_one("details.gifted-items-details summary")
        assert summary is not None, f"user {user_id}: no details/summary"
        assert text_of(summary) == "Подаренные (2)"
        entries = section.select("li.gifted-item")
        assert [e.get("id") for e in entries] == [f"gifted-item-{ids[1]}", f"gifted-item-{ids[0]}"]


def test_section_hidden_when_empty(env: AppEnv) -> None:
    """U-12, UA-2: with nothing received the container exists but renders nothing visible."""
    _client, _sessions, app = env
    wishlist_id, _ids = seed_list(app, [Wish("Kettle", 5)])

    section = _section(env, wishlist_id)

    assert section.select_one("details") is None
    assert text_of(section) == ""
    assert "Подаренные" not in text_of(parse(_page(env, wishlist_id).text))


def test_section_absent_for_giver_anonymous_share_and_stranger(env: AppEnv) -> None:
    """U-12, U-21, DoD 6: no section and no count for non-members (owner page is the control)."""
    client, _sessions, app = env
    wishlist_id, _ids = _team(app)
    promise(app, _ids[2], GIFTER, 1)
    token = str(run(domain(app).get_wishlist_by_id(wishlist_id)).public_token)
    assert _section(env, wishlist_id).select_one("li.gifted-item") is not None, "owner control"

    pages = {
        "giver": _page(env, wishlist_id, GIFTER_ID),
        "stranger": _page(env, wishlist_id, STRANGER_ID),
        "anonymous": _page(env, wishlist_id, None),
        "share": client.get(f"/share/{token}"),
    }

    for label, response in pages.items():
        assert response.status_code == 200, label
        soup = parse(response.text)
        assert soup.select_one("#gifted-items-section") is None, label
        visible = text_of(soup)
        assert "Подаренные" not in visible, label
        assert "Получено:" not in visible, label


def test_section_visible_on_archived_list_without_edit_controls(env: AppEnv) -> None:
    """U-12, DoD 5: members of an archived list still see the section; no edit controls."""
    _client, _sessions, app = env
    wishlist_id, ids = _team(app)
    run(domain(app).archive_wishlist(wishlist_id, OWNER))

    response = _page(env, wishlist_id, OWNER_ID)

    assert response.status_code == 200
    soup = parse(response.text)
    section = soup.select_one("#gifted-items-section")
    assert section is not None, "no section on an archived list"
    assert text_of(section.select_one("summary")) == "Подаренные (2)"
    assert section.select_one(f"#gifted-item-{ids[0]}") is not None
    for selector in (".btn-restore-item", ".btn-receipt-item", ".item-actions", "#quick-add-bar"):
        assert soup.select_one(selector) is None, selector


def test_section_separate_from_archive(env: AppEnv) -> None:
    """U-16: a partly received archived wish is in both lists; a full one only in gifted."""
    _client, _sessions, app = env
    wishlist_id, (partly, full) = seed_list(app, [Wish("Kettle", 5), Wish("Mug", 3)])
    receive(app, partly, 2)
    receive(app, full, 3)
    run(domain(app).archive_wish_item(wishlist_id, partly, OWNER))

    soup = parse(_page(env, wishlist_id).text)

    archive = soup.select_one("#archived-items-section")
    assert archive is not None
    assert archive.select_one(f"#archived-item-{partly}") is not None
    assert archive.select_one(f"#archived-item-{full}") is None
    remaining = archive.select_one(f"#archived-item-{partly} .archived-item-remaining")
    assert remaining is not None and text_of(remaining) == "Осталось 3"
    gifted = soup.select_one("#gifted-items-section")
    assert gifted is not None
    assert gifted.select_one(f"#gifted-item-{partly}") is not None
    assert gifted.select_one(f"#gifted-item-{full}") is not None
    assert "Подаренные" not in text_of(archive)
    assert soup.select_one(f"#items-list #item-card-{full}") is None


def _set_receipt_days(app: Any, item_id: int, days: list[str]) -> None:
    """Pin the stored receipt timestamps of one wish, oldest first."""
    db = db_path_of(app)

    rows = sql_rows(db, "SELECT id FROM wl_receipts WHERE wish_item_id = ? ORDER BY id", (item_id,))
    assert len(rows) == len(days)
    for row, day in zip(rows, days, strict=True):
        sql_exec(
            db,
            "UPDATE wl_receipts SET received_at = ? WHERE id = ?",
            (f"{day}T10:00:00+00:00", row["id"]),
        )


def test_entry_content_and_order(env: AppEnv) -> None:
    """U-13: title, price, recipient, counters, dated acts; newest receipt first; escaped title."""
    _client, _sessions, app = env
    wishlist_id, (alpha, other) = seed_list(
        app,
        [
            Wish("Alpha", 5, price=1500, recipient_name="Маша"),
            Wish(XSS_TITLE, 1),
        ],
    )
    receive(app, alpha, 2)
    receive(app, alpha, 1)
    receive(app, other, 1)
    _set_receipt_days(app, alpha, ["2026-03-10", "2026-03-12"])
    _set_receipt_days(app, other, ["2026-03-14"])

    response = _page(env, wishlist_id)

    section = parse(response.text).select_one("#gifted-items-section")
    assert section is not None
    entries = section.select("li.gifted-item")
    assert [e.get("id") for e in entries] == [f"gifted-item-{other}", f"gifted-item-{alpha}"]
    first, second = entries
    assert XSS_TITLE in text_of(first)
    assert "Получено: 1 из 1" in text_of(first)
    assert [text_of(s) for s in first.select("ul.gifted-receipts .gifted-act-text")] == [
        "14.03.2026 — 1 шт."
    ]
    body = text_of(second)
    for expected in ("Alpha", "1500 RUB", "Для: Маша", "Получено: 3 из 5"):
        assert expected in body, body
    assert [text_of(s) for s in second.select("ul.gifted-receipts .gifted-act-text")] == [
        "10.03.2026 — 2 шт.",
        "12.03.2026 — 1 шт.",
    ]
    assert section.find("script") is None
    assert XSS_TITLE not in str(section)
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in str(section)


def test_approximate_date_marked(env: AppEnv) -> None:
    """U-13, UA-4: a back-filled receipt is shown as an approximate date."""
    _client, _sessions, app = env
    wishlist_id, (item_id, *_rest) = seed_list(app, [Wish("Kettle", 5)])
    receive(app, item_id, 2)
    _set_receipt_days(app, item_id, ["2026-03-15"])
    sql_exec(db_path_of(app), "UPDATE wl_receipts SET is_approximate = 1")

    section = _section(env, wishlist_id)

    acts = [text_of(s) for s in section.select("ul.gifted-receipts .gifted-act-text")]
    assert acts == ["≈ 15.03.2026 (дата примерная) — 2 шт."]


def test_section_has_no_controls_or_booking_data(env: AppEnv) -> None:
    """U-14, U-20: only receipt edit/cancel buttons; no booking/item-edit controls or leaks."""
    _client, _sessions, app = env
    wishlist_id, (item_id, *_rest) = seed_list(app, [Wish("Kettle", 50)])
    promise(app, item_id, GIFTER, 37)
    promise(app, item_id, OTHER_GIFTER, 11)
    receive(app, item_id, 49)

    section = _section(env, wishlist_id)

    assert section.select_one("li.gifted-item") is not None
    assert section.select("form, a, input, select, textarea") == []
    buttons = section.select("button")
    assert len(buttons) == 2
    assert {tuple(btn.get("class") or []) for btn in buttons} == {
        ("btn-receipt-edit",),
        ("btn-receipt-cancel",),
    }
    hx_attrs = [
        (tag.name, attr)
        for tag in [section, *section.find_all(True)]
        for attr in tag.attrs
        if attr.lower().startswith("hx-") and attr.lower() != "hx-swap-oob"
    ]
    assert all(
        tag_name == "button" and attr.lower() in {"hx-get", "hx-target", "hx-swap"}
        for tag_name, attr in hx_attrs
    )
    assert on_attributes(parse(str(section))) == []
    text = text_of(section)
    lowered = text.lower()
    for word in BOOKING_WORDS:
        assert word not in lowered, word
    for name in GIVER_NAMES:
        assert name not in text
    for number in ("37", "202", "303"):
        assert number not in text.split(), number


def test_read_failure_shows_text(env: AppEnv, monkeypatch: pytest.MonkeyPatch) -> None:
    """U-15: a failing gifted read gives the fixed text; the page and its active list stay."""
    _client, _sessions, app = env
    wishlist_id, (item_id, *_rest) = seed_list(app, [Wish("Kettle", 5), Wish("Mug", 2)])
    receive(app, item_id, 2)

    async def failing(*_args: object, **_kwargs: object) -> None:
        raise PermissionDeniedError("gifted read failed")

    from wishenka.wishlists.repo_ops import RepoWishlistOps

    monkeypatch.setattr(WishlistService, "list_gifted_items", failing)
    monkeypatch.setattr(RepoWishlistOps, "list_gifted_items", failing)

    response = _page(env, wishlist_id)

    assert response.status_code == 200, response.text
    soup = parse(response.text)
    assert len(soup.select("#items-list .item-card")) == 2
    section = soup.select_one("#gifted-items-section")
    assert section is not None, "no gifted container when the read fails"
    assert text_of(section) == GIFTED_FAILURE
    assert section.select_one("li.gifted-item") is None
