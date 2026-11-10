# Roadmap: WISHENKA-11

## Task Metadata

- **Implementation language**: Python 3.12+

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
- [x] **STEP 2: High-Level Architecture Design**
- [x] **STEP 3: Failing Repro Test**
- [x] **STEP 4: Development**
- [x] **STEP 5: Code Cleanup**
- [x] **STEP 6: Observability**
- [x] **STEP 7: Technical Debt Analysis**
- [x] **STEP 8: Dev Docs**
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- [x] `ai-tasks/WISHENKA-11/10-requirements.md`

### STEP 2: Architecture

- [x] `ai-tasks/WISHENKA-11/20-architecture.md`

### STEP 3: Failing Repro

- [x] Red repro test: `tests/test_item_input_parsing.py`
  - [x] Universal input classification tests (`TestUniversalInputClassification`)
  - [x] HTML structured metadata extraction & fallback tests (`TestHtmlMetadataExtraction`)
  - [x] Graceful fallback & anti-bot challenge detection tests (`TestGracefulFallbackAndAntiBot`)
  - [x] Multi-quantity piece accounting & invariant tests (`TestMultiQuantityInvariants`)
  - [x] Surprise Invariant zero-leak integrity tests (`TestSurpriseInvariantIntegrity`)
  - [x] Confirmed red failure mode: `ModuleNotFoundError: No module named 'wishenka.items'`

### STEP 4: Development

- [x] Source implementation and green tests
  - [x] Implemented `wishenka/items/models.py`: `ItemPriority`, `InputType`, `ExtractedMetadata`, `InputClassificationResult`
  - [x] Implemented `wishenka/items/exceptions.py`: `ItemError`, `InvalidItemDataError`, re-exports of `CannotReduceQuantityBelowReservedError`, `InsufficientQuantityError`
  - [x] Implemented `wishenka/items/classifier.py`: `UniversalInputClassifier` with scheme/domain regex and residual text extraction
  - [x] Implemented `wishenka/items/parser.py`: `HtmlMetadataExtractor` with JSON-LD, OpenGraph, Microdata, HTML cascade, `clean_title`, `parse_price`, `normalize_currency`, `derive_store_name`
  - [x] Implemented `wishenka/items/schemas.py`: Pydantic v2 `ItemPreviewDTO`, `CreateItemDTO`, `UpdateItemDTO`
  - [x] Implemented `wishenka/items/service.py`: `ItemPreviewService` with async `preview`/`fetch_preview`, 4.0s timeout, anti-bot challenge detection, graceful fallback
  - [x] Implemented `wishenka/items/__init__.py`: Clean exports
  - [x] Integrated multi-quantity piece accounting in `wishenka/wishlists/models.py` (`WishItem` properties `reserved_quantity`, `available_quantity`, aliases `desired_quantity`, `fulfilled_quantity`)
  - [x] Updated `wishenka/wishlists/schemas.py` (`WishItemRecipientViewDTO`, `WishItemGifterViewDTO` with e-commerce fields while preserving Surprise Invariant)
  - [x] Updated `wishenka/wishlists/service.py`: `create_wishlist` supporting `owner_id`, `update_wish_item` enforcing multi-quantity lock invariants
  - [x] All 24 tests in `tests/test_item_input_parsing.py` green
  - [x] Full quality gate (`make check`: ruff lint, ruff format, mypy strict, pytest 65/65 tests) passed with 0 errors

### STEP 5: Code Cleanup

- [x] `ai-tasks/WISHENKA-11/40-code-cleanup.md`

### STEP 6: Observability

- [x] `ai-tasks/WISHENKA-11/50-observability.md`
  - [x] Structured logging across `wishenka.items` (classifier, parser, preview service) and `wishenka.wishlists` (service quantity updates)
  - [x] Sensitive parameters and raw HTML body strings filtered from log payloads
  - [x] Execution metrics (`duration_ms`), stages (`parser_stage`), domains (`url_domain`), and inventory deltas (`quantity_delta`)
  - [x] Dedicated caplog test suite `tests/test_item_observability.py` with 5 automated scenarios adhering to `do-testing` contracts

### STEP 7: Tech Debt

- [x] `ai-tasks/WISHENKA-11/60-tech-debt.md`
  - [x] Verified non-blocking nature of debt items DEBT-1..5 with SAFE TO CLOSE blocker review
  - [x] Ticketed follow-up Jira issues under Epic WISHENKA-10:
    - [x] [WISHENKA-52](https://pypost.atlassian.net/browse/WISHENKA-52): Non-blocking HTML parsing with threadpool or high-performance parser (2.0 SP)
    - [x] [WISHENKA-53](https://pypost.atlassian.net/browse/WISHENKA-53): Persistent HTTP client pool and preview cache (3.0 SP)
    - [x] [WISHENKA-54](https://pypost.atlassian.net/browse/WISHENKA-54): SSRF protection and response body size limit (3.0 SP)
    - [x] [WISHENKA-55](https://pypost.atlassian.net/browse/WISHENKA-55): Pluggable marketplace extractor pipeline (5.0 SP)
    - [x] [WISHENKA-56](https://pypost.atlassian.net/browse/WISHENKA-56): Character encoding normalization and expanded JSON-LD graph test suite (2.0 SP)

### STEP 8: Dev Docs

- [x] `doc/dev/items.md` developer documentation
- [x] `doc/dev/architecture.md` integration and domain cross-references
