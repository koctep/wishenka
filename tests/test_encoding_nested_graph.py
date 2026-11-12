"""Offline regression cases for legacy encodings and bounded JSON-LD processing."""

import json
import logging
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

from wishenka.items.exceptions import ResponseBodyTooLargeError
from wishenka.items.fetcher import UrlMetadataService
from wishenka.items.parser import HtmlMetadataExtractor
from wishenka.items.service import ItemPreviewService

pytestmark = pytest.mark.timeout(30)

URL = "https://example.com/product"
TITLE = "Русская книга о природе и путешествиях"
DESCRIPTION = "Подробное описание товара для всей семьи"


def page(meta: str = "") -> str:
    return (
        f"<html><head>{meta}<meta property='og:title' content='{TITLE}'>"
        f"<meta property='og:description' content='{DESCRIPTION}'></head></html>"
    )


async def preview_bytes(
    body: bytes,
    content_type: str,
    path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> Any:
    """Use real HTTPX responses and parsing without network access."""
    monkeypatch.setattr("wishenka.items.fetcher.resolve_and_validate_host", AsyncMock())
    response = httpx.Response(
        200,
        headers={"content-type": content_type},
        content=body,
        request=httpx.Request("GET", URL),
    )
    fetcher = UrlMetadataService()
    if path == "buffered":
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = response
        return await ItemPreviewService(url_metadata_service=fetcher).fetch_preview(
            URL, client=mock_client
        )
    transport = httpx.MockTransport(lambda request: response)
    async with httpx.AsyncClient(transport=transport, trust_env=False) as client:
        return await ItemPreviewService(url_metadata_service=fetcher, client=client).fetch_preview(
            URL
        )


@pytest.mark.parametrize("path", ["streaming", "buffered"])
@pytest.mark.parametrize(
    ("encoding", "content_type", "meta"),
    [
        ("cp1251", "text/html; charset=windows-1251", ""),
        ("cp1251", "text/html; charset=cp1251", ""),
        ("koi8-r", "text/html; charset=koi8-r", ""),
        ("cp1251", "text/html", "<meta charset='windows-1251'>"),
        (
            "koi8-r",
            "text/html",
            "<meta http-equiv='Content-Type' content='text/html; charset=koi8-r'>",
        ),
        ("cp1251", "text/html", ""),
        ("koi8-r", "text/html", ""),
        ("utf-8", "text/html; charset=cp1251", "<meta charset='koi8-r'>"),
        ("cp1251", "text/html; charset=unknown-encoding", "<meta charset='cp1251'>"),
        ("cp1251", "text/html; charset=cp1251", "<meta charset='koi8-r'>"),
    ],
)
async def test_legacy_and_conflicting_declarations(
    path: str,
    encoding: str,
    content_type: str,
    meta: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = await preview_bytes(page(meta).encode(encoding), content_type, path, monkeypatch)
    assert result.title == TITLE
    assert result.description == DESCRIPTION
    assert not result.is_fallback


@pytest.mark.parametrize("path", ["streaming", "buffered"])
async def test_bom_precedes_legacy_declarations(path: str, monkeypatch: pytest.MonkeyPatch) -> None:
    result = await preview_bytes(
        page("<meta charset='koi8-r'>").encode("utf-8-sig"),
        "text/html; charset=cp1251",
        path,
        monkeypatch,
    )
    assert result.title == TITLE
    assert result.description == DESCRIPTION


@pytest.mark.parametrize("path", ["streaming", "buffered"])
async def test_invalid_declarations_and_bytes_are_deterministic(
    path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = b"<html><head><meta charset='invalid@@'><title>Safe\xff</title></head></html>"
    first = await preview_bytes(data, "text/html; charset=invalid@@", path, monkeypatch)
    second = await preview_bytes(data, "text/html; charset=invalid@@", path, monkeypatch)
    assert first.title == second.title
    assert first.title is not None


@pytest.mark.parametrize("path", ["streaming", "buffered"])
@pytest.mark.parametrize("declaration", ["header", "meta"])
async def test_nul_in_charset_uses_next_valid_declaration(
    path: str, declaration: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    meta = "<meta charset='utf\x00-8'><meta charset='cp1251'>"
    content_type = "text/html"
    if declaration == "header":
        meta = "<meta charset='cp1251'>"
        content_type = "text/html; charset=utf\x00-8"
    result = await preview_bytes(page(meta).encode("cp1251"), content_type, path, monkeypatch)
    assert result.title == TITLE
    assert result.description == DESCRIPTION
    assert not result.is_fallback


@pytest.mark.parametrize("path", ["streaming", "buffered"])
async def test_size_limit_still_applies(path: str) -> None:
    fetcher = UrlMetadataService(max_bytes=16)
    response = httpx.Response(200, content=b"x" * 17, request=httpx.Request("GET", URL))
    if path == "buffered":
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = response
        with pytest.raises(ResponseBodyTooLargeError):
            await fetcher._fetch_via_get(mock_client, URL)
    else:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: response)
        ) as client:
            with pytest.raises(ResponseBodyTooLargeError):
                await fetcher._stream_and_read(client, URL)


def script(data: Any) -> str:
    return f'<script type="application/ld+json">{json.dumps(data, ensure_ascii=False)}</script>'


def test_nested_graph_offer_and_metadata_precedence() -> None:
    product = {
        "@type": ["Thing", "https://schema.org/Product"],
        "name": "Graph product",
        "description": "Graph details",
        "offers": {"@type": "AggregateOffer", "lowPrice": "1750", "priceCurrency": "RUB"},
    }
    graph = {"@graph": [{"@type": "WebSite"}, {"itemListElement": [[{"@graph": [product]}]]}]}
    html = (
        "<html><head><title>HTML title</title><meta property='og:title' content='OG title'>"
        + '<script type="application/ld+json">{broken</script>'
        + script(graph)
        + "</head><body><span itemprop='name'>Microdata title</span></body></html>"
    )
    result = HtmlMetadataExtractor.extract(html, URL)
    assert result.title == "Graph product"
    assert result.description == "Graph details"
    assert result.price == 1750
    assert result.currency == "RUB"


def test_graph_object_not_only_array() -> None:
    result = HtmlMetadataExtractor.extract(
        script({"@graph": {"@type": "Product", "name": "Object graph"}}), URL
    )
    assert result.title == "Object graph"


def test_deep_type_inspection_is_bounded() -> None:
    nested: Any = "Product"
    for _ in range(1500):
        nested = [nested]
    assert HtmlMetadataExtractor._is_product_type(nested) is False


def test_over_limit_type_does_not_hide_later_product() -> None:
    nested: Any = "Product"
    for _ in range(180):
        nested = [nested]
    html = script({"@type": nested, "name": "Too deeply nested"}) + script(
        {"@type": "Product", "name": "Later product"}
    )
    assert HtmlMetadataExtractor.extract(html, URL).title == "Later product"


def test_json_decode_recursion_failure_allows_html_fallback() -> None:
    deep = "[" * 15000 + "0" + "]" * 15000
    html = (
        f'<script type="application/ld+json">{deep}</script>'
        "<meta property='og:title' content='Safe fallback'>"
    )
    assert HtmlMetadataExtractor.extract(html, URL).title == "Safe fallback"


def test_deep_graph_allows_html_fallback() -> None:
    graph: Any = {"@type": "Product", "name": "Too deep"}
    for _ in range(180):
        graph = [graph]
    html = script(graph) + "<meta property='og:title' content='Safe fallback'>"
    assert HtmlMetadataExtractor.extract(html, URL).title == "Safe fallback"


def test_oversized_graph_stops_before_late_product_and_falls_back() -> None:
    nodes = [{"@type": "Thing"}] * 20010 + [{"@type": "Product", "name": "Too late"}]
    html = script({"@graph": nodes}) + "<meta property='og:title' content='Safe fallback'>"
    assert HtmlMetadataExtractor.extract(html, URL).title == "Safe fallback"


def test_bounded_and_malformed_jsonld_diagnostics_hide_page_content(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "private-page-marker"
    nested: Any = "Product"
    for _ in range(150):
        nested = [nested]
    html = (
        f'<script type="application/ld+json">{{broken {secret}</script>'
        + script({"@type": nested, "name": secret})
        + script([[[0]]] * 20001)
        + "<meta property='og:title' content='Safe fallback'>"
    )
    with caplog.at_level(logging.DEBUG, logger="wishenka.items"):
        result = HtmlMetadataExtractor.extract(html, URL)
    assert result.title == "Safe fallback"
    events = {getattr(record, "event", None) for record in caplog.records}
    assert {"jsonld_parse_skipped", "jsonld_type_limit", "jsonld_discovery_limit"} <= events
    assert all(secret not in record.getMessage() for record in caplog.records)
