# Items Domain: Input Parsing, Metadata Extraction, Preview Service, Marketplace Normalization, Piece Accounting, and Network Security

## Overview

The `wishenka.items` package and its integration with `wishenka.wishlists` implement universal wish creation, marketplace URL sanitization, rich asynchronous metadata extraction, resilient anti-bot degradation, enterprise-grade SSRF defense, streaming DoS payload limits, and piece-by-piece inventory accounting for the **Wishlist Service («Вишенка»)** Telegram Mini App.

```text
+----------------------------------------------------------------------------------------------------+
|                                      User Input Entry                                              |
|   (Plain text note, explicit URL https://..., implicit domain ozon.ru/..., or mobile share text)   |
+----------------------------------------------------------------------------------------------------+
                                                   |
                                                   v
+----------------------------------------------------------------------------------------------------+
|                          UniversalInputClassifier.classify(raw_text)                               |
|   - Output: InputClassificationResult (input_type, normalized_url, residual_text)                  |
+----------------------------------------------------------------------------------------------------+
                                                   |
                     +-----------------------------+-----------------------------+
                     | PLAIN_TEXT                                                | URL / COMPOSITE_SHARE
                     v                                                           v
+-----------------------------------------+         +------------------------------------------------+
|       ItemPreviewDTO (Manual Entry)     |         |     Marketplace URL Sanitizer (clean_url)      |
|   - title = residual_text               |         |  - Strip utm_*, clid, from=share*, tracking    |
|   - is_fallback = False                 |         +------------------------------------------------+
+-----------------------------------------+                                  |
                                                                             v
                                                    +------------------------------------------------+
                                                    |            UrlMetadataService                  |
                                                    |  - Scheme Check (http / https only)            |
                                                    |  - Async DNS Resolution (getaddrinfo)          |
                                                    |  - SSRF IP Validation (is_ip_safe)             |
                                                    |  - SSRFSafeTransport (Redirect Hops Check)     |
                                                    +------------------------------------------------+
                                                              |                             |
                                               SSRF / Bad IP  |                             | Destination Safe
                                                              v                             v
                                            +---------------------------+   +--------------------------------+
                                            | SSRFBlockedError / Scheme |   | Streaming HTTP Response Body   |
                                            | Graceful Fallback Preview |   | - Early Content-Length <= 2 MB |
                                            | - fallback_reason =       |   | - Stream chunk count <= 2 MB   |
                                            |   "ssrf_blocked"          |   +--------------------------------+
                                            | - is_fallback = True      |             |              |
                                            +---------------------------+             |              |
                                                                          > 2 MB Body |              | Body <= 2 MB
                                                                                      v              v
                                            +---------------------------+   +--------------------------------+
                                            | ResponseBodyTooLargeError |   | Anti-Bot Challenge / Error?    |
                                            | Graceful Fallback Preview |   | (403/429/503/WAF/Turnstile/    |
                                            | - fallback_reason =       |   |  Qrator challenge signatures)  |
                                            |   "response_too_large"    |   +--------------------------------+
                                            | - is_fallback = True      |             |              |
                                            +---------------------------+      YES    |              | NO (200 OK)
                                                                                      v              v
                                                                        +---------------------+  +-------------------+
                                                                        | Graceful Fallback   |  | HtmlMetadata      |
                                                                        | - is_fallback=True  |  |   Extractor       |
                                                                        | - anti_bot/timeout  |  | - JSON-LD @graph  |
                                                                        | - clean url, store  |  | - AggregateOffer  |
                                                                        +---------------------+  | - OpenGraph       |
                                                                                                 | - Microdata       |
                                                                                                 | - HTML Fallback   |
                                                                                                 +-------------------+
                                                                                                           |
                                                                                                           v
                                                                                                 +-------------------+
                                                                                                 | Rich Preview DTO  |
                                                                                                 | - cleaned title   |
                                                                                                 | - parsed price    |
                                                                                                 | - currency, image |
                                                                                                 | - store name/icon |
                                                                                                 +-------------------+
```

### Key Capabilities

1. **Universal Input Classification**:
   - Accurately classifies user inputs into four distinct types:
     - `PLAIN_TEXT`: Freeform gift description or wish note without hyperlinks.
     - `EXPLICIT_URL`: Direct link containing protocol scheme (`https://...` or `http://...`).
     - `IMPLICIT_URL`: Domain-style link pasted without protocol (e.g. `ozon.ru/product/...`), automatically normalized with `https://`.
     - `COMPOSITE_SHARE`: Mobile OS "Share" text containing both a link and surrounding commentary (e.g. `Посмотри кроссовки https://ozon.ru/t/123 классная модель!`). Extracts the URL while isolating `residual_text`.
2. **Marketplace Normalization & URL Sanitization**:
   - Strips affiliate, tracking, and marketing query parameters (`utm_*`, `clid`, `from=share*`, `ref`, `fbclid`, `yclid`, etc.) via [`clean_url`](file:///home/src/wishenka/items/marketplaces.py#L29) and [`MarketplaceRegistry`](file:///home/src/wishenka/items/marketplaces.py#L162).
   - Extensible marketplace protocol [`MarketplaceRule`](file:///home/src/wishenka/items/marketplaces.py#L83) with built-in rules for major Russian e-commerce platforms: **Ozon**, **Wildberries**, **Yandex Market**, **Avito**, and **Megamarket**.
   - Resolves canonical store names and platform aliases (e.g. `wb.ru` $\rightarrow$ `Wildberries`, `m.avito.ru` $\rightarrow$ `Авито`).
3. **Server-Side Request Forgery (SSRF) Defense**:
   - Multi-layered defense-in-depth preventing outbound calls to internal infrastructure, local loops, cloud metadata services, and unroutable addresses:
     - Scheme whitelist: strictly `http` and `https` allowed; `file://`, `gopher://`, `ftp://`, etc. rejected early.
     - IP boundary enforcement: blocks IPv4/IPv6 private ranges (RFC 1918), loopbacks (`127.0.0.0/8`, `::1`), link-local (`169.254.0.0/16`, `fe80::/10`), cloud metadata endpoints (`169.254.169.254`), CGNAT (`100.64.0.0/10`), multicast, broadcast, and IPv6-mapped IPv4 representations (`::ffff:127.0.0.1`).
     - Non-blocking asynchronous DNS resolution via `asyncio.get_running_loop().getaddrinfo` with validation across all returned IP addresses.
     - Custom transport [`SSRFSafeTransport`](file:///home/src/wishenka/items/ssrf.py#L209) that inspects every outbound request and every intermediate redirect hop before socket connection.
4. **DoS & Payload Size Limiting (2 MB Hard Ceiling)**:
   - Enforces a strict 2 MB (`2,097,152` bytes) limit on all upstream responses:
     - Fast-fail early rejection on `Content-Length > 2 MB` before downloading response bytes.
     - Streaming chunk accumulation counter (`aiter_bytes`) enforcing the 2 MB ceiling in real time to neutralize chunked transfer encoding bombs (`Transfer-Encoding: chunked`) or infinite streams.
     - Raises [`ResponseBodyTooLargeError`](file:///home/src/wishenka/items/exceptions.py#L56) immediately when breached, aborting network consumption.
5. **Cascading HTML Metadata Extraction with JSON-LD `@graph` & `AggregateOffer`**:
   - Prioritized hierarchical extraction pipeline: **JSON-LD Schema.org Product/Offer** $\rightarrow$ **OpenGraph** (`og:title`, `og:image`, `product:price:amount`) $\rightarrow$ **Microdata** (`itemprop`) $\rightarrow$ **Standard HTML** (`<title>`, `<meta name="description">`, `<link rel="icon">`).
   - Recursively traverses complex JSON-LD `@graph` trees and matches both standard `Product` and full Schema.org URI types (`https://schema.org/Product`).
   - Extracts pricing from both simple `Offer` and `AggregateOffer` structures (extracting `lowPrice`, `highPrice`, or `price`).
   - Cleans store advertising noise and marketing slogans from titles using regex patterns (e.g. stripping `— купить в интернет-магазине Ozon`, `в наличии на маркетплейсе`).
   - Normalizes currency symbols (`₽`, `руб`, `₸`, `Br`, `$`, `€`, `£`, `¥`) to standard ISO 4217 uppercase codes.
6. **Anti-Bot & Threat Graceful Fallback**:
   - Zero-crash degradation on SSRF blocks, oversized payloads, anti-bot gates (Cloudflare Turnstile, Qrator, DDoS-GUARD, WAF signatures, HTTP 403 Forbidden, HTTP 429 Too Many Requests, HTTP 503 Service Unavailable), and network timeouts (4.0s total, 2.0s connect).
   - Rather than returning 500 server errors, emits a valid fallback [`ItemPreviewDTO`](file:///home/src/wishenka/items/schemas.py#L11-L24) populated with the clean sanitized URL, recognized store name, and extracted residual title for seamless manual entry.
7. **Piece Accounting & Multi-Quantity Invariants**:
   - Desired quantity boundary: $1 \le \text{desired} \le 1000$.
   - Available piece calculation:
     $$\text{available} = \max(0, \text{desired} - \text{reserved} - \text{fulfilled})$$
   - **Reduction Lock Invariant**: A user cannot reduce `desired` quantity below already locked units ($\text{reserved} + \text{fulfilled}$). Attempting to do so raises [`CannotReduceQuantityBelowReservedError`](file:///home/src/wishenka/wishlists/exceptions.py#L40-L42).
   - **Surprise Invariant**: Gift recipients receive [`WishItemRecipientViewDTO`](file:///home/src/wishenka/wishlists/schemas.py#L14-L35) strictly devoid of reservation statuses, gifter identities, or booked quantities.

---

## Architecture & Components

The items subsystem consists of seven core architectural building blocks:

### 1. [`UniversalInputClassifier`](file:///home/src/wishenka/items/classifier.py#L24-L105)

Located in [`wishenka/items/classifier.py`](file:///home/src/wishenka/items/classifier.py).

Responsible for pure string classification and URL normalization without performing network operations.
- Regex pattern [`EXPLICIT_URL_REGEX`](file:///home/src/wishenka/items/classifier.py#L15) detects `https?://` schemes.
- Regex pattern [`DOMAIN_URL_REGEX`](file:///home/src/wishenka/items/classifier.py#L18-L21) matches popular e-commerce TLDs (`.ru`, `.com`, `.org`, `.net`, `.by`, `.kz`, `.io`, `.me`, `.app`, `.store`, `.shop`, `.market`, `.su`) and prepends `https://`.
- Strips matched URL substrings and consolidates surrounding whitespace into `residual_text`.

### 2. Marketplace Rule Registry & URL Normalization (`wishenka.items.marketplaces`)

Located in [`wishenka/items/marketplaces.py`](file:///home/src/wishenka/items/marketplaces.py).

Handles marketplace-specific store identification, URL cleaning, and affiliate tracking parameter removal:

- **Tracking Parameter Sanitization ([`clean_url`](file:///home/src/wishenka/items/marketplaces.py#L29-L80))**:
  - Parses query string parameters preserving non-tracking keys.
  - Strips prefixes starting with `utm_` (e.g. `utm_source`, `utm_medium`, `utm_campaign`).
  - Strips share parameters such as `from=share*` or any `from` query value containing `share`.
  - Strips common affiliate and ad click identifiers: `targeturl`, `clid`, `src`, `promo`, `track`, `_ref`, `ref`, `fbclid`, `gclid`, `yclid`, `dclid`, `sub_id`, `_bqv_`.
  - Preserves essential e-commerce routing keys (e.g. product IDs, SKU parameters, variant queries).
  - Emits structured log event `marketplace_url_cleaned` recording removed parameter names without exposing sensitive query values.
- **Protocol [`MarketplaceRule`](file:///home/src/wishenka/items/marketplaces.py#L83-L97)**:
  - Runtime checkable protocol specifying:
    - `domains: tuple[str, ...]`: List of domain names and regional aliases.
    - `store_name: str`: Canonical human-readable brand name.
    - `store_icon_url: str | None`: Optional URL to storefront branding asset.
    - `matches(domain: str) -> bool`: Domain matching predicate (supports subdomains and domain aliases).
    - `clean_url(url: str) -> str`: Normalization hook for canonicalizing product URLs.
- **Base Class [`BaseMarketplaceRule`](file:///home/src/wishenka/items/marketplaces.py#L99-L120)**:
  - Reusable implementation matching domain aliases (e.g. stripping `www.`, matching exact domain or ending with `.<domain>`).
- **Standard Marketplace Rules**:
  - [`OzonRule`](file:///home/src/wishenka/items/marketplaces.py#L122-L128): Domains `("ozon.ru", "ozon.by", "ozon.kz")`, store name `"Ozon"`.
  - [`WildberriesRule`](file:///home/src/wishenka/items/marketplaces.py#L130-L136): Domains `("wildberries.ru", "wb.ru")`, store name `"Wildberries"`.
  - [`YandexMarketRule`](file:///home/src/wishenka/items/marketplaces.py#L138-L144): Domains `("market.yandex.ru", "yandex.ru")`, store name `"Яндекс Маркет"`.
  - [`AvitoRule`](file:///home/src/wishenka/items/marketplaces.py#L146-L152): Domains `("avito.ru", "m.avito.ru", "avito.st")`, store name `"Авито"`.
  - [`MegamarketRule`](file:///home/src/wishenka/items/marketplaces.py#L154-L160): Domains `("megamarket.ru", "sbermegamarket.ru")`, store name `"Мегамаркет"`.
- **Registry [`MarketplaceRegistry`](file:///home/src/wishenka/items/marketplaces.py#L162-L216)**:
  - Central rule catalog offering `register(rule)`, `get_rule(url_or_domain)`, `clean_url(url)`, and `derive_store_name(url_or_domain)`.
  - Logs `marketplace_rule_matched` (at `DEBUG`) upon successful rule dispatch.

### 3. SSRF Protection Suite (`wishenka.items.ssrf`)

Located in [`wishenka/items/ssrf.py`](file:///home/src/wishenka/items/ssrf.py).

Provides non-blocking IP validation, hostname resolution, and HTTPX transport-level request interception:
- **Constants**:
  - `MAX_RESPONSE_BYTES = 2 * 1024 * 1024` (2 MB).
  - `ALLOWED_SCHEMES = frozenset({"http", "https"})`.
  - `FORBIDDEN_NETWORKS`: tuple of 20 CIDR blocks covering private RFC 1918, CGNAT (`100.64.0.0/10`), loopback (`127.0.0.0/8`, `::1`), link-local (`169.254.0.0/16`, `fe80::/10`), cloud metadata (`169.254.169.254`), multicast (`224.0.0.0/4`, `ff00::/8`), broadcast (`255.255.255.255/32`), and IPv6 ULA (`fc00::/7`).
- [`is_ip_safe(ip)`](file:///home/src/wishenka/items/ssrf.py#L45):
  - Validates `ipaddress.IPv4Address` or `ipaddress.IPv6Address`.
  - Automatically unmaps IPv6-mapped IPv4 addresses (e.g. `::ffff:127.0.0.1` unwraps to `127.0.0.1` and is recursively validated).
  - Checks standard flags: `ip.is_global`, `ip.is_private`, `ip.is_loopback`, `ip.is_link_local`, `ip.is_multicast`, `ip.is_reserved`, `ip.is_unspecified`.
  - Verifies address is not contained within any network in `FORBIDDEN_NETWORKS`.
- [`resolve_and_validate_host(host, port)`](file:///home/src/wishenka/items/ssrf.py#L76):
  - Asynchronously resolves hostnames via `loop.getaddrinfo(clean_host, port, proto=socket.IPPROTO_TCP)` on the running event loop without blocking the async worker thread.
  - If `host` is a direct IP literal, validates it directly.
  - Verifies that **all** resolved IP addresses pass `is_ip_safe`. If any resolved address is restricted, immediately raises [`SSRFBlockedError`](file:///home/src/wishenka/items/exceptions.py#L26).
- [`SSRFSafeTransport`](file:///home/src/wishenka/items/ssrf.py#L209):
  - Subclass of `httpx.AsyncHTTPTransport`.
  - Overrides `handle_async_request(request)`. Intercepts the original request as well as every subsequent request initiated by HTTP redirect hops (`301`, `302`, `303`, `307`, `308`).
  - Rejects disallowed schemes (`InvalidUrlSchemeError`), ensures host is present, and executes `resolve_and_validate_host` prior to forwarding the request to `super().handle_async_request(request)`.

### 4. Safe HTML Fetcher [`UrlMetadataService`](file:///home/src/wishenka/items/fetcher.py#L49)

Located in [`wishenka/items/fetcher.py`](file:///home/src/wishenka/items/fetcher.py).

Dedicated network service responsible for pulling HTML bodies under strict security constraints:
- Enforces `DEFAULT_TIMEOUT` (`4.0s` total, `2.0s` connect) and modern mobile headers (`DEFAULT_HEADERS`).
- **Internal `_fetch_html(url, client=None)`**:
  - Validates URL scheme against `ALLOWED_SCHEMES`.
  - Pre-validates destination host via `resolve_and_validate_host`.
  - If no client is passed, instantiates `httpx.AsyncClient(transport=SSRFSafeTransport(), follow_redirects=True)`.
  - If an external client is injected (e.g. in tests or custom sessions), registers a temporary `request` event hook to guarantee SSRF validation across all redirect steps.
  - Executes streaming download via `_stream_and_read`.
- **Early Fast-Fail & Streaming Accumulator (`_stream_and_read`)**:
  - Checks response header `Content-Length`. If $> 2 \text{ MB}$, immediately aborts and raises [`ResponseBodyTooLargeError`](file:///home/src/wishenka/items/exceptions.py#L56).
  - Iterates asynchronously over chunks via `response.aiter_bytes()`, tracking `total_bytes`. If cumulative size exceeds $2 \text{ MB}$, halts iteration immediately and raises [`ResponseBodyTooLargeError`](file:///home/src/wishenka/items/exceptions.py#L56).
  - Decodes accumulated raw bytes using `response.encoding or "utf-8"` with `errors="replace"`.
- **Safe Fallback Wrapper `fetch_and_extract(url, client=None)`**:
  - High-level interface that calls `_fetch_html` and feeds the result to `HtmlMetadataExtractor.extract`.
  - Catches network, security, and parsing exceptions, logging a warning and returning a safe fallback [`ExtractedMetadata`](file:///home/src/wishenka/items/models.py#L34-L46) populated with `store_name=derive_store_name(url)`.

### 5. Cascading HTML Metadata Extractor [`HtmlMetadataExtractor`](file:///home/src/wishenka/items/parser.py#L195-L456)

Located in [`wishenka/items/parser.py`](file:///home/src/wishenka/items/parser.py).

Parses HTML documents using `BeautifulSoup4` with a multi-level fallback cascade:
- **1. JSON-LD Cascade (`_find_jsonld_products`)**:
  - Traverses `<script type="application/ld+json">` elements.
  - Recursively unrolls `@graph` containers, searching for nodes where `@type` is `"Product"` or `https://schema.org/Product`.
  - Extracts title (`name`), description (`description`), image (`image`), and brand (`brand`).
  - Supports both standard `Offer` and `AggregateOffer` price extraction (`offers.price`, `offers.lowPrice`, `offers.highPrice`), recording `jsonld_aggregate_offer_extracted`.
- **2. OpenGraph Cascade**:
  - Scrapes `meta[property="og:*"]` (`og:title`, `og:description`, `og:image`, `og:site_name`) and `meta[property="product:*"]` (`product:price:amount`, `product:price:currency`).
- **3. Microdata Cascade**:
  - Scrapes elements with `[itemprop="name"]`, `[itemprop="description"]`, `[itemprop="image"]`, `[itemprop="price"]`, and `[itemprop="priceCurrency"]`.
- **4. Standard HTML Fallback**:
  - Scrapes `<title>`, `<meta name="description">`, and `<link rel="icon">`.
- **Sanitization Helpers**:
  - [`clean_title`](file:///home/src/wishenka/items/parser.py#L59-L75): Removes store advertising noise and marketing suffixes (e.g. `— купить в интернет-магазине Ozon`, `на маркетплейсе Wildberries`, `объявление на Авито`).
  - [`parse_price`](file:///home/src/wishenka/items/parser.py#L77-L110): Handles non-breaking spaces (`\xa0`), mixed European/Russian decimal separators, and casts values to integer minor units.
  - [`normalize_currency`](file:///home/src/wishenka/items/parser.py#L112-L123): Normalizes currency symbols (`₽`, `руб`, `rub`, `$`, `€`, `₸`, `kzt`, `byn`, `£`, `¥`) to ISO 4217 uppercase codes (`RUB`, `USD`, `EUR`, `KZT`, `BYN`, `GBP`, `CNY`), defaulting to `RUB`.
  - [`derive_store_name`](file:///home/src/wishenka/items/parser.py#L138-L167): Resolves store name via priority: OpenGraph `og:site_name` $\rightarrow$ brand $\rightarrow$ `KNOWN_STORES` domain map $\rightarrow$ [`MarketplaceRegistry.derive_store_name`](file:///home/src/wishenka/items/marketplaces.py#L210) $\rightarrow$ clean domain.

### 6. Link Preview Orchestrator & Graceful Fallback [`ItemPreviewService`](file:///home/src/wishenka/items/service.py#L38-L387)

Located in [`wishenka/items/service.py`](file:///home/src/wishenka/items/service.py).

Asynchronous facade orchestrating input classification, URL cleaning, secure fetching, anti-bot detection, and graceful degradation:
- Accepts optional `url_metadata_service` in `__init__` for dependency injection.
- Invokes `UniversalInputClassifier.classify(raw_input)`.
  - For `PLAIN_TEXT`, returns manual entry preview immediately without network activity.
  - For `EXPLICIT_URL`, `IMPLICIT_URL`, and `COMPOSITE_SHARE`, sanitizes the target link via `clean_url` and dispatches safe preview fetching.
- **Anti-Bot Challenge & WAF Detection**:
  - Inspects upstream HTTP status codes: HTTP 403 Forbidden, HTTP 429 Too Many Requests, and HTTP 503 Service Unavailable.
  - Scans HTML bodies against `CHALLENGE_SIGNATURES`:
    - Cloudflare challenges: `_cf_chl_opt`, `challenge-running`, `just a moment...`, `cf-mitigated`, `turnstile`, `checking your browser`.
    - Generic WAFs: `access denied`, `waf`, `ddos-guard`.
    - Qrator anti-bot shield: `qrator`, `qrator_jsid`, `qrator-js`.
  - Intercepts challenges and emits `item_preview_anti_bot` and `anti_bot_challenge_detected` logs, returning an `ItemPreviewDTO` with `is_fallback=True` and `fallback_reason="anti_bot_challenge"`.
- **Comprehensive Exception Trap**:
  - SSRF violations: `fallback_reason="ssrf_blocked"`.
  - Payload overflow (>2 MB): `fallback_reason="response_too_large"`.
  - Upstream timeout (>4.0s): `fallback_reason="timeout"`.
  - Other network / HTTP errors: `fallback_reason="http_error"`.
- Prevents unhandled 500 errors and ensures Telegram Mini App users always retain access to a functional manual wish entry form with extracted residual title and clean URL.

### 7. Multi-Quantity Integration in [`wishenka.wishlists`](file:///home/src/wishenka/wishlists/service.py#L1-L320)

Located in [`wishenka/wishlists/models.py`](file:///home/src/wishenka/wishlists/models.py) and [`wishenka/wishlists/service.py`](file:///home/src/wishenka/wishlists/service.py):
- Extends [`WishItem`](file:///home/src/wishenka/wishlists/models.py#L78-L127) with dynamic properties:
  - `reserved_quantity`: Sum of `quantity` across all active reservations.
  - `available_quantity`: `max(0, quantity - received_quantity - reserved_quantity)`.
  - `desired_quantity` / `fulfilled_quantity`: Explicit business aliases for `quantity` and `received_quantity`.
- [`WishlistService.update_wish_item`](file:///home/src/wishenka/wishlists/service.py#L158-L260): Enforces the reduction invariant `quantity >= reserved_quantity + received_quantity`, raising [`CannotReduceQuantityBelowReservedError`](file:///home/src/wishenka/wishlists/exceptions.py#L40-L42) if violated.
- Projection views strictly separate recipient visibility ([`WishItemRecipientViewDTO`](file:///home/src/wishenka/wishlists/schemas.py#L14-L35)) from gifter visibility ([`WishItemGifterViewDTO`](file:///home/src/wishenka/wishlists/schemas.py#L38-L62)).

---

## Domain Exceptions & Hierarchy

Located in [`wishenka/items/exceptions.py`](file:///home/src/wishenka/items/exceptions.py).

```text
WishlistError
  └── ItemError
        ├── InvalidItemDataError
        └── ItemParsingError
              ├── ResponseBodyTooLargeError
              └── SSRFError
                    ├── SSRFBlockedError
                    └── InvalidUrlSchemeError
```

### Exception Reference

| Exception | Base Class | Key Attributes | Trigger Condition |
| --- | --- | --- | --- |
| [`ItemError`](file:///home/src/wishenka/items/exceptions.py#L10) | `WishlistError` | None | Base exception for all item domain errors. |
| [`InvalidItemDataError`](file:///home/src/wishenka/items/exceptions.py#L14) | `ItemError` | None | Validation failures in item payloads (e.g. quantity $< 1$ or $> 1000$). |
| [`ItemParsingError`](file:///home/src/wishenka/items/exceptions.py#L18) | `ItemError` | None | Base exception for parsing, URL extraction, and network fetch limits. |
| [`SSRFError`](file:///home/src/wishenka/items/exceptions.py#L22) | `ItemParsingError` | None | Base exception for SSRF blocks and URL security violations. |
| [`SSRFBlockedError`](file:///home/src/wishenka/items/exceptions.py#L26) | `SSRFError` | `ip_address`, `host`, `reason` | Host or IP resolves to private, loopback, link-local, cloud metadata, or reserved range. |
| [`InvalidUrlSchemeError`](file:///home/src/wishenka/items/exceptions.py#L43) | `SSRFError` | `scheme` | URL scheme is not `http` or `https` (e.g. `file://`, `ftp://`). |
| [`ResponseBodyTooLargeError`](file:///home/src/wishenka/items/exceptions.py#L56) | `ItemParsingError` | `content_length`, `max_allowed` | Response exceeds 2 MB (`Content-Length` header or streaming chunk limit). |

---

## Domain Models and DTOs

| Model / DTO | Location | Description |
| --- | --- | --- |
| [`InputType`](file:///home/src/wishenka/items/models.py#L7-L13) | `wishenka.items.models` | Enum: `plain_text`, `explicit_url`, `implicit_url`, `composite_share`. |
| [`ItemPriority`](file:///home/src/wishenka/items/models.py#L16-L21) | `wishenka.items.models` | Enum: `low`, `medium`, `high`. |
| [`InputClassificationResult`](file:///home/src/wishenka/items/models.py#L24-L31) | `wishenka.items.models` | Result dataclass with `input_type`, `normalized_url`, `residual_text`, `raw_input`. |
| [`ExtractedMetadata`](file:///home/src/wishenka/items/models.py#L34-L46) | `wishenka.items.models` | Raw parsed fields: `title`, `description`, `image_url`, `price`, `currency`, `store_name`, `store_icon_url`, `raw_html_title`. |
| [`ItemPreviewDTO`](file:///home/src/wishenka/items/schemas.py#L11-L24) | `wishenka.items.schemas` | Pydantic DTO for client preview rendering, including `is_fallback` and `fallback_reason` (`ssrf_blocked`, `response_too_large`, `anti_bot_challenge`, `timeout`, `http_error`). |
| [`MarketplaceRule`](file:///home/src/wishenka/items/marketplaces.py#L83-L97) | `wishenka.items.marketplaces` | Runtime-checkable Protocol for marketplace URL cleaning and store resolution. |
| [`CreateItemDTO`](file:///home/src/wishenka/items/schemas.py#L27-L44) | `wishenka.items.schemas` | Pydantic DTO for creating new items with $1 \le \text{quantity} \le 1000$ validation. |
| [`UpdateItemDTO`](file:///home/src/wishenka/items/schemas.py#L47-L64) | `wishenka.items.schemas` | Pydantic DTO for item mutations with $1 \le \text{quantity} \le 1000$ validation. |

---

## API / Usage

### 1. Classifying User Inputs

Use [`UniversalInputClassifier.classify`](file:///home/src/wishenka/items/classifier.py#L27-L105) to parse raw user text into structured input types:

```python
from wishenka.items.classifier import UniversalInputClassifier
from wishenka.items.models import InputType

# Case A: Plain text note
result = UniversalInputClassifier.classify("Хочу теплый вязаный шарф")
assert result.input_type == InputType.PLAIN_TEXT
assert result.residual_text == "Хочу теплый вязаный шарф"
assert result.normalized_url is None

# Case B: Implicit marketplace domain
result = UniversalInputClassifier.classify("ozon.ru/product/nastolnaya-igra-123456")
assert result.input_type == InputType.IMPLICIT_URL
assert result.normalized_url == "https://ozon.ru/product/nastolnaya-igra-123456"

# Case C: Mobile composite share text
result = UniversalInputClassifier.classify(
    "Глянь какую кружку нашел https://market.yandex.ru/product/998877 синяя"
)
assert result.input_type == InputType.COMPOSITE_SHARE
assert result.normalized_url == "https://market.yandex.ru/product/998877"
assert result.residual_text == "Глянь какую кружку нашел синяя"
```

### 2. Marketplace URL Sanitization & Rule Matching

Use [`clean_url`](file:///home/src/wishenka/items/marketplaces.py#L29) or [`MarketplaceRegistry`](file:///home/src/wishenka/items/marketplaces.py#L162) to strip marketing parameters and resolve stores:

```python
from wishenka.items.marketplaces import MarketplaceRegistry, clean_url

# Stripping marketing and tracking parameters
dirty_url = (
    "https://www.ozon.ru/product/aerogrill-100200/?"
    "utm_source=tg&utm_medium=share&from=share_android&sku=123"
)
cleaned = clean_url(dirty_url)
# Cleaned URL preserves essential query params while removing trackers:
assert cleaned == "https://www.ozon.ru/product/aerogrill-100200/?sku=123"

# Resolving store name via MarketplaceRegistry
store = MarketplaceRegistry.derive_store_name("https://wb.ru/catalog/123/detail.aspx")
assert store == "Wildberries"

# Looking up specific marketplace rule
rule = MarketplaceRegistry.get_rule("market.yandex.ru")
assert rule is not None
assert rule.store_name == "Яндекс Маркет"
```

### 3. Generating Link Previews with SSRF & Anti-Bot Fallback

Use [`ItemPreviewService.fetch_preview`](file:///home/src/wishenka/items/service.py#L58-L377) (or alias `.preview(...)`):

```python
from wishenka.items.service import ItemPreviewService

service = ItemPreviewService()

# 1. Successful public preview scrape
preview = await service.fetch_preview("https://example.com/product/aerogrill")
if not preview.is_fallback:
    print(f"Title: {preview.title}")
    print(f"Price: {preview.price} {preview.currency}")
    print(f"Image: {preview.image_url}")
    print(f"Store: {preview.store_name}")
else:
    # 2. Handled degradation (SSRF, Oversized Payload, Anti-Bot, Timeout)
    print(f"Graceful degradation: {preview.fallback_reason}")
    print(f"Manual entry title: {preview.title or 'Enter title manually'}")

# Example: Anti-bot challenge (e.g. Cloudflare Turnstile, Qrator, or 403 Forbidden)
bot_preview = await service.fetch_preview("https://ozon.ru/product/protected-item-123")
if bot_preview.is_fallback:
    assert bot_preview.fallback_reason == "anti_bot_challenge"
    assert bot_preview.store_name == "Ozon"
    assert bot_preview.url == "https://ozon.ru/product/protected-item-123"

# Example: SSRF attempt degrades smoothly to fallback
ssrf_preview = await service.fetch_preview("http://169.254.169.254/latest/meta-data")
assert ssrf_preview.is_fallback is True
assert ssrf_preview.fallback_reason == "ssrf_blocked"
```

### 4. Cascading Metadata Parsing with JSON-LD `@graph` and `AggregateOffer`

Use [`HtmlMetadataExtractor.extract`](file:///home/src/wishenka/items/parser.py#L198-L419):

```python
from wishenka.items.parser import HtmlMetadataExtractor

html_content = """
<!DOCTYPE html>
<html>
<head>
    <script type="application/ld+json">
    {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebPage",
                "name": "Category Listing"
            },
            {
                "@type": "Product",
                "name": "Электрогриль Tefal — купить в интернет-магазине Ozon",
                "image": "https://cdn.example.com/grill.jpg",
                "offers": {
                    "@type": "AggregateOffer",
                    "lowPrice": "4990",
                    "highPrice": "6500",
                    "priceCurrency": "RUB"
                }
            }
        ]
    }
    </script>
</head>
<body></body>
</html>
"""

metadata = HtmlMetadataExtractor.extract(html_content, base_url="https://ozon.ru/product/grill")
assert metadata.title == "Электрогриль Tefal"  # Noise suffix cleanly stripped
assert metadata.price == 4990  # Extracted from lowPrice in AggregateOffer
assert metadata.currency == "RUB"
assert metadata.store_name == "Ozon"
```

### 5. Direct HTML Fetching with SSRF and Size Bounds

Use [`UrlMetadataService`](file:///home/src/wishenka/items/fetcher.py#L49) for lower-level safe fetching:

```python
from wishenka.items.exceptions import ResponseBodyTooLargeError, SSRFBlockedError
from wishenka.items.fetcher import UrlMetadataService

fetcher = UrlMetadataService()

# Safe high-level extraction (never raises, returns ExtractedMetadata)
metadata = await fetcher.fetch_and_extract("https://example.com/product/123")
print(metadata.title, metadata.price, metadata.store_name)

# Low-level fetching with explicit security exception handling
try:
    html_text, effective_url = await fetcher._fetch_html("http://127.0.0.1:8080/admin")
except SSRFBlockedError as exc:
    print(f"Blocked SSRF target: {exc.host} ({exc.ip_address}) - reason: {exc.reason}")
except ResponseBodyTooLargeError as exc:
    print(f"Payload exceeded {exc.max_allowed} bytes (actual: {exc.content_length})")
```

### 6. Direct IP and Hostname Validation

Use [`is_ip_safe`](file:///home/src/wishenka/items/ssrf.py#L45) and [`resolve_and_validate_host`](file:///home/src/wishenka/items/ssrf.py#L76):

```python
import ipaddress
from wishenka.items.exceptions import SSRFBlockedError
from wishenka.items.ssrf import is_ip_safe, resolve_and_validate_host

# Direct IP checks
assert is_ip_safe("93.184.216.34") is True  # Public IP (example.com)
assert is_ip_safe("127.0.0.1") is False  # Loopback
assert is_ip_safe("10.0.0.1") is False  # RFC 1918 Private
assert is_ip_safe("169.254.169.254") is False  # Cloud metadata / Link-local
assert is_ip_safe("100.64.0.1") is False  # CGNAT
assert is_ip_safe("::ffff:127.0.0.1") is False  # IPv6-mapped IPv4 loopback

# Asynchronous DNS resolution check
resolved_ips = await resolve_and_validate_host("example.com", port=443)
assert len(resolved_ips) > 0

try:
    await resolve_and_validate_host("localhost", port=80)
except SSRFBlockedError as exc:
    print(f"Hostname blocked: {exc.host} resolves to {exc.ip_address}")
```

### 7. Managing Multi-Quantity Items in Wishlists

Items are created and updated through [`WishlistService`](file:///home/src/wishenka/wishlists/service.py#L17-L320):

```python
from wishenka.wishlists.exceptions import CannotReduceQuantityBelowReservedError
from wishenka.wishlists.models import TelegramUser
from wishenka.wishlists.service import WishlistService

service = WishlistService()
owner = TelegramUser(telegram_id=101, username="alice")
gifter = TelegramUser(telegram_id=202, username="bob")

# Create wishlist and item with desired quantity = 5
wishlist = service.create_wishlist(owner_id=owner.telegram_id, title="Birthday Wishlist")
item = service.add_wish_item(
    actor=owner,
    wishlist_id=wishlist.id,
    title="Board Game Sets",
    quantity=5,
    price=2500,
)

assert item.desired_quantity == 5
assert item.available_quantity == 5

# Gifter reserves 2 units
service.reserve_item(actor=gifter, item_id=item.id, quantity=2)
assert item.reserved_quantity == 2
assert item.available_quantity == 3

# Attempting to reduce quantity below reserved (e.g. to 1) raises exception
try:
    service.update_wish_item(actor=owner, item_id=item.id, quantity=1)
except CannotReduceQuantityBelowReservedError as exc:
    print(f"Validation rejected: {exc}")

# Valid update: increase or reduce down to locked threshold
service.update_wish_item(actor=owner, item_id=item.id, quantity=3)
assert item.desired_quantity == 3
assert item.available_quantity == 1
```

---

## Configuration & Security Constants

### Network & Security Settings

Defined in [`wishenka/items/ssrf.py`](file:///home/src/wishenka/items/ssrf.py), [`wishenka/items/fetcher.py`](file:///home/src/wishenka/items/fetcher.py), and [`wishenka/items/marketplaces.py`](file:///home/src/wishenka/items/marketplaces.py):

| Constant | Value | Description |
| --- | --- | --- |
| `MAX_RESPONSE_BYTES` | `2 * 1024 * 1024` (2 MB) | Maximum permitted response size before abortion. |
| `ALLOWED_SCHEMES` | `frozenset({"http", "https"})` | Whitelisted URL schemes. |
| `DEFAULT_TIMEOUT` | `httpx.Timeout(4.0, connect=2.0)` | Total budget `4.0s`, connection budget `2.0s`. |
| `DEFAULT_HEADERS` | iOS Safari Mobile UA, Ru/En Accept | Standard headers maximizing storefront compatibility. |
| `TRACKING_QUERY_PREFIXES` | `("utm_",)` | Prefixes stripped from URL queries. |
| `TRACKING_QUERY_KEYS` | Set of 14 ad click / affiliate keys | Query keys stripped (`clid`, `targeturl`, `src`, `promo`, `track`, `ref`, `fbclid`, `gclid`, `yclid`, etc.). |

### Forbidden Network CIDRs (`FORBIDDEN_NETWORKS`)

The following subnets are hard-blocked from outbound connections:
- `0.0.0.0/8` (Current network)
- `10.0.0.0/8` (Private RFC 1918)
- `100.64.0.0/10` (Shared Address Space / CGNAT)
- `127.0.0.0/8` (IPv4 Loopback)
- `169.254.0.0/16` (IPv4 Link-Local / AWS/GCP/Azure Metadata)
- `172.16.0.0/12` (Private RFC 1918)
- `192.0.0.0/24` (IETF Protocol Assignments)
- `192.0.2.0/24` (TEST-NET-1)
- `192.168.0.0/16` (Private RFC 1918)
- `198.18.0.0/15` (Network Benchmark Tests)
- `198.51.100.0/24` (TEST-NET-2)
- `203.0.113.0/24` (TEST-NET-3)
- `224.0.0.0/4` (IPv4 Multicast)
- `240.0.0.0/4` (Reserved)
- `255.255.255.255/32` (Broadcast)
- `::/128` (IPv6 Unspecified)
- `::1/128` (IPv6 Loopback)
- `fc00::/7` (IPv6 Unique Local Address / ULA)
- `fe80::/10` (IPv6 Link-Local Unicast)
- `ff00::/8` (IPv6 Multicast)

### Structured Audit and Operational Logging

All events are logged via structured extra dictionaries under logger name `"wishenka.items"`:

| Event Name | Level | Key Context Fields | Trigger Condition |
| --- | --- | --- | --- |
| `marketplace_url_cleaned` | `INFO` | `url_domain`, `removed_params_count`, `removed_keys` | Stripped marketing tracking parameters from URL before fetch. |
| `marketplace_rule_matched` | `DEBUG` | `store_name`, `url_domain` | Target URL matched a registered marketplace rule. |
| `jsonld_graph_traversal` | `DEBUG` | `graph_items_count` | Found and traversing JSON-LD `@graph` container. |
| `jsonld_aggregate_offer_extracted` | `DEBUG` | `url_domain`, `offer_price`, `low_price`, `high_price` | Extracted price from Schema.org `AggregateOffer`. |
| `metadata_extraction_started` | `DEBUG` | `url_domain`, `parser_stage="start"` | Commenced HTML parsing and metadata extraction. |
| `metadata_stage_resolved` | `DEBUG` | `url_domain`, `parser_stage` (`json_ld`, `opengraph`) | Intermediate parsing stage successfully resolved fields. |
| `metadata_extraction_completed` | `INFO` | `url_domain`, `duration_ms`, `has_title`, `has_price`, `has_image` | HTML extraction completed; fields resolved. |
| `item_preview_anti_bot` | `WARNING` | `status_code`, `url_domain`, `duration_ms`, `fallback_reason` | Intercepted anti-bot gate (403, 429, 503, Turnstile, Qrator). |
| `anti_bot_challenge_detected` | `INFO` | `status_code`, `url_domain`, `duration_ms`, `fallback_reason` | Telemetry signal for anti-bot degradation monitoring. |
| `item_preview_plain_text` | `DEBUG` | `input_type`, `duration_ms` | Non-URL text input processed without network calls. |
| `item_preview_success` | `INFO` | `url_domain`, `duration_ms`, `input_type`, `is_fallback=False` | Successful link preview retrieval (HTTP 200). |
| `item_preview_ssrf_blocked` | `WARNING` | `url`, `url_domain`, `host`, `ip`, `reason`, `duration_ms` | SSRF attempt caught during preview generation; returns fallback. |
| `item_preview_invalid_scheme` | `WARNING` | `url`, `scheme`, `duration_ms` | Unsupported URL scheme caught; returns fallback. |
| `item_preview_response_too_large` | `WARNING` | `url`, `url_domain`, `content_length`, `max_allowed`, `duration_ms` | Oversized payload caught during preview generation; returns fallback. |
| `item_preview_timeout` | `WARNING` | `url_domain`, `duration_ms`, `fallback_reason="timeout"` | HTTP connection or read timeout ($> 4.0\text{s}$). |
| `item_preview_http_error` | `WARNING` | `status_code`, `url_domain`, `duration_ms`, `fallback_reason="http_error"` | Upstream HTTP $\ge 400$ error handled safely. |
| `item_preview_network_error` | `WARNING` | `url_domain`, `duration_ms`, `fallback_reason="http_error"` | Network transport error handled safely. |
| `item_metadata_parsing_error` | `ERROR` | `url_domain`, `duration_ms`, `fallback_reason="http_error"` | Unexpected HTML parsing failure during extraction. |
| `ssrf_blocked` | `WARNING` | `host`, `ip`, `reason` | Low-level SSRF rejection on outbound connection or redirect. |
| `payload_size_violation` | `WARNING` | `url`, `content_length`, `max_allowed`, `reason` | `Content-Length` or streaming chunks exceed 2 MB. |
| `dns_resolution_start` | `DEBUG` | `host`, `clean_host`, `port` | Starting asynchronous DNS resolution. |
| `dns_resolution_success` | `DEBUG` | `host`, `resolved_ips` | Successfully resolved hostname to safe IPs. |
| `dns_resolution_failed` | `INFO` | `host`, `error` | Host failed to resolve (NXDOMAIN, gaierror). |
| `ssrf_request_dispatch` | `DEBUG` | `url`, `host`, `scheme` | Outbound request verified and dispatched. |
| `url_fetch_success` | `INFO` | `url`, `effective_url`, `bytes` | Successfully streamed and decoded response body. |

### Privacy & Data Protection Guarantees

In accordance with security requirements:
- **No Payload Leaks**: Raw HTML bodies, full upstream responses, and long user notes are never dumped into logs.
- **Tracking Parameter Value Isolation**: URL tracking removal logs list sanitized key names only (`removed_keys=["utm_source"]`), strictly omitting query parameter values that might contain sensitive affiliate IDs or campaign tokens.
- **No Internal IP Leak to Clients**: Client-facing DTOs (`ItemPreviewDTO`) receive generic `fallback_reason="ssrf_blocked"`; internal IP details remain isolated to server audit logs.
- **No Token/Credential Leaks**: URL query parameters with authorization tokens or session cookies are excluded.
- **Clean Domains**: Domains are extracted without ports or query parameters (`url_domain`) for clean metric aggregation.

---

## Troubleshooting

### 1. SSRF Blocked Targets (`fallback_reason="ssrf_blocked"`)
- **Symptom**: `ItemPreviewDTO` returns with `is_fallback=True` and `fallback_reason="ssrf_blocked"`.
- **Cause**: The input URL points to an IP or domain resolving to localhost (`127.0.0.1`, `::1`), private networks (`10.x`, `172.16.x`, `192.168.x`), cloud metadata (`169.254.169.254`), or CGNAT (`100.64.x`).
- **Resolution**: This is the intended security defense. Check the server logs under `event="ssrf_blocked"` or `event="item_preview_ssrf_blocked"` for the exact destination host, resolved IP, and restriction rule. If a legitimate public service was erroneously classified, verify whether its DNS records include private IPs.

### 2. Disallowed URL Schemes (`fallback_reason="ssrf_blocked"`)
- **Symptom**: `fallback_reason="ssrf_blocked"` is returned for links using schemes like `ftp://`, `file://`, or `data:`.
- **Cause**: The system explicitly restricts network requests to `http` and `https`.
- **Resolution**: Only standard web URLs are permitted for link preview extraction. Users can still complete item creation manually.

### 3. Response Body Exceeds 2 MB (`fallback_reason="response_too_large"`)
- **Symptom**: `ItemPreviewDTO` returns with `is_fallback=True` and `fallback_reason="response_too_large"`.
- **Cause**: The target URL serves a response body larger than 2,097,152 bytes (e.g. a high-resolution media file, firmware archive, or bloated uncompressed HTML document).
- **Resolution**: Check the server logs for `event="payload_size_violation"`. The log indicates whether it was rejected early via `content_length_exceeded` or stopped during streaming (`stream_chunk_overflow`). The preview degrades gracefully to manual entry, protecting the worker from OOM failures.

### 4. Anti-Bot Challenge Fallbacks (Cloudflare / Qrator / WAF / Turnstile / 403 / 503)
- **Symptom**: `ItemPreviewDTO` returns with `is_fallback=True` and `fallback_reason="anti_bot_challenge"`.
- **Cause**: The remote store (e.g. Ozon, Wildberries, Avito) uses anti-scraping mitigation returning HTTP 403, 429, 503, or JavaScript challenge pages (`_cf_chl_opt`, `turnstile`, `qrator`, `ddos-guard`).
- **Resolution**: This is the expected design behavior. The frontend receives the fallback preview populated with the sanitized URL, the recognized store name, and the user's residual text, prompting the user to confirm or edit title and price manually. Dedicated official store APIs or headless rendering sidecars can be attached via [WISHENKA-55](https://pypost.atlassian.net/browse/WISHENKA-55).

### 5. Tracking Parameters and Affiliate Link Cleaning
- **Symptom**: User pastes a link containing heavy tracking tokens (`utm_source`, `from=share_android`, `clid`), and the resulting item preview URL has those removed.
- **Cause**: [`clean_url`](file:///home/src/wishenka/items/marketplaces.py#L29) automatically strips marketing parameters to prevent session bloat and tracker leakage.
- **Resolution**: Intended behavior. If a specific e-commerce platform requires an atypical query parameter to display the product properly, register an updated [`MarketplaceRule`](file:///home/src/wishenka/items/marketplaces.py#L83) in [`MarketplaceRegistry`](file:///home/src/wishenka/items/marketplaces.py#L162).

### 6. Unresolved Product Pricing (`price` is `None`)
- **Symptom**: Product title and store name are extracted, but `price` is returned as `None`.
- **Cause**: The remote HTML document loads prices dynamically via client-side JavaScript or hides them in shadow DOM components without standard Schema.org JSON-LD, OpenGraph, or Microdata markup.
- **Resolution**: The user can specify the price manually in the wish creation form. For high-volume stores without server-rendered markup, add store-specific JSON extraction to `wishenka.items.marketplaces`.

### 7. Upstream Timeout Handling
- **Symptom**: `ItemPreviewDTO` returns with `is_fallback=True` and `fallback_reason="timeout"`, and `item_preview_timeout` is logged.
- **Cause**: The remote server failed to respond within `2.0s` connect or `4.0s` total timeout.
- **Resolution**: Check external internet connectivity and upstream store availability. The service will never hang or block the TMA event loop.
