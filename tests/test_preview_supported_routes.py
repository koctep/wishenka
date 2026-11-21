"""Offline repros for the supported preview-route trust boundary."""

import asyncio
import logging
from pathlib import Path
from typing import Any

import httpx
import pytest

from wishenka.items.fetcher import PreviewTransportConfig, deny_route
from wishenka.items.service import ItemPreviewService

pytestmark = pytest.mark.timeout(30)


def test_cassette_replay_does_not_modify_global_dns_cache() -> None:
    """Loading fixtures must not replace the address used for real connections."""
    from wishenka.items.cassettes import Cassette, CassetteMode, CassetteTransport
    from wishenka.items.ssrf import _dns_cache, clear_dns_cache

    path = Path(__file__).parent / "cassettes" / "marketplaces" / "ozon_product.yaml"
    cassette = Cassette.load(path)
    url = httpx.URL(cassette.interactions[0].request.uri)
    port = url.port or 443
    clear_dns_cache()
    try:
        _dns_cache.put(url.host, port, ["8.8.8.8"])
        CassetteTransport(cassette, mode=CassetteMode.REPLAY)
        assert _dns_cache.get(url.host, port) == ["8.8.8.8"]
    finally:
        clear_dns_cache()


@pytest.mark.asyncio
async def test_cassette_record_does_not_modify_global_dns_cache() -> None:
    """Recording an interaction cannot replace the address used by live connections."""
    from wishenka.items.cassettes import Cassette, CassetteMode, CassetteTransport
    from wishenka.items.ssrf import _dns_cache, clear_dns_cache

    async def record_response(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="test", request=request)

    clear_dns_cache()
    try:
        _dns_cache.put("shop.example", 443, ["8.8.8.8"])
        transport = CassetteTransport(
            Cassette(),
            mode=CassetteMode.RECORD,
            inner_transport=httpx.MockTransport(record_response),
        )
        await transport.handle_async_request(httpx.Request("GET", "https://shop.example/item"))
        assert _dns_cache.get("shop.example", 443) == ["8.8.8.8"]
    finally:
        clear_dns_cache()


@pytest.fixture
def public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep URL validation deterministic without making DNS or network requests."""

    async def resolve(host: str, port: int = 80) -> list[str]:
        return ["8.8.8.8"]

    monkeypatch.setattr("wishenka.items.fetcher.resolve_and_validate_host", resolve)


@pytest.mark.asyncio
@pytest.mark.parametrize("route_reason", ["unknown_route", "route_denied"])
async def test_route_rejection_logs_reason_without_private_url_data(
    public_dns: None, caplog: pytest.LogCaptureFixture, route_reason: str
) -> None:
    """The rejection event identifies its cause without logging paths or query secrets."""
    secret = "private-route-secret"
    url = f"https://shop.example/{secret}?token={secret}"
    async with httpx.AsyncClient() as owner:
        service = (
            ItemPreviewService(client=owner)
            if route_reason == "unknown_route"
            else ItemPreviewService(routes=PreviewTransportConfig(default=deny_route(), mounts={}))
        )
        with caplog.at_level(logging.DEBUG, logger="wishenka.items"):
            preview = await service.fetch_preview(url)

    assert preview.is_fallback and preview.fallback_reason == "ssrf_blocked"
    records = [
        r for r in caplog.records if getattr(r, "event", None) == "item_preview_route_rejected"
    ]
    assert len(records) == 1
    assert records[0].__dict__["reason"] == route_reason
    assert records[0].__dict__["fallback_reason"] == "ssrf_blocked"
    assert secret not in str(records[0].__dict__)


@pytest.mark.asyncio
async def test_opaque_client_is_rejected_without_dispatch_or_ownership_transfer(
    public_dns: None,
) -> None:
    """An unverifiable caller route must fail closed while its owner retains the client."""
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text="<title>Untrusted</title>", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as owner:
        preview = await ItemPreviewService(client=owner).fetch_preview("https://shop.example/item")

        assert preview.is_fallback
        assert requests == []
        assert not owner.is_closed
        owner_response = await owner.get("https://owner.example/health")
        assert owner_response.status_code == 200
        assert len(requests) == 1


@pytest.mark.asyncio
async def test_proxy_mount_is_not_bypassed_by_direct_default(public_dns: None) -> None:
    """A selected proxy route cannot silently fall back to the caller's default transport."""
    direct_requests: list[httpx.Request] = []

    async def direct_handler(request: httpx.Request) -> httpx.Response:
        direct_requests.append(request)
        return httpx.Response(200, text="<title>Bypassed proxy</title>", request=request)

    direct = httpx.MockTransport(direct_handler)
    proxy = httpx.AsyncHTTPTransport(proxy="http://proxy.example:8080")
    async with httpx.AsyncClient(
        transport=direct, mounts={"all://shop.example": proxy}, trust_env=False
    ) as owner:
        preview = await ItemPreviewService(client=owner).fetch_preview("https://shop.example/item")

        assert preview.is_fallback
        assert direct_requests == []
        assert not owner.is_closed


@pytest.mark.asyncio
@pytest.mark.parametrize("client_on_service", [False, True])
async def test_opaque_client_cannot_be_silently_replaced_by_routes(
    public_dns: None, monkeypatch: pytest.MonkeyPatch, client_on_service: bool
) -> None:
    """A supplied client and independently configured routes are ambiguous, so deny both."""
    url = "https://shop.example/item"
    routes, _, transport = _controlled_routes({url: (200, {}, b"<title>Bypass</title>")}, {})
    calls: list[str] = []
    original = type(transport).handle_async_request

    async def observe(route: httpx.AsyncBaseTransport, request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return await original(route, request)

    monkeypatch.setattr(type(transport), "handle_async_request", observe)
    proxy = httpx.AsyncHTTPTransport(proxy="http://proxy.example:8080")
    async with httpx.AsyncClient(mounts={"all://shop.example": proxy}) as owner:
        if client_on_service:
            result = await ItemPreviewService(client=owner).fetch_preview(url, routes=routes)
        else:
            result = await ItemPreviewService(routes=routes).fetch_preview(url, client=owner)
        assert result.is_fallback and result.fallback_reason == "ssrf_blocked"
        assert calls == []
        assert not owner.is_closed


@pytest.mark.asyncio
async def test_concurrent_opaque_clients_never_dispatch_or_close_owner(public_dns: None) -> None:
    """Concurrent unsupported previews cannot send requests through caller-provided routes."""
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text="<title>Untrusted</title>", request=request)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), headers={"Authorization": "Bearer owner"}
    ) as owner:
        service = ItemPreviewService(client=owner)
        previews = await asyncio.gather(
            service.fetch_preview("https://shop.example/one"),
            service.fetch_preview("https://shop.example/two"),
        )
        assert all(preview.is_fallback for preview in previews)
        assert requests == []
        assert not owner.is_closed
        assert owner.headers["Authorization"] == "Bearer owner"


def _controlled_routes(
    default_responses: dict[str, tuple[int, dict[str, str], bytes]],
    mounted_responses: dict[str, tuple[int, dict[str, str], bytes]],
) -> tuple[PreviewTransportConfig, httpx.AsyncBaseTransport, httpx.AsyncBaseTransport]:
    """Build the proposed public fixture-only route contract without importing missing APIs."""
    from wishenka.items import fetcher

    config_type = getattr(fetcher, "PreviewTransportConfig", None)
    replay = getattr(fetcher, "offline_replay_route", None)
    deny = getattr(fetcher, "deny_route", None)
    assert callable(config_type), "public PreviewTransportConfig route contract is missing"
    assert callable(replay), "controlled fixture-only replay factory is missing"
    assert callable(deny), "explicit deny-route factory is missing"
    default_route = replay(default_responses)
    mounted_route = replay(mounted_responses)
    default_transport = getattr(default_route, "transport", None)
    mounted_transport = getattr(mounted_route, "transport", None)
    assert isinstance(default_transport, httpx.AsyncBaseTransport)
    assert isinstance(mounted_transport, httpx.AsyncBaseTransport)
    config = config_type(
        default=default_route,
        mounts={"all://shop.example": mounted_route, "all://denied.example": deny()},
    )
    return config, default_transport, mounted_transport


async def _assert_borrowed_transport_usable(
    transport: httpx.AsyncBaseTransport, url: str, expected_status: int
) -> None:
    response = await transport.handle_async_request(httpx.Request("GET", url))
    try:
        assert response.status_code == expected_status
        await response.aread()
    finally:
        await response.aclose()


@pytest.mark.asyncio
async def test_supported_mounted_replay_selects_specific_route_and_preserves_owner(
    public_dns: None,
) -> None:
    """The safe specific mount wins, and closing preview resources leaves the owner usable."""
    url = "https://shop.example/item"
    routes, _, borrowed = _controlled_routes(
        {url: (200, {}, b"<title>Wrong default</title>")},
        {url: (200, {}, b"<title>Mounted product</title>")},
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, request=request))
    ) as owner:
        result = await ItemPreviewService().fetch_preview(url, routes=routes)
        assert not result.is_fallback
        assert result.title == "Mounted product"
        await _assert_borrowed_transport_usable(borrowed, url, 200)
        assert not owner.is_closed
        assert (await owner.get("https://owner.example/health")).status_code == 200


@pytest.mark.asyncio
async def test_supported_redirect_into_denied_mount_fails_closed(
    public_dns: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An explicit deny mount wins on redirect even if the default has a response."""
    initial = "https://shop.example/item"
    forbidden = "https://denied.example/private"
    routes, default_transport, borrowed = _controlled_routes(
        {forbidden: (200, {}, b"<title>Must not reach default</title>")},
        {initial: (302, {"location": forbidden}, b"")},
    )
    seen: list[str] = []
    transport_type = type(default_transport)
    original_handle = transport_type.handle_async_request

    async def observe_dispatch(
        transport: httpx.AsyncBaseTransport, request: httpx.Request
    ) -> httpx.Response:
        seen.append(str(request.url))
        return await original_handle(transport, request)

    monkeypatch.setattr(transport_type, "handle_async_request", observe_dispatch)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, request=request))
    ) as owner:
        result = await ItemPreviewService().fetch_preview(initial, routes=routes)
        assert result.is_fallback
        assert initial in seen
        assert forbidden not in seen
        assert result.title != "Must not reach default"
        await _assert_borrowed_transport_usable(borrowed, initial, 302)
        assert not owner.is_closed
        assert (await owner.get("https://owner.example/health")).status_code == 200


@pytest.mark.asyncio
async def test_supported_concurrent_previews_isolate_owner_and_response_state(
    public_dns: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Concurrent requests omit caller state and cannot carry replay cookies between hops."""
    responses = {
        "https://shop.example/one": (
            302,
            {"location": "/one-final", "set-cookie": "leak=one"},
            b"",
        ),
        "https://shop.example/two": (
            302,
            {"location": "/two-final", "set-cookie": "leak=two"},
            b"",
        ),
        "https://shop.example/one-final": (200, {}, b"<title>One</title>"),
        "https://shop.example/two-final": (200, {}, b"<title>Two</title>"),
    }
    routes, _, _ = _controlled_routes({}, responses)
    seen: list[httpx.Request] = []
    original_init = httpx.AsyncClient.__init__

    async def observe_request(request: httpx.Request) -> None:
        if request.url.host == "shop.example":
            seen.append(request)

    def instrument_client(client: httpx.AsyncClient, **kwargs: Any) -> None:
        existing_hooks = kwargs.get("event_hooks") or {}
        hooks = {name: list(callbacks) for name, callbacks in existing_hooks.items()}
        hooks.setdefault("request", []).append(observe_request)
        kwargs["event_hooks"] = hooks
        original_init(client, **kwargs)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, request=request)),
        headers={"Authorization": "Bearer owner", "X-Owner-Secret": "secret"},
        cookies={"owner": "secret"},
    ) as owner:
        monkeypatch.setattr(httpx.AsyncClient, "__init__", instrument_client)
        service = ItemPreviewService()
        one, two = await asyncio.gather(
            service.fetch_preview("https://shop.example/one", routes=routes),
            service.fetch_preview("https://shop.example/two", routes=routes),
        )
        assert (one.title, two.title) == ("One", "Two")
        assert len(seen) == 4
        for request in seen:
            assert "authorization" not in request.headers
            assert "x-owner-secret" not in request.headers
            assert "cookie" not in request.headers
        assert owner.cookies.get("owner") == "secret"
        assert not owner.is_closed
        assert (await owner.get("https://owner.example/health")).status_code == 200


@pytest.mark.asyncio
async def test_cancelled_supported_preview_does_not_close_owner(
    public_dns: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cancellation releases preview-owned resources without closing the caller's client."""
    url = "https://shop.example/item"
    routes, _, borrowed = _controlled_routes({}, {url: (200, {}, b"<title>Item</title>")})
    entered = asyncio.Event()
    release = asyncio.Event()
    close_calls: list[httpx.AsyncBaseTransport] = []
    transport_type = type(borrowed)
    original_handle = transport_type.handle_async_request
    original_close = transport_type.aclose

    async def block_borrowed(
        transport: httpx.AsyncBaseTransport, request: httpx.Request
    ) -> httpx.Response:
        if transport is borrowed and str(request.url) == url:
            entered.set()
            await asyncio.wait_for(release.wait(), timeout=5)
        return await original_handle(transport, request)

    async def observe_close(transport: httpx.AsyncBaseTransport) -> None:
        close_calls.append(transport)
        await original_close(transport)

    monkeypatch.setattr(transport_type, "handle_async_request", block_borrowed)
    monkeypatch.setattr(transport_type, "aclose", observe_close)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, request=request))
    ) as owner:
        task = asyncio.create_task(ItemPreviewService().fetch_preview(url, routes=routes))
        try:
            await asyncio.wait_for(entered.wait(), timeout=5)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            release.set()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        assert borrowed not in close_calls
        await _assert_borrowed_transport_usable(borrowed, url, 200)
        assert not owner.is_closed
        assert (await owner.get("https://owner.example/health")).status_code == 200


def test_config_rejects_untrusted_transports_and_snapshots_mounts() -> None:
    """Opaque transports cannot be registered and caller mapping changes have no effect."""
    from wishenka.items.fetcher import PreviewRoute, PreviewTransportConfig, deny_route

    opaque = httpx.MockTransport(lambda request: httpx.Response(200, request=request))
    with pytest.raises(ValueError, match="Unapproved"):
        PreviewTransportConfig(default=PreviewRoute(opaque, object()), mounts={})
    mounts = {"all://shop.example": deny_route()}
    config = PreviewTransportConfig(default=deny_route(), mounts=mounts)
    identity = config.cache_identity
    mounts.clear()
    assert "all://shop.example" in config.mounts
    assert config.cache_identity == identity
    with pytest.raises(TypeError):
        config.mounts["all://evil.example"] = deny_route()  # type: ignore[index]


@pytest.mark.asyncio
async def test_factory_route_cannot_authorize_substituted_transport() -> None:
    """Copying a route's marker cannot approve a different direct transport."""
    from wishenka.items.fetcher import PreviewRoute, safe_direct_route
    from wishenka.items.ssrf import SSRFSafeTransport

    approved = safe_direct_route()
    replacement = SSRFSafeTransport()
    try:
        forged = PreviewRoute(replacement, approved._token)
        with pytest.raises(ValueError, match="Unapproved"):
            PreviewTransportConfig(default=forged, mounts={})
        with pytest.raises(RuntimeError, match="SSRF-safe"):
            SSRFSafeTransport(proxy="http://8.8.8.8:8080")
    finally:
        await approved.transport.aclose()
        await replacement.aclose()


@pytest.mark.asyncio
async def test_offline_replay_miss_never_delegates(public_dns: None) -> None:
    """Unknown fixture URLs fail closed rather than using a network transport."""
    from wishenka.items.exceptions import CassetteMissError
    from wishenka.items.fetcher import PreviewTransportConfig, offline_replay_route

    route = offline_replay_route({})
    config = PreviewTransportConfig(default=route, mounts={})
    with pytest.raises(CassetteMissError):
        await ItemPreviewService(routes=config).fetch_preview("https://shop.example/item")


@pytest.mark.asyncio
async def test_shared_cache_is_partitioned_by_explicit_route_config(public_dns: None) -> None:
    """Separate services sharing a cache cannot exchange results across routes."""
    from wishenka.items.fetcher import PreviewTransportConfig, offline_replay_route
    from wishenka.items.preview_cache import PreviewCache

    url = "https://shop.example/item"
    cache = PreviewCache()
    first_route = offline_replay_route(
        {url: (200, {"cache-control": "public, max-age=60"}, b"<title>First</title>")}
    )
    second_route = offline_replay_route(
        {url: (200, {"cache-control": "public, max-age=60"}, b"<title>Second</title>")}
    )
    first = ItemPreviewService(
        routes=PreviewTransportConfig(default=first_route, mounts={}), cache=cache
    )
    second = ItemPreviewService(
        routes=PreviewTransportConfig(default=second_route, mounts={}), cache=cache
    )
    assert (await first.fetch_preview(url)).title == "First"
    assert (await first.fetch_preview(url)).title == "First"
    assert (await second.fetch_preview(url)).title == "Second"
    assert len(cache.entries) == 2
