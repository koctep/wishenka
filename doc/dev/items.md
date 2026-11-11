# Items Domain: Input Parsing, Metadata Extraction, Preview Service, Piece Accounting, and Network Security

## Overview

The `wishenka.items` package and its integration with `wishenka.wishlists` implement universal wish creation, rich asynchronous preview generation, resilient anti-bot degradation, enterprise-grade SSRF defense, streaming DoS payload limits, and piece-by-piece inventory accounting for the **Wishlist Service («Вишенка»)** Telegram Mini App.

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
|       ItemPreviewDTO (Manual Entry)     |         |     ItemPreviewService.fetch_preview(...)      |
|   - title = residual_text               |         +------------------------------------------------+
|   - is_fallback = False                 |                                  |
+-----------------------------------------+                                  v
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
                                            | Graceful Fallback Preview |   | (403/429/WAF/Turnstile)        |
                                            | - fallback_reason =       |   +--------------------------------+
                                            |   "response_too_large"    |             |              |
                                            | - is_fallback = True      |      YES    |              | NO (200 OK)
                                            +---------------------------+             v              v
                                                                        +---------------------+  +-------------------+
                                                                        | Graceful Fallback   |  | HtmlMetadata      |
                                                                        | - is_fallback=True  |  |   Extractor       |
                                                                        | - anti_bot/timeout  |  | - JSON-LD         |
                                                                        +---------------------+  | - OpenGraph       |
                                                                                                 | - Microdata       |
                                                                                                 | - HTML Fallback   |
                                                                                                 +-------------------+
                                                                                                           |
                                                                                                           v
                                                                                                 +-------------------+
                                                                                                 | Rich Preview DTO  |
                                                                                                 | - title, price    |
                                                                                                 | - image, store    |
                                                                                                 +-------------------+
```

### Key Capabilities

1. **Universal Input Classification**:
   - Accurately classifies user inputs into four distinct types:
     - `PLAIN_TEXT`: Freeform gift description or wish note without hyperlinks.
     - `EXPLICIT_URL`: Direct link containing protocol scheme (`https://...` or `http://...`).
     - `IMPLICIT_URL`: Domain-style link pasted without protocol (e.g. `ozon.ru/product/...`), automatically normalized with `https://`.
     - `COMPOSITE_SHARE`: Mobile OS "Share" text containing both a link and surrounding commentary (e.g. `Посмотри кроссовки https://ozon.ru/t/123 классная модель!`). Extracts the URL while isolating `residual_text`.
2. **Server-Side Request Forgery (SSRF) Defense**:
   - Multi-layered defense-in-depth preventing outbound calls to internal infrastructure, local loops, cloud metadata services, and unroutable addresses:
     - Scheme whitelist: strictly `http` and `https` allowed; `file://`, `gopher://`, `ftp://`, etc. rejected early.
     - IP boundary enforcement: blocks IPv4/IPv6 private ranges (RFC 1918), loopbacks (`127.0.0.0/8`, `::1`), link-local (`169.254.0.0/16`, `fe80::/10`), cloud metadata endpoints (`169.254.169.254`), CGNAT (`100.64.0.0/10`), multicast, broadcast, and IPv6-mapped IPv4 representations (`::ffff:127.0.0.1`).
     - Non-blocking asynchronous DNS resolution via `asyncio.get_running_loop().getaddrinfo` with validation across all returned IP addresses.
     - Custom transport [`SSRFSafeTransport`](file:///home/src/wishenka/items/ssrf.py#L209) that inspects every outbound request and every intermediate redirect hop before socket connection.
3. **DoS & Payload Size Limiting (2 MB Hard Ceiling)**:
   - Enforces a strict 2 MB (`2,097,152` bytes) limit on all upstream responses:
     - Fast-fail early rejection on `Content-Length > 2 MB` before downloading response bytes.
     - Streaming chunk accumulation counter (`aiter_bytes`) enforcing the 2 MB ceiling in real time to neutralize chunked transfer encoding bombs (`Transfer-Encoding: chunked`) or infinite streams.
     - Raises [`ResponseBodyTooLargeError`](file:///home/src/wishenka/items/exceptions.py#L56) immediately when breached, aborting network consumption.
4. **Cascading HTML Metadata Extraction**:
   - Prioritized hierarchical extraction pipeline: **JSON-LD Schema.org Product/Offer** $\rightarrow$ **OpenGraph** (`og:title`, `og:image`, `product:price:amount`) $\rightarrow$ **Microdata** (`itemprop`) $\rightarrow$ **Standard HTML** (`<title>`, `<meta name="description">`, `<link rel="icon">`).
5. **Anti-Bot & Threat Graceful Fallback**:
   - Zero-crash degradation on SSRF blocks, oversized payloads, anti-bot gates (Cloudflare Turnstile, DDoS-GUARD, WAF signatures, HTTP 403 Forbidden, HTTP 429 Too Many Requests), and network timeouts (4.0s total, 2.0s connect). Instead of throwing 500 errors to the client, emits a valid fallback [`ItemPreviewDTO`](file:///home/src/wishenka/items/schemas.py#L11-L24) for seamless manual entry.
6. **Piece Accounting & Multi-Quantity Invariants**:
   - Desired quantity boundary: $1 \le \text{desired} \le 1000$.
   - Available piece calculation:
     $$\text{available} = \max(0, \text{desired} - \text{reserved} - \text{fulfilled})$$
   - **Reduction Lock Invariant**: A user cannot reduce `desired` quantity below already locked units ($\text{reserved} + \text{fulfilled}$). Attempting to do so raises [`CannotReduceQuantityBelowReservedError`](file:///home/src/wishenka/wishlists/exceptions.py#L40-L42).
   - **Surprise Invariant**: Gift recipients receive [`WishItemRecipientViewDTO`](file:///home/src/wishenka/wishlists/schemas.py#L14-L35) strictly devoid of reservation statuses, gifter identities, or booked quantities.

---

## Architecture & Components

The items subsystem consists of six core architectural building blocks:

### 1. [`UniversalInputClassifier`](file:///home/src/wishenka/items/classifier.py#L24-L105)

Located in [`wishenka/items/classifier.py`](file:///home/src/wishenka/items/classifier.py).

Responsible for pure string classification and URL normalization without performing network operations.
- Regex pattern [`EXPLICIT_URL_REGEX`](file:///home/src/wishenka/items/classifier.py#L15) detects `https?://` schemes.
- Regex pattern [`DOMAIN_URL_REGEX`](file:///home/src/wishenka/items/classifier.py#L18-L21) matches popular e-commerce TLDs (`.ru`, `.com`, `.org`, `.net`, `.by`, `.kz`, `.io`, `.me`, `.app`, `.store`, `.shop`, `.market`, `.su`) and prepends `https://`.
- Strips matched URL substrings and consolidates surrounding whitespace into `residual_text`.

### 2. SSRF Protection Suite (`wishenka.items.ssrf`)

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

### 3. Safe HTML Fetcher [`UrlMetadataService`](file:///home/src/wishenka/items/fetcher.py#L49)

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

### 4. [`HtmlMetadataExtractor`](file:///home/src/wishenka/items/parser.py#L177-L372)

Located in [`wishenka/items/parser.py`](file:///home/src/wishenka/items/parser.py).

Parses HTML documents using `BeautifulSoup4` with a multi-level fallback cascade:
- **JSON-LD**: Recursively inspects `<script type="application/ld+json">` for `@type == "Product"` schemas, extracting `name`, `description`, `image`, `brand`, and nested `offers` (`price`, `priceCurrency`).
- **OpenGraph**: Scrapes `meta[property="og:*"]` and `meta[property="product:*"]`.
- **Microdata**: Scrapes elements with `[itemprop="name"]`, `[itemprop="price"]`, etc.
- **HTML Fallback**: Scrapes `<title>`, `<meta name="description">`, and `<link rel="icon">`.
- **Sanitization Helpers**:
  - [`clean_title`](file:///home/src/wishenka/items/parser.py#L55-L67): Removes store noise suffixes and promotional phrases (e.g. `— купить в интернет-магазине Ozon`).
  - [`parse_price`](file:///home/src/wishenka/items/parser.py#L70-L103): Handles non-breaking spaces (`\xa0`), mixed European/Russian decimal separators, and casts values to integer minor units.
  - [`normalize_currency`](file:///home/src/wishenka/items/parser.py#L105-L115): Normalizes currency symbols (`₽`, `$`, `€`, `₸`, `руб`) to ISO 4217 uppercase codes (`RUB`, `USD`, `EUR`, `KZT`), defaulting to `RUB`.
  - [`derive_store_name`](file:///home/src/wishenka/items/parser.py#L131-L149): Resolves brand names, OpenGraph site names, or maps known domains to brand labels (e.g. `ozon.ru` $\rightarrow$ `Ozon`, `wildberries.ru` $\rightarrow$ `Wildberries`).

### 5. [`ItemPreviewService`](file:///home/src/wishenka/items/service.py#L35-L363)

Located in [`wishenka/items/service.py`](file:///home/src/wishenka/items/service.py).

Asynchronous facade orchestrating input classification, secure network requests via `UrlMetadataService`, anti-bot detection, and graceful degradation:
- Accepts optional `url_metadata_service` in `__init__` for dependency injection.
- Invokes `UniversalInputClassifier.classify(raw_input)`.
  - For `PLAIN_TEXT`, returns manual entry preview immediately without network activity.
  - For `EXPLICIT_URL`, `IMPLICIT_URL`, and `COMPOSITE_SHARE`, executes safe preview fetch.
- Comprehensive exception trap for graceful degradation:
  - Catches [`SSRFBlockedError`](file:///home/src/wishenka/items/exceptions.py#L26) and [`InvalidUrlSchemeError`](file:///home/src/wishenka/items/exceptions.py#L43): returns `ItemPreviewDTO` with `is_fallback=True` and `fallback_reason="ssrf_blocked"`.
  - Catches [`ResponseBodyTooLargeError`](file:///home/src/wishenka/items/exceptions.py#L56): returns `ItemPreviewDTO` with `is_fallback=True` and `fallback_reason="response_too_large"`.
  - Catches `httpx.TimeoutException`: returns `ItemPreviewDTO` with `is_fallback=True` and `fallback_reason="timeout"`.
  - Catches `httpx.HTTPStatusError`: checks `_is_challenge(body, status)`; returns `fallback_reason="anti_bot_challenge"` or `"http_error"`.
  - Catches other `httpx.RequestError` or generic exceptions: returns `fallback_reason="http_error"`.
- Prevents unhandled 500 errors and ensures Telegram Mini App users always retain access to a functional manual wish entry form with extracted residual title.

### 6. Multi-Quantity Integration in [`wishenka.wishlists`](file:///home/src/wishenka/wishlists/service.py#L1-L320)

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

### 2. Generating Link Previews with SSRF & Payload Fallback

Use [`ItemPreviewService.fetch_preview`](file:///home/src/wishenka/items/service.py#L53-L250) (or alias `.preview(...)`):

```python
from wishenka.items.service import ItemPreviewService

service = ItemPreviewService()

# 1. Successful public preview scrape
preview = await service.fetch_preview("https://ozon.ru/product/aerogrill-100200")
if not preview.is_fallback:
    print(f"Title: {preview.title}")
    print(f"Price: {preview.price} {preview.currency}")
    print(f"Image: {preview.image_url}")
    print(f"Store: {preview.store_name}")
else:
    # 2. Handled degradation (SSRF, Oversized Payload, Anti-Bot, Timeout)
    print(f"Graceful degradation: {preview.fallback_reason}")
    print(f"Manual entry title: {preview.title or 'Enter title manually'}")

# Example: SSRF attempt (e.g. cloud metadata or localhost) degrades smoothly
ssrf_preview = await service.fetch_preview("http://169.254.169.254/latest/meta-data")
assert ssrf_preview.is_fallback is True
assert ssrf_preview.fallback_reason == "ssrf_blocked"

# Example: DoS payload (>2MB) degrades smoothly
dos_preview = await service.fetch_preview("https://example.com/huge-50mb-file.iso")
if dos_preview.is_fallback:
    assert dos_preview.fallback_reason in ("response_too_large", "http_error")
```

### 3. Direct HTML Fetching with SSRF and Size Bounds

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

### 4. Direct IP and Hostname Validation

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

### 5. Using `SSRFSafeTransport` with Custom HTTPX Clients

```python
import httpx
from wishenka.items.ssrf import SSRFSafeTransport

transport = SSRFSafeTransport()
async with httpx.AsyncClient(transport=transport, follow_redirects=True) as client:
    # Safe request
    resp = await client.get("https://example.com")
    print(resp.status_code)

    # Any redirect targeting internal IPs will be blocked immediately
```

### 6. Managing Multi-Quantity Items in Wishlists

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

Defined in [`wishenka/items/ssrf.py`](file:///home/src/wishenka/items/ssrf.py) and [`wishenka/items/fetcher.py`](file:///home/src/wishenka/items/fetcher.py):

| Constant | Value | Description |
| --- | --- | --- |
| `MAX_RESPONSE_BYTES` | `2 * 1024 * 1024` (2 MB) | Maximum permitted response size before abortion. |
| `ALLOWED_SCHEMES` | `frozenset({"http", "https"})` | Whitelisted URL schemes. |
| `DEFAULT_TIMEOUT` | `httpx.Timeout(4.0, connect=2.0)` | Total budget `4.0s`, connection budget `2.0s`. |
| `DEFAULT_HEADERS` | iOS Safari Mobile UA, Ru/En Accept | Standard headers maximizing storefront compatibility. |

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
| `ssrf_blocked` | `WARNING` | `host`, `ip`, `reason` | Host or IP resolves to a restricted/forbidden address. |
| `payload_size_violation` | `WARNING` | `url`, `content_length`, `max_allowed`, `reason` | `Content-Length` or streaming chunks exceed 2 MB. |
| `dns_resolution_start` | `DEBUG` | `host`, `clean_host`, `port` | Starting asynchronous DNS resolution. |
| `dns_resolution_success` | `DEBUG` | `host`, `resolved_ips` | Successfully resolved hostname to safe IPs. |
| `dns_resolution_failed` | `INFO` | `host`, `error` | Host failed to resolve (NXDOMAIN, gaierror). |
| `ssrf_request_dispatch` | `DEBUG` | `url`, `host`, `scheme` | Outbound request verified and dispatched. |
| `url_fetch_success` | `INFO` | `url`, `effective_url`, `bytes` | Successfully streamed and decoded response body. |
| `fetch_and_extract_fallback` | `WARNING` | `url`, `error` | `UrlMetadataService.fetch_and_extract` caught an error and degraded safely. |
| `item_preview_ssrf_blocked` | `WARNING` | `url`, `url_domain`, `host`, `ip`, `reason`, `duration_ms` | SSRF attempt caught during preview generation; returns fallback. |
| `item_preview_invalid_scheme` | `WARNING` | `url`, `scheme`, `duration_ms` | Unsupported URL scheme caught; returns fallback. |
| `item_preview_response_too_large` | `WARNING` | `url`, `url_domain`, `content_length`, `max_allowed`, `duration_ms` | Oversized payload caught during preview generation; returns fallback. |
| `anti_bot_challenge_detected` | `INFO` | `status_code`, `url_domain`, `duration_ms`, `fallback_reason` | Cloudflare, Turnstile, or WAF challenge detected. |
| `item_preview_timeout` | `WARNING` | `url_domain`, `duration_ms`, `fallback_reason="timeout"` | HTTP connection or read timeout ($> 4.0\text{s}$). |
| `item_preview_success` | `INFO` | `url_domain`, `duration_ms`, `input_type`, `is_fallback=False` | Successful link preview retrieval (HTTP 200). |

### Privacy & Data Protection Guarantees

In accordance with security requirements:
- **No Payload Leaks**: Raw HTML bodies, full upstream responses, and long user notes are never dumped into logs.
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

### 4. Anti-Bot Challenge Fallbacks (Cloudflare / WAF / Turnstile)
- **Symptom**: `ItemPreviewDTO` returns with `is_fallback=True` and `fallback_reason="anti_bot_challenge"`.
- **Cause**: The remote store (e.g. Ozon or Wildberries) uses anti-scraping mitigation returning HTTP 403/429 or JavaScript challenges (`_cf_chl_opt`, `turnstile`).
- **Resolution**: This is the expected design behavior. The frontend receives the fallback preview with the pre-populated domain name and user text, prompting the user to confirm or edit the title/price manually. To support automated extraction for protected marketplaces, dedicated API connectors or headless sidecars can be plugged in via [WISHENKA-55](https://pypost.atlassian.net/browse/WISHENKA-55).

### 5. DNS Resolution Failures vs SSRF Blocks
- **Symptom**: A preview returns `fallback_reason="http_error"`, but the operator suspects an SSRF issue.
- **Cause**: If a hostname fails DNS resolution entirely (e.g. non-existent domain or upstream DNS outage), `resolve_and_validate_host` logs `dns_resolution_failed` and does not raise `SSRFBlockedError`. Instead, downstream HTTP connection fails with a standard network error.
- **Resolution**: Inspect the server log: `event="dns_resolution_failed"` indicates NXDOMAIN or resolver connectivity issues, whereas `event="ssrf_blocked"` confirms the hostname successfully resolved to a forbidden IP address.

### 6. Upstream Timeout Handling
- **Symptom**: `ItemPreviewDTO` returns with `is_fallback=True` and `fallback_reason="timeout"`, and `item_preview_timeout` is logged.
- **Cause**: The remote server failed to respond within `2.0s` connect or `4.0s` total timeout.
- **Resolution**: Check external internet connectivity and upstream store availability. The service will never hang or block the TMA event loop.
