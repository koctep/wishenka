# WISHENKA-93: Technical Debt Analysis

## Shortcuts Taken

1. **Task-local `_active_policy_var` `ContextVar` side-channel for policy propagation (`wishenka/items/ssrf.py:76-79, 200-210, 846-867`; `wishenka/items/fetcher.py:97-98, 358-381`; `wishenka/items/service.py:153-155`)**:
   - `validate_url`, `UrlMetadataService._fetch_html`, `ItemPreviewService.fetch_preview` (`PreviewCache` revalidation), `SSRFSafeNetworkBackend.connect_tcp`, and `SSRFSafeTransport.handle_async_request` propagate the active `SSRFPolicy` through a task-local `ContextVar[SSRFPolicy | None]` (`_active_policy_var`) instead of passing `forbidden_networks` or `policy` as required parameters to `resolve_and_validate_host` and `_validate_request`.
   - **Trade-off (accepted by design)**: Preserves backwards compatibility with the two-argument `(host, port=80)` monkeypatch signature used across existing SSRF/preview test suites (`tests/test_ssrf_and_response_limits.py`, `tests/test_preview_supported_routes.py`, `tests/test_preview_resource_reuse.py`, `tests/test_marketplace_cassettes.py`) and HTTPX's single-argument `event_hooks={"request": [_validate_request]}` contract (also imported by `wishenka/items/cassettes.py:789`). Relies on `with _use_ssrf_policy(...):` (`try ... finally: reset(token)`) discipline and assumes callers do not combine a `UrlMetadataService(settings=A)` with an externally built `routes` transport configured for a different `settings=B` (in that mixed case, `_validate_request` reads `_active_policy_var` `A` while `SSRFSafeTransport` prefers its pinned `self._policy` `B`; production `create_app` constructs both from the same `settings`).

2. **Snapshot-cached `get_default_ssrf_policy()` keyed by `os.environ` + `Path.cwd() / ".env"` stat (`wishenka/items/ssrf.py:75, 82-104, 182-197`)**:
   - Zero-arg consumers (`ItemPreviewService()`, `UrlMetadataService()`, `SSRFSafeTransport()`, `is_ip_safe()`, `resolve_and_validate_host()`) resolve ambient defaults through `get_default_ssrf_policy()`, which caches a single `(signature, SSRFPolicy)` tuple keyed on `(WISHENKA_SSRF_MAX_RESPONSE_BYTES, WISHENKA_SSRF_ALLOWED_SCHEMES, WISHENKA_SSRF_FORBIDDEN_CIDRS, (cwd, .env st_mtime_ns, .env st_size))`.
   - **Trade-off (accepted by design)**: Enables runtime `monkeypatch.setenv` / `.env` overrides in tests and scripts to take effect immediately without manual cache invalidation, while avoiding full `Settings()` instantiation on cache hits. However, `_default_policy_cache` is an unsynchronized module global (safe under CPython's GIL in single-event-loop asyncio, not lock-protected for multi-threaded mutations), and `.env` tracking inspects only `Path.cwd() / ".env"` matching `SettingsConfigDict(env_file=".env")`.

3. **Static import-time module constants alongside dynamic `SSRFPolicy` (`wishenka/items/ssrf.py:34-41`; `wishenka/items/__init__.py:67-71`)**:
   - `MAX_RESPONSE_BYTES`, `ALLOWED_SCHEMES`, and `FORBIDDEN_NETWORKS` remain frozen at import time from `wishenka.config` defaults (`DEFAULT_SSRF_*`), while `SSRFPolicy` and zero-arg helpers evaluate runtime `WISHENKA_SSRF_*` overrides dynamically.
   - **Trade-off (accepted by design)**: Guarantees backward compatibility for callers importing those module constants directly, at the cost that code or monkeypatches targeting `ssrf.MAX_RESPONSE_BYTES` / `ssrf.ALLOWED_SCHEMES` / `ssrf.FORBIDDEN_NETWORKS` directly do not alter `SSRFPolicy`-based enforcement.

4. **Shared process-local `_dns_cache` across differing CIDR policies (`wishenka/items/ssrf.py:364, 529-564, 567`)**:
   - `_dns_cache` remains keyed by `(normalized_host, port)` to preserve the global 512-entry LRU capacity and 60s TTL, while `resolve_and_validate_host` re-validates every cached IP against `active_networks` on cache hit (raising `SSRFBlockedError` with `cache_revalidation=True` without evicting the entry) and keys `_in_flight_resolutions` by `(_normalize_dns_key(clean_host, port), active_networks)`.
   - **Trade-off (accepted by design)**: Prevents cross-policy cache poisoning and keeps memory bounded. Because blocked lookups are never negatively cached, a cold lookup that fails under a strict policy does not populate `_dns_cache` for a subsequent permissive policy, and two `Settings` instances listing the same CIDRs in different order use separate single-flight keys.

5. **Ambient-default callers in `wishenka/items/cassettes.py` (`lines 519, 736-766, 810`)**:
   - `CassetteTransport._get_or_create_inner_transport` instantiates `SSRFSafeTransport()` with no arguments, `_verify_all_reference_cassettes` instantiates `OfflineMetadataService()` / `ItemPreviewService(...)` with no `settings`/`policy`, and `_record_or_refresh_cassette` calls `UrlMetadataService()._stream_and_read(...)` with no `settings`/`policy`.
   - **Trade-off (low risk — developer/QA CLI tooling)**: Zero-arg constructors inherit ambient `WISHENKA_SSRF_*` env/`.env` overrides via `get_default_ssrf_policy()`, though CLI cassette helpers cannot be given an explicit `Settings` instance programmatically.

6. **Inherited private `httpcore` / `httpx` backend hook (`wishenka/items/ssrf.py:785-803`)**:
   - `SSRFSafeTransport.__init__` continues to install `SSRFSafeNetworkBackend` via `self._pool._network_backend` (failing closed if absent or replaced). Already tracked in Jira ([WISHENKA-284](https://pypost.atlassian.net/browse/WISHENKA-284)); do not duplicate.

7. **Transient per-request `ItemPreviewService` fallback in `wishenka/web/routes/items_ui.py:479-481`**:
   - When `request.app.state.item_preview_service` is absent, `preview_item_input` now constructs `ItemPreviewService(settings=getattr(request.app.state, "settings", None))` (`app.state.settings` is populated by `create_app` at `wishenka/web/app.py:248`). That fallback correctly enforces configured SSRF settings, though it creates an unpooled transient `ItemPreviewService` without `PreviewCache` (only reachable outside normal lifespan startup).

## Code Quality Issues

1. **Out-of-scope pre-existing defect surfaced in Step 6: `extract_domain` mishandles URL userinfo and bracketed IPv6 literals (`wishenka/items/parser.py:349-359`)**:
   - `extract_domain(url)` computes `urlsplit(url).netloc.lower().split(":")[0]` instead of `urlsplit(url).hostname` (followed by stripping `"www."`).
   - Verified behavior:
     - `extract_domain("https://alice:secret@shop.example.com/item")` returns `"alice"` (and `derive_store_name(...)` returns `"alice"`).
     - `extract_domain("https://alice@shop.example.com/item")` returns `"alice@shop.example.com"`.
     - `extract_domain("https://[::1]:8080/item")` returns `"["`.
   - Concrete cross-layer impact:
     - `UniversalInputClassifier.classify` (`wishenka/items/classifier.py:94-106`) logs `"url_domain": extract_domain(result.normalized_url)` in the `input_classified` debug event, leaking URL usernames into structured logs and forcing `tests/test_ssrf_configurable_settings.py:1471-1472` (`test_ssrf_observability_never_logs_url_credentials`) to skip `input_classified` records.
     - `UrlMetadataService.fetch_and_extract` (`wishenka/items/fetcher.py:517`) passes raw `url` (rather than `safe_url` computed at line 510) into `derive_store_name(url)`, setting `ExtractedMetadata(store_name="alice")` on credential-bearing fallback failures.
     - `ItemPreviewService.fetch_preview` (`wishenka/items/service.py:224, 251, 279, 301, 349, 373, 397, 435, 468, 495`) returns unredacted `url=target_url` in `ItemPreviewDTO`, and `wishenka/web/routes/items_ui.py:484` passes `preview.url or classification.normalized_url` into `extract_domain(...)` for the `INFO` `ui_item_quick_add_preview` log event.
     - `clean_url` (`wishenka/items/marketplaces.py:65`) and `MarketplaceRegistry.get_rule` (`wishenka/items/marketplaces.py:183`) also call `extract_domain`.
   - Verdict: `NON-BLOCKER` (outside WISHENKA-93 scope; proposed as a new `Debt` follow-up task below).

2. **Minor defensive credential-redaction and import polish (`NON-BLOCKER`, low risk)**:
   - `UrlMetadataService._fetch_html` (`wishenka/items/fetcher.py:480-491`, `url_fetch_success`) and `SSRFSafeTransport.handle_async_request` (`wishenka/items/ssrf.py:834-842`, `missing_host`, and `lines 853-863`, `ssrf_request_dispatch`) log raw `url` / `final_effective_url` / `str(request.url)` after credential rejection has already run, rather than applying `redact_url_credentials(...)` defensively.
   - `wishenka/items/fetcher.py` imports `SSRFBlockedError` locally inside `validate_url` (`line 79`), `_validate_request` (`line 105`), and `UrlMetadataService._fetch_html` (`line 333`) instead of at module top level (matching pre-existing style).
   - `wishenka/items/{ssrf,fetcher,service}.py` import `Settings` directly from `wishenka.config` for convenience; safe because `wishenka/config.py` has zero internal `wishenka.*` imports.

3. **Explicit pytest timeout markers verified (no `BLOCKER`)**:
   - Checked `tests/test_ssrf_configurable_settings.py` (`line 53`): declares module-level `pytestmark = pytest.mark.timeout(30)`.
   - Verified via `pytest --collect-only` marker inspection: `collected=99 missing_timeout=0 timeouts=[30]`.
   - Companion SSRF/preview suites (`tests/test_ssrf_and_response_limits.py`, `tests/test_ssrf_dns_rebinding.py`, `tests/test_dns_cache.py`, `tests/test_preview_supported_routes.py`, `tests/test_preview_resource_reuse.py`, `tests/test_item_observability.py`, `tests/test_observability.py`) all declare explicit `pytest.mark.timeout(...)` markers as well.

## Missing Tests

- **Verified in this Step 7 session**:
  - `PYTHONPATH=. .venv/bin/pytest tests/test_ssrf_configurable_settings.py -q`: **`99 passed, 1 warning in 16.42s`** (`99/99` collected with `timeout(30)`).
  - `make analyze`: Ruff check (`All checks passed!`), Ruff format check (`249 files already formatted`), Mypy (`Success: no issues found in 249 source files`).
  - Note on broader suite: Earlier step artifacts report a 337-test focused suite (`ai-tasks/WISHENKA-93/40-code-cleanup.md`) and a 165-test focused suite plus 3 tests in `tests/test_observability.py` (`ai-tasks/WISHENKA-93/50-observability.md`); separately, the Step 4 B2 review / orchestrator record reports a Step 4 full parallel suite run (`1950 passed, 2 skipped, 17 failed`, all 17 pre-existing failures tracked in Jira, listed below). Those broader suites and full `make test` were not re-executed in this read-only Step 7 session (full `make test PYTEST_JOBS=4` also remains subject to pre-existing `WISHENKA-283` / `WISHENKA-285` issues).

- **Minor untested edge-case branches (`NON-BLOCKER`, low risk)**:
  1. Direct `SSRFPolicy.__post_init__` invalid-argument checks (`max_response_bytes < 1`, empty `allowed_schemes`, unsupported scheme) and mutual-exclusion `ValueError` on `SSRFSafeTransport(settings=..., policy=...)`, `UrlMetadataService(settings=..., policy=...)`, `ItemPreviewService(settings=..., policy=...)`, and `UrlMetadataService(max_bytes=True)` (`bool` guard at `wishenka/items/fetcher.py:292`).
  2. Concurrent async task isolation of `_active_policy_var` across interleaved `ItemPreviewService(settings=A)` and `ItemPreviewService(settings=B)` coroutines, plus verifying `_active_policy_var.get() is None` after exceptions inside `_use_ssrf_policy`.
  3. `redact_url_credentials` edge cases (`[invalid-url]` fallback, username-only `https://user@example.com/`, and `Authorization` header rejection logging in `_validate_request` / `SSRFSafeTransport`).
  4. `ItemPreviewService(url_metadata_service=UrlMetadataService(settings=custom))` inheriting `url_metadata_service.policy` for `PreviewCache` revalidation (`wishenka/items/service.py:82-85`).
  5. `wishenka/items/cassettes.py` zero-arg origin transport / `_record_or_refresh_cassette` honoring `WISHENKA_SSRF_*` overrides.

## Performance Concerns

1. **Per-call `Path.cwd()` + `.env.stat()` check in `_current_ssrf_env_signature()` on un-scoped zero-arg calls (`wishenka/items/ssrf.py:82-104, 182-197`)**:
   - Whenever `is_ip_safe()`, `resolve_and_validate_host()`, `validate_url()`, `SSRFSafeTransport()`, `UrlMetadataService()`, or `ItemPreviewService()` is called without explicit `settings`/`policy` and outside `_use_ssrf_policy(...)`, `get_default_ssrf_policy()` performs `os.environ.get(...)` x3, `Path.cwd()`, and `(cwd / ".env").stat()` (`stat(2)` syscall) to verify cache freshness.
   - **Impact (`NON-BLOCKER`)**: Injected paths (`create_app`, `bot.__main__.run`, `ItemPreviewService(settings=...)`, `UrlMetadataService(settings=...)`, `SSRFSafeTransport(settings=...)`) and nested calls inside `with _use_ssrf_policy(active_policy):` read `self.policy` / `_active_policy_var` directly in memory and skip `get_default_ssrf_policy()` completely. Only standalone un-scoped zero-arg calls incur the microsecond-level `stat(2)` check.

2. **Cache-miss `Settings()` construction and double CIDR parsing (`wishenka/items/ssrf.py:63-72, 189`)**:
   - On `_default_policy_cache` miss or `SSRFPolicy.from_settings(None)`, instantiating `Settings()` validates all ~45 unrelated application configuration fields and parses `.env`, and `from_settings` calls `ipaddress.ip_network(cidr, strict=False)` across `ssrf_forbidden_cidrs` (which `Settings._validate_ssrf_forbidden_cidrs` already parsed once). Because steady-state cache hit rate is ~100% and explicit `Settings` entrypoints build `SSRFPolicy` once at startup, runtime impact is negligible (`NON-BLOCKER`).

3. **Linear CIDR scan `O(N)` per IP check and warm `DNSCache` revalidation (`wishenka/items/ssrf.py:251, 531-532`)**:
   - `_is_ip_safe_for_networks` checks `ip in net` sequentially across `active_networks` for every resolved IP and every warm `DNSCache` hit. Negligible for the 20 default CIDRs (`NON-BLOCKER`); only relevant if an operator configures thousands of custom CIDR ranges.

## Follow-up Tasks

### New Unticketed Follow-up Tasks

- **`NON-BLOCKER` — Priority: Medium — Parent: `WISHENKA-10`**
  - **Title**: `Fix extract_domain userinfo/IPv6 parsing and sanitize raw fallback URLs in items domain`
  - **Jira**: [WISHENKA-286](https://pypost.atlassian.net/browse/WISHENKA-286) (3.0 Story Points)
  - **Description**:
    Surfaced during WISHENKA-93 Step 6/7 (`ai-tasks/WISHENKA-93/50-observability.md`). `extract_domain` (`wishenka/items/parser.py:349-359`) parses `urlsplit(url).netloc.lower().split(":")[0]` instead of `urlsplit(url).hostname` (plus `"www."` stripping). When given URLs with embedded credentials (`https://user:pass@shop.example.com/item`), username-only userinfo (`https://user@shop.example.com/item`), or bracketed IPv6 literals (`https://[::1]:8080/item`), it returns `"user"`, `"user@shop.example.com"`, or `"["` respectively instead of the hostname.

    This causes:
    1. `UniversalInputClassifier.classify` (`wishenka/items/classifier.py:94-106`) to emit userinfo usernames in `"url_domain"` of `input_classified` debug logs (requiring `tests/test_ssrf_configurable_settings.py:1471-1472` to exclude `input_classified` during credential-leak assertions).
    2. `UrlMetadataService.fetch_and_extract` (`wishenka/items/fetcher.py:517`) to call `derive_store_name(url)` with raw `url` instead of `safe_url` (line 510), producing `ExtractedMetadata(store_name="<username>")` on fallback.
    3. `ItemPreviewService.fetch_preview` (`wishenka/items/service.py:224, 251, 279, 301, 349, 373, 397, 435, 468, 495`) to keep raw `target_url` on `ItemPreviewDTO.url`, which `wishenka/web/routes/items_ui.py:484` passes to `extract_domain(...)` for the `INFO` `ui_item_quick_add_preview` log event.

    **Scope / Remediation**:
    - Update `extract_domain` (`wishenka/items/parser.py:349-359`) to extract `urlsplit(url).hostname` (handling `ValueError` safely and stripping leading `"www."`).
    - Pass `safe_url` to `derive_store_name` in `UrlMetadataService.fetch_and_extract` (`wishenka/items/fetcher.py:517`) and redact credentials on fallback/returned preview URLs or UI domain extraction as appropriate.
    - Remove the `input_classified` exclusion in `tests/test_ssrf_configurable_settings.py:1471-1472` and add unit tests for `user:pass@host`, `user@host`, and bracketed IPv6 URLs in `extract_domain` / `derive_store_name`.

### Intentionally Not Ticketed (Accepted Trade-offs / Low-Risk Polish)

- Accepted by design / low risk (no ticket required): `_active_policy_var` `ContextVar` preservation of 2-arg `resolve_and_validate_host` monkeypatches, `_default_policy_cache` env/`.env` snapshot check, import-time `MAX_RESPONSE_BYTES` / `ALLOWED_SCHEMES` / `FORBIDDEN_NETWORKS` constants, shared `_dns_cache` with hit-time revalidation, ambient zero-arg `cassettes.py` helpers, defensive `redact_url_credentials` on post-check `url_fetch_success` / `ssrf_request_dispatch` logs, and minor edge-case boundary test gaps noted above.

### Already-Tracked Pre-existing / Related Issues (Do NOT Duplicate)

- **`NON-BLOCKER` — `WISHENKA-284`** (`already tracked`): Remove private `_pool._network_backend` hook in `wishenka/items/ssrf.py`. Jira: [WISHENKA-284](https://pypost.atlassian.net/browse/WISHENKA-284)
- **`NON-BLOCKER` — [WISHENKA-95](https://pypost.atlassian.net/browse/WISHENKA-95), [WISHENKA-230](https://pypost.atlassian.net/browse/WISHENKA-230)** (`already tracked` in Sprint 2117): Expanded IPv6/redirect-chain SSRF tests and `SSRFSafeNetworkBackend.connect_tcp` edge-case unit tests.
- **`NON-BLOCKER — pre-existing` — [WISHENKA-283](https://pypost.atlassian.net/browse/WISHENKA-283), [WISHENKA-285](https://pypost.atlassian.net/browse/WISHENKA-285)** (`already tracked`):
  - [WISHENKA-283](https://pypost.atlassian.net/browse/WISHENKA-283) (`NON-BLOCKER — pre-existing`): Intermittent parallel `tests/test_i18n_unit.py` failures:
    - `tests/test_i18n_unit.py::test_anonymous_share_and_invite_locale_priority_chain`
    - `tests/test_i18n_unit.py::test_reminders_fallback_to_en_for_missing_user_locale_and_legacy_schema`
    - `tests/test_i18n_unit.py::test_miniapp_js_localizes_home_nav_shell_and_settings_label`
  - [WISHENKA-285](https://pypost.atlassian.net/browse/WISHENKA-285) (`NON-BLOCKER — pre-existing`): `make test PYTEST_JOBS=4` 600-second wall-limit timeout.
- **`NON-BLOCKER — pre-existing`** (17 failures observed in Step 4 full parallel suite `1950 passed, 2 skipped, 17 failed` per Step 4 B2 review / orchestrator record, all already filed in Jira — do not duplicate):
  - [WISHENKA-264](https://pypost.atlassian.net/browse/WISHENKA-264) (8 tests in `tests/test_items_ui_error_mapping.py`):
    - `tests/test_items_ui_error_mapping.py::test_archived_wishlist_gives_409[archive-confirm]`
    - `tests/test_items_ui_error_mapping.py::test_archived_wishlist_gives_409[archive]`
    - `tests/test_items_ui_error_mapping.py::test_unknown_wishlist_gives_404[archive-confirm]`
    - `tests/test_items_ui_error_mapping.py::test_unknown_wishlist_gives_404[archive]`
    - `tests/test_items_ui_error_mapping.py::test_non_member_gives_404[archive-confirm]`
    - `tests/test_items_ui_error_mapping.py::test_non_member_gives_404[archive]`
    - `tests/test_items_ui_error_mapping.py::test_unknown_item_gives_404[archive-confirm]`
    - `tests/test_items_ui_error_mapping.py::test_unknown_item_gives_404[archive]`
  - [WISHENKA-235](https://pypost.atlassian.net/browse/WISHENKA-235) (2 tests — anonymous share projection):
    - `tests/test_wish_card_giver_controls.py::test_anonymous_share_shows_availability_without_a_book_control`
    - `tests/test_surprise_role_context.py::test_share_link_visit_creates_no_account`
  - [WISHENKA-220](https://pypost.atlassian.net/browse/WISHENKA-220) (`tests/test_receipt_modal_browser.py::test_unmarked_error_neither_shows_notice_nor_reloads`)
  - [WISHENKA-226](https://pypost.atlassian.net/browse/WISHENKA-226) (`tests/test_wishlists_htmx_observability.py::test_wishlist_shared_view_observability`)
  - [WISHENKA-232](https://pypost.atlassian.net/browse/WISHENKA-232) (`tests/test_gift_receipt_migration.py::test_upgrade_is_repeatable`)
  - [WISHENKA-245](https://pypost.atlassian.net/browse/WISHENKA-245) (`tests/test_receipt_notices_extra.py::test_cleanup_cycle_survives_a_failing_notice_purge`)
  - [WISHENKA-265](https://pypost.atlassian.net/browse/WISHENKA-265) (`tests/test_receipt_modal_browser.py::test_stale_giver_card_is_neutral`)
  - [WISHENKA-266](https://pypost.atlassian.net/browse/WISHENKA-266) (`tests/test_receipt_theme_browser.py::test_receipt_text_has_readable_contrast[dark]`)
  - [WISHENKA-267](https://pypost.atlassian.net/browse/WISHENKA-267) (`tests/test_wishlist_htmx_smoke_browser.py::test_real_htmx_move_button_with_cookie_and_csrf`)
