# WISHENKA-11: Technical Debt Analysis

## Shortcuts Taken

1. **Synchronous In-Memory HTML Parsing with BeautifulSoup4**:
   - **Context**: `HtmlMetadataExtractor.extract(html: str, base_url: str)` constructs a full DOM representation using `BeautifulSoup(html, "html.parser")` synchronously on the main asyncio event loop.
   - **Trade-off**: For small and medium HTML payloads (< 100 KB), parse time is within 1–5 ms. However, for large HTML documents (> 1 MB), CPU-bound DOM construction blocks the event loop, momentarily starving concurrent web requests and bot webhooks.
   - **Compromise**: Avoided pulling in C-dependencies (`lxml`, `selectolax`) or managing `asyncio.to_thread` executor overhead during the initial baseline implementation.

2. **No Headless Browser Execution for Client-Side Rendered (SPA) Sites**:
   - **Context**: `ItemPreviewService.fetch_preview` relies purely on HTTP GET requests via `httpx.AsyncClient`.
   - **Trade-off**: Heavy JavaScript single-page applications (SPAs) without server-side rendering (SSR) or embedded JSON-LD/OpenGraph tags only yield fallback text or minimal metadata.
   - **Compromise**: Avoided heavyweight headless browser infrastructure (Playwright, Puppeteer, Selenium) to maintain zero external binary dependencies and sub-second preview response times. The fallback mechanism reliably degrades to manual user input.

3. **Hardcoded Static Store Mapping and Regular Expressions**:
   - **Context**: `KNOWN_STORES`, `CURRENCY_MAP`, and `clean_title` noise patterns in `wishenka/items/parser.py` are statically hardcoded dictionaries and regexes.
   - **Trade-off**: Adding or tuning marketplace mappings or currency conversions requires modifying source code rather than updating configuration or external pattern files.

4. **Ephemeral HTTP Client Instantiation per Request**:
   - **Context**: When an external `client` is not injected into `ItemPreviewService.fetch_preview`, an ad-hoc `httpx.AsyncClient` is created and closed per request.
   - **Trade-off**: Connection pools, TLS session resumption, and DNS caches are not reused across subsequent requests.

## Code Quality Issues

1. **Monolithic Cascading Parser in `parser.py`**:
   - `HtmlMetadataExtractor` encapsulates JSON-LD traversing, OpenGraph parsing, Microdata extraction, standard HTML fallback, price normalization, and title cleaning within a single module.
   - Future extensions for marketplace-specific parsing (e.g., extracting Ozon SKU/specs, Wildberries internal product cards) would bloat this class unless refactored into a strategy/pipeline pattern with discrete provider extractors.

2. **Lack of Outbound SSRF Protection**:
   - `UniversalInputClassifier` and `ItemPreviewService` accept arbitrary user URLs without validating against private/internal IP ranges (e.g., `127.0.0.1`, `10.0.0.0/8`, `192.168.0.0/16`, `169.254.169.254`). While deployed environments typically restrict egress, defense-in-depth URL sanitization is currently missing.

3. **Absence of Link Preview Caching Layer**:
   - Identical URLs submitted by different users or repeatedly previewed in the UI trigger repeated network roundtrips to the destination store. There is no short-lived cache (in-memory or Redis/SQLite) for extracted metadata.

4. **Outbound Rate Limiting / Domain Throttling**:
   - There is no per-destination domain throttling. A burst of requests to a single store domain (e.g. 50 simultaneous users adding items from the same store) could lead to rate limiting or IP banning by the store's anti-bot system.

## Missing Tests

1. **Legacy and Exotic Character Encodings**:
   - Current test cases in `tests/test_item_input_parsing.py` test valid UTF-8 strings. Missing test scenarios for legacy Russian e-commerce encodings (`Windows-1251`, `CP1251`, `KOI8-R`) or pages with conflicting HTTP headers vs. `<meta charset>` tags.

2. **Complex and Nested Schema.org JSON-LD Formats**:
   - Schema.org feeds can nest `Product` objects inside `@graph` arrays, `WebPage`, or composite catalogs (`itemListElement`). While recursive traversal (`_find_jsonld_products`) supports dictionaries and lists, dedicated unit tests with complex `@graph` payloads from real e-commerce platforms (Shopify, WooCommerce, Magento) should be added.

3. **SSRF and Protocol Filtering Test Scenarios**:
   - Tests do not currently assert rejection of non-HTTP schemes (e.g. `file://`, `ftp://`, `gopher://`) or loopback addresses in production preview flows.

4. **Response Payload Streaming and Truncation Limit Tests**:
   - Lack of tests ensuring that massive payloads (e.g., multi-gigabyte files or decompression bombs) are safely capped at a byte limit during HTTP download.

## Performance Concerns

1. **Event Loop Blocking under High Concurrency**:
   - In-memory parsing with `BeautifulSoup` executes synchronously on the event loop. If 20–50 requests are processed concurrently, CPU contention in Python's GIL can introduce latency spikes for concurrent FastAPI requests.

2. **Unbounded Response Body Ingestion**:
   - `client.get()` reads the entire body into memory before extracting metadata. If a target URL serves an unexpectedly large payload (e.g., a 100 MB media file mistakenly linked), memory consumption will spike.

3. **Connection Handshake Overhead**:
   - Instantiating short-lived `httpx.AsyncClient` instances incurs full TCP 3-way handshake and TLS negotiation overhead for each preview, adding 100–300 ms to every request.

## Follow-up Tasks

- **DEBT-1: Non-blocking HTML parsing with threadpool or high-performance parser**
  - *Jira Issue*: [WISHENKA-52](https://pypost.atlassian.net/browse/WISHENKA-52) (2.0 Story Points)
  - *Description*: Offload `HtmlMetadataExtractor.extract` to a background worker thread via `asyncio.to_thread` or evaluate lightweight C-based parsers (`selectolax`/`lexbor` or `lxml`) to eliminate asyncio event loop blocking.
  - *Target Epic*: WISHENKA-10
  - *Priority*: Medium

- **DEBT-2: Persistent HTTP client pool and preview cache**
  - *Jira Issue*: [WISHENKA-53](https://pypost.atlassian.net/browse/WISHENKA-53) (3.0 Story Points)
  - *Description*: Provide an application-scoped singleton `httpx.AsyncClient` with connection pooling, keep-alive, and an LRU/TTL cache (e.g., Redis or in-memory cache) to prevent duplicate outbound scrapes for identical URLs.
  - *Target Epic*: WISHENKA-10
  - *Priority*: Medium

- **DEBT-3: SSRF protection and response body size limit**
  - *Jira Issue*: [WISHENKA-54](https://pypost.atlassian.net/browse/WISHENKA-54) (3.0 Story Points)
  - *Description*: Add DNS resolution validation to block private/reserved IP ranges (`127.0.0.1`, `10.0.0.0/8`, `192.168.0.0/16`, `169.254.169.254`, `::1`) and stream response bodies up to a strict maximum cap (e.g., 2 MB) to prevent DoS.
  - *Target Epic*: WISHENKA-10
  - *Priority*: High

- **DEBT-4: Pluggable marketplace extractor pipeline**
  - *Jira Issue*: [WISHENKA-55](https://pypost.atlassian.net/browse/WISHENKA-55) (5.0 Story Points)
  - *Description*: Refactor `HtmlMetadataExtractor` into a pluggable pipeline with separate extractors (`JsonLdExtractor`, `OpenGraphExtractor`, `MicrodataExtractor`, and marketplace-specific adapters for Ozon, Wildberries, Yandex Market) implementing a common `MetadataExtractor` protocol.
  - *Target Epic*: WISHENKA-10
  - *Priority*: Low

- **DEBT-5: Character encoding normalization and expanded JSON-LD graph test suite**
  - *Jira Issue*: [WISHENKA-56](https://pypost.atlassian.net/browse/WISHENKA-56) (2.0 Story Points)
  - *Description*: Add comprehensive test fixtures for non-UTF-8 legacy encodings (Windows-1251) and complex Schema.org `@graph` hierarchies.
  - *Target Epic*: WISHENKA-10
  - *Priority*: Low

- **Pre-existing test failures**:
  - `None` (All 70 automated tests in the test suite pass with 0 errors).
