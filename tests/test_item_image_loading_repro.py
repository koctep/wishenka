"""Red failing repro tests for WISHENKA-107.

Verifies:
1. SSR/HTMX templates (``item_card.html``, ``item_preview_card.html``,
   ``item_edit_modal.html``) render ``loading="lazy"``,
   ``referrerpolicy="no-referrer"``, ``data-img-fallback``, and a paired
   hidden ``.item-thumbnail-placeholder`` without inline ``on*`` handlers.
2. ``image_url=None`` behavior remains unchanged in all three contexts.
3. ``wishenka/web/static/app.js`` registers a capture-phase ``error`` listener
   that hides broken ``img[data-img-fallback]`` elements and reveals the
   sibling ``.item-thumbnail-placeholder``.
4. ``wishenka/web/static/miniapp.css`` defines ``[hidden] { display: none; }``
   and size classes for thumbnails and placeholders.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from bs4 import BeautifulSoup, Tag

from tests.receipt_support import OWNER, AppEnv, app_env
from tests.receipt_ui_support import domain, hx, on_attributes, parse, run
from wishenka.items.models import InputType
from wishenka.items.schemas import ItemPreviewDTO
from wishenka.items.service import ItemPreviewService

pytestmark = pytest.mark.timeout(30)

SAMPLE_IMAGE_URL = "https://cdn.example.com/images/kettle.jpg"
PREVIEW_IMAGE_URL = "https://cdn.example.com/images/preview.jpg"
REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def env(tmp_path: Path) -> Iterator[AppEnv]:
    """Open create_app on an isolated SQLite file with bearer sessions."""
    with app_env(tmp_path) as opened:
        yield opened


def _seed_items(env: AppEnv) -> tuple[int, str, int, int]:
    """Create a wishlist with one imaged item and one imageless item."""
    _client, _sessions, app = env
    service = domain(app)

    async def _seed() -> tuple[int, str, int, int]:
        wl = await service.create_wishlist(owner=OWNER, title="Birthday")
        with_img = await service.add_wish_item(
            wishlist_id=wl.id,
            actor=OWNER,
            title="Kettle With Photo",
            image_url=SAMPLE_IMAGE_URL,
        )
        without_img = await service.add_wish_item(
            wishlist_id=wl.id,
            actor=OWNER,
            title="Mug Without Photo",
            image_url=None,
        )
        return wl.id, str(wl.public_token), with_img.id, without_img.id

    return run(_seed())


def _assert_no_inline_handlers(soup: BeautifulSoup) -> None:
    handlers = on_attributes(soup)
    assert handlers == [], f"expected no inline on* attributes, found {handlers}"


def _assert_fallback_image_pair(
    container: Tag,
    *,
    expected_src: str,
    expect_large: bool = False,
) -> None:
    """Assert that ``<img>`` and its hidden sibling placeholder satisfy the contract."""
    img = container.select_one("img")
    assert img is not None, "expected <img> inside thumbnail container"
    assert img.get("src") == expected_src
    assert img.get("loading") == "lazy"
    assert img.get("referrerpolicy") == "no-referrer"
    assert img.has_attr("data-img-fallback")

    img_classes = img.get_attribute_list("class")
    assert "item-thumbnail" in img_classes
    if expect_large:
        assert "item-thumbnail--lg" in img_classes

    parent = img.parent
    assert parent is not None
    placeholder = parent.select_one(".item-thumbnail-placeholder")
    assert placeholder is not None, "expected sibling .item-thumbnail-placeholder"
    assert placeholder.has_attr("hidden"), "fallback placeholder must start hidden"
    assert placeholder.get("aria-hidden") == "true"
    if expect_large:
        ph_classes = placeholder.get_attribute_list("class")
        assert "item-thumbnail-placeholder--lg" in ph_classes


@pytest.mark.parametrize("kind", ["owner", "share"])
def test_item_card_renders_lazy_no_referrer_and_hidden_placeholder(env: AppEnv, kind: str) -> None:
    """``item_card.html`` renders lazy/no-referrer attributes and hidden fallback placeholder."""
    client, sessions, _app = env
    wishlist_id, token, with_img_id, without_img_id = _seed_items(env)

    if kind == "owner":
        response = client.get(f"/web/wishlists/{wishlist_id}", headers=hx(sessions))
    else:
        response = client.get(f"/share/{token}")
    assert response.status_code == 200, response.text

    soup = parse(response.text)
    _assert_no_inline_handlers(soup)

    card_with_img = soup.select_one(f"#item-card-{with_img_id}")
    assert card_with_img is not None
    _assert_fallback_image_pair(card_with_img, expected_src=SAMPLE_IMAGE_URL)

    card_without_img = soup.select_one(f"#item-card-{without_img_id}")
    assert card_without_img is not None
    assert card_without_img.select_one("img") is None
    visible_ph = card_without_img.select_one(".item-thumbnail-placeholder")
    assert visible_ph is not None
    assert not visible_ph.has_attr("hidden")


def test_item_preview_card_renders_lazy_no_referrer_and_hidden_placeholder(
    env: AppEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``item_preview_card.html`` adds lazy/no-referrer and hidden fallback when image exists."""
    client, sessions, _app = env
    wishlist_id, _token, _with_img_id, _without_img_id = _seed_items(env)

    async def mock_fetch_preview(
        self: ItemPreviewService,
        raw_input: str,
        http_client: httpx.AsyncClient | None = None,
    ) -> ItemPreviewDTO:
        return ItemPreviewDTO(
            input_type=InputType.EXPLICIT_URL,
            url="https://example.com/gift",
            title="Gift Preview",
            description="Nice gift",
            image_url=PREVIEW_IMAGE_URL,
            price=1500,
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
    _assert_no_inline_handlers(soup)
    card = soup.select_one("#item-preview-card")
    assert card is not None
    _assert_fallback_image_pair(card, expected_src=PREVIEW_IMAGE_URL)


def test_item_preview_card_without_image_renders_no_placeholder(
    env: AppEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``item_preview_card.html`` omits thumbnail and placeholder when ``image_url`` is None."""
    client, sessions, _app = env
    wishlist_id, _token, _with_img_id, _without_img_id = _seed_items(env)

    async def mock_fetch_preview(
        self: ItemPreviewService,
        raw_input: str,
        http_client: httpx.AsyncClient | None = None,
    ) -> ItemPreviewDTO:
        return ItemPreviewDTO(
            input_type=InputType.EXPLICIT_URL,
            url="https://example.com/gift",
            title="Gift Preview",
            description=None,
            image_url=None,
            price=None,
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
    _assert_no_inline_handlers(soup)
    assert soup.select_one("img") is None
    assert soup.select_one(".item-thumbnail-placeholder") is None


def test_item_edit_modal_renders_lazy_no_referrer_and_hidden_placeholder(
    env: AppEnv,
) -> None:
    """``item_edit_modal.html`` renders large thumbnail with fallback and preserves None case."""
    client, sessions, _app = env
    wishlist_id, _token, with_img_id, without_img_id = _seed_items(env)

    resp_with_img = client.get(
        f"/web/wishlists/{wishlist_id}/items/{with_img_id}/edit",
        headers=hx(sessions),
    )
    assert resp_with_img.status_code == 200, resp_with_img.text
    soup_with_img = parse(resp_with_img.text)
    _assert_no_inline_handlers(soup_with_img)
    _assert_fallback_image_pair(
        soup_with_img,
        expected_src=SAMPLE_IMAGE_URL,
        expect_large=True,
    )

    resp_without_img = client.get(
        f"/web/wishlists/{wishlist_id}/items/{without_img_id}/edit",
        headers=hx(sessions),
    )
    assert resp_without_img.status_code == 200, resp_without_img.text
    soup_without_img = parse(resp_without_img.text)
    _assert_no_inline_handlers(soup_without_img)
    assert soup_without_img.select_one("img") is None
    assert soup_without_img.select_one(".item-thumbnail-placeholder") is None


def test_app_js_handles_image_error_in_capture_phase() -> None:
    """``app.js`` registers a capture-phase error listener that swaps img for placeholder."""
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is unavailable")

    script = r"""
const fs = require('fs');
const vm = require('vm');

const captureListeners = {};
global.window = {
  addEventListener: () => {},
};
global.document = {
  addEventListener: (name, fn, useCapture) => {
    if (useCapture === true) {
      captureListeners[name] = fn;
    }
  },
  querySelector: () => null,
  getElementById: () => null,
  body: {
    getAttribute: () => null,
    hasAttribute: () => false,
  },
};

vm.runInThisContext(fs.readFileSync(process.argv[1], 'utf8'));

const handler = captureListeners.error;
if (typeof handler !== 'function') {
  console.error('Missing capture-phase document error listener');
  process.exit(1);
}

function makeImg({ fallback = true, hasPlaceholder = true } = {}) {
  const placeholder = hasPlaceholder ? { hidden: true } : null;
  return {
    tagName: 'IMG',
    hidden: false,
    hasAttribute: (attr) => fallback && attr === 'data-img-fallback',
    matches: (sel) => fallback && sel === 'img[data-img-fallback]',
    parentElement: {
      querySelector: (sel) => (sel === '.item-thumbnail-placeholder' ? placeholder : null),
    },
    _placeholder: placeholder,
  };
}

// 1. Standard fallback swap
const img = makeImg({ fallback: true, hasPlaceholder: true });
handler({ target: img });
if (img.hidden !== true || img._placeholder.hidden !== false) {
  console.error('Expected img.hidden=true and placeholder.hidden=false');
  process.exit(2);
}

// 2. Idempotent on repeated error events
handler({ target: img });
if (img.hidden !== true || img._placeholder.hidden !== false) {
  console.error('Expected idempotent swap on repeated error');
  process.exit(3);
}

// 3. Ignores images without data-img-fallback
const plainImg = makeImg({ fallback: false, hasPlaceholder: true });
handler({ target: plainImg });
if (plainImg.hidden !== false || plainImg._placeholder.hidden !== true) {
  console.error('Expected non-fallback img to be ignored');
  process.exit(4);
}

// 4. Ignores non-IMG targets
const divTarget = {
  tagName: 'DIV',
  hidden: false,
  hasAttribute: () => true,
  matches: () => false,
  parentElement: null,
};
handler({ target: divTarget });
if (divTarget.hidden !== false) {
  console.error('Expected non-IMG target to be ignored');
  process.exit(5);
}

// 5. Safe when sibling placeholder is missing
const orphanImg = makeImg({ fallback: true, hasPlaceholder: false });
handler({ target: orphanImg });
if (orphanImg.hidden !== true) {
  console.error('Expected orphan img to be hidden safely');
  process.exit(6);
}
"""
    app_js = REPO_ROOT / "wishenka/web/static/app.js"
    result = subprocess.run(
        [node, "-e", script, str(app_js)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_miniapp_css_defines_hidden_and_thumbnail_sizes(env: AppEnv) -> None:
    """``miniapp.css`` must hide ``[hidden]`` thumbnails/placeholders and define ``--lg``."""
    client, _sessions, _app = env
    response = client.get("/static/miniapp.css")
    assert response.status_code == 200
    css = response.text

    assert ".item-thumbnail[hidden]" in css
    assert ".item-thumbnail-placeholder[hidden]" in css
    assert ".item-thumbnail {" in css or ".item-thumbnail{" in css
    assert ".item-thumbnail--lg" in css
    assert ".item-thumbnail-placeholder--lg" in css
