"""Automated failing repro tests for WISHENKA-98.

Covers:
1. International currency recognition, normalization, and inline extraction for
   CNY, GBP, JPY, TRY, GEL, and AMD (plus existing RUB, USD, EUR, KZT, BYN) and
   shared Yen/Yuan ('¥') disambiguation.
2. Localized numeric price parsing and separator disambiguation (European
   thousand dots + comma decimals, Anglo-Saxon thousand commas + dot decimals,
   3-digit thousand groupings vs 1-2 digit decimal fractions, Unicode thin and
   narrow non-breaking spaces, and rejection of non-positive/boolean values).
3. Complex JSON-LD structured pricing extraction (nested `priceSpecification`,
   multi-offer lists with empty/invalid leading offers, nested `AggregateOffer`
   offers, multiple Product nodes) and inline currency fallback across OpenGraph
   and Microdata tags.
4. End-to-end foreign e-commerce preview extraction via `ItemPreviewService`.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

import wishenka.items.parser as parser_mod
from wishenka.items.classifier import UniversalInputClassifier
from wishenka.items.models import InputType
from wishenka.items.parser import (
    HtmlMetadataExtractor,
    derive_store_name,
    normalize_currency,
    parse_price,
)
from wishenka.items.service import ItemPreviewService

pytestmark = pytest.mark.timeout(10)


# ============================================================================
# 1. International Currency Normalization & Inline Extraction
# ============================================================================


class TestInternationalCurrencyNormalization:
    """Validate normalization and inline extraction for CNY, GBP, JPY, TRY, GEL, AMD."""

    @pytest.mark.parametrize(
        ("raw_currency", "expected_iso"),
        [
            # Chinese Yuan (CNY)
            ("CNY", "CNY"),
            ("cny", "CNY"),
            ("¥", "CNY"),
            ("￥", "CNY"),
            ("CN¥", "CNY"),
            ("cn¥", "CNY"),
            ("RMB", "CNY"),
            ("rmb", "CNY"),
            ("元", "CNY"),
            ("юан", "CNY"),
            ("юань", "CNY"),
            ("юаней", "CNY"),
            # British Pound (GBP)
            ("GBP", "GBP"),
            ("gbp", "GBP"),
            ("£", "GBP"),
            ("￡", "GBP"),
            ("GB£", "GBP"),
            ("UK£", "GBP"),
            ("фунт", "GBP"),
            ("фунтов", "GBP"),
            # Japanese Yen (JPY)
            ("JPY", "JPY"),
            ("jpy", "JPY"),
            ("JP¥", "JPY"),
            ("jp¥", "JPY"),
            ("円", "JPY"),
            ("йен", "JPY"),
            ("йена", "JPY"),
            ("иен", "JPY"),
            ("yen", "JPY"),
            # Turkish Lira (TRY)
            ("TRY", "TRY"),
            ("try", "TRY"),
            ("₺", "TRY"),
            ("TL", "TRY"),
            ("tl", "TRY"),
            ("TRL", "TRY"),
            ("лир", "TRY"),
            ("лира", "TRY"),
            ("лиры", "TRY"),
            # Georgian Lari (GEL)
            ("GEL", "GEL"),
            ("gel", "GEL"),
            ("₾", "GEL"),
            ("лари", "GEL"),
            ("lari", "GEL"),
            # Armenian Dram (AMD)
            ("AMD", "AMD"),
            ("amd", "AMD"),
            ("֏", "AMD"),
            ("դր", "AMD"),
            ("դր.", "AMD"),
            ("драм", "AMD"),
            ("драмов", "AMD"),
            ("dram", "AMD"),
            # Existing supported currencies (regression check)
            ("RUB", "RUB"),
            ("₽", "RUB"),
            ("руб.", "RUB"),
            ("USD", "USD"),
            ("$", "USD"),
            ("EUR", "EUR"),
            ("€", "EUR"),
            ("KZT", "KZT"),
            ("₸", "KZT"),
            ("BYN", "BYN"),
            ("br", "BYN"),
        ],
    )
    def test_normalize_standalone_international_currencies(
        self, raw_currency: str, expected_iso: str
    ) -> None:
        """All target international currency codes, symbols, and names normalize to ISO 4217."""
        assert normalize_currency(raw_currency) == expected_iso

    @pytest.mark.parametrize(
        ("inline_text", "expected_iso"),
        [
            ("199 元", "CNY"),
            ("CN¥ 88.50", "CNY"),
            ("RMB 250", "CNY"),
            ("¥ 199.00", "CNY"),
            ("£49.99", "GBP"),
            ("129.00 GBP", "GBP"),
            ("JP¥ 12,800", "JPY"),
            ("12,800 円", "JPY"),
            ("3500 йен", "JPY"),
            ("1.450,50 ₺", "TRY"),
            ("1 450,50 ₺", "TRY"),
            ("899 TL", "TRY"),
            ("120,00 ₾", "GEL"),
            ("85 лари", "GEL"),
            ("15.000 ֏", "AMD"),
            ("25 000 драм", "AMD"),
            ("1.299,99 €", "EUR"),
            ("$1,299.99", "USD"),
        ],
    )
    def test_extract_and_normalize_inline_currency_from_price_text(
        self, inline_text: str, expected_iso: str
    ) -> None:
        """extract_currency and normalize_currency resolve inline currency from price strings."""
        assert hasattr(parser_mod, "extract_currency"), (
            "extract_currency must be exported in wishenka.items.parser"
        )
        extract_currency = parser_mod.extract_currency
        assert extract_currency(inline_text) == expected_iso
        assert normalize_currency(None, fallback_text=inline_text) == expected_iso

    def test_yen_vs_yuan_disambiguation_with_explicit_currency_and_fallback(self) -> None:
        """Explicit JPY/CNY codes and markers disambiguate the shared '¥' symbol."""
        # Explicit structured currency code takes precedence over bare ¥ in price text
        assert normalize_currency("JPY", fallback_text="¥ 12,800") == "JPY"
        assert normalize_currency("CNY", fallback_text="¥ 199.00") == "CNY"
        # When raw_currency is ambiguous bare '¥', fallback_text with JP¥ or 円 resolves JPY
        assert normalize_currency("¥", fallback_text="JP¥ 12,800") == "JPY"
        assert normalize_currency("¥", fallback_text="12,800 円") == "JPY"
        # When only bare '¥' is present with no JPY marker, default deterministically to CNY
        assert normalize_currency("¥", fallback_text="¥ 199.00") == "CNY"
        assert normalize_currency(None, fallback_text="¥ 199.00") == "CNY"


# ============================================================================
# 2. Localized Number Separator Disambiguation
# ============================================================================


class TestLocalizedNumericPriceParsing:
    """Validate European, Anglo-Saxon, and whitespace-grouped price parsing."""

    @pytest.mark.parametrize(
        ("raw_price", "expected_int"),
        [
            # European thousand dots + comma decimal
            ("1.299,99 €", 1299),
            ("1.234.567,89 €", 1234567),
            ("1.450,50 ₺", 1450),
            ("99,95 €", 99),
            ("12,5 €", 12),
            # Anglo-Saxon thousand commas + dot decimal
            ("$1,299.99", 1299),
            ("£1,234,567.89", 1234567),
            ("£49.99", 49),
            ("12.50 GBP", 12),
            # Whole-number 3-digit thousand groupings without fractional cents
            ("¥ 12,800", 12800),
            ("JP¥ 12,800", 12800),
            ("15.000 ₺", 15000),
            ("15.000 ֏", 15000),
            ("1.299 €", 1299),
            ("1.234.567", 1234567),
            ("1,234,567", 1234567),
            # Standard, non-breaking (\xa0), narrow no-break (\u202f), and thin (\u2009) spaces
            ("12 990,50 ₺", 12990),
            ("12\xa0990,50 ₺", 12990),
            ("12\u202f990,50 ₺", 12990),
            ("1\u2009250\u2009000 ֏", 1250000),
        ],
    )
    def test_parse_price_localized_thousand_and_decimal_separators(
        self, raw_price: str, expected_int: int
    ) -> None:
        """parse_price accurately disambiguates European, Anglo-Saxon, and spaced separators."""
        assert parse_price(raw_price) == expected_int

    @pytest.mark.parametrize(
        ("raw_price", "expected_decimal"),
        [
            ("1.299,99 €", 1299.99),
            ("1.234.567,89 €", 1234567.89),
            ("$1,299.99", 1299.99),
            ("£1,234,567.89", 1234567.89),
            ("¥ 12,800", 12800.0),
            ("15.000 ₺", 15000.0),
            ("15.000 ֏", 15000.0),
            ("1.234.567", 1234567.0),
            ("12,50 €", 12.50),
            ("12.50 GBP", 12.50),
            ("0,125 EUR", 0.125),
            ("0,005 EUR", 0.005),
            ("0.125 EUR", 0.125),
            ("0.005 EUR", 0.005),
            ("USD 25.00", 25.0),
            ("special-price EUR 25.00", 25.0),
            ("from 12 - 25 EUR", 12.0),
            ("12\u202f990,50 ₺", 12990.50),
            ("1\u2009250\u2009000 ֏", 1250000.0),
        ],
    )
    def test_parse_decimal_price_exact_floating_point_evaluation(
        self, raw_price: str, expected_decimal: float
    ) -> None:
        """parse_decimal_price evaluates exact decimal amounts before integer truncation."""
        assert hasattr(parser_mod, "parse_decimal_price"), (
            "parse_decimal_price must be exported in wishenka.items.parser"
        )
        parse_decimal_price = parser_mod.parse_decimal_price
        decimal_val = parse_decimal_price(raw_price)
        assert decimal_val is not None
        assert decimal_val == pytest.approx(expected_decimal)

    @pytest.mark.parametrize(
        "invalid_price",
        [
            0,
            0.0,
            -1,
            -100.50,
            "0",
            "0,00 €",
            "0.00",
            "-500 ₽",
            "-1.299,99 €",
            "-$25.00",
            "USD -25.00",
            "-USD 25.00",
            "- EUR 12,50",
            "EUR − 12,50",
            True,
            False,
            None,
            "",
            "Бесплатно",
        ],
    )
    def test_rejects_zero_negative_and_boolean_prices(self, invalid_price: object) -> None:
        """Zero, negative, and boolean values must be rejected as None."""
        assert parse_price(invalid_price) is None
        if hasattr(parser_mod, "parse_decimal_price"):
            assert parser_mod.parse_decimal_price(invalid_price) is None

    @pytest.mark.parametrize("currency", list(parser_mod.CURRENCY_MAP))
    @pytest.mark.parametrize("sign", ["-", "−"])
    @pytest.mark.parametrize("before_currency", [True, False])
    def test_negative_prices_with_every_supported_currency(
        self, currency: str, sign: str, before_currency: bool
    ) -> None:
        """Every supported currency rejects both sign positions without rejecting positives."""
        raw = f"{sign}{currency} 25" if before_currency else f"{currency} {sign}25"
        assert parser_mod.parse_decimal_price(raw) is None
        assert parser_mod.parse_decimal_price(f"{currency} 25") == 25


# ============================================================================
# 3. Complex JSON-LD Structured Pricing & Foreign E-Commerce HTML Fixtures
# ============================================================================


class TestComplexStructuredPricingAndForeignFixtures:
    """Validate complex JSON-LD offers and foreign e-commerce HTML page extraction."""

    @pytest.mark.parametrize("price", ["12.50 EUR", "€12.50"])
    def test_selected_jsonld_inline_currency_precedes_other_stage_currency(
        self, price: str
    ) -> None:
        """The selected price's inline currency precedes an unrelated OpenGraph currency."""
        html = f'''<script type="application/ld+json">
        {{"@type": "Product", "name": "Product", "offers": {{"price": "{price}"}}}}
        </script><meta property="og:price:currency" content="USD">'''
        result = HtmlMetadataExtractor.extract(html, "https://example.com/product")
        assert result.price == 12.5
        assert result.currency == "EUR"

    def test_invalid_product_offer_does_not_supply_currency_for_next_product(self) -> None:
        """The selected positive price and currency must come from the same product."""
        html = """<script type="application/ld+json">
        {"@graph": [
            {"@type": "Product", "name": "Product",
             "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"}},
            {"@type": "Product",
             "offers": {"@type": "Offer", "price": "12.50", "priceCurrency": "EUR"}}
        ]}
        </script>"""
        result = HtmlMetadataExtractor.extract(html, "https://example.com/product")
        assert result.price == 12.5
        assert result.currency == "EUR"

    def test_invalid_price_specification_cannot_override_inherited_currency(self) -> None:
        """Invalid nested pricing does not contaminate the selected offer's currency."""
        html = """<script type="application/ld+json">
        {"@type": "Product", "name": "Product", "offers": {
            "@type": "AggregateOffer", "priceCurrency": "EUR",
            "priceSpecification": {"price": "0", "priceCurrency": "USD"},
            "offers": [{"price": "12.50"}]
        }}
        </script>"""
        result = HtmlMetadataExtractor.extract(html, "https://example.com/product")
        assert result.price == 12.5
        assert result.currency == "EUR"

    def test_jsonld_nested_unit_price_specification_with_european_price(self) -> None:
        """JSON-LD Offer with nested priceSpecification extracts European EUR price and currency."""
        html = """
        <!DOCTYPE html>
        <html lang="de">
        <head>
            <script type="application/ld+json">
            {
                "@context": "https://schema.org",
                "@type": "Product",
                "name": "Kaffeevollautomat Jura E8",
                "image": "https://shop.example.de/img/jura-e8.jpg",
                "offers": {
                    "@type": "Offer",
                    "priceSpecification": {
                        "@type": "UnitPriceSpecification",
                        "price": "1.299,99",
                        "priceCurrency": "EUR"
                    }
                }
            }
            </script>
        </head>
        <body></body>
        </html>
        """
        meta = HtmlMetadataExtractor.extract(html, "https://shop.example.de/p/jura-e8")
        assert meta.title == "Kaffeevollautomat Jura E8"
        assert meta.price == 1299.99
        assert meta.currency == "EUR"

    def test_jsonld_multi_offer_list_skips_empty_first_offer(self) -> None:
        """When offers[0] has an empty price, extractor selects the first valid positive offer."""
        html = """
        <!DOCTYPE html>
        <html lang="en-GB">
        <head>
            <script type="application/ld+json">
            {
                "@context": "https://schema.org",
                "@type": "Product",
                "name": "Dyson Airwrap Multi-Styler",
                "offers": [
                    {
                        "@type": "Offer",
                        "price": "",
                        "priceCurrency": "GBP",
                        "availability": "https://schema.org/OutOfStock"
                    },
                    {
                        "@type": "Offer",
                        "price": "479.99",
                        "priceCurrency": "GBP",
                        "availability": "https://schema.org/InStock"
                    }
                ]
            }
            </script>
        </head>
        <body></body>
        </html>
        """
        meta = HtmlMetadataExtractor.extract(html, "https://www.amazon.co.uk/dp/B0ABCD1234")
        assert meta.title == "Dyson Airwrap Multi-Styler"
        assert meta.price == 479.99
        assert meta.currency == "GBP"
        assert meta.store_name == "Amazon"

    def test_jsonld_aggregate_offer_with_nested_offers_and_empty_top_price(self) -> None:
        """AggregateOffer with empty price and nested offers list resolves valid price and TRY."""
        html = """
        <!DOCTYPE html>
        <html lang="tr">
        <head>
            <script type="application/ld+json">
            {
                "@context": "https://schema.org",
                "@type": "Product",
                "name": "Türk Kahve Makinesi Arçelik Telve",
                "offers": {
                    "@type": "AggregateOffer",
                    "price": "",
                    "priceCurrency": "TRY",
                    "offers": [
                        {
                            "@type": "Offer",
                            "price": "4.299,00"
                        }
                    ]
                }
            }
            </script>
        </head>
        <body></body>
        </html>
        """
        meta = HtmlMetadataExtractor.extract(html, "https://www.trendyol.com/arcelik/telve-p-12345")
        assert meta.title == "Türk Kahve Makinesi Arçelik Telve"
        assert meta.price == 4299
        assert meta.currency == "TRY"

    def test_japanese_store_jsonld_with_yen_symbol_and_jpy_currency(self) -> None:
        """Amazon JP page with price '¥ 12,800' and priceCurrency 'JPY' extracts 12800 JPY."""
        html = """
        <!DOCTYPE html>
        <html lang="ja">
        <head>
            <script type="application/ld+json">
            {
                "@context": "https://schema.org",
                "@type": "Product",
                "name": "Nintendo Switch Proコントローラー",
                "offers": {
                    "@type": "Offer",
                    "price": "¥ 12,800",
                    "priceCurrency": "JPY"
                }
            }
            </script>
        </head>
        <body></body>
        </html>
        """
        meta = HtmlMetadataExtractor.extract(html, "https://www.amazon.co.jp/dp/B01NCX3W3O")
        assert meta.title == "Nintendo Switch Proコントローラー"
        assert meta.price == 12800
        assert meta.currency == "JPY"
        assert meta.store_name == "Amazon"

    def test_chinese_store_opengraph_with_inline_rmb_and_yuan_symbol(self) -> None:
        """Chinese store page with inline 'CN¥ 1,299.00' in OpenGraph price tag resolves CNY."""
        html = """
        <!DOCTYPE html>
        <html lang="zh-CN">
        <head>
            <meta property="og:title" content="Xiaomi Mechanical Keyboard Pro">
            <meta property="og:site_name" content="Taobao">
            <meta property="product:price:amount" content="CN¥ 1,299.00">
        </head>
        <body></body>
        </html>
        """
        meta = HtmlMetadataExtractor.extract(html, "https://item.taobao.com/item.htm?id=12345")
        assert meta.title == "Xiaomi Mechanical Keyboard Pro"
        assert meta.price == 1299
        assert meta.currency == "CNY"
        assert meta.store_name == "Taobao"

    def test_georgian_and_armenian_microdata_inline_currency_extraction(self) -> None:
        """Georgian (GEL / ₾) and Armenian (AMD / ֏) Microdata pages extract inline currencies."""
        gel_html = """
        <!DOCTYPE html>
        <html>
        <body>
            <div itemscope itemtype="https://schema.org/Product">
                <h1 itemprop="name">Georgian Wine Decanter</h1>
                <div itemprop="offers" itemscope itemtype="https://schema.org/Offer">
                    <span itemprop="price">120,50 ₾</span>
                </div>
            </div>
        </body>
        </html>
        """
        gel_meta = HtmlMetadataExtractor.extract(gel_html, "https://shop.example.ge/items/42")
        assert gel_meta.title == "Georgian Wine Decanter"
        assert gel_meta.price == 120.5
        assert gel_meta.currency == "GEL"

        amd_html = """
        <!DOCTYPE html>
        <html>
        <body>
            <div itemscope itemtype="https://schema.org/Product">
                <h1 itemprop="name">Armenian Handcrafted Chess Set</h1>
                <div itemprop="offers" itemscope itemtype="https://schema.org/Offer">
                    <span itemprop="price">15.000 ֏</span>
                </div>
            </div>
        </body>
        </html>
        """
        amd_meta = HtmlMetadataExtractor.extract(amd_html, "https://shop.example.am/items/99")
        assert amd_meta.title == "Armenian Handcrafted Chess Set"
        assert amd_meta.price == 15000
        assert amd_meta.currency == "AMD"

    def test_international_implicit_domain_classification_and_store_names(self) -> None:
        """UniversalInputClassifier recognizes implicit URLs for regional international TLDs."""
        for raw_url, expected_domain in [
            ("amazon.co.uk/dp/B012345", "https://amazon.co.uk/dp/B012345"),
            ("amazon.de/dp/B012345", "https://amazon.de/dp/B012345"),
            ("amazon.co.jp/dp/B012345", "https://amazon.co.jp/dp/B012345"),
            ("shop.example.ge/product/12", "https://shop.example.ge/product/12"),
            ("shop.example.am/product/34", "https://shop.example.am/product/34"),
            ("trendyol.com/brand/item-p-123", "https://trendyol.com/brand/item-p-123"),
        ]:
            classified = UniversalInputClassifier.classify(raw_url)
            assert classified.input_type == InputType.IMPLICIT_URL
            assert classified.normalized_url == expected_domain

        assert derive_store_name("https://www.amazon.co.uk/dp/B012345") == "Amazon"
        assert derive_store_name("https://www.amazon.de/dp/B012345") == "Amazon"
        assert derive_store_name("https://www.amazon.co.jp/dp/B012345") == "Amazon"
        assert derive_store_name("https://www.trendyol.com/brand/item-p-123") == "Trendyol"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("url", "html", "expected_price", "expected_currency"),
        [
            (
                "https://item.taobao.com/item.htm?id=101",
                '<meta property="og:title" content="Tea Set">'
                '<meta property="product:price:amount" content="¥ 268.00">',
                268,
                "CNY",
            ),
            (
                "https://www.amazon.co.uk/dp/B001",
                '<meta property="og:title" content="Kettle">'
                '<meta property="product:price:amount" content="£89.99">',
                89.99,
                "GBP",
            ),
            (
                "https://www.amazon.co.jp/dp/B002",
                '<meta property="og:title" content="Matcha Whisk">'
                '<meta property="product:price:amount" content="12,800 円">',
                12800,
                "JPY",
            ),
            (
                "https://www.trendyol.com/p-303",
                '<meta property="og:title" content="Turkish Lamp">'
                '<meta property="product:price:amount" content="1.450,50 ₺">',
                1450.50,
                "TRY",
            ),
            (
                "https://shop.example.ge/p/404",
                '<meta property="og:title" content="Saperavi Set">'
                '<meta property="product:price:amount" content="120,00 ₾">',
                120,
                "GEL",
            ),
            (
                "https://shop.example.am/p/505",
                '<meta property="og:title" content="Silver Bracelet">'
                '<meta property="product:price:amount" content="15.000 ֏">',
                15000,
                "AMD",
            ),
        ],
    )
    async def test_item_preview_service_end_to_end_international_stores(
        self,
        url: str,
        html: str,
        expected_price: int | float,
        expected_currency: str,
    ) -> None:
        """ItemPreviewService extracts price and normalized currency across all 6 target regions."""
        mock_fetcher = MagicMock()
        mock_fetcher._fetch_html = AsyncMock(return_value=(html, url))
        service = ItemPreviewService(url_metadata_service=mock_fetcher)

        preview = await service.fetch_preview(url)

        assert preview.is_fallback is False
        assert preview.price == expected_price
        assert preview.currency == expected_currency

    @pytest.mark.parametrize(("raw_price", "expected"), [("1.299,99 €", 1299.99), ("0,50 €", 0.5)])
    async def test_fractional_prices_survive_preview_service(
        self, raw_price: str, expected: float
    ) -> None:
        """Fractional and subunit prices survive extraction and the preview DTO."""
        url = "https://shop.example.com/product"
        html = (
            '<meta property="og:title" content="Product">'
            f'<meta property="product:price:amount" content="{raw_price}">'
        )
        mock_fetcher = MagicMock()
        mock_fetcher._fetch_html = AsyncMock(return_value=(html, url))

        preview = await ItemPreviewService(url_metadata_service=mock_fetcher).fetch_preview(url)

        assert preview.price == expected
        assert preview.currency == "EUR"
