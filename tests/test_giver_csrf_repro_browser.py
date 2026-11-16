"""Browser reproductions for giver-card CSRF initialization and rejection handling."""

import json
import shutil
import socket
import sqlite3
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.browser_cdp import ASSETS_DIR, HTMX_URL, JSON_ENC_URL, CdpBrowser, CdpPage
from tests.browser_helpers import Seeded
from tests.conftest import BROWSER_TEST_SECRET, BrowserServer

pytestmark = [pytest.mark.browser, pytest.mark.timeout(45)]


@pytest.fixture
def wishlist_server(migrated_db_template: Path, tmp_path: Path) -> Iterator[BrowserServer]:
    """Run the browser server with an origin matching its dynamically selected port."""
    import uvicorn

    from wishenka.auth.session import SessionTokenService
    from wishenka.config import Settings
    from wishenka.web.app import create_app

    database = tmp_path / "csrf-browser.db"
    shutil.copyfile(migrated_db_template, database)
    listen = socket.socket()
    listen.bind(("127.0.0.1", 0))
    listen.listen(128)
    base_url = f"http://127.0.0.1:{listen.getsockname()[1]}"
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{database}",
        secret_key=BROWSER_TEST_SECRET,
        application_origin=base_url,
    )
    server = uvicorn.Server(uvicorn.Config(create_app(settings), log_level="error", lifespan="on"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listen]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 8
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert server.started
        sessions = SessionTokenService(settings.secret_key)
        yield BrowserServer(
            base_url, sessions.create_token(101, "Owner"), sessions.create_token(202, "Viewer")
        )
    finally:
        server.should_exit = True
        thread.join(8)
        listen.close()
        assert not thread.is_alive()


# Install before DOMContentLoaded so the actual page script sees a held CSRF response.
_FETCH_BARRIER = r"""
(() => {
  const originalFetch = window.fetch.bind(window);
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  window.__releaseCsrf = () => release();
  window.__csrfStarted = false;
  window.__csrfCompleted = false;
  window.__mutations = [];
  window.__refreshes = [];
  window.fetch = (input, options = {}) => {
    const url = new URL(typeof input === 'string' ? input : input.url, location.href);
    if (url.pathname === '/api/auth/csrf') {
      window.__csrfStarted = true;
      const response = originalFetch(input, options);
      return Promise.all([response, gate]).then(([result]) => {
        window.__csrfCompleted = true;
        return result;
      });
    }
    if (url.pathname.includes('/reservations') && options.method) {
      window.__mutations.push({url: url.pathname, headers: options.headers});
    }
    if (url.pathname.endsWith('/card') && !window.__allowCardFetch) {
      window.__refreshes.push(url.search);
      return Promise.resolve(new Response('', {status: 200}));
    }
    return originalFetch(input, options);
  };
})();
"""

# The project stub deliberately does not process hx-*; this small adapter models the relevant
# htmx 1.9.12 confirm and configRequest cancellation/resumption event semantics for real forms.
_HTMX_FORM_ADAPTER = r"""
(() => {
  const form = document.querySelector('.item-card .item-giver form[hx-post]');
  form.addEventListener('submit', event => {
    event.preventDefault();
    const path = form.getAttribute('hx-post');
    const send = () => {
      const config = {elt: form, target: form, verb: 'post', path,
        headers: Object.assign({'Content-Type': 'application/json'},
          window.__testAuthorization ? {Authorization: window.__testAuthorization} : {}),
        parameters: Object.fromEntries(new FormData(form)), triggeringEvent: event};
      const before = new CustomEvent('htmx:configRequest',
        {bubbles: true, cancelable: true, detail: config});
      if (!form.dispatchEvent(before)) return;
      fetch(path, {method: 'POST', credentials: 'same-origin', headers: config.headers,
        body: JSON.stringify(config.parameters)}).then(response => {
          window.__mutationStatus = response.status;
        }).catch(() => {});
    };
    const confirm = new CustomEvent('htmx:confirm', {bubbles: true, cancelable: true,
      detail: {elt: form, target: form, path, verb: 'post', triggeringEvent: event,
        issueRequest: send}});
    if (form.dispatchEvent(confirm)) send();
  });
})();
"""


def _cookie_page(
    browser: CdpBrowser, pages: list[CdpPage], server: BrowserServer, seeded: Seeded
) -> CdpPage:
    page = browser.new_page()
    pages.append(page)
    page._send(  # noqa: SLF001 -- setup must precede the first document navigation
        "Network.setCookie",
        {"name": "session_id", "value": seeded.viewer_token, "url": server.base_url},
    )
    page._send("Page.addScriptToEvaluateOnNewDocument", {"source": _FETCH_BARRIER})  # noqa: SLF001
    page.navigate(f"{server.base_url}/share/{seeded.public_token}")
    assert page.evaluate("document.body.hasAttribute('data-viewer-identified')")
    assert page.evaluate("!!document.querySelector('.item-card .item-giver form[hx-post]')")
    page.wait_for("CSRF fetch initiated", "window.__csrfStarted")
    page.evaluate(_HTMX_FORM_ADAPTER)
    return page


def test_giver_click_waits_for_csrf_before_dispatch(
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
    wishlist_server: BrowserServer,
    seed_wishlist: Callable[..., Seeded],
) -> None:
    """A cookie mutation must wait for token readiness and include the issued token."""
    seeded = seed_wishlist(["Present"])
    page = _cookie_page(chromium_browser, _browser_pages, wishlist_server, seeded)
    page.evaluate("document.querySelector('.item-giver form').requestSubmit()")
    assert page.evaluate("window.__mutations.length") == 0, "mutation dispatched before CSRF"
    page.evaluate("window.__releaseCsrf()")
    page.wait_for("one protected mutation", "window.__mutations.length === 1")
    headers: dict[str, Any] = page.evaluate("window.__mutations[0].headers")
    assert headers.get("X-CSRF-Token"), headers
    assert page.evaluate("window.__mutations.length") == 1


def test_csrf_403_does_not_refresh_card_as_booking_refusal(
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
    wishlist_server: BrowserServer,
    seed_wishlist: Callable[..., Seeded],
) -> None:
    """A security rejection is distinct from the recipient's booking refusal."""
    seeded = seed_wishlist(["Present"])
    page = _cookie_page(chromium_browser, _browser_pages, wishlist_server, seeded)
    page.evaluate(r"""(() => {
      const form = document.querySelector('.item-giver form');
      form.dispatchEvent(new CustomEvent('htmx:afterRequest', {bubbles: true,
        detail: {elt: form, xhr: {status: 403,
          responseText: JSON.stringify({detail: 'Invalid CSRF token'})}}}));
    })()""")
    assert page.evaluate("window.__refreshes") == [], "CSRF 403 shown as booking refusal"


def test_failed_initialization_retries_and_coalesces_clicks(
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
    wishlist_server: BrowserServer,
    seed_wishlist: Callable[..., Seeded],
) -> None:
    """Failed token preparation blocks mutation and a later click retries once."""
    seeded = seed_wishlist(["Present"])
    page = _cookie_page(chromium_browser, _browser_pages, wishlist_server, seeded)
    page.evaluate(r"""(() => {
      const previous = window.fetch;
      let attempts = 0;
      window.fetch = (input, options) => {
        if (new URL(input, location.href).pathname === '/api/auth/csrf') {
          attempts++;
          return attempts === 1
            ? Promise.resolve(new Response('{}', {status: 503})) : previous(input, options);
        }
        return previous(input, options);
      };
      const form = document.querySelector('.item-giver form');
      form.dispatchEvent(new CustomEvent('htmx:afterRequest', {bubbles: true,
        detail: {elt: form, xhr: {status: 403,
          responseText: JSON.stringify({detail: 'Invalid CSRF token'})}}}));
      window.__csrfRetryCount = () => attempts;
    })()""")
    page.evaluate("window.__releaseCsrf()")
    # Wait for initial token fetch to settle without issuing a request.
    page.wait_for("initial request settled", "window.__csrfCompleted")
    page.evaluate("document.querySelector('.item-giver form').requestSubmit()")
    page.wait_for(
        "failed preparation message", "!document.querySelector('[data-giver-busy]').hidden"
    )
    assert page.evaluate("window.__mutations.length") == 0
    page.evaluate("document.querySelector('.item-giver form').requestSubmit()")
    page.evaluate("document.querySelector('.item-giver form').requestSubmit()")
    page.wait_for("retry mutation", "window.__mutations.length === 1")
    assert page.evaluate("window.__csrfRetryCount()") == 2


def test_header_guard_and_forbidden_classification(
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
    wishlist_server: BrowserServer,
    seed_wishlist: Callable[..., Seeded],
) -> None:
    """Only configured bearer credentials bypass a missing cookie token."""
    seeded = seed_wishlist(["Present"])
    page = _cookie_page(chromium_browser, _browser_pages, wishlist_server, seeded)
    result = page.evaluate(r"""(() => {
      const form = document.querySelector('.item-giver form');
      const check = headers => form.dispatchEvent(new CustomEvent('htmx:configRequest', {
        bubbles: true, cancelable: true, detail: {elt: form, verb: 'post', headers}
      }));
      const headerless = check({});
      const bearer = check({authorization: 'Bearer explicit-token'});
      const emptyBearer = check({Authorization: 'Bearer '});
      form.setAttribute('hx-request', '{"noHeaders":true}');
      const suppressed = check({Authorization: 'Bearer explicit-token'});
      form.removeAttribute('hx-request');
      form.dispatchEvent(new CustomEvent('htmx:afterRequest', {bubbles: true,
        detail: {elt: form, xhr: {status: 403, responseText: '{"detail":"Forbidden"}'}}}));
      return {headerless, bearer, emptyBearer, suppressed};
    })()""")
    assert result == {
        "headerless": False,
        "bearer": True,
        "emptyBearer": False,
        "suppressed": False,
    }
    page.wait_for("recipient refusal refresh", "window.__refreshes.length === 1")
    assert "notice=refused" in page.evaluate("window.__refreshes[0]")


def test_detached_card_is_not_submitted_after_token_arrives(
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
    wishlist_server: BrowserServer,
    seed_wishlist: Callable[..., Seeded],
) -> None:
    """A delayed action must not fire after its card has been removed."""
    seeded = seed_wishlist(["Present"])
    page = _cookie_page(chromium_browser, _browser_pages, wishlist_server, seeded)
    page.evaluate("document.querySelector('.item-giver form').requestSubmit()")
    page.evaluate("document.querySelector('.item-card').remove()")
    page.evaluate("window.__releaseCsrf()")
    page.wait_for("token response released", "window.__csrfCompleted")
    assert page.evaluate("window.__mutations.length") == 0


def _failure_page(
    browser: CdpBrowser,
    pages: list[CdpPage],
    server: BrowserServer,
    seeded: Seeded,
    failure: str,
) -> CdpPage:
    """Fail the first token request before exercising retry with the real endpoint."""
    page = browser.new_page()
    pages.append(page)
    page._send(  # noqa: SLF001 -- setup must happen before navigation
        "Network.setCookie",
        {"name": "session_id", "value": seeded.viewer_token, "url": server.base_url},
    )
    script = r"""(() => {
      const failure = FAILURE;
      const originalFetch = window.fetch.bind(window);
      const originalTimeout = window.setTimeout.bind(window);
      let attempts = 0;
      let shortened = false;
      let releaseFailure;
      const failureGate = new Promise(resolve => { releaseFailure = resolve; });
      window.__releaseFailure = () => releaseFailure();
      window.__mutations = [];
      window.__csrfAttempts = () => attempts;
      window.setTimeout = (callback, delay, ...args) => {
        if (failure === 'timeout' && delay === 10000 && !shortened) {
          shortened = true;
          return originalTimeout(callback, 500, ...args);
        }
        return originalTimeout(callback, delay, ...args);
      };
      window.fetch = (input, options = {}) => {
        const url = new URL(typeof input === 'string' ? input : input.url, location.href);
        if (url.pathname === '/api/auth/csrf') {
          attempts++;
          if (attempts === 1) {
            if (failure === 'timeout') return new Promise(() => {});
            if (failure === 'malformed') {
              return failureGate.then(() => new Response('{', {status: 200}));
            }
            return failureGate.then(() => new Response('{}', {status: 200}));
          }
        }
        if (url.pathname.includes('/reservations') && options.method) {
          window.__mutations.push({url: url.pathname, headers: options.headers});
        }
        return originalFetch(input, options);
      };
    })();""".replace("FAILURE", json.dumps(failure))
    page._send("Page.addScriptToEvaluateOnNewDocument", {"source": script})  # noqa: SLF001
    page.navigate(f"{server.base_url}/share/{seeded.public_token}")
    page.wait_for("CSRF fetch initiated", "window.__csrfAttempts() === 1")
    page.evaluate(_HTMX_FORM_ADAPTER)
    return page


@pytest.mark.parametrize("failure", ["empty", "malformed", "timeout"])
def test_failed_token_response_blocks_and_allows_retry(
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
    wishlist_server: BrowserServer,
    seed_wishlist: Callable[..., Seeded],
    failure: str,
    tmp_path: Path,
) -> None:
    """No mutation is sent while a missing, malformed, or timed-out token is unresolved."""
    seeded = seed_wishlist(["Present"])
    page = _failure_page(chromium_browser, _browser_pages, wishlist_server, seeded, failure)
    page.evaluate("document.querySelector('.item-giver form').requestSubmit()")
    page.evaluate("window.__releaseFailure()")
    page.wait_for("preparation failure", "!document.querySelector('[data-giver-busy]').hidden")
    assert page.evaluate("window.__mutations.length") == 0
    page.evaluate("document.querySelector('.item-giver form').requestSubmit()")
    page.wait_for("protected retry", "window.__mutations.length === 1")
    assert page.evaluate("!!window.__mutations[0].headers['X-CSRF-Token']")
    page.wait_for("server accepted retry", "window.__mutationStatus !== undefined")
    assert page.evaluate("window.__mutationStatus") == 201
    with sqlite3.connect(tmp_path / "csrf-browser.db") as conn:
        assert conn.execute(
            "SELECT quantity, status, user_id FROM wl_reservations WHERE wish_item_id = ?",
            (int(seeded.item_ids[0]),),
        ).fetchall() == [(1, "active", 202)]


@pytest.mark.parametrize("with_cookie", [False, True])
def test_real_bearer_request_after_csrf_failure(
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
    wishlist_server: BrowserServer,
    seed_wishlist: Callable[..., Seeded],
    with_cookie: bool,
) -> None:
    """A real bearer request reaches the server without a CSRF token or auth probe."""
    seeded = seed_wishlist(["Present"])
    page = _failure_page(chromium_browser, _browser_pages, wishlist_server, seeded, "empty")
    page.evaluate(r"""(() => {
      const previous = window.fetch;
      window.fetch = (input, options) =>
        new URL(input, location.href).pathname === '/api/auth/csrf'
          ? Promise.resolve(new Response('{}', {status: 200})) : previous(input, options);
    })()""")
    if not with_cookie:
        page._send(  # noqa: SLF001 -- exercise the bearer-only mutation
            "Network.deleteCookies", {"name": "session_id", "url": wishlist_server.base_url}
        )
    # A different bearer identity from the cookie proves server precedence when both are present.
    bearer = seeded.owner_token if with_cookie else seeded.viewer_token
    page.evaluate(f"window.__testAuthorization = {json.dumps('Bearer ' + bearer)}")
    page.evaluate("document.querySelector('.item-giver form').requestSubmit()")
    page.evaluate("window.__releaseFailure()")
    page.wait_for("bearer mutation", "window.__mutationStatus !== undefined")
    assert page.evaluate("window.__mutationStatus") == (403 if with_cookie else 201)
    headers: dict[str, Any] = page.evaluate("window.__mutations[0].headers")
    assert headers["Authorization"] == f"Bearer {bearer}"
    assert "X-CSRF-Token" not in headers


def test_hidden_bearer_cannot_bypass_header_guard(
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
    wishlist_server: BrowserServer,
    seed_wishlist: Callable[..., Seeded],
) -> None:
    """Credentials added outside HTMX config cannot authorize an unprotected click."""
    seeded = seed_wishlist(["Present"])
    page = _failure_page(chromium_browser, _browser_pages, wishlist_server, seeded, "empty")
    page.evaluate(
        f"""(() => {{
          const old = window.fetch;
          window.fetch = (input, options = {{}}) => {{
            if (new URL(input, location.href).pathname.includes('/reservations')) {{
              options.headers = Object.assign({{}}, options.headers,
                {{Authorization: {json.dumps("Bearer " + seeded.viewer_token)}}});
            }}
            return old(input, options);
          }};
        }})()"""
    )
    page.evaluate("document.querySelector('.item-giver form').requestSubmit()")
    page.evaluate("window.__releaseFailure()")
    page.wait_for("preparation blocked", "!document.querySelector('[data-giver-busy]').hidden")
    assert page.evaluate("window.__mutations.length") == 0


def test_real_htmx_waits_and_persists_cookie_booking(
    chromium_browser: CdpBrowser,
    _browser_pages: list[CdpPage],
    wishlist_server: BrowserServer,
    seed_wishlist: Callable[..., Seeded],
    tmp_path: Path,
) -> None:
    """HTMX 1.9.12 must resume one protected request after delayed token readiness."""
    seeded = seed_wishlist(["Present"])
    page = chromium_browser.new_page()
    _browser_pages.append(page)
    page._stubs[HTMX_URL] = (ASSETS_DIR / "htmx-1.9.12.min.js").read_bytes()  # noqa: SLF001
    json_enc = (ASSETS_DIR / "htmx-json-enc-1.9.12.js").read_bytes()
    page._stubs[JSON_ENC_URL] = json_enc  # noqa: SLF001
    page._send(  # noqa: SLF001
        "Network.setCookie",
        {"name": "session_id", "value": seeded.viewer_token, "url": wishlist_server.base_url},
    )
    page._send(  # noqa: SLF001
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": _FETCH_BARRIER + "\nwindow.__allowCardFetch = true;"},
    )
    page.navigate(f"{wishlist_server.base_url}/share/{seeded.public_token}")
    page.wait_for("real htmx initialized", "window.htmx && window.htmx.version === '1.9.12'")
    page.wait_for("CSRF request pending", "window.__csrfStarted")
    page.evaluate("document.querySelector('.item-giver form').requestSubmit()")
    assert not [request for request in page.requests if request.method == "POST"]
    page.evaluate("window.__releaseCsrf()")
    page.wait_for(
        "HTMX request complete",
        "document.querySelector('.item-giver .giver-own') !== null",
        timeout=8,
    )
    posts = [request for request in page.requests if request.method == "POST"]
    assert len(posts) == 1
    assert posts[0].status == 201
    with sqlite3.connect(tmp_path / "csrf-browser.db") as conn:
        assert conn.execute(
            "SELECT quantity, status, user_id FROM wl_reservations WHERE wish_item_id = ?",
            (int(seeded.item_ids[0]),),
        ).fetchall() == [(1, "active", 202)]
