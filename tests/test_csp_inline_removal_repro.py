"""Red failing repro tests for WISHENKA-140 (remove remaining inline JS and onclick handlers)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from bs4 import BeautifulSoup

from tests.receipt_support import AppEnv, app_env
from tests.receipt_ui_support import Wish, domain, hx, on_attributes, parse, run, seed_list
from wishenka.items.models import InputType
from wishenka.items.schemas import ItemPreviewDTO
from wishenka.items.service import ItemPreviewService

pytestmark = pytest.mark.timeout(30)


@pytest.fixture
def env(tmp_path: Path) -> Iterator[AppEnv]:
    """Open create_app on an isolated SQLite file with bearer sessions."""
    with app_env(tmp_path) as opened:
        yield opened


def _assert_no_inline_scripts_or_handlers(soup: BeautifulSoup) -> None:
    inline_scripts = [tag.get_text() for tag in soup.find_all("script") if not tag.get("src")]
    assert inline_scripts == [], f"expected no inline <script> tags, found {len(inline_scripts)}"
    handlers = on_attributes(soup)
    assert handlers == [], f"expected no inline on* attributes, found {handlers}"


def test_app_script_is_served_as_javascript(env: AppEnv) -> None:
    """``/static/app.js`` and ``/static/settings.js`` must be served with a JS Content-Type."""
    client, _sessions, _app = env
    for path in ("/static/app.js", "/static/settings.js"):
        response = client.get(path)
        assert response.status_code == 200, f"{path} returned {response.status_code}"
        assert "javascript" in response.headers["content-type"]


@pytest.mark.parametrize("kind", ["owner", "share"])
def test_pages_have_no_inline_scripts_and_load_app_script_deferred(env: AppEnv, kind: str) -> None:
    """Owner and share pages have zero inline scripts/handlers and load deferred app.js."""
    client, sessions, app = env
    wishlist_id, _items = seed_list(app, [Wish("Kettle", 2)])
    if kind == "owner":
        response = client.get(f"/web/wishlists/{wishlist_id}", headers=hx(sessions))
    else:
        token = str(run(domain(app).get_wishlist_by_id(wishlist_id)).public_token)
        response = client.get(f"/share/{token}")
    assert response.status_code == 200, response.text

    soup = parse(response.text)
    _assert_no_inline_scripts_or_handlers(soup)

    tags = soup.find_all("script", src=True)
    sources = [str(tag["src"]) for tag in tags]
    assert "/static/app.js" in sources, f"/static/app.js not referenced; scripts: {sources}"

    app_idx = sources.index("/static/app.js")
    assert tags[app_idx].has_attr("defer")
    htmx_idx = next(i for i, src in enumerate(sources) if "htmx.org" in src)
    assert app_idx > htmx_idx
    assert app_idx < sources.index("/static/wishlist.js")
    assert app_idx < sources.index("/static/receipt.js")


def test_item_edit_modal_has_no_inline_handlers_and_uses_data_attributes(env: AppEnv) -> None:
    """``item_edit_modal.html`` uses declarative data-* attributes instead of onclick."""
    client, sessions, app = env
    wishlist_id, (item_id, *_rest) = seed_list(app, [Wish("Kettle", 2)])
    response = client.get(
        f"/web/wishlists/{wishlist_id}/items/{item_id}/edit",
        headers=hx(sessions),
    )
    assert response.status_code == 200, response.text

    soup = parse(response.text)
    _assert_no_inline_scripts_or_handlers(soup)

    close_btn = soup.select_one(".btn-modal-close")
    cancel_btn = soup.select_one(".btn-cancel")
    dec_btn = soup.select_one(".btn-decrement")
    inc_btn = soup.select_one(".btn-increment")

    assert close_btn is not None
    assert close_btn.get("data-clear-target") == "#item-modal-container"
    assert cancel_btn is not None
    assert cancel_btn.get("data-clear-target") == "#item-modal-container"
    assert dec_btn is not None
    assert dec_btn.get("data-qty-step") == "-1"
    assert dec_btn.get("data-qty-target") == "#item-quantity-input"
    assert inc_btn is not None
    assert inc_btn.get("data-qty-step") == "1"
    assert inc_btn.get("data-qty-target") == "#item-quantity-input"


def test_item_archive_modal_has_no_inline_handlers_and_uses_data_attributes(env: AppEnv) -> None:
    """``item_archive_modal.html`` uses data-clear-target instead of onclick."""
    client, sessions, app = env
    wishlist_id, (item_id, *_rest) = seed_list(app, [Wish("Kettle", 2)])
    response = client.get(
        f"/web/wishlists/{wishlist_id}/items/{item_id}/archive-confirm",
        headers=hx(sessions),
    )
    assert response.status_code == 200, response.text

    soup = parse(response.text)
    _assert_no_inline_scripts_or_handlers(soup)

    cancel_btn = soup.select_one(".btn-modal-close")
    assert cancel_btn is not None
    assert cancel_btn.get("data-clear-target") == "#item-modal-container"


def test_item_preview_card_has_no_inline_handlers_and_uses_data_attributes(
    env: AppEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``item_preview_card.html`` uses data-clear-target instead of onclick."""
    client, sessions, app = env
    wishlist_id, _items = seed_list(app, [Wish("Kettle", 2)])

    async def mock_fetch_preview(
        self: ItemPreviewService,
        raw_input: str,
        client: httpx.AsyncClient | None = None,
    ) -> ItemPreviewDTO:
        return ItemPreviewDTO(
            input_type=InputType.EXPLICIT_URL,
            url="https://example.com/gift",
            title="Gift",
            description="Nice gift",
            image_url=None,
            price=100,
            currency="RUB",
            store_name="Example",
            is_fallback=False,
        )

    monkeypatch.setattr(ItemPreviewService, "fetch_preview", mock_fetch_preview)

    response = client.post(
        f"/web/wishlists/{wishlist_id}/items/preview",
        data={"raw_input": "https://example.com/gift"},
        headers=hx(sessions),
    )
    assert response.status_code == 200, response.text

    soup = parse(response.text)
    _assert_no_inline_scripts_or_handlers(soup)

    dismiss_btn = soup.select_one(".btn-preview-dismiss")
    assert dismiss_btn is not None
    assert dismiss_btn.get("data-clear-target") == "#quick-add-preview-target"


def test_settings_page_has_no_inline_scripts_and_loads_settings_script_deferred(
    env: AppEnv,
) -> None:
    """``/settings`` has zero inline scripts/handlers and loads deferred ``settings.js``."""
    client, sessions, app = env
    seed_list(app, [Wish("Kettle", 2)])
    response = client.get("/settings", headers=hx(sessions))
    assert response.status_code == 200, response.text

    soup = parse(response.text)
    _assert_no_inline_scripts_or_handlers(soup)

    tags = soup.find_all("script", src=True)
    sources = [str(tag["src"]) for tag in tags]
    assert "/static/settings.js" in sources, (
        f"/static/settings.js not referenced; scripts: {sources}"
    )
    settings_idx = sources.index("/static/settings.js")
    assert tags[settings_idx].has_attr("defer")
    assert settings_idx > sources.index("/static/app.js")
