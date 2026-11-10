"""Tests for item preview and quantity observability, structured logging, and caplog contracts."""

import logging
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from wishenka.auth.models import AuthenticatedUser
from wishenka.items.classifier import UniversalInputClassifier
from wishenka.items.parser import HtmlMetadataExtractor
from wishenka.items.service import ItemPreviewService
from wishenka.wishlists.exceptions import (
    CannotReduceQuantityBelowReservedError,
    ItemNotFoundError,
    WishlistArchivedError,
)
from wishenka.wishlists.service import WishlistService

pytestmark = pytest.mark.timeout(10)


def make_user(telegram_id: int, first_name: str) -> AuthenticatedUser:
    """Create test AuthenticatedUser instance."""
    return AuthenticatedUser(
        telegram_id=telegram_id,
        first_name=first_name,
        auth_method="session_token",
    )


class TestItemObservability:
    """Validate structured logging emission for item classifier, parser, and quantity updates."""

    def test_universal_input_classification_observability(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Classifier must emit structured DEBUG logs without sensitive leaks."""
        with caplog.at_level(logging.DEBUG, logger="wishenka.items"):
            UniversalInputClassifier.classify("Настольная игра Catan")
            UniversalInputClassifier.classify("https://ozon.ru/product/catan-12345/")
            UniversalInputClassifier.classify("wildberries.ru/catalog/123/detail.aspx")

        records = [r for r in caplog.records if r.name == "wishenka.items"]
        events = [getattr(r, "event", None) for r in records]
        assert events == ["input_classified", "input_classified", "input_classified"]

        plain_rec = records[0]
        assert getattr(plain_rec, "input_type", None) == "plain_text"
        assert getattr(plain_rec, "url_domain", None) is None
        assert getattr(plain_rec, "has_residual", None) is True

        url_rec = records[1]
        assert getattr(url_rec, "input_type", None) == "explicit_url"
        assert getattr(url_rec, "url_domain", None) == "ozon.ru"
        assert getattr(url_rec, "has_residual", None) is False

        implicit_rec = records[2]
        assert getattr(implicit_rec, "input_type", None) == "implicit_url"
        assert getattr(implicit_rec, "url_domain", None) == "wildberries.ru"

    def test_html_metadata_extractor_observability_no_payload_leak(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """HTML parser emits start and completion logs without logging raw HTML payloads."""
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Книга Clean Code - купить в Ozon</title>
            <script type="application/ld+json">
            {
                "@context": "https://schema.org",
                "@type": "Product",
                "name": "Clean Code",
                "offers": {"price": "1500", "priceCurrency": "RUB"}
            }
            </script>
        </head>
        <body><div>Some heavy DOM content</div></body>
        </html>
        """

        with caplog.at_level(logging.DEBUG, logger="wishenka.items"):
            meta = HtmlMetadataExtractor.extract(html, base_url="https://www.ozon.ru/product/123")

        assert meta.title == "Clean Code"
        assert meta.price == 1500

        records = [r for r in caplog.records if r.name == "wishenka.items"]
        events = [getattr(r, "event", None) for r in records]
        assert "metadata_extraction_started" in events
        assert "metadata_stage_resolved" in events
        assert "metadata_extraction_completed" in events

        # Verify no raw HTML payload is logged in messages or extras
        for rec in records:
            assert "Some heavy DOM content" not in rec.getMessage()
            assert "<!DOCTYPE html>" not in rec.getMessage()
            assert getattr(rec, "url_domain", None) == "ozon.ru"

        complete_rec = next(
            r for r in records if getattr(r, "event", None) == "metadata_extraction_completed"
        )
        assert complete_rec.levelname == "INFO"
        assert getattr(complete_rec, "parser_stage", None) == "complete"
        assert getattr(complete_rec, "has_title", None) is True
        assert getattr(complete_rec, "has_price", None) is True
        assert isinstance(getattr(complete_rec, "duration_ms", None), float)

    @pytest.mark.asyncio
    async def test_item_preview_service_success_and_plain_text_logging(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """ItemPreviewService emits structured events for plain text and successful link preview."""
        service = ItemPreviewService()

        # Plain text
        with caplog.at_level(logging.DEBUG, logger="wishenka.items"):
            dto_plain = await service.fetch_preview("Билеты в театр")
        assert dto_plain.input_type.value == "plain_text"
        assert any(
            getattr(r, "event", None) == "item_preview_plain_text"
            and isinstance(getattr(r, "duration_ms", None), float)
            for r in caplog.records
        )

        caplog.clear()

        # Successful URL scrape
        html = """
        <html><head>
        <meta property="og:title" content="Aeropress Coffee Maker" />
        <meta property="product:price:amount" content="3500" />
        </head><body></body></html>
        """
        mock_response = httpx.Response(
            status_code=200,
            text=html,
            request=httpx.Request("GET", "https://ozon.ru/product/aeropress-123"),
        )
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_response

        with caplog.at_level(logging.INFO, logger="wishenka.items"):
            dto = await service.fetch_preview(
                "https://ozon.ru/product/aeropress-123",
                client=mock_client,
            )

        assert dto.title == "Aeropress Coffee Maker"
        assert not dto.is_fallback

        success_rec = next(
            r
            for r in caplog.records
            if r.name == "wishenka.items" and getattr(r, "event", None) == "item_preview_success"
        )
        assert success_rec.levelname == "INFO"
        assert getattr(success_rec, "url_domain", None) == "ozon.ru"
        assert getattr(success_rec, "input_type", None) == "explicit_url"
        assert isinstance(getattr(success_rec, "duration_ms", None), float)

    @pytest.mark.asyncio
    async def test_item_preview_service_failure_and_degradation_logging(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """ItemPreviewService emits logs on timeout, anti-bot, and HTTP error."""
        service = ItemPreviewService()

        # 1. Timeout
        mock_client_timeout = AsyncMock(spec=httpx.AsyncClient)
        mock_client_timeout.get.side_effect = httpx.TimeoutException("Read timed out")

        with caplog.at_level(logging.WARNING, logger="wishenka.items"):
            dto_timeout = await service.fetch_preview(
                "https://ozon.ru/product/slow-item",
                client=mock_client_timeout,
            )
        assert dto_timeout.is_fallback
        assert dto_timeout.fallback_reason == "timeout"
        timeout_rec = next(
            r
            for r in caplog.records
            if r.name == "wishenka.items" and getattr(r, "event", None) == "item_preview_timeout"
        )
        assert timeout_rec.levelname == "WARNING"
        assert getattr(timeout_rec, "url_domain", None) == "ozon.ru"
        assert getattr(timeout_rec, "fallback_reason", None) == "timeout"

        caplog.clear()

        # 2. Network error
        mock_client_net = AsyncMock(spec=httpx.AsyncClient)
        mock_client_net.get.side_effect = httpx.ConnectError("Connection refused")

        with caplog.at_level(logging.WARNING, logger="wishenka.items"):
            dto_net = await service.fetch_preview(
                "https://wildberries.ru/catalog/error-item",
                client=mock_client_net,
            )
        assert dto_net.is_fallback
        assert dto_net.fallback_reason == "http_error"
        net_rec = next(
            r
            for r in caplog.records
            if r.name == "wishenka.items"
            and getattr(r, "event", None) == "item_preview_network_error"
        )
        assert net_rec.levelname == "WARNING"
        assert getattr(net_rec, "url_domain", None) == "wildberries.ru"

        caplog.clear()

        # 3. Anti-bot 403 challenge
        mock_client_antibot = AsyncMock(spec=httpx.AsyncClient)
        mock_client_antibot.get.return_value = httpx.Response(
            status_code=403,
            text="<html><title>Just a moment...</title></html>",
            request=httpx.Request("GET", "https://market.yandex.ru/product/antibot"),
        )

        with caplog.at_level(logging.INFO, logger="wishenka.items"):
            dto_antibot = await service.fetch_preview(
                "https://market.yandex.ru/product/antibot",
                client=mock_client_antibot,
            )
        assert dto_antibot.is_fallback
        assert dto_antibot.fallback_reason == "anti_bot_challenge"
        antibot_rec = next(
            r
            for r in caplog.records
            if r.name == "wishenka.items"
            and getattr(r, "event", None) == "anti_bot_challenge_detected"
        )
        assert antibot_rec.levelname == "INFO"
        assert getattr(antibot_rec, "status_code", None) == 403
        assert getattr(antibot_rec, "url_domain", None) == "market.yandex.ru"

        caplog.clear()

        # 4. HTTP 500 error
        mock_client_500 = AsyncMock(spec=httpx.AsyncClient)
        mock_client_500.get.return_value = httpx.Response(
            status_code=500,
            text="Server Error",
            request=httpx.Request("GET", "https://dns-shop.ru/product/err"),
        )

        with caplog.at_level(logging.WARNING, logger="wishenka.items"):
            dto_500 = await service.fetch_preview(
                "https://dns-shop.ru/product/err",
                client=mock_client_500,
            )
        assert dto_500.is_fallback
        assert dto_500.fallback_reason == "http_error"
        http_rec = next(
            r
            for r in caplog.records
            if r.name == "wishenka.items" and getattr(r, "event", None) == "item_preview_http_error"
        )
        assert http_rec.levelname == "WARNING"
        assert getattr(http_rec, "status_code", None) == 500
        assert getattr(http_rec, "url_domain", None) == "dns-shop.ru"

        caplog.clear()

        # 5. Metadata extraction exception
        mock_client_parse_err = AsyncMock(spec=httpx.AsyncClient)
        mock_client_parse_err.get.return_value = httpx.Response(
            status_code=200,
            text="<html></html>",
            request=httpx.Request("GET", "https://avito.ru/item/bug"),
        )

        with (
            caplog.at_level(logging.ERROR, logger="wishenka.items"),
            patch.object(
                HtmlMetadataExtractor,
                "extract",
                side_effect=RuntimeError("Parsing crash"),
            ),
        ):
            dto_parse_err = await service.fetch_preview(
                "https://avito.ru/item/bug",
                client=mock_client_parse_err,
            )
        assert dto_parse_err.is_fallback
        parse_rec = next(
            r
            for r in caplog.records
            if r.name == "wishenka.items"
            and getattr(r, "event", None) == "item_metadata_parsing_error"
        )
        assert parse_rec.levelname == "ERROR"
        assert getattr(parse_rec, "url_domain", None) == "avito.ru"

    @pytest.mark.asyncio
    async def test_wishlist_item_quantity_update_observability(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Item creation and quantity updates emit structured events with deltas and warnings."""
        service = WishlistService()
        owner = make_user(1001, "Alice")
        gifter = make_user(2001, "Bob")

        wl = await service.create_wishlist(owner=owner, title="Observability Wishlist")

        # 1. Add item with quantity=3
        with caplog.at_level(logging.INFO, logger="wishenka.wishlists"):
            item = await service.add_wish_item(
                wishlist_id=wl.id,
                actor=owner,
                title="Board Game",
                quantity=3,
            )
        created_rec = next(
            r
            for r in caplog.records
            if r.name == "wishenka.wishlists" and getattr(r, "event", None) == "item_created"
        )
        assert getattr(created_rec, "item_id", None) == item.id
        assert getattr(created_rec, "wishlist_id", None) == wl.id
        assert getattr(created_rec, "quantity", None) == 3

        caplog.clear()

        # 2. Update quantity to 5 (delta = +2)
        with caplog.at_level(logging.INFO, logger="wishenka.wishlists"):
            updated_item = await service.update_wish_item(
                item_id=item.id,
                actor=owner,
                quantity=5,
            )
        assert updated_item.quantity == 5
        update_rec = next(
            r
            for r in caplog.records
            if r.name == "wishenka.wishlists" and getattr(r, "event", None) == "item_updated"
        )
        assert getattr(update_rec, "item_id", None) == item.id
        assert getattr(update_rec, "wishlist_id", None) == wl.id
        assert getattr(update_rec, "quantity", None) == 5
        assert getattr(update_rec, "quantity_delta", None) == 2

        caplog.clear()

        # 3. Reserve 2 units
        await service.create_reservation(item_id=item.id, user=gifter, quantity=2)

        # 4. Attempt to reduce desired quantity below locked (requested 1, locked 2)
        with (
            caplog.at_level(logging.WARNING, logger="wishenka.wishlists"),
            pytest.raises(CannotReduceQuantityBelowReservedError),
        ):
            await service.update_wish_item(
                item_id=item.id,
                actor=owner,
                quantity=1,
            )

        rejected_rec = next(
            r
            for r in caplog.records
            if r.name == "wishenka.wishlists"
            and getattr(r, "event", None) == "item_quantity_reduction_rejected"
        )
        assert rejected_rec.levelname == "WARNING"
        assert getattr(rejected_rec, "item_id", None) == item.id
        assert getattr(rejected_rec, "requested_quantity", None) == 1
        assert getattr(rejected_rec, "locked_quantity", None) == 2

        caplog.clear()

        # 5. Non-existent item update emits item_not_found warning
        with (
            caplog.at_level(logging.WARNING, logger="wishenka.wishlists"),
            pytest.raises(ItemNotFoundError),
        ):
            await service.update_wish_item(
                item_id=99999,
                actor=owner,
                quantity=2,
            )

        not_found_rec = next(
            r
            for r in caplog.records
            if r.name == "wishenka.wishlists" and getattr(r, "event", None) == "item_not_found"
        )
        assert not_found_rec.levelname == "WARNING"
        assert getattr(not_found_rec, "item_id", None) == 99999

        caplog.clear()

        # 6. Archived wishlist blocks item update and emits warning
        await service.archive_wishlist(wishlist_id=wl.id, actor=owner)
        with (
            caplog.at_level(logging.WARNING, logger="wishenka.wishlists"),
            pytest.raises(WishlistArchivedError),
        ):
            await service.update_wish_item(
                item_id=item.id,
                actor=owner,
                title="Renamed after archive",
            )

        archived_rec = next(
            r
            for r in caplog.records
            if r.name == "wishenka.wishlists"
            and getattr(r, "event", None) == "item_mutation_blocked_archived"
        )
        assert archived_rec.levelname == "WARNING"
        assert getattr(archived_rec, "item_id", None) == item.id
