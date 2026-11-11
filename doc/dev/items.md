# Items Domain: Input Parsing, Metadata Extraction, Preview Service, Marketplace Normalization, REST CRUD API, Piece Accounting, Safe Archiving, and Network Security

## Overview

The `wishenka.items` package and its integration with `wishenka.wishlists` implement universal wish creation, marketplace URL sanitization, rich asynchronous metadata extraction, resilient anti-bot degradation, enterprise-grade SSRF defense, streaming DoS payload limits, RESTful CRUD lifecycle endpoints, piece-by-piece inventory accounting, atomic reordering, safe archiving, and collaborative gift targeting for the **Wishlist Service («Вишенка»)** Telegram Mini App.

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
8. **RESTful Wish Items CRUD API & Atomic Reordering**:
   - Complete endpoint suite mounted at `/api/wishlists/{wishlist_id}/items` supporting item creation, listing, detail reading, patch updating, atomic reordering, safe archiving, and restoring.
   - Reordering enforces strict 1:1 active permutation integrity: the request must include all active item IDs with zero duplicates, contiguous display indexing ($0, 1, \dots, N-1$), and transactional commit.
9. **Collaborative Wishlist Targeting & Dual-Role Projections**:
   - Items can be designated for specific members via `recipient_user_id` or descriptive `recipient_name`.
   - Access control verifies `recipient_user_id` belongs to the wishlist's active members.
   - Dual-role projection: recipients see clean recipient views (`WishItemRecipientViewDTO`), while collaborators and gifters see full booking and availability states (`WishItemGifterViewDTO`).
10. **Safe Archiving & End-of-List Restoration**:
    - Archiving acts as a non-destructive soft-delete (`is_archived = True`), preserving all active reservations in the database while immediately hiding the item from default listings and blocking new bookings.
    - Restoring reactivates the item (`is_archived = False`) and safely appends it to the tail of the active display order (`display_order = max(active_orders) + 1`).
11. **Telegram Mini App (TMA) HTMX Wish Item UI & BottomSheet Modals**:
    - Server-rendered Jinja2 + HTMX interface mounted at `/web/wishlists/{wishlist_id}` ([`wishenka/web/routes/items_ui.py`](file:///home/src/wishenka/web/routes/items_ui.py)) providing a fixed bottom Universal Quick Add Bar (`partials/item_quick_add.html`), debounced live URL preview card (`partials/item_preview_card.html`), Out-of-Band (`hx-swap-oob`) DOM updates, and a detailed creation/editing bottom-sheet modal (`partials/item_edit_modal.html`) with visual Reduction Lock enforcement and HTTP 409 error recovery.

---

## Architecture & Components

The items subsystem consists of ten core architectural building blocks:

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

### 7. Wish Items Domain Service & Piece Accounting ([`wishenka.wishlists.service`](file:///home/src/wishenka/wishlists/service.py))

Located in [`wishenka/wishlists/service.py`](file:///home/src/wishenka/wishlists/service.py) and [`wishenka/wishlists/models.py`](file:///home/src/wishenka/wishlists/models.py).

Provides transactional domain operations for item lifecycle, piece-by-piece inventory accounting, atomic reordering, safe archiving, and role-based view projection:

- **Piece Accounting Invariants on [`WishItem`](file:///home/src/wishenka/wishlists/models.py)**:
  - `reserved_quantity`: Sum of `quantity` across all reservations in `ACTIVE` or `PURCHASED` status.
  - `available_quantity`: $\max(0, \text{quantity} - \text{received\_quantity} - \text{reserved\_quantity})$.
  - `desired_quantity` / `fulfilled_quantity`: Explicit business aliases for `quantity` and `received_quantity`.
- **Item Creation ([`add_wish_item`](file:///home/src/wishenka/wishlists/service.py#L733))**:
  - Verifies parent wishlist state (mutations blocked on `ARCHIVED` or `DELETED` wishlists via [`WishlistArchivedError`](file:///home/src/wishenka/wishlists/exceptions.py#L18) and [`WishlistDeletedError`](file:///home/src/wishenka/wishlists/exceptions.py#L22)).
  - Checks actor permissions via [`WishlistAccessPolicy.can_add_or_edit_item`](file:///home/src/wishenka/wishlists/service.py#L779).
  - Validates collaborative recipient targeting: if `recipient_user_id` is specified, verifies it exists in active wishlist membership (`{owner_id} | {m.user_id for m in members}`).
  - Automatically calculates next contiguous `display_order = max([it.display_order for it in wl.items], default=-1) + 1`.
  - Emits structured event `item_created`.
- **Item Updates & Reduction Lock Invariant ([`update_wish_item`](file:///home/src/wishenka/wishlists/service.py#L845))**:
  - Row-level concurrency coordination via `async with self._concurrency_coordinator.acquire(item_id):`.
  - Rejects mutations on archived items ([`WishlistArchivedError`](file:///home/src/wishenka/wishlists/exceptions.py#L18)).
  - Enforces the **Reduction Lock Invariant**:
    $$\text{requested\_quantity} \ge \text{reserved\_quantity} + \text{received\_quantity}$$
    If violated, raises [`CannotReduceQuantityBelowReservedError`](file:///home/src/wishenka/wishlists/exceptions.py#L40) and logs `item_quantity_reduction_rejected`.
  - Computes `quantity_delta` and records modified fields list in structured event `item_updated`.
- **Atomic Reordering Protocol ([`reorder_wish_items`](file:///home/src/wishenka/wishlists/service.py#L1044))**:
  - Verifies active wishlist state and caller permissions.
  - Enforces strict 1:1 active permutation integrity:
    1. Zero duplicate IDs allowed (`len(item_ids) == len(set(item_ids))`).
    2. Set equality with active items: `set(item_ids) == {it.id for it in wl.items if not it.is_archived}`.
  - Re-indexes active items contiguously: `item.display_order = order` for `order, it_id in enumerate(item_ids)`.
  - Emits structured event `items_reordered`.
- **Safe Archiving ([`archive_wish_item`](file:///home/src/wishenka/wishlists/service.py#L1130))**:
  - Sets `is_archived = True` and updates `updated_at`.
  - Preserves all active reservations in the database without modification.
  - Hides item from default listings and rejects new reservation or edit attempts.
  - Emits structured event `item_archived` with `active_reservations_count`.
- **Restoration Semantics ([`restore_wish_item`](file:///home/src/wishenka/wishlists/service.py#L1186))**:
  - Sets `is_archived = False`.
  - Re-inserts item at the end of the active list: `display_order = max(active_orders, default=-1) + 1`.
  - Emits structured event `item_restored`.
- **Surprise Invariant Projections ([`project_wish_item`](file:///home/src/wishenka/wishlists/service.py#L69))**:
  - Strictly distinguishes recipient from gifter contexts using [`WishlistAccessPolicy.is_recipient`](file:///home/src/wishenka/wishlists/service.py#L74).
  - Recipient caller receives [`WishItemRecipientViewDTO`](file:///home/src/wishenka/wishlists/schemas.py#L11-L37) with `is_recipient=True` and all reservation/buyer fields stripped.
  - Non-recipient caller receives [`WishItemGifterViewDTO`](file:///home/src/wishenka/wishlists/schemas.py#L39-L71) containing `available_quantity`, `is_fully_reserved`, `is_reserved_by_me`, `my_reserved_quantity`, `my_reservation_status`, and `my_reservation_id`.

### 8. RESTful Wish Items Controller ([`wishenka.web.routes.items`](file:///home/src/wishenka/web/routes/items.py))

Located in [`wishenka/web/routes/items.py`](file:///home/src/wishenka/web/routes/items.py).

FastAPI APIRouter mounted at `/api/wishlists/{wishlist_id}/items` providing HTTP endpoints for item CRUD, reordering, and archiving:

- **Authentication Injections**:
  - `User = Annotated[AuthenticatedUser, Depends(get_current_user)]`: Enforces authenticated session for mutations (`POST`, `PUT`, `PATCH`).
  - `OptionalUser = Annotated[AuthenticatedUser | None, Depends(get_optional_current_user)]`: Allows anonymous access for public wishlist views while extracting caller credentials for personalized gifter badges when logged in.
- **Transactional Execution Wrapper ([`execute`](file:///home/src/wishenka/web/routes/items.py#L33-L74))**:
  - Executes operations against persistent `request.app.state.wishlist_store.execute` or test-injected domain service `request.app.state.wishlist_service`.
  - Maps domain exceptions to standard HTTP error responses:
    - [`WishlistNotFoundError`](file:///home/src/wishenka/wishlists/exceptions.py#L10), [`WishlistDeletedError`](file:///home/src/wishenka/wishlists/exceptions.py#L22), [`ItemNotFoundError`](file:///home/src/wishenka/wishlists/exceptions.py#L36) $\rightarrow$ **`404 Not Found`** (`event="item_not_found"`).
    - [`PermissionDeniedError`](file:///home/src/wishenka/wishlists/exceptions.py#L26) $\rightarrow$ **`403 Forbidden`** (`event="item_permission_denied"`).
    - [`WishlistArchivedError`](file:///home/src/wishenka/wishlists/exceptions.py#L18), [`CannotReduceQuantityBelowReservedError`](file:///home/src/wishenka/wishlists/exceptions.py#L40) $\rightarrow$ **`409 Conflict`** (`event="item_conflict"`).
    - `ValueError` (whitespace titles, invalid reorder permutations) $\rightarrow$ **`400 Bad Request`** (`event="item_validation_error"`).

### 9. Relational Persistence & Ordering Index ([`wl_items`](file:///home/src/wishenka/wishlists/store.py))

Located in [`wishenka/wishlists/db_models.py`](file:///home/src/wishenka/wishlists/db_models.py), [`wishenka/wishlists/store.py`](file:///home/src/wishenka/wishlists/store.py), and [`wishenka/wishlists/repository.py`](file:///home/src/wishenka/wishlists/repository.py):

- **Column**: `display_order INTEGER NOT NULL DEFAULT 0` on table `wl_items`.
- **Index**: `CREATE INDEX IF NOT EXISTS idx_wl_items_order ON wl_items(wishlist_id, display_order)`.
- **Dynamic Schema Migration**: On startup, `WishlistStore._init_db` inspects `PRAGMA table_info(wl_items)` and executes `ALTER TABLE wl_items ADD COLUMN display_order INTEGER NOT NULL DEFAULT 0` if absent, followed by creating `idx_wl_items_order`.
- **Deterministic Ordering**: Repository selects sort by `ORDER BY display_order ASC, id ASC`.

### 10. TMA HTMX Wish Items UI Controller & Partials ([`wishenka.web.routes.items_ui`](file:///home/src/wishenka/web/routes/items_ui.py))

Located in [`wishenka/web/routes/items_ui.py`](file:///home/src/wishenka/web/routes/items_ui.py) with templates in [`wishenka/web/templates/`](file:///home/src/wishenka/web/templates/).

Provides server-rendered HTML views and HTMX partials mounted at `/web/wishlists/{wishlist_id}` for the Telegram Mini App:

- **Wishlist Detail View ([`wishlist_detail.html`](file:///home/src/wishenka/web/templates/wishlist_detail.html))**:
  - Served at `GET /web/wishlists/{wishlist_id}` ([`view_wishlist_detail`](file:///home/src/wishenka/web/routes/items_ui.py#L108)).
  - Computes `can_edit_wishlist = WishlistAccessPolicy.can_add_or_edit_item(ctx, wl)` (`True` only for `OWNER`, `ADMIN`, or `MEMBER` when `wishlist.status == WishlistStatus.ACTIVE`).
  - Conditionally renders `#quick-add-bar` and the per-card `.btn-edit-item` button only when `can_edit_wishlist` is true, completely isolating guests, gifters, and archived wishlists from mutation controls.
- **Universal Quick Add Bar ([`partials/item_quick_add.html`](file:///home/src/wishenka/web/templates/partials/item_quick_add.html))**:
  - Fixed bottom bar (`.quick-add-container` in [`miniapp.css`](file:///home/src/wishenka/web/static/miniapp.css#L27) with `env(safe-area-inset-bottom)` and `44px` minimum touch targets).
  - Input `#quick-add-input` triggers `hx-post="/web/wishlists/{{ wishlist.id }}/items/preview"` with `hx-trigger="input changed delay:500ms, paste"`, rendering into `#quick-add-preview-target`.
  - Button `#btn-quick-details` («Подробнее») triggers `hx-get="/web/wishlists/{{ wishlist.id }}/items/new"` with `hx-include="#quick-add-form"` to open the creation bottom-sheet modal prepopulated with current input or scraped metadata.
  - Button `#btn-quick-add` («Добавить») submits `#quick-add-form` to `POST /web/wishlists/{{ wishlist.id }}/items/quick` (`hx-target="#items-list"`, `hx-swap="beforeend"`).
- **Live URL Preview Card ([`partials/item_preview_card.html`](file:///home/src/wishenka/web/templates/partials/item_preview_card.html))**:
  - Rendered by [`preview_item_input`](file:///home/src/wishenka/web/routes/items_ui.py#L143) (`POST /web/wishlists/{wishlist_id}/items/preview`).
  - If `UniversalInputClassifier.classify(raw_input)` returns `InputType.PLAIN_TEXT`, returns an empty `200 OK` body without network calls.
  - For URLs, calls `ItemPreviewService.fetch_preview(raw_input)` and renders product thumbnail, store badge (`preview.store_name`), cleaned title, price/currency, hidden `<input>` fields (`link`, `price`, `currency`, `image_url`, `store_name`, `title`), and a dismiss button (`✕`).
  - When `preview.is_fallback` is true (or `preview.title` is missing), renders a graceful fallback state preserving the sanitized URL and store badge while providing an inline text input for manual title entry.
- **HTMX Out-of-Band (`hx-swap-oob`) DOM Updates**:
  - Upon item creation in [`quick_add_item`](file:///home/src/wishenka/web/routes/items_ui.py#L225) (`POST /web/wishlists/{wishlist_id}/items/quick`), the server returns `201 Created` containing the rendered [`partials/item_card.html`](file:///home/src/wishenka/web/templates/partials/item_card.html) alongside four OOB swap fragments:
    1. `<div id="quick-add-preview-target" hx-swap-oob="innerHTML"></div>` (clears preview card).
    2. `<input type="text" id="quick-add-input" ... value="" hx-swap-oob="true" />` (clears input value while keeping HTMX attributes).
    3. `<div id="empty-items-placeholder" hx-swap-oob="delete"></div>` (removes empty list banner).
    4. `<div id="item-modal-container" hx-swap-oob="innerHTML"></div>` (closes creation modal if open).
- **Detailed Creation & Edit BottomSheet Modal ([`partials/item_edit_modal.html`](file:///home/src/wishenka/web/templates/partials/item_edit_modal.html))**:
  - Served in creation mode (`is_edit=False`) by [`get_new_item_modal`](file:///home/src/wishenka/web/routes/items_ui.py#L344) (`GET /web/wishlists/{wishlist_id}/items/new`) and in edit mode (`is_edit=True`) by [`get_edit_item_modal`](file:///home/src/wishenka/web/routes/items_ui.py#L438) (`GET /web/wishlists/{wishlist_id}/items/{item_id}/edit`).
  - Enforces **Reduction Lock UI**: computes `locked_quantity = item.reserved_quantity + item.received_quantity` and `min_quantity = max(1, locked_quantity)`, sets `min="{{ min_quantity }}"` on `#item-quantity-input`, stops the `-` stepper button at `min_quantity`, and displays an amber warning banner when `locked_quantity > 0`.
  - Enforces **HTTP 409 Error Recovery**: if [`submit_edit_item`](file:///home/src/wishenka/web/routes/items_ui.py#L541) (`POST /web/wishlists/{wishlist_id}/items/{item_id}/edit`) catches `CannotReduceQuantityBelowReservedError`, it re-renders `partials/item_edit_modal.html` with status `409 Conflict`, displaying a localized error alert while preserving all user-submitted form fields (`submitted_form`).
  - Enforces **Surprise Invariant & XSS Safety**: never exposes `item.reservations` or gifter identities (`user_id`, `username`, `first_name`), and relies on Jinja2 auto-escaping across all templates (`partials/item_card.html`, `partials/item_edit_modal.html`, `partials/item_preview_card.html`).
  - Supports **Safe Archiving & Restoration**: [`archive_item_ui`](file:///home/src/wishenka/web/routes/items_ui.py#L717) (`POST /web/wishlists/{wishlist_id}/items/{item_id}/archive`) archives the item while keeping reservations and emits `hx-swap-oob="delete"` for `#item-card-{item_id}` plus `hx-swap-oob="innerHTML"` for `#item-modal-container`. [`restore_item_ui`](file:///home/src/wishenka/web/routes/items_ui.py#L776) (`POST /web/wishlists/{wishlist_id}/items/{item_id}/restore`) restores the item and returns the rendered `partials/item_card.html`.

---

## Domain Exceptions & Hierarchy

Located in [`wishenka/items/exceptions.py`](file:///home/src/wishenka/items/exceptions.py) and [`wishenka/wishlists/exceptions.py`](file:///home/src/wishenka/wishlists/exceptions.py).

```text
WishlistError
  ├── ItemError
  │     ├── InvalidItemDataError
  │     └── ItemParsingError
  │           ├── ResponseBodyTooLargeError
  │           └── SSRFError
  │                 ├── SSRFBlockedError
  │                 └── InvalidUrlSchemeError
  ├── ItemNotFoundError
  ├── CannotReduceQuantityBelowReservedError
  ├── WishlistNotFoundError
  ├── WishlistArchivedError
  ├── WishlistDeletedError
  └── PermissionDeniedError
```

### Exception Reference

| Exception | Base Class | Key Attributes | HTTP Status | Trigger Condition |
| --- | --- | --- | :---: | --- |
| [`ItemError`](file:///home/src/wishenka/items/exceptions.py#L10) | `WishlistError` | None | `400` | Base exception for all item domain errors. |
| [`InvalidItemDataError`](file:///home/src/wishenka/items/exceptions.py#L14) | `ItemError` | None | `400` | Validation failures in item payloads (e.g. quantity $< 1$ or $> 1000$). |
| [`ItemParsingError`](file:///home/src/wishenka/items/exceptions.py#L18) | `ItemError` | None | `400` | Base exception for parsing, URL extraction, and network fetch limits. |
| [`SSRFError`](file:///home/src/wishenka/items/exceptions.py#L22) | `ItemParsingError` | None | `400` | Base exception for SSRF blocks and URL security violations. |
| [`SSRFBlockedError`](file:///home/src/wishenka/items/exceptions.py#L26) | `SSRFError` | `ip_address`, `host`, `reason` | `400` | Host or IP resolves to private, loopback, link-local, cloud metadata, or reserved range. |
| [`InvalidUrlSchemeError`](file:///home/src/wishenka/items/exceptions.py#L43) | `SSRFError` | `scheme` | `400` | URL scheme is not `http` or `https` (e.g. `file://`, `ftp://`). |
| [`ResponseBodyTooLargeError`](file:///home/src/wishenka/items/exceptions.py#L56) | `ItemParsingError` | `content_length`, `max_allowed` | `400` | Response exceeds 2 MB (`Content-Length` header or streaming chunk limit). |
| [`ItemNotFoundError`](file:///home/src/wishenka/wishlists/exceptions.py#L36) | `WishlistError` | None | `404` | Target `item_id` does not exist or does not belong to the specified wishlist. |
| [`CannotReduceQuantityBelowReservedError`](file:///home/src/wishenka/wishlists/exceptions.py#L40) | `WishlistError` | None | `409` | Invariant violation: attempting to set `quantity < reserved_quantity + received_quantity`. |
| [`WishlistNotFoundError`](file:///home/src/wishenka/wishlists/exceptions.py#L10) | `WishlistError` | None | `404` | Parent wishlist ID does not exist. |
| [`WishlistArchivedError`](file:///home/src/wishenka/wishlists/exceptions.py#L18) | `WishlistError` | None | `409` | Attempting to mutate an item in an archived wishlist or edit an archived item. |
| [`WishlistDeletedError`](file:///home/src/wishenka/wishlists/exceptions.py#L22) | `WishlistError` | None | `404` | Parent wishlist is marked as deleted. |
| [`PermissionDeniedError`](file:///home/src/wishenka/wishlists/exceptions.py#L26) | `WishlistError` | None | `403` | Caller lacks `can_add_or_edit_item` privilege for the wishlist. |

---

## Domain Models and DTOs

| Model / DTO | Location | Description |
| --- | --- | --- |
| [`InputType`](file:///home/src/wishenka/items/models.py#L7-L13) | `wishenka.items.models` | Enum: `plain_text`, `explicit_url`, `implicit_url`, `composite_share`. |
| [`ItemPriority`](file:///home/src/wishenka/items/models.py#L16-L21) | `wishenka.items.models` | Enum: `low`, `medium`, `high`. |
| [`InputClassificationResult`](file:///home/src/wishenka/items/models.py#L24-L31) | `wishenka.items.models` | Result dataclass with `input_type`, `normalized_url`, `residual_text`, `raw_input`. |
| [`ExtractedMetadata`](file:///home/src/wishenka/items/models.py#L34-L46) | `wishenka.items.models` | Raw parsed fields: `title`, `description`, `image_url`, `price`, `currency`, `store_name`, `store_icon_url`, `raw_html_title`. |
| [`ItemPreviewDTO`](file:///home/src/wishenka/items/schemas.py#L11-L24) | `wishenka.items.schemas` | Pydantic DTO for client preview rendering, including `is_fallback` and `fallback_reason`. |
| [`MarketplaceRule`](file:///home/src/wishenka/items/marketplaces.py#L83-L97) | `wishenka.items.marketplaces` | Runtime-checkable Protocol for marketplace URL cleaning and store resolution. |
| [`CreateItemDTO`](file:///home/src/wishenka/items/schemas.py#L26-L49) | `wishenka.items.schemas` | Pydantic DTO for creating items: non-whitespace title, $1 \le \text{quantity} \le 1000$, optional `recipient_user_id` and `recipient_name`. |
| [`UpdateItemDTO`](file:///home/src/wishenka/items/schemas.py#L51-L74) | `wishenka.items.schemas` | Pydantic DTO for updating items: non-whitespace title, $1 \le \text{quantity} \le 1000$, optional recipient overrides. |
| [`ReorderItemsDTO`](file:///home/src/wishenka/items/schemas.py#L76-L82) | `wishenka.items.schemas` | Pydantic DTO for atomic reordering containing `item_ids: list[int]`. |
| [`WishItemRecipientViewDTO`](file:///home/src/wishenka/wishlists/schemas.py#L11-L37) | `wishenka.wishlists/schemas` | Surprise Invariant view for the recipient: omits all reservation status and gifter details. |
| [`WishItemGifterViewDTO`](file:///home/src/wishenka/wishlists/schemas.py#L39-L71) | `wishenka.wishlists/schemas` | View for gifters and non-recipient collaborators: includes `available_quantity`, `is_fully_reserved`, `my_reserved_quantity`, and `my_reservation_id`. |

---

## Business Invariants & Operational Rules

### 1. Piece Accounting & Reduction Lock Invariant

- **Quantity Bounds**: $1 \le \text{quantity} \le 1000$. Enforced at schema level ([`CreateItemDTO`](file:///home/src/wishenka/items/schemas.py#L37), [`UpdateItemDTO`](file:///home/src/wishenka/items/schemas.py#L62)) and domain level.
- **Availability Formula**:
  $$\text{available\_quantity} = \max(0, \text{quantity} - \text{received\_quantity} - \text{reserved\_quantity})$$
- **Reduction Lock**: A wishlist creator or editor cannot reduce the `quantity` of an item below units that are already promised or delivered:
  $$\text{requested\_quantity} \ge \text{reserved\_quantity} + \text{received\_quantity}$$
  Attempting to reduce below this threshold raises [`CannotReduceQuantityBelowReservedError`](file:///home/src/wishenka/wishlists/exceptions.py#L40) and returns HTTP 409 Conflict. This prevents race conditions where a creator reduces an item quantity while a gifter is purchasing it.

### 2. Reordering Protocol & 1:1 Active Permutation Integrity

- **Contiguous Zero-Indexed Ordering**: Item positions in a wishlist are defined by `display_order` ($0, 1, 2, \dots$).
- **Auto-Increment on Creation**: Newly created items receive `display_order = max(active_display_orders, default=-1) + 1`.
- **1:1 Active Permutation**: When invoking `PUT /api/wishlists/{wishlist_id}/items/reorder`:
  1. The payload `item_ids` must contain no duplicates (`len(item_ids) == len(set(item_ids))`).
  2. The set of `item_ids` must match **exactly** the set of all active (non-archived) items belonging to that wishlist:
     $$\text{set}(item\_ids) == \{i.id \mid i \in \text{items}, \neg i.is\_archived\}$$
  3. If any active item is missing, or an extra/archived item ID is provided, the operation raises `ValueError` (HTTP 400 Bad Request) and logs `item_reorder_invalid`.
  4. On success, items are contiguously re-indexed to $0, 1, \dots, N-1$ matching the list order.

### 3. Safe Archiving & Restore Semantics

- **Non-Destructive Soft-Delete**: Archiving an item (`POST /api/wishlists/{wishlist_id}/items/{item_id}/archive`) marks `is_archived = True`.
- **Reservation Preservation**: Active and purchased reservations on the archived item remain intact in the database. Gifters who committed to a gift do not lose their reservation history or booking records.
- **Booking & Mutation Freeze**: Archived items cannot be booked or edited; attempting to modify an archived item raises [`WishlistArchivedError`](file:///home/src/wishenka/wishlists/exceptions.py#L18) (HTTP 409 Conflict).
- **Listing Exclusion**: Archived items are hidden from default item listings (`include_archived=False`) and excluded from active reordering permutations.
- **Tail Restoration**: Restoring an item (`POST /api/wishlists/{wishlist_id}/items/{item_id}/restore`) unsets `is_archived = False` and sets its `display_order` to `max(active_orders, default=-1) + 1`, appending it cleanly to the end of the active list.

### 4. Collaborative Wishlist Targeting & Surprise Invariant

- **Target Recipients**: In collaborative wishlists, an item can be designated for a specific recipient via `recipient_user_id` or descriptive `recipient_name`.
- **Membership Check**: `recipient_user_id` must belong to the wishlist's active members (`owner_id` or enrolled members). Non-member recipient IDs are rejected with `ValueError` (HTTP 400 Bad Request).
- **Dual-Role Projections ([`project_wish_item`](file:///home/src/wishenka/wishlists/service.py#L69))**:
  - **Recipient View ([`WishItemRecipientViewDTO`](file:///home/src/wishenka/wishlists/schemas.py#L11))**: Returned when `WishlistAccessPolicy.is_recipient(current_user, item)` is true (i.e. caller is the designated recipient, or caller is the wishlist owner if no recipient is set). Completely omits `available_quantity`, `is_fully_reserved`, and all reservation details.
  - **Gifter View ([`WishItemGifterViewDTO`](file:///home/src/wishenka/wishlists/schemas.py#L39))**: Returned to all other callers (collaborators and gifters). Displays `available_quantity`, whether the item is fully reserved, and the caller's personal reservation status (`is_reserved_by_me`, `my_reserved_quantity`, `my_reservation_id`).

---

## REST API Reference

All endpoints are mounted at `/api/wishlists/{wishlist_id}/items`.

| Method | Endpoint Path | Auth Required | Request Body | Response DTO | Status Codes | Description |
| :---: | :--- | :---: | :--- | :--- | :---: | :--- |
| `POST` | `/api/wishlists/{wishlist_id}/items` | **Yes** | [`CreateItemDTO`](file:///home/src/wishenka/items/schemas.py#L26) | Recipient or Gifter DTO | `201`, `400`, `403`, `404`, `409` | Create new wish item with auto-incremented `display_order`. |
| `GET` | `/api/wishlists/{wishlist_id}/items` | Optional | None | `list[Recipient or Gifter DTO]` | `200`, `404` | List items sorted by `display_order ASC`. Query param `include_archived=bool`. |
| `PUT` | `/api/wishlists/{wishlist_id}/items/reorder` | **Yes** | [`ReorderItemsDTO`](file:///home/src/wishenka/items/schemas.py#L76) | `list[Recipient or Gifter DTO]` | `200`, `400`, `403`, `404`, `409` | Atomically reorder active items enforcing 1:1 permutation integrity. |
| `GET` | `/api/wishlists/{wishlist_id}/items/{item_id}` | Optional | None | Recipient or Gifter DTO | `200`, `404` | Retrieve single item projected for the caller. |
| `PATCH` | `/api/wishlists/{wishlist_id}/items/{item_id}` | **Yes** | [`UpdateItemDTO`](file:///home/src/wishenka/items/schemas.py#L51) | Recipient or Gifter DTO | `200`, `400`, `403`, `404`, `409` | Update item properties enforcing Reduction Lock Invariant. |
| `POST` | `/api/wishlists/{wishlist_id}/items/{item_id}/archive` | **Yes** | None | Recipient or Gifter DTO | `200`, `403`, `404`, `409` | Safely archive item, preserving reservations and blocking new bookings. |
| `POST` | `/api/wishlists/{wishlist_id}/items/{item_id}/restore` | **Yes** | None | Recipient or Gifter DTO | `200`, `403`, `404`, `409` | Restore archived item, placing it at the end of the active list. |

---

## HTMX Web UI Endpoints Reference (`/web/wishlists/{wishlist_id}`)

All HTMX UI endpoints are defined in [`wishenka/web/routes/items_ui.py`](file:///home/src/wishenka/web/routes/items_ui.py) and mounted at `/web/wishlists/{wishlist_id}`.

| Method | Endpoint Path | Handler | Auth | Request Payload | HTML Response / OOB Swaps | Status Codes | Description |
| :---: | :--- | :--- | :---: | :--- | :--- | :---: | :--- |
| `GET` | `/web/wishlists/{wishlist_id}` | [`view_wishlist_detail`](file:///home/src/wishenka/web/routes/items_ui.py#L108) | Optional | None | [`wishlist_detail.html`](file:///home/src/wishenka/web/templates/wishlist_detail.html) | `200`, `404` | Renders main TMA wishlist page; shows `#quick-add-bar` and edit buttons only when `can_edit_wishlist=True`. |
| `POST` | `/web/wishlists/{wishlist_id}/items/preview` | [`preview_item_input`](file:///home/src/wishenka/web/routes/items_ui.py#L143) | **Yes** | Form: `raw_input` | [`partials/item_preview_card.html`](file:///home/src/wishenka/web/templates/partials/item_preview_card.html) or empty string (`PLAIN_TEXT`) | `200`, `404`, `409` | Classifies universal input; renders live URL preview card or graceful fallback (`is_fallback=True`). |
| `POST` | `/web/wishlists/{wishlist_id}/items/quick` | [`quick_add_item`](file:///home/src/wishenka/web/routes/items_ui.py#L225) | **Yes** | Form: `raw_input`, `title`, `link`, `price`, `currency`, `image_url`, `store_name`, `description`, `quantity`, `priority`, `category`, `recipient_user_id`, `recipient_name` | [`partials/item_card.html`](file:///home/src/wishenka/web/templates/partials/item_card.html) + OOB resets (`#quick-add-preview-target`, `#quick-add-input`, `#empty-items-placeholder`, `#item-modal-container`) | `201`, `400`, `404`, `409` | Quick-adds wish item (from Quick Add Bar or creation modal) and resets UI via `hx-swap-oob`. |
| `GET` | `/web/wishlists/{wishlist_id}/items/new` | [`get_new_item_modal`](file:///home/src/wishenka/web/routes/items_ui.py#L344) | **Yes** | Query: `raw_input`, `title`, `link`, `price`, `currency`, `image_url`, `description`, `quantity`, `priority`, `category` | [`partials/item_edit_modal.html`](file:///home/src/wishenka/web/templates/partials/item_edit_modal.html) (`is_edit=False`, `min_quantity=1`) | `200`, `404`, `409` | Opens detailed item creation BottomSheet modal prepopulated from Quick Add or preview card. |
| `GET` | `/web/wishlists/{wishlist_id}/items/{item_id}/edit` | [`get_edit_item_modal`](file:///home/src/wishenka/web/routes/items_ui.py#L438) | **Yes** | None | [`partials/item_edit_modal.html`](file:///home/src/wishenka/web/templates/partials/item_edit_modal.html) (`is_edit=True`, `min_quantity=max(1, locked_quantity)`) | `200`, `404`, `409` | Opens detailed edit modal enforcing Reduction Lock and Surprise Invariant. |
| `POST` | `/web/wishlists/{wishlist_id}/items/{item_id}/edit` | [`submit_edit_item`](file:///home/src/wishenka/web/routes/items_ui.py#L541) | **Yes** | Form: `title`, `link`, `price`, `currency`, `quantity`, `description`, `image_url`, `priority`, `category`, `recipient_user_id`, `recipient_name` | [`partials/item_card.html`](file:///home/src/wishenka/web/templates/partials/item_card.html) + OOB close `#item-modal-container` (or `409` [`partials/item_edit_modal.html`](file:///home/src/wishenka/web/templates/partials/item_edit_modal.html) preserving inputs) | `200`, `400`, `404`, `409` | Saves item edits; on `CannotReduceQuantityBelowReservedError` returns HTTP 409 modal preserving form state. |
| `POST` | `/web/wishlists/{wishlist_id}/items/{item_id}/archive` | [`archive_item_ui`](file:///home/src/wishenka/web/routes/items_ui.py#L717) | **Yes** | None | OOB delete `#item-card-{item_id}` + OOB close `#item-modal-container` | `200`, `404`, `409` | Safely archives item while preserving gifter reservations and removes card from DOM. |
| `POST` | `/web/wishlists/{wishlist_id}/items/{item_id}/restore` | [`restore_item_ui`](file:///home/src/wishenka/web/routes/items_ui.py#L776) | **Yes** | None | [`partials/item_card.html`](file:///home/src/wishenka/web/templates/partials/item_card.html) | `200`, `404`, `409` | Restores archived item to the tail of the active list and renders updated card partial. |

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

### 7. Managing Wish Items and Piece Accounting via Domain Service

Items are managed through [`WishlistService`](file:///home/src/wishenka/wishlists/service.py#L144):

```python
from wishenka.auth.models import AuthenticatedUser
from wishenka.items.models import ItemPriority
from wishenka.wishlists.exceptions import (
    CannotReduceQuantityBelowReservedError,
    PermissionDeniedError,
    WishlistArchivedError,
)
from wishenka.wishlists.models import TelegramUser
from wishenka.wishlists.service import WishlistService, project_wish_item

service = WishlistService()
owner = AuthenticatedUser(telegram_id=101, username="alice")
gifter = AuthenticatedUser(telegram_id=202, username="bob")

# 1. Create a wishlist and an item with piece quantity = 5
wishlist = await service.create_wishlist(owner_id=owner.telegram_id, title="Birthday Wishlist")
item1 = await service.add_wish_item(
    actor=owner,
    wishlist_id=wishlist.id,
    title="Board Game Sets",
    quantity=5,
    price=2500,
    priority=ItemPriority.HIGH,
)
assert item1.display_order == 0
assert item1.desired_quantity == 5
assert item1.available_quantity == 5

# Add a second item - display_order auto-increments
item2 = await service.add_wish_item(
    actor=owner,
    wishlist_id=wishlist.id,
    title="Wireless Headphones",
    quantity=1,
    price=12000,
)
assert item2.display_order == 1

# 2. Gifter reserves 2 units of item1
await service.create_reservation(item_id=item1.id, user=gifter, quantity=2)
assert item1.reserved_quantity == 2
assert item1.available_quantity == 3

# 3. Reduction Lock Invariant: Reducing desired quantity below locked (2) is rejected
try:
    await service.update_wish_item(item_id=item1.id, actor=owner, quantity=1)
except CannotReduceQuantityBelowReservedError as exc:
    print(f"Reduction blocked: {exc}")

# Valid update: reduce to exactly locked threshold (2) or higher (3)
await service.update_wish_item(item_id=item1.id, actor=owner, quantity=3)
assert item1.quantity == 3
assert item1.available_quantity == 1

# 4. Atomic Reordering: Swap item2 and item1
reordered = await service.reorder_wish_items(
    wishlist_id=wishlist.id,
    actor=owner,
    item_ids=[item2.id, item1.id],
)
assert reordered[0].id == item2.id
assert reordered[0].display_order == 0
assert reordered[1].id == item1.id
assert reordered[1].display_order == 1

# 5. Safe Archiving: Soft-deletes item1 while preserving the reservation
archived_view = await service.archive_wish_item(
    wishlist_id=wishlist.id,
    item_id=item1.id,
    actor=owner,
)
assert archived_view.is_archived is True
# Reservations remain safely intact:
assert len([r for r in item1.reservations if r.status.value == "active"]) == 1

# Editing archived item is rejected
try:
    await service.update_wish_item(item_id=item1.id, actor=owner, title="New Title")
except WishlistArchivedError:
    print("Archived item cannot be modified")

# 6. Restoration: Unarchives and appends item1 to the end of the active list
restored_view = await service.restore_wish_item(
    wishlist_id=wishlist.id,
    item_id=item1.id,
    actor=owner,
)
assert restored_view.is_archived is False
assert restored_view.display_order == 1  # item2 is 0, so restored item takes 1

# 7. Surprise Invariant Projections
recipient_view = project_wish_item(item1, current_user=owner)
assert recipient_view.is_recipient is True
assert not hasattr(recipient_view, "available_quantity")  # Zero reservation leakage

gifter_view = project_wish_item(item1, current_user=gifter)
assert gifter_view.is_recipient is False
assert gifter_view.available_quantity == 1
assert gifter_view.is_reserved_by_me is True
assert gifter_view.my_reserved_quantity == 2
```

### 8. Invoking the REST API via HTTP Client

Using `httpx.AsyncClient` to perform CRUD operations against `/api/wishlists/{wishlist_id}/items`:

```python
import httpx

headers = {"Authorization": "Bearer <alice-session-token>"}

async with httpx.AsyncClient(base_url="https://api.wishenka.app") as client:
    # 1. Create item
    res = await client.post(
        "/api/wishlists/42/items",
        headers=headers,
        json={
            "title": "Mechanical Keyboard",
            "quantity": 2,
            "price": 15000,
            "priority": "high",
            "category": "Electronics",
        },
    )
    assert res.status_code == 201
    created_item = res.json()
    item_id = created_item["id"]

    # 2. List items
    res = await client.get("/api/wishlists/42/items", headers=headers)
    assert res.status_code == 200
    items = res.json()

    # 3. Update item
    res = await client.patch(
        f"/api/wishlists/42/items/{item_id}",
        headers=headers,
        json={"price": 14000, "description": "Cherry MX Blue switches"},
    )
    assert res.status_code == 200

    # 4. Reorder items (must supply exact active ID permutation)
    active_ids = [it["id"] for it in items]
    reversed_ids = list(reversed(active_ids))
    res = await client.put(
        "/api/wishlists/42/items/reorder",
        headers=headers,
        json={"item_ids": reversed_ids},
    )
    assert res.status_code == 200

    # 5. Archive item
    res = await client.post(
        f"/api/wishlists/42/items/{item_id}/archive",
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["is_archived"] is True

    # 6. Restore item
    res = await client.post(
        f"/api/wishlists/42/items/{item_id}/restore",
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["is_archived"] is False
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

All events are logged via structured extra dictionaries under logger names `"wishenka.items"` (URL parsing and preview pipeline), `"wishenka.wishlists"` (domain service lifecycle), `"wishenka.web.items"` (REST API layer), and `"wishenka.web.items_ui"` (TMA HTMX UI layer):

#### 1. Wish Items Lifecycle & Accounting Events (`wishenka.wishlists`, `wishenka.web.items`)

| Event Name | Level | Key Context Fields | Trigger Condition |
| :--- | :---: | :--- | :--- |
| `item_created` | `INFO` | `wishlist_id`, `item_id`, `actor_id`, `recipient_user_id`, `quantity`, `display_order`, `has_recipient` | Wish item successfully added to wishlist with auto-incremented `display_order`. |
| `item_updated` | `INFO` | `wishlist_id`, `item_id`, `actor_id`, `updated_fields`, `quantity`, `quantity_delta` | Wish item properties updated within reduction limits. |
| `item_archived` | `INFO` | `wishlist_id`, `item_id`, `actor_id`, `active_reservations_count` | Item safely soft-deleted while retaining all active reservations. |
| `item_restored` | `INFO` | `wishlist_id`, `item_id`, `actor_id`, `display_order`, `new_display_order` | Archived item restored and appended to the tail of the active list. |
| `items_reordered` | `INFO` | `wishlist_id`, `actor_id`, `item_count`, `count`, `item_ids` | Active items display order atomically permuted. |
| `item_quantity_reduction_rejected` | `WARNING` | `wishlist_id`, `item_id`, `actor_id`, `requested_quantity`, `locked_quantity`, `reason` | Invariant violation: attempt to reduce quantity below reserved + fulfilled units. |
| `item_reorder_invalid` | `WARNING` | `wishlist_id`, `actor_id`, `reason` | Permutation integrity violation: duplicate IDs or set mismatch against active items. |
| `item_access_denied` | `WARNING` | `wishlist_id`, `actor_id`, `action`, `role`, `item_id` | Unauthorized actor denied permission to create, edit, reorder, archive, or restore items. |
| `item_not_found` | `WARNING` | `operation`, `item_id`, `actor_id` | HTTP route caught `ItemNotFoundError` or `WishlistNotFoundError` (returns 404). |
| `item_permission_denied` | `WARNING` | `operation` | HTTP route caught `PermissionDeniedError` (returns 403). |
| `item_conflict` | `WARNING` | `operation` | HTTP route caught `CannotReduceQuantityBelowReservedError` or `WishlistArchivedError` (returns 409). |
| `item_validation_error` | `WARNING` | `operation` | HTTP route caught `ValueError` on whitespace titles or invalid reorder permutations (returns 400). |

#### 2. Input Parsing, Preview & SSRF Telemetry Events (`wishenka.items`)

| Event Name | Level | Key Context Fields | Trigger Condition |
| :--- | :---: | :--- | :--- |
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

#### 3. TMA HTMX Wish Item UI Events (`wishenka.web.items_ui`)

| Event Name | Level | Key Context Fields | Trigger Condition |
| :--- | :---: | :--- | :--- |
| `ui_item_quick_add_preview` | `INFO` | `wishlist_id`, `actor_id`, `user_id`, `input_type`, `domain`, `store_name`, `is_fallback`, `duration_ms` | Universal input classified (`PLAIN_TEXT` or URL) and live preview card or fallback rendered. |
| `ui_item_quick_add_success` | `INFO` | `wishlist_id`, `item_id`, `actor_id`, `user_id`, `has_link`, `price`, `quantity` | Wish item created via Quick Add Bar or creation modal with HTMX OOB resets. |
| `ui_item_edit_opened` | `INFO` | `wishlist_id`, `item_id`, `actor_id`, `user_id`, `mode`, `locked_quantity`, `is_collaborative` | Detailed item creation (`mode="create"`) or edit (`mode="edit"`) BottomSheet modal opened. |
| `ui_reduction_lock_rendered` | `INFO` | `wishlist_id`, `item_id`, `actor_id`, `user_id`, `locked_quantity` | Edit modal rendered with active Reduction Lock constraint (`locked_quantity > 0`). |
| `ui_reduction_lock_rejected` | `WARNING` | `wishlist_id`, `item_id`, `actor_id`, `user_id`, `requested_quantity`, `locked_quantity` | Edit submission rejected with HTTP 409 Conflict due to quantity below locked reservations. |
| `ui_item_edit_saved` | `INFO` | `wishlist_id`, `item_id`, `actor_id`, `user_id`, `quantity`, `has_recipient` | Wish item attributes and collaborative recipient targeting saved via edit modal. |
| `ui_item_archived` | `INFO` | `wishlist_id`, `item_id`, `actor_id`, `user_id` | Wish item safely archived via HTMX UI while preserving gifter reservations. |
| `ui_item_restored` | `INFO` | `wishlist_id`, `item_id`, `actor_id`, `user_id` | Archived wish item restored to the active list via HTMX UI. |

### Privacy & Data Protection Guarantees

In accordance with security requirements:
- **Zero Capability Token Leaks**: Wishlist capability tokens (`public_token`, `invite_token`) are strictly omitted from item logs and exceptions.
- **Zero Authentication Secret Leaks**: Telegram `init_data`, session cookies, and authorization bearer tokens are completely excluded from log attributes.
- **No Payload Leaks**: Raw HTML bodies, full upstream responses, and long user notes are never dumped into logs.
- **Tracking Parameter Value Isolation**: URL tracking removal logs list sanitized key names only (`removed_keys=["utm_source"]`), strictly omitting query parameter values that might contain sensitive affiliate IDs or campaign tokens.
- **No Internal IP Leak to Clients**: Client-facing DTOs (`ItemPreviewDTO`) receive generic `fallback_reason="ssrf_blocked"`; internal IP details remain isolated to server audit logs.
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

### 8. Quantity Reduction Rejection (`CannotReduceQuantityBelowReservedError` / HTTP 409 Conflict)
- **Symptom**: `PATCH /api/wishlists/{wishlist_id}/items/{item_id}` returns `409 Conflict` with detail `"Cannot reduce quantity to X: Y units already locked"`.
- **Cause**: The user attempted to reduce `quantity` below already committed reservations plus fulfilled units ($\text{reserved\_quantity} + \text{received\_quantity}$).
- **Resolution**: The item quantity cannot be reduced below the locked count while active reservations exist. If the reservations are no longer valid, gifters must cancel their reservations first. Alternatively, the creator can archive the entire item.

### 9. Reorder Permutation Validation Failure (`ValueError` / HTTP 400 Bad Request)
- **Symptom**: `PUT /api/wishlists/{wishlist_id}/items/reorder` returns `400 Bad Request` with detail `"Reorder list must contain exactly all active item IDs for this wishlist"` or `"Duplicate item IDs in reorder request"`.
- **Cause**: The submitted `item_ids` array contains duplicates, omits one or more active items, or includes archived/foreign item IDs.
- **Resolution**: Retrieve the current list of active items using `GET /api/wishlists/{wishlist_id}/items` and supply the complete set of IDs in the desired order.

### 10. Modifying or Booking Archived Items (`WishlistArchivedError` / HTTP 409 Conflict)
- **Symptom**: `PATCH /api/wishlists/{wishlist_id}/items/{item_id}` returns `409 Conflict` with `"Cannot edit archived item"`.
- **Cause**: The target item has `is_archived = True`.
- **Resolution**: Archived items are frozen to preserve integrity. Restore the item first via `POST /api/wishlists/{wishlist_id}/items/{item_id}/restore` before applying modifications.

### 11. Target Recipient Membership Validation Failure (`ValueError` / HTTP 400 Bad Request)
- **Symptom**: `POST` or `PATCH` on an item returns `400 Bad Request` with `"Recipient user X is not a member of wishlist Y"`.
- **Cause**: The provided `recipient_user_id` does not correspond to the wishlist owner or any active collaborator member.
- **Resolution**: Ensure the intended recipient has accepted an invite token to become an official member of the wishlist, or supply `recipient_name` as a textual note without setting `recipient_user_id`.

### 12. Unauthorized Action on Item (`PermissionDeniedError` / HTTP 403 Forbidden)
- **Symptom**: Item mutations or reordering return `403 Forbidden`.
- **Cause**: The caller lacks the `can_add_or_edit_item` privilege on the target wishlist (e.g. viewer role or non-member).
- **Resolution**: Wishlist administrators must promote the user to `editor` or `admin` via `PATCH /api/wishlists/{id}/members/{user_id}/role`.
