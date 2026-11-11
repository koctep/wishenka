"""Automated red repro tests for WISHENKA-12.

Validates:
1. JSON-LD `@graph` hierarchy extraction and `AggregateOffer` (lowPrice, highPrice,
   priceCurrency, ImageObject).
2. Marketplace registry & rules (`wishenka.items.marketplaces`): domain aliasing
   (Ozon, Wildberries, Yandex Market, Avito, Megamarket), tracking parameter stripping
   (`utm_*`, `from=share`), brand title cleaning.
3. Price and currency normalization across localized marketplace formats
   (`от 15 990 ₽`, `12 500,50 руб.`, `kzt`, `eur`, `usd`).
4. Anti-bot challenge detection (Cloudflare Turnstile, Qrator challenge pages)
   resulting in graceful fallback `ItemPreviewDTO(is_fallback=True, fallback_reason=...)`.
"""

import logging
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from wishenka.items import marketplaces
from wishenka.items.marketplaces import MarketplaceRegistry, clean_url
from wishenka.items.parser import (
    HtmlMetadataExtractor,
    clean_title,
    derive_store_name,
    normalize_currency,
    parse_price,
)
from wishenka.items.service import ItemPreviewService

pytestmark = pytest.mark.timeout(30)


class TestJsonLdGraphAndAggregateOffers:
    """Test JSON-LD `@graph` array traversal, namespaced types, and AggregateOffers."""

    def test_jsonld_graph_schema_org_uri_and_aggregate_offer_low_price(self) -> None:
        """JSON-LD `@graph` with Schema.org URI and AggregateOffer extracts lowPrice & Image."""
        html = """
        <!DOCTYPE html>
        <html>
        <head>
          <script type="application/ld+json">
          {
            "@context": "https://schema.org",
            "@graph": [
              {
                "@type": "WebSite",
                "name": "Мегамаркет",
                "url": "https://megamarket.ru"
              },
              {
                "@type": "https://schema.org/Product",
                "name": "Телевизор 55 4K Ultra HD",
                "description": "Smart TV с поддержкой HDR",
                "image": {
                  "@type": "ImageObject",
                  "contentUrl": "https://cdn.example.com/tv55.jpg"
                },
                "offers": {
                  "@type": "AggregateOffer",
                  "lowPrice": "49990",
                  "highPrice": "59990",
                  "priceCurrency": "RUB"
                }
              }
            ]
          }
          </script>
        </head>
        <body></body>
        </html>
        """
        extracted = HtmlMetadataExtractor.extract(html, "https://megamarket.ru/catalog/item-123/")

        assert extracted.title == "Телевизор 55 4K Ultra HD"
        assert extracted.description == "Smart TV с поддержкой HDR"
        assert extracted.price == 49990
        assert extracted.currency == "RUB"
        assert extracted.image_url == "https://cdn.example.com/tv55.jpg"

    def test_jsonld_aggregate_offer_high_price_fallback(self) -> None:
        """When lowPrice is missing in AggregateOffer, fallback to highPrice."""
        html = """
        <!DOCTYPE html>
        <html>
        <head>
          <script type="application/ld+json">
          {
            "@context": "http://schema.org",
            "@type": "Product",
            "name": "Смарт-часы",
            "offers": {
              "@type": "AggregateOffer",
              "highPrice": "15990",
              "priceCurrency": "RUB"
            }
          }
          </script>
        </head>
        <body></body>
        </html>
        """
        extracted = HtmlMetadataExtractor.extract(html, "https://example.com/watch")
        assert extracted.title == "Смарт-часы"
        assert extracted.price == 15990
        assert extracted.currency == "RUB"

    def test_jsonld_image_object_list(self) -> None:
        """When JSON-LD image is a list of ImageObjects, extract the first contentUrl/url."""
        html = """
        <!DOCTYPE html>
        <html>
        <head>
          <script type="application/ld+json">
          {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": "Наушники Bluetooth",
            "image": [
              {"@type": "ImageObject", "url": "https://cdn.example.com/headphones_main.jpg"},
              {"@type": "ImageObject", "url": "https://cdn.example.com/headphones_side.jpg"}
            ],
            "offers": {
              "@type": "Offer",
              "price": "3490",
              "priceCurrency": "RUB"
            }
          }
          </script>
        </head>
        <body></body>
        </html>
        """
        extracted = HtmlMetadataExtractor.extract(html, "https://example.com/headphones")
        assert extracted.image_url == "https://cdn.example.com/headphones_main.jpg"
        assert extracted.price == 3490

    def test_jsonld_relative_image_resolved_against_base_url(self) -> None:
        """Relative image path in JSON-LD must be resolved using base_url."""
        html = """
        <!DOCTYPE html>
        <html>
        <head>
          <script type="application/ld+json">
          {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": "Книга о дизайне",
            "image": "/images/book_cover.jpg",
            "offers": {
              "@type": "Offer",
              "price": "990",
              "priceCurrency": "RUB"
            }
          }
          </script>
        </head>
        <body></body>
        </html>
        """
        extracted = HtmlMetadataExtractor.extract(html, "https://bookstore.ru/catalog/123/")
        assert extracted.image_url == "https://bookstore.ru/images/book_cover.jpg"


class TestMarketplaceRegistryAndRules:
    """Test marketplace rules, domain aliasing, tracking param stripping, and title cleaning."""

    def test_marketplace_module_and_rule_classes_exist(self) -> None:
        """Marketplace registry module and rule classes must exist."""
        assert marketplaces is not None, "wishenka.items.marketplaces module must be implemented"
        assert hasattr(marketplaces, "MarketplaceRegistry")
        assert hasattr(marketplaces, "MarketplaceRule")
        assert hasattr(marketplaces, "OzonRule")
        assert hasattr(marketplaces, "WildberriesRule")
        assert hasattr(marketplaces, "YandexMarketRule")
        assert hasattr(marketplaces, "AvitoRule")
        assert hasattr(marketplaces, "MegamarketRule")
        assert hasattr(marketplaces, "clean_url")

    @pytest.mark.parametrize(
        ("url", "expected_store"),
        [
            ("https://wb.ru/catalog/12345/detail.aspx", "Wildberries"),
            ("https://wildberries.ru/catalog/12345/detail.aspx", "Wildberries"),
            ("https://ozon.kz/product/item-456/", "Ozon"),
            ("https://ozon.by/product/item-789/", "Ozon"),
            ("https://ozon.ru/product/item-101/", "Ozon"),
            ("https://m.avito.ru/moskva/tovary/123", "Авито"),
            ("https://avito.ru/moskva/tovary/123", "Авито"),
            ("https://sbermegamarket.ru/catalog/item-555/", "Мегамаркет"),
            ("https://megamarket.ru/catalog/item-999/", "Мегамаркет"),
            ("https://market.yandex.ru/product--item/111", "Яндекс Маркет"),
        ],
    )
    def test_marketplace_domain_aliasing(self, url: str, expected_store: str) -> None:
        """Domain aliases for Ozon, WB, Avito, Megamarket must resolve to store names."""
        derived = derive_store_name(url)
        assert derived == expected_store

    @pytest.mark.parametrize(
        ("raw_url", "expected_clean_url"),
        [
            (
                "https://ozon.ru/product/item-123/?from=share_android&utm_source=tg",
                "https://ozon.ru/product/item-123/",
            ),
            (
                "https://www.wildberries.ru/catalog/12345/detail.aspx"
                "?utm_campaign=winter_sale&targetUrl=SP",
                "https://www.wildberries.ru/catalog/12345/detail.aspx",
            ),
            (
                "https://market.yandex.ru/product/789?clid=123&utm_medium=cpc",
                "https://market.yandex.ru/product/789",
            ),
            (
                "https://m.avito.ru/moskva/123?utm_source=avito&src=share",
                "https://m.avito.ru/moskva/123",
            ),
            (
                "https://megamarket.ru/item-999?utm_content=banner&promo=yes",
                "https://megamarket.ru/item-999",
            ),
        ],
    )
    def test_marketplace_tracking_param_cleaning(
        self, raw_url: str, expected_clean_url: str
    ) -> None:
        """Tracking parameters (utm_*, from=share, clid, promo) must be stripped."""
        cleaned = clean_url(raw_url)
        assert cleaned == expected_clean_url

    @pytest.mark.parametrize(
        ("noisy_title", "expected_cleaned"),
        [
            (
                "Игровая приставка Sony PlayStation 5 — купить в интернет-магазине Мегамаркет",
                "Игровая приставка Sony PlayStation 5",
            ),
            (
                "Велосипед горный — объявление на Авито",
                "Велосипед горный",
            ),
            (
                "Чехол для iPhone 15 — купить на маркетплейсе СберМегамаркет по акции",
                "Чехол для iPhone 15",
            ),
            (
                "Кроссовки Nike Air Max | Купить в интернет-магазине Wildberries",
                "Кроссовки Nike Air Max",
            ),
            (
                "Умная колонка Яндекс Станция — купить по выгодной цене на Яндекс Маркете",
                "Умная колонка Яндекс Станция",
            ),
        ],
    )
    def test_clean_title_strips_marketplace_slogans(
        self, noisy_title: str, expected_cleaned: str
    ) -> None:
        """Marketplace marketing slogans and suffix branding must be cleanly stripped."""
        cleaned = clean_title(noisy_title)
        assert cleaned == expected_cleaned


class TestPriceAndCurrencyNormalization:
    """Test price parsing and currency normalization across localized marketplace formats."""

    @pytest.mark.parametrize(
        ("raw_price", "expected_price"),
        [
            ("от 15 990 ₽", 15990),
            ("12 500,50 руб.", 12500),
            ("2 499.00 USD", 2499),
            ("от 1 490 - 2 500 ₽", 1490),
            ("25000", 25000),
            ("1 250 000 ₸", 1250000),
            ("Бесплатно", None),
        ],
    )
    def test_localized_price_parsing(self, raw_price: str, expected_price: int | None) -> None:
        """Prices with currency symbols, ranges, and decimal separators must parse properly."""
        parsed = parse_price(raw_price)
        assert parsed == expected_price

    @pytest.mark.parametrize(
        ("raw_currency", "expected_currency"),
        [
            ("₽", "RUB"),
            ("руб.", "RUB"),
            ("kzt", "KZT"),
            ("₸", "KZT"),
            ("eur", "EUR"),
            ("€", "EUR"),
            ("usd", "USD"),
            ("$", "USD"),
            ("br", "BYN"),
            ("byn", "BYN"),
            ("try", "TRY"),
            ("gel", "GEL"),
            ("amd", "AMD"),
        ],
    )
    def test_currency_normalization(self, raw_currency: str, expected_currency: str) -> None:
        """Currency symbols and lowercase ISO codes must normalize to uppercase ISO 4217."""
        normalized = normalize_currency(raw_currency)
        assert normalized == expected_currency


class TestAntiBotChallengeDetectionAndFallback:
    """Test anti-bot challenge detection (Cloudflare, Qrator, 403, 503) resulting in fallback."""

    @pytest.mark.asyncio
    async def test_qrator_challenge_html_200_results_in_fallback(self) -> None:
        """A 200 response containing Qrator challenge script must degrade to challenge fallback."""
        qrator_html = """
        <!DOCTYPE html>
        <html>
        <head>
          <title>Qrator Protection</title>
          <script src="/qrator_jsid.js"></script>
        </head>
        <body>
          <p>Checking browser...</p>
        </body>
        </html>
        """
        mock_fetcher = MagicMock()
        mock_fetcher._fetch_html = AsyncMock(
            return_value=(qrator_html, "https://www.wildberries.ru/catalog/123/detail.aspx")
        )

        service = ItemPreviewService(url_metadata_service=mock_fetcher)
        preview = await service.fetch_preview("https://www.wildberries.ru/catalog/123/detail.aspx")

        assert preview.is_fallback is True
        assert preview.fallback_reason == "anti_bot_challenge"
        assert preview.store_name == "Wildberries"

    @pytest.mark.asyncio
    async def test_qrator_challenge_403_results_in_anti_bot_fallback(self) -> None:
        """A 403 response with Qrator challenge on wb.ru degrades with store Wildberries."""
        qrator_html = (
            "<html><head><title>Access Restricted</title></head>"
            "<body><script src='qrator-js.js'></script></body></html>"
        )
        qrator_response = httpx.Response(
            status_code=403,
            html=qrator_html,
            request=httpx.Request("GET", "https://wb.ru/catalog/12345/detail.aspx"),
        )
        mock_fetcher = MagicMock()
        mock_fetcher._fetch_html = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                message="Client error '403 Forbidden'",
                request=qrator_response.request,
                response=qrator_response,
            )
        )

        service = ItemPreviewService(url_metadata_service=mock_fetcher)
        preview = await service.fetch_preview("https://wb.ru/catalog/12345/detail.aspx")

        assert preview.is_fallback is True
        assert preview.fallback_reason == "anti_bot_challenge"
        assert preview.store_name == "Wildberries"

    @pytest.mark.asyncio
    async def test_cloudflare_turnstile_503_results_in_anti_bot_fallback(self) -> None:
        """A 503 response with Cloudflare Turnstile challenge screen must degrade gracefully."""
        cf_response = httpx.Response(
            status_code=503,
            html="""
            <html>
            <head><title>Just a moment...</title></head>
            <body>
              <div class="cf-turnstile"></div>
              <script src="/cdn-cgi/challenge-platform/h/b/orchestrate/chl_api/v1"></script>
            </body>
            </html>
            """,
            request=httpx.Request("GET", "https://ozon.ru/product/123/"),
        )
        mock_fetcher = MagicMock()
        mock_fetcher._fetch_html = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                message="Server error '503 Service Unavailable'",
                request=cf_response.request,
                response=cf_response,
            )
        )

        service = ItemPreviewService(url_metadata_service=mock_fetcher)
        preview = await service.fetch_preview("https://ozon.ru/product/123/")

        assert preview.is_fallback is True
        assert preview.fallback_reason == "anti_bot_challenge"
        assert preview.store_name == "Ozon"

    @pytest.mark.asyncio
    async def test_url_tracking_params_cleaned_in_item_preview_service(self) -> None:
        """ItemPreviewService must clean tracking query parameters before fetching."""
        mock_html = """
        <!DOCTYPE html>
        <html>
        <head>
          <meta property="og:title" content="Наушники Sony" />
          <meta property="og:site_name" content="Ozon" />
        </head>
        <body></body>
        </html>
        """
        mock_fetcher = MagicMock()
        mock_fetcher._fetch_html = AsyncMock(
            return_value=(mock_html, "https://ozon.ru/product/123/")
        )

        service = ItemPreviewService(url_metadata_service=mock_fetcher)
        dirty_url = "https://ozon.ru/product/123/?from=share_android&utm_source=tg"

        preview = await service.fetch_preview(dirty_url)

        # Ensure fetcher was called with cleaned URL, not dirty tracking URL
        mock_fetcher._fetch_html.assert_called_once_with(
            "https://ozon.ru/product/123/", client=None
        )
        assert preview.url == "https://ozon.ru/product/123/"


class TestObservabilityAndLogging:
    """Validate Step 6 observability additions: structured events and safety invariants."""

    def test_marketplace_url_cleaned_observability(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """clean_url must log at INFO with event='marketplace_url_cleaned' without secret leaks."""
        caplog.clear()
        with caplog.at_level(logging.DEBUG, logger="wishenka.items"):
            cleaned = clean_url("https://ozon.ru/item/101/?utm_source=ad&from=share_app&foo=bar")

        assert cleaned == "https://ozon.ru/item/101/?foo=bar"
        records = [
            r for r in caplog.records if getattr(r, "event", None) == "marketplace_url_cleaned"
        ]
        assert len(records) == 1
        rec = records[0]
        assert rec.levelname == "INFO"
        assert getattr(rec, "url_domain", None) == "ozon.ru"
        assert getattr(rec, "removed_params_count", None) == 2
        assert "utm_source" in getattr(rec, "removed_keys", [])
        # Ensure values (which could be tracking tokens) are not logged in message
        assert "share_app" not in rec.getMessage()

    def test_marketplace_rule_matching_observability(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """MarketplaceRegistry.get_rule must log matched rule at DEBUG."""
        caplog.clear()
        with caplog.at_level(logging.DEBUG, logger="wishenka.items"):
            rule = MarketplaceRegistry.get_rule("https://wb.ru/catalog/12345/detail.aspx")

        assert rule is not None
        records = [
            r for r in caplog.records if getattr(r, "event", None) == "marketplace_rule_matched"
        ]
        assert len(records) == 1
        rec = records[0]
        assert rec.levelname == "DEBUG"
        assert getattr(rec, "store_name", None) == "Wildberries"
        assert getattr(rec, "url_domain", None) == "wb.ru"

    def test_jsonld_graph_and_aggregate_offer_debug_diagnostics(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """HtmlMetadataExtractor must log @graph and AggregateOffer extraction at DEBUG."""
        caplog.clear()
        html = """
        <!DOCTYPE html>
        <html>
        <head>
          <script type="application/ld+json">
          {
            "@context": "https://schema.org",
            "@graph": [
              {
                "@type": "Product",
                "name": "Робот-пылесос Xiaomi",
                "offers": {
                  "@type": "AggregateOffer",
                  "lowPrice": "18990",
                  "highPrice": "24990",
                  "priceCurrency": "RUB"
                }
              }
            ]
          }
          </script>
        </head>
        <body><div id="secret-heavy-content">Do not leak raw HTML in logs</div></body>
        </html>
        """
        with caplog.at_level(logging.DEBUG, logger="wishenka.items"):
            meta = HtmlMetadataExtractor.extract(
                html, base_url="https://market.yandex.ru/product/123"
            )

        assert meta.title == "Робот-пылесос Xiaomi"
        assert meta.price == 18990

        graph_records = [
            r for r in caplog.records if getattr(r, "event", None) == "jsonld_graph_traversal"
        ]
        assert len(graph_records) >= 1
        assert graph_records[0].levelname == "DEBUG"
        assert getattr(graph_records[0], "graph_items_count", None) == 1

        agg_records = [
            r
            for r in caplog.records
            if getattr(r, "event", None) == "jsonld_aggregate_offer_extracted"
        ]
        assert len(agg_records) == 1
        assert agg_records[0].levelname == "DEBUG"
        assert getattr(agg_records[0], "offer_price", None) == "18990"

        # Invariant: No raw HTML payloads in logs
        for r in caplog.records:
            assert "Do not leak raw HTML" not in r.getMessage()
            assert "<!DOCTYPE html>" not in r.getMessage()

    @pytest.mark.asyncio
    async def test_item_preview_anti_bot_warning_observability(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """ItemPreviewService must log anti-bot challenges at WARNING."""
        caplog.clear()
        cf_response = httpx.Response(
            status_code=403,
            text="<html><title>Just a moment...</title><body>Checking your browser</body></html>",
            request=httpx.Request("GET", "https://ozon.ru/product/123/"),
        )
        mock_fetcher = MagicMock()
        mock_fetcher._fetch_html = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                message="Server error '403 Forbidden'",
                request=cf_response.request,
                response=cf_response,
            )
        )

        service = ItemPreviewService(url_metadata_service=mock_fetcher)
        with caplog.at_level(logging.DEBUG, logger="wishenka.items"):
            preview = await service.fetch_preview("https://ozon.ru/product/123/")

        assert preview.is_fallback is True
        assert preview.fallback_reason == "anti_bot_challenge"

        anti_bot_records = [
            r for r in caplog.records if getattr(r, "event", None) == "item_preview_anti_bot"
        ]
        assert len(anti_bot_records) == 1
        rec = anti_bot_records[0]
        assert rec.levelname == "WARNING"
        assert getattr(rec, "url_domain", None) == "ozon.ru"
        assert getattr(rec, "status_code", None) == 403
        assert getattr(rec, "fallback_reason", None) == "anti_bot_challenge"

        # Invariant: No raw HTML payloads in log messages
        for r in caplog.records:
            assert "Checking your browser" not in r.getMessage()
            assert "Just a moment..." not in r.getMessage()
