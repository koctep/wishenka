"""Failing repro tests for WISHENKA-160 (older edit & archive modals).

Covers:
1. SSR & route contracts: inline archive target in ``item_edit_modal.html``,
   ``HX-Retarget``/``HX-Reswap`` headers on 409/503/400 edit responses, and
   HTML OOB error responses on 409/404 archive failures.
2. Chromium CDP browser tests: modal backdrop/sheet CSS layering above
   ``#quick-add-bar`` on mobile viewports, and visible error rendering for
   409/503 edit errors and 409 archived-wishlist archive errors.

STEP 3: red on current production code; expected to pass after Step 4.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from bs4 import BeautifulSoup
from fastapi import FastAPI

from tests.browser_cdp import CdpPage
from tests.browser_helpers import Seeded, js_str, record_receipt, settle
from tests.conftest import BrowserServer
from tests.receipt_support import (
    OWNER,
    OWNER_ID,
    AppEnv,
    app_env,
    bearer,
    seed_wish,
)
from wishenka.wishlists.exceptions import InventoryBusyError
from wishenka.wishlists.store import WishlistStore

pytestmark = pytest.mark.timeout(45)

SeedFactory = Callable[..., Seeded]
PageFactory = Callable[..., CdpPage]

MOBILE_VIEWPORT = (390, 844)


@pytest.fixture
def test_app(tmp_path: Path) -> Iterator[AppEnv]:
    """Provide an isolated application with a real SQLite store."""
    with app_env(tmp_path) as env:
        yield env


def _make_busy(monkeypatch: pytest.MonkeyPatch, app: FastAPI) -> None:
    async def busy(*_args: object, **_kwargs: object) -> None:
        raise InventoryBusyError()

    monkeypatch.setattr(app.state.wishlist_store, "execute_wish", busy)


def _open_modal(page: CdpPage, url: str, modal_selector: str) -> None:
    page.evaluate(
        f"void window.htmx.ajax('GET', {js_str(url)},"
        " {target: '#item-modal-container', swap: 'innerHTML'})"
    )
    settle(page)
    page.wait_for(
        f"modal {modal_selector} opened",
        f"!!document.querySelector({js_str(modal_selector)})",
    )


def _hit_test_button(page: CdpPage, button_selector: str) -> dict[str, Any]:
    """Scroll button into view inside its modal and check ``document.elementFromPoint``."""
    return cast(
        dict[str, Any],
        page.evaluate(
            f"""(() => {{
            const btn = document.querySelector({js_str(button_selector)});
            if (!btn) return {{ found: false }};
            btn.scrollIntoView({{ block: 'center' }});
            const r = btn.getBoundingClientRect();
            const cx = r.left + r.width / 2;
            const cy = r.top + r.height / 2;
            const hit = document.elementFromPoint(cx, cy);
            return {{
                found: true,
                inViewport: (
                    cy >= 0 && cy <= window.innerHeight && cx >= 0 && cx <= window.innerWidth
                ),
                hitsButton: hit === btn || btn.contains(hit),
                hitId: hit ? hit.id : null,
                hitClass: hit ? hit.className : null,
            }};
        }})()"""
        ),
    )


def _backdrop_layer_info(page: CdpPage, modal_selector: str) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        page.evaluate(
            f"""(() => {{
            const backdrop = document.querySelector({js_str(modal_selector)});
            const quickAdd = document.getElementById('quick-add-bar');
            const bStyle = getComputedStyle(backdrop);
            const qStyle = getComputedStyle(quickAdd);
            const bz = Number.parseInt(bStyle.zIndex, 10);
            const qz = Number.parseInt(qStyle.zIndex, 10);
            return {{
                position: bStyle.position,
                backdropZ: Number.isNaN(bz) ? 0 : bz,
                quickAddZ: Number.isNaN(qz) ? 0 : qz,
            }};
        }})()"""
        ),
    )


# --- SSR & Route Contract Repro Tests -------------------------------------------------------


def test_edit_modal_inline_archive_has_modal_container_target(test_app: AppEnv) -> None:
    """Inline archive button in item_edit_modal.html must target #item-modal-container."""
    client, sessions, app = test_app
    wishlist_id, item_id = asyncio.run(
        seed_wish(app.state.domain_service, quantity=2, title="Lamp")
    )

    response = client.get(
        f"/web/wishlists/{wishlist_id}/items/{item_id}/edit",
        headers=bearer(sessions, OWNER_ID),
    )

    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    btn = soup.select_one(".btn-archive-item")
    assert btn is not None
    assert btn.get("hx-target") == "#item-modal-container"
    assert btn.get("hx-swap") == "none"


def test_submit_edit_item_409_and_503_include_hx_retarget_headers(
    test_app: AppEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    """409 Reduction Lock and 503 Busy edit responses must retarget #item-modal-container."""
    client, sessions, app = test_app

    async def seed_received() -> tuple[int, int]:
        wl_id, it_id = await seed_wish(app.state.domain_service, quantity=3, title="Camera")
        await app.state.domain_service.record_item_fulfillment(it_id, OWNER, 2)
        return wl_id, it_id

    wishlist_id, item_id = asyncio.run(seed_received())
    url = f"/web/wishlists/{wishlist_id}/items/{item_id}/edit"

    resp_409 = client.post(
        url,
        data={"title": "Camera", "quantity": "1"},
        headers=bearer(sessions, OWNER_ID),
    )
    assert resp_409.status_code == 409
    assert resp_409.headers.get("HX-Retarget") == "#item-modal-container"
    assert resp_409.headers.get("HX-Reswap") == "innerHTML"

    _make_busy(monkeypatch, app)
    resp_503 = client.post(
        url,
        data={"title": "Camera", "quantity": "3"},
        headers=bearer(sessions, OWNER_ID),
    )
    assert resp_503.status_code == 503
    assert resp_503.headers.get("HX-Retarget") == "#item-modal-container"
    assert resp_503.headers.get("HX-Reswap") == "innerHTML"


def test_submit_edit_item_400_empty_title_returns_html_retargeted_to_modal(
    test_app: AppEnv,
) -> None:
    """400 validation errors on edit must return modal HTML retargeted to #item-modal-container."""
    client, sessions, app = test_app
    wishlist_id, item_id = asyncio.run(seed_wish(app.state.domain_service, quantity=1, title="Mug"))

    response = client.post(
        f"/web/wishlists/{wishlist_id}/items/{item_id}/edit",
        data={"title": "   ", "quantity": "1"},
        headers=bearer(sessions, OWNER_ID),
    )

    assert response.status_code == 400
    assert "text/html" in response.headers.get("content-type", "")
    assert response.headers.get("HX-Retarget") == "#item-modal-container"
    assert response.headers.get("HX-Reswap") == "innerHTML"
    assert 'role="alert"' in response.text


def test_archive_item_ui_archived_wishlist_and_missing_item_return_oob_html(
    test_app: AppEnv,
) -> None:
    """409 archived-wishlist and 404 missing-item archive errors must return OOB HTML notices."""
    client, sessions, app = test_app
    wishlist_id, item_id = asyncio.run(
        seed_wish(app.state.domain_service, quantity=1, title="Book")
    )

    resp_missing = client.post(
        f"/web/wishlists/{wishlist_id}/items/999999/archive",
        data={"warn_on_delete_reserved": "false"},
        headers=bearer(sessions, OWNER_ID),
    )
    assert resp_missing.status_code == 404
    assert "text/html" in resp_missing.headers.get("content-type", "")
    soup_missing = BeautifulSoup(resp_missing.text, "html.parser")
    assert soup_missing.select_one("#list-notice[hx-swap-oob]") is not None
    assert soup_missing.select_one("#item-modal-container[hx-swap-oob]") is not None

    asyncio.run(app.state.domain_service.archive_wishlist(wishlist_id, OWNER))
    resp_archived = client.post(
        f"/web/wishlists/{wishlist_id}/items/{item_id}/archive",
        data={"warn_on_delete_reserved": "false"},
        headers=bearer(sessions, OWNER_ID),
    )
    assert resp_archived.status_code == 409
    assert "text/html" in resp_archived.headers.get("content-type", "")
    soup_archived = BeautifulSoup(resp_archived.text, "html.parser")
    assert soup_archived.select_one("#list-notice[hx-swap-oob]") is not None
    assert soup_archived.select_one("#item-modal-container[hx-swap-oob]") is not None


# --- Chromium CDP Browser Repro Tests -------------------------------------------------------


@pytest.mark.browser
def test_archive_modal_layers_above_quick_add_bar_and_button_is_clickable(
    seed_wishlist: SeedFactory, wishlist_page: PageFactory
) -> None:
    """Archive modal must render as a fixed overlay above #quick-add-bar with clickable confirm."""
    seeded = seed_wishlist(["Teapot"], quantities=[1])
    page = wishlist_page(seeded, accept_language="ru", viewport=MOBILE_VIEWPORT)
    item = seeded.item_ids[0]

    _open_modal(
        page,
        f"/web/wishlists/{seeded.wishlist_id}/items/{item}/archive-confirm",
        "#item-archive-modal",
    )

    layer = _backdrop_layer_info(page, "#item-archive-modal")
    assert layer["position"] == "fixed", f"Expected fixed modal backdrop, got: {layer}"
    assert int(layer["backdropZ"]) > int(layer["quickAddZ"]), (
        f"Modal z-index must exceed quick-add bar z-index: {layer}"
    )

    hit = _hit_test_button(page, "#item-archive-modal .btn-confirm-archive")
    assert hit.get("found") and hit.get("inViewport"), f"Confirm button not reachable: {hit}"
    assert hit.get("hitsButton") is True, (
        f"Confirm archive button is obscured by another element: {hit}"
    )


@pytest.mark.browser
def test_edit_modal_layers_above_quick_add_bar_and_controls_unobstructed(
    seed_wishlist: SeedFactory, wishlist_page: PageFactory
) -> None:
    """Edit modal must render as a fixed overlay above #quick-add-bar with unobstructed buttons."""
    seeded = seed_wishlist(["Headphones"], quantities=[2])
    page = wishlist_page(seeded, accept_language="ru", viewport=MOBILE_VIEWPORT)
    item = seeded.item_ids[0]

    _open_modal(
        page,
        f"/web/wishlists/{seeded.wishlist_id}/items/{item}/edit",
        "#item-edit-sheet",
    )

    layer = _backdrop_layer_info(page, "#item-edit-sheet")
    assert layer["position"] == "fixed", f"Expected fixed modal backdrop, got: {layer}"
    assert int(layer["backdropZ"]) > int(layer["quickAddZ"]), (
        f"Modal z-index must exceed quick-add bar z-index: {layer}"
    )

    for selector in ("#item-edit-sheet .btn-save", "#item-edit-sheet .btn-archive-item"):
        hit = _hit_test_button(page, selector)
        assert hit.get("found") and hit.get("inViewport"), f"Button {selector} not reachable: {hit}"
        assert hit.get("hitsButton") is True, f"Button {selector} is obscured: {hit}"


@pytest.mark.browser
def test_edit_modal_409_and_503_render_alert_inside_modal_container(
    wishlist_server: BrowserServer,
    seed_wishlist: SeedFactory,
    wishlist_page: PageFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """409 Reduction Lock and 503 Busy edit responses must render [role=alert] in the modal."""
    seeded = seed_wishlist(["Mixer"], quantities=[3])
    item = seeded.item_ids[0]
    record_receipt(wishlist_server.base_url, seeded, item, 2)

    page = wishlist_page(seeded, accept_language="ru", viewport=MOBILE_VIEWPORT)
    edit_url = f"/web/wishlists/{seeded.wishlist_id}/items/{item}/edit"
    _open_modal(page, edit_url, "#item-edit-sheet")

    # 409 Reduction Lock
    page.evaluate(
        f"void window.htmx.ajax('POST', {js_str(edit_url)},"
        " {target: '#item-modal-container', swap: 'innerHTML',"
        " values: {title: 'Mixer', quantity: '1'}})"
    )
    settle(page)
    alert_409 = page.evaluate(
        "(() => { const a = document.querySelector('#item-modal-container [role=\"alert\"]');"
        " return a ? a.textContent.trim() : ''; })()"
    )
    assert alert_409, "Expected visible [role=alert] error inside #item-modal-container on 409"
    assert page.evaluate(f"!!document.querySelector('#item-card-{item}')")

    # 503 InventoryBusyError
    async def busy(*_args: object, **_kwargs: object) -> None:
        raise InventoryBusyError()

    monkeypatch.setattr(WishlistStore, "execute_wish", busy)
    page.evaluate(
        f"void window.htmx.ajax('POST', {js_str(edit_url)},"
        " {target: '#item-modal-container', swap: 'innerHTML',"
        " values: {title: 'Mixer', quantity: '3'}})"
    )
    settle(page)
    alert_503 = page.evaluate(
        "(() => { const a = document.querySelector('#item-modal-container [role=\"alert\"]');"
        " return a ? a.textContent.trim() : ''; })()"
    )
    assert alert_503, "Expected visible [role=alert] error inside #item-modal-container on 503"


@pytest.mark.browser
def test_archive_modal_409_archived_wishlist_shows_list_notice_and_closes_modal(
    wishlist_server: BrowserServer,
    seed_wishlist: SeedFactory,
    wishlist_page: PageFactory,
) -> None:
    """Confirming archive on an archived wishlist (409) must show #list-notice and close modal."""
    seeded = seed_wishlist(["Scarf"], quantities=[1])
    item = seeded.item_ids[0]
    page = wishlist_page(seeded, accept_language="ru", viewport=MOBILE_VIEWPORT)

    _open_modal(
        page,
        f"/web/wishlists/{seeded.wishlist_id}/items/{item}/archive-confirm",
        "#item-archive-modal",
    )

    resp = httpx.post(
        f"{wishlist_server.base_url}/api/wishlists/{seeded.wishlist_id}/archive",
        headers={"Authorization": f"Bearer {seeded.owner_token}"},
        timeout=10,
    )
    assert resp.status_code == 200, f"archive wishlist setup failed: {resp.status_code} {resp.text}"

    archive_url = f"/web/wishlists/{seeded.wishlist_id}/items/{item}/archive"
    page.evaluate(
        f"void window.htmx.ajax('POST', {js_str(archive_url)},"
        " {target: '#items-list', swap: 'none', values: {warn_on_delete_reserved: 'false'}})"
    )
    settle(page)

    notice_text = page.evaluate(
        "(() => { const n = document.getElementById('list-notice');"
        " return n ? n.textContent.trim() : ''; })()"
    )
    modal_html = page.evaluate("document.getElementById('item-modal-container').innerHTML.trim()")
    assert notice_text, "Expected non-empty #list-notice feedback on 409 archived wishlist"
    assert modal_html == "", f"Expected #item-modal-container to close, got: {modal_html!r}"
