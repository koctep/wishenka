# WISHENKA-116: Technical Debt Analysis

## Shortcuts Taken

- **`_type_limit_collector` `ContextVar` side channel (`wishenka/items/parser.py:21-23, 769-771, 813-818`):**
  `_walk_jsonld_products` calls `HtmlMetadataExtractor._is_product_type(type_val)` through a
  module-level `ContextVar[list[int] | None]` instead of calling `_walk_product_type` directly or
  changing `_is_product_type`'s signature. This was chosen so regression tests that monkeypatch
  `_is_product_type` still intercept discovery calls while limit-hit metadata (`visited_nodes`) is
  captured for memo replay. It introduces hidden call-stack state (`try ... finally: reset(token)`)
  and assumes at most one recorded limit entry (`limits[0]`) per `_is_product_type` invocation.
- **Private test-only diagnostic seam (`wishenka/items/parser.py:735-868`):**
  `_walk_product_type` and `_walk_jsonld_products` maintain `peak = max(peak, len(stack))` on
  every iteration and return `(result, peak)` so `_jsonld_traversal_diagnostics(walk, data)` can
  report actual pending stack records for `tests/test_jsonld_traversal_bounds.py:165-183`.
  Production callers `_is_product_type` and `_find_jsonld_products` discard `peak`.
- **Identity-based `list` memo retaining strong references (`wishenka/items/parser.py:784-785, 805-820`):**
  For `list`-valued `@type`, `memo` keys on `("list", id(type_val))` and retains `(type_val, matched, limit_visited)`
  for the duration of `_walk_jsonld_products` (up to `20_000` entries) so Python cannot reclaim and
  reuse an object's `id()` mid-walk. For scalar types `(str, int, float, bool, type(None))`, keys
  use `(type(type_val), type_val)` to separate e.g. `bool` from `int`, while non-list/non-scalar
  objects (such as `dict`) set `key = None` and bypass memoization. Because `json.loads()` allocates
  distinct `list` instances for every JSON array in text, identity memoization only deduplicates
  in-process shared list references (not structurally identical distinct JSON arrays), and assumes
  inputs are not mutated during synchronous traversal.
- **Preserved per-candidate type budget (`20_000` x `20_000`) instead of a shared aggregate budget:**
  To guarantee exact behavioral compatibility with base `ccfdae1` (`ai-tasks/WISHENKA-116/10-requirements.md`,
  `ai-tasks/WISHENKA-116/20-architecture.md`), each processed dictionary retains its own `20_000`-visit
  type budget (`<= 400,000,000` theoretical type visits per `<script>` for an in-process DAG of
  distinct outer lists) rather than introducing a shared cross-candidate type cap that could skip
  late products.
- **Standalone manual benchmark script (`ai-tasks/WISHENKA-116/benchmark_traversal.py`):**
  The micro-benchmark lives under `ai-tasks/WISHENKA-116/` rather than a CI/Makefile target, is
  outside `make analyze` scope (`wishenka` and `tests` only), and reports ad-hoc 3-sample runs for
  manual comparison rather than automated gating.

## Code Quality Issues

- **Duplicated iterator-frame and budget-check logic (`wishenka/items/parser.py:735-772, 780-854`):**
  `_walk_product_type` and `_walk_jsonld_products` duplicate the `"iterate"` frame pop/next/re-push
  mechanics, the `visited >= 20_000` check with frame re-push and `peak` update, and the `depth > 128`
  guard. The `20_000` and `128` limits also appear as inline integer literals across both walkers
  (`:750`, `:755`, `:799`, `:819`, `:832`), alongside inline `_depth > 16` in `_extract_offer_pricing`
  (`:644`), rather than named constants.
- **Duplicated `jsonld_type_limit` logging call (`wishenka/items/parser.py:765-768, 824-827`):**
  The structured `logger.debug("JSON-LD type inspection reached a limit", extra={"event": "jsonld_type_limit", ...})`
  call is duplicated between `_walk_product_type` and memo-hit replay in `_walk_jsonld_products`.
- **Unchecked `limits[0]` assumption (`wishenka/items/parser.py:813-820`):**
  If a patched or wrapped `_is_product_type` ever triggered `_walk_product_type` more than once in
  one call, `limits[0]` would silently discard subsequent entries; in unmodified production code
  `_walk_product_type` appends at most once per call.
- **Benchmark label vs fixture structure (`ai-tasks/WISHENKA-116/benchmark_traversal.py:13` vs `00-roadmap.md:23, 36`):**
  `benchmark_traversal.py` names the third fixture `"repeated_types"` and builds 500 distinct flat
  lists (`[{"@type": ["Offer"] * 100} for _ in range(500)]`), whereas Step 3/4 roadmap notes refer
  to that fixture as `"Nested types"`.

## Missing Tests

- **Explicit timeout markers verified (no blocker):**
  `tests/test_jsonld_traversal_bounds.py:13` declares `pytestmark = pytest.mark.timeout(30)` (all
  23 collected tests carry `timeout(30)`), and `tests/test_encoding_nested_graph.py:21` also
  declares `pytestmark = pytest.mark.timeout(30)`.
- **Verified passing tests and static checks in this Step 7 session:**
  - `make analyze`: Ruff linter (`All checks passed!`), Ruff format check (`248 files already formatted`),
    and Mypy (`Success: no issues found in 248 source files`).
  - Focused JSON-LD and preview suite (`PYTHONPATH=. .venv/bin/pytest tests/test_jsonld_traversal_bounds.py tests/test_encoding_nested_graph.py tests/test_metadata_extractor_service.py tests/test_marketplace_cassettes.py`):
    `149 passed in 4.58s` (`23` in `tests/test_jsonld_traversal_bounds.py`, `38` in
    `tests/test_encoding_nested_graph.py`, `59` in `tests/test_metadata_extractor_service.py`, `29`
    in `tests/test_marketplace_cassettes.py`).
  - Observability suite (`PYTHONPATH=. .venv/bin/pytest tests/test_item_observability.py`):
    `7 passed in 0.41s`.
  - Targeted i18n suite (`PYTHONPATH=. .venv/bin/pytest tests/test_i18n_unit.py tests/test_i18n_sync.py`):
    `40 passed, 1 warning in 2.56s`.
- **Incomplete full `make test` coverage:**
  Full `make test` (`PYTEST_JOBS=4` / `PYTEST_JOBS=auto`) was not completed in this run due to the
  pre-existing 600-second `TEST_WALL_LIMIT` hang (`WISHENKA-285`) and pre-existing intermittent
  failures in `tests/test_i18n_unit.py` under parallel `make test PYTEST_JOBS=4` (`WISHENKA-283`,
  `NON-BLOCKER — pre-existing`; targeted i18n suite passed `40/40` locally). Test modules outside
  the `149 + 7 + 40` sets above were not executed in this session and are not claimed as passing.
- **Unit/edge-case coverage gaps in `tests/test_jsonld_traversal_bounds.py`:**
  - **Memo saturation boundary (`len(memo) == 20_000`):** no test exercises `>= 20_000` distinct
    scalar or list `@type` keys to assert the cap stops growing `memo` while remaining entries still
    evaluate accurately.
  - **`ContextVar` cleanup on exception and scalar-vs-non-scalar memo keys:** no test checks that
    `_type_limit_collector.reset(token)` restores prior state if `_is_product_type` raises, or
    explicitly exercises `bool` vs `int` (`True` vs `1`) and unmemoized `dict` `@type` keys.
  - **Near-2 MiB multi-script end-to-end HTML extraction:** `tests/test_jsonld_traversal_bounds.py`
    exercises `_find_jsonld_products`, `_is_product_type`, and `_jsonld_traversal_diagnostics` on
    in-memory Python structures; no automated test feeds a near-2 MiB (`< 2,097,152` bytes) HTML
    document with multiple adversarial `<script type="application/ld+json">` blocks end-to-end
    through `HtmlMetadataExtractor.extract` or `ItemPreviewService.fetch_preview`.
  - **Differential comparison (`5,000` seeded graphs):** the 5,000-graph differential check run
    against base `ccfdae1` in Step 4 is not codified as an automated test in `tests/`.

## Performance Concerns

- **Per-item iterator frame and `memo` miss overhead vs baseline:**
  Re-running `PYTHONPATH=. .venv/bin/python ai-tasks/WISHENKA-116/benchmark_traversal.py` on
  Python 3.13.5 (`Linux-6.8.0-117-generic-aarch64`) reproduced the Step 4 trade-off against the Step 3
  `ccfdae1` baseline:
  - `wide_list` (`150,001` bytes): median `0.017333` s (`0.016417` s in Step 4) and `168` max peak
    traced bytes, vs baseline `0.011659` s and `2,038,920` bytes (~99.99% reduction in peak traced
    traversal memory, ~1.49x slower wall time from per-element `"iterate"` stack hops).
  - `wide_object` (`408,891` bytes): median `0.018252` s (`0.017397` s in Step 4) and `760` max peak
    traced bytes, vs baseline `0.022195` s and `3,847,016` bytes (~99.98% reduction in peak traced
    memory and faster wall time by avoiding `list(node.items())` + `reversed(...)`).
  - `repeated_types` (`406,001` bytes, 500 distinct flat lists of 100 strings): median `0.028652` s
    (`0.026877` s in Step 4) and `20,344` max peak traced bytes, vs baseline `0.015445` s and `6,888`
    bytes (~1.85x slower wall time and +13,456 peak traced bytes because distinct `list` objects miss
    `("list", id(type_val))` and populate `memo` plus `ContextVar` bookkeeping).
- **Boundedness within 262/131 records and the 2 MiB HTML limit:**
  Pending stack records are strictly bounded at `<= 262` for discovery and `<= 131` for type
  inspection (`memo <= 20_000` entries), eliminating container-width stack allocations. Because
  `json.loads()` on HTML responses within `MAX_RESPONSE_BYTES` (`2,097,152` bytes) produces a strict
  tree without shared list references, total JSON `@type` nodes across all candidates and scripts
  in one HTTP response cannot exceed the linear response token count (unlike an artificial
  in-process DAG that could hit `20_000 * 20_000` distinct-wrapper type visits). Synchronous CPU time
  and worker-pool concurrency/cancellation under multi-script adversarial inputs remain governed by
  the extraction worker pool tracked in [WISHENKA-113](https://pypost.atlassian.net/browse/WISHENKA-113).

## Follow-up Tasks

- **Pre-existing / already tracked (do NOT duplicate):**
  - **NON-BLOCKER — pre-existing ([WISHENKA-283](https://pypost.atlassian.net/browse/WISHENKA-283)):**
    Three intermittent failures in `tests/test_i18n_unit.py` observed in earlier parallel
    `make test PYTEST_JOBS=4` runs (documented in `ai-tasks/WISHENKA-114/60-tech-debt.md` and
    `ai-tasks/WISHENKA-98/60-tech-debt.md`):
    - `tests/test_i18n_unit.py::test_anonymous_share_and_invite_locale_priority_chain`
    - `tests/test_i18n_unit.py::test_reminders_fallback_to_en_for_missing_user_locale_and_legacy_schema`
    - `tests/test_i18n_unit.py::test_miniapp_js_localizes_home_nav_shell_and_settings_label`
    In this session, the targeted i18n suite (`tests/test_i18n_unit.py tests/test_i18n_sync.py`)
    passed `40 passed`.
  - **NON-BLOCKER — pre-existing ([WISHENKA-285](https://pypost.atlassian.net/browse/WISHENKA-285)):**
    `make test PYTEST_JOBS=4` hits the 600-second Makefile `TEST_WALL_LIMIT` hang guard before
    completing the full suite.
  - **NON-BLOCKER — pre-existing ([WISHENKA-113](https://pypost.atlassian.net/browse/WISHENKA-113)):**
    Metadata extraction worker-pool load, saturation, and cancellation.
- **New follow-up tasks:**
  - **None warranted (no `BLOCKER` issues).** The `ContextVar` collector, `_jsonld_traversal_diagnostics`
    seam, identity-based memoization, and per-candidate budgets are intentional compatibility
    trade-offs aligned with `ai-tasks/WISHENKA-116/10-requirements.md` and
    `ai-tasks/WISHENKA-116/20-architecture.md`. The minor test-boundary and helper-deduplication
    observations noted under *Code Quality Issues* and *Missing Tests* are low-risk polish items that
    do not justify separate follow-up tickets.
