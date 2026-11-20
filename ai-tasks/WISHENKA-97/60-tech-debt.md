# WISHENKA-97: Technical Debt Analysis

## Shortcuts Taken

1. **Direct seeding of the module-level `_dns_cache` singleton with `SAFE_REPLAY_PUBLIC_IP = "93.184.216.34"`** (`wishenka/items/cassettes.py:33`, `518-524`, `627-630`, `759-763`):
   - In `CassetteMode.REPLAY` (and when a custom `inner_transport` is provided for mock-origin tests), `CassetteTransport._seed_dns_cache_for_recorded_hosts` pre-populates the shared module-level `_dns_cache` (`wishenka/items/ssrf.py`) with `SAFE_REPLAY_PUBLIC_IP = "93.184.216.34"` for every recorded host/port pair in the cassette.
   - **Trade-off**: This allows `UrlMetadataService._fetch_html` and `_validate_request` to execute the real `resolve_and_validate_host` SSRF validation pipeline completely offline without performing live `loop.getaddrinfo` DNS lookups or monkeypatching `resolve_and_validate_host`. However, it mutates the process-local `_dns_cache` singleton, relying on the `autouse` `_clear_dns_cache` fixture in `tests/conftest.py` (or explicit `clear_dns_cache()` calls) to isolate DNS state between tests (`NON-BLOCKER`).

2. **Substring-based heuristic for sensitive header and query-parameter stripping** (`wishenka/items/cassettes.py:55-63`, `108-113`, `160-169`):
   - In addition to the explicit `SENSITIVE_HEADER_NAMES` and `SENSITIVE_QUERY_KEYS` sets, `_is_sensitive_header` and `sanitize_uri` strip any header or query key containing substrings such as `"cookie"`, `"token"`, `"secret"`, `"auth"`, `"session"`, `"api-key"`, `"apikey"`, or `"password"`.
   - **Trade-off**: This fail-safe heuristic guarantees that vendor-specific authentication headers or tokens (e.g., `X-Ozon-Auth-Token`, `X-WB-Session-Cookie`, `avito_secret_key`) cannot accidentally leak into committed YAML cassettes (US-4). A minor side effect is that if a marketplace ever used a benign product query parameter containing one of those substrings (e.g., `author=...` matching `"auth"`), `sanitize_uri` would strip it (`NON-BLOCKER`).

3. **Substring matching in `CHALLENGE_SIGNATURES` across full lowercased HTML** (`wishenka/items/service.py:31-55`, `436-441`):
   - `ItemPreviewService._is_challenge` checks `any(sig in lowered for sig in CHALLENGE_SIGNATURES)` against the entire lowercased HTML document, now expanded with Russian anti-bot markers (`"доступ ограничен"`, `"доступ временно ограничен"`, `"почти готово"`, `"проверка браузера"`, `"подтвердите, что запросы отправляли вы, а не робот"`, `"smartcaptcha"`, `"showcaptcha"`, `"firewall-container"`, `"antibot-challenge"`, `"ozon-captcha"`, `"fab_chlg"`).
   - **Trade-off**: Simple and fast ($O(N)$ scan over at most 2 MB of HTML), reliably catching 200 OK and 403/429/503 Russian anti-bot challenge screens across Ozon, Wildberries, Yandex Market, Avito, and Megamarket. However, generic phrases like `"почти готово"` or `"доступ ограничен"` could theoretically trigger a false-positive `anti_bot_challenge` fallback if a normal product description or user review on the page contained that exact substring (`NON-BLOCKER`).

## Code Quality Issues

1. **Sequential linear scan in `Cassette.find_interaction`** (`wishenka/items/cassettes.py:445-461`):
   - `Cassette.find_interaction(method, uri)` iterates through `self.interactions` and calls `sanitize_uri(recorded_uri)` and `clean_url(recorded_uri)` on each entry until a match is found.
   - **Impact**: Negligible for marketplace cassettes (`NON-BLOCKER`), as each reference cassette contains 1–2 interactions (a single GET request or a redirect chain). If multi-hundred-interaction cassettes were introduced in the future, pre-indexing interactions by `(method, sanitized_uri)` on load/add would avoid repeated URI parsing.

2. **Single-URL refresh assumption in `_verify_all_reference_cassettes` and `_refresh_all_cassettes`** (`wishenka/items/cassettes.py:735`, `791`):
   - Both directory-level CLI helpers read `target_uri = cassette.interactions[0].request.uri` as the entrypoint URL for `ItemPreviewService.fetch_preview(target_uri, client=client)`.
   - **Impact**: Low (`NON-BLOCKER`) — matches the standard one-URL-per-cassette convention (`<marketplace>_<scenario>.yaml`) and supports multi-hop HTTP redirect chains starting from `interactions[0]`, though a cassette bundling multiple unrelated product URLs in a single file would only verify/refresh the first entry via the batch directory CLI.

3. **Explicit pytest timeout markers verified**:
   - `tests/test_marketplace_cassettes.py` declares `pytestmark = pytest.mark.timeout(15)` at module level (line 35) per `do-testing` and `lsr-python` requirements. There are no missing timeout-marker blockers.

## Missing Tests

All core requirements from `10-requirements.md` and `20-architecture.md` (10 reference cassettes for Ozon, Wildberries, Yandex Market, Avito, and Megamarket across `product` and `antibot` scenarios; offline `REPLAY` without live DNS/network calls; 200 OK and 403/503 Russian anti-bot challenge detection without title leakage; `COMPOSITE_SHARE` residual text preservation; fail-closed `CassetteMissError` propagation; `RECORD`/`REFRESH` header, cookie, IP, and query token sanitization; CLI `--mode record|refresh` and `--verify`; and structured logging observability) are covered by 19 test items in `tests/test_marketplace_cassettes.py`.

Minor edge-case branches without dedicated unit tests (`NON-BLOCKER`):

1. **Multi-hop HTTP redirect chain recording and offline replay in a single cassette**:
   - While `cassette_client` sets `follow_redirects=True` and `Cassette` stores an ordered list of `interactions`, there is no dedicated test in `tests/test_marketplace_cassettes.py` exercising a 301/302 short-link redirect (e.g., `ozon.ru/t/...` $\rightarrow$ `ozon.ru/product/...`) recorded as two interactions in one YAML cassette and replayed end-to-end.
2. **Error handling for malformed YAML cassettes and invalid CLI arguments**:
   - Error branches such as `resolve_cassette_mode("invalid")` raising `CassetteError`, `Cassette.load` on corrupt YAML or non-mapping root structures (`wishenka/items/cassettes.py:353-360`, `399-400`), and CLI `parser.error` when `--url` is passed without `--output` (`wishenka/items/cassettes.py:863-864`) are not covered by dedicated negative unit tests.

## Performance Concerns

1. **Full synchronous YAML load and save on every recorded interaction** (`wishenka/items/cassettes.py:391-443`, `624-625`):
   - `Cassette.load` uses `yaml.safe_load` and `Cassette.save` uses `yaml.safe_dump` synchronously on the event loop thread when `CassetteTransport.handle_async_request` records or refreshes an interaction.
   - **Impact**: `CassetteMode.REPLAY`, `RECORD`, and `REFRESH` are testbench and QA audit tools rather than production user-traffic paths. Replaying all 10 reference marketplace cassettes in `tests/test_marketplace_cassettes.py` completes in ~0.35 seconds total (`NON-BLOCKER`).

## Follow-up Tasks

New follow-up items identified during WISHENKA-97 technical debt analysis:

- `NON-BLOCKER`: **Refine `sanitize_uri` sensitive query key matching and scope Russian HTML anti-bot challenge signatures to `<title>` / challenge containers** — Avoid substring false positives on benign query keys (such as `author` matching `"auth"`) by using token/boundary matching in `sanitize_uri`, and tighten generic text signatures (`"почти готово"`, `"доступ ограничен"`) in `ItemPreviewService._is_challenge` so normal product descriptions containing those phrases cannot trigger a false-positive `anti_bot_challenge` fallback — Priority: Low.
  Jira: [WISHENKA-282](https://pypost.atlassian.net/browse/WISHENKA-282)
- `NON-BLOCKER`: **Add unit tests for multi-hop redirect cassette replay and malformed cassette / CLI error branches in `tests/test_marketplace_cassettes.py`** — Cover 301/302 redirect chains across multiple cassette interactions, invalid `CassetteMode` values, corrupt YAML structures, and mismatched CLI `--url`/`--output` flags — Priority: Low.
  Jira: [WISHENKA-281](https://pypost.atlassian.net/browse/WISHENKA-281)

Related backlog items already tracked in Jira (do not duplicate):

- **Externalize marketplace rules, tracking query parameters, and challenge signatures into configuration** (`NON-BLOCKER` — out of scope per `10-requirements.md`, already tracked in backlog):
  Jira: [WISHENKA-96](https://pypost.atlassian.net/browse/WISHENKA-96)

Pre-existing unrelated test failures (`NON-BLOCKER — pre-existing`, 17 total across the full test suite, already tracked in Jira — do not duplicate):

- `NON-BLOCKER — pre-existing` — Archive response mapping ([WISHENKA-264](https://pypost.atlassian.net/browse/WISHENKA-264)):
  - `tests/test_items_ui_error_mapping.py::test_archived_wishlist_gives_409[archive-confirm]`
  - `tests/test_items_ui_error_mapping.py::test_archived_wishlist_gives_409[archive]`
  - `tests/test_items_ui_error_mapping.py::test_unknown_wishlist_gives_404[archive-confirm]`
  - `tests/test_items_ui_error_mapping.py::test_unknown_wishlist_gives_404[archive]`
  - `tests/test_items_ui_error_mapping.py::test_non_member_gives_404[archive-confirm]`
  - `tests/test_items_ui_error_mapping.py::test_non_member_gives_404[archive]`
  - `tests/test_items_ui_error_mapping.py::test_unknown_item_gives_404[archive-confirm]`
  - `tests/test_items_ui_error_mapping.py::test_unknown_item_gives_404[archive]`
- `NON-BLOCKER — pre-existing` — Stale giver card ([WISHENKA-265](https://pypost.atlassian.net/browse/WISHENKA-265)):
  - `tests/test_receipt_modal_browser.py::test_stale_giver_card_is_neutral`
- `NON-BLOCKER — pre-existing` — Dark theme contrast ([WISHENKA-266](https://pypost.atlassian.net/browse/WISHENKA-266)):
  - `tests/test_receipt_theme_browser.py::test_receipt_text_has_readable_contrast[dark]`
- `NON-BLOCKER — pre-existing` — HTMX move and CSRF ([WISHENKA-267](https://pypost.atlassian.net/browse/WISHENKA-267)):
  - `tests/test_wishlist_htmx_smoke_browser.py::test_real_htmx_move_button_with_cookie_and_csrf`
- `NON-BLOCKER — pre-existing` — Shared-view observability ([WISHENKA-226](https://pypost.atlassian.net/browse/WISHENKA-226)):
  - `tests/test_wishlists_htmx_observability.py::test_wishlist_shared_view_observability`
- `NON-BLOCKER — pre-existing` — Anonymous public projection ([WISHENKA-235](https://pypost.atlassian.net/browse/WISHENKA-235)):
  - `tests/test_surprise_role_context.py::test_share_link_visit_creates_no_account`
  - `tests/test_wish_card_giver_controls.py::test_anonymous_share_shows_availability_without_a_book_control`
- `NON-BLOCKER — pre-existing` — Gift receipt migration repeatability ([WISHENKA-232](https://pypost.atlassian.net/browse/WISHENKA-232)):
  - `tests/test_gift_receipt_migration.py::test_upgrade_is_repeatable`
- `NON-BLOCKER — pre-existing` — Unmarked browser error ([WISHENKA-220](https://pypost.atlassian.net/browse/WISHENKA-220)):
  - `tests/test_receipt_modal_browser.py::test_unmarked_error_neither_shows_notice_nor_reloads`
- `NON-BLOCKER — pre-existing` — Notice cleanup error handling ([WISHENKA-245](https://pypost.atlassian.net/browse/WISHENKA-245)):
  - `tests/test_receipt_notices_extra.py::test_cleanup_cycle_survives_a_failing_notice_purge`
