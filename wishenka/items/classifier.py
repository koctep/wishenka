"""Universal input classifier for wishlist items."""

import logging
import re

from wishenka.items.models import (
    InputClassificationResult,
    InputType,
)
from wishenka.items.parser import extract_domain

logger = logging.getLogger("wishenka.items")

# Explicit URL with protocol
EXPLICIT_URL_REGEX = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)

# Implicit domain URL without protocol
DOMAIN_URL_REGEX = re.compile(
    r"\b(?:[a-zA-Z0-9-]+\.)+(?:ru|com|org|net|by|kz|io|me|app|store|shop|market|su)(?:/[^\s<>\"']*)?",
    re.IGNORECASE,
)


class UniversalInputClassifier:
    """Classifies user input into plain text, explicit URLs, implicit URLs, or composite shares."""

    @classmethod
    def classify(cls, raw_text: str) -> InputClassificationResult:
        """Classify raw user text and extract normalized URLs or residual text."""
        cleaned = raw_text.strip()
        if not cleaned:
            result = InputClassificationResult(
                input_type=InputType.PLAIN_TEXT,
                normalized_url=None,
                residual_text="",
                raw_input=raw_text,
            )
        # 1. Search for explicit protocol URL (https?://...)
        elif match_explicit := EXPLICIT_URL_REGEX.search(cleaned):
            url = match_explicit.group(0)
            prefix = cleaned[: match_explicit.start()]
            suffix = cleaned[match_explicit.end() :]
            residual = f"{prefix} {suffix}"
            residual = re.sub(r"\s+", " ", residual).strip()

            if not residual:
                result = InputClassificationResult(
                    input_type=InputType.EXPLICIT_URL,
                    normalized_url=url,
                    residual_text=None,
                    raw_input=raw_text,
                )
            else:
                result = InputClassificationResult(
                    input_type=InputType.COMPOSITE_SHARE,
                    normalized_url=url,
                    residual_text=residual,
                    raw_input=raw_text,
                )
        # 2. Search for implicit domain URL
        elif match_domain := DOMAIN_URL_REGEX.search(cleaned):
            domain_url = match_domain.group(0)
            normalized_url = f"https://{domain_url}"
            prefix = cleaned[: match_domain.start()]
            suffix = cleaned[match_domain.end() :]
            residual = f"{prefix} {suffix}"
            residual = re.sub(r"\s+", " ", residual).strip()

            if not residual:
                result = InputClassificationResult(
                    input_type=InputType.IMPLICIT_URL,
                    normalized_url=normalized_url,
                    residual_text=None,
                    raw_input=raw_text,
                )
            else:
                result = InputClassificationResult(
                    input_type=InputType.COMPOSITE_SHARE,
                    normalized_url=normalized_url,
                    residual_text=residual,
                    raw_input=raw_text,
                )
        # 3. Fallback to plain text
        else:
            result = InputClassificationResult(
                input_type=InputType.PLAIN_TEXT,
                normalized_url=None,
                residual_text=raw_text,
                raw_input=raw_text,
            )

        url_domain = extract_domain(result.normalized_url)
        logger.debug(
            "Universal input classified as %s (domain=%s, has_residual=%s)",
            result.input_type.value,
            url_domain,
            bool(result.residual_text),
            extra={
                "event": "input_classified",
                "input_type": result.input_type.value,
                "url_domain": url_domain,
                "has_residual": bool(result.residual_text),
            },
        )
        return result
