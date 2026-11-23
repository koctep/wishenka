"""Minimal Chrome DevTools Protocol driver for the wishlist browser tests (WISHENKA-110).

A single reader (no threads): every command waits for its own response while events are handled
as they arrive (console, Fetch interception, loading, drag interception). All waits are bounded.

The tab runs with ``Fetch`` interception: the three external scripts of ``base.html`` are served
offline from local stubs, requests to the local application pass through and are recorded, and
any other external request is blocked and listed in ``external_requests``.
"""

from __future__ import annotations

import atexit
import base64
import contextlib
import dataclasses
import json
import os
import shutil
import signal
import subprocess
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast
from urllib.parse import urlsplit

import httpx
from websockets.sync.client import ClientConnection, connect

# One finger: (finger id, x, y) in CSS pixels of the viewport.
TouchPoint = tuple[int, float, float]

WindowEventKind = Literal["blur", "visibilitychange"]

ASSETS_DIR = Path(__file__).resolve().parent / "browser_assets"
HTMX_URL = "https://unpkg.com/htmx.org@1.9.12"
JSON_ENC_URL = "https://unpkg.com/htmx.org@1.9.12/dist/ext/json-enc.js"
TELEGRAM_URL = "https://telegram.org/js/telegram-web-app.js"

COMMAND_TIMEOUT = 10.0
LOAD_TIMEOUT = 10.0
DRAG_INTERCEPT_TIMEOUT = 3.0
POLL_STEP = 0.025
TOUCH_MOVE_INTERVAL = 0.016
TOUCH_REST_BEFORE_END = 0.06
LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost"})
INTERNAL_SCHEMES = frozenset({"data", "blob", "about", "chrome", "chrome-error"})

# key -> (key, code, windowsVirtualKeyCode, text)
_KEYS: dict[str, tuple[str, str, int, str]] = {
    "Enter": ("Enter", "Enter", 13, "\r"),
    "Space": (" ", "Space", 32, " "),
    "Escape": ("Escape", "Escape", 27, ""),
    "ArrowDown": ("ArrowDown", "ArrowDown", 40, ""),
    "Tab": ("Tab", "Tab", 9, ""),
}


class PageWaitTimeout(AssertionError):
    """A bounded wait expired; the message carries the wait description and a page snapshot."""


@dataclass(frozen=True)
class ConsoleEntry:
    """One browser console message or uncaught exception.

    Attributes:
        type: ``Runtime.consoleAPICalled`` type (``"log"``, ``"warning"``, ``"error"`` ...) or
            ``"exception"`` for ``Runtime.exceptionThrown``. ``console.warn`` is ``"warning"``.
        text: Message text (arguments joined by a space).
    """

    type: str
    text: str


class ConsoleLog(list[ConsoleEntry]):
    """Console messages in arrival order."""

    def warnings(self) -> list[ConsoleEntry]:
        """Return entries of type ``"warning"`` (``console.warn``)."""
        return [entry for entry in self if entry.type == "warning"]


@dataclass(frozen=True)
class RecordedRequest:
    """One request that reached the real application server.

    Attributes:
        method: HTTP method.
        url: Absolute URL.
        post_data: Request body for POST requests, else ``None``.
        status: Response status once known, else ``None``.
    """

    method: str
    url: str
    post_data: str | None = None
    status: int | None = None

    @property
    def path(self) -> str:
        """URL path without scheme, host and query."""
        rest = self.url.split("://", 1)[-1]
        path = "/" + rest.split("/", 1)[1] if "/" in rest else "/"
        return path.split("?", 1)[0].split("#", 1)[0]


def _js_string(value: str) -> str:
    return json.dumps(value)


def _stub_bodies() -> dict[str, bytes]:
    return {
        HTMX_URL: (ASSETS_DIR / "htmx_stub.js").read_bytes(),
        JSON_ENC_URL: b"",
        TELEGRAM_URL: b"",
    }


def _real_htmx_bodies() -> dict[str, bytes]:
    return {
        HTMX_URL: (ASSETS_DIR / "htmx-1.9.12.min.js").read_bytes(),
        JSON_ENC_URL: (ASSETS_DIR / "htmx-json-enc-1.9.12.js").read_bytes(),
        TELEGRAM_URL: b"",
    }


class CdpPage:
    """One browser tab driven over CDP (Page Object used by the tests)."""

    def __init__(
        self,
        ws: ClientConnection,
        target_id: str,
        debug_url: str,
        *,
        use_real_htmx: bool = False,
    ) -> None:
        self._ws = ws
        self._target_id = target_id
        self._debug_url = debug_url
        self._next_id = 0
        self._fire_and_forget: set[int] = set()
        self._driver_errors: list[str] = []
        self._console = ConsoleLog()
        self._requests: list[RecordedRequest] = []
        self._request_index: dict[str, int] = {}
        self._external: list[str] = []
        self._stubs = _real_htmx_bodies() if use_real_htmx else _stub_bodies()
        self._loaded = False
        self._drag_data: dict[str, Any] | None = None
        self._fingers: dict[int, tuple[float, float]] = {}
        self._closed = False
        self._hold_sign = 1

    # --- connection plumbing ------------------------------------------------------------

    def setup(self, viewport: tuple[int, int]) -> None:
        """Enable the CDP domains, offline interception and the viewport."""
        for domain in ("Page", "Runtime", "Network"):
            self._send(f"{domain}.enable")
        self._send("Fetch.enable", {"patterns": [{"urlPattern": "*"}]})
        self._send(
            "Emulation.setDeviceMetricsOverride",
            {"width": viewport[0], "height": viewport[1], "deviceScaleFactor": 1, "mobile": False},
        )

    def set_viewport(self, width: int, height: int) -> None:
        """Resize the emulated viewport of the open tab (one page can serve every width)."""
        self._send(
            "Emulation.setDeviceMetricsOverride",
            {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False},
        )

    def set_bearer(self, token: str, *, accept_language: str | None = None) -> None:
        """Send ``Authorization: Bearer <token>`` (and optional Accept-Language) on the tab."""
        self._send("Network.enable")
        headers = {"Authorization": f"Bearer {token}"}
        if accept_language:
            headers["Accept-Language"] = accept_language
        self._send("Network.setExtraHTTPHeaders", {"headers": headers})

    def clear_cookies(self) -> None:
        """Drop every cookie of the shared browser profile (cookies ignore the server port)."""
        self._send("Network.enable")
        self._send("Network.clearBrowserCookies")

    def set_cookie(self, name: str, value: str, url: str) -> None:
        """Set a cookie (``HttpOnly``, ``SameSite=Lax``) on the tab via ``Network.setCookie``."""
        self._send("Network.enable")
        result = self._send(
            "Network.setCookie",
            {
                "name": name,
                "value": value,
                "url": url,
                "httpOnly": True,
                "sameSite": "Lax",
            },
        )
        assert result.get("success", True), f"Network.setCookie failed: {result}"

    def _send(
        self, method: str, params: dict[str, Any] | None = None, timeout: float = COMMAND_TIMEOUT
    ) -> dict[str, Any]:
        self._next_id += 1
        command_id = self._next_id
        self._ws.send(json.dumps({"id": command_id, "method": method, "params": params or {}}))
        deadline = time.monotonic() + timeout
        while True:
            message = self._receive(deadline)
            if message is None:
                raise AssertionError(f"CDP {method}: no response within {timeout:g}s")
            if message.get("id") == command_id:
                if "error" in message:
                    raise AssertionError(f"CDP {method} failed: {message['error']}")
                return cast(dict[str, Any], message.get("result", {}))

    def _send_nowait(self, method: str, params: dict[str, Any]) -> None:
        self._next_id += 1
        self._fire_and_forget.add(self._next_id)
        self._ws.send(json.dumps({"id": self._next_id, "method": method, "params": params}))

    def _receive(self, deadline: float) -> dict[str, Any] | None:
        """Read one message (handling events); ``None`` when ``deadline`` passes first."""
        remaining = deadline - time.monotonic()
        try:
            raw = self._ws.recv(timeout=max(remaining, 0.001))
        except TimeoutError:
            return None
        message = cast(dict[str, Any], json.loads(raw))
        if "method" in message:
            self._handle_event(message["method"], message.get("params", {}))
        elif message.get("id") in self._fire_and_forget:
            self._fire_and_forget.discard(message["id"])
            if "error" in message:
                self._driver_errors.append(str(message["error"]))
        return message

    def _pump(self, duration: float) -> None:
        """Handle incoming events for up to ``duration`` seconds."""
        deadline = time.monotonic() + duration
        while self._receive(deadline) is not None:
            pass

    def _handle_event(self, method: str, params: dict[str, Any]) -> None:
        if method == "Runtime.consoleAPICalled":
            parts = [str(a.get("value", a.get("description", ""))) for a in params.get("args", [])]
            self._console.append(ConsoleEntry(params.get("type", "log"), " ".join(parts)))
        elif method == "Runtime.exceptionThrown":
            details = params.get("exceptionDetails", {})
            exception = details.get("exception", {})
            text = exception.get("description") or details.get("text", "")
            self._console.append(ConsoleEntry("exception", str(text)))
        elif method == "Page.loadEventFired":
            self._loaded = True
        elif method == "Input.dragIntercepted":
            self._drag_data = cast(dict[str, Any], params.get("data", {}))
        elif method == "Fetch.requestPaused":
            self._on_request_paused(params)
        elif method == "Network.responseReceived":
            index = self._request_index.get(params.get("requestId", ""))
            if index is not None:
                status = int(params["response"]["status"])
                self._requests[index] = dataclasses.replace(self._requests[index], status=status)

    def _on_request_paused(self, params: dict[str, Any]) -> None:
        request_id = params["requestId"]
        request = params["request"]
        url = str(request["url"])
        parts = urlsplit(url)
        if url in self._stubs:
            self._send_nowait(
                "Fetch.fulfillRequest",
                {
                    "requestId": request_id,
                    "responseCode": 200,
                    "responseHeaders": [{"name": "Content-Type", "value": "text/javascript"}],
                    "body": base64.b64encode(self._stubs[url]).decode("ascii"),
                },
            )
        elif parts.scheme in INTERNAL_SCHEMES:
            self._send_nowait("Fetch.continueRequest", {"requestId": request_id})
        elif parts.hostname in LOCAL_HOSTS:
            self._requests.append(
                RecordedRequest(str(request["method"]), url, request.get("postData"))
            )
            network_id = params.get("networkId")
            if network_id:
                self._request_index[str(network_id)] = len(self._requests) - 1
            self._send_nowait("Fetch.continueRequest", {"requestId": request_id})
        else:
            self._external.append(url)
            self._send_nowait(
                "Fetch.failRequest", {"requestId": request_id, "errorReason": "BlockedByClient"}
            )

    # --- observation -----------------------------------------------------------------------

    @property
    def console(self) -> ConsoleLog:
        """Console messages and exceptions captured since the tab was created."""
        self._pump(0.02)
        return self._console

    @property
    def requests(self) -> list[RecordedRequest]:
        """Requests that went to the application server, in order."""
        self._pump(0.02)
        return list(self._requests)

    @property
    def external_requests(self) -> list[str]:
        """URLs of blocked requests to anything but the application server and the stubs."""
        self._pump(0.02)
        return list(self._external)

    def navigate(self, url: str) -> None:
        """``Page.navigate`` and wait for ``Page.loadEventFired`` (deadline 10 s)."""
        self._loaded = False
        result = self._send("Page.navigate", {"url": url})
        if result.get("errorText"):
            raise AssertionError(f"navigation to {url} failed: {result['errorText']}")
        deadline = time.monotonic() + LOAD_TIMEOUT
        while not self._loaded:
            if self._receive(deadline) is None:
                raise AssertionError(f"{url} did not finish loading within {LOAD_TIMEOUT:g}s")
        self._pump(0.02)

    def evaluate(self, expression: str, *, await_promise: bool = False) -> Any:
        """Run a JS expression and return its value; a page exception becomes AssertionError."""
        result = self._send(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": await_promise,
                "userGesture": True,
            },
        )
        if "exceptionDetails" in result:
            details = result["exceptionDetails"]
            text = details.get("exception", {}).get("description") or details.get("text")
            raise AssertionError(f"page exception in {expression[:120]!r}: {text}")
        return result["result"].get("value")

    def wait_for(self, description: str, predicate_js: str, timeout: float = 5.0) -> Any:
        """Poll ``predicate_js`` until truthy; raise ``PageWaitTimeout`` at the deadline.

        Returns:
            The last (truthy) value of the predicate.
        """
        deadline = time.monotonic() + timeout
        value: Any = None
        while True:
            value = self.evaluate(predicate_js)
            if value:
                return value
            if time.monotonic() >= deadline:
                raise PageWaitTimeout(
                    f"timed out after {timeout:g}s waiting for: {description}\n"
                    f"last value: {value!r}\n{self.snapshot()}"
                )
            self._hold_fingers()
            self._pump(POLL_STEP)

    def _hold_fingers(self) -> None:
        """Make fingers that are down report a sub-pixel move, as a resting real finger does.

        Chromium processes a pending ``lostpointercapture`` only together with the next pointer
        event; without a move it would never arrive while the test waits for it.
        """
        if not self._fingers:
            return
        self._hold_sign = -self._hold_sign
        shift = 0.01 * self._hold_sign
        for finger, (x, y) in list(self._fingers.items()):
            self._fingers[finger] = (x, y + shift)
        self._touch("touchMove", [(f, x, y) for f, (x, y) in self._fingers.items()])

    # --- mouse and keyboard ----------------------------------------------------------------

    def _rect_point(self, selector: str, y_fraction: float = 0.5) -> tuple[float, float]:
        rect = self.evaluate(
            f"(() => {{ const e = document.querySelector({_js_string(selector)});"
            " if (!e) return null; const r = e.getBoundingClientRect();"
            " return [r.left + r.width / 2, r.top + r.height * " + repr(y_fraction) + "]; })()"
        )
        if rect is None:
            raise AssertionError(f"no element matches {selector!r}\n{self.snapshot()}")
        return float(rect[0]), float(rect[1])

    def _mouse(self, kind: str, x: float, y: float, **extra: Any) -> None:
        self._send("Input.dispatchMouseEvent", {"type": kind, "x": x, "y": y, **extra})

    def click(self, selector: str) -> None:
        """Mouse press and release at the centre of the first element matching ``selector``."""
        x, y = self._rect_point(selector)
        self._mouse("mouseMoved", x, y)
        self._mouse("mousePressed", x, y, button="left", clickCount=1)
        self._mouse("mouseReleased", x, y, button="left", clickCount=1)

    def press_key(self, key: str) -> None:
        """``keyDown`` and ``keyUp`` for ``Enter``, ``Space``, ``Escape``, ``ArrowDown``, ``Tab``,
        ``Shift+Tab``, or a letter.

        ``Space`` is sent with ``key=" "`` and ``text=" "``. The key goes to the focused element.
        """
        modifiers = 0
        lookup = key
        if key == "Shift+Tab":
            modifiers = 8
            lookup = "Tab"
        if lookup in _KEYS:
            name, code, virtual, text = _KEYS[lookup]
        elif len(lookup) == 1 and lookup.isalpha():
            name, code, virtual, text = lookup, f"Key{lookup.upper()}", ord(lookup.upper()), lookup
        else:
            raise ValueError(f"unsupported key {key!r}")
        down: dict[str, Any] = {
            "type": "keyDown",
            "key": name,
            "code": code,
            "windowsVirtualKeyCode": virtual,
        }
        if modifiers:
            down["modifiers"] = modifiers
        if text:
            down["text"] = text
        up: dict[str, Any] = {
            "type": "keyUp",
            "key": name,
            "code": code,
            "windowsVirtualKeyCode": virtual,
        }
        if modifiers:
            up["modifiers"] = modifiers
        self._send("Input.dispatchKeyEvent", down)
        self._send("Input.dispatchKeyEvent", up)

    def _native_drag(
        self, source_selector: str, release: tuple[float, float], *, drop: bool
    ) -> None:
        """Drag from the source and release at ``release`` (native HTML5 drag through CDP)."""
        sx, sy = self._rect_point(source_selector)
        self._drag_data = None
        self._send("Input.setInterceptDrags", {"enabled": True})
        try:
            self._mouse("mouseMoved", sx, sy)
            self._mouse("mousePressed", sx, sy, button="left", clickCount=1, buttons=1)
            self._mouse("mouseMoved", sx + 6, sy + 6, button="left", buttons=1)
            self._mouse("mouseMoved", release[0], release[1], button="left", buttons=1)
            deadline = time.monotonic() + DRAG_INTERCEPT_TIMEOUT
            while self._drag_data is None:
                if self._receive(deadline) is None:
                    raise AssertionError(
                        f"Input.dragIntercepted not received within {DRAG_INTERCEPT_TIMEOUT:g}s "
                        f"for {source_selector!r}\n{self.snapshot()}"
                    )
            data = self._drag_data
            x, y = release
            self._send(
                "Input.dispatchDragEvent", {"type": "dragEnter", "x": x, "y": y, "data": data}
            )
            self._send(
                "Input.dispatchDragEvent", {"type": "dragOver", "x": x, "y": y, "data": data}
            )
            if drop:
                self._send(
                    "Input.dispatchDragEvent", {"type": "drop", "x": x, "y": y, "data": data}
                )
            else:
                self._send(
                    "Input.dispatchDragEvent", {"type": "dragCancel", "x": x, "y": y, "data": data}
                )
            self._mouse("mouseReleased", x, y, button="left", buttons=0)
        finally:
            with contextlib.suppress(AssertionError):
                self._send("Input.setInterceptDrags", {"enabled": False})
        self._pump(0.02)

    def mouse_drag(self, source_selector: str, target_selector: str, *, y_fraction: float) -> None:
        """Native drag and drop: press on the source, drop at ``y_fraction`` of the target height.

        ``y_fraction`` is 0.0 at the target top edge and 1.0 at its bottom edge.
        """
        self._native_drag(source_selector, self._rect_point(target_selector, y_fraction), drop=True)

    def drop_outside(self, source_selector: str, point: tuple[float, float]) -> None:
        """Native drag from the source and release at a viewport point (x, y)."""
        self._native_drag(source_selector, point, drop=True)

    # --- touch -----------------------------------------------------------------------------

    def enable_touch(self) -> None:
        """``Emulation.setTouchEmulationEnabled``; call before any touch gesture."""
        self._send("Emulation.setTouchEmulationEnabled", {"enabled": True, "maxTouchPoints": 5})

    def _touch(self, kind: str, points: list[TouchPoint]) -> None:
        payload = [{"x": x, "y": y, "id": finger} for finger, x, y in points]
        self._send("Input.dispatchTouchEvent", {"type": kind, "touchPoints": payload})

    def touch_start(self, points: list[TouchPoint]) -> None:
        """``touchStart`` with the given fingers.

        Calling it again with a longer list adds the new finger to the gesture in progress.
        """
        for finger, x, y in points:
            self._fingers[finger] = (x, y)
        self._touch("touchStart", points)

    def touch_move(self, points: list[TouchPoint]) -> None:
        """``touchMove`` with the current position of every finger that is down."""
        for finger, x, y in points:
            self._fingers[finger] = (x, y)
        self._touch("touchMove", points)
        self._pump(TOUCH_MOVE_INTERVAL)

    def touch_end(self) -> None:
        """``touchEnd`` for all fingers; a no-op when no finger is down."""
        if not self._fingers:
            return
        self._fingers.clear()
        # Without a rest before the release the gesture has a huge velocity: Chromium starts a
        # fling and swallows the next tap (observed in Step 4). Real fingers pause a moment.
        self._pump(TOUCH_REST_BEFORE_END)
        self._touch("touchEnd", [])

    def touch_cancel(self) -> None:
        """``touchCancel`` for all fingers (source of ``pointercancel``)."""
        self._fingers.clear()
        self._touch("touchCancel", [])

    def touch_tap(self, selector: str) -> None:
        """Touch down and up at the centre of the element, without movement."""
        x, y = self._rect_point(selector)
        self.touch_start([(1, x, y)])
        self.touch_end()

    def touch_drag(
        self, handle_selector: str, target_selector: str, y_fraction: float, *, steps: int = 4
    ) -> None:
        """Complete touch gesture: down on the handle, ``steps`` moves to the target, up."""
        start_x, start_y = self._rect_point(handle_selector)
        end_x, end_y = self._rect_point(target_selector, y_fraction)
        self.touch_start([(1, start_x, start_y)])
        for step in range(1, steps + 1):
            fraction = step / steps
            self.touch_move(
                [
                    (
                        1,
                        start_x + (end_x - start_x) * fraction,
                        start_y + (end_y - start_y) * fraction,
                    )
                ]
            )
        self.touch_end()

    def dispatch_window_event(self, kind: WindowEventKind) -> None:
        """Dispatch a synthetic ``blur`` (window) or ``visibilitychange`` (hidden document)."""
        if kind == "blur":
            self.evaluate("window.dispatchEvent(new Event('blur'))")
        else:
            self.evaluate(
                "(() => { Object.defineProperty(document, 'hidden',"
                " {value: true, configurable: true});"
                " document.dispatchEvent(new Event('visibilitychange')); })()"
            )

    # --- page state ------------------------------------------------------------------------

    def ajax_calls(self) -> list[dict[str, Any]]:
        """``window.__ajaxCalls`` of the htmx stub: dicts with verb, url, target, swap, values."""
        return cast(list[dict[str, Any]], self.evaluate("window.__ajaxCalls || []"))

    def order(self) -> list[str]:
        """``data-item-id`` of every ``#items-list`` card in DOM order, as strings."""
        return cast(
            list[str],
            self.evaluate(
                "Array.from(document.querySelectorAll('#items-list .item-card'),"
                " (c) => c.getAttribute('data-item-id'))"
            ),
        )

    def card_state(self, item_id: str) -> dict[str, Any]:
        """Return ``{"expanded": <aria-expanded string or None>, "hidden": <details.hidden>}``."""
        card_id = _js_string(f"item-card-{item_id}")
        return cast(
            dict[str, Any],
            self.evaluate(
                f"(() => {{ const c = document.getElementById({card_id});"
                " const s = c.querySelector('.item-card-summary');"
                " const d = c.querySelector('.item-card-details');"
                " return {expanded: s.getAttribute('aria-expanded'), hidden: d.hidden}; })()"
            ),
        )

    def snapshot(self) -> str:
        """Text dump for failure diagnostics (order, states, console and request tails, HTML)."""
        lines: list[str] = ["--- page snapshot ---"]
        try:
            page_state = self.evaluate(
                "(() => ({url: location.href, scrollY: window.scrollY,"
                " order: Array.from(document.querySelectorAll('#items-list .item-card'),"
                " (c) => [c.getAttribute('data-item-id'),"
                " c.querySelector('.item-card-summary')?.getAttribute('aria-expanded'),"
                " c.querySelector('.item-card-details')?.hidden, c.className]),"
                " body: document.body.className,"
                " ajax: window.__ajaxCalls || [],"
                " html: (document.getElementById('items-list') || {outerHTML: ''}).outerHTML}))()"
            )
            lines.append(f"url: {page_state['url']}  scrollY: {page_state['scrollY']}")
            lines.append(f"body class: {page_state['body']!r}")
            for entry in page_state["order"]:
                lines.append(
                    f"card {entry[0]}: aria-expanded={entry[1]} hidden={entry[2]}"
                    f" class={entry[3]!r}"
                )
            lines.append(f"ajax calls: {page_state['ajax']}")
            lines.append(f"items-list: {str(page_state['html'])[:2000]}")
        except AssertionError as error:
            lines.append(f"(page state unavailable: {error})")
        lines.append("console (last 20): " + repr([(e.type, e.text) for e in self._console[-20:]]))
        lines.append(
            "requests (last 20): "
            + repr([(r.method, r.path, r.status, r.post_data) for r in self._requests[-20:]])
        )
        lines.append(f"external requests: {self._external}")
        if self._driver_errors:
            lines.append(f"driver errors: {self._driver_errors[-5:]}")
        return "\n".join(lines)

    def screenshot(self, path: Path) -> None:
        """``Page.captureScreenshot`` into ``path``."""
        result = self._send("Page.captureScreenshot", {"format": "png"})
        path.write_bytes(base64.b64decode(result["data"]))

    def close(self) -> None:
        """Close the websocket and the tab (bounded)."""
        if self._closed:
            return
        self._closed = True
        with contextlib.suppress(Exception):
            self._ws.close()
        with contextlib.suppress(Exception):
            httpx.get(f"{self._debug_url}/json/close/{self._target_id}", timeout=5)


_LIVE_BROWSERS: set[subprocess.Popen[bytes]] = set()
TERMINATE_TIMEOUT = 5.0


def launch_chromium(command: Sequence[str]) -> subprocess.Popen[bytes]:
    """Start a Chromium process that cannot outlive the test run (WISHENKA-166, hazard H9).

    ``setpriv --pdeathsig KILL`` (when available) makes the kernel kill the browser if the launching
    thread dies, even by ``SIGKILL``; ``start_new_session`` gives it its own process group so that
    ``stop_chromium`` and the ``atexit`` hook can kill the whole tree. Without ``setpriv`` a
    ``SIGKILL`` of the test process can leave an orphan. ``preexec_fn`` is avoided on purpose: it
    is unsafe in a multi-threaded process.
    """
    setpriv = shutil.which("setpriv")
    argv = [setpriv, "--pdeathsig", "KILL", *command] if setpriv else list(command)
    process = subprocess.Popen(
        argv,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    _LIVE_BROWSERS.add(process)
    return process


def _kill_group(process: subprocess.Popen[bytes]) -> None:
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(process.pid, signal.SIGKILL)


def stop_chromium(process: subprocess.Popen[bytes]) -> None:
    """``terminate``, bounded ``wait``, then kill the whole process group (children included)."""
    _LIVE_BROWSERS.discard(process)
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(TERMINATE_TIMEOUT)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(TERMINATE_TIMEOUT)
    _kill_group(process)


def _kill_live_browsers() -> None:
    for process in list(_LIVE_BROWSERS):
        _kill_group(process)
    _LIVE_BROWSERS.clear()


atexit.register(_kill_live_browsers)


def read_debug_port(port_file: Path) -> int | None:
    """Port from ``DevToolsActivePort`` once Chromium has written its first line, else ``None``.

    Chromium creates the file before it writes the port, so existence alone is not readiness.
    """
    try:
        lines = port_file.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    if lines and lines[0].strip().isdigit():
        return int(lines[0])
    return None


class CdpBrowser:
    """One headless Chromium process shared by the session."""

    def __init__(self) -> None:
        self._process: subprocess.Popen[bytes] | None = None
        self._executable = ""
        self._profile_root = Path()
        self._debug_url = ""
        self._generation = 0

    def start(self, executable: str, profile_dir: Path) -> None:
        """Start Chromium with ``--remote-debugging-port=0`` and an isolated profile."""
        self._executable = executable
        self._profile_root = profile_dir
        self._launch()

    def _launch(self) -> None:
        self.stop()  # a dead process may have left children: reap its whole group
        self._generation += 1
        profile = self._profile_root / f"run{self._generation}"
        process = launch_chromium(
            [
                self._executable,
                "--headless",
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--remote-debugging-port=0",
                f"--user-data-dir={profile}",
                "about:blank",
            ]
        )
        self._process = process
        port_file = profile / "DevToolsActivePort"
        deadline = time.monotonic() + 10
        port = read_debug_port(port_file)
        while port is None and time.monotonic() < deadline:
            if process.poll() is not None:
                code = process.returncode
                self.stop()
                raise AssertionError(f"Chromium exited early with code {code}")
            time.sleep(0.05)
            port = read_debug_port(port_file)
        if port is None:
            self.stop()
            raise AssertionError("Chromium debugging endpoint did not start within 10 s")
        self._debug_url = f"http://127.0.0.1:{port}"

    def ensure_alive(self) -> None:
        """Restart the process if it died."""
        if self._process is None or self._process.poll() is not None:
            self._launch()

    def new_page(
        self, viewport: tuple[int, int] = (412, 800), *, use_real_htmx: bool = False
    ) -> CdpPage:
        """Open a new tab (``PUT /json/new``) and attach a ``CdpPage``."""
        target = httpx.put(f"{self._debug_url}/json/new?about:blank", timeout=5).json()
        # ``legacy=True`` is the documented way to hold a connection open without ``with``.
        ws = connect(
            target["webSocketDebuggerUrl"],
            open_timeout=5,
            close_timeout=5,
            max_size=None,
            legacy=True,
        )
        page = CdpPage(ws, str(target["id"]), self._debug_url, use_real_htmx=use_real_htmx)
        try:
            page.setup(viewport)
        except BaseException:
            page.close()
            raise
        return page

    def stop(self) -> None:
        """Stop the process and its group (bounded); the profile directory is the caller's."""
        process = self._process
        self._process = None
        if process is not None:
            stop_chromium(process)
