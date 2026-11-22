# WISHENKA-116: Bound JSON-LD Traversal Overhead

## Research

- `HtmlMetadataExtractor.extract` parses each JSON-LD script and invokes
  `_find_jsonld_products`. Discovery schedules every list child and materializes
  `list(node.items())` before checking its 20,000-node budget again. The result list preserves
  graph-first discovery order. Type checking separately traverses list-valued `@type` with its
  own 20,000-node and depth-128 limits for every candidate.
- Existing logic has an important boundary: the discovery loop checks its budget before popping
  *any* item, including a dictionary's deferred process action. At exactly 20,000 visited nodes,
  pending process actions are not run. This behavior must remain intact.
- The [Python standard library documentation](https://docs.python.org/3.13/library/stdtypes.html)
  specifies insertion-ordered dictionaries and reversible views. Forward iterators can yield the
  same child order without copying all entries; no dictionary may be mutated during traversal.
- [Python tracemalloc](https://docs.python.org/3/library/tracemalloc.html) provides peak traced
  allocation measurements. It does not measure total process RSS or CPU time.

## Implementation Plan

1. Record baseline on the task base commit before changing production code. Build deterministic
   JSON fixtures below the existing 2,097,152-byte response cap: a wide list, a wide object, and
   many candidate dictionaries with nested type lists. Record byte size, Python version, platform,
   exact command, repeated wall-clock time and `tracemalloc` peak for traversal only. Use the same
   process, fixture construction outside the measured region, warm-up, repetitions and reporting
   method for the revised code; retain raw values and compare medians and peaks. Measurements are
   observations, not resource guarantees.
2. **Failing repro, Step 3:** add offline tests in `tests/test_jsonld_traversal_bounds.py` before
   the production change. Instrument lazy sequence/mapping access and type-inspection calls so
   a very wide container cannot cause materialization or scheduling proportional to width, and
   repeated identical type inputs are evaluated once per discovery. Exercise lists and dicts,
   values before, at, and after node/depth limits, and meaningful expected output. Existing eager
   expansion and repeated scalar type inspection must fail these behavioral assertions, not fail
   due to missing imports or fixtures. Independent review precedes implementation.
3. Implement iterator-frame depth-first traversal and per-discovery type-result memoization as
   specified below. Keep public methods and extraction order unchanged. Add deterministic counters
   or instrumentable helper seams for peak pending frames and type work; counters must not persist
   across requests or alter production results.
4. Run red tests green, then compare against an unmodified reference traversal across nested
   arrays/objects, graph containers, multiple candidates and scripts, malformed types, matching
   and nonmatching strings, first usable offer, fallback, and exact boundary cases. Run existing
   preview, encoding and JSON-LD tests, record full-suite limitations, and repeat measurements.

## Architecture

```text
HTML fetch (2 MiB cap, SSRF policy unchanged)
  -> JSON parse per script (no remote retrieval)
  -> product discovery (bounded iterator frames + per-discovery type memo)
  -> existing offer extraction and OpenGraph/manual fallback
```

`wishenka/items/parser.py` owns both walkers; callers retain
`_find_jsonld_products(data) -> list[dict[str, Any]]` and
`_is_product_type(type_val) -> bool`. A private traversal helper may receive a per-call memo and
optional test-only accounting; no network, settings, schema or public API change is needed.

### Discovery order and limits

Represent pending traversal with one iterator/cursor per active container plus one deferred
process action per active dictionary. Visit graph first, then process the dictionary's type, then
its non-`@graph` values in insertion order. Lists visit items in order. Do not copy dictionary
items or push all siblings. Each non-process visit consumes exactly one of 20,000 visits; process
and frame bookkeeping consume none. At the top of every logical pop, including before a deferred
process action, stop immediately when visits reach 20,000, exactly as today. At depth 129 consume
one visit and skip children; 128 remains visitable. Preserve prior results and existing limit
logging behavior when work remains or depth is exceeded.

A container at depth 128 can schedule a child at depth 129, but that child cannot descend. With
at most one active iterator and one deferred dictionary action per level, discovery bookkeeping
has at most `2 * 130 + 2 = 262` pending records, independent of container width. A type walk
uses at most `130 + 1 = 131` frames. State counters used by tests must measure actual pending
records, not just output count. Results themselves can contain up to 20,000 product references;
the already-parsed JSON tree and extracted result fields are not temporary traversal stack.

### Type checking and repeat work

Retain `_is_product_type` semantics: only strings and nested lists are inspected; dicts and other
values are leaves. Visit left-to-right, stop at the first match, count visits and depth with the
same 20,000/128 boundaries and preserve limit logging. Use the same lazy list iterator strategy.
Within one discovery, memoize exact type-check results for immutable scalar inputs by
`(type, value)` and for identical list objects by identity with a retained strong reference;
retain enough limit metadata to reproduce logging on cache hits. Never share the memo between
scripts, invocations or requests, and do not recursively hash or copy a list to create a key.
The input must not mutate during this synchronous walk. Bound memo entries to 20,000 (one per
processed dictionary), including retained references; a hit does not repeat a type walk. JSON
text cannot express shared list identity, but repeated scalar type strings are common. Distinct
list values can still cost up to 20,000 visited type nodes each: at most 20,000 processed
candidate dictionaries times 20,000 type visits = 400,000,000 type visits per script, plus
20,000 discovery visits. This conservative bound preserves per-candidate behavior; it is not a
claim that all fixtures reach it. Across `S` scripts, the bound is `S` times that work, with
`S` itself constrained by the existing response byte limit. No new shared aggregate budget may
silently skip a candidate that the current implementation would inspect.

## Q&A

- **Why not truncate wide containers?** A narrower budget or shared type budget changes which
  existing product can be selected. Iterator frames bound width-related temporary storage while
  preserving the current limits and ordering.
- **Does this bound JSON parsing memory?** No. The existing response cap bounds raw bytes; JSON
  parsing and result storage are separate. This change bounds traversal bookkeeping and work.
- **What about unusual cyclic objects?** JSON text cannot encode cycles. For direct in-process
  inputs, node/depth budgets still terminate walks; identity memo retains references during the
  invocation and must not change results or leak across calls.
