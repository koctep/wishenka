# WISHENKA-56: Encoding and Nested Product Metadata

## Research

- The [HTML parsing standard](https://html.spec.whatwg.org/multipage/parsing.html) gives a BOM
  precedence over transport declarations and describes a bounded metadata prescan. This service
  is a metadata extractor, not a browser; the recovery policy below is an explicit deviation.
- [Python codecs](https://docs.python.org/3/library/codecs.html#standard-encodings) lists
  `windows-1251` as an alias of `cp1251` and provides `koi8-r`. Strict decoding exposes invalid
  byte sequences, but a successful single-byte decode cannot prove the intended language.
- [JSON-LD 1.1](https://www.w3.org/TR/json-ld11/#graph-objects) permits graph objects and
  embedded nodes at multiple levels. The existing extractor implements a useful subset, not a
  complete JSON-LD processor: it must not fetch remote contexts or references.
- The streaming fetch path currently decodes using `response.encoding`, which defaults to UTF-8
  in HTTPX even without a declared charset. `_fetch_via_get` instead uses `response.text`.
  The parser recursively visits graphs and other values, then takes the first Product, but a
  deeply nested input can raise `RecursionError` in JSON parsing or traversal.

## Implementation Plan

1. Add a bounded byte-to-text decoder shared by the streaming and buffered response paths, after
   the existing response-size and HTTP status checks. Preserve effective URL and cache provenance.
2. Normalize declarations, establish a deterministic conflict policy, and apply a conservative
   legacy fallback when declarations are absent or unusable. Never claim arbitrary bytes can be
   reliably identified; retain replacement decoding as a final safe fallback.
3. Make JSON-LD traversal bounded and resilient while retaining first-product and existing metadata
   precedence. Preserve inline `Offer` and `AggregateOffer` handling and ignore malformed scripts.
4. Run targeted regression tests and the repository quality gate; document policy and limitations.

### Failing Repro: Step 3 Before Production Changes

Add network-independent tests under `tests/` using HTTPX mock responses with actual encoded bytes
through the real fetch and preview path, and local HTML fixtures for the extractor. First run them
against current production code and record assertion failures; only then implement the fix.
Tests must assert exact Cyrillic title and description for Windows-1251 / CP1251 and KOI8-R,
including header-only, meta-only, absent declarations with representative Russian text, and a
conflict whose bytes unambiguously establish the intended result (such as BOM or strict UTF-8).
Cover unknown and malformed labels, invalid bytes and deterministic ambiguous legacy conflicts.
Exercise streaming and buffered compatibility paths, unchanged size checks and fallback behavior.

Use nested arrays and multi-level `@graph` fixtures with irrelevant nodes, Product and inline Offer
or AggregateOffer, namespaced and list `@type`, and malformed scripts followed by valid metadata.
Add an input beyond the depth limit, and an oversized node collection, asserting a bounded,
non-throwing result and continued OpenGraph / HTML fallback. Independently construct an `@type`
value with nested lists deeper than Python's recursion limit and call product type inspection;
assert no `RecursionError` and a deterministic non-match when its limit is exceeded. Also exercise
an over-limit `@type` in a parseable JSON-LD script followed by valid metadata, asserting fallback
or later product discovery remains available. This direct helper case avoids relying on the JSON
decoder accepting recursion-depth-exceeding input. Preserve a separate regression for JSON-LD >
OpenGraph > microdata > HTML precedence. Tests use explicit timeouts and no live network.

## Architecture

```text
URL preview service
  -> SSRF-safe HTTP transport -> bounded raw bytes + headers
  -> shared decoder -> HTML text + effective URL (existing interface)
  -> HtmlMetadataExtractor (worker thread)
     -> bounded JSON-LD Product discovery -> existing field extraction
     -> OpenGraph -> microdata -> HTML fallback -> ExtractedMetadata
```

### Response decoding

Keep `_stream_and_read` and `_fetch_via_get` returning `tuple[str, str]`. A pure internal helper
accepts bytes and the response Content-Type; it returns text and performs no I/O. Both paths call
it after size and status validation. Inspect only a fixed prefix (at most 4096 bytes) for ASCII
HTML meta `charset` and `http-equiv=content-type` declarations, handling quoted, unquoted,
case-insensitive and malformed forms without treating arbitrary page text as a declaration.
Normalize codec labels through the standard codec registry; reject unsupported or non-text codecs
and bound declaration length. Do not mistake HTTPX's default UTF-8 for an explicit header.

Select deterministically: (1) a recognized BOM wins; (2) strict UTF-8 with non-ASCII bytes wins
over conflicting legacy declarations, since this is a reliable signal for these fixtures;
(3) otherwise prefer a recognized HTTP charset, then a recognized meta charset. If a chosen codec
cannot strictly decode, try the next candidate. For missing or unusable signals, first try strict
UTF-8, then score strict CP1251 and KOI8-R decodings on a bounded text sample using documented,
fixed Russian-language plausibility rules and a minimum confidence margin. Use a stable tie-break
and final UTF-8 replacement decode for low confidence or malformed bytes. Header/meta conflicts
between valid single-byte encodings are inherently ambiguous; honor header precedence and do not
promise to correct every mislabeled document. ASCII-only data remains ASCII-compatible. Do not
log raw content, headers or query-bearing URLs as part of detection.

### Structured product discovery

Keep `HtmlMetadataExtractor.extract(html, base_url) -> ExtractedMetadata` and its current worker
offload. Replace recursive discovery with iterative depth-first traversal of dictionaries and
lists, with fixed limits (e.g. depth 128 and 20,000 nodes per script), preserving existing order:
graph children first, current Product, then other keys in insertion order. Stop deterministically
at limits, retain already found products, and allow fallback when none is found. Handle `@graph`
objects as well as arrays. Replace recursive `_is_product_type` list inspection with an iterative
depth-first stack using its own fixed depth and node limits (e.g. 128 and 20,000). Preserve
existing string and namespaced Product matching and list order within those limits. If inspection
reaches a limit without a match, treat the candidate as a non-match and continue bounded discovery;
do not recurse or let a malformed type prevent later candidates or fallback. Catch `RecursionError`
from `json.loads` alongside malformed JSON and continue to later scripts and fallback. Never
dereference `@id` or remote context. Keep the existing first-product policy and embedded offer
extraction; referenced offers are out of scope. Avoid changing field normalization, manual
correction, logging contracts, or network safeguards.

## Q&A

- **Can encoding always be recovered?** No. CP1251 and KOI8-R often decode the same bytes without
  errors. A deterministic guess is not proof; users can correct preview fields manually.
- **Does this add a full JSON-LD implementation?** No. It supports bounded discovery of embedded
  product nodes and inline offers without network dereferencing or JSON-LD context expansion.
- **What happens at a traversal limit?** Stop that bounded search, retain prior results and allow
  other metadata sources to supply missing fields; the request must not fail from recursion.
