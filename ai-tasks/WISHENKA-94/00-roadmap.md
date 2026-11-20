# Roadmap: WISHENKA-94

## Task Metadata

- **Implementation language**: Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-94/10-requirements.md`
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-94/20-architecture.md`
  - Выбран подход: in-memory TTL/LRU кэш (`DNSCache` на базе `OrderedDict` и `time.monotonic()`) + per-loop single-flight coalescing поверх `loop.getaddrinfo` в `wishenka/items/ssrf.py` (без добавления `aiodns`).
  - Определён план failing-repro тестов для Шага 3 (`tests/test_dns_cache.py`).
- [x] **STEP 3: Failing Repro Test**
  - `tests/test_dns_cache.py` (failing repro tests for TTL caching, TTL expiration + SSRF re-validation, negative caching prohibition, LRU capacity eviction, and single-flight coalescing)
- [x] **STEP 4: Development**
  - [x] Implemented `DNSCacheEntry`, `DNSCache` (TTL=60s, LRU capacity=512, key normalization), `clear_dns_cache()`, and per-loop single-flight coalescing (`_in_flight_resolutions`) in `wishenka/items/ssrf.py`.
  - [x] Added autouse `_clear_dns_cache` fixture in `tests/conftest.py` for test isolation.
  - [x] Verified `tests/test_dns_cache.py` (5/5 passed), `tests/test_ssrf_and_response_limits.py` + `tests/test_ssrf_dns_rebinding.py` (39/39 total passed), and `make analyze` (ruff + mypy passed with 0 issues). Full `make test`: 1303 passed, 2 skipped, 17 pre-existing unrelated failures (gift receipt migration / receipt notices / UI error mapping / browser receipt tests).
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-94/40-code-cleanup.md`
  - Verified `make analyze` (Ruff check, Ruff format check, Mypy across 243 files: 0 issues) and targeted pytest suite (`tests/test_dns_cache.py`, `tests/test_ssrf_and_response_limits.py`, `tests/test_ssrf_dns_rebinding.py`: 39/39 passed). No source edits needed.
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-94/50-observability.md`
  - Enhanced structured `DEBUG` logging in `wishenka/items/ssrf.py` (`wishenka.items` logger) for DNS cache lifecycle events: `dns_cache_hit`, `dns_cache_miss`, `dns_single_flight_coalesced`, `dns_cache_expired`, and `dns_cache_evicted` (alongside existing `dns_resolution_start`, `dns_resolution_success`, `dns_resolution_failed`, and `ssrf_blocked`).
  - Added `test_dns_cache_structured_logging_events` (`caplog` verification) in `tests/test_dns_cache.py`.
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-94/60-tech-debt.md`
  - Documented shortcuts and trade-offs (module-level `_dns_cache` singleton with constant defaults and `WISHENKA-93` link, port-scoped cache keying), code quality observations (single-flight leader cancellation propagation, explicit `pytestmark = pytest.mark.timeout(30)` verification), minor unit test gaps (single-flight failure/cancellation propagation and zero-capacity/TTL guards), lazy TTL expiration characteristics, and the 17 pre-existing unrelated test failures already tracked in Jira (`WISHENKA-220`, `WISHENKA-226`, `WISHENKA-232`, `WISHENKA-235`, `WISHENKA-245`, `WISHENKA-264`–`WISHENKA-267`).
- [x] **STEP 8: Dev Docs**
  - Updated `doc/dev/items.md` to document the in-memory TTL/LRU DNS cache (`DNSCache`, `DNSCacheEntry`, `DEFAULT_DNS_CACHE_TTL_SECONDS`, `DEFAULT_DNS_CACHE_CAPACITY`, `clear_dns_cache()`), per-loop single-flight coalescing (`_in_flight_resolutions`), structured `DEBUG` log events (`dns_cache_hit`, `dns_cache_miss`, `dns_single_flight_coalesced`, `dns_cache_expired`, `dns_cache_evicted`), usage examples, configuration constants, and troubleshooting in `wishenka/items/ssrf.py`.
  - Updated `doc/dev/architecture.md` subsystem index entry for `doc/dev/items.md` to reference SSRF / DNS rebinding protection and in-memory TTL/LRU DNS caching (`DNSCache`, single-flight coalescing).
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-94/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-94/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-94/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-94/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-94/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
