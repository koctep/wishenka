"""Marketplace registry and normalization rules for major e-commerce platforms."""

import logging
from typing import Protocol, runtime_checkable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from wishenka.items.parser import extract_domain

logger = logging.getLogger("wishenka.items")

TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_KEYS = {
    "targeturl",
    "clid",
    "src",
    "promo",
    "track",
    "_ref",
    "ref",
    "fbclid",
    "gclid",
    "yclid",
    "dclid",
    "sub_id",
    "_bqv_",
}


def clean_url(url: str) -> str:
    """Strip marketing tracking parameters (utm_*, clid, from=share*, etc.) from URL."""
    if not url:
        return ""
    stripped = url.strip()
    try:
        parts = urlsplit(stripped)
    except Exception:
        return stripped

    if not parts.scheme or not parts.netloc:
        return stripped

    query_tuples = parse_qsl(parts.query, keep_blank_values=True)
    if not query_tuples:
        return stripped

    cleaned_tuples: list[tuple[str, str]] = []
    removed_keys: list[str] = []
    for key, val in query_tuples:
        key_lower = key.lower()
        val_lower = val.lower()
        if any(key_lower.startswith(prefix) for prefix in TRACKING_QUERY_PREFIXES):
            removed_keys.append(key)
            continue
        if key_lower == "from" and (val_lower.startswith("share") or "share" in val_lower):
            removed_keys.append(key)
            continue
        if key_lower in TRACKING_QUERY_KEYS:
            removed_keys.append(key)
            continue
        cleaned_tuples.append((key, val))

    if removed_keys:
        new_query = urlencode(cleaned_tuples)
        result = urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))
        domain = extract_domain(stripped) or parts.netloc.lower().strip()
        logger.info(
            "Cleaned %d tracking parameter(s) from URL for domain %s",
            len(removed_keys),
            domain,
            extra={
                "event": "marketplace_url_cleaned",
                "url_domain": domain,
                "removed_params_count": len(removed_keys),
                "removed_keys": removed_keys,
            },
        )
        return result

    return stripped


@runtime_checkable
class MarketplaceRule(Protocol):
    """Protocol for marketplace-specific extraction and normalization rules."""

    domains: tuple[str, ...]
    store_name: str
    store_icon_url: str | None

    def matches(self, domain: str) -> bool:
        """Check if rule matches the target domain."""
        ...

    def clean_url(self, url: str) -> str:
        """Strip tracking parameters and normalize canonical product URL."""
        ...


class BaseMarketplaceRule:
    """Base implementation for marketplace rules."""

    domains: tuple[str, ...] = ()
    store_name: str = ""
    store_icon_url: str | None = None

    def matches(self, domain: str) -> bool:
        """Check if rule matches domain or domain alias."""
        if not domain:
            return False
        clean = domain.lower().strip()
        if clean.startswith("www."):
            clean = clean[4:]
        if clean in self.domains:
            return True
        return any(clean.endswith("." + d) for d in self.domains)

    def clean_url(self, url: str) -> str:
        """Strip tracking parameters using general clean_url utility."""
        return clean_url(url)


class OzonRule(BaseMarketplaceRule):
    """Ozon marketplace normalization rule."""

    domains: tuple[str, ...] = ("ozon.ru", "ozon.by", "ozon.kz")
    store_name: str = "Ozon"
    store_icon_url: str | None = None


class WildberriesRule(BaseMarketplaceRule):
    """Wildberries marketplace normalization rule."""

    domains: tuple[str, ...] = ("wildberries.ru", "wb.ru")
    store_name: str = "Wildberries"
    store_icon_url: str | None = None


class YandexMarketRule(BaseMarketplaceRule):
    """Yandex Market normalization rule."""

    domains: tuple[str, ...] = ("market.yandex.ru", "yandex.ru")
    store_name: str = "Яндекс Маркет"
    store_icon_url: str | None = None


class AvitoRule(BaseMarketplaceRule):
    """Avito marketplace normalization rule."""

    domains: tuple[str, ...] = ("avito.ru", "m.avito.ru", "avito.st")
    store_name: str = "Авито"
    store_icon_url: str | None = None


class MegamarketRule(BaseMarketplaceRule):
    """Megamarket normalization rule."""

    domains: tuple[str, ...] = ("megamarket.ru", "sbermegamarket.ru")
    store_name: str = "Мегамаркет"
    store_icon_url: str | None = None


class MarketplaceRegistry:
    """Registry for marketplace rules and domain-to-store lookup."""

    _rules: list[MarketplaceRule] = [
        OzonRule(),
        WildberriesRule(),
        YandexMarketRule(),
        AvitoRule(),
        MegamarketRule(),
    ]

    @classmethod
    def register(cls, rule: MarketplaceRule) -> None:
        """Register a new marketplace rule."""
        cls._rules.append(rule)

    @classmethod
    def get_rule(cls, url_or_domain: str) -> MarketplaceRule | None:
        """Look up marketplace rule by URL or domain string."""
        if not url_or_domain:
            return None
        domain = extract_domain(url_or_domain) or url_or_domain.lower().strip()
        if domain.startswith("www."):
            domain = domain[4:]
        for rule in cls._rules:
            if rule.matches(domain):
                logger.debug(
                    "Marketplace rule '%s' matched for domain %s",
                    rule.store_name,
                    domain,
                    extra={
                        "event": "marketplace_rule_matched",
                        "store_name": rule.store_name,
                        "url_domain": domain,
                    },
                )
                return rule
        return None

    @classmethod
    def clean_url(cls, url: str) -> str:
        """Normalize URL using matching rule or default cleaning."""
        rule = cls.get_rule(url)
        if rule is not None:
            return rule.clean_url(url)
        return clean_url(url)

    @classmethod
    def derive_store_name(cls, url_or_domain: str) -> str | None:
        """Determine store name from registered marketplace rules."""
        rule = cls.get_rule(url_or_domain)
        if rule is not None:
            return rule.store_name
        return None


__all__ = [
    "AvitoRule",
    "MarketplaceRegistry",
    "MarketplaceRule",
    "MegamarketRule",
    "OzonRule",
    "WildberriesRule",
    "YandexMarketRule",
    "clean_url",
]
