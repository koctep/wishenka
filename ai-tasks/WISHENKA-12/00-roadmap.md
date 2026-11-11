# Roadmap: WISHENKA-12

## Task Metadata

- **Implementation language**: Python 3.12+

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - [x] `ai-tasks/WISHENKA-12/10-requirements.md`
- [x] **STEP 2: High-Level Architecture Design**
  - [x] `ai-tasks/WISHENKA-12/20-architecture.md`
- [x] **STEP 3: Failing Repro Test**
  - [x] `tests/test_metadata_extractor_service.py`
- [x] **STEP 4: Development**
  - [x] Implemented `wishenka/items/marketplaces.py` with `MarketplaceRule` protocol, concrete rules for Ozon, Wildberries, Yandex Market, Avito, Megamarket, `clean_url`, and `MarketplaceRegistry`.
  - [x] Enhanced `wishenka/items/parser.py`: added `@graph` traversal and `https://schema.org/Product` detection to JSON-LD extractor, added `AggregateOffer` (`lowPrice`, `highPrice`) parsing, updated `clean_title` to strip marketplace marketing slogans and suffixes, updated `derive_store_name` with marketplace aliases.
  - [x] Enhanced `wishenka/items/service.py`: URL cleaning via `clean_url` before fetching, Qrator challenge detection (`qrator`, `qrator_jsid`, `qrator-js`), and HTTP 403/503 anti-bot challenge fallback.
  - [x] Exported marketplace components in `wishenka/items/__init__.py`.
  - [x] Verified all 49 tests in `tests/test_metadata_extractor_service.py` pass (100% green), all 268 repository tests pass, and `make analyze` passes with 0 errors.
- [x] **STEP 5: Code Cleanup**
  - [x] `ai-tasks/WISHENKA-12/40-code-cleanup.md`
- [x] **STEP 6: Observability**
  - [x] `ai-tasks/WISHENKA-12/50-observability.md`
- [x] **STEP 7: Technical Debt Analysis**
  - [x] `ai-tasks/WISHENKA-12/60-tech-debt.md`
- [x] **STEP 8: Dev Docs**
  - [x] `doc/dev/items.md` updated with marketplace normalization, URL cleaning, JSON-LD `@graph` & `AggregateOffer`, anti-bot fallback, and observability.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-12/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-12/20-architecture.md`

### STEP 3: Failing Repro

- `tests/test_metadata_extractor_service.py`

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-12/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-12/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-12/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/items.md`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
