"""Browser regression for Mini App sharing and permission-aware controls."""

import json
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
import uvicorn
from websockets.sync.client import ClientConnection, connect

from wishenka.config import Settings
from wishenka.web.app import create_app

pytestmark = pytest.mark.timeout(45)

# This script runs before app code. No Telegram service, clipboard permission or network
# access is required; the mock records what the app actually sends to each browser API.
BRIDGE_MOCK = r"""
window.__bridgeCalls = {copied: [], shared: []};
window.__loadedPaths = [];
Object.defineProperty(navigator, 'clipboard', {configurable: true, value: {
  writeText: async (text) => { window.__bridgeCalls.copied.push(text); }
}});
window.Telegram = {WebApp: {
  initData: 'signed-test-data', ready() {}, expand() {},
  openTelegramLink: (url) => window.__bridgeCalls.shared.push(url)
}};
const realFetch = window.fetch.bind(window);
const role = new URL(location.href).searchParams.get('test_role') || 'owner';
const wishlist = {id: 1, name: 'Party', description: '', event_title: null,
  event_date: null, status: 'active', items: [], role,
  share_token: 'public-token', invite_token: 'private-invite-token', members: [
    {user_id: 101, display_name: 'Owner', role: 'owner'},
    {user_id: 202, display_name: 'Member', role: 'member'}]};
window.fetch = async (url, options = {}) => {
  const path = new URL(url, location.href).pathname;
  window.__loadedPaths.push(path);
  const response = (data) => new Response(JSON.stringify(data),
    {status: 200, headers: {'content-type': 'application/json'}});
  if (path === '/api/auth/me') return response({telegram_id: role === 'owner' ? 101 : 202});
  if (path === '/api/auth/csrf') return response({csrf_token: 'test-csrf'});
  if (path === '/api/wishlists') return response([wishlist]);
  if (path === '/api/wishlists/1') return response(wishlist);
  if (path === '/api/wishlists/1/members') return response(wishlist.members);
  return realFetch(url, options);
};
"""


def send_command(
    ws: ClientConnection, counter: int, method: str, params: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Send a Chrome DevTools command and ignore unrelated events."""
    ws.send(json.dumps({"id": counter, "method": method, "params": params or {}}))
    while True:
        response = json.loads(ws.recv(timeout=15))
        if response.get("id") == counter:
            assert "error" not in response, response
            return cast(dict[str, Any], response.get("result", {}))


def wait_for_load(ws: ClientConnection) -> None:
    """Wait for navigation before evaluating in its document context."""
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        event = json.loads(ws.recv(timeout=max(0.1, deadline - time.monotonic())))
        if event.get("method") == "Page.loadEventFired":
            return
    raise AssertionError("Page did not load")


@pytest.mark.browser
def test_browser_copy_share_and_role_controls(tmp_path: Path, chromium_executable: str) -> None:
    """Owner sharing uses the public link and member UI hides management controls."""
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'browser.db'}",
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
    assert server.started, "Local test server did not start"
    profile = tmp_path / "chromium-profile"
    browser = subprocess.Popen(
        [
            chromium_executable,
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
            send_command(ws, 1, "Page.enable")
            send_command(ws, 2, "Runtime.enable")
            send_command(ws, 3, "Page.addScriptToEvaluateOnNewDocument", {"source": BRIDGE_MOCK})
            send_command(ws, 4, "Page.navigate", {"url": f"http://127.0.0.1:{port}/"})
            wait_for_load(ws)
            # Wait for asynchronous initialization, open the mocked list if necessary,
            # then exercise controls by their accessible visible labels.
            script = r"""(async () => {
              const visible = el => {
                if (!el || !el.getClientRects().length) return false;
                for (let node = el; node; node = node.parentElement) {
                  const css = getComputedStyle(node);
                  if (node.hidden || css.display === 'none' || css.visibility !== 'visible'
                      || Number(css.opacity) === 0) return false;
                }
                return true;
              };
              const find = pattern => [...document.querySelectorAll('button,a,[role=button]')]
                .find(el => visible(el) && pattern.test((el.getAttribute('aria-label') || '') +
                  ' ' + el.textContent));
              const until = async (check, ms = 3000) => {
                const deadline = performance.now() + ms;
                while (performance.now() < deadline) {
                  const value = check(); if (value) return value;
                  await new Promise(resolve => setTimeout(resolve, 40));
                }
                return null;
              };
              const list = await until(() => find(/Party/i));
              if (list) list.click();
              const ownerControl = !!(
                await until(() => find(/member|участник|настро/i))
              );
              if (ownerControl) {
                const copy = await until(() => find(/copy|копир/i));
                if (copy) { copy.click(); await until(() => window.__bridgeCalls.copied.length); }
                const share = await until(() => find(/share|подел/i));
                if (share) { share.click(); await until(() => window.__bridgeCalls.shared.length); }
              }
              return {body: document.body.innerText, ownerControl, calls: window.__bridgeCalls};
            })()"""
            result = send_command(
                ws,
                5,
                "Runtime.evaluate",
                {
                    "expression": script,
                    "awaitPromise": True,
                    "returnByValue": True,
                },
            )["result"]["value"]
            assert result["ownerControl"], f"Owner management controls missing: {result['body']}"
            assert result["calls"]["copied"], "Copy did not invoke navigator.clipboard.writeText"
            assert result["calls"]["shared"], "Share did not invoke Telegram openTelegramLink"
            for link in result["calls"]["copied"] + result["calls"]["shared"]:
                assert "public-token" in link
                assert "private-invite-token" not in link
            send_command(
                ws, 6, "Page.navigate", {"url": f"http://127.0.0.1:{port}/?test_role=member"}
            )
            wait_for_load(ws)
            member_script = r"""(async () => {
              const visible = el => {
                if (!el || !el.getClientRects().length) return false;
                for (let node = el; node; node = node.parentElement) {
                  const css = getComputedStyle(node);
                  if (node.hidden || css.display === 'none' || css.visibility !== 'visible'
                      || Number(css.opacity) === 0) return false;
                }
                return true;
              };
              const buttons = () => [...document.querySelectorAll('button,a,[role=button]')]
                .filter(visible);
              const until = async (check, ms = 3000) => {
                const deadline = performance.now() + ms;
                while (performance.now() < deadline) {
                  const value = check(); if (value) return value;
                  await new Promise(resolve => setTimeout(resolve, 40));
                }
                return null;
              };
              const list = await until(() => buttons().find(el => /Party/i.test(el.textContent)));
              if (list) list.click();
              await until(() => window.__loadedPaths.includes('/api/wishlists/1'));
              await until(() => document.body.innerText.includes('Party'));
              return {body: document.body.innerText,
                managerControl: buttons().some(el =>
                  /invite|приглас|manage members|управление участ/i.test(
                    (el.getAttribute('aria-label') || '') + ' ' + el.textContent))};
            })()"""
            member = send_command(
                ws,
                7,
                "Runtime.evaluate",
                {
                    "expression": member_script,
                    "awaitPromise": True,
                    "returnByValue": True,
                },
            )["result"]["value"]
            assert "Party" in member["body"], "Member must be able to see the list"
            assert not member["managerControl"], "Member can see manager-only controls"
    finally:
        browser.terminate()
        try:
            browser.wait(timeout=5)
        except subprocess.TimeoutExpired:
            browser.kill()
            browser.wait(timeout=5)
        server.should_exit = True
        thread.join(timeout=8)
        listen.close()
        assert not thread.is_alive(), "Local test server failed to stop"
