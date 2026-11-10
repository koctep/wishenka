# Items Domain: Input Parsing, Metadata Extraction, Preview Service, and Piece Accounting

## Overview

The `wishenka.items` package and its integration with `wishenka.wishlists` implement universal wish creation, rich asynchronous preview generation, resilient anti-bot degradation, and piece-by-piece inventory accounting for the **Wishlist Service («Вишенка»)** Telegram Mini App.

```
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
|   - title = residual_text               |         |   - httpx.AsyncClient (Timeout: 4.0s / 2.0s)   |
|   - is_fallback = False                 |         +------------------------------------------------+
+-----------------------------------------+                                  |
                                                                             v
                                            +------------------------------------------------+
                                            |   Anti-Bot Challenge / Error Detection?        |
                                            |   (403/429, Cloudflare, Turnstile, WAF, etc.)  |
                                            +------------------------------------------------+
                                                           |                                 |
                                                  YES      |                                 | NO (200 OK)
                                                           v                                 v
                                    +------------------------------+     +-------------------------------+
                                    | Graceful Degradation Fallback|     |     HtmlMetadataExtractor     |
                                    | - title = residual_text      |     | - 1. JSON-LD Schema.org       |
                                    | - store_name = derived       |     | - 2. OpenGraph                |
                                    | - is_fallback = True         |     | - 3. Microdata                |
                                    +------------------------------+     | - 4. HTML Fallback (<title>)  |
                                                                         +-------------------------------+
                                                                                         |
                                                                                         v
                                                                         +-------------------------------+
                                                                         | Rich ItemPreviewDTO           |
                                                                         | - title, price, currency      |
                                                                         | - image_url, store_name, etc. |
                                                                         +-------------------------------+
```

### Key Capabilities

1. **Universal Input Classification**:
   - Accurately classifies user inputs into four types:
     - `PLAIN_TEXT`: Freeform gift description or wish note without hyperlinks.
     - `EXPLICIT_URL`: Direct link containing protocol scheme (`https://...` or `http://...`).
     - `IMPLICIT_URL`: Domain-style link pasted without protocol (e.g. `ozon.ru/product/...`), automatically normalized with `https://`.
     - `COMPOSITE_SHARE`: Mobile OS "Share" text containing both a link and surrounding commentary (e.g. `Посмотри кроссовки https://ozon.ru/t/123 классная модель!`). Extracts the URL while isolating `residual_text`.
2. **Cascading HTML Metadata Extraction**:
   - Prioritized hierarchical extraction pipeline: **JSON-LD Schema.org Product/Offer** $\rightarrow$ **OpenGraph** (`og:title`, `og:image`, `product:price:amount`) $\rightarrow$ **Microdata** (`itemprop`) $\rightarrow$ **Standard HTML** (`<title>`, `<meta name="description">`, `<link rel="icon">`).
3. **Anti-Bot Graceful Fallback**:
   - Zero-crash degradation on anti-bot gates (Cloudflare Turnstile, DDoS-GUARD, WAF signatures, HTTP 403 Forbidden, HTTP 429 Too Many Requests) and network timeouts (4.0s total, 2.0s connect). Instead of throwing errors, emits a valid fallback [`ItemPreviewDTO`](file:///home/src/wishenka/items/schemas.py#L11-L24) for seamless manual entry.
4. **Piece Accounting & Multi-Quantity Invariants**:
   - Desired quantity boundary: $1 \le \text{desired} \le 1000$.
   - Available piece calculation:
     $$\text{available} = \max(0, \text{desired} - \text{reserved} - \text{fulfilled})$$
   - **Reduction Lock Invariant**: A user cannot reduce `desired` quantity below already locked units ($\text{reserved} + \text{fulfilled}$). Attempting to do so raises [`CannotReduceQuantityBelowReservedError`](file:///home/src/wishenka/wishlists/exceptions.py#L40-L42).
   - **Surprise Invariant**: Gift recipients receive [`WishItemRecipientViewDTO`](file:///home/src/wishenka/wishlists/schemas.py#L14-L35) strictly devoid of reservation statuses, gifter identities, or booked quantities.

---

## Architecture & Components

The items subsystem consists of four core building blocks:

### 1. [`UniversalInputClassifier`](file:///home/src/wishenka/items/classifier.py#L24-L105)

Located in [`wishenka/items/classifier.py`](file:///home/src/wishenka/items/classifier.py).

Responsible for pure string classification and URL normalization without performing network operations.
- Regex pattern [`EXPLICIT_URL_REGEX`](file:///home/src/wishenka/items/classifier.py#L15) detects `https?://` schemes.
- Regex pattern [`DOMAIN_URL_REGEX`](file:///home/src/wishenka/items/classifier.py#L18-L21) matches popular e-commerce TLDs (`.ru`, `.com`, `.org`, `.net`, `.by`, `.kz`, `.io`, `.me`, `.app`, `.store`, `.shop`, `.market`, `.su`) and prepends `https://`.
- Strips matched URL substrings and consolidates surrounding whitespace into `residual_text`.

### 2. [`HtmlMetadataExtractor`](file:///home/src/wishenka/items/parser.py#L177-L372)

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

### 3. [`ItemPreviewService`](file:///home/src/wishenka/items/service.py#L39-L259)

Located in [`wishenka/items/service.py`](file:///home/src/wishenka/items/service.py).

Asynchronous service orchestrating HTTP requests, timeout enforcement, anti-bot signature matching, and metadata extraction:
- Uses modern mobile Safari / iOS User-Agent headers to maximize compatibility with mobile storefronts.
- Enforces a strict timeout budget: `4.0s` total, `2.0s` connection timeout via [`DEFAULT_TIMEOUT`](file:///home/src/wishenka/items/service.py#L24).
- Inspects response status codes (`403`, `429`, `>=400`) and HTML body content for challenge signatures (`_cf_chl_opt`, `challenge-running`, `turnstile`, `ddos-guard`, etc.) via [`_is_challenge`](file:///home/src/wishenka/items/service.py#L251-L257).
- Returns [`ItemPreviewDTO`](file:///home/src/wishenka/items/schemas.py#L11-L24) with `is_fallback=True` and `fallback_reason` (`timeout`, `anti_bot_challenge`, `http_error`) upon any scraping difficulty.

### 4. Multi-Quantity Integration in [`wishenka.wishlists`](file:///home/src/wishenka/wishlists/service.py#L1-L320)

Located in [`wishenka/wishlists/models.py`](file:///home/src/wishenka/wishlists/models.py) and [`wishenka/wishlists/service.py`](file:///home/src/wishenka/wishlists/service.py):
- Extends [`WishItem`](file:///home/src/wishenka/wishlists/models.py#L78-L127) with dynamic properties:
  - `reserved_quantity`: Sum of `quantity` across all active reservations.
  - `available_quantity`: `max(0, quantity - received_quantity - reserved_quantity)`.
  - `desired_quantity` / `fulfilled_quantity`: Explicit business aliases for `quantity` and `received_quantity`.
- [`WishlistService.update_wish_item`](file:///home/src/wishenka/wishlists/service.py#L158-L260): Enforces the reduction invariant `quantity >= reserved_quantity + received_quantity`, raising [`CannotReduceQuantityBelowReservedError`](file:///home/src/wishenka/wishlists/exceptions.py#L40-L42) if violated.
- Projection views strictly separate recipient visibility ([`WishItemRecipientViewDTO`](file:///home/src/wishenka/wishlists/schemas.py#L14-L35)) from gifter visibility ([`WishItemGifterViewDTO`](file:///home/src/wishenka/wishlists/schemas.py#L38-L62)).

---

## Domain Models and DTOs

| Model / DTO | Location | Description |
| --- | --- | --- |
| [`InputType`](file:///home/src/wishenka/items/models.py#L7-L13) | `wishenka.items.models` | Enum: `plain_text`, `explicit_url`, `implicit_url`, `composite_share`. |
| [`ItemPriority`](file:///home/src/wishenka/items/models.py#L16-L21) | `wishenka.items.models` | Enum: `low`, `medium`, `high`. |
| [`InputClassificationResult`](file:///home/src/wishenka/items/models.py#L24-L31) | `wishenka.items.models` | Result dataclass with `input_type`, `normalized_url`, `residual_text`, `raw_input`. |
| [`ExtractedMetadata`](file:///home/src/wishenka/items/models.py#L34-L46) | `wishenka.items.models` | Raw parsed fields: `title`, `description`, `image_url`, `price`, `currency`, `store_name`, `store_icon_url`, `raw_html_title`. |
| [`ItemPreviewDTO`](file:///home/src/wishenka/items/schemas.py#L11-L24) | `wishenka.items.schemas` | Pydantic DTO for client preview rendering, including `is_fallback` and `fallback_reason`. |
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

### 2. Generating Link Previews with Fallback Handling

Use [`ItemPreviewService.fetch_preview`](file:///home/src/wishenka/items/service.py#L50-L250) (or alias `.preview(...)`) to scrape metadata:

```python
import httpx
from wishenka.items.service import ItemPreviewService

service = ItemPreviewService()

# 1. Successful scrape example
preview = await service.fetch_preview("https://ozon.ru/product/aerogrill-100200")
if not preview.is_fallback:
    print(f"Title: {preview.title}")
    print(f"Price: {preview.price} {preview.currency}")
    print(f"Image: {preview.image_url}")
    print(f"Store: {preview.store_name}")
else:
    # 2. Anti-bot or network timeout fallback
    print(f"Graceful degradation: {preview.fallback_reason}")
    print(f"Manual entry title: {preview.title or 'Enter title manually'}")
```

### 3. Managing Multi-Quantity Items in Wishlists

Items are created and updated through [`WishlistService`](file:///home/src/wishenka/wishlists/service.py#L17-L320):

```python
from wishenka.wishlists.models import TelegramUser
from wishenka.wishlists.service import WishlistService
from wishenka.wishlists.exceptions import CannotReduceQuantityBelowReservedError

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

## Configuration & Observability

### Network & Timeout Configuration

The default HTTP client in [`wishenka.items.service`](file:///home/src/wishenka/items/service.py#L24) enforces bounded timeouts:

```python
DEFAULT_TIMEOUT = httpx.Timeout(4.0, connect=2.0)
```
- **Connection Timeout (`2.0s`)**: Prevents blocking on unresponsive remote TCP connections.
- **Total Timeout (`4.0s`)**: Enforces total latency ceiling for preview generation before degrading gracefully.

### Structured Audit and Operational Logging

All events are logged via structured key-value extra dictionaries under the logger named `"wishenka.items"` and `"wishenka.wishlists"`:

| Event Name | Level | Key Context Fields | Trigger Condition |
| --- | --- | --- | --- |
| `input_classified` | `DEBUG` | `input_type`, `url_domain`, `has_residual` | Executed on every `UniversalInputClassifier.classify` call. |
| `metadata_extraction_started` | `DEBUG` | `url_domain`, `parser_stage="start"`, `html_len` | Executed upon beginning BeautifulSoup parsing. |
| `metadata_stage_resolved` | `DEBUG` | `url_domain`, `parser_stage` (`json_ld`, `opengraph`, `microdata`) | Triggered when a metadata cascade stage finds product data. |
| `metadata_extraction_completed` | `INFO` | `url_domain`, `duration_ms`, `has_title`, `has_price`, `has_image` | Successful extraction completion. |
| `item_preview_success` | `INFO` | `url_domain`, `duration_ms`, `input_type`, `is_fallback=False` | Successful link preview retrieval (HTTP 200). |
| `item_preview_plain_text` | `DEBUG` | `input_type="plain_text"`, `duration_ms` | Immediate return for plain text inputs. |
| `anti_bot_challenge_detected` | `INFO` | `status_code`, `url_domain`, `duration_ms`, `fallback_reason` | Cloudflare, Turnstile, or WAF challenge detected. |
| `item_preview_timeout` | `WARNING` | `url_domain`, `duration_ms`, `fallback_reason="timeout"` | HTTP connection or read timeout ($>4.0\text{s}$). |
| `item_preview_network_error` | `WARNING` | `url_domain`, `duration_ms`, `fallback_reason="http_error"` | DNS failure, connection reset, or network drop. |
| `item_preview_http_error` | `WARNING` | `status_code`, `url_domain`, `duration_ms`, `fallback_reason="http_error"` | Upstream HTTP status $\ge 400$. |
| `item_metadata_parsing_error` | `ERROR` | `url_domain`, `duration_ms`, `fallback_reason="http_error"` | Parsing crash in BeautifulSoup or JSON-LD. |
| `item_created` | `INFO` | `item_id`, `wishlist_id`, `actor_id`, `quantity` | Item added to a wishlist. |
| `item_updated` | `INFO` | `item_id`, `wishlist_id`, `actor_id`, `quantity`, `quantity_delta` | Item updated (tracks inventory changes). |
| `item_quantity_reduction_rejected`| `WARNING` | `item_id`, `wishlist_id`, `actor_id`, `requested_quantity`, `locked_quantity` | Rejection of quantity reduction below locked count. |

### Privacy & Data Protection Guarantees

In accordance with security requirements:
- **No Payload Leaks**: Raw HTML bodies, full upstream responses, and long user notes are never dumped into logs.
- **No Token/Credential Leaks**: URL query parameters with authorization tokens or session cookies are excluded.
- **Clean Domains**: Domains are extracted without ports or query parameters (`url_domain`) for clean metric aggregation.

---

## Troubleshooting

### 1. Anti-Bot Challenge Fallbacks (Cloudflare / WAF / Turnstile)
- **Symptom**: `ItemPreviewDTO` returns with `is_fallback=True` and `fallback_reason="anti_bot_challenge"`.
- **Cause**: The remote store (e.g. Ozon or Wildberries) uses anti-scraping mitigation returning HTTP 403/429 or JavaScript challenges (`_cf_chl_opt`, `turnstile`).
- **Resolution**: This is the expected design behavior. The frontend receives the fallback preview with the pre-populated domain name and user text, prompting the user to confirm or edit the title/price manually. To support automated extraction for protected marketplaces, dedicated API connectors or headless sidecars can be plugged in via [WISHENKA-55](https://pypost.atlassian.net/browse/WISHENKA-55).

### 2. Upstream Timeout Handling
- **Symptom**: `ItemPreviewDTO` returns with `is_fallback=True` and `fallback_reason="timeout"`, and `item_preview_timeout` is logged.
- **Cause**: The remote server failed to respond within `2.0s` connect or `4.0s` total timeout.
- **Resolution**: Check external internet connectivity and upstream store availability. The service will never hang or block the TMA event loop.

### 3. Non-Breaking Spaces in Prices (`\xa0`)
- **Symptom**: E-commerce price strings such as `"12 500 руб."` or `"12\xa0500 ₽"` failing numeric parsing.
- **Cause**: Russian e-commerce sites format thousands using `&nbsp;` (`\xa0`).
- **Resolution**: [`parse_price`](file:///home/src/wishenka/items/parser.py#L70-L103) automatically replaces `\xa0` with standard spaces before cleaning. It also parses comma and dot decimal separators without losing integer precision.

### 4. Currency Normalization
- **Symptom**: Product currency parsed from HTML contains non-standard strings like `руб`, `rur`, `byn`, `br`, `₸`, `¥`.
- **Cause**: Differing conventions across regional platforms.
- **Resolution**: [`normalize_currency`](file:///home/src/wishenka/items/parser.py#L105-L115) maps all recognized local symbols into ISO 4217 uppercase 3-letter codes (`RUB`, `USD`, `EUR`, `KZT`, `BYN`, `GBP`, `CNY`, `JPY`). Unrecognized symbols default safely to `"RUB"`.
