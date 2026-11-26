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
                                                    |  - Scheme Check (SSRFPolicy.allowed_schemes)   |
                                                    |  - Async DNS Resolution (getaddrinfo)          |
                                                    |  - SSRF IP Validation (is_ip_safe)             |
                                                    |  - SSRFSafeTransport + SSRFSafeNetworkBackend  |
                                                    |    (Pinned-IP & Redirect Hops Check)           |
                                                    +------------------------------------------------+
                                                              |                             |
                                               SSRF / Bad IP  |                             | Destination Safe
                                                              v                             v
                                            +---------------------------+   +--------------------------------+
                                            | SSRFBlockedError / Scheme |   | Streaming HTTP Response Body   |
                                            | Graceful Fallback Preview |   | - Content-Length <= max_bytes  |
                                            | - fallback_reason =       |   | - Stream chunks <= max_bytes   |
                                            |   "ssrf_blocked"          |   |   (default 2 MB, configurable) |
                                            | - is_fallback = True      |   +--------------------------------+
                                            +---------------------------+             |              |
                                                                          > max_bytes |              | <= max_bytes
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
   - Multi-layered defense-in-depth driven by an immutable [`SSRFPolicy`](file:///home/src/wishenka/items/ssrf.py#L45-L72) resolved from [`Settings`](file:///home/src/wishenka/config.py#L68-L205) (`WISHENKA_SSRF_*` environment variables / `.env`), preventing outbound calls to internal infrastructure, local loops, cloud metadata services, and unroutable addresses:
     - Scheme allowlist: defaults to `http` and `https`, configurable via `ssrf_allowed_schemes` (`WISHENKA_SSRF_ALLOWED_SCHEMES`) within `SUPPORTED_SSRF_SCHEMES = {"http", "https"}`; `file://`, `gopher://`, `ftp://`, etc. fail fast on startup or are rejected before network I/O.
     - IP boundary enforcement: unconditionally blocks IPv4/IPv6 private ranges (RFC 1918), loopbacks (`127.0.0.0/8`, `::1`), link-local (`169.254.0.0/16`, `fe80::/10`), cloud metadata endpoints (`169.254.169.254`), CGNAT (`100.64.0.0/10`), multicast, broadcast, reserved/unspecified addresses, and IPv6-mapped IPv4 representations (`::ffff:127.0.0.1`), plus configurable CIDR blocks via `ssrf_forbidden_cidrs` (`WISHENKA_SSRF_FORBIDDEN_CIDRS`, 20 default CIDRs).
     - Non-blocking asynchronous DNS resolution via `asyncio.get_running_loop().getaddrinfo` with validation across all returned IP addresses, backed by a bounded in-memory TTL/LRU DNS cache ([`DNSCache`](file:///home/src/wishenka/items/ssrf.py#L298-L361), default 60s TTL / 512 entries) that re-validates cached IPs against the caller's active `forbidden_networks` on every hit, and per-event-loop single-flight coalescing keyed by normalized `(host, port)` and active CIDR networks (`WISHENKA-94`, `WISHENKA-93`).
     - Custom transport [`SSRFSafeTransport`](file:///home/src/wishenka/items/ssrf.py#L750-L867) and [`SSRFSafeNetworkBackend`](file:///home/src/wishenka/items/ssrf.py#L623-L747) that inspect every outbound request and every intermediate redirect hop under the active `SSRFPolicy` (`_active_policy_var`), pin validated IPs in a task-scoped `ContextVar` (`_pinned_ips_var`), redact URL userinfo credentials before logging ([`redact_url_credentials`](file:///home/src/wishenka/items/ssrf.py#L107-L115)), and connect directly to the pinned IP without re-querying DNS (eliminating DNS rebinding TOCTOU).
4. **DoS & Payload Size Limiting (Configurable, 2 MB Default Ceiling)**:
   - Enforces a configurable response size ceiling (`ssrf_max_response_bytes` / `WISHENKA_SSRF_MAX_RESPONSE_BYTES`, defaulting to 2 MB / `2,097,152` bytes, or per-service `max_bytes` override) on all upstream responses:
     - Fast-fail early rejection on `Content-Length > self.max_bytes` before downloading response bytes.
     - Streaming chunk accumulation counter (`aiter_bytes`) enforcing `self.max_bytes` in real time to neutralize chunked transfer encoding bombs (`Transfer-Encoding: chunked`) or infinite streams.
     - Raises [`ResponseBodyTooLargeError`](file:///home/src/wishenka/items/exceptions.py#L56) immediately when breached, aborting network consumption.
5. **Cascading HTML Metadata Extraction with JSON-LD `@graph` & `AggregateOffer`**:
   - Prioritized hierarchical extraction pipeline: **JSON-LD Schema.org Product/Offer** $\rightarrow$ **OpenGraph** (`og:title`, `og:image`, `product:price:amount`) $\rightarrow$ **Microdata** (`itemprop`) $\rightarrow$ **Standard HTML** (`<title>`, `<meta name="description">`, `<link rel="icon">`).
   - Iteratively traverses bounded JSON-LD graphs and matches standard and URI Product types.
   - Extracts pricing from both simple `Offer` and `AggregateOffer` structures (extracting `lowPrice`, `highPrice`, or `price`).
   - Cleans store advertising noise and marketing slogans from titles using regex patterns (e.g. stripping `— купить в интернет-магазине Ozon`, `в наличии на маркетплейсе`).
   - Normalizes currency symbols (`₽`, `руб`, `₸`, `Br`, `$`, `€`, `£`, `¥`) to standard ISO 4217 uppercase codes.
6. **Anti-Bot & Threat Graceful Fallback**:
   - Zero-crash degradation on SSRF blocks, oversized payloads, anti-bot gates (Cloudflare Turnstile, Qrator, DDoS-GUARD, WAF signatures, Russian marketplace anti-bot screens such as Yandex SmartCaptcha, Avito IP firewall, Ozon/Wildberries/Megamarket browser verification pages, HTTP 403 Forbidden, HTTP 429 Too Many Requests, HTTP 503 Service Unavailable), and network timeouts (4.0s total, 2.0s connect).
   - Rather than returning 500 server errors, emits a valid fallback [`ItemPreviewDTO`](file:///home/src/wishenka/items/schemas.py#L11-L24) populated with the cleaned URL, recognized store name, and extracted residual title for seamless manual entry (never leaking anti-bot challenge `<title>` text such as `"Почти готово..."` or `"Доступ ограничен: проблема с IP"` into the wish title).
7. **Piece Accounting & Multi-Quantity Invariants**:
   - Desired quantity boundary: $1 \le \text{desired} \le 1000$.
   - Occupied units are the sum of reservation `quantity` in `ACTIVE` or `PURCHASED`. The free remainder a promise may take is $\max(0, \text{requested} - \text{received} - \text{occupied})$.
   - A receipt adds received units and is capped by requested minus units already received. It leaves the promise open. After a successful receipt, occupied plus received may exceed the requested quantity.
   - **Quantity reduction**: An author may reduce the requested quantity to
     `max(1, received_quantity)` even when open promises occupy more units. A smaller value
     raises `CannotReduceQuantityBelowReservedError` without revealing booking information.
     If received plus occupied units exceed the new quantity, the wish is over-booked and
     existing promises remain unchanged.
   - Inventory writes for one wish run in a wish-scoped SQLite WAL transaction ([`WishlistStore.execute_wish`](file:///home/src/wishenka/wishlists/store.py#L942-L997)). `SQLITE_BUSY` after `busy_timeout` becomes [`InventoryBusyError`](file:///home/src/wishenka/wishlists/exceptions.py#L52-L59) and changes nothing.
   - **Surprise Invariant**: Gift recipients receive [`WishItemRecipientViewDTO`](file:///home/src/wishenka/wishlists/schemas.py#L14-L35) strictly devoid of reservation statuses, gifter identities, or booked quantities.
8. **RESTful Wish Items CRUD API & Atomic Reordering**:
   - Complete endpoint suite mounted at `/api/wishlists/{wishlist_id}/items` supporting item creation, listing, detail reading, patch updating, atomic reordering, safe archiving, and restoring.
   - Reordering enforces strict 1:1 active permutation integrity: the request must include all active item IDs with zero duplicates, contiguous display indexing ($0, 1, \dots, N-1$), and transactional commit.
9. **Collaborative Wishlist Targeting & Dual-Role Projections**:
   - Items can be designated for specific members via `recipient_user_id` or descriptive `recipient_name`.
   - Access control verifies `recipient_user_id` belongs to the wishlist's active members.
   - Dual-role projection: recipients see clean recipient views (`WishItemRecipientViewDTO`), while collaborators and gifters see full booking and availability states (`WishItemGifterViewDTO`). Per `WISHENKA-154` (`FR-4` / Q11), a co-author who is also the recipient retains full author rights (edit, archive/restore, record/undo/correct receipt) under strict surprise protection and cannot self-book, while acting as a normal gifter on other wishes in the list.
10. **Safe Archiving & End-of-List Restoration**:
    - Archiving acts as a non-destructive soft-delete (`is_archived = True`), preserving all active reservations in the database while immediately hiding the item from default listings and blocking new bookings.
    - Restoring reactivates the item (`is_archived = False`) and safely appends it to the tail of the active display order (`display_order = max(active_orders) + 1`).
11. **Telegram Mini App (TMA) HTMX Wish Item UI & BottomSheet Modals**:
    - Server-rendered Jinja2 + HTMX interface mounted at `/web/wishlists/{wishlist_id}` ([`wishenka/web/routes/items_ui.py`](file:///home/src/wishenka/web/routes/items_ui.py)) providing a fixed bottom Universal Quick Add Bar (`partials/item_quick_add.html`), debounced live URL preview card (`partials/item_preview_card.html`), Out-of-Band (`hx-swap-oob`) DOM updates, and a detailed creation/editing bottom-sheet modal (`partials/item_edit_modal.html`) with visual Reduction Lock enforcement, HTTP 409 quantity recovery, and HTTP 503 when the wish is busy.
12. **VCR-Compatible Marketplace Web Cassette Testbench (`wishenka.items.cassettes`, `WISHENKA-97`)**:
    - Offline-first recording, sanitization, and deterministic replay engine built on [`CassetteTransport(httpx.AsyncBaseTransport)`](file:///home/src/wishenka/items/cassettes.py#L498) and VCR-compatible YAML cassettes (`tests/cassettes/marketplaces/*.yaml`).
    - Supports three execution modes via [`CassetteMode`](file:///home/src/wishenka/items/cassettes.py#L88) (`REPLAY`, `RECORD`, `REFRESH` or `WISHENKA_CASSETTE_MODE`), fail-closed offline verification raising [`CassetteMissError`](file:///home/src/wishenka/items/exceptions.py#L75) on unrecorded requests, automatic stripping of sensitive headers/cookies/query tokens (`sanitize_headers`, `sanitize_uri`, `sanitize_interaction`), and a CLI audit tool (`python -m wishenka.items.cassettes --verify` / `--mode record|refresh`).

---

## Architecture & Components

The items subsystem consists of eleven core architectural building blocks:

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

Located in [`wishenka/items/ssrf.py`](file:///home/src/wishenka/items/ssrf.py) (with public symbols also re-exported from [`wishenka/items/__init__.py`](file:///home/src/wishenka/items/__init__.py#L67-L74)).

Provides policy resolution from application settings, credential redaction, non-blocking IP validation, cached hostname resolution with policy-aware single-flight coalescing, and HTTPX transport-level request interception:

- **Backward-Compatible Default Constants** (derived from [`wishenka/config.py`](file:///home/src/wishenka/config.py#L11-L35)):
  - [`MAX_RESPONSE_BYTES`](file:///home/src/wishenka/items/ssrf.py#L34) `= DEFAULT_SSRF_MAX_RESPONSE_BYTES` (`2 * 1024 * 1024` / 2 MB).
  - [`ALLOWED_SCHEMES`](file:///home/src/wishenka/items/ssrf.py#L35) `= frozenset(DEFAULT_SSRF_ALLOWED_SCHEMES)` (`frozenset({"http", "https"})`).
  - `DEFAULT_DNS_CACHE_TTL_SECONDS = 60.0` (60 seconds).
  - `DEFAULT_DNS_CACHE_CAPACITY = 512` (512 normalized `(host, port)` entries).
  - [`FORBIDDEN_NETWORKS`](file:///home/src/wishenka/items/ssrf.py#L39-L41): tuple of 20 default `ipaddress` CIDR networks parsed from `DEFAULT_SSRF_FORBIDDEN_CIDRS` covering private RFC 1918, CGNAT (`100.64.0.0/10`), loopback (`127.0.0.0/8`, `::1`), link-local (`169.254.0.0/16`, `fe80::/10`), cloud metadata (`169.254.169.254`), multicast (`224.0.0.0/4`, `ff00::/8`), broadcast (`255.255.255.255/32`), and IPv6 ULA (`fc00::/7`).
- **[`SSRFPolicy`](file:///home/src/wishenka/items/ssrf.py#L45-L72), [`get_default_ssrf_policy()`](file:///home/src/wishenka/items/ssrf.py#L182-L197), [`resolve_ssrf_policy()`](file:///home/src/wishenka/items/ssrf.py#L213-L228), and [`_active_policy_var`](file:///home/src/wishenka/items/ssrf.py#L76-L79)**:
  - `SSRFPolicy` is an immutable (`frozen=True, slots=True`) dataclass holding `max_response_bytes`, `allowed_schemes: frozenset[str]`, and `forbidden_networks: tuple[IPNetwork, ...]`. `__post_init__` enforces `max_response_bytes >= 1`, non-empty `allowed_schemes`, and `allowed_schemes.issubset(SUPPORTED_SSRF_SCHEMES)`.
  - `SSRFPolicy.from_settings(settings=None)` compiles a `Settings` instance (defaulting to `Settings()`) into a new `SSRFPolicy` on each call, pre-parsing `ssrf_forbidden_cidrs` into `IPNetwork` tuples and normalizing `ssrf_allowed_schemes` into a `frozenset[str]`.
  - `get_default_ssrf_policy()` computes a lightweight env/`.env` snapshot key (`_current_ssrf_env_signature()`) over `WISHENKA_SSRF_MAX_RESPONSE_BYTES`, `WISHENKA_SSRF_ALLOWED_SCHEMES`, `WISHENKA_SSRF_FORBIDDEN_CIDRS`, and `(cwd, .env mtime_ns, .env size)`. Matching snapshots return the cached `SSRFPolicy` without re-parsing `.env`; changes instantiate `Settings()`, refresh `_default_policy_cache`, and emit `ssrf_policy_loaded` (`DEBUG`). Invalid env/`.env` values raise `pydantic.ValidationError` fail-fast without poisoning the cache.
  - `_active_policy_var` (`ContextVar[SSRFPolicy | None]`) and [`_use_ssrf_policy(policy)`](file:///home/src/wishenka/items/ssrf.py#L201-L210) propagate an active policy across `await` boundaries (including HTTPX request hooks and 2-argument `resolve_and_validate_host(host, port)` calls) without altering existing call signatures or breaking monkeypatched test stubs.
  - `resolve_ssrf_policy(*, settings=None, policy=None)` enforces mutual exclusion between `settings` and `policy` (`ValueError`), resolving in order: explicit `policy` -> `SSRFPolicy.from_settings(settings)` -> `_active_policy_var.get()` -> `get_default_ssrf_policy()`.
- **[`redact_url_credentials(url)`](file:///home/src/wishenka/items/ssrf.py#L107-L115)**:
  - Strips `username` and `password` userinfo via `httpx.URL(url).copy_with(username="", password="")` (returning `"[invalid-url]"` on malformed URLs) before any SSRF, payload-size, or preview warning logs write a URL, and before `ItemPreviewService.fetch_preview` derives `url_domain` or `store_name`.
- [`is_ip_safe(ip, *, forbidden_networks=None)`](file:///home/src/wishenka/items/ssrf.py#L270-L282):
  - Accepts `str`, `ipaddress.IPv4Address`, or `ipaddress.IPv6Address` and resolves `active_networks` from explicit `forbidden_networks` if given, otherwise from `resolve_ssrf_policy().forbidden_networks` (`_active_policy_var` or `get_default_ssrf_policy()`).
  - Checks membership in `active_networks`, recursively unwraps IPv6-mapped IPv4 addresses (e.g. `::ffff:93.184.216.34` or `::ffff:127.0.0.1`) passing the same `active_networks`, and **unconditionally** enforces baseline `ipaddress` safety checks (`not ip.is_global`, `ip.is_private`, `ip.is_loopback`, `ip.is_link_local`, `ip.is_multicast`, `ip.is_reserved`, `ip.is_unspecified`) regardless of `ssrf_forbidden_cidrs` (so even an empty `ssrf_forbidden_cidrs=()` / `'[]'` never permits internal, loopback, CGNAT, or metadata addresses).
- [`DNSCacheEntry`](file:///home/src/wishenka/items/ssrf.py#L286-L290), [`DNSCache`](file:///home/src/wishenka/items/ssrf.py#L298-L361), and [`clear_dns_cache()`](file:///home/src/wishenka/items/ssrf.py#L371-L373) (`WISHENKA-94`):
  - `DNSCacheEntry(ips: tuple[str, ...], expires_at: float)` is an immutable (`frozen=True, slots=True`) dataclass storing SSRF-validated IP strings and a `time.monotonic()` expiration timestamp.
  - `DNSCache(capacity=DEFAULT_DNS_CACHE_CAPACITY, ttl=DEFAULT_DNS_CACHE_TTL_SECONDS)` is a bounded in-memory TTL and LRU cache backed by `OrderedDict[tuple[str, int], DNSCacheEntry]`.
  - Keys are normalized via `_normalize_dns_key(host, port)` to `(host.strip("[]").lower().rstrip("."), port)`.
  - `get(host, port)` checks whether an entry exists and `expires_at > time.monotonic()`. Expired entries are lazily removed (emitting `dns_cache_expired` at `DEBUG`); valid hits refresh LRU ordering via `move_to_end` and return a fresh `list(entry.ips)` copy so caller mutations cannot corrupt cached state.
  - `put(host, port, ips)` stores non-empty validated IP tuples when `capacity > 0` and `ttl > 0`, refreshes LRU position, and evicts the least-recently-used entries (`popitem(last=False)`) when `len(_entries) > capacity` (emitting `dns_cache_evicted` at `DEBUG`).
  - `clear_dns_cache()` resets the process-local `_dns_cache` singleton (invoked automatically before and after every pytest test by the `autouse` `_clear_dns_cache` fixture in [`tests/conftest.py`](file:///home/src/tests/conftest.py)).
- [`resolve_and_validate_host(host, port=80, *, forbidden_networks=None)`](file:///home/src/wishenka/items/ssrf.py#L473-L614) & Policy-Isolated Single-Flight Coalescing (`_in_flight_resolutions`):
  - Resolves `active_networks` from explicit `forbidden_networks` or the active `SSRFPolicy` (`_active_policy_var` / `get_default_ssrf_policy()`).
  - If `host` is a direct IP literal, validates it directly against `active_networks` and baseline safety checks without touching `_dns_cache`.
  - For domain names, checks `_dns_cache.get(clean_host, port)` first; on hit, **re-validates every cached IP** against `active_networks` before logging `dns_cache_hit` (`DEBUG`, with `forbidden_cidr_count`) and returning. If a cached IP violates a stricter active policy's `forbidden_networks`, logs `ssrf_blocked` (`WARNING`, `cache_revalidation=True`, `forbidden_cidr_count`) and raises [`SSRFBlockedError`](file:///home/src/wishenka/items/exceptions.py#L26) without evicting the shared `_dns_cache` entry for other callers.
  - On cache miss, coordinates concurrent lookups on the same event loop via `_in_flight_resolutions` (`WeakKeyDictionary[asyncio.AbstractEventLoop, dict[tuple[tuple[str, int], tuple[IPNetwork, ...]], asyncio.Future[list[str]]]]`), keying single-flight coalescing by `(_normalize_dns_key(clean_host, port), active_networks)` so concurrent requests under differing CIDR policies never cross-contaminate:
    - If an in-flight `Future` already exists for `(loop, key)`, follower coroutines log `dns_single_flight_coalesced` (`DEBUG`) and await `asyncio.shield(existing_future)`, returning a fresh `list(...)` copy without spawning duplicate `loop.getaddrinfo` threadpool calls.
    - Otherwise, the leader coroutine logs `dns_cache_miss` (`DEBUG`), registers a new `Future`, calls `_resolve_and_validate_uncached(host, clean_host, port, active_networks)` (`await loop.getaddrinfo(clean_host, port, proto=socket.IPPROTO_TCP)`), and verifies that **all** resolved IP addresses pass `_is_ip_safe_for_networks(ip_obj, active_networks)`. If any resolved address is restricted, immediately raises [`SSRFBlockedError`](file:///home/src/wishenka/items/exceptions.py#L26).
  - **No Negative Caching**: `SSRFBlockedError`, `socket.gaierror`, `OSError`, and empty resolution results (`[]`) are **never** stored in `_dns_cache`. Only non-empty IP lists where every address passed validation are cached.
  - Covered by [`tests/test_dns_cache.py`](file:///home/src/tests/test_dns_cache.py) and [`tests/test_ssrf_configurable_settings.py`](file:///home/src/tests/test_ssrf_configurable_settings.py).
- [`_pinned_ips_var`](file:///home/src/wishenka/items/ssrf.py#L617-L620):
  - `ContextVar[dict[tuple[str, int], list[str]] | None]` that isolates validated IP lists per async task keyed by `(clean_host, port)` across concurrent requests.
- [`SSRFSafeNetworkBackend`](file:///home/src/wishenka/items/ssrf.py#L623-L747):
  - Subclass of `httpcore.AsyncNetworkBackend` wrapping the connection pool's inner network backend and holding an optional pinned `policy: SSRFPolicy | None`.
  - `connect_tcp`: reads pinned IPs for `(host.strip("[]"), port)` from `_pinned_ips_var`; on pinned-cache miss, resolves `active_policy = resolve_ssrf_policy(policy=self._policy)`, logs `ssrf_pinned_cache_miss` (`DEBUG` with `policy_source` `"pinned"`/`"ambient"` and `forbidden_cidr_count`), and calls `resolve_and_validate_host(clean_host, port)` inside `with _use_ssrf_policy(active_policy):`. Deduplicates IPs and tries each numeric IP sequentially via `self._inner.connect_tcp(host=ip, ...)` without ever passing the raw hostname to the underlying socket backend. Raises `httpcore.ConnectError` if the validated IP list is empty or all pinned attempts fail.
  - Offline backend regression tests in `tests/test_ssrf_dns_rebinding.py` check that failed DNS
    resolution never connects to an unvalidated hostname, exhausted pinned addresses produce
    `ssrf_all_pinned_connects_failed` with the unique attempt count, and duplicate addresses are
    attempted once in their original order. An exhausted `OSError` is chained to the resulting
    `httpcore.ConnectError`. Run the focused module with:

    ```bash
    PYTHONPATH=. .venv/bin/pytest tests/test_ssrf_dns_rebinding.py -q
    ```
  - `connect_unix_socket`: blocks Unix domain socket connections with `SSRFBlockedError(..., reason="uds")`.
  - `sleep`: delegates to `self._inner.sleep`.
- [`SSRFSafeTransport`](file:///home/src/wishenka/items/ssrf.py#L750-L867):
  - Subclass of `httpx.AsyncHTTPTransport` accepting optional keyword-only `policy: SSRFPolicy | None = None` or `settings: Settings | None = None` (mutually exclusive; specifying either pins `self._policy` and emits `ssrf_policy_configured` at `DEBUG`, whereas zero-arg construction validates ambient `get_default_ssrf_policy()` at init if `_active_policy_var` is unset so invalid `WISHENKA_SSRF_*` env vars fail fast, while keeping `self._policy = None` to follow `_active_policy_var` or runtime env changes).
  - Installs `SSRFSafeNetworkBackend(backend, policy=self._policy)` into the expected connection pool. Unknown pool or backend layouts fail closed; dispatch also checks that the pinned backend has not been replaced (`reason="unsafe_backend"`).
  - Overrides `handle_async_request(request)` to intercept the initial request and every subsequent HTTP redirect hop (`301`, `302`, `303`, `307`, `308`).
  - Rejects URL credentials and `Authorization` headers (`log_ssrf_credentials_blocked`, `reason="credentials"`), resolves `active_policy = resolve_ssrf_policy(policy=self._policy)`, validates `request.url.scheme` against `active_policy.allowed_schemes` (logging credential-redacted `url` via `log_ssrf_invalid_scheme` and raising [`InvalidUrlSchemeError`](file:///home/src/wishenka/items/exceptions.py#L43)), rejects missing hosts (`SSRFError`), resolves and validates the destination under `with _use_ssrf_policy(active_policy):`, and pins the validated IPs in `_pinned_ips_var` inside a `try ... finally: _pinned_ips_var.reset(token)` block around `super().handle_async_request(request)` without rewriting `request.url` (preserving the `Host` header, TLS SNI `server_hostname`, relative redirect resolution, and `response.url`).
  - Covered by [`tests/test_ssrf_dns_rebinding.py`](file:///home/src/tests/test_ssrf_dns_rebinding.py) and [`tests/test_ssrf_configurable_settings.py`](file:///home/src/tests/test_ssrf_configurable_settings.py) (pinned-IP connection, redirect-hop pinning, Host/TLS SNI preservation, IPv6 pinning, multi-IP failover, concurrent `ContextVar` isolation, defense-in-depth fallback, configurable schemes/CIDRs, and UDS blocking).

### 4. Safe HTML Fetcher [`UrlMetadataService`](file:///home/src/wishenka/items/fetcher.py#L279-L518)

Located in [`wishenka/items/fetcher.py`](file:///home/src/wishenka/items/fetcher.py).

Dedicated network service responsible for pulling HTML bodies under strict security constraints:
- Accepts optional `max_bytes: int | None = None`, `timeout: httpx.Timeout = DEFAULT_TIMEOUT` (`4.0s` total, `2.0s` connect), and keyword-only `settings: Settings | None = None` or `policy: SSRFPolicy | None = None` (plus `DEFAULT_HEADERS` for storefront compatibility).
- Resolves `base_policy = resolve_ssrf_policy(settings=settings, policy=policy)`; when `max_bytes` is explicitly supplied, rejects `bool` or values `< 1` (`ValueError`) and applies `dataclasses.replace(base_policy, max_response_bytes=max_bytes)`, storing `self.policy` and `self.max_bytes = effective_policy.max_response_bytes` (emitting `ssrf_policy_configured` at `DEBUG` when `settings`, `policy`, or `max_bytes` is supplied).
- **URL & Hook Helpers ([`validate_url`](file:///home/src/wishenka/items/fetcher.py#L69-L98), [`_validate_request`](file:///home/src/wishenka/items/fetcher.py#L101-L109), [`safe_direct_route`](file:///home/src/wishenka/items/fetcher.py#L217-L231))**:
  - `validate_url(url, *, policy=None, settings=None)` resolves `active_policy = resolve_ssrf_policy(settings=settings, policy=policy)`, rejects URL userinfo credentials (`log_ssrf_credentials_blocked`, `SSRFBlockedError(..., reason="credentials")`), validates the scheme against `active_policy.allowed_schemes` (`log_ssrf_invalid_scheme`, `InvalidUrlSchemeError`), and runs `resolve_and_validate_host(parsed.host, port)` inside `with _use_ssrf_policy(active_policy):`.
  - `_validate_request(request)` strips `cookie`, blocks `authorization` headers (`log_ssrf_credentials_blocked`, `reason="credentials"`), and delegates to `await validate_url(str(request.url))` (preserving the 1-arg HTTPX request hook / `wishenka.items.cassettes` contract while inheriting `_active_policy_var` from `_fetch_html`).
  - `safe_direct_route(*, limits=None, settings=None, policy=None)` constructs a [`PreviewRoute`](file:///home/src/wishenka/items/fetcher.py#L179-L185) wrapping `SSRFSafeTransport` with forwarded `limits`, `settings`, and `policy`.
- **Internal `_fetch_html(url, client=None, routes=None)`**:
  - Rejects URL userinfo credentials (`reason="credentials"`) and validates URL scheme against `self.policy.allowed_schemes` (`InvalidUrlSchemeError`).
  - Rejects an opaque `client`, even when `routes` are also supplied, before DNS or dispatch. Use `PreviewTransportConfig` instead; the caller retains ownership of supplied routes.
  - Enters `with _use_ssrf_policy(self.policy):`, pre-validates destination host via `resolve_and_validate_host(host, port)`, and builds an isolated HTTPX client (`trust_env=False`, `CookieJar(policy=RejectCookies())`, `event_hooks={"request": [_validate_request]}`):
    - With no routes, creates `safe_direct_route(policy=self.policy)` and closes it in `finally`.
    - With explicit routes, builds non-owning `_BorrowedTransport` wrappers around the supplied transports.
  - Executes streaming download via `_stream_and_read`.
- **Early Fast-Fail & Streaming Accumulator (`_stream_and_read`)**:
  - Checks response header `Content-Length`. If `> self.max_bytes` (default 2 MB / `2,097,152` bytes, or configured `ssrf_max_response_bytes` / `max_bytes`), logs credential-redacted `payload_size_violation` (`reason="content_length_exceeded"`), aborts, and raises [`ResponseBodyTooLargeError`](file:///home/src/wishenka/items/exceptions.py#L56).
  - Iterates asynchronously over chunks via `response.aiter_bytes()`, tracking `total_bytes`. If cumulative size exceeds `self.max_bytes`, halts iteration immediately, logs credential-redacted `payload_size_violation` (`reason="stream_chunk_overflow"`), and raises [`ResponseBodyTooLargeError`](file:///home/src/wishenka/items/exceptions.py#L56).
  - Decodes accumulated raw bytes with `decode_html` after status and size checks. The buffered
    compatibility path uses the same decoder.
- **Safe Fallback Wrapper `fetch_and_extract(url, client=None, routes=None)`**:
  - High-level interface that calls `_fetch_html` and feeds the result to `HtmlMetadataExtractor.extract`.
  - Catches network, security, and parsing exceptions, logging a credential-redacted `fetch_and_extract_fallback` warning and returning a safe fallback [`ExtractedMetadata`](file:///home/src/wishenka/items/models.py#L34-L46) populated with `store_name=derive_store_name(url)`.
  - Explicitly re-raises [`CassetteError`](file:///home/src/wishenka/items/exceptions.py#L71) (including [`CassetteMissError`](file:///home/src/wishenka/items/exceptions.py#L75)) before the generic exception handler so missing cassette interactions fail closed during offline test replay.

#### Explicit preview routes

`PreviewTransportConfig(default, mounts)` snapshots its mount mapping. Use
`safe_direct_route(settings=..., policy=...)` for a pinned direct route, `deny_route()` for a
forbidden route, or `offline_replay_route()` for immutable response fixtures. HTTPX selects the
most specific mount for every request and redirect. A denied route never falls back to a
less-specific route. Factories bind each approved route to its original transport; arbitrary
transports and substituted routes are rejected. Per-preview clients have isolated headers, cookies
and authentication state; their non-owning wrappers do not close the route transport on completion
or cancellation.

A route rejection emits `item_preview_route_rejected` with `unknown_route` or `route_denied`,
without the URL or client data. If a preview falls back with `ssrf_blocked`, inspect this event
and migrate callers using `client=` to an explicit route configuration. Do not replace a rejected
route with an unvalidated client or enable environment proxies.

#### Extraction execution and responsiveness

`ItemPreviewService.fetch_preview` and `UrlMetadataService.fetch_and_extract` both await
`asyncio.to_thread(HtmlMetadataExtractor.extract, ...)` after the protected fetch. The extractor
itself remains synchronous and returns the same metadata; use the async service methods from
event-loop code rather than calling `extract` directly there. Each service retains its existing
exception handling and fallback result. SSRF checks, anti-bot checks, and response limits are
unchanged.

The calls share the event loop's default executor and need no additional configuration or parser
dependency. Its worker count is bounded, but submissions can queue. Cancelling the awaiting
request does not stop an extraction already running in a worker. Python's GIL and concurrent
parsing can still affect latency; thread offload is not a latency guarantee under saturation.
The network timeout settings below apply to HTTP activity, not as a deadline on worker parsing.

`tests/test_metadata_extractor_service.py` checks both service paths, including a real HTML
document over 1 MiB and a concurrent `/healthz` request. Its one-second test bound applies to
that controlled workload, not every deployment. Further load and queue analysis is tracked in
[WISHENKA-113](https://pypost.atlassian.net/browse/WISHENKA-113).

#### HTML encoding policy

`wishenka.items.encoding.decode_html(raw, content_type)` converts response bytes to text without
I/O. A recognized BOM takes precedence; otherwise strict non-ASCII UTF-8 wins over conflicting
legacy declarations. Next, valid HTTP charset and then HTML meta declarations are tried in order.
The header scan is limited to 1024 characters and the HTML meta scan to the first 4096 bytes;
unsupported, malformed, non-text or overlong codec labels are ignored. When declarations are
missing or unusable, strict UTF-8 is followed by a bounded Russian-language plausibility score
for CP1251 and KOI8-R. Low-confidence input falls back to UTF-8 replacement decoding.

Windows-1251 and CP1251 are aliases. Single-byte encodings can decode the same bytes, so the
heuristic cannot guarantee the original encoding; a valid but incorrect header also takes
precedence over a conflicting legacy meta declaration. Users can correct preview fields. This
policy is fixed in code and has no environment settings. Offline coverage for both fetch paths
and ambiguous or malformed inputs is in `tests/test_encoding_nested_graph.py`.

### 5. Cascading HTML Metadata Extractor [`HtmlMetadataExtractor`](file:///home/src/wishenka/items/parser.py#L419-L868)

Located in [`wishenka/items/parser.py`](file:///home/src/wishenka/items/parser.py).

Parses HTML documents using `BeautifulSoup4` with a multi-level fallback cascade:
- **1. JSON-LD Cascade (`_find_jsonld_products`)**:
  - Traverses `<script type="application/ld+json">` elements using bounded iterator frames and
    discovery-local `@type` memoization (see *Bounded JSON-LD traversal and type memoization*
    below).
  - Searches `@graph` objects and arrays first, matching `Product` and namespaced `.../Product`
    types; discovery and `@type` inspection each stop at 20,000 visited nodes or depth 128.
    Discovery retains earlier results; invalid or over-limit data can fall through to later
    scripts and metadata sources. Remote contexts and `@id` references are not dereferenced.
  - Extracts title (`name`), description (`description`), image (`image`), and brand (`brand`).
  - Supports both standard `Offer` and `AggregateOffer` price extraction (`offers.price`, `offers.lowPrice`, `offers.highPrice`), recording `jsonld_aggregate_offer_extracted`.
- **2. OpenGraph Cascade**:
  - Scrapes `meta[property="og:*"]` (`og:title`, `og:description`, `og:image`, `og:site_name`) and `meta[property="product:*"]` (`product:price:amount`, `product:price:currency`).
- **3. Microdata Cascade**:
  - Scrapes elements with `[itemprop="name"]`, `[itemprop="description"]`, `[itemprop="image"]`, `[itemprop="price"]`, and `[itemprop="priceCurrency"]`.
- **4. Standard HTML Fallback**:
  - Scrapes `<title>`, `<meta name="description">`, and `<link rel="icon">`.
- **Sanitization Helpers**:
  - [`clean_title`](file:///home/src/wishenka/items/parser.py#L173-L188): Removes store advertising noise and marketing suffixes (e.g. `— купить в интернет-магазине Ozon`, `на маркетплейсе Wildberries`, `объявление на Авито`).
  - `parse_decimal_price` parses localized positive prices as floats; `parse_price` is the
    legacy whole-unit helper and truncates the fraction. The preview uses the decimal helper.
  - `extract_currency` recognizes supported codes and inline labels; `normalize_currency`
    resolves the currency or falls back to `RUB`. See the pricing notes below.
  - [`derive_store_name`](file:///home/src/wishenka/items/parser.py#L362-L390): Resolves store name via priority: OpenGraph `og:site_name` $\rightarrow$ brand $\rightarrow$ `KNOWN_STORES` domain map $\rightarrow$ [`MarketplaceRegistry.derive_store_name`](file:///home/src/wishenka/items/marketplaces.py#L210) $\rightarrow$ clean domain.

#### International prices and currency

`HtmlMetadataExtractor.extract(html, base_url)` selects the first valid positive JSON-LD offer
price, including offer lists, nested offers, and `priceSpecification`. It pairs the selected price
with its offer currency; an inline currency in that price takes precedence over unrelated
OpenGraph currency metadata. If no usable JSON-LD price is found, OpenGraph and then microdata
can supply it. `price`, `lowPrice`, `minPrice`, `highPrice`, and `maxPrice` are checked in that
order. Invalid, zero, and negative offer prices are skipped.

`parse_decimal_price(value)` accepts finite positive numbers and localized price strings. It
handles decimal commas and dots, grouped thousands, and Unicode spaces. With a single separator
and exactly three trailing digits, a nonzero integer prefix is interpreted as thousands grouping;
a zero prefix is interpreted as a fractional amount. This is an intentional default where the
source does not provide locale information. `parse_price(value)` remains available for callers
that need integer units and truncates the fractional part; do not use it for a preview price.

`extract_currency(text)` recognizes codes, names, and symbols for `RUB`, `USD`, `EUR`, `KZT`,
`BYN`, `CNY`, `GBP`, `JPY`, `TRY`, `GEL`, and `AMD`. `normalize_currency` accepts a separate
currency and optional `fallback_text` containing the price. An unqualified `¥` defaults to CNY;
an explicit JPY or CNY marker disambiguates it. An unrecognized currency defaults to `RUB`.
Aliases, known stores, and recognized implicit URL suffixes are static lists in the parser and
classifier, rather than environment settings.

For example:

```python
from wishenka.items.parser import extract_currency, parse_decimal_price

assert parse_decimal_price("1.299,99 €") == 1299.99
assert parse_decimal_price("0,50 €") == 0.5
assert extract_currency("1.299,99 €") == "EUR"
assert parse_decimal_price("-EUR 25") is None
```

Preview and wish DTOs accept `int | float | None`: whole amounts remain integers and fractional
amounts pass through quick-add, edit, storage, and the gift-giver view. The existing SQLite
`wl_items.price` column has INTEGER affinity, but SQLite stores non-integral numeric values as
REAL; existing integer records remain compatible and no migration is required for SQLite. These
are major currency units, not integer minor units. Python floats and SQLite REAL use binary
floating point, so callers requiring exact decimal accounting must not treat this representation
as a fixed-point ledger. The edit form offers all supported currencies and preserves a previously
stored unknown currency as an option.

For troubleshooting, inspect `metadata_extraction_completed`, `inline_currency_extracted`,
`currency_fallback_default`, `jsonld_price_specification_extracted`, and
`jsonld_aggregate_offer_extracted` logs. Offer diagnostics contain parsed numeric values and
recognized currency, not raw merchant offer content. If a preview falls back to RUB, check the
source currency and supported aliases. If separators are ambiguous, compare the source locale
with the deterministic rules above. Run the focused regression suite with
`make test` or `.venv/bin/pytest tests/test_international_currency_parsing.py`; the latter covers
localized numbers, currency labels, JSON-LD offers, and the preview path.

#### Bounded JSON-LD traversal and type memoization

Product discovery and `@type` checking in [`wishenka/items/parser.py`](file:///home/src/wishenka/items/parser.py)
use lazy iterator frames so temporary traversal stack storage depends only on depth, never on
list or object width:

- **Product discovery (`_walk_jsonld_products`, `_find_jsonld_products`)**:
  - `_find_jsonld_products(data)` delegates to `_walk_jsonld_products(data)[0]` and preserves
    `@graph`-first order: for each `dict`, a `list` or `dict` `@graph` value is traversed first
    (logging `jsonld_graph_traversal` at `DEBUG` with `graph_items_count`), then the `dict`
    itself is evaluated, and finally its non-`@graph` values are traversed in insertion order.
  - Instead of copying `dict.items()` or pushing all siblings eagerly, traversal pushes lazy
    `("iterate", iter(...), depth)` frames and at most one deferred `("process", node, depth)`
    record per active `dict`. Across depths `0..128` plus one depth-`129` child, pending stack
    records are bounded at `<= 262`, independent of container width.
  - Non-process visits consume `1` of the `20,000`-visit budget (`"iterate"` and `"process"`
    bookkeeping consume `0`). Before every logical pop—including before a deferred `"process"`
    action—the loop stops immediately when `visited >= 20_000`. Nodes at depth `128` remain
    visitable and may enqueue depth-`129` children, which consume `1` visit and skip descending
    (`depth > 128`). Earlier results (up to `20,000` matching `dict` references) are retained; if
    `depth > 128` or pending stack frames remain at exit, `jsonld_discovery_limit` is logged at
    `DEBUG` with `visited_nodes`.
- **Lazy `@type` inspection (`_walk_product_type`, `_is_product_type`)**:
  - `_is_product_type(type_val)` delegates to `_walk_product_type(type_val)[0]`, inspecting only
    `str` values and nested `list` containers left-to-right (`dict` and other values are
    non-matching leaves).
  - Nested lists use lazy `("iterate", iter(value), depth + 1)` frames, bounding pending stack
    records to `<= 131` frames regardless of list width, and stop immediately on the first `str`
    whose stripped lowercase value is `"product"` or ends with `"/product"`.
  - Applies the same `20,000`-visit and depth-`128` limits; hitting either limit without an
    earlier match emits `jsonld_type_limit` at `DEBUG` with `visited_nodes` and records
    `visited` in `_type_limit_collector` when active.
- **Discovery-local `@type` memoization and telemetry replay**:
  - Each `_walk_jsonld_products` invocation allocates a fresh `memo` capped at `20,000` entries
    and never shares it across `<script>` blocks, invocations, or requests.
  - Scalar `@type` values (`str`, `int`, `float`, `bool`, `None`) use key
    `(type(type_val), type_val)`. `list`-valued `@type` values use `("list", id(type_val))` while
    retaining a strong reference to `type_val` inside `memo` for the duration of the walk so
    `id()` values cannot be recycled mid-traversal; non-scalar/non-list objects (such as `dict`)
    bypass memoization. Because `json.loads()` creates distinct `list` instances per JSON array,
    list-identity memoization deduplicates shared in-process `list` references rather than
    structurally equal distinct JSON arrays, and assumes inputs do not mutate during traversal.
  - Each uncached candidate retains its own `20,000`-visit `@type` budget so earlier wide types
    never starve later candidates; for fetched HTML within the configured response-size
    limit (2 MB by default), `json.loads()` yields a strict tree whose total nodes across scripts are bounded
    linearly by the response bytes.
  - On a memo miss, `_walk_jsonld_products` captures limit-hit `visited_nodes` via the
    `_type_limit_collector` `ContextVar` around `_is_product_type(type_val)`. On a memo hit whose
    first evaluation hit a limit, it replays `jsonld_type_limit` at `DEBUG` with the recorded
    `visited_nodes` without re-traversing `@type`.
- **Diagnostics and verification**:
  - `HtmlMetadataExtractor._jsonld_traversal_diagnostics(walk, data)` runs `"discovery"` or
    `"type"` and returns `(result, peak_pending)` from the live stack length for per-invocation
    bounds assertions.
  - Deterministic offline checks live in
    [`tests/test_jsonld_traversal_bounds.py`](file:///home/src/tests/test_jsonld_traversal_bounds.py)
    (`pytestmark = pytest.mark.timeout(30)`), verifying lazy `CountingList` / `CountingDict`
    reads, bounded `tracemalloc` traversal memory (`< 512 KiB`), exact `20,000`-visit and
    depth-`128` boundaries, `@graph`-first ordering, `<= 262` / `<= 131` pending-record bounds,
    discovery-local memoization, and `DEBUG` telemetry without raw payload leaks. Run with
    `.venv/bin/pytest tests/test_jsonld_traversal_bounds.py`.

### 6. Link Preview Orchestrator & Graceful Fallback [`ItemPreviewService`](file:///home/src/wishenka/items/service.py#L67-L508)

Located in [`wishenka/items/service.py`](file:///home/src/wishenka/items/service.py).

Asynchronous facade orchestrating input classification, URL cleaning, policy-aware secure fetching, anti-bot detection, and graceful degradation:
- Accepts optional `url_metadata_service`, `client`, `cache`, `routes`, and keyword-only `settings: Settings | None = None` or `policy: SSRFPolicy | None = None` in `__init__`:
  - When `settings` or `policy` is supplied, resolves `self.policy = resolve_ssrf_policy(settings=settings, policy=policy)` and logs `ssrf_policy_configured` (`DEBUG`).
  - Otherwise, inherits `url_metadata_service.policy` only when `isinstance(getattr(url_metadata_service, "policy", None), SSRFPolicy)` (preserving `MagicMock` compatibility for injected test doubles), or falls back to `resolve_ssrf_policy()`.
  - When `url_metadata_service` is `None`, creates `UrlMetadataService(timeout=DEFAULT_TIMEOUT, policy=self.policy)`.
- Wired with application `Settings` across all runtime entrypoints:
  - [`create_app`](file:///home/src/wishenka/web/app.py#L161-L289) passes `settings=settings` to [`safe_direct_route(limits=limits, settings=settings)`](file:///home/src/wishenka/web/app.py#L185) and [`ItemPreviewService(..., settings=settings)`](file:///home/src/wishenka/web/app.py#L189-L193).
  - [`preview_item_input`](file:///home/src/wishenka/web/routes/items_ui.py#L479-L481) falls back to `ItemPreviewService(settings=getattr(request.app.state, "settings", None))` when `app.state.item_preview_service` is not set.
  - [`wishenka.bot.__main__.run()`](file:///home/src/wishenka/bot/__main__.py#L63-L103) passes [`ItemPreviewService(settings=settings)`](file:///home/src/wishenka/bot/__main__.py#L85) into bot `Dependencies`.
- Invokes `UniversalInputClassifier.classify(raw_input)`:
  - For `PLAIN_TEXT`, returns manual entry preview immediately without network activity.
  - For `EXPLICIT_URL`, `IMPLICIT_URL`, and `COMPOSITE_SHARE`, sanitizes the target link via `clean_url`, strips any URL userinfo via [`redact_url_credentials`](file:///home/src/wishenka/items/ssrf.py#L107-L115) before deriving `url_domain`/`store_name` and writing warning logs, and dispatches safe preview fetching.
- **Anti-Bot Challenge & WAF Detection**:
  - Inspects upstream HTTP status codes: HTTP 403 Forbidden, HTTP 429 Too Many Requests, and HTTP 503 Service Unavailable.
  - Scans HTML bodies (including `200 OK` responses) against [`CHALLENGE_SIGNATURES`](file:///home/src/wishenka/items/service.py#L40-L64):
    - Cloudflare challenges: `_cf_chl_opt`, `challenge-running`, `just a moment...`, `cf-mitigated`, `turnstile`, `checking your browser`.
    - Generic WAFs: `access denied`, `waf`, `ddos-guard`.
    - Qrator anti-bot shield: `qrator`, `qrator_jsid`, `qrator-js`.
    - Russian marketplace anti-bot and CAPTCHA screens (`WISHENKA-97`): `доступ ограничен`, `доступ временно ограничен`, `почти готово`, `проверка браузера`, `подтвердите, что запросы отправляли вы, а не робот`, `smartcaptcha`, `showcaptcha` (Yandex SmartCaptcha), `firewall-container` (Avito IP firewall), `antibot-challenge`, `ozon-captcha`, `fab_chlg` (Ozon / Wildberries / Megamarket).
  - Intercepts challenges (both on `403`/`429`/`503` and `200 OK` HTML challenge pages) and emits `item_preview_anti_bot` and `anti_bot_challenge_detected` logs (including `status_code=200` for `200 OK` challenges), returning an `ItemPreviewDTO` with `is_fallback=True`, `fallback_reason="anti_bot_challenge"`, `store_name`, and `title=classification.residual_text` (preventing challenge page `<title>` text from leaking into wish titles).
- **Comprehensive Exception Trap**:
  - SSRF violations and disallowed schemes (`SSRFBlockedError`, `InvalidUrlSchemeError`): `fallback_reason="ssrf_blocked"`.
  - Payload overflow (`> self.policy.max_response_bytes`, default 2 MB): `fallback_reason="response_too_large"`.
  - Upstream timeout (>4.0s): `fallback_reason="timeout"`.
  - Web cassette testbench errors ([`CassetteError`](file:///home/src/wishenka/items/exceptions.py#L71) / [`CassetteMissError`](file:///home/src/wishenka/items/exceptions.py#L75)): explicitly re-raised (`except CassetteError: raise`) so unrecorded requests in offline `REPLAY` mode fail immediately instead of being masked as `fallback_reason="http_error"`.
  - Other network / HTTP errors: `fallback_reason="http_error"`.
- Prevents unhandled 500 errors and ensures Telegram Mini App users always retain access to a functional manual wish entry form with extracted residual title and clean URL.

#### Pooled requests and preview cache

The FastAPI lifespan owns one safe direct route (`safe_direct_route(limits=limits, settings=settings)`)
and one `ItemPreviewService` with a `PreviewCache` per application instance. It closes the owned
transport and clears the cache on shutdown and startup failure. Independent application instances
have independent pools, caches, and SSRF policies. Standalone `ItemPreviewService()` calls
resolve the ambient default `SSRFPolicy` and create/close their own direct transport. A per-call
route configuration bypasses the service cache; configured routes partition its keys.

The bounded in-memory cache stores copies of extracted source metadata by cleaned URL. It rebuilds
the preview with the current caller's input and residual text. A plain-text input, failure,
challenge, or fallback is never cached. Each response in a redirect chain must explicitly allow
shared caching with `Cache-Control: public`; query strings, URL credentials, `Set-Cookie`, `Vary`,
authentication challenges, and restrictive cache directives disqualify the chain. Freshness
accounts for origin age and expiry headers. Concurrent misses can still perform duplicate fetches.

Every cache hit revalidates the original and redirect destinations (`cached.urls`) via
[`validate_url`](file:///home/src/wishenka/items/fetcher.py#L69-L98) inside
`with _use_ssrf_policy(self.policy):` against the service's active DNS, CIDR, and scheme rules. If
revalidation fails (for example, a cached `http://` entry under an `https`-only policy or a host
whose IP enters `ssrf_forbidden_cidrs`), the entry is evicted from `self.cache.entries`,
`preview_cache_revalidation_evicted` is logged (`DEBUG`), and the request degrades gracefully to
`fallback_reason="ssrf_blocked"`. Outbound requests reject URL credentials and do not retain or
send cookies; opaque clients and unapproved proxy transports are rejected before dispatch. DNS
resolutions performed by [`resolve_and_validate_host`](file:///home/src/wishenka/items/ssrf.py#L473-L614)
are cached in-memory via [`DNSCache`](file:///home/src/wishenka/items/ssrf.py#L298-L361)
(`DEFAULT_DNS_CACHE_TTL_SECONDS = 60.0`, `DEFAULT_DNS_CACHE_CAPACITY = 512`) with per-event-loop
single-flight coalescing ([WISHENKA-94](https://pypost.atlassian.net/browse/WISHENKA-94)) and
cache-hit CIDR revalidation, while outbound connections via
[`SSRFSafeTransport`](file:///home/src/wishenka/items/ssrf.py#L750-L867) and
[`SSRFSafeNetworkBackend`](file:///home/src/wishenka/items/ssrf.py#L623-L747) pin validated IP
addresses per request and redirect hop to prevent DNS rebinding (TOCTOU;
[WISHENKA-92](https://pypost.atlassian.net/browse/WISHENKA-92)). Route selection uses the public
HTTPX transport interface. Connection pinning still uses private HTTPX/httpcore pool internals;
unexpected layouts fail closed. HTTPX is constrained to `>=0.28.0,<0.29`; review both HTTPX and
httpcore upgrades before deployment. Replacing that connection-layer hook is tracked in
[WISHENKA-284](https://pypost.atlassian.net/browse/WISHENKA-284).

`tests/test_preview_resource_reuse.py` covers cache eligibility and expiry, isolation, lifecycle,
redirect validation, and connection reuse with a local HTTP server. Run it through the repository
test workflow when changing preview transport or cache behavior.

`tests/test_ssrf_and_response_limits.py` also exercises IPv6 policy decisions for 6to4, Teredo,
scoped addresses, and equivalent compressed and expanded forms. Offline redirect cases use
controlled DNS and replay responses to check a safe multi-hop chain, rejection of a restricted
later hop before dispatch, and termination of a circular chain at HTTPX's redirect limit. Run the
focused regression module with:

```bash
PYTHONPATH=. .venv/bin/pytest tests/test_ssrf_and_response_limits.py -q
```

These tests do not make external network requests. If an address classification changes after a
Python upgrade, inspect the `ipaddress` policy and the configured CIDRs before updating expected
results. Browser-dependent tests in the full suite require Chromium; see
[testing.md](testing.md) for setup and troubleshooting.

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
- **Item Updates & Reduction Lock Invariant ([`update_wish_item`](file:///home/src/wishenka/wishlists/service.py#L930))**:
  - The in-process `ItemConcurrencyCoordinator` still wraps the check. It is an `asyncio.Lock` on that service instance. A second process does not share it, and the wish-scoped SQLite transaction is what excludes other copies.
  - Rejects mutations on archived items ([`WishlistArchivedError`](file:///home/src/wishenka/wishlists/exceptions.py#L16)).
  - Rejects a quantity below `max(1, received_quantity)` with
    `CannotReduceQuantityBelowReservedError` and `item_quantity_reduction_rejected`. The
    transaction rolls back. The exception name is retained for compatibility; its message
    references only received units.
  - On a reduction where received plus `ACTIVE`/`PURCHASED` reserved units exceed the new
    quantity, preserves promises and queues `item_quantity_overbooked` for distinct eligible
    givers, including an eligible editing co-author. These givers are excluded from the generic
    `item_updated` notice for the same edit. Delivery is asynchronous; see
    [notifications](notifications.md).
  - Computes `quantity_delta` and records modified fields list in structured event `item_updated`.
- **Receipt and promises** (same wish-scoped transaction when the configured store is attached):
  - `record_item_fulfillment` (keyword-only `wishlist_id`) adds `received_quantity`, appends a dated `ReceiptRecord` and drafts the giver notices. The cap is requested minus units already received. It is refused with `QuantityAboveRemainingError` (a `ValueError`) above the cap and `NothingRemainingError` when nothing remains. Receipt does not cancel or complete the promise and is not capped by occupied units. After a successful receipt, occupied plus received may exceed the requested quantity.
  - [`create_reservation`](file:///home/src/wishenka/wishlists/service.py#L1337) and an increase in [`update_reservation_quantity`](file:///home/src/wishenka/wishlists/service.py#L1699) use the free remainder `available_quantity` $= \max(0, \text{requested} - \text{received} - \text{occupied})$. A larger promise raises [`InsufficientQuantityError`](file:///home/src/wishenka/wishlists/exceptions.py#L48). A later promise still uses that remainder after a receipt.
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
  - Emits structured event `item_archived` (without reservation counts, preserving the no-presence-leak guarantee).
- **Restoration Semantics ([`restore_wish_item`](file:///home/src/wishenka/wishlists/service.py#L1186))**:
  - Sets `is_archived = False`.
  - Re-inserts item at the end of the active list: `display_order = max(active_orders, default=-1) + 1`.
  - Emits structured event `item_restored`.
- **Surprise Invariant Projections ([`project_wish_item`](file:///home/src/wishenka/wishlists/service.py#L121))**:
  - Strictly distinguishes recipient from gifter contexts using [`WishlistAccessPolicy.is_recipient`](file:///home/src/wishenka/wishlists/policy.py#L115). On a personal list the owner is the recipient of every wish, including a display-name-only wish. On a collaborative list the recipient is `recipient_user_id` only. A display name is never compared to a user.
  - Recipient caller receives [`WishItemRecipientViewDTO`](file:///home/src/wishenka/wishlists/schemas.py#L11-L37) with `is_recipient=True` and all reservation/buyer fields stripped. The wish card then omits `.item-giver`.
  - Non-recipient caller receives [`WishItemGifterViewDTO`](file:///home/src/wishenka/wishlists/schemas.py#L39-L73) containing `available_quantity`, `is_fully_reserved`, `is_reserved_by_me`, `my_reserved_quantity`, `my_reservation_status`, `my_reservation_id`, `my_latest_reservation_quantity`, and `my_occupying_reservation_count`. The wish-card summary paints giver controls from these fields. See [reservations.md](reservations.md#6-wish-card-giver-controls).

### 8. RESTful Wish Items Controller ([`wishenka.web.routes.items`](file:///home/src/wishenka/web/routes/items.py))

Located in [`wishenka/web/routes/items.py`](file:///home/src/wishenka/web/routes/items.py).

FastAPI APIRouter mounted at `/api/wishlists/{wishlist_id}/items` providing HTTP endpoints for item CRUD, reordering, and archiving:

- **Authentication Injections**:
  - `User = Annotated[AuthenticatedUser, Depends(get_current_user)]`: Enforces authenticated session for mutations (`POST`, `PUT`, `PATCH`).
  - `OptionalUser = Annotated[AuthenticatedUser | None, Depends(get_optional_current_user)]`: Allows anonymous access for public wishlist views while extracting caller credentials for personalized gifter badges when logged in.
- **Transactional Execution Wrapper ([`execute`](file:///home/src/wishenka/web/routes/items.py#L34-L104))**:
  - The handler uses the request `WishlistRepository`. Shared item actions (`add_wish_item`, list, reorder, archive, restore) run on `RepoWishlistOps(repo)`.
  - When `item_id` is set, the persistent path is [`WishlistStore.execute_wish`](file:///home/src/wishenka/wishlists/store.py#L942). `update_item` (`PATCH`) passes the item id. That wish-scoped path translates a timed-out SQLite lock to [`InventoryBusyError`](file:///home/src/wishenka/wishlists/exceptions.py#L52) before a generic storage `RuntimeError`. Reservations and receipts stay on `execute_wish`.
  - Maps domain exceptions to standard HTTP error responses. The 503 body is the exception text (`The wish was busy and the attempt changed nothing`). It names no gifter.
    - [`InventoryBusyError`](file:///home/src/wishenka/wishlists/exceptions.py#L52) $\rightarrow$ **`503 Service Unavailable`** (`event="item_inventory_busy"`, plus `item_id` when the route passed one).
    - [`WishlistNotFoundError`](file:///home/src/wishenka/wishlists/exceptions.py#L12), [`WishlistDeletedError`](file:///home/src/wishenka/wishlists/exceptions.py#L20), [`ItemNotFoundError`](file:///home/src/wishenka/wishlists/exceptions.py#L32) $\rightarrow$ **`404 Not Found`** (`event="item_not_found"`).
    - [`PermissionDeniedError`](file:///home/src/wishenka/wishlists/exceptions.py#L8) $\rightarrow$ **`403 Forbidden`** (`event="item_permission_denied"`).
    - [`WishlistArchivedError`](file:///home/src/wishenka/wishlists/exceptions.py#L16), [`CannotReduceQuantityBelowReservedError`](file:///home/src/wishenka/wishlists/exceptions.py#L44), `NothingRemainingError` $\rightarrow$ **`409 Conflict`** (`event="item_conflict"`).
    - `ValueError` (whitespace titles, invalid reorder permutations, a recipient who is not a member) $\rightarrow$ **`400 Bad Request`** (`event="item_validation_error"`). The receipt route does not use this table: it maps its own closed refusals (see [gift-receipt.md](gift-receipt.md)). `NothingRemainingError` (archive or restore of a fully received wish) joins the `409` group here.

### 9. Relational Persistence & Ordering Index ([`wl_items`](file:///home/src/wishenka/wishlists/store.py))

Located in [`wishenka/wishlists/db_models.py`](file:///home/src/wishenka/wishlists/db_models.py), [`wishenka/wishlists/store.py`](file:///home/src/wishenka/wishlists/store.py), and [`wishenka/wishlists/repository.py`](file:///home/src/wishenka/wishlists/repository.py):

- **Column**: `display_order INTEGER NOT NULL DEFAULT 0` on table `wl_items`.
- **Index**: `CREATE INDEX idx_wl_items_order ON wl_items(wishlist_id, display_order)` (a plain `CREATE INDEX` run once by the `add_item_order_index` revision).
- **Schema Migration**: The column and the index are created by the Alembic revisions `add_display_order` and `add_item_order_index` (see [migrations.md](migrations.md)). `WishlistStore.initialize()` brings the database to the Alembic head on startup; a legacy database that lacks them is stamped at the matching revision and upgraded without rewriting rows. The old runtime `ALTER TABLE` is removed.
- **Deterministic Ordering**: Repository selects sort by `ORDER BY display_order ASC, id ASC`.

#### Wish-scoped inventory transaction

Inventory changes for one wish share the SQLite file across service copies. The exclusion is a wish-scoped WAL write on the wishlist engine. Redis is not part of this path. `ItemConcurrencyCoordinator` keeps an in-process `asyncio.Lock` per item on the service instance that owns it. `execute_wish` builds a fresh `WishlistService` for the loaded wish, so that lock is not shared with another process or another request. The quantity rules still run inside the SQLite transaction.

[`_configure_immediate_transactions`](file:///home/src/wishenka/wishlists/store.py#L48-L68) attaches to `engine.sync_engine`:

- On `connect`, `isolation_level = None` so the sqlite3 driver does not emit its own `BEGIN`. The same connect sets `PRAGMA foreign_keys=ON` and `PRAGMA busy_timeout=5000`. `PRAGMA journal_mode=WAL` is persistent database state and is selected once by the migration startup, not by this hook (see [migrations.md](migrations.md)).
- On `begin`, the listener sets `PRAGMA busy_timeout=5000` and then emits `BEGIN IMMEDIATE`. The listener runs because code calls `Connection.begin()`.

[`_immediate`](file:///home/src/wishenka/wishlists/store.py#L1262-L1273) opens a connection, calls `await conn.begin()`, runs the work, and `COMMIT`s. Any `BaseException` rolls the transaction back when it is still open, then re-raises. A failed attempt leaves the wish at the last commit.

[`execute_wish`](file:///home/src/wishenka/wishlists/store.py#L942-L997) requires exactly one of `item_id` or `reservation_id`. Inside that transaction it:

1. Resolves `reservation_id` with `SELECT wish_item_id FROM wl_reservations WHERE id = :reservation_id` ([`_resolve_wish_item_id`](file:///home/src/wishenka/wishlists/store.py#L999-L1014)). A missing row raises `ReservationNotFoundError` before any write.
2. Loads the parent wishlist with its members, the one item, that item's reservations, and the `reservation` counter ([`_load_wish`](file:///home/src/wishenka/wishlists/store.py#L1016-L1166)). The wishlist carries `owner_id`, `is_collaborative`, and the member rows that `is_recipient`, `resolve_context`, and `submit_edit_item` read. Other wishes are not loaded.
3. Runs the domain operation on that partial service. The service has no store, so the method body runs in memory inside the open transaction.
4. Persists changed rows only ([`_persist_wish`](file:///home/src/wishenka/wishlists/store.py#L1168-L1219)): the item row when its state changed, reservations that are new or changed, and the reservation counter when it changed. It does not call `_write`. Unchanged rows, other wishes, members, favorites, and view history stay untouched.

The configured `WishlistService` sends these methods through `execute_wish` via `_transactional`: `create_reservation`, `update_wish_item`, and `record_item_fulfillment` (by `item_id`); `cancel_reservation`, `update_reservation_quantity`, `mark_reservation_purchased`, and `revert_reservation_to_active` (by `reservation_id`). Shared names in `_SHARED_REPOSITORY_METHODS` forward through `WishlistStore.run_repository`. `update_wishlist_settings`, `transfer_ownership`, and `is_favorite` still use the snapshot `execute`.

`SQLITE_BUSY` after `busy_timeout` is recognized on the driver error, its
`orig`, or its cause (`sqlite_errorcode` low byte `SQLITE_BUSY`, or the text
`database is locked` / `database is busy`).
[`_raise_for_storage_error`](file:///home/src/wishenka/wishlists/store.py#L167-L205)
logs `wishlist_inventory_busy` and raises `InventoryBusyError`. The default
text is `The wish was busy and the attempt changed nothing`. A non-busy
`SQLAlchemyError` logs `wishlist_inventory_rolled_back` at `ERROR` only when
the wish key is present (`item_id`, `reservation_id`, or `operation` on that
helper) and becomes `RuntimeError` (`Wishlist storage operation failed`).
[`WishlistStore.execute`](file:///home/src/wishenka/wishlists/store.py#L1221)
calls the helper with no `item_id`, `reservation_id`, or `operation`. That
branch logs `wishlist_store_error` at `ERROR`. A full-snapshot `execute`
omits the id and the operation. A `WishlistError` or `ValueError` from the
domain method is rolled back, logged as `wishlist_inventory_rolled_back` at
`WARNING`, and re-raised unchanged. `wishlist_inventory_committed` is written
only after `COMMIT`.

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
  - Upon item creation in [`quick_add_item`](file:///home/src/wishenka/web/routes/items_ui.py#L499) (`POST /web/wishlists/{wishlist_id}/items/quick`) or [`submit_new_item`](file:///home/src/wishenka/web/routes/items_ui.py#L734) (`POST /web/wishlists/{wishlist_id}/items/new`), `_render_created_item_response` returns `201 Created` containing the rendered [`partials/item_card.html`](file:///home/src/wishenka/web/templates/partials/item_card.html) alongside four OOB swap fragments:
    1. `<div id="quick-add-preview-target" hx-swap-oob="innerHTML"></div>` (clears preview card).
    2. `<input type="text" id="quick-add-input" ... value="" hx-swap-oob="true" />` (clears input value while keeping HTMX attributes).
    3. `<div id="empty-items-placeholder" hx-swap-oob="delete"></div>` (removes empty list banner).
    4. `<div id="item-modal-container" hx-swap-oob="innerHTML"></div>` (closes creation modal if open).
- **Detailed Creation & Edit BottomSheet Modal ([`partials/item_edit_modal.html`](file:///home/src/wishenka/web/templates/partials/item_edit_modal.html))**:
  - Served in creation mode (`is_edit=False`) by [`get_new_item_modal`](file:///home/src/wishenka/web/routes/items_ui.py#L638) (`GET /web/wishlists/{wishlist_id}/items/new`) and submitted to [`submit_new_item`](file:///home/src/wishenka/web/routes/items_ui.py#L734) (`POST /web/wishlists/{wishlist_id}/items/new`). On `400 Bad Request` validation errors (form parsing/empty title or domain `ValueError`), [`_render_item_modal_error`](file:///home/src/wishenka/web/routes/items_ui.py#L172) (`is_edit=False`) re-renders `partials/item_edit_modal.html` with `HX-Retarget: #item-modal-container` and `HX-Reswap: innerHTML`, preserving all user-submitted fields and collaborative recipient options/selection while displaying a localized `[role="alert"]` banner.
  - Served in edit mode (`is_edit=True`) by [`get_edit_item_modal`](file:///home/src/wishenka/web/routes/items_ui.py#L891) (`GET /web/wishlists/{wishlist_id}/items/{item_id}/edit`).
  - Sets the quantity input and stepper minimum to `max(1, received_quantity)` without
    rendering a reservation-based minimum or booking hint.
  - Enforces **HTTP 409 Error Recovery**: if [`submit_edit_item`](file:///home/src/wishenka/web/routes/items_ui.py#L543) (`POST /web/wishlists/{wishlist_id}/items/{item_id}/edit`) catches `CannotReduceQuantityBelowReservedError`, it re-renders `partials/item_edit_modal.html` with status `409 Conflict`, displaying a localized error alert while preserving all user-submitted form fields (`submitted_form`).
  - Enforces **HTTP 503 retry**: the same handler saves through `execute_wish`. `InventoryBusyError` re-renders that modal with status `503 Service Unavailable` and the sentence `The wish was busy, the edit was not saved, and it can be submitted again.` The modal stays open, the submitted fields stay filled, and the sentence names no gifter. A busy lower-quantity edit is this 503, not an unhandled 500. The log event is `ui_item_edit_busy` with `wishlist_id` and `item_id`.
  - Enforces **Surprise Invariant & XSS Safety**: never exposes `item.reservations` or gifter identities (`user_id`, `username`, `first_name`), and relies on Jinja2 auto-escaping across all templates (`partials/item_card.html`, `partials/item_edit_modal.html`, `partials/item_preview_card.html`).
  - Supports **Safe Archiving & Restoration**: [`archive_item_ui`](file:///home/src/wishenka/web/routes/items_ui.py#L717) (`POST /web/wishlists/{wishlist_id}/items/{item_id}/archive`) archives the item while keeping reservations and emits `hx-swap-oob="delete"` for `#item-card-{item_id}` plus `hx-swap-oob="innerHTML"` for `#item-modal-container`. [`restore_item_ui`](file:///home/src/wishenka/web/routes/items_ui.py#L776) (`POST /web/wishlists/{wishlist_id}/items/{item_id}/restore`) restores the item and returns the rendered `partials/item_card.html`.

### 11. VCR-Compatible Marketplace Web Cassette Testbench ([`wishenka.items.cassettes`](file:///home/src/wishenka/items/cassettes.py))

Located in [`wishenka/items/cassettes.py`](file:///home/src/wishenka/items/cassettes.py) with versioned reference YAML cassettes in [`tests/cassettes/marketplaces/`](file:///home/src/tests/cassettes/marketplaces) and regression coverage in [`tests/test_marketplace_cassettes.py`](file:///home/src/tests/test_marketplace_cassettes.py) (`WISHENKA-97`).

Provides an offline-first, VCR-compatible YAML HTTP recording, sanitization, and replay engine built on `httpx.AsyncBaseTransport` and `PyYAML` without external network access during regular test runs:

- **Execution Modes ([`CassetteMode`](file:///home/src/wishenka/items/cassettes.py#L88), [`resolve_cassette_mode`](file:///home/src/wishenka/items/cassettes.py#L96))**:
  - `CassetteMode.REPLAY` (`"replay"`, default): offline playback; a missing interaction logs
    `cassette_miss` and raises `CassetteMissError`. It does not seed the shared DNS cache. The
    CLI `--verify` uses a private fixture-only preview fetcher, so verification needs no DNS.
  - `CassetteMode.RECORD` (`"record"`): Replays existing interactions on hit; on miss, dispatches the request through `inner_transport` (defaulting to [`SSRFSafeTransport`](file:///home/src/wishenka/items/ssrf.py#L750-L867)), sanitizes the interaction, appends it to the cassette, and saves the YAML file.
  - `CassetteMode.REFRESH` (`"refresh"`): Always fetches fresh responses through `inner_transport`, sanitizes request and response data, replaces matching interactions in the cassette, and saves the YAML file.
  - Mode resolution checks the explicit `mode` parameter first and falls back to the `WISHENKA_CASSETTE_MODE` environment variable (defaulting to `"replay"`).
- **Data Models & VCR YAML Schema**:
  - [`CassetteRequest(method, uri, headers, body)`](file:///home/src/wishenka/items/cassettes.py#L175): Immutable dataclass (`frozen=True, slots=True`) representing a sanitized HTTP request.
  - [`CassetteResponse(status_code, reason_phrase, headers, body, http_version)`](file:///home/src/wishenka/items/cassettes.py#L209): Immutable dataclass storing decoded response body (`body.string` in YAML), status code/message, and sanitized headers.
  - [`CassetteInteraction(request, response, marketplace, scenario, recorded_at)`](file:///home/src/wishenka/items/cassettes.py#L261): Single request/response interaction pair.
  - [`Cassette(version=1, marketplace, scenario, interactions)`](file:///home/src/wishenka/items/cassettes.py#L332): Loads (`Cassette.load(path)`), saves (`cassette.save(path)`), matches (`cassette.find_interaction(method, uri)`), and updates (`cassette.add_interaction(interaction, replace=...)`) YAML files.
  - [`load_marketplace_cassette(marketplace, scenario, cassettes_dir=...)`](file:///home/src/wishenka/items/cassettes.py#L486): Loads `<marketplace>_<scenario>.yaml` from [`DEFAULT_CASSETTES_DIR`](file:///home/src/wishenka/items/cassettes.py#L29) (`tests/cassettes/marketplaces/`).
- **Mandatory Header, Cookie, and URI Sanitization**:
  - [`sanitize_headers(headers)`](file:///home/src/wishenka/items/cassettes.py#L116): Case-insensitively strips all headers in [`SENSITIVE_HEADER_NAMES`](file:///home/src/wishenka/items/cassettes.py#L35) (`authorization`, `proxy-authorization`, `cookie`, `set-cookie`, `set-cookie2`, `x-api-key`, `x-auth-token`, `x-csrf-token`, `x-xsrf-token`, `cf-connecting-ip`, `x-forwarded-for`, `x-real-ip`, `x-client-ip`, `x-device-id`, `x-session-id`) and any header name containing [`SENSITIVE_HEADER_SUBSTRINGS`](file:///home/src/wishenka/items/cassettes.py#L55) (`cookie`, `token`, `secret`, `auth`, `session`, `api-key`, `apikey`).
  - [`sanitize_uri(uri)`](file:///home/src/wishenka/items/cassettes.py#L142): Normalizes URLs via [`clean_url`](file:///home/src/wishenka/items/marketplaces.py#L29) (stripping `utm_*`, `from=share*`, `clid`, `targetUrl`, `promo`, etc.), removes `user:pass@` netloc credentials, and strips query parameters matching [`SENSITIVE_QUERY_KEYS`](file:///home/src/wishenka/items/cassettes.py#L65) (`token`, `access_token`, `refresh_token`, `id_token`, `api_key`, `apikey`, `session`, `session_id`, `sessionid`, `auth`, `auth_token`, `key`, `secret`, `password`, `passwd`, `signature`, `sig`) or containing sensitive substrings.
  - [`sanitize_interaction(interaction)`](file:///home/src/wishenka/items/cassettes.py#L300): Applied automatically on `Cassette` initialization, `add_interaction`, `from_dict`, and `to_dict`/`save` so secrets can never be written to disk.
- **Transport & Client Context Manager**:
  - `CassetteTransport` implements the async transport interface and matches requests by method
    and normalized URI. Recording and refresh use a separate direct path. Response body headers
    are normalized for replay; sensitive request and response fields are removed before saving.
  - `cassette_client(...)` remains a standalone cassette HTTP client; it is not an approved
    preview client. For preview integration, `cassette_replay_routes(cassette)` copies fixtures
    into an explicit non-network `PreviewTransportConfig`. Normal preview still validates DNS.
    Recording and refresh use a separate pinned direct path and reject custom recorder transports.
- **Reference Marketplace Cassette Catalog (`tests/cassettes/marketplaces/`)**:
  - Contains 10 sanitized reference YAML cassettes covering the top-5 Russian marketplaces across two scenarios (`product` and `antibot`):
    - **Ozon**: `ozon_product.yaml` (`200 OK` JSON-LD `Product` + OpenGraph), `ozon_antibot.yaml` (`403 Forbidden` Cloudflare / «Доступ ограничен»).
    - **Wildberries**: `wildberries_product.yaml` (`200 OK` JSON-LD `@graph` + `AggregateOffer`), `wildberries_antibot.yaml` (`403 Forbidden` Qrator / `qrator_jsid` / «Проверка браузера»).
    - **Yandex Market**: `yandex_market_product.yaml` (`200 OK` OpenGraph + JSON-LD), `yandex_market_antibot.yaml` (`200 OK` Yandex SmartCaptcha `<title>Почти готово...</title>` / `smartcaptcha`).
    - **Avito**: `avito_product.yaml` (`200 OK` Microdata + OpenGraph), `avito_antibot.yaml` (`200 OK` Avito IP firewall `<title>Доступ ограничен: проблема с IP</title>` / `firewall-container`).
    - **Megamarket**: `megamarket_product.yaml` (`200 OK` JSON-LD `@graph` + `AggregateOffer`), `megamarket_antibot.yaml` (`503 Service Unavailable` DDoS-Guard / «Проверка браузера»).
- **CLI Audit & Recording Utility (`python -m wishenka.items.cassettes`)**:
  - `--verify` (or `--mode replay`): Verifies all `*.yaml` cassettes in `--cassettes-dir` offline through `ItemPreviewService.fetch_preview`, asserting that `product` cassettes resolve with `is_fallback=False` and `antibot` cassettes degrade gracefully with `is_fallback=True`.
  - `--mode record|refresh --url <url> --output <path>` records or refreshes a cassette
    through the validated, pinned direct transport with automatic sanitization. Optional
    `--marketplace` and `--scenario` specify the fixture metadata.
  - `--mode record|refresh [--cassettes-dir <dir>]`: Batch-refreshes all existing YAML cassettes in the target directory.

---

## Domain Exceptions & Hierarchy

Located in [`wishenka/items/exceptions.py`](file:///home/src/wishenka/items/exceptions.py) and [`wishenka/wishlists/exceptions.py`](file:///home/src/wishenka/wishlists/exceptions.py).

```text
WishlistError
  ├── ItemError
  │     ├── InvalidItemDataError
  │     ├── CassetteError
  │     │     └── CassetteMissError
  │     └── ItemParsingError
  │           ├── ResponseBodyTooLargeError
  │           └── SSRFError
  │                 ├── SSRFBlockedError
  │                 └── InvalidUrlSchemeError
  ├── ItemNotFoundError
  ├── CannotReduceQuantityBelowReservedError
  ├── InventoryBusyError
  ├── WishlistNotFoundError
  ├── WishlistArchivedError
  ├── WishlistDeletedError
  ├── PermissionDeniedError
  └── WishRefusalError
        ├── QuantityInvalidError
        ├── QuantityAboveRemainingError
        ├── NothingRemainingError
        └── WishArchivedError
```

### Exception Reference

| Exception | Base Class | Key Attributes | HTTP Status | Trigger Condition |
| --- | --- | --- | :---: | --- |
| [`ItemError`](file:///home/src/wishenka/items/exceptions.py#L10) | `WishlistError` | None | `400` | Base exception for all item domain errors. |
| [`InvalidItemDataError`](file:///home/src/wishenka/items/exceptions.py#L14) | `ItemError` | None | `400` | Validation failures in item payloads (e.g. quantity $< 1$ or $> 1000$). |
| [`CassetteError`](file:///home/src/wishenka/items/exceptions.py#L71) | `ItemError` | None | N/A | Base exception for web cassette loading, structure, or mode errors; explicitly re-raised by `ItemPreviewService` and `UrlMetadataService`. |
| [`CassetteMissError`](file:///home/src/wishenka/items/exceptions.py#L75) | `CassetteError` | `method`, `uri`, `cassette_path` | N/A | Requested `(method, sanitized_uri)` interaction is missing from the loaded cassette in offline `CassetteMode.REPLAY`. |
| [`ItemParsingError`](file:///home/src/wishenka/items/exceptions.py#L18) | `ItemError` | None | `400` | Base exception for parsing, URL extraction, and network fetch limits. |
| [`SSRFError`](file:///home/src/wishenka/items/exceptions.py#L22) | `ItemParsingError` | None | `400` | Base exception for SSRF blocks and URL security violations. |
| [`SSRFBlockedError`](file:///home/src/wishenka/items/exceptions.py#L26) | `SSRFError` | `ip_address`, `host`, `reason` | `400` | Host or IP resolves to private, loopback, link-local, cloud metadata, reserved, or configured `ssrf_forbidden_cidrs` range (or triggers URL credentials / unsafe backend / UDS blocks). |
| [`InvalidUrlSchemeError`](file:///home/src/wishenka/items/exceptions.py#L43) | `SSRFError` | `scheme` | `400` | URL scheme is disallowed by the active `SSRFPolicy.allowed_schemes` (default `http` and `https`). |
| [`ResponseBodyTooLargeError`](file:///home/src/wishenka/items/exceptions.py#L56) | `ItemParsingError` | `content_length`, `max_allowed` | `400` | Response exceeds configured `ssrf_max_response_bytes` / `max_bytes` limit (default 2 MB / `2,097,152` bytes). |
| [`ItemNotFoundError`](file:///home/src/wishenka/wishlists/exceptions.py#L36) | `WishlistError` | None | `404` | Target `item_id` does not exist or does not belong to the specified wishlist. |
| [`CannotReduceQuantityBelowReservedError`](file:///home/src/wishenka/wishlists/exceptions.py#L44) | `WishlistError` | None | `409` | A schema-valid quantity is below `received_quantity`; the legacy exception name is retained. |
| [`InventoryBusyError`](file:///home/src/wishenka/wishlists/exceptions.py#L52) | `WishlistError` | None | `503` | `SQLITE_BUSY` after `busy_timeout`. The transaction rolled back and the wish is unchanged. The message names no gifter. |
| [`WishlistNotFoundError`](file:///home/src/wishenka/wishlists/exceptions.py#L10) | `WishlistError` | None | `404` | Parent wishlist ID does not exist. |
| [`WishlistArchivedError`](file:///home/src/wishenka/wishlists/exceptions.py#L18) | `WishlistError` | None | `409` | Attempting to mutate an item in an archived wishlist or edit an archived item. |
| [`WishlistDeletedError`](file:///home/src/wishenka/wishlists/exceptions.py#L22) | `WishlistError` | None | `404` | Parent wishlist is marked as deleted. |
| [`PermissionDeniedError`](file:///home/src/wishenka/wishlists/exceptions.py#L26) | `WishlistError` | None | `403` | Caller lacks `can_add_or_edit_item` privilege for the wishlist. |
| [`WishRefusalError`](file:///home/src/wishenka/wishlists/exceptions.py#L62) | `WishlistError` | `reason` | per subclass | Base of the closed set of receipt refusals; `reason` is the stable machine code. |
| [`QuantityInvalidError`](file:///home/src/wishenka/wishlists/exceptions.py#L68) | `WishRefusalError`, `ValueError` | `reason` | `400` | Received quantity is below one (receipt route code `quantity_invalid`). |
| [`QuantityAboveRemainingError`](file:///home/src/wishenka/wishlists/exceptions.py#L77) | `WishRefusalError`, `ValueError` | `reason`, `remaining_quantity` | `409` | Received quantity exceeds what remains to be received (`quantity_above_remaining`). |
| [`NothingRemainingError`](file:///home/src/wishenka/wishlists/exceptions.py#L89) | `WishRefusalError` | `reason`, `remaining_quantity` (always 0) | `409` | The wish is fully received, so nothing is left to receive or restore (`nothing_remaining`). |
| [`WishArchivedError`](file:///home/src/wishenka/wishlists/exceptions.py#L99) | `WishRefusalError` | `reason` | `409` | A receipt is recorded on an archived wish (`wish_archived`). |

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
| [`CassetteMode`](file:///home/src/wishenka/items/cassettes.py#L88-L93) | `wishenka.items.cassettes` | `StrEnum` for web cassette execution mode: `replay` (default), `record`, `refresh`. |
| [`CassetteRequest`](file:///home/src/wishenka/items/cassettes.py#L175-L205) | `wishenka.items.cassettes` | Frozen dataclass representing a sanitized HTTP request (`method`, `uri`, `headers`, `body`). |
| [`CassetteResponse`](file:///home/src/wishenka/items/cassettes.py#L209-L257) | `wishenka.items.cassettes` | Frozen dataclass representing a sanitized HTTP response (`status_code`, `reason_phrase`, `headers`, `body`, `http_version`). |
| [`CassetteInteraction`](file:///home/src/wishenka/items/cassettes.py#L261-L297) | `wishenka.items.cassettes` | Frozen dataclass pairing `CassetteRequest` and `CassetteResponse` with `marketplace`, `scenario`, and `recorded_at`. |
| [`Cassette`](file:///home/src/wishenka/items/cassettes.py#L332-L483) | `wishenka.items.cassettes` | In-memory VCR-compatible YAML cassette container with `load`, `save`, `find_interaction`, and `add_interaction`. |
| [`CassetteTransport`](file:///home/src/wishenka/items/cassettes.py#L498-L685) | `wishenka.items.cassettes` | `httpx.AsyncBaseTransport` implementing offline replay, fail-closed `CassetteMissError`, and sanitized recording/refresh. |
| [`CreateItemDTO`](file:///home/src/wishenka/items/schemas.py#L26-L49) | `wishenka.items.schemas` | Pydantic DTO for creating items: non-whitespace title, $1 \le \text{quantity} \le 1000$, optional `recipient_user_id` and `recipient_name`. |
| [`UpdateItemDTO`](file:///home/src/wishenka/items/schemas.py#L51-L74) | `wishenka.items.schemas` | Pydantic DTO for updating items: non-whitespace title, $1 \le \text{quantity} \le 1000$, optional recipient overrides. |
| [`ReorderItemsDTO`](file:///home/src/wishenka/items/schemas.py#L76-L82) | `wishenka.items.schemas` | Pydantic DTO for atomic reordering containing `item_ids: list[int]`. |
| [`WishItemRecipientViewDTO`](file:///home/src/wishenka/wishlists/schemas.py#L11-L37) | `wishenka.wishlists/schemas` | Surprise Invariant view for the recipient: omits all reservation status and gifter details. |
| [`WishItemGifterViewDTO`](file:///home/src/wishenka/wishlists/schemas.py#L39-L73) | `wishenka.wishlists/schemas` | View for gifters and non-recipient collaborators: includes `available_quantity`, `is_fully_reserved`, `my_reserved_quantity`, `my_reservation_id`, `my_latest_reservation_quantity`, and `my_occupying_reservation_count`. The wish card reads these fields. |

---

## Business Invariants & Operational Rules

### 1. Piece Accounting & Reduction Lock Invariant

- **Quantity Bounds**: $1 \le \text{quantity} \le 1000$. Enforced at schema level ([`CreateItemDTO`](file:///home/src/wishenka/items/schemas.py#L37), [`UpdateItemDTO`](file:///home/src/wishenka/items/schemas.py#L62)) and domain level.
- **Occupied units**: `reserved_quantity` sums reservation `quantity` in `ACTIVE` or `PURCHASED`.
- **Free remainder for a promise**:
  $$\text{available\_quantity} = \max(0, \text{quantity} - \text{received\_quantity} - \text{reserved\_quantity})$$
  A new promise or a larger one that would make this remainder negative raises `InsufficientQuantityError`. The earlier promise stays as it was.
- **Receipt cap**: `record_item_fulfillment` adds received units up to requested minus units already received. It does not close the promise and is not limited by occupied units. After a successful receipt, occupied plus received may exceed the requested quantity. A later promise still uses the free remainder.

- **Receipt guards and record**: `record_item_fulfillment` also refuses a non-member
  (`PermissionDeniedError`), a deleted list (`WishlistDeletedError`), an archived list
  (`WishlistArchivedError`), an archived wish (`WishArchivedError`), a quantity below one
  (`QuantityInvalidError`) and a wish with nothing remaining (`NothingRemainingError`), and writes
  one dated row in `wl_receipts` in the same transaction. The author check is now plain list
  membership (owner, admin or member). The HTTP route is
  `POST /api/wishlists/{wishlist_id}/items/{item_id}/receipts`. See
  [gift-receipt.md](gift-receipt.md). The receipt dialog, the owner card and the «Подаренные»
  section (WISHENKA-24) are Mini App routes that call this service method; see
  [gift-receipt.md](gift-receipt.md#mini-app-ui-wishenka-24).
- **Quantity floor**: The editor may set quantity to `max(1, received_quantity)` or higher.
  The REST API rejects values outside 1–1000 with HTTP 422 during DTO validation. For a
  schema-valid value below `received_quantity`, the service raises
  `CannotReduceQuantityBelowReservedError`, the API returns HTTP 409, and the wish-scoped
  transaction rolls back. Open promises do not affect this floor.
- **Busy lock**: these checks run inside the wish-scoped `BEGIN IMMEDIATE` transaction. If the write lock is still held when `busy_timeout` (5000 ms) expires, the store raises `InventoryBusyError`, rolls back, and changes nothing. Item `execute` and the edit modal answer that with HTTP 503 and name no gifter.

### 2. Reordering Protocol & 1:1 Active Permutation Integrity

- **Contiguous Zero-Indexed Ordering**: Item positions in a wishlist are defined by `display_order` ($0, 1, 2, \dots$).
- **Auto-Increment on Creation**: Newly created items receive `display_order = max(active_display_orders, default=-1) + 1`.
- **1:1 Active Permutation**: When invoking `PUT /api/wishlists/{wishlist_id}/items/reorder`:
  1. The payload `item_ids` must contain no duplicates (`len(item_ids) == len(set(item_ids))`).
  2. The set of `item_ids` must match **exactly** the set of all active items belonging to that wishlist. Active means `WishItem.is_active`: not archived and not fully received:
     $$\text{set}(item\_ids) == \{i.id \mid i \in \text{items}, \neg i.is\_archived \land i.received < i.quantity\}$$
  3. If any active item is missing, or an extra/archived item ID is provided, the operation raises `ValueError` (HTTP 400 Bad Request) and logs `item_reorder_invalid`.
  4. On success, items are contiguously re-indexed to $0, 1, \dots, N-1$ matching the list order.

### 3. Safe Archiving & Restore Semantics

- **Non-Destructive Soft-Delete**: Archiving an item (`POST /api/wishlists/{wishlist_id}/items/{item_id}/archive`) marks `is_archived = True`.
- **Reservation Preservation**: Active and purchased reservations on the archived item remain intact in the database. Gifters who committed to a gift do not lose their reservation history or booking records.
- **Booking & Mutation Freeze**: Archived items cannot be booked or edited; attempting to modify an archived item raises [`WishlistArchivedError`](file:///home/src/wishenka/wishlists/exceptions.py#L18) (HTTP 409 Conflict).
- **Listing Exclusion**: Archived items are hidden from default item listings (`include_archived=False`) and excluded from active reordering permutations. Fully received wishes are hidden from both modes (`include_archived=True` returns every wish that is not fully received).
- **Tail Restoration**: Restoring an item (`POST /api/wishlists/{wishlist_id}/items/{item_id}/restore`) unsets `is_archived = False` and sets its `display_order` to `max(active_orders, default=-1) + 1`, appending it cleanly to the end of the active list.

- **Received units**: the active-list predicate is `WishItem.is_active` (not archived and
  `received_quantity < quantity`), shared by the list view, reorder, restore tail order and the
  public projection. Archiving a partly received wish moves only its unreceived part to the
  archive (`is_in_archive`: archived and not fully received); the received part stays in the
  gifted read (`GET /api/wishlists/{wishlist_id}/gifted`). `archive_wish_item` of a fully
  received wish and `restore_wish_item` with nothing remaining raise `NothingRemainingError`
  (HTTP 409 on the archive and restore routes). Partly received wishes log INFO
  `wish_archived_partial` or `wish_restored_partial`; the refusal logs WARNING
  `wish_archive_refused`. Legacy archived rows that were fully received are cleared by the
  migration `add_gift_receipts`. In the Mini App (`items_ui.py`), a stale archive or restore of a
  fully received wish is a 409 with `X-Receipt-Refusal: nothing_remaining` and an out-of-band
  body (`_nothing_remaining_response`); the archive confirmation dialog gets a note about the
  received part (`has_received`), the archive section shows «Осталось N», and the stale reorder
  400 carries `X-Reorder-Refusal: stale_order`. See [gift-receipt.md](gift-receipt.md).

### 4. Collaborative Wishlist Targeting & Surprise Invariant

- **Target Recipients**: In collaborative wishlists, an item can be designated for a specific recipient via `recipient_user_id` or descriptive `recipient_name`.
- **Membership Check**: `recipient_user_id` must belong to the wishlist's active members (`owner_id` or enrolled members). Non-member recipient IDs are rejected with `ValueError` (HTTP 400 Bad Request).
- **Dual-Role Projections ([`project_wish_item`](file:///home/src/wishenka/wishlists/service.py#L121))**:
  - **Recipient View ([`WishItemRecipientViewDTO`](file:///home/src/wishenka/wishlists/schemas.py#L11))**: Returned when [`WishlistAccessPolicy.is_recipient`](file:///home/src/wishenka/wishlists/policy.py#L115) is true. On a personal list the owner is the recipient of every wish, including a display-name-only wish. On a collaborative list the caller is the recipient only when `recipient_user_id` equals `telegram_id`. A display name is never compared to a user. The DTO omits `available_quantity`, `is_fully_reserved`, and all reservation details, and the wish card omits `.item-giver`.
  - **Gifter View ([`WishItemGifterViewDTO`](file:///home/src/wishenka/wishlists/schemas.py#L39))**: Returned to every other caller. Displays `available_quantity`, whether the item is fully reserved, and the caller's occupying promises (`is_reserved_by_me`, `my_reserved_quantity`, `my_reservation_status`, `my_reservation_id`, `my_latest_reservation_quantity`, `my_occupying_reservation_count`). The card summary uses the combined quantity for `Забронировано вами (N)` and the latest row for `Изменить`, `Куплено`, and `Вернуть в бронь`. See [reservations.md](reservations.md#6-wish-card-giver-controls).

---

## REST API Reference

All endpoints are mounted at `/api/wishlists/{wishlist_id}/items`.

| Method | Endpoint Path | Auth Required | Request Body | Response DTO | Status Codes | Description |
| :---: | :--- | :---: | :--- | :--- | :---: | :--- |
| `POST` | `/api/wishlists/{wishlist_id}/items` | **Yes** | [`CreateItemDTO`](file:///home/src/wishenka/items/schemas.py#L26) | Recipient or Gifter DTO | `201`, `400`, `403`, `404`, `409` | Create new wish item with auto-incremented `display_order`. |
| `GET` | `/api/wishlists/{wishlist_id}/items` | Optional | None | `list[Recipient or Gifter DTO]` | `200`, `404` | List items sorted by `display_order ASC`. Query param `include_archived=bool`. |
| `PUT` | `/api/wishlists/{wishlist_id}/items/reorder` | **Yes** | [`ReorderItemsDTO`](file:///home/src/wishenka/items/schemas.py#L76) | `list[Recipient or Gifter DTO]` | `200`, `400`, `403`, `404`, `409` | Atomically reorder active items enforcing 1:1 permutation integrity. |
| `GET` | `/api/wishlists/{wishlist_id}/items/{item_id}` | Optional | None | Recipient or Gifter DTO | `200`, `404` | Retrieve single item projected for the caller. |
| `PATCH` | `/api/wishlists/{wishlist_id}/items/{item_id}` | **Yes** | [`UpdateItemDTO`](file:///home/src/wishenka/items/schemas.py#L51) | Recipient or Gifter DTO | `200`, `400`, `403`, `404`, `409`, `503` | Update item properties through `execute_wish`. Reduction lock is 409. A busy lock is 503 and names no gifter. |
| `POST` | `/api/wishlists/{wishlist_id}/items/{item_id}/archive` | **Yes** | None | Recipient or Gifter DTO | `200`, `403`, `404`, `409` | Safely archive item, preserving reservations and blocking new bookings. |
| `POST` | `/api/wishlists/{wishlist_id}/items/{item_id}/restore` | **Yes** | None | Recipient or Gifter DTO | `200`, `403`, `404`, `409` | Restore archived item, placing it at the end of the active list. |

---

## HTMX Web UI Endpoints Reference (`/web/wishlists/{wishlist_id}`)

All HTMX UI endpoints are defined in [`wishenka/web/routes/items_ui.py`](file:///home/src/wishenka/web/routes/items_ui.py) and mounted at `/web/wishlists/{wishlist_id}`.

| Method | Endpoint Path | Handler | Auth | Request Payload | HTML Response / OOB Swaps | Status Codes | Description |
| :---: | :--- | :--- | :---: | :--- | :--- | :---: | :--- |
| `GET` | `/web/wishlists/{wishlist_id}` | [`view_wishlist_detail`](file:///home/src/wishenka/web/routes/items_ui.py#L108) | Optional | None | [`wishlist_detail.html`](file:///home/src/wishenka/web/templates/wishlist_detail.html) | `200`, `404` | Renders main TMA wishlist page; shows `#quick-add-bar` and edit buttons only when `can_edit_wishlist=True`. |
| `POST` | `/web/wishlists/{wishlist_id}/items/preview` | [`preview_item_input`](file:///home/src/wishenka/web/routes/items_ui.py#L143) | **Yes** | Form: `raw_input` | [`partials/item_preview_card.html`](file:///home/src/wishenka/web/templates/partials/item_preview_card.html) or empty string (`PLAIN_TEXT`) | `200`, `404`, `409` | Classifies universal input; renders live URL preview card or graceful fallback (`is_fallback=True`). |
| `POST` | `/web/wishlists/{wishlist_id}/items/quick` | [`quick_add_item`](file:///home/src/wishenka/web/routes/items_ui.py#L499) | **Yes** | Form: `raw_input`, `title`, `link`, `price`, `currency`, `image_url`, `store_name`, `description`, `quantity`, `priority`, `category`, `recipient_user_id`, `recipient_name` | [`partials/item_card.html`](file:///home/src/wishenka/web/templates/partials/item_card.html) + OOB resets (`#quick-add-preview-target`, `#quick-add-input`, `#empty-items-placeholder`, `#item-modal-container`) | `201`, `400`, `404`, `409` | Quick-adds wish item from Quick Add Bar and resets UI via `hx-swap-oob`. |
| `GET` | `/web/wishlists/{wishlist_id}/items/new` | [`get_new_item_modal`](file:///home/src/wishenka/web/routes/items_ui.py#L638) | **Yes** | Query: `raw_input`, `title`, `link`, `price`, `currency`, `image_url`, `description`, `quantity`, `priority`, `category` | [`partials/item_edit_modal.html`](file:///home/src/wishenka/web/templates/partials/item_edit_modal.html) (`is_edit=False`, `min_quantity=1`) | `200`, `404`, `409` | Opens detailed item creation BottomSheet modal prepopulated from Quick Add or preview card. |
| `POST` | `/web/wishlists/{wishlist_id}/items/new` | [`submit_new_item`](file:///home/src/wishenka/web/routes/items_ui.py#L734) | **Yes** | Form: `title`, `link`, `price`, `currency`, `quantity`, `description`, `image_url`, `priority`, `category`, `recipient_user_id`, `recipient_name` | [`partials/item_card.html`](file:///home/src/wishenka/web/templates/partials/item_card.html) + OOB resets (or `partials/item_edit_modal.html` with `HX-Retarget: #item-modal-container` + `HX-Reswap: innerHTML` via `_render_item_modal_error` on `400`; OOB `#list-notice` on `404`/`409` archived) | `201`, `400`, `404`, `409` | Creates wish item from detailed creation modal; preserves form state and collaborative recipient options/selection on `400`. |
| `GET` | `/web/wishlists/{wishlist_id}/items/{item_id}/edit` | [`get_edit_item_modal`](file:///home/src/wishenka/web/routes/items_ui.py#L438) | **Yes** | None | [`partials/item_edit_modal.html`](file:///home/src/wishenka/web/templates/partials/item_edit_modal.html) (`is_edit=True`, `min_quantity=max(1, received_quantity)`) | `200`, `404`, `409` | Opens detailed edit modal enforcing Reduction Lock and Surprise Invariant. |
| `POST` | `/web/wishlists/{wishlist_id}/items/{item_id}/edit` | [`submit_edit_item`](file:///home/src/wishenka/web/routes/items_ui.py#L543) | **Yes** | Form: `title`, `link`, `price`, `currency`, `quantity`, `description`, `image_url`, `priority`, `category`, `recipient_user_id`, `recipient_name` | [`partials/item_card.html`](file:///home/src/wishenka/web/templates/partials/item_card.html) + OOB close `#item-modal-container` (or `partials/item_edit_modal.html` with `HX-Retarget: #item-modal-container` + `HX-Reswap: innerHTML` on 400/409/503; OOB `#list-notice` on 404/409 archived) | `200`, `400`, `404`, `409`, `503` | Saves through `execute_wish`. Quantity below received units returns 409. A busy lock returns 503, keeps the modal open, and names no gifter. |
| `POST` | `/web/wishlists/{wishlist_id}/items/{item_id}/archive` | [`archive_item_ui`](file:///home/src/wishenka/web/routes/items_ui.py#L717) | **Yes** | None | OOB delete `#item-card-{item_id}` + OOB close `#item-modal-container` (or OOB `#list-notice` + modal close on 404/409) | `200`, `404`, `409` | Safely archives item while preserving gifter reservations and removes card from DOM. |
| `POST` | `/web/wishlists/{wishlist_id}/items/{item_id}/restore` | [`restore_item_ui`](file:///home/src/wishenka/web/routes/items_ui.py#L776) | **Yes** | None | [`partials/item_card.html`](file:///home/src/wishenka/web/templates/partials/item_card.html) | `200`, `404`, `409` | Restores archived item to the tail of the active list and renders updated card partial. |

### WISHENKA-15 additions: ordering, archive confirmation

| Method | Endpoint Path | Handler | Request | Response | Description |
| :---: | :--- | :--- | :--- | :--- | :--- |
| `POST` | `/web/wishlists/{wishlist_id}/items/reorder` | `reorder_items_ui` | Form: `item_ids` (repeated) | `partials/items_list.html` | Persists full manual order; `400` if not an exact permutation of active items. |
| `POST` | `/web/wishlists/{wishlist_id}/items/{item_id}/move?direction=up\|down` | `move_item_ui` | Query: `direction` | `partials/items_list.html` | Swaps item with its neighbour; no-op at the list edges. |
| `GET` | `/web/wishlists/{wishlist_id}/items/{item_id}/archive-confirm` | `archive_confirm_ui` | None | `partials/item_archive_modal.html` | Confirmation modal; warns about active reservations when `warn_on_delete_reserved` is set. |

Notes: `Wishlist.warn_on_delete_reserved` (bool, default `True`, `wl_lists.warn_on_delete_reserved`)
is persisted by the store; the column is created by the Alembic revision `add_warn_on_delete_reserved` (see [migrations.md](migrations.md)). Archive and
restore responses include an OOB swap of `#archived-items-section`. Events: `ui_items_reordered`,
`ui_item_moved`, `ui_items_reorder_rejected`, `ui_item_archive_confirm_opened`, `ui_item_archived`,
`ui_item_restored`. See [miniapp.md](miniapp.md) section 9.8 for the UI behaviour.

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

Instantiate [`ItemPreviewService(...)`](file:///home/src/wishenka/items/service.py#L70-L79) (optionally passing `settings=Settings(...)` or `policy=SSRFPolicy(...)` at initialization rather than on `fetch_preview`/`.preview(...)`), then call [`ItemPreviewService.fetch_preview`](file:///home/src/wishenka/items/service.py#L113-L500) (or alias [`.preview(...)`](file:///home/src/wishenka/items/service.py#L103-L111)):

```python
from wishenka.config import Settings
from wishenka.items.service import ItemPreviewService

service = ItemPreviewService(settings=Settings())

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

Use [`HtmlMetadataExtractor.extract`](file:///home/src/wishenka/items/parser.py#L423-L630):

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

Use [`UrlMetadataService`](file:///home/src/wishenka/items/fetcher.py#L279-L518) and [`validate_url`](file:///home/src/wishenka/items/fetcher.py#L69-L98) for lower-level safe fetching:

```python
from wishenka.config import Settings
from wishenka.items.exceptions import ResponseBodyTooLargeError, SSRFBlockedError
from wishenka.items.fetcher import UrlMetadataService, validate_url

settings = Settings(ssrf_max_response_bytes=512 * 1024, ssrf_allowed_schemes=("https",))
fetcher = UrlMetadataService(settings=settings)
await validate_url("https://example.com/product/123", settings=settings)

# Safe high-level extraction (never raises, returns ExtractedMetadata)
metadata = await fetcher.fetch_and_extract("https://example.com/product/123")
print(metadata.title, metadata.price, metadata.store_name)

# Low-level fetching with explicit security exception handling
try:
    html_text, effective_url = await fetcher._fetch_html("https://127.0.0.1:8080/admin")
except SSRFBlockedError as exc:
    print(f"Blocked SSRF target: {exc.host} ({exc.ip_address}) - reason: {exc.reason}")
except ResponseBodyTooLargeError as exc:
    print(f"Payload exceeded {exc.max_allowed} bytes (actual: {exc.content_length})")
```

### 6. Direct IP, Hostname Validation, Policy Resolution, and DNS Cache Management

Use [`SSRFPolicy`](file:///home/src/wishenka/items/ssrf.py#L45-L72), [`get_default_ssrf_policy`](file:///home/src/wishenka/items/ssrf.py#L182-L197), [`resolve_ssrf_policy`](file:///home/src/wishenka/items/ssrf.py#L213-L228), [`redact_url_credentials`](file:///home/src/wishenka/items/ssrf.py#L107-L115), [`is_ip_safe`](file:///home/src/wishenka/items/ssrf.py#L270-L282), [`resolve_and_validate_host`](file:///home/src/wishenka/items/ssrf.py#L473-L614), [`DNSCache`](file:///home/src/wishenka/items/ssrf.py#L298-L361), and [`clear_dns_cache`](file:///home/src/wishenka/items/ssrf.py#L371-L373):

```python
import ipaddress
from wishenka.config import Settings
from wishenka.items.exceptions import SSRFBlockedError
from wishenka.items.ssrf import (
    DEFAULT_DNS_CACHE_CAPACITY,
    DEFAULT_DNS_CACHE_TTL_SECONDS,
    DNSCache,
    SSRFPolicy,
    clear_dns_cache,
    get_default_ssrf_policy,
    is_ip_safe,
    redact_url_credentials,
    resolve_and_validate_host,
    resolve_ssrf_policy,
)

# Policy resolution & credential redaction
default_policy = get_default_ssrf_policy()
strict_policy = resolve_ssrf_policy(
    settings=Settings(ssrf_forbidden_cidrs=("93.184.216.0/24",))
)
assert redact_url_credentials("https://user:secret@example.com/item") == "https://example.com/item"

# Direct IP checks (ambient default policy + optional custom forbidden_networks)
assert is_ip_safe("93.184.216.34") is True  # Public IP (example.com)
assert is_ip_safe("93.184.216.34", forbidden_networks=strict_policy.forbidden_networks) is False
assert is_ip_safe("127.0.0.1", forbidden_networks=()) is False  # Baseline loopback always blocked
assert is_ip_safe("10.0.0.1") is False  # RFC 1918 Private
assert is_ip_safe("169.254.169.254") is False  # Cloud metadata / Link-local
assert is_ip_safe("100.64.0.1") is False  # CGNAT
assert is_ip_safe("::ffff:127.0.0.1") is False  # IPv6-mapped IPv4 loopback

# Asynchronous DNS resolution check (caches validated public IPs for 60s TTL,
# revalidates cached hits against active forbidden_networks, and isolates
# single-flight coalescing per (host, port, active_networks))
resolved_ips = await resolve_and_validate_host("example.com", port=443)
assert len(resolved_ips) > 0

# Clear the process-local DNS cache when needed (e.g. lifecycle resets or isolated tests)
clear_dns_cache()

# Standalone DNSCache instance with custom capacity and TTL
custom_cache = DNSCache(
    capacity=DEFAULT_DNS_CACHE_CAPACITY,
    ttl=DEFAULT_DNS_CACHE_TTL_SECONDS,
)
custom_cache.put("Shop.Example.COM.", 443, ["93.184.216.34"])
assert custom_cache.get("shop.example.com", 443) == ["93.184.216.34"]

try:
    await resolve_and_validate_host("localhost", port=80)
except SSRFBlockedError as exc:
    print(f"Hostname blocked: {exc.host} resolves to {exc.ip_address}")
```

### 7. Managing Wish Items and Piece Accounting via Domain Service

Shared wish methods (`create_wishlist`, `add_wish_item`, `reorder_wish_items`,
`archive_wish_item`, `restore_wish_item`) run on `RepoWishlistOps` inside
`WishlistStore.run_repository`. On `WishlistService.in_memory()` those names
log `wishlist_repository_path_required` and raise `WishlistNotFoundError`.
Reservation, quantity, and receipt methods still run their bodies when the
service has no store, and a store-backed service sends them through
`execute_wish`. See [Shared wishlist rule set](wishlists.md#shared-wishlist-rule-set).

The sample below uses a store-backed service for reservation, quantity, and
receipt calls, which go through `execute_wish`. It creates, reorders, archives,
and restores wishes with `RepoWishlistOps` inside `run_repository`. Each shared
call returns the object from that transaction. Piece checks that follow a wish
mutation read the reservation returned by `execute_wish`, or the aggregate
loaded by a later repository call.

```python
from wishenka.auth.models import AuthenticatedUser
from wishenka.items.models import ItemPriority
from wishenka.wishlists.exceptions import (
    CannotReduceQuantityBelowReservedError,
    WishlistArchivedError,
)
from wishenka.wishlists.repo_ops import RepoWishlistOps
from wishenka.wishlists.service import WishlistService, project_wish_item
from wishenka.wishlists.store import WishlistStore

store = WishlistStore("sqlite+aiosqlite:///:memory:")
await store.initialize()
# Reservation, quantity, and receipt methods on this service use execute_wish.
service = WishlistService(store)
owner = AuthenticatedUser(telegram_id=101, first_name="Alice", username="alice")
gifter = AuthenticatedUser(telegram_id=202, first_name="Bob", username="bob")

# 1. Create a wishlist and an item with piece quantity = 5
async def seed(repo):
    ops = RepoWishlistOps(repo)
    wishlist = await ops.create_wishlist(owner_id=owner.telegram_id, title="Birthday Wishlist")
    item1 = await ops.add_wish_item(
        actor=owner,
        wishlist_id=wishlist.id,
        title="Board Game Sets",
        quantity=5,
        price=2500,
        priority=ItemPriority.HIGH,
    )
    item2 = await ops.add_wish_item(
        actor=owner,
        wishlist_id=wishlist.id,
        title="Wireless Headphones",
        quantity=1,
        price=12000,
    )
    return wishlist, item1, item2

wishlist, item1, item2 = await store.run_repository(seed)
assert item1.display_order == 0
assert item1.desired_quantity == 5
assert item1.available_quantity == 5
assert item2.display_order == 1

# 2. Gifter reserves 2 units of item1 (wish transaction, not the repository path)
reservation = await service.create_reservation(item_id=item1.id, user=gifter, quantity=2)
assert reservation.wish_item.reserved_quantity == 2
assert reservation.wish_item.available_quantity == 3

# 3. Open promises do not set the minimum: reducing to 1 is allowed and over-books the item.
reduced = await service.update_wish_item(item_id=item1.id, actor=owner, quantity=1)
assert reduced.quantity == 1
assert reduced.reserved_quantity == 2  # The open promise remains intact.

# Restore quantity for the following examples.
restored_qty = await service.update_wish_item(item_id=item1.id, actor=owner, quantity=3)
assert restored_qty.available_quantity == 1

# Received units do set the minimum, even though the exception retains its legacy name.
await service.update_wish_item(item_id=item2.id, actor=owner, quantity=3)
await service.record_item_fulfillment(item_id=item2.id, actor=owner, received_quantity=2)
try:
    await service.update_wish_item(item_id=item2.id, actor=owner, quantity=1)
except CannotReduceQuantityBelowReservedError as exc:
    print(f"Reduction blocked: {exc}")

# 4. Atomic Reordering: Swap item2 and item1
async def reorder(repo):
    return await RepoWishlistOps(repo).reorder_wish_items(
        wishlist_id=wishlist.id,
        actor=owner,
        item_ids=[item2.id, item1.id],
    )

reordered = await store.run_repository(reorder)
assert reordered[0].id == item2.id
assert reordered[0].display_order == 0
assert reordered[1].id == item1.id
assert reordered[1].display_order == 1

# 5. Safe Archiving: Soft-deletes item1 while preserving the reservation
async def archive(repo):
    return await RepoWishlistOps(repo).archive_wish_item(
        wishlist_id=wishlist.id,
        item_id=item1.id,
        actor=owner,
    )

archived_view = await store.run_repository(archive)
assert archived_view.is_archived is True

async def load(repo):
    return await RepoWishlistOps(repo).get_wishlist_by_id(wishlist.id)

loaded = await store.run_repository(load)
stored_item1 = next(it for it in loaded.items if it.id == item1.id)
# Reservations remain safely intact:
assert len([r for r in stored_item1.reservations if r.status.value == "active"]) == 1

# Editing archived item is rejected (execute_wish)
try:
    await service.update_wish_item(item_id=item1.id, actor=owner, title="New Title")
except WishlistArchivedError:
    print("Archived item cannot be modified")

# 6. Restoration: Unarchives and appends item1 to the end of the active list
async def restore(repo):
    return await RepoWishlistOps(repo).restore_wish_item(
        wishlist_id=wishlist.id,
        item_id=item1.id,
        actor=owner,
    )

restored_view = await store.run_repository(restore)
assert restored_view.is_archived is False
assert restored_view.display_order == 1  # item2 is 0, so restored item takes 1

# 7. Surprise Invariant Projections
loaded = await store.run_repository(load)
stored_item1 = next(it for it in loaded.items if it.id == item1.id)
recipient_view = project_wish_item(stored_item1, current_user=owner)
assert recipient_view.is_recipient is True
assert not hasattr(recipient_view, "available_quantity")  # Zero reservation leakage

gifter_view = project_wish_item(stored_item1, current_user=gifter)
assert gifter_view.is_recipient is False
assert gifter_view.available_quantity == 1
assert gifter_view.is_reserved_by_me is True
assert gifter_view.my_reserved_quantity == 2
await store.dispose()
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

### 9. Offline Replay, Recording, and CLI Audit with Marketplace Web Cassettes

The preview service accepts explicitly approved routes, not an injected HTTPX client. A direct
route is owned by the caller; close its transport after all previews complete:

```python
from wishenka.items.fetcher import PreviewTransportConfig, safe_direct_route
from wishenka.items.service import ItemPreviewService

route = safe_direct_route()
routes = PreviewTransportConfig(default=route, mounts={})
try:
    preview = await ItemPreviewService(routes=routes).fetch_preview("https://example.com/item")
finally:
    await route.transport.aclose()
```

For fixture-backed preview integration, load a cassette and supply its replay routes:

```python
from wishenka.items.cassettes import cassette_replay_routes, load_marketplace_cassette
from wishenka.items.service import ItemPreviewService

cassette = load_marketplace_cassette("ozon", "product")
routes = cassette_replay_routes(cassette)
target = cassette.interactions[0].request.uri
preview = await ItemPreviewService(routes=routes).fetch_preview(target)
```

The normal preview path validates DNS even for replay routes. Use the CLI `--verify` for fully
offline verification: its private fixture-only fetcher runs the preview and recorded redirect
chain without network or global DNS-cache changes. Missing interactions raise `CassetteMissError`.

CLI commands for offline cassette verification and controlled recording/refresh:

```bash
# Verify all 10 reference marketplace cassettes offline (product + antibot for top-5 stores)
python -m wishenka.items.cassettes --verify

# Record or refresh a single marketplace cassette with automatic header/cookie/URI sanitization
python -m wishenka.items.cassettes \
  --mode refresh \
  --url "https://ozon.ru/product/besprovodnye-naushniki-sony-wh-1000xm5-123456789/" \
  --output tests/cassettes/marketplaces/ozon_product.yaml \
  --marketplace ozon \
  --scenario product

# Refresh all existing YAML cassettes in tests/cassettes/marketplaces/
python -m wishenka.items.cassettes --mode refresh
```

---

## Configuration & Security Constants

### Wishlist inventory lock

Set on the wishlist engine in [`_configure_immediate_transactions`](file:///home/src/wishenka/wishlists/store.py#L48-L68). There is no separate environment variable and no Redis client for this lock.

| Setting | Value | Where |
| --- | --- | --- |
| `PRAGMA journal_mode` | `WAL` | migration startup (`upgrade_to_head_sync`), once per database file; not set by `connect` |
| `PRAGMA foreign_keys` | `ON` | `connect` |
| `PRAGMA busy_timeout` | `5000` (milliseconds) | `connect`, and again in the `begin` listener before `BEGIN IMMEDIATE` |
| `isolation_level` | `None` | `connect`, so sqlite3 does not emit its own `BEGIN` |

### Network & Security Settings

Configurable SSRF defaults and validation live in [`wishenka/config.py`](file:///home/src/wishenka/config.py) (`Settings`), with policy enforcement and network constants in [`wishenka/items/ssrf.py`](file:///home/src/wishenka/items/ssrf.py), [`wishenka/items/fetcher.py`](file:///home/src/wishenka/items/fetcher.py), [`wishenka/items/marketplaces.py`](file:///home/src/wishenka/items/marketplaces.py), [`wishenka/items/service.py`](file:///home/src/wishenka/items/service.py), [`wishenka/items/cassettes.py`](file:///home/src/wishenka/items/cassettes.py), [`wishenka/web/app.py`](file:///home/src/wishenka/web/app.py), [`wishenka/web/routes/items_ui.py`](file:///home/src/wishenka/web/routes/items_ui.py), and [`wishenka/bot/__main__.py`](file:///home/src/wishenka/bot/__main__.py):

- **Environment Variable & `.env` Parsing (`SettingsConfigDict(env_prefix="WISHENKA_", env_file=".env", extra="ignore")`)**:
  - `ssrf_max_response_bytes` (`WISHENKA_SSRF_MAX_RESPONSE_BYTES`): `int = Field(default=DEFAULT_SSRF_MAX_RESPONSE_BYTES, ge=1)`. Pre-validator `_validate_ssrf_max_response_bytes` rejects `bool` and `float` before Pydantic `int` parsing, failing fast with `pydantic.ValidationError` on `0`, negative values, blanks, or non-integer strings.
  - `ssrf_allowed_schemes` (`WISHENKA_SSRF_ALLOWED_SCHEMES`): `Annotated[tuple[str, ...], NoDecode] = DEFAULT_SSRF_ALLOWED_SCHEMES`. Suppressing `pydantic-settings` auto-JSON decoding with `NoDecode` allows [`_parse_env_string_tuple`](file:///home/src/wishenka/config.py#L38-L65) to accept **both** JSON arrays (`'["https"]'`) and comma-separated strings (`'https'`, `'http, https'`), as well as Python string iterables. Validator [`_validate_ssrf_allowed_schemes`](file:///home/src/wishenka/config.py#L143-L163) rejects blank strings, empty comma segments (e.g. `"http, "`), internal whitespace, `"/"`, `":"`, non-strings, empty sequences (`()` / `'[]'`), and schemes outside `SUPPORTED_SSRF_SCHEMES = frozenset({"http", "https"})`, normalizing to lowercase and deduplicating in order.
  - `ssrf_forbidden_cidrs` (`WISHENKA_SSRF_FORBIDDEN_CIDRS`): `Annotated[tuple[str, ...], NoDecode] = DEFAULT_SSRF_FORBIDDEN_CIDRS`. Accepts **both** JSON arrays (`'["93.184.216.0/24"]'`) and comma-separated strings (`'93.184.216.0/24, 2001:db8::/32'`), plus Python string iterables. Validator [`_validate_ssrf_forbidden_cidrs`](file:///home/src/wishenka/config.py#L165-L183) rejects blank strings (`""`, `"   "`), empty comma segments (`"10.0.0.0/8, "`), entries containing whitespace, non-strings, and invalid CIDR syntax (`ipaddress.ip_network(item, strict=False)`), canonicalizing via `str(network)` and deduplicating in order. Empty sequences (`()` / `'[]'`) are accepted and represent zero additional configured CIDRs; baseline IP safety invariants in `is_ip_safe` remain unconditional.
- **Propagation**: `Settings` compiles to [`SSRFPolicy`](file:///home/src/wishenka/items/ssrf.py#L45-L72) and flows through [`create_app`](file:///home/src/wishenka/web/app.py#L185-L193), [`preview_item_input`](file:///home/src/wishenka/web/routes/items_ui.py#L479-L481) fallback, [`wishenka.bot.__main__.run()`](file:///home/src/wishenka/bot/__main__.py#L85), [`safe_direct_route`](file:///home/src/wishenka/items/fetcher.py#L217-L231), [`validate_url`](file:///home/src/wishenka/items/fetcher.py#L69-L98), [`UrlMetadataService`](file:///home/src/wishenka/items/fetcher.py#L279-L518), [`ItemPreviewService`](file:///home/src/wishenka/items/service.py#L67-L508), and [`SSRFSafeTransport`](file:///home/src/wishenka/items/ssrf.py#L750-L867). Zero-argument callers resolve the ambient `get_default_ssrf_policy()` (cached per env/`.env` snapshot) or active `_active_policy_var`. `wishenka/config.py` imports no internal `wishenka.*` modules and emits no logs, keeping startup validation fail-fast and dependency-cycle free.

| Setting / Env Var / Constant | Default Value | Description |
| --- | --- | --- |
| `ssrf_max_response_bytes` / `WISHENKA_SSRF_MAX_RESPONSE_BYTES` / `MAX_RESPONSE_BYTES` | `2 * 1024 * 1024` (2 MB / `2,097,152` bytes) | Maximum permitted response size (`>= 1` integer) before aborting via `ResponseBodyTooLargeError`. |
| `ssrf_allowed_schemes` / `WISHENKA_SSRF_ALLOWED_SCHEMES` / `ALLOWED_SCHEMES` | `("http", "https")` / `frozenset({"http", "https"})` | Non-empty allowlist of URL schemes (JSON array or CSV string), bounded by `SUPPORTED_SSRF_SCHEMES`. |
| `SUPPORTED_SSRF_SCHEMES` | `frozenset({"http", "https"})` | Closed set of schemes accepted by `Settings` and `SSRFPolicy` validation. |
| `ssrf_forbidden_cidrs` / `WISHENKA_SSRF_FORBIDDEN_CIDRS` / `FORBIDDEN_NETWORKS` | 20 default IPv4/IPv6 CIDRs (`DEFAULT_SSRF_FORBIDDEN_CIDRS`) | Configurable CIDR blocklist (JSON array or CSV string); merged with unconditional baseline IP safety checks. |
| `DEFAULT_DNS_CACHE_TTL_SECONDS` | `60.0` (60 seconds) | Monotonic TTL for cached SSRF-validated DNS resolutions in `DNSCache`. |
| `DEFAULT_DNS_CACHE_CAPACITY` | `512` | Maximum normalized `(host, port)` entries in `DNSCache` before LRU eviction. |
| `DEFAULT_TIMEOUT` | `httpx.Timeout(4.0, connect=2.0)` | Total budget `4.0s`, connection budget `2.0s`. |
| `DEFAULT_HEADERS` | iOS Safari Mobile UA, Ru/En Accept | Standard headers maximizing storefront compatibility. |
| Preview cache | 256 entries, 300 seconds maximum TTL | Per application instance; LRU eviction, origin freshness, and active `SSRFPolicy` hit revalidation apply. |
| Preview connection pool | 20 connections, 10 keep-alive, 5 seconds idle expiry | Lifespan-owned outbound transport; per application instance. |
| `TRACKING_QUERY_PREFIXES` | `("utm_",)` | Prefixes stripped from URL queries. |
| `TRACKING_QUERY_KEYS` | Set of 14 ad click / affiliate keys | Query keys stripped (`clid`, `targeturl`, `src`, `promo`, `track`, `ref`, `fbclid`, `gclid`, `yclid`, etc.). |
| `CHALLENGE_SIGNATURES` | List of 23 anti-bot / WAF markers | Substrings scanned case-insensitively in HTML responses (Cloudflare, Qrator, DDoS-Guard, Yandex SmartCaptcha, Avito IP firewall, Ozon/WB/Megamarket challenges). |
| `WISHENKA_CASSETTE_MODE` | `"replay"` (default), `"record"`, `"refresh"` | Environment variable controlling `resolve_cassette_mode` when no explicit `mode` argument is supplied. |
| `DEFAULT_CASSETTES_DIR` | `tests/cassettes/marketplaces` | Default directory containing versioned marketplace YAML cassettes. |
| `SENSITIVE_HEADER_NAMES` / `SENSITIVE_HEADER_SUBSTRINGS` | Set of 16 names + 7 substrings | Headers stripped by `sanitize_headers` before persisting cassettes (`Authorization`, `Cookie`, `Set-Cookie`, `X-Api-Key`, `X-Csrf-Token`, client IP headers, etc.). |
| `SENSITIVE_QUERY_KEYS` | Set of 18 query parameter names | Query keys stripped by `sanitize_uri` (`token`, `access_token`, `api_key`, `session_id`, `password`, `signature`, etc.). |

### Forbidden Network CIDRs (`DEFAULT_SSRF_FORBIDDEN_CIDRS` / `FORBIDDEN_NETWORKS`)

The following 20 subnets comprise [`DEFAULT_SSRF_FORBIDDEN_CIDRS`](file:///home/src/wishenka/config.py#L14-L35) (and [`FORBIDDEN_NETWORKS`](file:///home/src/wishenka/items/ssrf.py#L39-L41)). They can be extended or replaced via `WISHENKA_SSRF_FORBIDDEN_CIDRS`, while baseline `ipaddress` safety checks in [`is_ip_safe`](file:///home/src/wishenka/items/ssrf.py#L270-L282) (`not ip.is_global`, `is_private`, `is_loopback`, `is_link_local`, `is_multicast`, `is_reserved`, `is_unspecified`, plus recursive `ip.ipv4_mapped` unwrapping) remain **unconditionally enforced** even when `ssrf_forbidden_cidrs` is set to `()` or `'[]'`:
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

All events are logged via structured extra dictionaries under logger names `"wishenka.items"` (URL parsing, SSRF policy, and preview pipeline), `"wishenka.web"` (web startup SSRF metadata), `"wishenka.wishlists"` (domain service lifecycle), `"wishenka.wishlists.store"` (wish-scoped inventory commit, busy, and rollback), `"wishenka.web.items"` (REST API layer), and `"wishenka.web.items_ui"` (TMA HTMX UI layer):

#### 1. Wish Items Lifecycle & Accounting Events (`wishenka.wishlists`, `wishenka.wishlists.store`, `wishenka.web.items`)

| Event Name | Level | Key Context Fields | Trigger Condition |
| :--- | :---: | :--- | :--- |
| `item_created` | `INFO` | `wishlist_id`, `item_id`, `actor_id`, `recipient_user_id`, `quantity`, `display_order`, `has_recipient` | Wish item successfully added to wishlist with auto-incremented `display_order`. |
| `item_updated` | `INFO` | `wishlist_id`, `item_id`, `actor_id`, `updated_fields`, `quantity`, `quantity_delta` | Wish item properties updated within reduction limits. |
| `item_archived` | `INFO` | `wishlist_id`, `item_id`, `actor_id` | Item safely soft-deleted while retaining all active reservations. |
| `item_restored` | `INFO` | `wishlist_id`, `item_id`, `actor_id`, `display_order`, `new_display_order` | Archived item restored and appended to the tail of the active list. |
| `items_reordered` | `INFO` | `wishlist_id`, `actor_id`, `item_count`, `count`, `item_ids` | Active items display order atomically permuted. |
| `item_quantity_reduction_rejected` | `WARNING` | `wishlist_id`, `item_id`, `actor_id`, `requested_quantity`, `received_quantity`, `reason` | Quantity is below received units. |
| `item_quantity_overbooked` | `WARNING` | `wishlist_id`, `item_id`, `actor_id`, `quantity`, `quantity_delta`, `notified_givers_count` | Quantity reduction leaves the wish over-booked. Restrict access to this diagnostic event: the count can reveal promise activity. |
| `wishlist_inventory_committed` | `INFO` | `item_id`, `operation`, `reservations_written` | `WishlistStore.execute_wish` after `COMMIT`. No row dump, title, or gifter identity. A failed attempt does not emit this event. |
| `wishlist_inventory_busy` | `WARNING` | `item_id` or `reservation_id`, `operation` | `SQLITE_BUSY` after `busy_timeout` became `InventoryBusyError`. The wish is unchanged. No gifter id or name. A full-snapshot `execute` with no wish key omits the id. |
| `wishlist_inventory_rolled_back` | `WARNING` | `error_type`, `item_id` or `reservation_id`, `operation` | Domain refusal (`WishlistError` or `ValueError`, including a quantity or membership check). The exception is re-raised. Driver text and gifter identity are omitted. |
| `wishlist_inventory_rolled_back` | `ERROR` | `error_type`, `item_id` or `reservation_id`, `operation` | Non-busy `SQLAlchemyError` only when the wish key is present (`item_id`, `reservation_id`, or `operation`). Re-raised as `RuntimeError` (`Wishlist storage operation failed`). |
| `wishlist_store_error` | `ERROR` | none | [`WishlistStore.execute`](file:///home/src/wishenka/wishlists/store.py#L1221) calls `_raise_for_storage_error` with no `item_id`, `reservation_id`, or `operation`. A full-snapshot `execute` omits the id and the operation. That branch logs this event for a non-busy `SQLAlchemyError`, then raises `RuntimeError` (`Wishlist storage operation failed`). |
| `item_inventory_busy` | `WARNING` | `operation`, `item_id` when the route is wish-scoped | `items.py` `execute` mapped `InventoryBusyError` to HTTP 503. The response body is the busy sentence and names no gifter. |
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
| `jsonld_graph_traversal` | `DEBUG` | `graph_items_count` | Entering a `list` or `dict` JSON-LD `@graph` container during discovery (scalar item count only). |
| `jsonld_parse_skipped` | `DEBUG` | — | Malformed or excessively nested JSON-LD was skipped. |
| `jsonld_type_limit` | `DEBUG` | `visited_nodes` | Product `@type` inspection reached `depth > 128` or `20,000` visited nodes (also replayed on discovery-local memo hits). |
| `jsonld_discovery_limit` | `DEBUG` | `visited_nodes` | Product discovery reached `depth > 128` or `20,000` visited nodes with pending stack frames remaining. |
| `jsonld_aggregate_offer_extracted` | `DEBUG` | `url_domain`, `offer_price`, `low_price`, `high_price` | Extracted price from Schema.org `AggregateOffer`. |
| `metadata_extraction_started` | `DEBUG` | `url_domain`, `parser_stage="start"` | Commenced HTML parsing and metadata extraction. |
| `metadata_stage_resolved` | `DEBUG` | `url_domain`, `parser_stage` (`json_ld`, `opengraph`) | Intermediate parsing stage successfully resolved fields. |
| `metadata_extraction_completed` | `INFO` | `url_domain`, `duration_ms`, `has_title`, `has_price`, `has_image` | HTML extraction completed; fields resolved. |
| `item_preview_anti_bot` | `WARNING` | `status_code`, `url_domain`, `input_type`, `duration_ms`, `fallback_reason` | Intercepted anti-bot gate (`403`, `429`, `503`, or `200 OK` HTML matching `CHALLENGE_SIGNATURES` including Russian marketplace anti-bot screens). |
| `anti_bot_challenge_detected` | `INFO` | `status_code`, `url_domain`, `input_type`, `duration_ms`, `fallback_reason` | Telemetry signal for anti-bot degradation monitoring (`status_code=200` on `200 OK` HTML challenges). |
| `cassette_loaded` | `DEBUG` | `cassette_path`, `marketplace`, `scenario`, `interactions_count` | YAML cassette file loaded and parsed from disk. |
| `cassette_saved` | `DEBUG` | `cassette_path`, `marketplace`, `scenario`, `interactions_count` | Sanitized YAML cassette persisted to disk. |
| `cassette_replay_hit` | `DEBUG` | `method`, `uri`, `status_code`, `mode`, `marketplace`, `scenario` | Incoming request matched a recorded interaction in `REPLAY` or `RECORD` mode. |
| `cassette_miss` | `WARNING` | `method`, `uri`, `cassette_path`, `marketplace`, `scenario` | Unrecorded request encountered in offline `REPLAY` mode before raising `CassetteMissError` (`uri` is sanitized via `sanitize_uri`). |
| `cassette_recorded` | `INFO` | `method`, `uri`, `status_code`, `mode`, `marketplace`, `scenario`, `cassette_path` | New interaction fetched, sanitized, and recorded in `RECORD` mode. |
| `cassette_refreshed` | `INFO` | `method`, `uri`, `status_code`, `mode`, `marketplace`, `scenario`, `cassette_path` | Existing interaction re-fetched, sanitized, and overwritten in `REFRESH` mode. |
| `item_preview_plain_text` | `DEBUG` | `input_type`, `duration_ms` | Non-URL text input processed without network calls. |
| `ssrf_policy_loaded` | `DEBUG` | `component`, `source` (`"default_settings"`), `max_response_bytes`, `allowed_schemes`, `forbidden_cidr_count` | Ambient default `SSRFPolicy` loaded/reloaded from `Settings()` when env/`.env` snapshot initializes or changes. |
| `ssrf_policy_configured` | `DEBUG` | `component` (`"SSRFSafeTransport"`, `"UrlMetadataService"`, `"ItemPreviewService"`), `source` (`"settings"`, `"policy"`, `"max_bytes_override"`), `max_response_bytes`, `allowed_schemes`, `forbidden_cidr_count` | Component initialized with an explicit `Settings`, `SSRFPolicy`, or `max_bytes` override. |
| `preview_cache_lookup` | `DEBUG` | `cache_outcome` (`hit`, `miss`) | Cache lookup without logging its URL or key. |
| `preview_cache_revalidation_evicted` | `DEBUG` | `url_domain`, `destination_count` | Cached `PreviewCache` entry evicted after failing active `SSRFPolicy` revalidation (`validate_url`). |
| `item_preview_success` | `INFO` | `url_domain`, `duration_ms`, `input_type`, `is_fallback=False` | Successful link preview retrieval (HTTP 200). |
| `item_preview_ssrf_blocked` | `WARNING` | `url`, `url_domain`, `host`, `ip`, `reason`, `forbidden_cidr_count`, `input_type`, `duration_ms`, `fallback_reason="ssrf_blocked"` | SSRF attempt caught during preview generation (credential-redacted `url`); returns fallback. |
| `item_preview_invalid_scheme` | `WARNING` | `url`, `url_domain`, `scheme`, `allowed_schemes`, `reason="invalid_scheme"`, `input_type`, `duration_ms`, `fallback_reason="ssrf_blocked"` | Disallowed URL scheme caught against active `SSRFPolicy` (credential-redacted `url`); returns fallback. |
| `item_preview_response_too_large` | `WARNING` | `url`, `url_domain`, `content_length`, `max_allowed`, `reason="response_too_large"`, `input_type`, `duration_ms`, `fallback_reason="response_too_large"` | Oversized payload exceeding active `max_bytes` caught during preview generation (credential-redacted `url`); returns fallback. |
| `item_preview_timeout` | `WARNING` | `url_domain`, `duration_ms`, `fallback_reason="timeout"` | HTTP connection or read timeout ($> 4.0\text{s}$). |
| `item_preview_http_error` | `WARNING` | `status_code`, `url_domain`, `duration_ms`, `fallback_reason="http_error"` | Upstream HTTP $\ge 400$ error handled safely. |
| `item_preview_network_error` | `WARNING` | `url_domain`, `duration_ms`, `fallback_reason="http_error"` | Network transport error handled safely. |
| `item_metadata_parsing_error` | `ERROR` | `url_domain`, `duration_ms`, `fallback_reason="http_error"` | Unexpected HTML parsing failure during extraction. |
| `ssrf_blocked` | `WARNING` | `host`, `ip`, `reason`, `forbidden_cidr_count`, `cache_revalidation`, `url`, `scheme`, `allowed_schemes`, `path` (variant-dependent) | Low-level SSRF rejection on `validate_url`, redirect hook, DNS lookup, `DNSCache` revalidation (`cache_revalidation=True`), or transport (`reason`: `"forbidden_ip"`, `"credentials"`, `"invalid_scheme"`, `"uds"`, `"unsafe_backend"`, `"missing_host"`). Credential-redacted `url` is included for `"invalid_scheme"`/`"missing_host"`; `"credentials"` logs `host` only. |
| `payload_size_violation` | `WARNING` | `url`, `content_length` or `streamed_bytes`, `max_allowed`, `reason` | `Content-Length` (`"content_length_exceeded"`) or streaming chunks (`"stream_chunk_overflow"`) exceed configured `self.max_bytes` (credential-redacted `url`). |
| `fetch_and_extract_fallback` | `WARNING` | `url`, `error` | `UrlMetadataService.fetch_and_extract` caught fetch/parse failure and returned fallback `ExtractedMetadata` (credential-redacted `url`). |
| `dns_cache_hit` | `DEBUG` | `host`, `port`, `ip_count`, `forbidden_cidr_count` | Unexpired SSRF-validated IP list returned from `DNSCache` after active-policy CIDR revalidation. |
| `dns_cache_miss` | `DEBUG` | `host`, `port` | Cold or expired hostname initiated an uncached DNS resolution leader task. |
| `dns_single_flight_coalesced` | `DEBUG` | `host`, `port` | Concurrent request joined an already in-flight DNS resolution on the same event loop. |
| `dns_cache_expired` | `DEBUG` | `host`, `port` | Cached DNS entry's monotonic TTL elapsed and was lazily removed on lookup. |
| `dns_cache_evicted` | `DEBUG` | `evicted_host`, `evicted_port`, `capacity` | Least-recently-used DNS cache entry evicted to stay within `capacity`. |
| `dns_resolution_start` | `DEBUG` | `host`, `clean_host`, `port` | Starting asynchronous DNS resolution. |
| `dns_resolution_success` | `DEBUG` | `host`, `resolved_ips` | Successfully resolved hostname to safe IPs. |
| `dns_resolution_failed` | `INFO` | `host`, `error` | Host failed to resolve (NXDOMAIN, gaierror). |
| `ssrf_pinned_cache_miss` | `DEBUG` | `host`, `port`, `policy_source` (`"pinned"` / `"ambient"`), `forbidden_cidr_count` | Defense-in-depth fallback resolution when `_pinned_ips_var` has no entry for `(host, port)`. |
| `ssrf_no_validated_ips` | `WARNING` | `host`, `port` | `connect_tcp` aborted because no validated IP addresses are available. |
| `ssrf_pinned_connect_failed` | `DEBUG` | `host`, `ip`, `port`, `error` | Single pinned IP TCP connection attempt failed; failing over to next pinned IP. |
| `ssrf_all_pinned_connects_failed` | `WARNING` | `host`, `port`, `attempted_count`, `error` | All pinned IP TCP connection attempts failed for `host:port`. |
| `ssrf_request_dispatch` | `DEBUG` | `url`, `host`, `scheme`, `pinned_ip_count` | Outbound request verified, IPs pinned, and request dispatched. |
| `url_fetch_success` | `INFO` | `url`, `effective_url`, `bytes` | Successfully streamed and decoded response body. |

#### 3. TMA HTMX Wish Item UI Events (`wishenka.web.items_ui`)

| Event Name | Level | Key Context Fields | Trigger Condition |
| :--- | :---: | :--- | :--- |
| `ui_item_quick_add_preview` | `INFO` | `wishlist_id`, `actor_id`, `user_id`, `input_type`, `domain`, `store_name`, `is_fallback`, `duration_ms` | Universal input classified (`PLAIN_TEXT` or URL) and live preview card or fallback rendered. |
| `ui_item_quick_add_success` | `INFO` | `wishlist_id`, `item_id`, `actor_id`, `user_id`, `has_link`, `price`, `quantity` | Wish item created via Quick Add Bar or creation modal with HTMX OOB resets. |
| `ui_item_edit_opened` | `INFO` | `wishlist_id`, `item_id`, `actor_id`, `user_id`, `mode`, `received_quantity` (edit only), `is_collaborative` | Detailed item creation (`mode="create"`) or edit (`mode="edit"`) BottomSheet modal opened. |
| `ui_reduction_lock_rejected` | `WARNING` | `wishlist_id`, `item_id`, `actor_id`, `user_id`, `requested_quantity`, `received_quantity` | Edit submission rejected with HTTP 409 due to quantity below received units. |
| `ui_item_edit_busy` | `WARNING` | `wishlist_id`, `item_id` | Edit modal returned HTTP 503. The sentence names no gifter. |
| `ui_item_edit_validation_error` | `WARNING` | `stage`, `status_code`, `wishlist_id`, `item_id`, `actor_id`, `user_id` | Edit modal form or domain validation failed (HTTP 400). User-entered strings are omitted. |
| `ui_item_quick_add_validation_error` | `WARNING` | `reason`, `status_code`, `wishlist_id`, `actor_id`, `user_id` | Quick-add submission failed validation (HTTP 400). User-entered strings are omitted. |
| `ui_modal_domain_error` | `WARNING` | `operation`, `error_type`, `status_code`, `wishlist_id`, `item_id`, `actor_id`, `user_id` | Modal/UI route encountered `WishlistArchivedError` (409) or missing/forbidden resource (404) and returned an OOB `#list-notice`. |
| `ui_item_edit_saved` | `INFO` | `wishlist_id`, `item_id`, `actor_id`, `user_id`, `quantity`, `has_recipient` | Wish item attributes and collaborative recipient targeting saved via edit modal. |
| `ui_item_archived` | `INFO` | `wishlist_id`, `item_id`, `actor_id`, `user_id` | Wish item safely archived via HTMX UI while preserving gifter reservations. |
| `ui_item_restored` | `INFO` | `wishlist_id`, `item_id`, `actor_id`, `user_id` | Archived wish item restored to the active list via HTMX UI. |

#### 4. Web Application Startup SSRF Metadata (`wishenka.web`)

Inside [`create_app`](file:///home/src/wishenka/web/app.py#L209-L220) lifespan, `"Wishenka web application starting up"` (`INFO` on logger `wishenka.web`) logs bounded SSRF configuration metadata alongside application runtime fields:
- `ssrf_max_response_bytes`: configured `settings.ssrf_max_response_bytes` integer limit.
- `ssrf_allowed_schemes`: `list(settings.ssrf_allowed_schemes)` (e.g. `["http", "https"]` or `["https"]`).
- `ssrf_forbidden_cidr_count`: `len(settings.ssrf_forbidden_cidrs)` (bounded scalar count; full CIDR lists and application secrets are never dumped).

### Privacy & Data Protection Guarantees

In accordance with security requirements:
- **Zero Capability Token Leaks**: Wishlist capability tokens (`public_token`, `invite_token`) are strictly omitted from item logs and exceptions.
- **Credential handling**: Outbound requests reject URL userinfo and authorization headers.
  [`redact_url_credentials`](file:///home/src/wishenka/items/ssrf.py#L107-L115) removes
  userinfo from the URL fields in SSRF, size, and preview warning logs. This is not a general
  guarantee for all derived values: `ItemPreviewDTO.url` can retain userinfo, and the fallback
  store-name and UI domain parsing paths can derive a value from the original URL. Avoid treating
  those values as credential-free; the remaining parsing and redaction gap is tracked in
  `ai-tasks/WISHENKA-93/60-tech-debt.md`.
- **Bounded Policy Telemetry**: Startup and policy logs emit scalar bounds (`ssrf_forbidden_cidr_count`, `forbidden_cidr_count`, `max_response_bytes`, `allowed_schemes`) rather than dumping full CIDR lists.
- **No Payload Leaks**: Raw HTML bodies, full upstream responses, and long user notes are never dumped into logs.
- **Tracking Parameter Value Isolation**: URL tracking removal logs list sanitized key names only (`removed_keys=["utm_source"]`), strictly omitting query parameter values that might contain sensitive affiliate IDs or campaign tokens.
- **No Internal IP Leak to Clients**: Client-facing DTOs (`ItemPreviewDTO`) receive generic `fallback_reason="ssrf_blocked"`; internal IP details remain isolated to server audit logs.
- **No gifter on a busy wish**: `InventoryBusyError`, the HTTP 503 detail, the edit-modal sentence, and `wishlist_inventory_busy` / `wishlist_inventory_rolled_back` / `item_inventory_busy` / `ui_item_edit_busy` omit gifter ids and names.
- **Clean Domains**: Domains are extracted without ports or query parameters (`url_domain`) for clean metric aggregation.

---

## Troubleshooting

### Garbled text or missing structured product metadata

- **Symptom**: A preview contains replacement characters, incorrect Cyrillic text, or misses a
  product present in JSON-LD.
- **Cause**: A legacy charset declaration may be wrong or an undeclared page may be ambiguous.
  Invalid JSON-LD and products beyond the fixed traversal limits (`20,000` visited nodes or
  depth `128` in discovery or `@type` inspection; pending dictionary processing stops once
  `20,000` discovery visits are reached) are skipped.
- **Resolution**: Compare the response bytes, `Content-Type` charset and early meta declarations
  in a controlled environment; avoid logging page contents. At `DEBUG` level, inspect
  `jsonld_parse_skipped`, `jsonld_graph_traversal`, `jsonld_discovery_limit`, and
  `jsonld_type_limit` (which also replays on discovery-local memo hits without logging raw
  `@type` tokens or node values). Users can edit fields manually. Run
  `.venv/bin/pytest tests/test_encoding_nested_graph.py tests/test_jsonld_traversal_bounds.py`
  for offline encoding and bounded-traversal regressions (covering `_jsonld_traversal_diagnostics`
  and `262`/`131` pending-record bounds); expanding the encoding calibration corpus remains
  tracked in WISHENKA-117.

### 1. SSRF Blocked Targets (`fallback_reason="ssrf_blocked"`)

- **Symptom**: `ItemPreviewDTO` returns with `is_fallback=True` and `fallback_reason="ssrf_blocked"`.
- **Cause**: The input URL points to an IP or domain resolving to localhost (`127.0.0.1`, `::1`), private networks (`10.x`, `172.16.x`, `192.168.x`), cloud metadata (`169.254.169.254`), CGNAT (`100.64.x`), or a custom range configured in `WISHENKA_SSRF_FORBIDDEN_CIDRS` (including after a `DNSCache` or `PreviewCache` hit revalidation against a stricter active policy).
- **Resolution**: This is the intended security defense. Check server logs under `event="ssrf_blocked"` or `event="item_preview_ssrf_blocked"` for the destination host, resolved IP, `reason`, `forbidden_cidr_count`, and `cache_revalidation=True` (when a warm `DNSCache` hit was rejected by the active policy; `PreviewCache` evictions log `preview_cache_revalidation_evicted` at `DEBUG`). Verify `WISHENKA_SSRF_FORBIDDEN_CIDRS` in `.env` or environment variables (note that baseline `ipaddress` protections in `is_ip_safe` remain enforced even if `WISHENKA_SSRF_FORBIDDEN_CIDRS='[]'`). Note that `DNSCache` never caches negative results (`SSRFBlockedError`, `socket.gaierror`, or empty IP lists), so fixing an upstream DNS record takes effect immediately on the next request (or after at most `DEFAULT_DNS_CACHE_TTL_SECONDS = 60.0` seconds if a previous public IP entry was cached; call `clear_dns_cache()` in tests or interactive sessions to flush immediately). If a host fails DNS resolution or all pinned IPs fail to connect, inspect `dns_resolution_failed`, `ssrf_no_validated_ips`, and `ssrf_all_pinned_connects_failed` (in `DEBUG`, `ssrf_policy_loaded`, `ssrf_policy_configured`, `dns_cache_hit`, `dns_cache_miss`, `dns_single_flight_coalesced`, `dns_cache_expired`, `dns_cache_evicted`, and `ssrf_pinned_connect_failed` trace policy resolution, DNS caching, and per-IP failover attempts).

### 2. Disallowed URL Schemes or Invalid SSRF Startup Config (`fallback_reason="ssrf_blocked"` / `ValidationError`)

- **Symptom**: `fallback_reason="ssrf_blocked"` is returned for links using schemes like `ftp://`, `file://`, `data:`, or `http://` when `WISHENKA_SSRF_ALLOWED_SCHEMES` is restricted to `https`; or application startup / `Settings()` raises `pydantic.ValidationError` on invalid `WISHENKA_SSRF_*` values.
- **Cause**: Runtime requests are checked against `SSRFPolicy.allowed_schemes` (default `("http", "https")`, configurable via `WISHENKA_SSRF_ALLOWED_SCHEMES`). Startup configuration fails fast if `WISHENKA_SSRF_MAX_RESPONSE_BYTES` is non-integer/`bool`/`float`/`< 1`, if `WISHENKA_SSRF_ALLOWED_SCHEMES` is empty/malformed/outside `{"http", "https"}`, or if `WISHENKA_SSRF_FORBIDDEN_CIDRS` contains blank strings, trailing empty comma items (e.g. `"10.0.0.0/8, "`), or invalid CIDR blocks.
- **Resolution**: Check `item_preview_invalid_scheme` / `ssrf_blocked` (`reason="invalid_scheme"`, `allowed_schemes`) and `wishenka.web` startup `ssrf_allowed_schemes` metadata. Ensure `WISHENKA_SSRF_ALLOWED_SCHEMES` and `WISHENKA_SSRF_FORBIDDEN_CIDRS` are either valid JSON string arrays (e.g. `'["https"]'`) or comma-separated strings without trailing commas (e.g. `'https'` or `'http, https'`). Users can still complete item creation manually when a URL falls back.

### 3. Response Body Exceeds Configured Size Limit (`fallback_reason="response_too_large"`)

- **Symptom**: `ItemPreviewDTO` returns with `is_fallback=True` and `fallback_reason="response_too_large"`.
- **Cause**: The target URL serves a response body larger than the configured ceiling (`ssrf_max_response_bytes` / `WISHENKA_SSRF_MAX_RESPONSE_BYTES`, defaulting to 2 MB / `2,097,152` bytes, or an explicit `UrlMetadataService(max_bytes=...)` override).
- **Resolution**: Check server logs for `event="payload_size_violation"` and `event="item_preview_response_too_large"` (`max_allowed`, `content_length` / `streamed_bytes`, and `reason="content_length_exceeded"` or `"stream_chunk_overflow"`). Adjust `WISHENKA_SSRF_MAX_RESPONSE_BYTES` if larger legitimate HTML documents must be parsed; otherwise the preview degrades gracefully to manual entry, protecting the worker from OOM failures. To verify all configurable SSRF settings, env formats, fail-fast validation, cache revalidation, and observability contracts offline, run `.venv/bin/pytest tests/test_ssrf_configurable_settings.py` (uses `pytestmark = pytest.mark.timeout(30)` in [`tests/test_ssrf_configurable_settings.py`](file:///home/src/tests/test_ssrf_configurable_settings.py#L53)).

### 4. Anti-Bot Challenge Fallbacks (Cloudflare / Qrator / WAF / Turnstile / SmartCaptcha / Avito Firewall / 200 OK & 403 / 503)
- **Symptom**: `ItemPreviewDTO` returns with `is_fallback=True` and `fallback_reason="anti_bot_challenge"`.
- **Cause**: The remote store (e.g. Ozon, Wildberries, Yandex Market, Avito, Megamarket) uses anti-scraping mitigation returning HTTP 403, 429, 503, or `200 OK` HTML/JavaScript challenge pages (`_cf_chl_opt`, `turnstile`, `qrator`, `ddos-guard`, `smartcaptcha`, `showcaptcha`, `firewall-container`, `доступ ограничен`, `почти готово`, `проверка браузера`).
- **Resolution**: This is the expected design behavior. The frontend receives the fallback preview populated with the sanitized URL, the recognized store name, and the user's residual text (never leaking challenge page titles like `"Почти готово..."` or `"Доступ ограничен: проблема с IP"`), prompting the user to confirm or edit title and price manually. Dedicated official store APIs or headless rendering sidecars can be attached via [WISHENKA-55](https://pypost.atlassian.net/browse/WISHENKA-55).

### Cassette Miss During Offline Replay (`CassetteMissError`)
- **Symptom**: Running marketplace cassette tests (`pytest tests/test_marketplace_cassettes.py` or `python -m wishenka.items.cassettes --verify`) raises `CassetteMissError: No recorded interaction for GET <uri> in cassette <path>` and logs `event="cassette_miss"`.
- **Cause**: The request URL (after `sanitize_uri` / `clean_url` normalization) or HTTP method does not match any `request.uri` recorded in the loaded YAML cassette, or URL normalization rules in `clean_url` changed. In `CassetteMode.REPLAY`, `CassetteTransport` is fail-closed and `ItemPreviewService.fetch_preview` / `UrlMetadataService.fetch_and_extract` explicitly re-raise `CassetteError` rather than converting it to `fallback_reason="http_error"`.
- **Resolution**: Inspect the `uri` and `cassette_path` attributes on `CassetteMissError` (or the `cassette_miss` warning log). Verify that new query parameters were either added to `TRACKING_QUERY_KEYS` / `SENSITIVE_QUERY_KEYS` if they are tracking/secret tokens, or refresh the cassette intentionally in an environment with network access using `python -m wishenka.items.cassettes --mode refresh --url "<url>" --output <cassette.yaml>` and inspect `git diff` to confirm no cookies or sensitive headers were persisted.

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
- **Resolution**: Check external internet connectivity and upstream store availability. The HTTP
  timeout does not limit time spent parsing after the response has been downloaded.

### Slow previews during concurrent extraction

- **Symptom**: Preview duration or unrelated request latency grows while large pages are parsed.
- **Cause**: The shared executor may be busy or queued; CPU contention under the GIL can also
  delay the event loop. Cancelled requests can leave already-running extraction work behind.
- **Resolution**: Inspect `item_preview_success` duration and parsing-error events alongside CPU
  and request load. The duration includes fetching, queueing, and parsing; it does not isolate
  queue or parse time. Investigate sustained contention using the WISHENKA-113 follow-up.

### Repeated preview requests still fetch upstream

- **Cause**: The response or a redirect may not explicitly permit public caching, or may contain
  a query string, cookies, `Vary`, restrictive directives, or expired freshness. Entries also
  expire, are evicted, and are local to each application instance. Simultaneous misses can fetch
  independently.
- **Resolution**: Inspect `preview_cache_lookup` at DEBUG level and check upstream cache headers
  without logging sensitive URLs. Verify that the application lifespan is running; direct
  standalone services do not automatically share the application cache.

### 8. Quantity Reduction Rejection (`CannotReduceQuantityBelowReservedError` / HTTP 409 Conflict)
- **Symptom**: The item `PATCH` or edit modal returns HTTP 409 and reports already received units.
  The modal preserves the form.
- **Cause**: The requested quantity is below `received_quantity`.
- **Resolution**: Set quantity to at least `max(1, received_quantity)` and retry. The store logs
  `wishlist_inventory_rolled_back` with `CannotReduceQuantityBelowReservedError`.

### Wish inventory busy (`InventoryBusyError` / HTTP 503)
- **Symptom**: `PATCH` returns `503 Service Unavailable` with detail `The wish was busy and the attempt changed nothing`. `POST .../items/{item_id}/edit` returns `503` and re-renders the edit modal with `The wish was busy, the edit was not saved, and it can be submitted again.` Neither sentence names a gifter. The wish balance is unchanged.
- **Cause**: Another writer held the SQLite reserved lock until `busy_timeout` (5000 ms) elapsed. `execute_wish` rolled the transaction back and raised `InventoryBusyError`. This is the shared write path. Redis and `asyncio.Lock` do not exclude the other process.
- **Resolution**: Submit the same change again. Confirm `wishlist_inventory_busy` at `WARNING` on `wishenka.wishlists.store`, and `item_inventory_busy` or `ui_item_edit_busy` on the route logger. A quantity or membership refusal stays HTTP 409 or 400 and logs `wishlist_inventory_rolled_back` at `WARNING`. A non-busy `SQLAlchemyError` logs `wishlist_inventory_rolled_back` at `ERROR` only when the wish key is present. A full-snapshot `execute` that omits the id and the operation logs `wishlist_store_error` at `ERROR`. Both become `RuntimeError` (`Wishlist storage operation failed`).

To verify both HTTP responses, run:

```bash
make test PYTEST_ARGS='-n 0 tests/test_item_busy_responses.py'
```

These tests inject `InventoryBusyError` into the store, exercise the real HTTP handlers, and
check response privacy, preserved form fields, and the unchanged item. They do not simulate an
actual SQLite lock; the module has an explicit 30-second timeout.

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
