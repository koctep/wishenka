"""Item preview service providing asynchronous HTTP scraping and anti-bot graceful fallback."""

import logging
import time

import httpx

from wishenka.items.classifier import UniversalInputClassifier
from wishenka.items.models import InputType
from wishenka.items.parser import HtmlMetadataExtractor, derive_store_name, extract_domain
from wishenka.items.schemas import ItemPreviewDTO

logger = logging.getLogger("wishenka.items")

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}

DEFAULT_TIMEOUT = httpx.Timeout(4.0, connect=2.0)

CHALLENGE_SIGNATURES = [
    "_cf_chl_opt",
    "challenge-running",
    "just a moment...",
    "cf-mitigated",
    "turnstile",
    "checking your browser",
    "access denied",
    "waf",
    "ddos-guard",
]


class ItemPreviewService:
    """Orchestrates link scraping, universal classification, and graceful degradation."""

    async def preview(
        self,
        raw_input: str,
        client: httpx.AsyncClient | None = None,
    ) -> ItemPreviewDTO:
        """Alias for fetch_preview."""
        return await self.fetch_preview(raw_input, client=client)

    async def fetch_preview(
        self,
        raw_input: str,
        client: httpx.AsyncClient | None = None,
    ) -> ItemPreviewDTO:
        """Classify input, scrape metadata if URL, and degrade gracefully on anti-bot/timeout."""
        start_time = time.perf_counter()
        classification = UniversalInputClassifier.classify(raw_input)

        if classification.input_type == InputType.PLAIN_TEXT:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.debug(
                "Plain text item preview processed in %sms",
                duration_ms,
                extra={
                    "event": "item_preview_plain_text",
                    "input_type": InputType.PLAIN_TEXT.value,
                    "duration_ms": duration_ms,
                },
            )
            return ItemPreviewDTO(
                input_type=InputType.PLAIN_TEXT,
                title=classification.residual_text,
                is_fallback=False,
            )

        target_url = classification.normalized_url or raw_input
        url_domain = extract_domain(target_url)
        store_name = derive_store_name(target_url)

        try:
            if client is not None:
                response = await client.get(
                    target_url,
                    headers=DEFAULT_HEADERS,
                    follow_redirects=True,
                )
            else:
                async with httpx.AsyncClient(
                    timeout=DEFAULT_TIMEOUT,
                    follow_redirects=True,
                ) as local_client:
                    response = await local_client.get(
                        target_url,
                        headers=DEFAULT_HEADERS,
                    )
        except httpx.TimeoutException:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.warning(
                "Link preview timed out after %sms for domain %s",
                duration_ms,
                url_domain,
                extra={
                    "event": "item_preview_timeout",
                    "url_domain": url_domain,
                    "input_type": classification.input_type.value,
                    "duration_ms": duration_ms,
                    "fallback_reason": "timeout",
                },
            )
            return ItemPreviewDTO(
                input_type=classification.input_type,
                url=target_url,
                store_name=store_name,
                title=classification.residual_text,
                is_fallback=True,
                fallback_reason="timeout",
            )
        except (httpx.HTTPError, Exception) as exc:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.warning(
                "Link preview network error for domain %s: %s",
                url_domain,
                exc,
                extra={
                    "event": "item_preview_network_error",
                    "url_domain": url_domain,
                    "input_type": classification.input_type.value,
                    "duration_ms": duration_ms,
                    "fallback_reason": "http_error",
                },
            )
            return ItemPreviewDTO(
                input_type=classification.input_type,
                url=target_url,
                store_name=store_name,
                title=classification.residual_text,
                is_fallback=True,
                fallback_reason="http_error",
            )

        response_url = str(response.url) if response.url else target_url
        response_domain = extract_domain(response_url) or url_domain
        effective_store = derive_store_name(response_url) or store_name

        # Check anti-bot challenges or HTTP errors
        if response.status_code in (403, 429) or self._is_challenge(response.text):
            reason = (
                "anti_bot_challenge"
                if (response.status_code == 403 or self._is_challenge(response.text))
                else "http_error"
            )
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.info(
                "Anti-bot or restricted response (%s) for domain %s; degrading gracefully",
                response.status_code,
                response_domain,
                extra={
                    "event": "anti_bot_challenge_detected",
                    "status_code": response.status_code,
                    "url_domain": response_domain,
                    "input_type": classification.input_type.value,
                    "duration_ms": duration_ms,
                    "fallback_reason": reason,
                },
            )
            return ItemPreviewDTO(
                input_type=classification.input_type,
                url=target_url,
                store_name=effective_store,
                title=classification.residual_text,
                is_fallback=True,
                fallback_reason=reason,
            )

        if response.status_code >= 400:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.warning(
                "Link preview HTTP error (%s) for domain %s; degrading gracefully",
                response.status_code,
                response_domain,
                extra={
                    "event": "item_preview_http_error",
                    "status_code": response.status_code,
                    "url_domain": response_domain,
                    "input_type": classification.input_type.value,
                    "duration_ms": duration_ms,
                    "fallback_reason": "http_error",
                },
            )
            return ItemPreviewDTO(
                input_type=classification.input_type,
                url=target_url,
                store_name=effective_store,
                title=classification.residual_text,
                is_fallback=True,
                fallback_reason="http_error",
            )

        # 200 OK: extract rich metadata
        try:
            extracted = HtmlMetadataExtractor.extract(response.text, base_url=response_url)
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.info(
                "Link preview successfully generated for domain %s in %sms",
                response_domain,
                duration_ms,
                extra={
                    "event": "item_preview_success",
                    "url_domain": response_domain,
                    "input_type": classification.input_type.value,
                    "duration_ms": duration_ms,
                    "is_fallback": False,
                },
            )
            return ItemPreviewDTO(
                input_type=classification.input_type,
                url=target_url,
                title=extracted.title or classification.residual_text,
                description=extracted.description,
                image_url=extracted.image_url,
                price=extracted.price,
                currency=extracted.currency,
                store_name=extracted.store_name or effective_store,
                store_icon_url=extracted.store_icon_url,
                is_fallback=False,
                fallback_reason=None,
            )
        except Exception as exc:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.error(
                "Metadata parsing failed for domain %s: %s",
                response_domain,
                exc,
                extra={
                    "event": "item_metadata_parsing_error",
                    "url_domain": response_domain,
                    "input_type": classification.input_type.value,
                    "duration_ms": duration_ms,
                    "fallback_reason": "http_error",
                },
            )
            return ItemPreviewDTO(
                input_type=classification.input_type,
                url=target_url,
                store_name=effective_store,
                title=classification.residual_text,
                is_fallback=True,
                fallback_reason="http_error",
            )

    @staticmethod
    def _is_challenge(html: str) -> bool:
        """Detect Cloudflare, WAF, or CAPTCHA challenge signatures in HTML body."""
        if not html:
            return False
        lowered = html.lower()
        return any(sig in lowered for sig in CHALLENGE_SIGNATURES)


__all__ = ["ItemPreviewService"]
