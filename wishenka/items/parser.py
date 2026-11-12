"""HTML metadata parser, price cleaner, and currency normalizer."""

import json
import logging
import re
import time
from typing import Any
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from wishenka.items.models import ExtractedMetadata

logger = logging.getLogger("wishenka.items")

CURRENCY_MAP = {
    "₽": "RUB",
    "руб": "RUB",
    "руб.": "RUB",
    "rub": "RUB",
    "rur": "RUB",
    "$": "USD",
    "usd": "USD",
    "€": "EUR",
    "eur": "EUR",
    "₸": "KZT",
    "kzt": "KZT",
    "byn": "BYN",
    "br": "BYN",
    "£": "GBP",
    "gbp": "GBP",
    "¥": "CNY",
    "cny": "CNY",
    "jpy": "JPY",
}

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


def parse_price(raw_price: Any) -> int | None:
    """Clean and convert string or numeric price representation to integer units."""
    if raw_price is None:
        return None
    if isinstance(raw_price, (int, float)):
        return int(raw_price)

    text = str(raw_price).strip().replace("\xa0", " ")
    if not text:
        return None

    match = re.search(r"(\d+(?:[\s.,]\d+)*)", text)
    if not match:
        return None

    num_str = match.group(1).replace(" ", "")
    if "," in num_str and "." in num_str:
        if num_str.rfind(".") > num_str.rfind(","):
            num_str = num_str.replace(",", "")
        else:
            num_str = num_str.replace(".", "").replace(",", ".")
    elif "," in num_str:
        parts = num_str.split(",")
        if len(parts) == 2 and len(parts[1]) in (1, 2):
            num_str = f"{parts[0]}.{parts[1]}"
        else:
            num_str = num_str.replace(",", "")

    try:
        val = float(num_str)
        return int(val)
    except ValueError:
        return None


def normalize_currency(raw_currency: str | None) -> str:
    """Normalize raw currency symbol or string into ISO 4217 uppercase code."""
    if not raw_currency:
        return "RUB"
    cleaned = raw_currency.strip().lower()
    if cleaned in CURRENCY_MAP:
        return CURRENCY_MAP[cleaned]
    upper = raw_currency.strip().upper()
    if len(upper) == 3 and upper.isalpha():
        return upper
    return "RUB"


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
                prod = products[0]
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
                if price_raw is None and prod.get("offers"):
                    offers = prod["offers"]
                    if isinstance(offers, list) and offers:
                        offers = offers[0]
                    if isinstance(offers, dict):
                        offer_type = offers.get("@type")
                        offer_price = offers.get("price")
                        is_aggregate = (
                            offer_type == "AggregateOffer"
                            or (
                                isinstance(offer_type, str)
                                and offer_type.endswith("/AggregateOffer")
                            )
                            or offers.get("lowPrice") is not None
                            or offers.get("highPrice") is not None
                        )
                        if offer_price is None:
                            offer_price = offers.get("lowPrice")
                        if offer_price is None:
                            offer_price = offers.get("highPrice")
                        if is_aggregate:
                            logger.debug(
                                "Extracted AggregateOffer price for domain %s (price=%s)",
                                url_domain,
                                offer_price,
                                extra={
                                    "event": "jsonld_aggregate_offer_extracted",
                                    "url_domain": url_domain,
                                    "offer_price": offer_price,
                                    "low_price": offers.get("lowPrice"),
                                    "high_price": offers.get("highPrice"),
                                },
                            )
                        price_raw = offer_price
                        if not currency_raw:
                            currency_raw = offers.get("priceCurrency")
                logger.debug(
                    "JSON-LD product metadata extracted for domain %s",
                    url_domain,
                    extra={
                        "event": "metadata_stage_resolved",
                        "url_domain": url_domain,
                        "parser_stage": "json_ld",
                    },
                )
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
                'meta[property="product:price:amount"], meta[property="og:price:amount"]'
            )
            price_raw = _get_attr(og_price, "content")

        if not currency_raw:
            og_curr = soup.select_one(
                'meta[property="product:price:currency"], meta[property="og:price:currency"]'
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
        parsed_price = parse_price(price_raw)
        normalized_curr = normalize_currency(currency_raw)
        resolved_image = urljoin(base_url, image_url.strip()) if image_url else None
        store = derive_store_name(base_url, og_site_name=og_site_name, brand=brand_name)

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.info(
            "HTML metadata extraction completed for domain %s in %sms",
            url_domain,
            duration_ms,
            extra={
                "event": "metadata_extraction_completed",
                "url_domain": url_domain,
                "parser_stage": "complete",
                "duration_ms": duration_ms,
                "has_title": bool(clean_name),
                "has_price": parsed_price is not None,
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

    @staticmethod
    def _is_product_type(type_val: Any) -> bool:
        """Check if @type string or list corresponds to Schema.org Product."""
        stack = [(type_val, 0)]
        visited = 0
        depth_exceeded = False
        while stack and visited < 20_000:
            value, depth = stack.pop()
            visited += 1
            if depth > 128:
                depth_exceeded = True
                continue
            if isinstance(value, str):
                val = value.strip().lower()
                if val == "product" or val.endswith("/product"):
                    return True
            elif isinstance(value, list):
                stack.extend((item, depth + 1) for item in reversed(value))
        if depth_exceeded or stack:
            logger.debug(
                "JSON-LD type inspection reached a limit",
                extra={"event": "jsonld_type_limit", "visited_nodes": visited},
            )
        return False

    @staticmethod
    def _find_jsonld_products(data: Any) -> list[dict[str, Any]]:
        """Find products in graph-first order with bounded iterative traversal."""
        results: list[dict[str, Any]] = []
        stack: list[tuple[Any, int, bool]] = [(data, 0, False)]
        visited = 0
        depth_exceeded = False
        while stack and visited < 20_000:
            node, depth, process = stack.pop()
            if process:
                if HtmlMetadataExtractor._is_product_type(node.get("@type")):
                    results.append(node)
                continue
            visited += 1
            if depth > 128:
                depth_exceeded = True
                continue
            if isinstance(node, dict):
                stack.extend(
                    (v, depth + 1, False) for k, v in reversed(list(node.items())) if k != "@graph"
                )
                stack.append((node, depth, True))
                if isinstance(node.get("@graph"), (list, dict)):
                    logger.debug(
                        "Traversing JSON-LD @graph container (items=%d)",
                        len(node["@graph"]),
                        extra={
                            "event": "jsonld_graph_traversal",
                            "graph_items_count": len(node["@graph"]),
                        },
                    )
                    stack.append((node["@graph"], depth + 1, False))
            elif isinstance(node, list):
                stack.extend((item, depth + 1, False) for item in reversed(node))
        if depth_exceeded or stack:
            logger.debug(
                "JSON-LD discovery reached a limit",
                extra={"event": "jsonld_discovery_limit", "visited_nodes": visited},
            )
        return results
