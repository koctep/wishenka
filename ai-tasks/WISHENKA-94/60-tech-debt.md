# WISHENKA-94: Technical Debt Analysis

## Shortcuts Taken

1. **Module-level singleton `_dns_cache = DNSCache()` with constant defaults** (`wishenka/items/ssrf.py:24-25`, `164`):
   - `DNSCache` accepts `capacity` and `ttl` constructor parameters, and the module instantiates `_dns_cache = DNSCache()` with `DEFAULT_DNS_CACHE_TTL_SECONDS = 60.0` and `DEFAULT_DNS_CACHE_CAPACITY = 512`.
   - Because `resolve_and_validate_host(host, port)` is a module-level function invoked directly by `validate_url`, `UrlMetadataService._fetch_html`, `SSRFSafeTransport.handle_async_request`, and `SSRFSafeNetworkBackend.connect_tcp`, the cache is process-local rather than injected from Pydantic `Settings` or `app.state`.
   - **Trade-off**: Keeps the existing function signature (`resolve_and_validate_host(host, port)`) backwards-compatible across all callers and tests, at the cost of requiring an `autouse` fixture (`_clear_dns_cache` in `tests/conftest.py:143-151`) to reset `_dns_cache` between tests. Configurable SSRF and DNS parameters via Pydantic `Settings` is already tracked in Jira as an open Sprint 2117 ticket ([WISHENKA-93](https://pypost.atlassian.net/browse/WISHENKA-93)).

2. **Port-scoped DNS cache and single-flight key `(normalized_host, port)`** (`wishenka/items/ssrf.py:93-95`):
   - `_normalize_dns_key(host, port)` includes `port` in the key tuple `(host.strip("[]").lower().rstrip("."), port)` because `loop.getaddrinfo(clean_host, port, proto=socket.IPPROTO_TCP)` takes `port`.
   - **Trade-off**: Since `resolve_and_validate_host` strips the port from the returned `sockaddr` tuple and caches only `ip_str = str(sockaddr[0])`, an `http://shop.example.com` (`:80`) request that redirects to `https://shop.example.com` (`:443`) performs two DNS lookups (one for port 80 and one for port 443) instead of sharing a single host-only entry. In practice, this costs at most one extra lookup per HTTP-to-HTTPS redirect domain per 60-second TTL window (`NON-BLOCKER`).

## Code Quality Issues

1. **Single-flight leader cancellation propagates to waiting followers** (`wishenka/items/ssrf.py:330-374`):
   - Follower coroutines await `asyncio.shield(existing_future)` (`wishenka/items/ssrf.py:341`), so cancelling a follower does not cancel the shared `existing_future` or affect other callers.
   - However, the leader coroutine awaits `_resolve_and_validate_uncached(host, clean_host, port)` directly (`wishenka/items/ssrf.py:356`). If the leader coroutine itself is cancelled while followers are awaiting `existing_future`, the leader's `except BaseException:` handler (`wishenka/items/ssrf.py:362-365`) cancels `future`, propagating `CancelledError` to waiting followers even though the followers were not cancelled.
   - **Impact**: Low (`NON-BLOCKER`) — only occurs if the very first request in a concurrent cold-cache burst for the exact same uncached domain is cancelled mid-DNS-resolution, and `_in_flight_resolutions` is always cleaned up in `finally` so the next request succeeds cleanly.

2. **Explicit pytest timeout markers verified**:
   - `tests/test_dns_cache.py` declares `pytestmark = pytest.mark.timeout(30)` at module level (line 22), and the companion SSRF test suites (`tests/test_ssrf_and_response_limits.py` and `tests/test_ssrf_dns_rebinding.py`) also carry `pytestmark = pytest.mark.timeout(30)`. There are no missing timeout-marker blockers.

## Missing Tests

All core requirements (TTL hit, case and trailing-dot normalization, caller list-mutation isolation, TTL expiry with SSRF re-validation, prohibition of negative caching for `SSRFBlockedError` and `socket.gaierror`, LRU eviction at capacity 512, concurrent single-flight coalescing, and structured `DEBUG` log events) are covered in `tests/test_dns_cache.py`.

Minor edge-case branches without dedicated unit tests (`NON-BLOCKER`):

1. **Single-flight failure and cancellation propagation to follower coroutines**:
   - `test_dns_cache_coalesces_concurrent_misses_single_flight` verifies concurrent cold-cache hits when the leader succeeds. There is no unit test verifying that when the leader's `getaddrinfo` call raises `SSRFBlockedError` (or is cancelled), all coalesced followers receive the exception and subsequent calls start a fresh resolution after the `finally` cleanup.
2. **Direct `DNSCache` disabled-boundary guards (`capacity <= 0` or `ttl <= 0`)**:
   - `DNSCache.put` includes a guard `if not ips or self.capacity <= 0 or self.ttl <= 0: return` (`wishenka/items/ssrf.py:134`) that is not directly exercised with `DNSCache(capacity=0)` or `DNSCache(ttl=0.0)`.

## Performance Concerns

1. **Lazy TTL expiration in `DNSCache`** (`wishenka/items/ssrf.py:116-128`, `142-154`):
   - Expired entries are removed lazily on the next `DNSCache.get(host, port)` for the same key, or evicted in `DNSCache.put` via `popitem(last=False)` when `len(self._entries) > self.capacity`.
   - There is no background sweep task, which avoids timer overhead, and memory usage is strictly upper-bounded by `DEFAULT_DNS_CACHE_CAPACITY = 512` immutable `DNSCacheEntry` tuples (a few kilobytes total).
   - **Note**: Under an extreme burst of more than 512 distinct uncached domains within 60 seconds, `DNSCache.put` evicts the least-recently-used entry (`popitem(last=False)`) even if a more recently accessed entry happened to have an earlier `expires_at` (not possible when all entries share the same `self.ttl`, since insertion/update order with a uniform TTL is monotonic with `expires_at`).

## Follow-up Tasks

New and related SSRF/DNS follow-up items:

- **Configurable SSRF and DNS settings via Pydantic `Settings`** (`NON-BLOCKER` — already tracked in Sprint 2117):
  Expose SSRF and DNS policy parameters in application settings (`wishenka/config.py`) as planned in the existing backlog story.
  Jira: [WISHENKA-93](https://pypost.atlassian.net/browse/WISHENKA-93)
- `NON-BLOCKER`: **Add single-flight error/cancellation propagation and `DNSCache` zero-capacity/zero-TTL boundary unit tests in `tests/test_dns_cache.py` (and optionally shield single-flight leader resolution from leader task cancellation)** — Priority: Low.
  Jira: [WISHENKA-279](https://pypost.atlassian.net/browse/WISHENKA-279)
- `NON-BLOCKER`: **Consider host-only cache keying in `DNSCache`** (`normalized_host` without `port`) so `http://` (`:80`) to `https://` (`:443`) redirects to the same hostname reuse the validated IP list without a second `getaddrinfo` lookup — Priority: Low.
  Jira: [WISHENKA-280](https://pypost.atlassian.net/browse/WISHENKA-280)

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
