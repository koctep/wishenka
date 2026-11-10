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
    "wildberries.ru": "Wildberries",
    "market.yandex.ru": "Яндекс Маркет",
    "yandex.ru": "Яндекс Маркет",
    "lamoda.ru": "Lamoda",
    "avito.ru": "Авито",
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
            r"в наличии|на маркетплейсе|в интернет-магазине).*$"
        ),
        r"\s*[-—–|•]\s*(?:ozon|wildberries|яндекс\s*маркет|вайлдберриз|озон|lamoda|авито).*$",
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

    for known_domain, name in KNOWN_STORES.items():
        if domain == known_domain or domain.endswith("." + known_domain):
            return name
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
            except (json.JSONDecodeError, TypeError):
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
                        price_raw = offers.get("price")
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
    def _find_jsonld_products(data: Any) -> list[dict[str, Any]]:
        """Extract Product schema objects recursively from JSON-LD structure."""
        results: list[dict[str, Any]] = []
        if isinstance(data, dict):
            type_val = data.get("@type")
            if type_val == "Product" or (isinstance(type_val, list) and "Product" in type_val):
                results.append(data)
            for v in data.values():
                results.extend(HtmlMetadataExtractor._find_jsonld_products(v))
        elif isinstance(data, list):
            for item in data:
                results.extend(HtmlMetadataExtractor._find_jsonld_products(item))
        return results
