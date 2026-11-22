# Roadmap: WISHENKA-93

## Task Metadata

- **Implementation language**: Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-93/10-requirements.md`
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-93/20-architecture.md`
- [x] **STEP 3: Failing Repro Test**
  - `tests/test_ssrf_configurable_settings.py` (95/95 failed RED in `PYTHONPATH=. .venv/bin/pytest tests/test_ssrf_configurable_settings.py -v --tb=short`: missing `Settings.ssrf_*` attributes, missing `SSRFPolicy`, unrejected invalid SSRF settings/env overrides, missing `forbidden_networks` kwargs on `is_ip_safe`/`resolve_and_validate_host`, missing `settings` wiring on `SSRFSafeTransport`/`safe_direct_route`/`UrlMetadataService`/`ItemPreviewService`/`create_app`/`bot.__main__`)
- [x] **STEP 4: Development**
  - [x] Iteration 1: Added SSRF defaults, `ssrf_max_response_bytes`/`ssrf_allowed_schemes`/`ssrf_forbidden_cidrs` fields, and fail-fast CSV/JSON validators to `wishenka/config.py` (77/95 repro tests passing; ruff/mypy clean)
  - [x] Iteration 2: Added `SSRFPolicy`, env-cached `get_default_ssrf_policy`, `ContextVar` scoping, `forbidden_networks` support on `is_ip_safe`/`resolve_and_validate_host` with DNS cache revalidation & single-flight policy isolation, and `policy`/`settings` wiring in `SSRFSafeNetworkBackend`/`SSRFSafeTransport` + `wishenka/items/__init__.py` exports (plus clearing leaked `WISHENKA_SSRF_*` env vars in `test_ssrf_safe_transport_enforces_configured_schemes_cidrs_and_baseline`)
  - [x] Iteration 3: Propagated `SSRFPolicy` and `Settings` through `validate_url`, `safe_direct_route`, `UrlMetadataService`, and `ItemPreviewService` (including `PreviewCache` destination revalidation and `MagicMock` compatibility; 93/95 repro tests passing; ruff/mypy clean)
  - [x] Iteration 4: Wired `Settings` into `create_app`, `items_ui.py` preview fallback, and `wishenka.bot.__main__.run()` (`95/95` in `tests/test_ssrf_configurable_settings.py`, `408/408` across targeted SSRF/preview/fetcher/bot/infra suites, `make analyze` clean)
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-93/40-code-cleanup.md`
  - Audited all 9 Python scope files (<= 100 chars/line, 0 unused imports/vars, 0 commented-out/dead code, 0 debug prints, `95/95` tests in `tests/test_ssrf_configurable_settings.py` marked with `pytest.mark.timeout(30)`, `git diff --check` & `py_compile` clean); deduplicated policy resolution via `resolve_ssrf_policy(...)` in `wishenka/items/ssrf.py` and simplified `owned_route` initialization in `wishenka/items/fetcher.py`; `make analyze` clean (`ruff check`: `All checks passed!`, `ruff format --check`: `249 files already formatted`, `mypy`: `Success: no issues found in 249 source files`); focused suite passed `337/337` in `167.03s` (`95/95` in `tests/test_ssrf_configurable_settings.py`).
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-93/50-observability.md`
  - Audited structured logging across `wishenka/config.py`, `wishenka/items/ssrf.py`, `wishenka/items/fetcher.py`, `wishenka/items/service.py`, and `wishenka/web/app.py` (metrics N/A: no Prometheus/Grafana collector in repository); added bounded `ssrf_policy_loaded`/`ssrf_policy_configured` (`DEBUG`) and `wishenka.web` startup SSRF metadata (`INFO`), closed `validate_url`/`_validate_request`/`SSRFSafeTransport` `ssrf_blocked` logging gaps (`invalid_scheme`, `credentials`, `unsafe_backend`), enriched `dns_cache_hit`/`ssrf_pinned_cache_miss`/`preview_cache_revalidation_evicted`/`item_preview_*` events, redacted URL userinfo credentials via `redact_url_credentials`, and added 4 `caplog` + `JsonFormatter` tests in `tests/test_ssrf_configurable_settings.py` (`99/99` passing; `165/165` across focused suite; `make analyze` & `git diff --check` clean).
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-93/60-tech-debt.md`
  - Audited WISHENKA-93 changes across `wishenka/config.py`, `wishenka/items/{__init__,ssrf,fetcher,service,cassettes}.py`, `wishenka/web/{app,routes/items_ui}.py`, `wishenka/bot/__main__.py`, and `tests/test_ssrf_configurable_settings.py`. Verified `99/99` tests in `tests/test_ssrf_configurable_settings.py` declare `pytestmark = pytest.mark.timeout(30)` (`missing_timeout=0`), passed `99 passed, 1 warning in 16.42s`, and `make analyze` is clean (`ruff check`, `ruff format --check`, `mypy`: 0 issues across 249 files). Documented accepted design trade-offs (`_active_policy_var`, `_default_policy_cache` env/`.env` snapshot, import-time `MAX_RESPONSE_BYTES`/`ALLOWED_SCHEMES`/`FORBIDDEN_NETWORKS`, shared `_dns_cache` hit revalidation, ambient zero-arg `cassettes.py` callers, and pre-existing `WISHENKA-284`), minor low-risk edge-case test gaps, and one unticketed `NON-BLOCKER` Medium follow-up (parent `WISHENKA-10`) to fix `extract_domain` userinfo/IPv6 host parsing (`wishenka/items/parser.py:349-359`) and sanitize raw fallback URLs (`wishenka/items/fetcher.py:517`, `wishenka/items/service.py`). No `BLOCKER` issues found.
- [x] **STEP 8: Dev Docs**
  - `doc/dev/items.md`
  - Updated developer documentation in `doc/dev/items.md` (overview diagram, key capabilities, SSRF Protection Suite, `UrlMetadataService`, `ItemPreviewService`, Domain Exceptions, API/Usage examples, Network & Security Settings, Forbidden Network CIDRs, Telemetry Events & Privacy Guarantees, and Troubleshooting) to document `Settings.ssrf_*` (`WISHENKA_SSRF_*` JSON/CSV `NoDecode` parsing, fail-fast startup validation, defaults, and unconditional baseline IP invariants), `SSRFPolicy`, `get_default_ssrf_policy()`, `resolve_ssrf_policy()`, `_active_policy_var`, `redact_url_credentials`, `DNSCache` re-validation on hit & policy-isolated single-flight coalescing, `Settings`/`SSRFPolicy` propagation through `validate_url`, `safe_direct_route`, `UrlMetadataService`, `ItemPreviewService`, `create_app`, `items_ui.py` fallback, and `wishenka.bot.__main__.run()`, new/updated telemetry events (`ssrf_policy_loaded`, `ssrf_policy_configured`, `preview_cache_revalidation_evicted`, `ssrf_blocked`, `item_preview_*`, `dns_cache_hit`, `ssrf_pinned_cache_miss`, `wishenka.web` startup metadata), and offline verification via `tests/test_ssrf_configurable_settings.py` (`pytestmark = pytest.mark.timeout(30)`), refreshing all shifted `wishenka/items/{ssrf,fetcher,service}.py` line links.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-93/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-93/20-architecture.md`

### STEP 3: Failing Repro

- `tests/test_ssrf_configurable_settings.py`

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-93/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-93/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-93/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/items.md`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
