# Roadmap: WISHENKA-54

## Task Metadata

- **Implementation language**: Python 3.12+

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
- [x] **STEP 2: High-Level Architecture Design**
  - [ ] `ai-tasks/WISHENKA-54/20-architecture.md`
- [x] **STEP 3: Failing Repro Test**
  - [x] `tests/test_ssrf_and_response_limits.py`
- [x] **STEP 4: Development**
  - [x] Defined and added domain exception hierarchy (`ItemParsingError`, `SSRFError`, `SSRFBlockedError`, `InvalidUrlSchemeError`, `ResponseBodyTooLargeError`) in `wishenka/items/exceptions.py`.
  - [x] Implemented SSRF protection module in `wishenka/items/ssrf.py`: IP safety checker `is_ip_safe` (RFC1918, loopback, link-local, cloud metadata, CGNAT, broadcast, reserved), asynchronous DNS validator `resolve_and_validate_host`, and `SSRFSafeTransport` intercepting requests and redirect hops.
  - [x] Implemented safe HTML fetcher `UrlMetadataService` in `wishenka/items/fetcher.py`: strict scheme verification, early rejection on `Content-Length > 2MB`, streaming chunk accumulation capped at 2MB (`ResponseBodyTooLargeError`), and backwards-compatible mock hook support.
  - [x] Integrated `UrlMetadataService` into `ItemPreviewService` (`wishenka/items/service.py`) with graceful fallback to `ItemPreviewDTO(is_fallback=True)` on SSRF blocks (`fallback_reason="ssrf_blocked"`) and payload limit exceeded (`fallback_reason="response_too_large"`).
  - [x] Updated domain exports in `wishenka/items/__init__.py`.
  - [x] Verified full test suite (`make test` — 215 tests green, `tests/test_ssrf_and_response_limits.py` 22/22 green) and static analysis (`make analyze` — Ruff linter, Ruff format, Mypy 100% clean).
- [x] **STEP 5: Code Cleanup**
  - [ ] `ai-tasks/WISHENKA-54/40-code-cleanup.md`
- [x] **STEP 6: Observability**
  - [ ] `ai-tasks/WISHENKA-54/50-observability.md`
  - Added structured security logging in `wishenka/items/ssrf.py` for blocked SSRF attempts (host, IP, reason).
  - Added DNS resolution diagnostics at DEBUG/INFO in `wishenka/items/ssrf.py`.
  - Added payload size violation logs (Content-Length and stream chunks > 2MB) in `wishenka/items/fetcher.py`.
  - Enriched graceful fallback logging with structured attributes (`host`, `ip`, `reason`, `url`, `content_length`, `duration_ms`) in `wishenka/items/service.py`.
  - Verified no raw response HTML or secret tokens leaked into logs.
  - Added automated observability tests in `tests/test_ssrf_and_response_limits.py` (26/26 tests passing).
- [x] **STEP 7: Technical Debt Analysis**
  - [ ] `ai-tasks/WISHENKA-54/60-tech-debt.md`
- [x] **STEP 8: Dev Docs**
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- [x] `ai-tasks/WISHENKA-54/10-requirements.md`

### STEP 2: Architecture

- [x] `ai-tasks/WISHENKA-54/20-architecture.md`

### STEP 3: Failing Repro

- [x] `tests/test_ssrf_and_response_limits.py`

### STEP 4: Development

- [x] `wishenka/items/exceptions.py`
- [x] `wishenka/items/ssrf.py`
- [x] `wishenka/items/fetcher.py`
- [x] `wishenka/items/service.py`
- [x] `wishenka/items/__init__.py`
- [x] `tests/test_ssrf_and_response_limits.py`

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-54/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-54/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-54/60-tech-debt.md`

### STEP 8: Dev Docs

- [x] `doc/dev/items.md`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
