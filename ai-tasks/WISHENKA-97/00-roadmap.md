# Roadmap: WISHENKA-97

## Task Metadata

- **Implementation language**: Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-97/10-requirements.md`
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-97/20-architecture.md`
  - Designed VCR-compatible YAML cassette subsystem (`wishenka/items/cassettes.py`) with `CassetteTransport(httpx.AsyncBaseTransport)`, `CassetteMode` (`REPLAY`, `RECORD`, `REFRESH`), header/cookie/URI sanitization, `CassetteMissError` fail-closed propagation, Russian marketplace anti-bot signature expansion in `wishenka/items/service.py`, 10 reference cassettes (`tests/cassettes/marketplaces/`), and Step 3 failing repro plan (`tests/test_marketplace_cassettes.py`).
- [x] **STEP 3: Failing Repro Test**
  - `tests/test_marketplace_cassettes.py` (17 red test items verifying Russian anti-bot challenge detection without title leakage, offline `REPLAY` for top-5 marketplaces `product` and `antibot` cassettes, fail-closed `CassetteMissError` propagation, and `RECORD`/`REFRESH` header/cookie/URI sanitization)
  - `tests/cassettes/marketplaces/` (10 reference YAML cassettes: `ozon_product.yaml`, `ozon_antibot.yaml`, `wildberries_product.yaml`, `wildberries_antibot.yaml`, `yandex_market_product.yaml`, `yandex_market_antibot.yaml`, `avito_product.yaml`, `avito_antibot.yaml`, `megamarket_product.yaml`, `megamarket_antibot.yaml`)
- [x] **STEP 4: Development**
  - [x] Added `CassetteError` and `CassetteMissError` to `wishenka/items/exceptions.py`, expanded `CHALLENGE_SIGNATURES` in `wishenka/items/service.py` with Russian marketplace anti-bot markers, and propagated `CassetteError` in `ItemPreviewService.fetch_preview` and `UrlMetadataService.fetch_and_extract`.
  - [x] Implemented `wishenka/items/cassettes.py` (`CassetteMode`, `CassetteRequest`, `CassetteResponse`, `CassetteInteraction`, `Cassette`, `CassetteTransport`, `cassette_client`, `load_marketplace_cassette`, `sanitize_headers`, `sanitize_uri`, `sanitize_interaction`, CLI `--verify` and `--mode replay|record|refresh --url <url> --output <path>`) and exported the cassette public API in `wishenka/items/__init__.py`.
  - [x] Verified all 18 tests in `tests/test_marketplace_cassettes.py` (including CLI `record`/`refresh`/`verify` coverage) pass alongside `ruff check` and `mypy`.
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-97/40-code-cleanup.md`
  - Formatted `wishenka/items/cassettes.py` and `tests/test_marketplace_cassettes.py` with `ruff format`, verified docstrings, type annotations, and explicit pytest timeout markers, and confirmed `make analyze` (`ruff check`, `ruff format --check`, `mypy`) passes cleanly across all 245 source files.
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-97/50-observability.md`
  - Enhanced structured logging on `wishenka.items` in `wishenka/items/cassettes.py` (`cassette_loaded`, `cassette_saved`, `cassette_replay_hit`, sanitized `cassette_miss`, `cassette_recorded`, `cassette_refreshed`) and `wishenka/items/service.py` (`status_code=200` context on `200 OK` HTML `item_preview_anti_bot` / `anti_bot_challenge_detected` events).
  - Added `caplog` observability test `test_cassette_and_antibot_structured_logging_observability` in `tests/test_marketplace_cassettes.py` verifying all cassette lifecycle and anti-bot log events and ensuring no raw HTML bodies or secrets leak into logs.
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-97/60-tech-debt.md`
  - Documented trade-offs (module-level `_dns_cache` seeding in offline `REPLAY`, substring heuristics in `sanitize_uri` / `_is_sensitive_header`, full-HTML `CHALLENGE_SIGNATURES` matching), code quality notes, edge-case test gaps (multi-hop redirect cassette replay, malformed YAML/CLI error branches), and non-blocker follow-up tasks alongside the 17 pre-existing tracked test failures (`WISHENKA-220`, `WISHENKA-226`, `WISHENKA-232`, `WISHENKA-235`, `WISHENKA-245`, `WISHENKA-264`, `WISHENKA-265`, `WISHENKA-266`, `WISHENKA-267`).
- [x] **STEP 8: Dev Docs**
  - `doc/dev/items.md` (documented VCR-compatible marketplace web cassette harness `wishenka.items.cassettes`, `CassetteMode`, `Cassette`, `CassetteRequest`, `CassetteResponse`, `CassetteInteraction`, `CassetteTransport`, `cassette_client`, `load_marketplace_cassette`, `CassetteError`/`CassetteMissError`, `tests/cassettes/marketplaces/` 10 reference cassettes, CLI `python -m wishenka.items.cassettes --verify` / `--mode record|refresh`, header/cookie/URI sanitization rules, Russian marketplace `CHALLENGE_SIGNATURES` anti-bot detection, structured log events, and troubleshooting)
  - `doc/dev/architecture.md` (updated `doc/dev/items.md` subsystem summary to reference the VCR-compatible marketplace web cassette harness and Russian anti-bot challenge detection)
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-97/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-97/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-97/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-97/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-97/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
