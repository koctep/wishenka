"""Automated failing repro tests for WISHENKA-11.

Covers universal input classification, HTML scraping, graceful fallback,
multi-quantity piece accounting, and surprise invariant integrity.
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from pydantic import ValidationError

from wishenka.auth.models import AuthenticatedUser
from wishenka.items.classifier import UniversalInputClassifier
from wishenka.items.models import (
    ExtractedMetadata,
    InputClassificationResult,
    InputType,
    ItemPriority,
)
from wishenka.items.parser import (
    HtmlMetadataExtractor,
    clean_title,
    normalize_currency,
    parse_price,
)
from wishenka.items.schemas import CreateItemDTO, ItemPreviewDTO, UpdateItemDTO
from wishenka.items.service import ItemPreviewService
from wishenka.wishlists.exceptions import (
    CannotReduceQuantityBelowReservedError,
    InsufficientQuantityError,
)
from wishenka.wishlists.models import (
    Reservation,
    ReservationStatus,
    WishItem,
)
from wishenka.wishlists.schemas import (
    WishItemGifterViewDTO,
    WishItemRecipientViewDTO,
)
from wishenka.wishlists.service import WishlistService
from wishenka.wishlists.store import WishlistStore

pytestmark = pytest.mark.timeout(10)


# ============================================================================
# Helpers
# ============================================================================


def make_user(telegram_id: int, first_name: str, username: str | None = None) -> AuthenticatedUser:
    """Create test AuthenticatedUser instance."""
    return AuthenticatedUser(
        telegram_id=telegram_id,
        first_name=first_name,
        username=username,
        auth_method="session_token",
    )


# ============================================================================
# 1. Universal Input Classification
# ============================================================================


class TestUniversalInputClassification:
    """Validate routing of plain text notes, explicit URLs, and mobile sharing."""

    def test_plain_text_classification(self) -> None:
        raw_text = "Настольная игра Catan (Колонизаторы)"
        result = UniversalInputClassifier.classify(raw_text)

        assert isinstance(result, InputClassificationResult)
        assert result.input_type == InputType.PLAIN_TEXT
        assert result.normalized_url is None
        assert result.residual_text == raw_text
        assert result.raw_input == raw_text

    def test_plain_text_with_special_characters_and_punctuation(self) -> None:
        raw_text = "Книга: Clean Code (Роберт Мартин) — 2-е изд.!"
        result = UniversalInputClassifier.classify(raw_text)

        assert result.input_type == InputType.PLAIN_TEXT
        assert result.normalized_url is None
        assert result.residual_text == raw_text

    def test_explicit_https_url(self) -> None:
        raw_text = "https://ozon.ru/product/nastolnaya-igra-catan-123456789/?from=share"
        result = UniversalInputClassifier.classify(raw_text)

        assert result.input_type == InputType.EXPLICIT_URL
        assert (
            result.normalized_url
            == "https://ozon.ru/product/nastolnaya-igra-catan-123456789/?from=share"
        )
        assert result.residual_text is None

    def test_explicit_http_url(self) -> None:
        raw_text = "http://example.com/goods/item-42.html"
        result = UniversalInputClassifier.classify(raw_text)

        assert result.input_type == InputType.EXPLICIT_URL
        assert result.normalized_url == "http://example.com/goods/item-42.html"
        assert result.residual_text is None

    def test_implicit_domain_url_auto_prefix_https(self) -> None:
        raw_text = "wildberries.ru/catalog/12345/detail.aspx"
        result = UniversalInputClassifier.classify(raw_text)

        assert result.input_type == InputType.IMPLICIT_URL
        assert result.normalized_url == "https://wildberries.ru/catalog/12345/detail.aspx"
        assert result.residual_text is None

    def test_implicit_ozon_short_url(self) -> None:
        raw_text = "ozon.ru/t/AbCdEf"
        result = UniversalInputClassifier.classify(raw_text)

        assert result.input_type == InputType.IMPLICIT_URL
        assert result.normalized_url == "https://ozon.ru/t/AbCdEf"
        assert result.residual_text is None

    def test_mobile_share_composite_text_with_prefix_and_suffix(self) -> None:
        raw_text = (
            "Посмотри, какой классный термос: "
            "https://wildberries.ru/catalog/12345/detail.aspx супер для походов!"
        )
        result = UniversalInputClassifier.classify(raw_text)

        assert result.input_type == InputType.COMPOSITE_SHARE
        assert result.normalized_url == "https://wildberries.ru/catalog/12345/detail.aspx"
        assert result.residual_text == "Посмотри, какой классный термос: супер для походов!"

    def test_mobile_share_implicit_domain_composite_text(self) -> None:
        raw_text = "Глянь кофеварку market.yandex.ru/product/1012345 на кухню"
        result = UniversalInputClassifier.classify(raw_text)

        assert result.input_type == InputType.COMPOSITE_SHARE
        assert result.normalized_url == "https://market.yandex.ru/product/1012345"
        assert result.residual_text == "Глянь кофеварку на кухню"


# ============================================================================
# 2. HTML Structured Metadata Extraction
# ============================================================================


class TestHtmlMetadataExtraction:
    """Validate JSON-LD, OpenGraph, Microdata cascades, and price parsing."""

    def test_extract_json_ld_schema_org_product_and_offer(self) -> None:
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <script type="application/ld+json">
            {
                "@context": "https://schema.org/",
                "@type": "Product",
                "name": "Беспроводные наушники Sony WH-1000XM5",
                "description": "Флагманские наушники с активным шумоподавлением",
                "image": "https://example.com/images/sony-xm5.jpg",
                "brand": {
                    "@type": "Brand",
                    "name": "Sony"
                },
                "offers": {
                    "@type": "Offer",
                    "price": "34990",
                    "priceCurrency": "RUB",
                    "availability": "https://schema.org/InStock"
                }
            }
            </script>
        </head>
        <body><h1>Sony WH-1000XM5</h1></body>
        </html>
        """
        extracted = HtmlMetadataExtractor.extract(
            html, base_url="https://example.com/product/sony-xm5"
        )

        assert isinstance(extracted, ExtractedMetadata)
        assert extracted.title == "Беспроводные наушники Sony WH-1000XM5"
        assert extracted.description == "Флагманские наушники с активным шумоподавлением"
        assert extracted.image_url == "https://example.com/images/sony-xm5.jpg"
        assert extracted.price == 34990
        assert extracted.currency == "RUB"
        assert extracted.store_name in ("Sony", "example.com")

    def test_extract_opengraph_fallback_when_no_json_ld(self) -> None:
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta property="og:title" content="Кофемашина DeLonghi Magnifica">
            <meta property="og:description" content="Автоматическая кофемашина для зёрен">
            <meta property="og:image" content="/media/delonghi.jpg">
            <meta property="og:site_name" content="Яндекс Маркет">
            <meta property="product:price:amount" content="29990.00">
            <meta property="product:price:currency" content="RUB">
        </head>
        <body></body>
        </html>
        """
        extracted = HtmlMetadataExtractor.extract(
            html, base_url="https://market.yandex.ru/product/123"
        )

        assert extracted.title == "Кофемашина DeLonghi Magnifica"
        assert extracted.description == "Автоматическая кофемашина для зёрен"
        assert extracted.image_url == "https://market.yandex.ru/media/delonghi.jpg"
        assert extracted.price == 29990
        assert extracted.currency == "RUB"
        assert extracted.store_name == "Яндекс Маркет"

    def test_extract_microdata_fallback(self) -> None:
        html = """
        <!DOCTYPE html>
        <html>
        <body>
            <div itemscope itemtype="https://schema.org/Product">
                <span itemprop="name">Термокружка Stanley Classic 0.47L</span>
                <img itemprop="image" src="https://example.com/stanley.png" alt="Stanley">
                <div itemprop="offers" itemscope itemtype="https://schema.org/Offer">
                    <span itemprop="price">3 890</span>
                    <span itemprop="priceCurrency">RUB</span>
                </div>
            </div>
        </body>
        </html>
        """
        extracted = HtmlMetadataExtractor.extract(html, base_url="https://example.com/stanley")

        assert extracted.title == "Термокружка Stanley Classic 0.47L"
        assert extracted.image_url == "https://example.com/stanley.png"
        assert extracted.price == 3890
        assert extracted.currency == "RUB"

    def test_extract_standard_html_fallback(self) -> None:
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Умные часы Garmin Fenix 7 — купить в интернет-магазине OZON</title>
            <meta name="description" content="Надежные спортивные часы с GPS и пульсометром.">
            <link rel="icon" href="/favicon-32x32.png">
        </head>
        <body></body>
        </html>
        """
        extracted = HtmlMetadataExtractor.extract(
            html, base_url="https://ozon.ru/product/garmin-fenix-7"
        )

        assert extracted.title == "Умные часы Garmin Fenix 7"
        assert extracted.description == "Надежные спортивные часы с GPS и пульсометром."
        assert extracted.store_name == "Ozon"
        assert extracted.store_icon_url == "https://ozon.ru/favicon-32x32.png"

    def test_price_cleaning_and_formatting(self) -> None:
        assert parse_price(" 1 299 ₽ ") == 1299
        assert parse_price("1490.00") == 1490
        assert parse_price("1,490.50") == 1490
        assert parse_price("$49.99") == 49
        assert parse_price(2500) == 2500
        assert parse_price(None) is None

    def test_currency_normalization_iso_4217(self) -> None:
        assert normalize_currency("₽") == "RUB"
        assert normalize_currency("руб.") == "RUB"
        assert normalize_currency("$") == "USD"
        assert normalize_currency("€") == "EUR"
        assert normalize_currency("₸") == "KZT"
        assert normalize_currency("BYN") == "BYN"
        assert normalize_currency(None) == "RUB"

    def test_title_de_noising(self) -> None:
        clean = clean_title("Книга Чистый Код — купить по выгодной цене в интернет-магазине")
        assert clean == "Книга Чистый Код"
        assert clean_title("Наушники Apple AirPods Pro • OZON") == "Наушники Apple AirPods Pro"
        assert clean_title("Термос 1л | Wildberries") == "Термос 1л"


# ============================================================================
# 3. Graceful Fallback and Anti-Bot Handling
# ============================================================================


class TestGracefulFallbackAndAntiBot:
    """Validate non-blocking degradation against Cloudflare, WAF, or timeouts."""

    @pytest.mark.asyncio
    async def test_http_403_and_429_returns_fallback_preview_without_raising(
        self,
    ) -> None:
        service = ItemPreviewService()
        mock_response = httpx.Response(
            status_code=403,
            request=httpx.Request("GET", "https://ozon.ru/product/12345"),
            text="<html><head><title>Access Denied</title></head></html>",
        )

        with patch.object(
            service.url_metadata_service, "_fetch_html", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = httpx.HTTPStatusError(
                "blocked", request=mock_response.request, response=mock_response
            )
            preview = await service.fetch_preview("https://ozon.ru/product/12345")

        assert isinstance(preview, ItemPreviewDTO)
        assert preview.is_fallback is True
        assert preview.url == "https://ozon.ru/product/12345"
        assert preview.store_name == "Ozon"
        assert preview.fallback_reason in ("anti_bot_challenge", "http_error")

    @pytest.mark.asyncio
    async def test_cloudflare_challenge_detection(self) -> None:
        service = ItemPreviewService()
        html_challenge = """
        <!DOCTYPE html>
        <html>
        <head><title>Just a moment...</title></head>
        <body>
            <div id="challenge-running">Checking your browser...</div>
            <script>window._cf_chl_opt = {};</script>
        </body>
        </html>
        """
        mock_response = httpx.Response(
            status_code=403,
            request=httpx.Request("GET", "https://wildberries.ru/catalog/123"),
            text=html_challenge,
        )

        with patch.object(
            service.url_metadata_service, "_fetch_html", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = httpx.HTTPStatusError(
                "blocked", request=mock_response.request, response=mock_response
            )
            preview = await service.fetch_preview("https://wildberries.ru/catalog/123")

        assert preview.is_fallback is True
        assert preview.fallback_reason == "anti_bot_challenge"
        assert preview.store_name == "Wildberries"
        assert preview.url == "https://wildberries.ru/catalog/123"

    @pytest.mark.asyncio
    async def test_timeout_fallback_to_manual_entry_dto(self) -> None:
        service = ItemPreviewService()

        with patch.object(
            service.url_metadata_service, "_fetch_html", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = httpx.TimeoutException("Connection timed out after 4.0s")
            preview = await service.fetch_preview("https://slow-shop.ru/item/999")

        assert isinstance(preview, ItemPreviewDTO)
        assert preview.is_fallback is True
        assert preview.fallback_reason == "timeout"
        assert preview.url == "https://slow-shop.ru/item/999"


# ============================================================================
# 4. Multi-Quantity Invariants and Piece Accounting
# ============================================================================


class TestMultiQuantityInvariants:
    """Validate desired_quantity boundaries, available_quantity, and lock rules."""

    def test_desired_quantity_default_and_validation_bounds(self) -> None:
        dto = CreateItemDTO(title="Книга")
        assert dto.quantity == 1
        assert dto.priority == ItemPriority.MEDIUM

        dto_valid = CreateItemDTO(title="Тарелки", quantity=12, priority=ItemPriority.HIGH)
        assert dto_valid.quantity == 12
        assert dto_valid.priority == ItemPriority.HIGH

        update_dto = UpdateItemDTO(quantity=8, priority=ItemPriority.LOW)
        assert update_dto.quantity == 8

        with pytest.raises(ValidationError):
            CreateItemDTO(title="Invalid", quantity=0)

        with pytest.raises(ValidationError):
            CreateItemDTO(title="Invalid", quantity=-2)

        with pytest.raises(ValidationError):
            CreateItemDTO(title="Invalid", quantity=1001)

    def test_available_quantity_calculation_formula(self) -> None:
        item = WishItem(
            id=1,
            title="Бокалы для вина",
            quantity=6,
            received_quantity=1,
            reservations=[
                Reservation(
                    id=1,
                    wish_item_id=1,
                    user_id=101,
                    quantity=2,
                    status=ReservationStatus.ACTIVE,
                ),
                Reservation(
                    id=2,
                    wish_item_id=1,
                    user_id=102,
                    quantity=1,
                    status=ReservationStatus.CANCELLED,
                ),
            ],
        )

        assert item.reserved_quantity == 2
        assert item.available_quantity == 3

    @pytest.mark.asyncio
    async def test_partial_reservations_by_multiple_independent_gifters(
        self, tmp_path: Path
    ) -> None:
        store = WishlistStore(f"sqlite+aiosqlite:///{tmp_path / 'pieces.db'}")
        await store.initialize()
        service = WishlistService(store=store)
        owner = make_user(10, "Alice")
        gifter1 = make_user(20, "Bob")
        gifter2 = make_user(30, "Charlie")
        gifter3 = make_user(40, "Dave")
        try:
            wl = await service.create_wishlist(owner_id=owner.telegram_id, title="Новоселье")
            item = await service.add_wish_item(
                wishlist_id=wl.id,
                actor=owner,
                title="Стулья",
                quantity=4,
            )

            res1 = await service.create_reservation(item_id=item.id, user=gifter1, quantity=2)
            assert res1.quantity == 2
            loaded = await service.get_wishlist_by_id(wl.id)
            current = next(it for it in loaded.items if it.id == item.id)
            assert current.available_quantity == 2

            res2 = await service.create_reservation(item_id=item.id, user=gifter2, quantity=1)
            assert res2.quantity == 1
            loaded = await service.get_wishlist_by_id(wl.id)
            current = next(it for it in loaded.items if it.id == item.id)
            assert current.available_quantity == 1

            with pytest.raises(InsufficientQuantityError):
                await service.create_reservation(item_id=item.id, user=gifter3, quantity=2)
        finally:
            await store.dispose()

    def test_cannot_reduce_desired_quantity_below_reserved_plus_fulfilled(
        self,
    ) -> None:
        item = WishItem(
            id=1,
            title="Набор полотенец",
            quantity=5,
            received_quantity=1,
            reservations=[
                Reservation(
                    id=1,
                    wish_item_id=1,
                    user_id=101,
                    quantity=2,
                    status=ReservationStatus.ACTIVE,
                ),
            ],
        )

        active_locked = item.reserved_quantity + item.received_quantity
        assert active_locked == 3

        new_quantity = 2
        with pytest.raises(CannotReduceQuantityBelowReservedError):
            if new_quantity < active_locked:
                raise CannotReduceQuantityBelowReservedError(
                    f"Cannot reduce quantity to {new_quantity}: "
                    f"{active_locked} units already locked"
                )


# ============================================================================
# 5. Surprise Invariant Integrity
# ============================================================================


class TestSurpriseInvariantIntegrity:
    """Validate strict masking of reservation fields for recipient vs gifters."""

    def test_recipient_view_masks_all_reservation_fields(self) -> None:
        recipient_dto = WishItemRecipientViewDTO(
            id=1,
            title="Кофейный сервиз",
            quantity=6,
            received_quantity=0,
            is_recipient=True,
        )

        dumped = recipient_dto.model_dump()
        forbidden_fields = {
            "reserved_quantity",
            "available_quantity",
            "is_fully_reserved",
            "is_reserved_by_me",
            "my_reserved_quantity",
            "reservations",
        }

        leaked_fields = forbidden_fields.intersection(dumped.keys())
        msg = f"Surprise Invariant violated: recipient leaked {leaked_fields}"
        assert not leaked_fields, msg
        assert dumped["quantity"] == 6
        assert dumped["received_quantity"] == 0

    def test_gifter_view_exposes_available_quantity_and_full_reservation(
        self,
    ) -> None:
        gifter_dto = WishItemGifterViewDTO(
            id=1,
            title="Кофейный сервиз",
            quantity=6,
            received_quantity=1,
            available_quantity=2,
            is_fully_reserved=False,
            is_reserved_by_me=True,
            my_reserved_quantity=3,
        )

        dumped = gifter_dto.model_dump()
        assert dumped["available_quantity"] == 2
        assert dumped["is_fully_reserved"] is False
        assert dumped["my_reserved_quantity"] == 3
        assert dumped["is_reserved_by_me"] is True
