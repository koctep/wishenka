"""Failing repro tests for WISHENKA-89: SSR templates, sharing/UI routes, and date i18n."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from wishenka.auth.models import AuthenticatedUser, TelegramUser
from wishenka.auth.session import SessionTokenService
from wishenka.config import Settings
from wishenka.i18n.locale import SupportedLocale
from wishenka.web.app import create_app
from wishenka.wishlists.service import WishlistService

pytestmark = pytest.mark.timeout(30)

_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
_OWNER_ID = 101
_GIFTER_ID = 202
_COAUTHOR_ID = 303
_EVENT_DT = datetime(2026, 12, 25, 12, 0, tzinfo=UTC)


def _assert_no_cyrillic(text: str, *, context: str) -> None:
    """Assert that rendered English UI text contains no untranslated Cyrillic characters."""
    matches = _CYRILLIC_RE.findall(text)
    if matches:
        snippet_match = re.search(r".{0,30}[А-Яа-яЁё].{0,30}", text)
        snippet = snippet_match.group(0) if snippet_match else ""
        raise AssertionError(f"Unexpected Cyrillic in English SSR output ({context}): {snippet!r}")


def _make_user(telegram_id: int, first_name: str) -> AuthenticatedUser:
    return AuthenticatedUser(
        telegram_id=telegram_id,
        first_name=first_name,
        auth_method="session_token",
    )


def _bearer(sessions: SessionTokenService, user_id: int, name: str = "User") -> dict[str, str]:
    return {"Authorization": f"Bearer {sessions.create_token(user_id, name)}"}


@pytest.fixture
def ssr_env(tmp_path: Path) -> Iterator[tuple[TestClient, SessionTokenService, FastAPI]]:
    """Create an isolated FastAPI TestClient with SQLite storage and no live Telegram."""
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'ssr_i18n_repro.db'}",
        secret_key="ssr-i18n-repro-secret",
    )
    app = create_app(settings)
    sessions = SessionTokenService(settings.secret_key)
    with TestClient(app) as client:
        yield client, sessions, app


async def _seed_user_locale(
    app: FastAPI, telegram_id: int, first_name: str, locale: SupportedLocale
) -> None:
    await app.state.user_store.upsert_user(
        TelegramUser(id=telegram_id, first_name=first_name, language_code=locale)
    )
    await app.state.user_store.set_locale(telegram_id, locale)


def _seed_wishlist_with_items(
    app: FastAPI,
    *,
    owner_locale: SupportedLocale = "en",
    gifter_locale: SupportedLocale = "en",
    coauthor_locale: SupportedLocale = "en",
) -> dict[str, object]:
    """Seed users, a collaborative wishlist with event_date, items, reservation, and receipt."""
    service: WishlistService = app.state.domain_service
    owner = _make_user(_OWNER_ID, "Alice")
    gifter = _make_user(_GIFTER_ID, "Bob")
    coauthor = _make_user(_COAUTHOR_ID, "Charlie")

    async def _run() -> dict[str, object]:
        await _seed_user_locale(app, _OWNER_ID, "Alice", owner_locale)
        await _seed_user_locale(app, _GIFTER_ID, "Bob", gifter_locale)
        await _seed_user_locale(app, _COAUTHOR_ID, "Charlie", coauthor_locale)

        wl = await service.create_wishlist(
            owner=owner,
            title="Birthday Wishlist",
            event_date=_EVENT_DT,
        )
        item1 = await service.add_wish_item(
            wishlist_id=wl.id,
            actor=owner,
            title="Wireless Headphones",
            quantity=2,
        )
        item2 = await service.add_wish_item(
            wishlist_id=wl.id,
            actor=owner,
            title="Board Game",
            quantity=1,
        )
        archived_item = await service.add_wish_item(
            wishlist_id=wl.id,
            actor=owner,
            title="Old Mug",
            quantity=1,
        )
        await service.archive_wish_item(wishlist_id=wl.id, item_id=archived_item.id, actor=owner)
        await service.create_reservation(item_id=item1.id, user=gifter, quantity=1)
        await service.record_item_fulfillment(
            item2.id,
            owner,
            1,
            wishlist_id=wl.id,
        )
        return {
            "wishlist_id": wl.id,
            "public_token": str(wl.public_token),
            "invite_token": str(wl.invite_token),
            "item1_id": item1.id,
            "item2_id": item2.id,
            "archived_id": archived_item.id,
            "coauthor": coauthor,
        }

    return asyncio.run(_run())


def test_format_date_locale_aware() -> None:
    """format_date renders Dec 25, 2026 for 'en' and 25.12.2026 for 'ru'."""
    from wishenka.i18n import format_date

    assert format_date(_EVENT_DT, "en") == "Dec 25, 2026"
    assert format_date(date(2026, 12, 25), "en") == "Dec 25, 2026"
    assert format_date(_EVENT_DT, "ru") == "25.12.2026"
    assert format_date(None, "en") == ""


def test_public_share_page_en_and_ru_localization(
    ssr_env: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """Public share view respects ?lang=en, Accept-Language, and locale-aware date formatting."""
    client, _sessions, app = ssr_env
    seeded = _seed_wishlist_with_items(app)
    public_token = seeded["public_token"]

    resp_query = client.get(f"/share/{public_token}?lang=en")
    assert resp_query.status_code == 200
    assert '<html lang="en"' in resp_query.text
    assert "Dec 25, 2026" in resp_query.text
    _assert_no_cyrillic(resp_query.text, context="GET /share/{token}?lang=en")

    resp_accept_en = client.get(
        f"/share/{public_token}",
        headers={"Accept-Language": "en-US,en;q=0.9"},
    )
    assert resp_accept_en.status_code == 200
    assert '<html lang="en"' in resp_accept_en.text
    _assert_no_cyrillic(resp_accept_en.text, context="GET /share/{token} Accept-Language: en")

    resp_accept_ru = client.get(
        f"/share/{public_token}",
        headers={"Accept-Language": "ru-RU,ru;q=0.9"},
    )
    assert resp_accept_ru.status_code == 200
    assert '<html lang="ru"' in resp_accept_ru.text
    assert "25.12.2026" in resp_accept_ru.text


def test_invite_preview_and_join_en_localization(
    ssr_env: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """Invite preview (valid and invalid) and join banner render in English without Cyrillic."""
    client, sessions, app = ssr_env
    seeded = _seed_wishlist_with_items(app, coauthor_locale="en")
    invite_token = seeded["invite_token"]

    valid_resp = client.get(f"/invite/{invite_token}?lang=en")
    assert valid_resp.status_code == 200
    assert '<html lang="en"' in valid_resp.text
    _assert_no_cyrillic(valid_resp.text, context="GET /invite/{token}?lang=en")

    invalid_resp = client.get("/invite/nonexistent-invite-token?lang=en")
    assert invalid_resp.status_code in (200, 404)
    _assert_no_cyrillic(invalid_resp.text, context="GET /invite/invalid?lang=en")

    join_resp = client.post(
        f"/invite/{invite_token}/join",
        headers=_bearer(sessions, _COAUTHOR_ID, "Charlie"),
    )
    assert join_resp.status_code == 200
    _assert_no_cyrillic(join_resp.text, context="POST /invite/{token}/join")


def test_authenticated_wishlist_detail_and_sharing_partials_en(
    ssr_env: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """Wishlist detail, share modal, member list, item card, and regenerate render in English."""
    client, sessions, app = ssr_env
    seeded = _seed_wishlist_with_items(app, owner_locale="en")
    wl_id = seeded["wishlist_id"]
    item1_id = seeded["item1_id"]
    headers = _bearer(sessions, _OWNER_ID, "Alice")

    detail = client.get(f"/web/wishlists/{wl_id}", headers=headers)
    assert detail.status_code == 200
    assert '<html lang="en"' in detail.text
    assert "Dec 25, 2026" in detail.text
    assert "data-i18n-prepare-error=" in detail.text
    assert "data-i18n-busy-error=" in detail.text
    _assert_no_cyrillic(detail.text, context="GET /web/wishlists/{id}")

    for label, method, url in [
        ("share-modal", "GET", f"/wishlists/{wl_id}/share-modal"),
        ("members-partial", "GET", f"/wishlists/{wl_id}/members/partial"),
        ("item-card", "GET", f"/wishlists/{wl_id}/items/{item1_id}/card"),
        ("invite-regenerate", "POST", f"/wishlists/{wl_id}/invite/regenerate"),
    ]:
        resp = client.request(method, url, headers=headers | {"HX-Request": "true"})
        assert resp.status_code == 200, f"{label} returned {resp.status_code}"
        _assert_no_cyrillic(resp.text, context=label)


def test_items_ui_modals_and_validation_errors_en(
    ssr_env: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """Item UI modals and validation error responses render in English for locale='en'."""
    client, sessions, app = ssr_env
    seeded = _seed_wishlist_with_items(app, owner_locale="en")
    wl_id = seeded["wishlist_id"]
    item1_id = seeded["item1_id"]
    headers = _bearer(sessions, _OWNER_ID, "Alice") | {"HX-Request": "true"}

    for label, url in [
        ("items-new", f"/web/wishlists/{wl_id}/items/new"),
        ("items-edit", f"/web/wishlists/{wl_id}/items/{item1_id}/edit"),
        ("items-archive-confirm", f"/web/wishlists/{wl_id}/items/{item1_id}/archive-confirm"),
    ]:
        resp = client.get(url, headers=headers)
        assert resp.status_code == 200, f"{label} returned {resp.status_code}"
        _assert_no_cyrillic(resp.text, context=label)

    empty_quick = client.post(
        f"/web/wishlists/{wl_id}/items/quick",
        data={"raw_input": "   "},
        headers=headers,
    )
    assert empty_quick.status_code == 400
    _assert_no_cyrillic(empty_quick.text, context="POST /items/quick empty")

    below_reserved = client.post(
        f"/web/wishlists/{wl_id}/items/{item1_id}/edit",
        data={"title": "Wireless Headphones", "quantity": "0"},
        headers=headers,
    )
    assert below_reserved.status_code == 409
    _assert_no_cyrillic(below_reserved.text, context="POST /items/{id}/edit quantity=0")


def test_receipts_ui_modal_refusal_and_oob_notice_en(
    ssr_env: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """Receipt modal, refusal messages, and OOB confirmation notice render in English."""
    client, sessions, app = ssr_env
    seeded = _seed_wishlist_with_items(app, owner_locale="en")
    wl_id = seeded["wishlist_id"]
    item1_id = seeded["item1_id"]
    headers = _bearer(sessions, _OWNER_ID, "Alice") | {"HX-Request": "true"}

    modal_resp = client.get(
        f"/web/wishlists/{wl_id}/items/{item1_id}/receipt",
        headers=headers,
    )
    assert modal_resp.status_code == 200
    _assert_no_cyrillic(modal_resp.text, context="GET /items/{id}/receipt")

    invalid_resp = client.post(
        f"/web/wishlists/{wl_id}/items/{item1_id}/receipt",
        data={"quantity": "0"},
        headers=headers,
    )
    assert invalid_resp.status_code == 400
    _assert_no_cyrillic(invalid_resp.text, context="POST /items/{id}/receipt invalid quantity")

    valid_resp = client.post(
        f"/web/wishlists/{wl_id}/items/{item1_id}/receipt",
        data={"quantity": "1"},
        headers=headers,
    )
    assert valid_resp.status_code == 201
    _assert_no_cyrillic(valid_resp.text, context="POST /items/{id}/receipt valid")


def test_reservations_ui_cabinet_card_and_list_en(
    ssr_env: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """Reservations cabinet, home card, and list fragment render in English with localized date."""
    client, sessions, app = ssr_env
    _seed_wishlist_with_items(app, gifter_locale="en")
    headers = _bearer(sessions, _GIFTER_ID, "Bob")

    cabinet = client.get("/web/reservations", headers=headers)
    assert cabinet.status_code == 200
    assert '<html lang="en"' in cabinet.text
    assert "Dec 25, 2026" in cabinet.text
    _assert_no_cyrillic(cabinet.text, context="GET /web/reservations")

    card = client.get("/web/reservations/card", headers=headers | {"HX-Request": "true"})
    assert card.status_code == 200
    _assert_no_cyrillic(card.text, context="GET /web/reservations/card")

    lst = client.get("/web/reservations/list", headers=headers | {"HX-Request": "true"})
    assert lst.status_code == 200
    assert "Dec 25, 2026" in lst.text
    _assert_no_cyrillic(lst.text, context="GET /web/reservations/list")
