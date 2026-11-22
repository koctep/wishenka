# WISHENKA-93: Observability Implementation

## Logging Implementation

### Added Logs

Structured logging audited and enhanced across [`wishenka/config.py`](file:///home/src/wishenka/config.py), [`wishenka/items/ssrf.py`](file:///home/src/wishenka/items/ssrf.py), [`wishenka/items/fetcher.py`](file:///home/src/wishenka/items/fetcher.py), [`wishenka/items/service.py`](file:///home/src/wishenka/items/service.py), and [`wishenka/web/app.py`](file:///home/src/wishenka/web/app.py) (loggers `wishenka.items` and `wishenka.web`, compatible with [`JsonFormatter`](file:///home/src/wishenka/logging.py)):

- **EMERG**: N/A — Configurable SSRF policy validation and outbound preview protections fail fast at startup or degrade gracefully per request without system-wide emergencies.
- **ALERT**: N/A — No immediate operator paging triggers originate in the SSRF policy configuration or preview fetch layer.
- **CRIT**: N/A — Invalid configuration fails fast with `pydantic.ValidationError` prior to serving traffic; runtime blocks fall back safely.
- **ERR**: [`wishenka/items/service.py`](file:///home/src/wishenka/items/service.py) (`ItemPreviewService.fetch_preview`) — Existing `event="item_metadata_parsing_error"` on unexpected HTML extraction failures.
- **WARNING**:
  - [`wishenka/items/ssrf.py`](file:///home/src/wishenka/items/ssrf.py) (`_resolve_and_validate_uncached`, `resolve_and_validate_host`, `event="ssrf_blocked"`): IP/CIDR rejections (`reason="forbidden_ip"`) now include bounded `forbidden_cidr_count` (never dumping full CIDR lists) and `cache_revalidation=True` when a warm `DNSCache` hit violates the caller's active CIDR policy.
  - [`wishenka/items/ssrf.py`](file:///home/src/wishenka/items/ssrf.py) (`SSRFSafeTransport.handle_async_request`, `event="ssrf_blocked"`): Emits `ssrf_blocked` for unsafe/replaced backends (`reason="unsafe_backend"`), URL credentials/`Authorization` headers (`log_ssrf_credentials_blocked`, `reason="credentials"` with `host` only), and disallowed schemes (`log_ssrf_invalid_scheme`, `reason="invalid_scheme"`, `allowed_schemes`, credential-redacted `url`).
  - [`wishenka/items/fetcher.py`](file:///home/src/wishenka/items/fetcher.py) (`validate_url`, `_validate_request`, `UrlMetadataService._fetch_html`, `event="ssrf_blocked"`): Checks URL credentials before scheme checks and emits `ssrf_blocked` via `log_ssrf_credentials_blocked` (`reason="credentials"`) and `log_ssrf_invalid_scheme` (`reason="invalid_scheme"`, `allowed_schemes`, credential-redacted `url`) so direct `validate_url`, HTTPX redirect hooks, and `PreviewCache` revalidations emit consistent structured warnings.
  - [`wishenka/items/fetcher.py`](file:///home/src/wishenka/items/fetcher.py) (`UrlMetadataService._stream_and_read`, `fetch_and_extract`, `event="payload_size_violation"`, `event="fetch_and_extract_fallback"`): Uses `redact_url_credentials(url)` and records configured `max_allowed` (`self.max_bytes`), `content_length` / `streamed_bytes`, and `reason` (`"content_length_exceeded"` / `"stream_chunk_overflow"`).
  - [`wishenka/items/service.py`](file:///home/src/wishenka/items/service.py) (`ItemPreviewService.fetch_preview`):
    - `event="item_preview_ssrf_blocked"`: Enriched with `forbidden_cidr_count` and credential-redacted `url` / `url_domain`.
    - `event="item_preview_invalid_scheme"`: Enriched with `allowed_schemes`, `scheme`, `fallback_reason="ssrf_blocked"`, and credential-redacted `url`.
    - `event="item_preview_response_too_large"`: Records active `max_allowed`, `content_length`, `fallback_reason="response_too_large"`, and credential-redacted `url`.
- **NOTICE**: N/A — Python `logging` maps operational notifications to `INFO`/`WARNING`.
- **INFO**:
  - [`wishenka/web/app.py`](file:///home/src/wishenka/web/app.py) (`create_app` lifespan, `"Wishenka web application starting up"` on `wishenka.web`): Enriched with bounded SSRF startup metadata `ssrf_max_response_bytes`, `ssrf_allowed_schemes`, and `ssrf_forbidden_cidr_count` (omitting full CIDR sets and application secrets).
  - [`wishenka/items/ssrf.py`](file:///home/src/wishenka/items/ssrf.py) & [`wishenka/items/fetcher.py`](file:///home/src/wishenka/items/fetcher.py): Existing `event="dns_resolution_failed"` and `event="url_fetch_success"`.
- **DEBUG**:
  - [`wishenka/items/ssrf.py`](file:///home/src/wishenka/items/ssrf.py) (`get_default_ssrf_policy`, `event="ssrf_policy_loaded"`): Emitted via `log_ssrf_policy_event` when the ambient env/`.env` snapshot changes (`component="ssrf"`, `source="default_settings"`, `max_response_bytes`, `allowed_schemes`, `forbidden_cidr_count`).
  - [`wishenka/items/ssrf.py`](file:///home/src/wishenka/items/ssrf.py), [`wishenka/items/fetcher.py`](file:///home/src/wishenka/items/fetcher.py), [`wishenka/items/service.py`](file:///home/src/wishenka/items/service.py) (`event="ssrf_policy_configured"`): Emitted when `SSRFSafeTransport`, `UrlMetadataService`, or `ItemPreviewService` is initialized with explicit `settings`, `policy`, or `max_bytes`.
  - [`wishenka/items/ssrf.py`](file:///home/src/wishenka/items/ssrf.py) (`resolve_and_validate_host`, `event="dns_cache_hit"`): Enriched with `forbidden_cidr_count` confirming revalidation under active policy.
  - [`wishenka/items/ssrf.py`](file:///home/src/wishenka/items/ssrf.py) (`SSRFSafeNetworkBackend.connect_tcp`, `event="ssrf_pinned_cache_miss"`): Enriched with `policy_source` (`"pinned"`/`"ambient"`) and `forbidden_cidr_count`.
  - [`wishenka/items/service.py`](file:///home/src/wishenka/items/service.py) (`ItemPreviewService.fetch_preview`, `event="preview_cache_revalidation_evicted"`): Emitted when a cached preview entry is evicted after failing active `SSRFPolicy` revalidation (`url_domain`, `destination_count`).

### Log Structure

Log format used:

- Structured logs: yes (`extra={"event": ..., ...}` dictionary fields formatted as JSON via [`JsonFormatter`](file:///home/src/wishenka/logging.py) when `WISHENKA_LOG_JSON=true`, or standard formatted text in console mode).
- Includes context: yes (`event`, `component`, `source`, `max_response_bytes`, `ssrf_max_response_bytes`, `allowed_schemes`, `ssrf_allowed_schemes`, `forbidden_cidr_count`, `ssrf_forbidden_cidr_count`, `policy_source`, `cache_revalidation`, `destination_count`, `url_domain`, `host`, `ip`, `scheme`, `reason`, `content_length`, `streamed_bytes`, `max_allowed`, `duration_ms`, `fallback_reason`).
- Log levels: `DEBUG`, `INFO`, `WARNING`, `ERROR`.

## Metrics Implementation (if applicable)

### Performance Metrics

No Prometheus, StatsD, OpenTelemetry metrics exporter, or Grafana metrics collector exists in this repository (`pyproject.toml` and application entrypoints expose structured logs only; `opentelemetry-api` is only a transitive dependency of FastAPI and is not wired as a metrics backend).

- **Response time**: `duration_ms` recorded in `item_preview_*` structured log events in [`wishenka/items/service.py`](file:///home/src/wishenka/items/service.py).
- **Throughput**: Observable via `url_fetch_success` and `item_preview_success` structured log event rates.
- **Error rate**: Observable via `ssrf_blocked`, `item_preview_ssrf_blocked`, `item_preview_invalid_scheme`, `payload_size_violation`, and `item_preview_response_too_large` event frequencies.

### Business Metrics

- `fallback_reason` (`"ssrf_blocked"`, `"response_too_large"`), `reason` (`"forbidden_ip"`, `"invalid_scheme"`, `"credentials"`, `"content_length_exceeded"`, `"stream_chunk_overflow"`), and `url_domain` in `wishenka.items` warning logs track policy enforcement outcomes per preview domain.

### System Health Metrics

- **Resource usage**: Outbound HTML payload buffering is bounded by `ssrf_max_response_bytes` (`max_allowed` in `payload_size_violation` and `item_preview_response_too_large`).
- **Component status**: Active SSRF policy bounds are emitted at web startup (`wishenka.web` `"Wishenka web application starting up"`) and on component initialization (`ssrf_policy_loaded` / `ssrf_policy_configured`).

## Monitoring Integration

Integration with monitoring systems:

- [ ] Prometheus metrics (not applicable — no Prometheus collector/endpoint in repository)
- [ ] Grafana dashboards (not applicable — no Grafana provisioning/metrics backend in repository)
- [ ] Alerting rules (not applicable — handled externally by log aggregation alerts)
- [x] Log aggregation (structured `extra` JSON fields emitted via `wishenka.logging.JsonFormatter`)

## Validation Results

Validation results (executed after the final code edit):

- [x] Logs are correctly formatted: Verified `JsonFormatter().format(record)` outputs valid JSON across all new `caplog` tests in [`tests/test_ssrf_configurable_settings.py`](file:///home/src/tests/test_ssrf_configurable_settings.py) and [`tests/test_observability.py`](file:///home/src/tests/test_observability.py) (3/3 passed).
- [x] Metrics are collected correctly: N/A for external metrics backend; structured `duration_ms`, `max_allowed`, `forbidden_cidr_count`, and `allowed_schemes` fields verified via `caplog`.
- [x] Logging works in error scenarios: Verified `validate_url`, redirect hops, `SSRFSafeTransport`, `UrlMetadataService`, `ItemPreviewService`, `DNSCache` revalidation, and `PreviewCache` revalidation eviction under `WISHENKA_SSRF_*` overrides (`99/99` passed in [`tests/test_ssrf_configurable_settings.py`](file:///home/src/tests/test_ssrf_configurable_settings.py)).
- [x] Large data structures are not logged: Verified configured CIDR lists (e.g., `93.184.216.0/24`, `198.51.100.0/24`), application secrets, and URL `username:password` credentials are excluded from `wishenka.web` and `wishenka.items` log messages, `extra` payloads, and `JsonFormatter` output.
- [x] Static analysis and focused regression suite green: `make analyze` clean (`ruff check`: `All checks passed!`, `ruff format --check`: `249 files already formatted`, `mypy`: `Success: no issues found in 249 source files`); `git diff --check` clean; focused pytest suite passed `165 passed, 1 warning in 14.66s` across `tests/test_ssrf_configurable_settings.py` (99), `tests/test_ssrf_and_response_limits.py` (26), `tests/test_ssrf_dns_rebinding.py` (10), `tests/test_dns_cache.py` (6), `tests/test_preview_supported_routes.py` (17), and `tests/test_item_observability.py` (7).

## Notes

- [`wishenka/config.py`](file:///home/src/wishenka/config.py) remains intentionally logger-free to avoid circular dependencies; invalid SSRF configuration raises `pydantic.ValidationError` fail-fast on load, while active SSRF settings are logged at web startup and policy initialization.
- Pre-existing out-of-scope observation for Step 7 (Technical Debt): [`extract_domain`](file:///home/src/wishenka/items/parser.py#L349-L359) parses `urlsplit(url).netloc.lower().split(":")[0]` instead of `urlsplit(url).hostname`, causing [`UniversalInputClassifier.classify`](file:///home/src/wishenka/items/classifier.py#L94-L106) to record the URL username as `url_domain` when raw user input contains `user:pass@host`. All WISHENKA-93 SSRF and preview layers (`ssrf.py`, `fetcher.py`, and `service.py`) now strip URL userinfo via `redact_url_credentials` before logging or extracting `url_domain`.
