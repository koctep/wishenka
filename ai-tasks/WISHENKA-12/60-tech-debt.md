# WISHENKA-12: Technical Debt Analysis

## Shortcuts Taken

1. **Static Regex Heuristics for Tracking Parameters and Title Cleaning**:
   - **Context**: [`clean_url`](file:///home/src/wishenka/items/marketplaces.py#L29) and [`clean_title`](file:///home/src/wishenka/items/parser.py#L59) rely on static regular expressions and hardcoded string matching (`utm_*`, `from=share*`, `clid`, marketing slogan suffixes such as `"купить в интернет-магазине"`, `"на маркетплейсе"`, etc.).
   - **Trade-off**: While regex-based stripping is computationally lightweight (< 0.1 ms) and requires zero external network calls, it is inherently heuristic and fragile. Stores continuously invent novel referral structures, obfuscated query tokens (e.g. internal base64 state tokens), and dynamic advertising headlines that static regex patterns cannot reliably isolate without false positives or negatives.
   - **Compromise**: Chosen to maintain zero external dependencies and fast sub-millisecond cleaning without maintaining a heavyweight dynamic selector engine or headless browser parsing layer.

2. **Server-Side Static HTML Parsing for Single-Page Applications (SPA / GraphQL)**:
   - **Context**: [`ItemPreviewService`](file:///home/src/wishenka/items/service.py#L40) downloads the initial static HTML payload via [`httpx.AsyncClient`](file:///home/src/wishenka/items/service.py#L137) and analyzes it using [`HtmlMetadataExtractor`](file:///home/src/wishenka/items/parser.py#L195).
   - **Trade-off**: Modern e-commerce sites increasingly hydrate product cards on the client side using JavaScript (React, Next.js, Vue, Nuxt) and dynamic GraphQL queries. If a store serves an empty HTML shell without pre-rendered OpenGraph meta tags or Schema.org JSON-LD scripts, server-side static parsing cannot extract the dynamic product price or description.
   - **Compromise**: The system immediately falls back to graceful degradation ([`ItemPreviewDTO(is_fallback=True)`](file:///home/src/wishenka/items/models.py#L25)) preserving the URL and identified store name, rather than bundling a resource-intensive headless browser (Chromium/Playwright) on the backend.

## Code Quality Issues

1. **Hardcoded Tracking Parameters in `marketplaces.py`**:
   - **Context**: Tracking prefixes ([`TRACKING_QUERY_PREFIXES`](file:///home/src/wishenka/items/marketplaces.py#L11)) and query parameter sets ([`TRACKING_QUERY_KEYS`](file:///home/src/wishenka/items/marketplaces.py#L12)) are defined as module-level constants directly in Python code.
   - **Impact**: Updating the list of tracking parameters or adding store-specific referral tags requires a full code commit, test execution, and application deployment cycle.
   - **Remediation**: Move tracking parameters into an external structured configuration file (e.g., YAML/JSON) or database configuration table loaded dynamically by [`MarketplaceRegistry`](file:///home/src/wishenka/items/marketplaces.py#L162).

2. **Marketplace Rules Coupled Directly in Source Code**:
   - **Context**: Marketplace rules ([`OzonRule`](file:///home/src/wishenka/items/marketplaces.py#L122), [`WildberriesRule`](file:///home/src/wishenka/items/marketplaces.py#L130), [`YandexMarketRule`](file:///home/src/wishenka/items/marketplaces.py#L138), [`AvitoRule`](file:///home/src/wishenka/items/marketplaces.py#L146), [`MegamarketRule`](file:///home/src/wishenka/items/marketplaces.py#L154)) are hardcoded classes registered in [`MarketplaceRegistry._rules`](file:///home/src/wishenka/items/marketplaces.py#L165).
   - **Impact**: Adding a new marketplace, updating domain aliases (e.g. `.by`, `.kz`), or customizing store icons requires editing core application source files.
   - **Remediation**: Implement a pluggable plugin architecture or config-driven loader where marketplace adapters can be registered dynamically via entrypoints or configuration files without altering codebase internals.

## Missing Tests

1. **Live E-commerce Fixture Recording (VCR.py / Cassette Replay)**:
   - **Context**: The test suite in [`tests/test_metadata_extractor_service.py`](file:///home/src/tests/test_metadata_extractor_service.py) currently relies on static synthetic HTML strings and mock HTTP responses.
   - **Gap**: Real marketplace DOM trees, anti-bot challenge signatures (Cloudflare, Qrator), and JSON-LD payloads change frequently in production. Without an automated recording and cassette replay harness (`vcrpy` or `pytest-recording`), upstream DOM drifts may go undetected until reported by end users.
   - **Remediation**: Introduce a cassette-based integration test pipeline that regularly refreshes recordings against staging or public marketplace URLs and alerts on schema discrepancies.

2. **International Currencies Test Scenarios**:
   - **Context**: While [`CURRENCY_MAP`](file:///home/src/wishenka/items/parser.py#L16) and [`normalize_currency`](file:///home/src/wishenka/items/parser.py#L112) include international ISO codes (`CNY`, `GBP`, `JPY`, `USD`, `EUR`, `KZT`, `BYN`), unit test coverage in [`tests/test_metadata_extractor_service.py`](file:///home/src/tests/test_metadata_extractor_service.py) focuses primarily on Russian market currencies (`RUB`, `USD`, `EUR`, `KZT`).
   - **Gap**: End-to-end extraction scenarios featuring Chinese Yuan (`CNY`, `¥`), British Pounds (`GBP`, `£`), and Japanese Yen (`JPY`, `¥`) from foreign e-commerce platforms (AliExpress Global, Amazon UK/JP) are not comprehensively covered in integration tests.
   - **Remediation**: Add dedicated test fixtures validating parsing of Asian and European currency symbols, non-standard decimal formats (e.g., European comma vs dot separators), and multi-currency JSON-LD pricing.

3. **Explicit Timeout Verification in Test Suite**:
   - **Status**: **VERIFIED NON-BLOCKER**. All test modules adhere strictly to the timeout policy; [`tests/test_metadata_extractor_service.py`](file:///home/src/tests/test_metadata_extractor_service.py#L32) explicitly sets `pytestmark = pytest.mark.timeout(30)`, preventing hung test processes.

## Performance Concerns

1. **Synchronous BeautifulSoup DOM Construction on 2MB HTML Payloads**:
   - **Context**: [`HtmlMetadataExtractor.extract`](file:///home/src/wishenka/items/parser.py#L199) parses HTML documents up to the 2MB safety limit synchronously using `BeautifulSoup(html, "html.parser")` on the main asyncio event loop.
   - **Impact**: Parsing a complex 2MB HTML document with deep DOM hierarchies can consume 20–60 ms of CPU time. Under high concurrent user traffic, this synchronous processing holds Python's GIL and stalls asynchronous event loop scheduling, increasing response latency for other concurrent HTTP requests.
   - **Cross-Reference**: Tracked in **DEBT-1 ([WISHENKA-52](https://pypost.atlassian.net/browse/WISHENKA-52))** — *Non-blocking HTML parsing with threadpool or high-performance parser* (2.0 Story Points).

2. **Ephemeral HTTP Client Connection Overhead**:
   - **Context**: When an external client is not injected into [`ItemPreviewService.fetch_preview`](file:///home/src/wishenka/items/service.py#L40), an ad-hoc `httpx.AsyncClient` is created and torn down per request.
   - **Impact**: Each preview request requires establishing fresh TCP connections, TLS handshakes, and DNS queries, adding 150–350 ms of network latency per external URL scrape.
   - **Cross-Reference**: Tracked in **DEBT-2 ([WISHENKA-53](https://pypost.atlassian.net/browse/WISHENKA-53))** — *Persistent HTTP client pool and preview cache* (3.0 Story Points).

## Follow-up Tasks

- **DEBT-1: Non-blocking HTML parsing with threadpool or high-performance parser**
  - *Jira Issue*: [WISHENKA-52](https://pypost.atlassian.net/browse/WISHENKA-52) (2.0 Story Points)
  - *Description*: Offload [`HtmlMetadataExtractor.extract`](file:///home/src/wishenka/items/parser.py#L199) to a background worker thread via `asyncio.to_thread` or evaluate lightweight C-based parsers (`selectolax`/`lexbor` or `lxml`) to eliminate asyncio event loop blocking on 2MB payloads.
  - *Priority*: Medium
  - *Target Epic*: WISHENKA-10

- **DEBT-2: Persistent HTTP client pool and preview cache**
  - *Jira Issue*: [WISHENKA-53](https://pypost.atlassian.net/browse/WISHENKA-53) (3.0 Story Points)
  - *Description*: Provide an application-scoped singleton `httpx.AsyncClient` with connection pooling, keep-alive, and an LRU/TTL cache to prevent duplicate outbound scrapes and eliminate TLS handshake overhead.
  - *Priority*: Medium
  - *Target Epic*: WISHENKA-10

- **DEBT-6: Config-driven marketplace rules and tracking parameter configuration**
  - *Jira Issue*: [WISHENKA-96](https://pypost.atlassian.net/browse/WISHENKA-96) (5.0 Story Points)
  - *Description*: Extract hardcoded tracking keys ([`TRACKING_QUERY_PREFIXES`](file:///home/src/wishenka/items/marketplaces.py#L11), [`TRACKING_QUERY_KEYS`](file:///home/src/wishenka/items/marketplaces.py#L12)) and marketplace rules into external YAML/JSON configuration files with hot-reloading support, allowing operational rule updates without codebase redeployment.
  - *Priority*: Low
  - *Target Epic*: WISHENKA-10

- **DEBT-7: VCR.py / Web cassette recording harness for real marketplace regression tests**
  - *Jira Issue*: [WISHENKA-97](https://pypost.atlassian.net/browse/WISHENKA-97) (3.0 Story Points)
  - *Description*: Implement automated cassette recording (`vcrpy` or `pytest-recording`) with periodically refreshed cassettes against live marketplace product pages (Ozon, Wildberries, Yandex Market, Avito, Megamarket) to detect upstream layout updates and anti-bot signature drift.
  - *Priority*: Low
  - *Target Epic*: WISHENKA-10

- **DEBT-8: International currency parsing & foreign e-commerce test suite**
  - *Jira Issue*: [WISHENKA-98](https://pypost.atlassian.net/browse/WISHENKA-98) (2.0 Story Points)
  - *Description*: Expand test coverage for international currency codes (`CNY`, `GBP`, `JPY`, `TRY`), localized formatting (European comma/dot decimal separators), and multi-currency JSON-LD pricing structures.
  - *Priority*: Low
  - *Target Epic*: WISHENKA-10

- **DEBT-9: Headless rendering fallback / worker for client-side hydrated SPA marketplaces**
  - *Jira Issue*: [WISHENKA-99](https://pypost.atlassian.net/browse/WISHENKA-99) (5.0 Story Points)
  - *Description*: Evaluate an asynchronous background worker pool or rendering gateway service for e-commerce sites rendering exclusively via client-side JavaScript / GraphQL with no initial SSR HTML/JSON-LD.
  - *Priority*: Low
  - *Target Epic*: WISHENKA-10

- **Pre-existing test failures**:
  - `None` (All 272 automated tests in the test suite pass with 0 errors).
