"""Offline checks for lifespan-owned preview resources and safe reuse."""

import asyncio
import logging
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import cast

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from wishenka.auth.models import AuthenticatedUser
from wishenka.auth.session import SessionTokenService
from wishenka.config import Settings
from wishenka.items.exceptions import SSRFBlockedError
from wishenka.items.service import ItemPreviewService
from wishenka.web.app import create_app

pytestmark = pytest.mark.timeout(30)


@pytest.fixture
def recording_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> list[tuple[httpx.AsyncHTTPTransport, httpx.Request]]:
    """Replace external I/O while retaining the safe transport and real HTTPX client."""
    requests: list[tuple[httpx.AsyncHTTPTransport, httpx.Request]] = []

    async def resolve(host: str, port: int = 80) -> list[str]:
        return ["8.8.8.8"]

    async def respond(
        transport: httpx.AsyncHTTPTransport, request: httpx.Request
    ) -> httpx.Response:
        requests.append((transport, request))
        headers = {"Cache-Control": "public, max-age=300"}
        if request.url.path == "/private":
            headers = {"Cache-Control": "private, no-store", "Set-Cookie": "sid=secret; Path=/"}
        elif request.url.path == "/vary":
            headers["Vary"] = "Accept-Language"
        elif request.url.path == "/cookie":
            headers["Set-Cookie"] = "sid=secret; Path=/"
        elif request.url.path == "/expired":
            headers["Cache-Control"] = "public, max-age=0"
        body = "<html><head><title>Product</title></head></html>"
        if request.url.path == "/untitled":
            body = "<html><body></body></html>"
        return httpx.Response(
            200,
            headers=headers,
            text=body,
            request=request,
        )

    monkeypatch.setattr("wishenka.items.fetcher.resolve_and_validate_host", resolve)
    monkeypatch.setattr("wishenka.items.ssrf.resolve_and_validate_host", resolve)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", respond)
    return requests


@pytest.fixture
def preview_app(tmp_path: Path) -> Iterator[tuple[TestClient, str]]:
    """Run the actual app lifespan and create an authenticated wishlist."""
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'preview.db'}",
        secret_key="preview-resource-test-secret",
        background_cleanup_enabled=False,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        owner = AuthenticatedUser(telegram_id=101, first_name="Alice", auth_method="session_token")
        wishlist = asyncio.run(app.state.domain_service.create_wishlist(owner=owner, title="Test"))
        token = SessionTokenService(settings.secret_key).create_token(101, "Alice")
        client.headers.update({"Authorization": f"Bearer {token}", "HX-Request": "true"})
        yield client, f"/web/wishlists/{wishlist.id}/items/preview"


def test_public_preview_is_reused_in_actual_ui(
    preview_app: tuple[TestClient, str],
    recording_origin: list[tuple[httpx.AsyncHTTPTransport, httpx.Request]],
) -> None:
    """Two requests for one publicly cacheable product perform one origin fetch."""
    client, endpoint = preview_app
    for _ in range(2):
        response = client.post(endpoint, data={"raw_input": "https://shop.example.com/product"})
        assert response.status_code == 200
        assert "Product" in response.text
    assert len(recording_origin) == 1


@pytest.mark.parametrize(("amount", "expected"), [("1.299,99 €", "1299.99"), ("0,50 €", "0.5")])
def test_fractional_preview_persists_for_gifter(
    preview_app: tuple[TestClient, str], monkeypatch: pytest.MonkeyPatch, amount: str, expected: str
) -> None:
    """Preview, quick-add, SQLite readback, and public gifter view keep the same amount."""
    from unittest.mock import AsyncMock, MagicMock

    from bs4 import BeautifulSoup

    client, endpoint = preview_app
    url = "https://shop.example.com/product"
    html = (
        '<meta property="og:title" content="Product">'
        f'<meta property="product:price:amount" content="{amount}">'
    )
    fetcher = MagicMock()
    fetcher._fetch_html = AsyncMock(return_value=(html, url))
    monkeypatch.setattr(
        cast(FastAPI, client.app).state, "item_preview_service", ItemPreviewService(fetcher)
    )

    response = client.post(endpoint, data={"raw_input": url})

    assert response.status_code == 200
    assert f"{expected} EUR" in response.text
    card = BeautifulSoup(response.text, "html.parser")
    fields = {node["name"]: node["value"] for node in card.select('input[type="hidden"]')}
    assert fields["price"] == expected
    quick_response = client.post(endpoint.removesuffix("preview") + "quick", data=fields)
    assert quick_response.status_code == 201
    wishlist_id = int(endpoint.split("/")[3])
    service = cast(FastAPI, client.app).state.domain_service
    wishlist = asyncio.run(service.get_wishlist_by_id(wishlist_id))
    assert wishlist.items[0].price == float(expected)
    client.headers.pop("Authorization")
    share_response = client.get(f"/share/{wishlist.public_token}")
    assert share_response.status_code == 200
    assert f"{expected} EUR" in share_response.text


@pytest.mark.parametrize("currency", ["GBP", "JPY", "CNY", "TRY", "GEL", "AMD", "CHF"])
def test_imported_currency_survives_wish_edit(
    preview_app: tuple[TestClient, str], monkeypatch: pytest.MonkeyPatch, currency: str
) -> None:
    """Creating from preview and submitting the edit form keeps its selected currency."""
    from unittest.mock import AsyncMock, MagicMock

    from bs4 import BeautifulSoup

    client, endpoint = preview_app
    url = "https://shop.example.com/product"
    html = (
        '<meta property="og:title" content="Product">'
        '<meta property="product:price:amount" content="12.50">'
        f'<meta property="product:price:currency" content="{currency}">'
    )
    fetcher = MagicMock()
    fetcher._fetch_html = AsyncMock(return_value=(html, url))
    monkeypatch.setattr(
        cast(FastAPI, client.app).state, "item_preview_service", ItemPreviewService(fetcher)
    )
    # CHF is a stored legacy code rather than a parser-supported import.
    if currency == "CHF":
        from wishenka.items.schemas import ItemPreviewDTO

        cast(FastAPI, client.app).state.item_preview_service.fetch_preview = AsyncMock(
            return_value=ItemPreviewDTO(title="Product", price=12.5, currency=currency, url=url)
        )
    preview = client.post(endpoint, data={"raw_input": url})
    assert preview.status_code == 200
    card = BeautifulSoup(preview.text, "html.parser")
    fields = {node["name"]: node["value"] for node in card.select('input[type="hidden"]')}
    assert fields["currency"] == currency
    assert client.post(endpoint.removesuffix("preview") + "quick", data=fields).status_code == 201

    wishlist_id = int(endpoint.split("/")[3])
    service = cast(FastAPI, client.app).state.domain_service
    wishlist = asyncio.run(service.get_wishlist_by_id(wishlist_id))
    item_id = wishlist.items[0].id
    edit_url = f"/web/wishlists/{wishlist_id}/items/{item_id}/edit"
    edit_page = client.get(edit_url)
    assert edit_page.status_code == 200
    form = BeautifulSoup(edit_page.text, "html.parser")
    selected = form.select_one("#item-currency-select option[selected]")
    assert selected is not None and selected["value"] == currency
    response = client.post(
        edit_url,
        data={"title": "Edited product", "price": "12.5", "currency": selected["value"]},
    )
    assert response.status_code == 200
    updated = asyncio.run(service.get_wishlist_by_id(wishlist_id))
    assert updated.items[0].currency == currency
    assert updated.items[0].price == 12.5


def test_cache_lookup_logs_outcome_without_url(
    preview_app: tuple[TestClient, str],
    recording_origin: list[tuple[httpx.AsyncHTTPTransport, httpx.Request]],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Cache observability identifies reuse without revealing the key."""
    client, endpoint = preview_app
    with caplog.at_level(logging.DEBUG, logger="wishenka.items"):
        for _ in range(2):
            response = client.post(
                endpoint, data={"raw_input": "https://shop.example.com/private-product"}
            )
            assert response.status_code == 200
    records = [r for r in caplog.records if getattr(r, "event", None) == "preview_cache_lookup"]
    assert [getattr(r, "cache_outcome", None) for r in records] == ["miss", "hit"]
    assert all("private-product" not in r.getMessage() for r in records)
    assert all(not hasattr(r, "url") for r in records)
    assert len(recording_origin) == 1


def test_uncached_requests_share_transport_without_sharing_cookies(
    preview_app: tuple[TestClient, str],
    recording_origin: list[tuple[httpx.AsyncHTTPTransport, httpx.Request]],
) -> None:
    """Non-cacheable responses still use one pool without forwarding origin cookies."""
    client, endpoint = preview_app
    for url in ("https://shop.example.com/private", "https://shop.example.com/other"):
        response = client.post(endpoint, data={"raw_input": url})
        assert response.status_code == 200
        assert "Product" in response.text
    assert len(recording_origin) == 2
    assert "cookie" not in recording_origin[1][1].headers
    assert recording_origin[0][0] is recording_origin[1][0]


def test_uncached_previews_reuse_real_http_connection(
    preview_app: tuple[TestClient, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A real HTTP/1.1 origin sees two uncached requests on one connection."""
    requests: list[tuple[str, tuple[str, int]]] = []

    class Origin(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:
            requests.append((self.path, self.client_address))
            body = b"<html><head><title>Product</title></head></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Origin)
    server.daemon_threads = True
    port = server.server_address[1]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    async def allow_test_origin(host: str, requested_port: int = 80) -> list[str]:
        assert (host, requested_port) == ("127.0.0.1", port)
        return [host]

    monkeypatch.setattr("wishenka.items.fetcher.resolve_and_validate_host", allow_test_origin)
    monkeypatch.setattr("wishenka.items.ssrf.resolve_and_validate_host", allow_test_origin)
    try:
        client, endpoint = preview_app
        for path in ("/first", "/second"):
            response = client.post(endpoint, data={"raw_input": f"http://127.0.0.1:{port}{path}"})
            assert response.status_code == 200
            assert "Product" in response.text
        assert [path for path, _ in requests] == ["/first", "/second"]
        assert requests[0][1] == requests[1][1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        assert not thread.is_alive()


def test_cache_expiry_and_distinct_urls(
    preview_app: tuple[TestClient, str],
    recording_origin: list[tuple[httpx.AsyncHTTPTransport, httpx.Request]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fresh data is reused, different URLs are distinct, and expired data refetches."""
    client, endpoint = preview_app
    real_monotonic = time.monotonic
    offset = [0.0]
    monkeypatch.setattr(time, "monotonic", lambda: real_monotonic() + offset[0])
    for path in ("/one", "/two", "/one"):
        assert (
            client.post(endpoint, data={"raw_input": f"https://shop.example.com{path}"}).status_code
            == 200
        )
    assert len(recording_origin) == 2
    offset[0] += 301
    assert (
        client.post(endpoint, data={"raw_input": "https://shop.example.com/one"}).status_code == 200
    )
    assert len(recording_origin) == 3


@pytest.mark.timeout(120)
def test_cache_capacity_evicts_least_recently_used(
    preview_app: tuple[TestClient, str],
    recording_origin: list[tuple[httpx.AsyncHTTPTransport, httpx.Request]],
) -> None:
    """The 256-entry cache retains a refreshed item and evicts the least recent."""
    client, endpoint = preview_app

    def submit(index: int) -> None:
        response = client.post(endpoint, data={"raw_input": f"https://shop.example.com/p{index}"})
        assert response.status_code == 200

    for index in range(256):
        submit(index)
    submit(0)
    submit(256)
    submit(0)
    submit(1)
    assert len(recording_origin) == 258


@pytest.mark.parametrize("path", ["/private", "/vary", "/cookie", "/expired", "/p?color=red"])
def test_nonshareable_responses_are_not_cached(
    path: str,
    preview_app: tuple[TestClient, str],
    recording_origin: list[tuple[httpx.AsyncHTTPTransport, httpx.Request]],
) -> None:
    """Private, cookie-bearing, varied, stale and query responses are never shared."""
    client, endpoint = preview_app
    for _ in range(2):
        assert (
            client.post(endpoint, data={"raw_input": f"https://shop.example.com{path}"}).status_code
            == 200
        )
    assert len(recording_origin) == 2
    assert all("cookie" not in request.headers for _, request in recording_origin)


def test_distinct_queries_are_fetched_separately(
    preview_app: tuple[TestClient, str],
    recording_origin: list[tuple[httpx.AsyncHTTPTransport, httpx.Request]],
) -> None:
    client, endpoint = preview_app
    for color in ("red", "blue"):
        response = client.post(
            endpoint, data={"raw_input": f"https://shop.example.com/product?color={color}"}
        )
        assert response.status_code == 200
    assert len(recording_origin) == 2
    assert recording_origin[0][1].url.params["color"] == "red"
    assert recording_origin[1][1].url.params["color"] == "blue"


def test_dns_is_revalidated_before_reuse(
    preview_app: tuple[TestClient, str],
    recording_origin: list[tuple[httpx.AsyncHTTPTransport, httpx.Request]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A formerly public destination cannot be served when DNS becomes private."""
    client, endpoint = preview_app
    url = "https://shop.example.com/product"
    assert "Product" in client.post(endpoint, data={"raw_input": url}).text

    async def blocked(host: str, port: int = 80) -> list[str]:
        raise SSRFBlockedError("private", host=host, ip_address="127.0.0.1", reason="forbidden_ip")

    monkeypatch.setattr("wishenka.items.fetcher.resolve_and_validate_host", blocked)
    monkeypatch.setattr("wishenka.items.ssrf.resolve_and_validate_host", blocked)
    response = client.post(endpoint, data={"raw_input": url})
    assert response.status_code == 200
    assert "Product" not in response.text
    assert len(recording_origin) == 1


def test_plain_text_does_not_fetch(
    preview_app: tuple[TestClient, str],
    recording_origin: list[tuple[httpx.AsyncHTTPTransport, httpx.Request]],
) -> None:
    client, endpoint = preview_app
    response = client.post(endpoint, data={"raw_input": "A plain gift"})
    assert response.status_code == 200
    assert not recording_origin


def test_concurrent_responses_do_not_share_cookies(
    preview_app: tuple[TestClient, str],
    recording_origin: list[tuple[httpx.AsyncHTTPTransport, httpx.Request]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An origin cookie is never sent on another simultaneously submitted request."""
    client, endpoint = preview_app
    respond = httpx.AsyncHTTPTransport.handle_async_request
    arrived = 0
    both_arrived = asyncio.Event()

    async def concurrent(
        transport: httpx.AsyncHTTPTransport, request: httpx.Request
    ) -> httpx.Response:
        nonlocal arrived
        arrived += 1
        if arrived == 2:
            both_arrived.set()
        await asyncio.wait_for(both_arrived.wait(), timeout=5)
        return await respond(transport, request)

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", concurrent)

    def submit(path: str) -> int:
        return int(
            client.post(endpoint, data={"raw_input": f"https://shop.example.com{path}"}).status_code
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, ("/private", "/other")))
    assert results == [200, 200]
    assert len(recording_origin) == 2
    assert all("cookie" not in request.headers for _, request in recording_origin)


def test_residual_text_is_not_shared_between_callers(
    preview_app: tuple[TestClient, str],
    recording_origin: list[tuple[httpx.AsyncHTTPTransport, httpx.Request]],
) -> None:
    client, endpoint = preview_app
    url = "https://shop.example.com/untitled"
    first = client.post(endpoint, data={"raw_input": f"{url} Alice gift"})
    app = cast(FastAPI, client.app)
    owner = AuthenticatedUser(telegram_id=102, first_name="Bob", auth_method="session_token")
    wishlist = asyncio.run(app.state.domain_service.create_wishlist(owner=owner, title="Bob"))
    token = SessionTokenService("preview-resource-test-secret").create_token(102, "Bob")
    client.headers["Authorization"] = f"Bearer {token}"
    second = client.post(
        f"/web/wishlists/{wishlist.id}/items/preview", data={"raw_input": f"{url} Bob gift"}
    )
    assert "Alice gift" in first.text
    assert "Bob gift" in second.text
    assert "Alice gift" not in second.text
    assert len(recording_origin) == 1


def test_lifespan_closes_single_outbound_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The application owns and closes its direct transport exactly once."""
    from wishenka.items.ssrf import SSRFSafeTransport

    closed: list[SSRFSafeTransport] = []
    original_close = SSRFSafeTransport.aclose

    async def close(transport: SSRFSafeTransport) -> None:
        closed.append(transport)
        await original_close(transport)

    monkeypatch.setattr(SSRFSafeTransport, "aclose", close)
    app = create_app(
        Settings(
            database_url=f"sqlite+aiosqlite:///{tmp_path / 'lifecycle.db'}",
            secret_key="preview-resource-test-secret",
            background_cleanup_enabled=False,
        )
    )
    with TestClient(app):
        route = app.state.item_preview_service.routes.default
        assert not closed
    assert closed == [route.transport]


def test_lifespan_closes_outbound_client_on_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from wishenka.items.ssrf import SSRFSafeTransport

    closed: list[SSRFSafeTransport] = []
    original_close = SSRFSafeTransport.aclose

    async def close(transport: SSRFSafeTransport) -> None:
        closed.append(transport)
        await original_close(transport)

    monkeypatch.setattr(SSRFSafeTransport, "aclose", close)
    app = create_app(
        Settings(
            database_url=f"sqlite+aiosqlite:///{tmp_path / 'exception.db'}",
            secret_key="preview-resource-test-secret",
            background_cleanup_enabled=False,
        )
    )
    with pytest.raises(RuntimeError, match="test failure"), TestClient(app):
        route = app.state.item_preview_service.routes.default
        raise RuntimeError("test failure")
    assert closed == [route.transport]


def test_application_instances_do_not_share_resources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from wishenka.items.ssrf import SSRFSafeTransport

    closed: list[SSRFSafeTransport] = []
    original_close = SSRFSafeTransport.aclose

    async def close(transport: SSRFSafeTransport) -> None:
        closed.append(transport)
        await original_close(transport)

    monkeypatch.setattr(SSRFSafeTransport, "aclose", close)
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'instances.db'}",
        secret_key="preview-resource-test-secret",
        background_cleanup_enabled=False,
    )
    app1, app2 = create_app(settings), create_app(settings)
    with TestClient(app1), TestClient(app2):
        first = app1.state.item_preview_service.routes.default.transport
        second = app2.state.item_preview_service.routes.default.transport
        assert first is not second
        assert not closed
    assert len(closed) == 2 and set(closed) == {first, second}


def test_failed_startup_closes_any_created_outbound_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from wishenka.items.ssrf import SSRFSafeTransport

    closed: list[SSRFSafeTransport] = []
    original_close = SSRFSafeTransport.aclose

    async def close(transport: SSRFSafeTransport) -> None:
        closed.append(transport)
        await original_close(transport)

    async def fail_startup() -> None:
        raise RuntimeError("startup failed")

    monkeypatch.setattr(SSRFSafeTransport, "aclose", close)
    app = create_app(
        Settings(
            database_url=f"sqlite+aiosqlite:///{tmp_path / 'startup.db'}",
            secret_key="preview-resource-test-secret",
            background_cleanup_enabled=False,
        )
    )
    monkeypatch.setattr(app.state.wishlist_store, "initialize", fail_startup)
    with pytest.raises(RuntimeError, match="startup failed"), TestClient(app):
        pass
    assert len(closed) == 1


def test_cache_construction_failure_closes_owned_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failure immediately after transport creation still releases that transport."""
    from wishenka.items.ssrf import SSRFSafeTransport

    closed: list[SSRFSafeTransport] = []
    original_close = SSRFSafeTransport.aclose

    async def close(transport: SSRFSafeTransport) -> None:
        closed.append(transport)
        await original_close(transport)

    def fail_cache() -> None:
        raise RuntimeError("cache initialization failed")

    monkeypatch.setattr(SSRFSafeTransport, "aclose", close)
    monkeypatch.setattr("wishenka.web.app.PreviewCache", fail_cache)
    app = create_app(
        Settings(
            database_url=f"sqlite+aiosqlite:///{tmp_path / 'startup-cache.db'}",
            secret_key="preview-resource-test-secret",
            background_cleanup_enabled=False,
        )
    )
    with pytest.raises(RuntimeError, match="cache initialization failed"), TestClient(app):
        pass
    assert len(closed) == 1


@pytest.mark.parametrize("failure", ["http", "timeout", "oversized", "challenge"])
def test_failed_preview_retries_and_recovers(
    failure: str,
    preview_app: tuple[TestClient, str],
    recording_origin: list[tuple[httpx.AsyncHTTPTransport, httpx.Request]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed lookup remains editable and a later successful response is fetched."""
    client, endpoint = preview_app
    respond = httpx.AsyncHTTPTransport.handle_async_request
    attempts = 0

    async def flaky(transport: httpx.AsyncHTTPTransport, request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            if failure == "timeout":
                raise httpx.ReadTimeout("timeout", request=request)
            if failure == "http":
                return httpx.Response(503, request=request)
            if failure == "oversized":
                return httpx.Response(200, headers={"Content-Length": "2097153"}, request=request)
            return httpx.Response(200, text="checking your browser", request=request)
        return await respond(transport, request)

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", flaky)
    url = "https://shop.example.com/retry"
    first = client.post(endpoint, data={"raw_input": url})
    second = client.post(endpoint, data={"raw_input": url})
    assert first.status_code == second.status_code == 200
    assert "Product" not in first.text
    assert "Product" in second.text
    assert attempts == 2
    assert len(recording_origin) == 1


def test_unsafe_redirect_never_fetches_private_destination(
    preview_app: tuple[TestClient, str],
    recording_origin: list[tuple[httpx.AsyncHTTPTransport, httpx.Request]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, endpoint = preview_app
    respond = httpx.AsyncHTTPTransport.handle_async_request

    async def redirect(
        transport: httpx.AsyncHTTPTransport, request: httpx.Request
    ) -> httpx.Response:
        if request.url.path == "/redirect":
            return httpx.Response(
                302, headers={"Location": "http://127.0.0.1/private"}, request=request
            )
        return await respond(transport, request)

    async def resolve(host: str, port: int = 80) -> list[str]:
        if host == "127.0.0.1":
            raise SSRFBlockedError("private", host=host, ip_address=host, reason="forbidden_ip")
        return ["8.8.8.8"]

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", redirect)
    monkeypatch.setattr("wishenka.items.fetcher.resolve_and_validate_host", resolve)
    monkeypatch.setattr("wishenka.items.ssrf.resolve_and_validate_host", resolve)
    for _ in range(2):
        response = client.post(endpoint, data={"raw_input": "https://shop.example.com/redirect"})
        assert response.status_code == 200
        assert "Product" not in response.text
    assert not recording_origin


async def test_url_credentials_never_reach_origin(
    recording_origin: list[tuple[httpx.AsyncHTTPTransport, httpx.Request]],
) -> None:
    """Userinfo is rejected instead of sending Basic credentials to the origin."""
    result = await ItemPreviewService().fetch_preview(
        "https://alice:secret@shop.example.com/product"
    )
    assert result.is_fallback
    assert not recording_origin


def test_redirect_destinations_are_revalidated_before_cache_hit(
    preview_app: tuple[TestClient, str],
    recording_origin: list[tuple[httpx.AsyncHTTPTransport, httpx.Request]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, endpoint = preview_app
    respond = httpx.AsyncHTTPTransport.handle_async_request
    private = False
    redirects = 0

    async def origin(transport: httpx.AsyncHTTPTransport, request: httpx.Request) -> httpx.Response:
        nonlocal redirects
        if request.url.host == "shop.example.com":
            redirects += 1
            return httpx.Response(
                302,
                headers={"Location": "https://cdn.example.com/product", "Cache-Control": "public"},
                request=request,
            )
        return await respond(transport, request)

    async def resolve(host: str, port: int = 80) -> list[str]:
        if private and host == "cdn.example.com":
            raise SSRFBlockedError(
                "private", host=host, ip_address="127.0.0.1", reason="forbidden_ip"
            )
        return ["8.8.8.8"]

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", origin)
    monkeypatch.setattr("wishenka.items.fetcher.resolve_and_validate_host", resolve)
    monkeypatch.setattr("wishenka.items.ssrf.resolve_and_validate_host", resolve)
    url = "https://shop.example.com/redirected"
    assert "Product" in client.post(endpoint, data={"raw_input": url}).text
    private = True
    response = client.post(endpoint, data={"raw_input": url})
    assert response.status_code == 200
    assert "Product" not in response.text
    assert redirects == 1
    assert len(recording_origin) == 1


@pytest.mark.parametrize(
    ("control", "age", "expected"),
    [
        ("public, max-age=20", "15", 5),
        ("public, max-age=20, s-maxage=2", "0", 2),
        ("public, max-age=invalid", "0", 0),
    ],
)
def test_cache_respects_origin_freshness(
    control: str, age: str, expected: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Shared freshness does not exceed origin directives and response age."""
    from wishenka.items.models import ExtractedMetadata
    from wishenka.items.preview_cache import PreviewCache

    now = [100.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    cache = PreviewCache()
    url = "https://shop.example.com/item"
    cache.put(
        url,
        ExtractedMetadata(title="Product"),
        (
            (
                url,
                httpx.Headers(
                    {
                        "Cache-Control": control,
                        "Age": age,
                    }
                ),
            ),
        ),
    )
    assert (cache.get(url) is not None) == (expected > 0)
    now[0] += expected
    assert cache.get(url) is None


@pytest.mark.parametrize(
    ("header", "value"),
    [("Date", "Wed, 01 Jan 2020 00:00:00 GMT"), ("Expires", "Wed, 01 Jan 2020 00:00:00 GMT")],
)
def test_cache_rejects_ambiguous_origin_dates(header: str, value: str) -> None:
    """Origin dates cannot accidentally extend the freshness of stale responses."""
    from wishenka.items.models import ExtractedMetadata
    from wishenka.items.preview_cache import PreviewCache

    cache = PreviewCache()
    url = "https://shop.example.com/product"
    cache.put(
        url,
        ExtractedMetadata(title="Product"),
        ((url, httpx.Headers({"Cache-Control": "public, max-age=300", header: value})),),
    )
    assert cache.get(url) is None


def test_cache_honors_fresh_origin_dates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Valid Date and Expires permit caching only for the remaining freshness."""
    from wishenka.items.models import ExtractedMetadata
    from wishenka.items.preview_cache import PreviewCache

    monotonic = [10.0]
    monkeypatch.setattr(time, "time", lambda: 1577836810.0)
    monkeypatch.setattr(time, "monotonic", lambda: monotonic[0])
    cache = PreviewCache()
    url = "https://shop.example.com/product"
    cache.put(
        url,
        ExtractedMetadata(title="Product"),
        (
            (
                url,
                httpx.Headers(
                    {
                        "Cache-Control": "public, max-age=100",
                        "Date": "Wed, 01 Jan 2020 00:00:00 GMT",
                        "Expires": "Wed, 01 Jan 2020 00:00:20 GMT",
                    }
                ),
            ),
        ),
    )
    assert cache.get(url) is not None
    monotonic[0] += 10
    assert cache.get(url) is None


async def test_injected_client_remains_unchanged_after_preview(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An ambiguous client and routes fail closed; route-only calls remain supported."""
    from wishenka.items.fetcher import PreviewTransportConfig, offline_replay_route

    requests: list[httpx.Request] = []

    async def resolve(host: str, port: int = 80) -> list[str]:
        return ["8.8.8.8"]

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text="Owner", request=request)

    monkeypatch.setattr("wishenka.items.fetcher.resolve_and_validate_host", resolve)
    url = "https://shop.example.com/product"
    route = offline_replay_route(
        {url: (200, {"set-cookie": "preview=secret"}, b"<title>Product</title>")}
    )
    config = PreviewTransportConfig(default=route, mounts={})
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(respond),
        headers={"Authorization": "Bearer owner"},
        cookies={"owner": "cookie"},
    ) as client:
        initial_hooks = list(client.event_hooks["request"])
        preview = await ItemPreviewService().fetch_preview(url, client=client, routes=config)
        assert preview.is_fallback and preview.fallback_reason == "ssrf_blocked"
        safe_preview = await ItemPreviewService().fetch_preview(url, routes=config)
        assert not safe_preview.is_fallback and safe_preview.title == "Product"
        assert requests == []
        assert list(client.event_hooks["request"]) == initial_hooks
        assert client.cookies.get("preview") is None
        assert (await client.get("https://shop.example.com/owner")).status_code == 200
        assert requests[0].headers["authorization"] == "Bearer owner"
        assert "owner=cookie" in requests[0].headers["cookie"]


async def test_preview_ignores_injected_client_proxy_mount(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unverified proxy clients fail closed and the owner's route remains usable."""
    proxied: list[str] = []

    async def resolve(host: str, port: int = 80) -> list[str]:
        return ["8.8.8.8"]

    async def send_proxy(request: httpx.Request) -> httpx.Response:
        proxied.append(str(request.url))
        return httpx.Response(200, text="Owner", request=request)

    monkeypatch.setattr("wishenka.items.fetcher.resolve_and_validate_host", resolve)
    proxy = httpx.AsyncHTTPTransport(proxy="http://localhost:12345")
    monkeypatch.setattr(proxy, "handle_async_request", send_proxy)
    async with httpx.AsyncClient(transport=proxy, trust_env=False) as client:
        preview = await ItemPreviewService().fetch_preview(
            "https://shop.example.com/product", client=client
        )
        assert preview.is_fallback
        assert not proxied
        assert (await client.get("https://shop.example.com/owner")).text == "Owner"
        assert proxied == ["https://shop.example.com/owner"]


async def test_preview_rejects_injected_direct_proxy_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def resolve(host: str, port: int = 80) -> list[str]:
        return ["8.8.8.8"]

    monkeypatch.setattr("wishenka.items.fetcher.resolve_and_validate_host", resolve)
    transport = httpx.AsyncHTTPTransport(proxy="http://localhost:12345")
    async with httpx.AsyncClient(transport=transport) as client:
        preview = await ItemPreviewService().fetch_preview(
            "https://shop.example.com/product", client=client
        )
    assert preview.is_fallback
    assert preview.fallback_reason == "ssrf_blocked"


async def test_preview_uses_injected_safe_mount(monkeypatch: pytest.MonkeyPatch) -> None:
    """An explicit fixture mount is selected instead of a denied default route."""
    from wishenka.items.fetcher import PreviewTransportConfig, deny_route, offline_replay_route

    async def resolve(host: str, port: int = 80) -> list[str]:
        return ["8.8.8.8"]

    monkeypatch.setattr("wishenka.items.fetcher.resolve_and_validate_host", resolve)
    url = "https://shop.example.com/product"
    mounted = offline_replay_route({url: (200, {}, b"<title>Mounted</title>")})
    routes = PreviewTransportConfig(
        default=deny_route(), mounts={"https://shop.example.com": mounted}
    )
    result = await ItemPreviewService(routes=routes).fetch_preview(url)
    assert not result.is_fallback
    assert result.title == "Mounted"
