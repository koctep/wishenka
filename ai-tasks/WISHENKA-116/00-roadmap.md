# Roadmap: WISHENKA-116

## Task Metadata

- **Implementation language**: Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-116/10-requirements.md`
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-116/20-architecture.md`
- [x] **STEP 3: Failing Repro Test**
  - `tests/test_jsonld_traversal_bounds.py`: 7 intended failures, 2 compatibility checks pass.
  - Baseline benchmark: `ai-tasks/WISHENKA-116/benchmark_traversal.py` on `ccfdae1`.
  - Python 3.13.5, Linux aarch64; command `PYTHONPATH=. .venv/bin/python
    ai-tasks/WISHENKA-116/benchmark_traversal.py`. Three samples after warm-up, fixture
    construction excluded; durations in seconds and peak traced bytes:
    - Wide list (150,001 bytes): (0.011659, 2038896), (0.011844, 2038920),
      (0.011464, 2038920); median 0.011659, peak 2038920.
    - Wide object (408,891 bytes): (0.022722, 3846960), (0.022195, 3847016),
      (0.021449, 3847016); median 0.022195, peak 3847016.
    - Nested types (406,001 bytes): (0.015756, 6888), (0.015437, 6888),
      (0.015445, 6888); median 0.015445, peak 6888.
- [x] **STEP 4: Development**
  - [x] Replaced eager sibling scheduling with iterator frames and preserved graph-first order,
    visit/depth limits, and limit logging. Per-call diagnostics record actual peak pending records.
  - [x] Added discovery-local scalar and list-identity type memoization with limit-event replay;
    no state is shared across invocations. The reviewed repro passes (21 tests), and 643 related
    tests passed. A seeded comparison of 5,000 graphs and boundary inputs matched base `ccfdae1`.
  - [x] Repeated the Step 3 benchmark using the same command, environment and measurement method:
    - Wide list: (0.016408, 144), (0.016490, 168), (0.016417, 168); median 0.016417 s,
      peak 168 bytes, versus baseline 0.011659 s and 2,038,920 bytes.
    - Wide object: (0.017548, 760), (0.017308, 760), (0.017397, 760); median 0.017397 s,
      peak 760 bytes, versus baseline 0.022195 s and 3,847,016 bytes.
    - Nested types: (0.027346, 20,344), (0.026339, 20,344), (0.026877, 20,344); median
      0.026877 s, peak 20,344 bytes, versus baseline 0.015445 s and 6,888 bytes. These lists
      have distinct identities, so they are not memo hits; overhead remains within the documented
      bound. Timings and traced peaks are observations, not guaranteed thresholds.
  - [x] `make analyze` passed (Ruff, formatting and mypy).
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-116/40-code-cleanup.md`
  - `make analyze` passed (Ruff check, Ruff format check across 248 files, Mypy across 248 source files;
    0 fixes needed in `wishenka/items/parser.py` and `tests/test_jsonld_traversal_bounds.py`).
  - Verified line length <= 100 chars, no unused imports/variables, no dead code or debug prints,
    `pytestmark = pytest.mark.timeout(30)` on all 21 collected tests in
    `tests/test_jsonld_traversal_bounds.py`, and clean `git diff --check`.
  - Focused pytest suite passed: 147 passed in 4.54s (`test_jsonld_traversal_bounds.py` 21,
    `test_encoding_nested_graph.py` 38, `test_metadata_extractor_service.py` 59,
    `test_marketplace_cassettes.py` 29).
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-116/50-observability.md`
  - Audited `wishenka/items/parser.py` (`wishenka.items` logger) and confirmed structured `DEBUG`
    traversal/limit logs (`jsonld_type_limit` including memo-hit replay, `jsonld_discovery_limit`,
    `jsonld_graph_traversal`) and `extract` lifecycle logs (`metadata_extraction_started`,
    `jsonld_parse_skipped`, `metadata_stage_resolved`, `metadata_extraction_completed` at `INFO`
    with `duration_ms`) emit bounded scalar `extra` fields with no raw JSON-LD or HTML payloads;
    noted no Prometheus/Grafana metrics backend exists in this module.
  - Added `test_discovery_and_graph_logging_emit_debug_metadata_without_raw_payloads` and
    `test_type_visit_limit_logging_replays_on_memo_hit_without_payloads` in
    `tests/test_jsonld_traversal_bounds.py` (with `JsonFormatter` serialization and payload-leak
    assertions).
  - Verified `make analyze` (Ruff check, Ruff format across 248 files, Mypy across 248 source
    files), focused pytest suite (`149 passed`), and `tests/test_item_observability.py` (`7 passed`).
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-116/60-tech-debt.md`
  - Documented intentional trade-offs (`_type_limit_collector` ContextVar, `_jsonld_traversal_diagnostics`
    test seam, strong-reference `list` identity memo, preserved `20_000` x `20_000` per-candidate
    type budget), code-quality/coverage observations, and Step 7 benchmark comparison (`168` B / `760` B
    / `20,344` B peaks; `262`/`131` pending-record bounds within 2 MiB HTML limit).
  - Verified `pytestmark = pytest.mark.timeout(30)` on `tests/test_jsonld_traversal_bounds.py`,
    `make analyze` (`ruff` + `mypy` across 248 files), focused tests (`149 passed` + `7 passed`), and
    targeted i18n tests (`40 passed`); recorded incomplete full `make test` (`WISHENKA-285`) and
    pre-existing intermittent `tests/test_i18n_unit.py` failures (`WISHENKA-283`, `NON-BLOCKER — pre-existing`),
    with no new follow-up tasks warranted.
- [x] **STEP 8: Dev Docs**
  - `doc/dev/items.md`
  - Documented bounded iterator-frame JSON-LD product discovery (`_walk_jsonld_products`, `<= 262`
    pending stack records, `@graph`-first order, `20,000`-visit / depth-`128` limits), lazy
    `@type` inspection (`_walk_product_type`, `<= 131` frames, early match stop), discovery-local
    `@type` memoization (scalar `(type, value)` and `list` identity keys capped at `20,000`
    entries per invocation, `jsonld_type_limit` replay on memo hits), `_jsonld_traversal_diagnostics`
    and `tests/test_jsonld_traversal_bounds.py` checks, updated telemetry event details
    (`jsonld_graph_traversal`, `jsonld_type_limit`, `jsonld_discovery_limit`), refreshed stale
    `wishenka/items/parser.py` line links, and updated Troubleshooting to remove the stale
    pending WISHENKA-116 tracking note.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-116/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-116/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-116/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-116/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-116/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
