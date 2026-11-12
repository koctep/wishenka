"""Item preview service providing asynchronous HTTP scraping and anti-bot graceful fallback."""

import asyncio
import logging
import time

import httpx

from wishenka.items.classifier import UniversalInputClassifier
from wishenka.items.exceptions import (
    InvalidUrlSchemeError,
    ResponseBodyTooLargeError,
    SSRFBlockedError,
)
from wishenka.items.fetcher import DEFAULT_HEADERS, DEFAULT_TIMEOUT, UrlMetadataService
from wishenka.items.marketplaces import clean_url
from wishenka.items.models import InputType
from wishenka.items.parser import HtmlMetadataExtractor, derive_store_name, extract_domain
from wishenka.items.schemas import ItemPreviewDTO

logger = logging.getLogger("wishenka.items")

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
    "qrator",
    "qrator_jsid",
    "qrator-js",
]


class ItemPreviewService:
    """Orchestrates link scraping, universal classification, and graceful degradation."""

    def __init__(
        self,
        url_metadata_service: UrlMetadataService | None = None,
    ) -> None:
        self.url_metadata_service = url_metadata_service or UrlMetadataService(
            timeout=DEFAULT_TIMEOUT
        )

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

        target_url = clean_url(classification.normalized_url or raw_input)
        url_domain = extract_domain(target_url)
        store_name = derive_store_name(target_url)

        try:
            html_text, response_url = await self.url_metadata_service._fetch_html(
                target_url,
                client=client,
            )
        except SSRFBlockedError as exc:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.warning(
                "SSRF blocked for domain %s (host=%s, ip=%s, reason=%s): %s",
                url_domain,
                exc.host,
                exc.ip_address,
                exc.reason,
                exc,
                extra={
                    "event": "item_preview_ssrf_blocked",
                    "url": target_url,
                    "url_domain": url_domain,
                    "host": exc.host,
                    "ip": exc.ip_address,
                    "reason": exc.reason,
                    "input_type": classification.input_type.value,
                    "duration_ms": duration_ms,
                    "fallback_reason": "ssrf_blocked",
                },
            )
            return ItemPreviewDTO(
                input_type=classification.input_type,
                url=target_url,
                store_name=store_name,
                title=classification.residual_text,
                is_fallback=True,
                fallback_reason="ssrf_blocked",
            )
        except InvalidUrlSchemeError as exc:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.warning(
                "Invalid URL scheme '%s' for %s: %s",
                exc.scheme,
                target_url,
                exc,
                extra={
                    "event": "item_preview_invalid_scheme",
                    "url": target_url,
                    "url_domain": url_domain,
                    "scheme": exc.scheme,
                    "reason": "invalid_scheme",
                    "input_type": classification.input_type.value,
                    "duration_ms": duration_ms,
                    "fallback_reason": "ssrf_blocked",
                },
            )
            return ItemPreviewDTO(
                input_type=classification.input_type,
                url=target_url,
                store_name=store_name,
                title=classification.residual_text,
                is_fallback=True,
                fallback_reason="ssrf_blocked",
            )
        except ResponseBodyTooLargeError as exc:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.warning(
                "Response body too large for domain %s (%s bytes, limit %s bytes): %s",
                url_domain,
                exc.content_length,
                exc.max_allowed,
                exc,
                extra={
                    "event": "item_preview_response_too_large",
                    "url": target_url,
                    "url_domain": url_domain,
                    "content_length": exc.content_length,
                    "max_allowed": exc.max_allowed,
                    "reason": "response_too_large",
                    "input_type": classification.input_type.value,
                    "duration_ms": duration_ms,
                    "fallback_reason": "response_too_large",
                },
            )
            return ItemPreviewDTO(
                input_type=classification.input_type,
                url=target_url,
                store_name=store_name,
                title=classification.residual_text,
                is_fallback=True,
                fallback_reason="response_too_large",
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
        except httpx.HTTPStatusError as exc:
            response = exc.response
            response_url = str(response.url) if response.url else target_url
            response_domain = extract_domain(response_url) or url_domain
            effective_store = derive_store_name(response_url) or store_name

            is_challenge = self._is_challenge(response.text)
            if response.status_code in (403, 429, 503) or is_challenge:
                reason = (
                    "anti_bot_challenge"
                    if (response.status_code == 403 or is_challenge)
                    else "http_error"
                )
                duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
                logger.warning(
                    "Anti-bot or restricted status (%s) for domain %s; degrading gracefully",
                    response.status_code,
                    response_domain,
                    extra={
                        "event": "item_preview_anti_bot",
                        "status_code": response.status_code,
                        "url_domain": response_domain,
                        "input_type": classification.input_type.value,
                        "duration_ms": duration_ms,
                        "fallback_reason": reason,
                    },
                )
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

        response_domain = extract_domain(response_url) or url_domain
        effective_store = derive_store_name(response_url) or store_name

        if self._is_challenge(html_text):
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.warning(
                "Anti-bot challenge signature detected in HTML for domain %s; degrading gracefully",
                response_domain,
                extra={
                    "event": "item_preview_anti_bot",
                    "url_domain": response_domain,
                    "input_type": classification.input_type.value,
                    "duration_ms": duration_ms,
                    "fallback_reason": "anti_bot_challenge",
                },
            )
            logger.info(
                "Anti-bot or restricted response for domain %s; degrading gracefully",
                response_domain,
                extra={
                    "event": "anti_bot_challenge_detected",
                    "url_domain": response_domain,
                    "input_type": classification.input_type.value,
                    "duration_ms": duration_ms,
                    "fallback_reason": "anti_bot_challenge",
                },
            )
            return ItemPreviewDTO(
                input_type=classification.input_type,
                url=target_url,
                store_name=effective_store,
                title=classification.residual_text,
                is_fallback=True,
                fallback_reason="anti_bot_challenge",
            )

        try:
            extracted = await asyncio.to_thread(
                HtmlMetadataExtractor.extract, html_text, base_url=response_url
            )
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


__all__ = [
    "DEFAULT_HEADERS",
    "DEFAULT_TIMEOUT",
    "ItemPreviewService",
]
