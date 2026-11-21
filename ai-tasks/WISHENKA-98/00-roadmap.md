# Roadmap: WISHENKA-98

## Task Metadata

- **Implementation language**: Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-98/10-requirements.md`
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-98/20-architecture.md`
  - Designed international currency normalization and inline extraction (`CNY`, `GBP`, `JPY`, `TRY`, `GEL`, `AMD` + existing `RUB`, `USD`, `EUR`, `KZT`, `BYN` with `¥` vs `JPY`/`CNY` disambiguation), localized numeric price separator disambiguation (European thousand dots/comma decimals, Anglo-Saxon thousand commas/dot decimals, 3-digit thousand grouping vs 1–2 digit fractional decimals, Unicode whitespace separators, non-positive rejection), complex JSON-LD offer/priceSpecification extraction, and Step 3 failing-repro test suite plan (`tests/test_international_currency_parsing.py`).
- [x] **STEP 3: Failing Repro Test**
  - `tests/test_international_currency_parsing.py`
  - Added automated failing repro test suite covering international currency normalization and inline extraction (`CNY`, `GBP`, `JPY`, `TRY`, `GEL`, `AMD` + existing `RUB`, `USD`, `EUR`, `KZT`, `BYN` and `¥` vs `JPY`/`CNY` disambiguation), localized numeric price separator disambiguation (`parse_decimal_price` and `parse_price` for European thousand dots/decimal commas, Anglo-Saxon thousand commas/decimal dots, 3-digit thousand grouping vs 2-digit decimals, Unicode thin/narrow non-breaking spaces, and non-positive price rejection), complex JSON-LD structured pricing (`priceSpecification`, multi-offer arrays, nested `AggregateOffer` offers), and end-to-end foreign e-commerce HTML extraction via `HtmlMetadataExtractor.extract` and `ItemPreviewService.fetch_preview`.
- [x] **STEP 4: Development**
  - [x] Iteration 1: Expanded `CURRENCY_MAP` and `KNOWN_STORES` in `wishenka/items/parser.py`, implemented `extract_currency` for standalone and inline currency recognition (`CNY`, `GBP`, `JPY`, `TRY`, `GEL`, `AMD` + existing currencies), and enhanced `normalize_currency` with `fallback_text` support and `¥` vs `JPY`/`CNY` disambiguation.
  - [x] Iteration 2: Implemented `parse_decimal_price` and updated `parse_price` in `wishenka/items/parser.py` to disambiguate European thousand dots/decimal commas, Anglo-Saxon thousand commas/decimal dots, 3-digit thousand groupings vs 1–2 digit decimal fractions, Unicode thin/narrow non-breaking spaces, and reject non-positive/boolean prices.
  - [x] Iteration 3: Implemented `HtmlMetadataExtractor._extract_offer_pricing` in `wishenka/items/parser.py` for complex JSON-LD `Offer`, `AggregateOffer`, `priceSpecification`, and multi-offer structures, added inline `fallback_text` currency normalization in `HtmlMetadataExtractor.extract`, expanded `DOMAIN_URL_REGEX` with international TLDs in `wishenka/items/classifier.py`, and exported `extract_currency` and `parse_decimal_price` in `wishenka/items/__init__.py`. All 141 tests in `tests/test_international_currency_parsing.py` and 108 companion items/parser/currency/cassette tests pass alongside `ruff` and `mypy`.
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-98/40-code-cleanup.md`
  - Ran `make analyze` (`ruff check`, `ruff format --check`, `mypy`) across 246 source files with zero warnings or errors; verified 100-char line limits, PEP 484 type annotations, English docstrings, absence of dead code/unused imports, and `pytestmark = pytest.mark.timeout(10)` on `tests/test_international_currency_parsing.py` (141/141 tests passing).
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-98/50-observability.md`
  - Bounded JSON-LD pricing diagnostics and added a payload-leak regression test.
  - Focused tests: 5 passed; full suite: 1465 passed, 17 failed, 2 skipped; all failures reproduced on base 7ef1b53 and are tracked separately.
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-98/60-tech-debt.md`
  - Recorded baseline failures and a potential fractional-price acceptance blocker for review.
- [x] **STEP 8: Dev Docs**
  - `doc/dev/items.md`: documented international parsing, currency and price persistence.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-98/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-98/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-98/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-98/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-98/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
