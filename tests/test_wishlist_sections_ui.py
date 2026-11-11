"""Automated failing repro tests for WISHENKA-9: Wishlist sections and viewing history.

Asserts:
- Home section grouping: My Wishlists, Collaborating, Favorites.
- Role badge rendering and badge precedence.
- Favorites toggle endpoint & list favorites endpoint.
- Viewing history recording, bounds (20), deduplication, and clear history endpoint.
- Surprise invariant: zero leak of reservations in favorites and history responses.
- Browser Mini App DOM regression for section grouping, role badges, and history navigation.
"""

import asyncio
import json
import shutil
import socket
import subprocess
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.testclient import TestClient
from websockets.sync.client import ClientConnection, connect

from wishenka.auth.models import AuthenticatedUser
from wishenka.auth.session import SessionTokenService
from wishenka.config import Settings
from wishenka.web.app import create_app
from wishenka.wishlists.models import WishlistRole
from wishenka.wishlists.service import WishlistService

pytestmark = pytest.mark.timeout(60)

ORIGIN = "http://testserver"


def bearer(sessions: SessionTokenService, user_id: int) -> dict[str, str]:
    """Authenticate as a test user via Bearer token."""
    return {"Authorization": f"Bearer {sessions.create_token(user_id, 'User')}"}


@pytest.fixture
def test_app(tmp_path: Path) -> Iterator[tuple[TestClient, SessionTokenService, FastAPI]]:
    """Initialize test client and session token service with isolated database."""
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'sections.db'}",
        secret_key="sections-test-secret",
    )
    app = create_app(settings)
    sessions = SessionTokenService(settings.secret_key)
    with TestClient(app) as client:
        yield client, sessions, app


# ============================================================================
# 1. Favorites API Lifecycle & Invariant Validation
# ============================================================================


def test_favorites_endpoints_lifecycle_and_own_wishlist_guard(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """Favorites lifecycle: toggle, list, delete, and prevent favoriting own list."""
    client, sessions, app = test_app
    service: WishlistService = app.state.domain_service

    alice = AuthenticatedUser(telegram_id=101, first_name="Alice", auth_method="session_token")
    bob = AuthenticatedUser(telegram_id=202, first_name="Bob", auth_method="session_token")

    async def seed() -> tuple[int, int]:
        wl_alice = await service.create_wishlist(alice, title="Alice's Wishlist")
        wl_bob = await service.create_wishlist(bob, title="Bob's Wishlist")
        return wl_alice.id, wl_bob.id

    alice_wl_id, _ = asyncio.run(seed())

    alice_headers = bearer(sessions, 101)
    bob_headers = bearer(sessions, 202)

    # 1. User cannot favorite own wishlist -> 400 Bad Request
    own_fav = client.post(f"/api/favorites/{alice_wl_id}", headers=alice_headers)
    assert own_fav.status_code == 400, f"Expected 400 for own wishlist, got {own_fav.status_code}"
    assert "own" in own_fav.json().get("detail", "").lower()

    # 2. Bob favorites Alice's wishlist -> 200 OK
    fav_resp = client.post(f"/api/favorites/{alice_wl_id}", headers=bob_headers)
    assert fav_resp.status_code == 200, f"Expected 200, got {fav_resp.status_code}"
    fav_data = fav_resp.json()
    assert fav_data.get("status") == "favorited"
    assert fav_data.get("wishlist_id") == alice_wl_id

    # 3. Bob lists favorites -> Alice's wishlist is included with is_favorite=True
    list_fav = client.get("/api/favorites", headers=bob_headers)
    assert list_fav.status_code == 200, f"Expected 200, got {list_fav.status_code}"
    favorites = list_fav.json()
    assert isinstance(favorites, list)
    fav_ids = [f["id"] for f in favorites]
    assert alice_wl_id in fav_ids
    alice_fav_item = next(f for f in favorites if f["id"] == alice_wl_id)
    assert alice_fav_item.get("is_favorite") is True
    assert alice_fav_item.get("role") == "favorite"

    # 4. Bob unfavorites Alice's wishlist -> 200 OK
    del_fav = client.delete(f"/api/favorites/{alice_wl_id}", headers=bob_headers)
    assert del_fav.status_code == 200, f"Expected 200, got {del_fav.status_code}"
    assert del_fav.json().get("status") == "removed"

    # 5. Bob lists favorites again -> empty
    after_del = client.get("/api/favorites", headers=bob_headers)
    assert after_del.status_code == 200
    assert not any(f["id"] == alice_wl_id for f in after_del.json())


# ============================================================================
# 2. Viewing History Recording, Bounds (20), and Deduplication
# ============================================================================


def test_viewing_history_recording_ordering_deduplication_and_bounds(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """Viewing history records views, reverse-chronological order, deduplicates, and caps at 20."""
    client, sessions, app = test_app
    service: WishlistService = app.state.domain_service

    owner = AuthenticatedUser(telegram_id=101, first_name="Owner", auth_method="session_token")
    viewer_headers = bearer(sessions, 202)

    # Seed 25 wishlists
    async def seed_wishlists() -> list[int]:
        ids = []
        for i in range(25):
            wl = await service.create_wishlist(owner, title=f"List {i + 1}")
            ids.append(wl.id)
        return ids

    wl_ids = asyncio.run(seed_wishlists())

    # Viewer opens List 1, List 2, List 3 via POST /api/history/{id}
    for wl_id in [wl_ids[0], wl_ids[1], wl_ids[2]]:
        rec = client.post(f"/api/history/{wl_id}", headers=viewer_headers)
        assert rec.status_code == 200, f"Failed recording view for {wl_id}: {rec.status_code}"

    # Verify initial history order: [List 3, List 2, List 1]
    hist = client.get("/api/history", headers=viewer_headers)
    assert hist.status_code == 200, f"Expected 200, got {hist.status_code}"
    history_entries = hist.json()
    assert len(history_entries) == 3
    assert [e["id"] for e in history_entries] == [wl_ids[2], wl_ids[1], wl_ids[0]]

    # Deduplication test: re-view List 1 -> must move to top without duplicating
    rec_again = client.post(f"/api/history/{wl_ids[0]}", headers=viewer_headers)
    assert rec_again.status_code == 200

    hist_after_review = client.get("/api/history", headers=viewer_headers).json()
    assert len(hist_after_review) == 3, "Deduplication failed: duplicate entry created"
    assert [e["id"] for e in hist_after_review] == [wl_ids[0], wl_ids[2], wl_ids[1]]

    # Cap test: view remaining 22 lists (wl_ids[3] through wl_ids[24])
    for wl_id in wl_ids[3:]:
        client.post(f"/api/history/{wl_id}", headers=viewer_headers)

    # Assert bounded to 20 entries
    bounded_hist = client.get("/api/history", headers=viewer_headers).json()
    assert len(bounded_hist) == 20, f"History not bounded to 20 items, got {len(bounded_hist)}"
    assert bounded_hist[0]["id"] == wl_ids[24]  # Most recent is at the top
    assert wl_ids[1] not in [e["id"] for e in bounded_hist]  # Oldest entries evicted


def test_viewing_history_clear_endpoint(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """DELETE /api/history clears all entries for current user."""
    client, sessions, app = test_app
    service: WishlistService = app.state.domain_service

    owner = AuthenticatedUser(telegram_id=101, first_name="Owner", auth_method="session_token")
    viewer_headers = bearer(sessions, 202)

    async def seed() -> int:
        wl = await service.create_wishlist(owner, title="History Clear Test List")
        return wl.id

    wl_id = asyncio.run(seed())

    # Record view
    client.post(f"/api/history/{wl_id}", headers=viewer_headers)
    assert len(client.get("/api/history", headers=viewer_headers).json()) > 0

    # Clear history
    clear_resp = client.delete("/api/history", headers=viewer_headers)
    assert clear_resp.status_code == 200
    assert clear_resp.json().get("status") == "cleared"

    # Verify empty
    after_clear = client.get("/api/history", headers=viewer_headers)
    assert after_clear.status_code == 200
    assert after_clear.json() == []


# ============================================================================
# 3. Surprise Invariant in Favorites and History Projections
# ============================================================================


def test_surprise_invariant_in_favorites_and_history_projections(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """Neither /api/favorites nor /api/history exposes reservation details or buyer identities."""
    client, sessions, app = test_app
    service: WishlistService = app.state.domain_service

    recipient = AuthenticatedUser(telegram_id=101, first_name="Alice", auth_method="session_token")
    gifter = AuthenticatedUser(telegram_id=202, first_name="Bob", auth_method="session_token")
    recipient_headers = bearer(sessions, 101)

    async def seed_with_reservation() -> None:
        wl = await service.create_wishlist(recipient, title="Secret Surprise Wishlist")
        item = await service.add_wish_item(wl.id, actor=recipient, title="Surprise Gift")
        await service.create_reservation(item_id=item.id, user=gifter, quantity=1)

    asyncio.run(seed_with_reservation())

    # Gifter creates another wishlist for Alice to favorite & view
    async def seed_gifter_wl() -> int:
        wl2 = await service.create_wishlist(gifter, title="Gifter Wishlist")
        item2 = await service.add_wish_item(wl2.id, actor=gifter, title="Gifter Item")
        # Alice reserves item in Gifter's list
        await service.create_reservation(item_id=item2.id, user=recipient, quantity=1)
        return wl2.id

    wl2_id = asyncio.run(seed_gifter_wl())

    # Alice favorites wl2 and views wl2
    client.post(f"/api/favorites/{wl2_id}", headers=recipient_headers)
    client.post(f"/api/history/{wl2_id}", headers=recipient_headers)

    fav_res = client.get("/api/favorites", headers=recipient_headers)
    assert fav_res.status_code == 200, f"Expected 200, got {fav_res.status_code}"
    fav_lists = fav_res.json()
    assert len(fav_lists) >= 1

    hist_res = client.get("/api/history", headers=recipient_headers)
    assert hist_res.status_code == 200, f"Expected 200, got {hist_res.status_code}"
    hist_lists = hist_res.json()
    assert len(hist_lists) >= 1

    # Invariant: Neither favorites nor history may leak reservation data
    forbidden_keys = {
        "reservations",
        "reserved_quantity",
        "available_quantity",
        "is_fully_reserved",
        "giver",
        "comments",
    }
    for item_data in fav_lists + hist_lists:
        assert forbidden_keys.isdisjoint(item_data.keys()), (
            f"Reservation leak detected in summary: {item_data.keys() & forbidden_keys}"
        )
        if "items" in item_data and item_data["items"]:
            for wish_item in item_data["items"]:
                assert forbidden_keys.isdisjoint(wish_item.keys()), (
                    f"Reservation leak detected in item: {wish_item.keys() & forbidden_keys}"
                )


# ============================================================================
# 4. Role Badge Rendering & Badge Precedence
# ============================================================================


def test_home_sections_api_and_role_badge_precedence(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """Operational collaboration role takes precedence when user both collaborates and favorites."""
    client, sessions, app = test_app
    service: WishlistService = app.state.domain_service

    alice = AuthenticatedUser(telegram_id=101, first_name="Alice", auth_method="session_token")
    bob = AuthenticatedUser(telegram_id=202, first_name="Bob", auth_method="session_token")
    alice_headers = bearer(sessions, 101)

    async def seed() -> tuple[int, int, int]:
        # 1. Alice is owner
        wl_owner = await service.create_wishlist(alice, title="Owned by Alice")
        # 2. Bob is owner, Alice is member
        wl_collab = await service.create_wishlist(bob, title="Collab Wishlist")
        await service.add_member(wl_collab.id, bob, 101, WishlistRole.MEMBER)
        # 3. Bob is owner, Alice is pure favorite
        wl_pure_fav = await service.create_wishlist(bob, title="Pure Favorite Wishlist")
        return wl_owner.id, wl_collab.id, wl_pure_fav.id

    owner_id, collab_id, pure_fav_id = asyncio.run(seed())

    # Alice favorites both the collab wishlist and the pure favorite wishlist
    client.post(f"/api/favorites/{collab_id}", headers=alice_headers)
    client.post(f"/api/favorites/{pure_fav_id}", headers=alice_headers)

    # Check /api/wishlists for Alice
    wl_response = client.get("/api/wishlists", headers=alice_headers)
    assert wl_response.status_code == 200
    lists = wl_response.json()
    list_map = {item["id"]: item for item in lists}

    # Alice's owned wishlist
    assert list_map[owner_id]["role"] == "owner"

    # Alice's collab wishlist: operational role 'member' MUST take precedence over 'favorite'
    assert list_map[collab_id]["role"] == "member"
    assert list_map[collab_id].get("is_favorite") is True

    # Check /api/favorites for Alice
    fav_response = client.get("/api/favorites", headers=alice_headers)
    assert fav_response.status_code == 200
    fav_map = {item["id"]: item for item in fav_response.json()}
    assert pure_fav_id in fav_map
    assert fav_map[pure_fav_id]["role"] == "favorite"
    assert fav_map[pure_fav_id].get("is_favorite") is True


# ============================================================================
# 5. Browser Mini App DOM Regression (Headless Chromium CDP)
# ============================================================================


def send_cdp(
    ws: ClientConnection, counter: int, method: str, params: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Send a Chrome DevTools command and wait for response."""
    ws.send(json.dumps({"id": counter, "method": method, "params": params or {}}))
    while True:
        response = json.loads(ws.recv(timeout=15))
        if response.get("id") == counter:
            assert "error" not in response, response
            return cast(dict[str, Any], response.get("result", {}))


def wait_for_load(ws: ClientConnection) -> None:
    """Wait for page load event."""
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        event = json.loads(ws.recv(timeout=max(0.1, deadline - time.monotonic())))
        if event.get("method") == "Page.loadEventFired":
            return
    raise AssertionError("Page did not load in time")


BRIDGE_SECTIONS_MOCK = r"""
window.__bridgeCalls = {navigated: []};
window.Telegram = {WebApp: {
  initData: 'signed-test-data', ready() {}, expand() {},
  openTelegramLink: (url) => window.__bridgeCalls.navigated.push(url)
}};
const realFetch = window.fetch.bind(window);
const myWishlist = {id: 1, name: 'My Birthday', role: 'owner', is_favorite: false};
const collabWishlist = {id: 2, name: 'Family Holiday', role: 'member', is_favorite: false};
const favWishlist = {id: 3, name: 'Friend Wishlist', role: 'favorite', is_favorite: true};
const historyWishlists = [{id: 3, name: 'Friend Wishlist', viewed_at: '2026-11-11T00:00:00Z'}];

window.fetch = async (url, options = {}) => {
  const path = new URL(url, location.href).pathname;
  const response = (data, status = 200) => new Response(JSON.stringify(data),
    {status, headers: {'content-type': 'application/json'}});
  if (path === '/api/auth/me') return response({telegram_id: 101});
  if (path === '/api/auth/csrf') return response({csrf_token: 'test-csrf'});
  if (path === '/api/wishlists') return response([myWishlist, collabWishlist]);
  if (path === '/api/favorites') return response([favWishlist]);
  if (path === '/api/history') return response(historyWishlists);
  return realFetch(url, options);
};
"""


def test_mini_app_home_sections_and_badges_browser(tmp_path: Path) -> None:
    """Mini App home renders My Wishlists, Collaborating, and Favorites sections with badges."""
    executable = shutil.which("chromium")
    assert executable is not None, "Chromium is required to exercise the Mini App browser flow"

    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'browser_sections.db'}",
        telegram_bot_username="test_bot",
        telegram_app_short_name="app",
    )
    app = create_app(settings)
    listen = socket.socket()
    listen.bind(("127.0.0.1", 0))
    listen.listen(128)
    port = listen.getsockname()[1]

    server = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="on"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listen]}, daemon=True)
    thread.start()

    deadline = time.monotonic() + 8
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    assert server.started, "Uvicorn test server did not start"

    profile = tmp_path / "chromium-profile"
    browser = subprocess.Popen(
        [
            executable,
            "--headless",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--remote-debugging-port=0",
            f"--user-data-dir={profile}",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        debug_file = profile / "DevToolsActivePort"
        deadline = time.monotonic() + 8
        while not debug_file.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert debug_file.exists(), "Chromium debugging endpoint did not start"

        debug_port = int(debug_file.read_text(encoding="utf-8").splitlines()[0])
        debug_url = f"http://127.0.0.1:{debug_port}"
        target = httpx.put(f"{debug_url}/json/new?about:blank", timeout=5).json()

        with connect(target["webSocketDebuggerUrl"], open_timeout=5, close_timeout=5) as ws:
            send_cdp(ws, 1, "Page.enable")
            send_cdp(ws, 2, "Runtime.enable")
            send_cdp(
                ws, 3, "Page.addScriptToEvaluateOnNewDocument", {"source": BRIDGE_SECTIONS_MOCK}
            )
            send_cdp(ws, 4, "Page.navigate", {"url": f"http://127.0.0.1:{port}/"})
            wait_for_load(ws)

            # Check DOM for semantic sections, role badges, and viewing history navigation
            dom_eval_script = r"""(async () => {
              const until = async (check, ms = 3000) => {
                const deadline = performance.now() + ms;
                while (performance.now() < deadline) {
                  const val = check();
                  if (val) return val;
                  await new Promise(r => setTimeout(r, 40));
                }
                return check();
              };
              await until(() => document.querySelector('.badge, [class*="badge"]'));
              const headings = [...document.querySelectorAll('h1, h2, h3, section')].map(el =>
                (el.getAttribute('aria-label') || '') + ' ' + el.textContent);
              const badges = [...document.querySelectorAll('.badge, [class*="badge"]')].map(
                el => el.textContent.trim());
              const historyLinks = [...document.querySelectorAll('button, a')].filter(el =>
                /история просмотров|viewing history|history/i.test(
                  el.textContent + ' ' + (el.getAttribute('aria-label') || '')));

              return {
                headings: headings.join(' | '),
                badges: badges.join(' | '),
                hasHistoryLink: historyLinks.length > 0,
                html: document.body.innerHTML
              };
            })()"""

            eval_res = send_cdp(
                ws,
                5,
                "Runtime.evaluate",
                {"expression": dom_eval_script, "awaitPromise": True, "returnByValue": True},
            )
            data = eval_res["result"]["value"]

            # 1. Assert semantic section division (My Wishlists, Collaborating, Favorites)
            has_my_section = bool(re_search(r"мои вишлисты|my wishlists", data["headings"]))
            has_collab_section = bool(re_search(r"совместные|collaborat", data["headings"]))
            has_fav_section = bool(re_search(r"избранные|favorite", data["headings"]))

            assert has_my_section, (
                f"Missing My Wishlists section in Mini App home! Headings: {data['headings']}"
            )
            assert has_collab_section, (
                f"Missing Collaborating section in Mini App home! Headings: {data['headings']}"
            )
            assert has_fav_section, (
                f"Missing Favorites section in Mini App home! Headings: {data['headings']}"
            )

            # 2. Assert role badges rendering
            has_owner_badge = bool(re_search(r"владелец|owner", data["badges"]))
            has_collab_badge = bool(
                re_search(r"соавтор|member|admin|администратор", data["badges"])
            )
            assert has_owner_badge and has_collab_badge, (
                f"Missing role badges in Mini App home! Badges: {data['badges']}"
            )

            # 3. Assert viewing history link
            assert data["hasHistoryLink"], (
                "Missing 'Viewing history' navigation link on Mini App home"
            )

    finally:
        browser.terminate()
        browser.wait(timeout=5)


def re_search(pattern: str, text: str) -> bool:
    """Helper regex search."""
    import re

    return bool(re.search(pattern, text, re.IGNORECASE))
