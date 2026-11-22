"""HTML metadata parser, price cleaner, and currency normalizer."""

import json
import logging
import math
import re
import time
from collections.abc import Iterator
from contextvars import ContextVar
from typing import Any
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from wishenka.currency import DEFAULT_CURRENCY
from wishenka.items.models import ExtractedMetadata

logger = logging.getLogger("wishenka.items")

# A discovery-local collector preserves limit events on memo hits without shared state.
_type_limit_collector: ContextVar[list[int] | None] = ContextVar(
    "jsonld_type_limit_collector", default=None
)

CURRENCY_MAP: dict[str, str] = {
    # Russian Ruble (RUB)
    "₽": "RUB",
    "руб": "RUB",
    "руб.": "RUB",
    "рубли": "RUB",
    "рублей": "RUB",
    "rub": "RUB",
    "rur": "RUB",
    # US Dollar (USD)
    "$": "USD",
    "us$": "USD",
    "usd": "USD",
    "доллар": "USD",
    "долларов": "USD",
    # Euro (EUR)
    "€": "EUR",
    "eur": "EUR",
    "евро": "EUR",
    # Kazakhstani Tenge (KZT)
    "₸": "KZT",
    "kzt": "KZT",
    "тг": "KZT",
    "тг.": "KZT",
    "тенге": "KZT",
    # Belarusian Ruble (BYN)
    "byn": "BYN",
    "br": "BYN",
    "бел. руб.": "BYN",
    # British Pound (GBP)
    "£": "GBP",
    "￡": "GBP",
    "gbp": "GBP",
    "gb£": "GBP",
    "uk£": "GBP",
    "фунт": "GBP",
    "фунта": "GBP",
    "фунтов": "GBP",
    "фунт стерлингов": "GBP",
    # Chinese Yuan (CNY)
    "¥": "CNY",
    "￥": "CNY",
    "cny": "CNY",
    "cn¥": "CNY",
    "cn￥": "CNY",
    "rmb": "CNY",
    "元": "CNY",
    "юан": "CNY",
    "юань": "CNY",
    "юаня": "CNY",
    "юаней": "CNY",
    # Japanese Yen (JPY)
    "jpy": "JPY",
    "jp¥": "JPY",
    "jp￥": "JPY",
    "jpy¥": "JPY",
    "円": "JPY",
    "йен": "JPY",
    "йена": "JPY",
    "йены": "JPY",
    "иен": "JPY",
    "иена": "JPY",
    "иены": "JPY",
    "yen": "JPY",
    # Turkish Lira (TRY)
    "₺": "TRY",
    "try": "TRY",
    "tl": "TRY",
    "тл": "TRY",
    "trl": "TRY",
    "лир": "TRY",
    "лира": "TRY",
    "лиры": "TRY",
    "турецкая лира": "TRY",
    # Georgian Lari (GEL)
    "₾": "GEL",
    "ლ": "GEL",
    "gel": "GEL",
    "лари": "GEL",
    "lari": "GEL",
    # Armenian Dram (AMD)
    "֏": "AMD",
    "amd": "AMD",
    "դր": "AMD",
    "դր.": "AMD",
    "драм": "AMD",
    "драма": "AMD",
    "драмов": "AMD",
    "dram": "AMD",
}

_INLINE_PREFIX_CURRENCIES: tuple[tuple[str, str], ...] = (
    ("jpy¥", "JPY"),
    ("jp¥", "JPY"),
    ("jp￥", "JPY"),
    ("cn¥", "CNY"),
    ("cn￥", "CNY"),
    ("gb£", "GBP"),
    ("uk£", "GBP"),
    ("us$", "USD"),
)

_INLINE_SYMBOL_CURRENCIES: tuple[tuple[str, str], ...] = (
    ("円", "JPY"),
    ("元", "CNY"),
    ("₺", "TRY"),
    ("₾", "GEL"),
    ("֏", "AMD"),
    ("£", "GBP"),
    ("￡", "GBP"),
    ("€", "EUR"),
    ("₸", "KZT"),
    ("₽", "RUB"),
    ("$", "USD"),
    ("¥", "CNY"),
    ("￥", "CNY"),
)

_WORD_TOKEN_RE = re.compile(r"[a-zA-Zа-яА-ЯёЁ\u0530-\u058f\u10a0-\u10ff]+")

KNOWN_STORES = {
    "ozon.ru": "Ozon",
    "ozon.by": "Ozon",
    "ozon.kz": "Ozon",
    "wildberries.ru": "Wildberries",
    "wb.ru": "Wildberries",
    "market.yandex.ru": "Яндекс Маркет",
    "yandex.ru": "Яндекс Маркет",
    "lamoda.ru": "Lamoda",
    "avito.ru": "Авито",
    "m.avito.ru": "Авито",
    "aliexpress.ru": "AliExpress",
    "aliexpress.com": "AliExpress",
    "amazon.com": "Amazon",
    "amazon.co.uk": "Amazon",
    "amazon.de": "Amazon",
    "amazon.co.jp": "Amazon",
    "trendyol.com": "Trendyol",
    "taobao.com": "Taobao",
    "jd.com": "JD",
    "dns-shop.ru": "DNS",
    "mvideo.ru": "М.Видео",
    "eldorado.ru": "Эльдорадо",
    "megamarket.ru": "Мегамаркет",
    "sbermegamarket.ru": "Мегамаркет",
}


def clean_title(raw_title: str) -> str:
    """Clean advertising noise and marketplace suffixes from titles."""
    title = raw_title.strip()
    noise_patterns = [
        (
            r"\s*[-—–|•]\s*(?:купить|интернет-магазин|по выгодной цене|"
            r"в наличии|на маркетплейсе|в интернет-магазине|объявление).*$"
        ),
        (
            r"\s*[-—–|•]\s*(?:ozon|wildberries|яндекс\s*маркет|вайлдберриз|"
            r"озон|lamoda|авито|мегамаркет|сбермегамаркет).*$"
        ),
    ]
    for pattern in noise_patterns:
        title = re.sub(pattern, "", title, flags=re.IGNORECASE).strip()
    return title


_NEGATIVE_PREFIX_RE = re.compile(r"^\s*[^0-9a-zA-Zа-яА-ЯёЁ]*[-−]\s*[^0-9a-zA-Zа-яА-ЯёЁ]*$")
_NEGATIVE_CURRENCY_PREFIX_RE = re.compile(r"[-−]\s*(?:[A-Za-z]{3}\s*)?[^\w\d]*$")
_NEGATIVE_NAMED_CURRENCY_RE = re.compile(
    r"[-−]\s*(?:" + "|".join(re.escape(token) for token in CURRENCY_MAP) + r")\s*$",
    re.IGNORECASE,
)
_WHITESPACE_RE = re.compile(r"[\s\xa0\u202f\u2009\u2007]+")


def parse_decimal_price(raw_price: Any) -> float | None:
    """Clean and convert localized string or numeric price to an exact positive float (> 0)."""
    if raw_price is None or isinstance(raw_price, bool):
        return None
    if isinstance(raw_price, (int, float)):
        val = float(raw_price)
        return val if math.isfinite(val) and val > 0 else None

    text = _WHITESPACE_RE.sub(" ", str(raw_price)).strip()
    if not text:
        return None

    match = re.search(r"(\d+(?:[\s.,]\d+)*)", text)
    if not match:
        return None

    prefix = text[: match.start()]
    if (
        _NEGATIVE_PREFIX_RE.match(prefix)
        or _NEGATIVE_CURRENCY_PREFIX_RE.search(prefix)
        or _NEGATIVE_NAMED_CURRENCY_RE.search(prefix)
    ):
        return None

    num_str = match.group(1).replace(" ", "")
    if "," in num_str and "." in num_str:
        if num_str.rfind(".") > num_str.rfind(","):
            num_str = num_str.replace(",", "")
        else:
            num_str = num_str.replace(".", "").replace(",", ".")
    elif "," in num_str:
        parts = num_str.split(",")
        if len(parts) == 2:
            if len(parts[1]) in (1, 2):
                num_str = f"{parts[0]}.{parts[1]}"
            elif len(parts[1]) == 3 and parts[0].lstrip("0") != "":
                num_str = f"{parts[0]}{parts[1]}"
            elif len(parts[1]) == 3:
                num_str = f"{parts[0]}.{parts[1]}"
            else:
                num_str = num_str.replace(",", "")
        elif len(parts[-1]) in (1, 2):
            num_str = "".join(parts[:-1]) + "." + parts[-1]
        else:
            num_str = "".join(parts)
    elif "." in num_str:
        parts = num_str.split(".")
        if len(parts) == 2:
            if len(parts[1]) in (1, 2):
                num_str = f"{parts[0]}.{parts[1]}"
            elif len(parts[1]) == 3 and parts[0].lstrip("0") != "":
                num_str = f"{parts[0]}{parts[1]}"
        elif len(parts[-1]) in (1, 2):
            num_str = "".join(parts[:-1]) + "." + parts[-1]
        else:
            num_str = "".join(parts)

    try:
        val = float(num_str)
    except ValueError:
        return None
    return val if math.isfinite(val) and val > 0 else None


def parse_price(raw_price: Any) -> int | None:
    """Clean and convert string or numeric price representation to positive integer units."""
    val = parse_decimal_price(raw_price)
    if val is None:
        return None
    int_val = int(val)
    return int_val if int_val > 0 else None


def extract_currency(raw_text: Any) -> str | None:
    """Extract normalized 3-letter ISO 4217 currency code from standalone or inline text."""
    if raw_text is None or isinstance(raw_text, (bool, int, float)):
        return None
    text = str(raw_text).strip()
    if not text:
        return None

    lower = text.lower()
    if lower in CURRENCY_MAP:
        return CURRENCY_MAP[lower]
    stripped_dot = lower.rstrip(".")
    if stripped_dot in CURRENCY_MAP:
        return CURRENCY_MAP[stripped_dot]

    if len(text) == 3 and text.isascii() and text.isalpha():
        return text.upper()

    for prefix, iso_code in _INLINE_PREFIX_CURRENCIES:
        if prefix in lower:
            return iso_code

    for token in _WORD_TOKEN_RE.findall(lower):
        if token in CURRENCY_MAP:
            return CURRENCY_MAP[token]

    for symbol, iso_code in _INLINE_SYMBOL_CURRENCIES:
        if symbol in text:
            return iso_code

    return None


def normalize_currency(
    raw_currency: str | None,
    *,
    fallback_text: Any = None,
) -> str:
    """Normalize raw currency symbol, code, or fallback price text into ISO 4217 uppercase code."""
    if raw_currency and isinstance(raw_currency, str):
        cleaned = raw_currency.strip()
        if cleaned in ("¥", "￥"):
            if fallback_text is not None:
                fallback_iso = extract_currency(fallback_text)
                if fallback_iso in ("JPY", "CNY"):
                    return fallback_iso
            return "CNY"
        extracted = extract_currency(cleaned)
        if extracted is not None:
            return extracted

    if fallback_text is not None:
        fallback_iso = extract_currency(fallback_text)
        if fallback_iso is not None:
            logger.debug(
                "Extracted inline currency %s from fallback price text",
                fallback_iso,
                extra={
                    "event": "inline_currency_extracted",
                    "currency": fallback_iso,
                },
            )
            return fallback_iso

    if raw_currency and isinstance(raw_currency, str) and raw_currency.strip():
        logger.debug(
            "Unrecognized currency token; falling back to %s",
            DEFAULT_CURRENCY,
            extra={
                "event": "currency_fallback_default",
                "currency": DEFAULT_CURRENCY,
            },
        )
    return DEFAULT_CURRENCY


def extract_domain(url: str | None) -> str | None:
    """Extract clean domain without port or www prefix for observability."""
    if not url:
        return None
    try:
        domain = urlsplit(url).netloc.lower().split(":")[0]
        if domain.startswith("www."):
            domain = domain[4:]
        return domain if domain else None
    except Exception:
        return None


def derive_store_name(
    base_url: str,
    og_site_name: str | None = None,
    brand: str | None = None,
) -> str:
    """Determine store name from OpenGraph site name, brand, or domain mapping."""
    if og_site_name and og_site_name.strip():
        return og_site_name.strip()

    domain = extract_domain(base_url) or ""

    if brand and brand.strip():
        return brand.strip()

    # Check known stores first (including aliases)
    for known_domain, name in KNOWN_STORES.items():
        if domain == known_domain or domain.endswith("." + known_domain):
            return name

    try:
        from wishenka.items.marketplaces import MarketplaceRegistry

        reg_name = MarketplaceRegistry.derive_store_name(base_url)
        if reg_name:
            return reg_name
    except ImportError:
        pass

    return domain


def _get_attr(tag: Any, attr: str) -> str | None:
    """Safely extract string attribute from BeautifulSoup Tag."""
    if tag is None:
        return None
    val = tag.get(attr)
    if val is None:
        return None
    if isinstance(val, (list, tuple)):
        val = val[0] if val else None
    if val is not None:
        res = str(val).strip()
        return res if res else None
    return None


def _get_text(tag: Any) -> str | None:
    """Safely extract text from BeautifulSoup Tag."""
    if tag is None:
        return None
    text = tag.get_text()
    if text:
        res = text.strip()
        return res if res else None
    return None


class HtmlMetadataExtractor:
    """Cascading HTML metadata extractor for e-commerce products."""

    @classmethod
    def extract(cls, html: str, base_url: str) -> ExtractedMetadata:
        """Extract structured metadata using JSON-LD, OpenGraph, Microdata, and HTML tags."""
        start_time = time.perf_counter()
        url_domain = extract_domain(base_url)
        logger.debug(
            "Started HTML metadata extraction for domain %s (html_len=%d)",
            url_domain,
            len(html),
            extra={
                "event": "metadata_extraction_started",
                "url_domain": url_domain,
                "parser_stage": "start",
            },
        )

        soup = BeautifulSoup(html, "html.parser")

        title: str | None = None
        description: str | None = None
        image_url: str | None = None
        price_raw: Any = None
        currency_raw: str | None = None
        brand_name: str | None = None
        og_site_name: str | None = None
        raw_html_title: str | None = None
        store_icon_url: str | None = None

        # Extract raw <title>
        title_tag = soup.find("title")
        if title_tag and title_tag.string:
            raw_html_title = str(title_tag.string).strip()

        # Extract favicon
        icon_tag = soup.select_one('link[rel*="icon"], link[rel*="apple-touch-icon"]')
        icon_href = _get_attr(icon_tag, "href")
        if icon_href:
            store_icon_url = urljoin(base_url, icon_href)

        # 1. JSON-LD Cascade
        for script in soup.select('script[type="application/ld+json"]'):
            script_text = script.string or script.get_text()
            if not script_text:
                continue
            try:
                data = json.loads(script_text)
            except (json.JSONDecodeError, TypeError, RecursionError):
                logger.debug(
                    "JSON-LD script could not be parsed",
                    extra={"event": "jsonld_parse_skipped"},
                )
                continue

            products = cls._find_jsonld_products(data)
            if products:
                for prod in products:
                    if not title and prod.get("name"):
                        title = str(prod["name"])
                    if not description and prod.get("description"):
                        description = str(prod["description"])
                    if not image_url and prod.get("image"):
                        img = prod["image"]
                        if isinstance(img, list) and img:
                            img = img[0]
                        if isinstance(img, dict):
                            img = img.get("url") or img.get("contentUrl")
                        if img:
                            image_url = str(img)
                    if not brand_name and prod.get("brand"):
                        b = prod["brand"]
                        if isinstance(b, dict):
                            brand_name = b.get("name")
                        elif b:
                            brand_name = str(b)
                    if price_raw is None and prod.get("offers") is not None:
                        extracted_price, extracted_curr = cls._extract_offer_pricing(
                            prod["offers"],
                            url_domain=url_domain,
                        )
                        if extracted_price is not None:
                            price_raw = extracted_price
                            currency_raw = extracted_curr or extract_currency(extracted_price)
                logger.debug(
                    "JSON-LD product metadata extracted for domain %s",
                    url_domain,
                    extra={
                        "event": "metadata_stage_resolved",
                        "url_domain": url_domain,
                        "parser_stage": "json_ld",
                    },
                )
                if title and price_raw is not None:
                    break

        # 2. OpenGraph Cascade
        og_site_tag = soup.select_one('meta[property="og:site_name"]')
        og_site_content = _get_attr(og_site_tag, "content")
        if og_site_content:
            og_site_name = og_site_content

        if not title:
            og_title = soup.select_one('meta[property="og:title"]')
            title = _get_attr(og_title, "content")

        if not description:
            og_desc = soup.select_one('meta[property="og:description"]')
            description = _get_attr(og_desc, "content")

        if not image_url:
            og_img = soup.select_one('meta[property="og:image"], meta[property="og:image:url"]')
            image_url = _get_attr(og_img, "content")

        if price_raw is None:
            og_price = soup.select_one(
                'meta[property="product:price:amount"], meta[property="og:price:amount"], '
                'meta[name="product:price:amount"], meta[name="og:price:amount"]'
            )
            price_raw = _get_attr(og_price, "content")

        if not currency_raw:
            og_curr = soup.select_one(
                'meta[property="product:price:currency"], meta[property="og:price:currency"], '
                'meta[name="product:price:currency"], meta[name="og:price:currency"]'
            )
            currency_raw = _get_attr(og_curr, "content")

        if og_site_name or title or description or image_url or price_raw is not None:
            logger.debug(
                "OpenGraph metadata processed for domain %s",
                url_domain,
                extra={
                    "event": "metadata_stage_resolved",
                    "url_domain": url_domain,
                    "parser_stage": "opengraph",
                },
            )

        # 3. Microdata Cascade
        if not title:
            micro_name = soup.select_one('[itemprop="name"]')
            title = _get_attr(micro_name, "content") or _get_text(micro_name)

        if not description:
            micro_desc = soup.select_one('[itemprop="description"]')
            description = _get_attr(micro_desc, "content") or _get_text(micro_desc)

        if not image_url:
            micro_img = soup.select_one('[itemprop="image"]')
            image_url = _get_attr(micro_img, "src") or _get_attr(micro_img, "content")

        if price_raw is None:
            micro_price = soup.select_one('[itemprop="price"]')
            price_raw = _get_attr(micro_price, "content") or _get_text(micro_price)

        if not currency_raw:
            micro_curr = soup.select_one('[itemprop="priceCurrency"]')
            currency_raw = _get_attr(micro_curr, "content") or _get_text(micro_curr)

        # 4. Standard HTML Fallback
        if not title and raw_html_title:
            title = raw_html_title

        if not description:
            meta_desc = soup.select_one('meta[name="description"]')
            description = _get_attr(meta_desc, "content")

        # Cleaning & Normalization
        clean_name = clean_title(title) if title else None
        cleaned_desc = description.strip() if description else None
        decimal_price = parse_decimal_price(price_raw)
        parsed_price = (
            int(decimal_price)
            if decimal_price is not None and decimal_price.is_integer()
            else decimal_price
        )
        normalized_curr = normalize_currency(currency_raw, fallback_text=price_raw)
        resolved_image = urljoin(base_url, image_url.strip()) if image_url else None
        store = derive_store_name(base_url, og_site_name=og_site_name, brand=brand_name)

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.info(
            "HTML metadata extraction completed for domain %s in %sms (price=%s, currency=%s)",
            url_domain,
            duration_ms,
            parsed_price,
            normalized_curr,
            extra={
                "event": "metadata_extraction_completed",
                "url_domain": url_domain,
                "parser_stage": "complete",
                "duration_ms": duration_ms,
                "has_title": bool(clean_name),
                "has_price": parsed_price is not None,
                "price": parsed_price,
                "currency": normalized_curr,
                "has_image": bool(resolved_image),
            },
        )

        return ExtractedMetadata(
            title=clean_name,
            description=cleaned_desc,
            image_url=resolved_image,
            price=parsed_price,
            currency=normalized_curr,
            store_name=store,
            store_icon_url=store_icon_url,
            raw_html_title=raw_html_title,
        )

    @classmethod
    def _extract_offer_pricing(
        cls,
        offers_node: Any,
        *,
        url_domain: str | None = None,
        inherited_currency: str | None = None,
        _depth: int = 0,
    ) -> tuple[Any, str | None]:
        """Extract first valid positive (price_raw, currency_raw) from Offer, AggregateOffer,
        nested priceSpecification, or multi-offer list/dict structures.
        """
        if _depth > 16 or offers_node is None:
            return None, inherited_currency

        if isinstance(offers_node, list):
            for item in offers_node:
                cand_price, cand_curr = cls._extract_offer_pricing(
                    item,
                    url_domain=url_domain,
                    inherited_currency=inherited_currency,
                    _depth=_depth + 1,
                )
                if cand_price is not None and parse_decimal_price(cand_price) is not None:
                    return cand_price, cand_curr
            return None, inherited_currency

        if isinstance(offers_node, dict):
            raw_curr = offers_node.get("priceCurrency")
            curr = (
                raw_curr.strip()
                if isinstance(raw_curr, str) and raw_curr.strip()
                else inherited_currency
            )

            offer_type = offers_node.get("@type")
            is_aggregate = (
                offer_type == "AggregateOffer"
                or (isinstance(offer_type, str) and offer_type.endswith("/AggregateOffer"))
                or offers_node.get("lowPrice") is not None
                or offers_node.get("highPrice") is not None
            )

            offer_price: Any = None
            for field in ("price", "lowPrice", "minPrice", "highPrice", "maxPrice"):
                val = offers_node.get(field)
                if val is not None and parse_decimal_price(val) is not None:
                    offer_price = val
                    break

            if offer_price is None and offers_node.get("priceSpecification") is not None:
                offer_price, spec_curr = cls._extract_offer_pricing(
                    offers_node["priceSpecification"],
                    url_domain=url_domain,
                    inherited_currency=curr,
                    _depth=_depth + 1,
                )
                if offer_price is not None and spec_curr:
                    curr = spec_curr
                if offer_price is not None:
                    safe_price = format(parse_decimal_price(offer_price) or 0, ".15g")
                    safe_currency = extract_currency(curr)
                    logger.debug(
                        "Extracted priceSpecification price for domain %s (price=%s, currency=%s)",
                        url_domain,
                        safe_price,
                        safe_currency,
                        extra={
                            "event": "jsonld_price_specification_extracted",
                            "url_domain": url_domain,
                            "offer_price": safe_price,
                            "currency": safe_currency,
                        },
                    )

            if offer_price is None and offers_node.get("offers") is not None:
                offer_price, nested_curr = cls._extract_offer_pricing(
                    offers_node["offers"],
                    url_domain=url_domain,
                    inherited_currency=curr,
                    _depth=_depth + 1,
                )
                if offer_price is not None and nested_curr:
                    curr = nested_curr

            if is_aggregate and offer_price is not None:
                safe_price = format(parse_decimal_price(offer_price) or 0, ".15g")
                logger.debug(
                    "Extracted AggregateOffer price for domain %s (price=%s)",
                    url_domain,
                    safe_price,
                    extra={
                        "event": "jsonld_aggregate_offer_extracted",
                        "url_domain": url_domain,
                        "offer_price": safe_price,
                    },
                )

            return offer_price, curr

        return None, inherited_currency

    @staticmethod
    def _walk_product_type(type_val: Any) -> tuple[bool, int]:
        """Inspect types lazily and report the actual peak number of pending records."""
        stack: list[tuple[str, Any, int]] = [("visit", type_val, 0)]
        visited = 0
        peak = 1
        depth_exceeded = False
        while stack:
            action, value, depth = stack.pop()
            if action == "iterate":
                try:
                    item = next(value)
                except StopIteration:
                    continue
                stack.append(("iterate", value, depth))
                action, value = "visit", item
            if visited >= 20_000:
                stack.append((action, value, depth))
                peak = max(peak, len(stack))
                break
            visited += 1
            if depth > 128:
                depth_exceeded = True
            elif isinstance(value, str):
                val = value.strip().lower()
                if val == "product" or val.endswith("/product"):
                    return True, peak
            elif isinstance(value, list):
                stack.append(("iterate", iter(value), depth + 1))
            peak = max(peak, len(stack))
        if depth_exceeded or stack:
            logger.debug(
                "JSON-LD type inspection reached a limit",
                extra={"event": "jsonld_type_limit", "visited_nodes": visited},
            )
            collector = _type_limit_collector.get()
            if collector is not None:
                collector.append(visited)
        return False, peak

    @staticmethod
    def _is_product_type(type_val: Any) -> bool:
        """Check if @type string or list corresponds to Schema.org Product."""
        return HtmlMetadataExtractor._walk_product_type(type_val)[0]

    @staticmethod
    def _walk_jsonld_products(data: Any) -> tuple[list[dict[str, Any]], int]:
        """Discover products with width-independent pending state and a local type memo."""
        results: list[dict[str, Any]] = []
        stack: list[tuple[str, Any, int]] = [("visit", data, 0)]
        # Values retain list objects, avoiding identity reuse during this invocation.
        memo: dict[Any, tuple[Any, bool, int | None]] = {}
        visited = 0
        peak = 1
        depth_exceeded = False
        while stack:
            action, node, depth = stack.pop()
            if action == "iterate":
                iterator: Iterator[Any] = node
                try:
                    child = next(iterator)
                except StopIteration:
                    continue
                stack.append(("iterate", iterator, depth))
                action, node = "visit", child
            if visited >= 20_000:
                stack.append((action, node, depth))
                peak = max(peak, len(stack))
                break
            if action == "process":
                type_val = node.get("@type")
                if isinstance(type_val, list):
                    key: Any = ("list", id(type_val))
                elif type(type_val) in (str, int, float, bool, type(None)):
                    key = (type(type_val), type_val)
                else:
                    key = None
                cached = memo.get(key) if key is not None else None
                if cached is None:
                    limits: list[int] = []
                    token = _type_limit_collector.set(limits)
                    try:
                        matched = HtmlMetadataExtractor._is_product_type(type_val)
                    finally:
                        _type_limit_collector.reset(token)
                    if key is not None and len(memo) < 20_000:
                        memo[key] = (type_val, matched, limits[0] if limits else None)
                else:
                    _, matched, limit_visited = cached
                    if limit_visited is not None:
                        logger.debug(
                            "JSON-LD type inspection reached a limit",
                            extra={"event": "jsonld_type_limit", "visited_nodes": limit_visited},
                        )
                if matched:
                    results.append(node)
                continue
            visited += 1
            if depth > 128:
                depth_exceeded = True
            elif isinstance(node, dict):
                children = (value for key, value in node.items() if key != "@graph")
                stack.append(("iterate", iter(children), depth + 1))
                stack.append(("process", node, depth))
                graph = node.get("@graph")
                if isinstance(graph, (list, dict)):
                    logger.debug(
                        "Traversing JSON-LD @graph container (items=%d)",
                        len(graph),
                        extra={"event": "jsonld_graph_traversal", "graph_items_count": len(graph)},
                    )
                    stack.append(("visit", graph, depth + 1))
            elif isinstance(node, list):
                stack.append(("iterate", iter(node), depth + 1))
            peak = max(peak, len(stack))
        if depth_exceeded or stack:
            logger.debug(
                "JSON-LD discovery reached a limit",
                extra={"event": "jsonld_discovery_limit", "visited_nodes": visited},
            )
        return results, peak

    @staticmethod
    def _find_jsonld_products(data: Any) -> list[dict[str, Any]]:
        """Find products in graph-first order with bounded iterative traversal."""
        return HtmlMetadataExtractor._walk_jsonld_products(data)[0]

    @staticmethod
    def _jsonld_traversal_diagnostics(walk: str, data: Any) -> tuple[Any, int]:
        """Run a traversal and expose its actual per-invocation peak pending records."""
        if walk == "discovery":
            return HtmlMetadataExtractor._walk_jsonld_products(data)
        if walk == "type":
            return HtmlMetadataExtractor._walk_product_type(data)
        raise ValueError(f"Unknown JSON-LD traversal: {walk}")
