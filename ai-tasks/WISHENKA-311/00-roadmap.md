# Roadmap: WISHENKA-311

## Task Metadata

- **Implementation language**: Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-311/00-roadmap.md` created from the template
  - Implementation language recorded in Task Metadata: Python
  - `ai-tasks/WISHENKA-311/10-requirements.md` written: the busy quick-add
    check and the viewing-history open check stay green when other browser
    checks run beside them. A sequential pass is not enough. A longer
    wall-clock wait is not the fix.
  - Step left `[/]` for the acceptance gate. The gate owner marks `[x]`.
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-311/20-architecture.md` written
  - Smallest change is test-only. The quick-add request stays held until
    the check releases it. Both checks then settle on a condition they can
    see. `WAIT` is not increased. Product code stays unchanged.
  - Parallel proof and the sequential command are named in that file.
  - Step left `[/]` for the acceptance gate. The gate owner marks `[x]`.
- [x] **STEP 3: Failing Repro Test**
  - N/A — no new test and no product behavioral change. The two checks
    already state the desired outcomes and go red only under parallel
    load. Step 3 records the parallel command from
    `20-architecture.md`. It does not add a third test, does not edit
    `wishenka/`, and does not lengthen `WAIT`.
  - Artifact: `ai-tasks/WISHENKA-311/30-failing-repro.md`
  - Unprimed command, labeled WISHENKA-357 (not this ticket's failure):
    `PYTEST_JOBS=2` on the two browser modules alone. 80 errors in
    5.00 s. Every item dies in `migrated_db_template` on the
    WishlistStore import cycle. No page opened. That cycle is not
    fixed here.
  - Primed parallel run, same two modules, `PYTEST_JOBS=2`,
    `--dist loadfile`. Each worker collects
    `tests/test_receipt_modal_browser.py::test_stale_giver_card_is_neutral`
    before scheduling, so the import finishes in both processes.
    `2 workers [81 items]`, `81 passed` in 31.57 s. Both named checks
    passed. One green run is not the fix. Step 4 still applies the
    hold-and-poll change. No product or test edit.
- [x] **STEP 4: Development**
  - [x] Hold-and-poll on the two named checks only. The busy-form check
    still holds the quick-add send, reads busy and disabled while it is
    held, then releases it. That check and the history-open check poll
    the same predicates until they hold, passing the existing 45 second
    module budget as the timeout. `WAIT`, the 5 second driver default,
    `LOAD_TIMEOUT`, and `pytest.mark.timeout(45)` stay as they are.
    Shared helpers keep today's defaults. A failed history read is
    retried inside this check's poll. No edit under `wishenka/`.
  - Primed parallel run (`TEST_WALL_LIMIT=1800`, `PYTEST_JOBS=2`,
    `test_stale_giver_card_is_neutral` plus both browser modules,
    `-q --tb=line`): `2 workers [81 items]`, `81 passed` in 33.98 s.
    Both named checks passed.
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-311/40-code-cleanup.md` written
  - First `make analyze` failed on one Mypy `no-any-return` in
    `tests/test_history_screen_browser.py` (`_older_list_is_first`).
    The predicate now returns `bool(name == "Older list")`. Second
    `make analyze` exited 0: Ruff clean, 306 files formatted, Mypy
    clean on 306 source files.
  - No edit under `wishenka/`. No receipt change. WISHENKA-357 and
    WISHENKA-285 left untouched.
  - Step left `[/]` for the acceptance gate. The gate owner marks `[x]`.
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-311/50-observability.md` written
  - Test-only change. This step adds no log and no metric. Product code
    stays unchanged. The quick-add request already logs
    `ui_item_quick_add_success` and `item_created`, plus the HTTP
    completion line. The history read already logs `view_history_listed`,
    plus the same HTTP completion line. Those records do not include the
    wish text, the list title, or a token.
  - WISHENKA-357 and WISHENKA-285 stay outside this step.
  - Step left `[/]` for the acceptance gate. The gate owner marks `[x]`.
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-311/60-tech-debt.md` written
  - No new debt and no follow-up. The two named checks poll up to the
    existing 45 second module budget. `WAIT`, the driver defaults, and
    `pytest.mark.timeout(45)` stay as they are. Nothing here blocks close.
  - The unprimed two-module run still dies on the WishlistStore import
    cycle (WISHENKA-357). The full-suite hang stays WISHENKA-285. Neither
    is filed again. `doc/` was not edited; developer docs stay Step 8.
  - Step left `[/]` for the acceptance gate. The gate owner marks `[x]`.
- [x] **STEP 8: Dev Docs**
  - `doc/dev/testing.md` (правила запуска, WISHENKA-294): the known
    load-sensitive failure list is empty. The two checks now settle on a
    condition. The busy-form check holds the quick-add request, reads the
    busy state, then polls with `timeout=45` (the existing module mark).
    `WAIT` stays `3.0` for other checks. The history-open check polls with
    `timeout=45`. Shared helpers still default to 5 seconds. A primed
    parallel run of both modules plus `test_stale_giver_card_is_neutral`
    passed 81 items. The full suite was not run. WISHENKA-357 and
    WISHENKA-285 stay open.
  - Step left `[/]` for the acceptance gate. The gate owner marks `[x]`.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-311/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-311/20-architecture.md`

### STEP 3: Failing Repro

- N/A — no new test. Recorded run: `ai-tasks/WISHENKA-311/30-failing-repro.md`

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-311/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-311/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-311/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
