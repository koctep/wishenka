# WISHENKA-98: Observability Implementation

## Logging Implementation

The existing `wishenka.items` structured events cover metadata extraction and preview outcomes.
`metadata_extraction_completed` includes the domain, elapsed milliseconds, availability flags,
parsed integer price and normalized currency. `item_preview_success` carries the normalized
price and currency alongside the domain and elapsed time. Existing warning events cover fetch and
fallback errors.

At DEBUG level, `jsonld_price_specification_extracted` and `jsonld_aggregate_offer_extracted`
identify structured pricing sources. Their price is a bounded numeric rendering; the former also
includes a normalized currency when recognized. Raw offer objects, raw price text and aggregate
high/low values are excluded from these events. Existing currency fallback and inline-currency
DEBUG events identify normalization outcomes. The fallback event never records the unrecognized
merchant-supplied currency text.

## Metrics Implementation

No new metrics or monitoring integration were added. The existing completion events contain
elapsed time and outcome fields suitable for log-based analysis; this change introduces no metrics
backend or dashboard.

## Validation Results

- The observability regression checks both JSON-LD events and verifies that untrusted offer
  content does not appear in any record field.
- The currency fallback regression exercises HTML extraction with control characters in an
  unknown currency and checks that its contents are absent from the diagnostic record.
- Existing item observability tests exercise structured events, timing, fallback and error paths.
- `make test PYTEST_JOBS=4`: 1465 passed, 17 failed, 2 skipped. All 17 failures reproduced
  on base commit `7ef1b53`; see `60-tech-debt.md`.
- Focused observability and aggregate offer tests: 5 passed. Ruff and mypy passed on edited files.
