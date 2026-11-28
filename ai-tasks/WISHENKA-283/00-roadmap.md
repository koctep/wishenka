# Roadmap: WISHENKA-283

## Task Metadata

- **Implementation language**: Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-283/00-roadmap.md` created from the template
  - Implementation language recorded in Task Metadata: Python
  - `ai-tasks/WISHENKA-283/10-requirements.md` written: three language checks
    stay green when the suite runs with other tests in parallel
    (`PYTEST_JOBS=4`). Passing them alone is not enough. A 600-second
    full-suite cutoff is not the outcome.
  - Awaiting review and the acceptance gate (the gate owner marks `[x]`)
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-283/20-architecture.md` written
  - No shared catalog, locale cache, or file write found for the three checks
  - Bounded `pytest -n 4 --dist loadfile` runs passed (80 tests in 10.01s;
    508 tests in 33.46s), including the three checks. Failure not reproduced
  - No product file to change. Parallel proof is the bounded neighbor run,
    not the 600-second full suite
  - Awaiting review and the acceptance gate (the gate owner marks `[x]`)
- [x] **STEP 3: Failing Repro Test**
  - N/A — no behavioral change. The three named checks already live in
    `tests/test_i18n_unit.py` and stay green under
    `pytest -n 4 --dist loadfile`. No new red test. Product code and tests
    were not edited. The 600-second full-suite kill stays WISHENKA-285.
  - `ai-tasks/WISHENKA-283/30-failing-repro.md`
  - Command: `.venv/bin/pytest -n 4 --dist loadfile tests/test_i18n_unit.py -q --tb=line`
  - Orchestrator: 37 passed in 5.57s. Confirmation: 37 passed, 4 warnings in 5.30s.
- [x] **STEP 4: Development**
  - [x] No product change. No source file and no test file was edited.
    `wishenka/web/static/app.js` was not given `receipt`. WISHENKA-285,
    WISHENKA-357, WISHENKA-298, and WISHENKA-311 were not fixed. The full
    suite was not run.
  - [x] The three i18n checks pass under
    `.venv/bin/pytest -n 4 --dist loadfile tests/test_i18n_unit.py`
    (37 passed, 4 warnings in 5.53s).
  - [x] Neighbor parallel proof (review): the same `-n 4 --dist loadfile`
    run of `tests/test_i18n_unit.py` with the neighbor files from Step 2.
    The three i18n nodes passed with that set. No node failed
    (WISHENKA-357 not seen). Product code and tests were not edited. The
    full suite was not run. Summary:
    `508 passed, 4 warnings in 33.17s`.
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-283/40-code-cleanup.md` written
  - No product edit. No source file and no test file was changed.
  - `make analyze`: Ruff checks passed, 306 files already formatted, Mypy
    found no issues in 306 source files.
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-283/50-observability.md` written
  - This step adds no log. Product code was not edited.
  - The three i18n checks were already green under parallel neighbors.
  - The 600-second suite hang stays WISHENKA-285.
  - Awaiting review and the acceptance gate (the gate owner marks `[x]`)
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-283/60-tech-debt.md` written
  - No new technical debt. No product code and no test was edited.
  - The three i18n checks already have timeout marks and passed in the
    508-test neighbor run (`508 passed, 4 warnings in 33.17s`).
  - The 600-second full-suite hang stays WISHENKA-285. It is not a new
    follow-up. No Jira issue was filed.
  - User docs under `doc/` were left unchanged. No user-facing change.
  - Awaiting review and the acceptance gate (the gate owner marks `[x]`)
- [x] **STEP 8: Dev Docs**
  - `doc/dev/` already matches. No sentence lists
    `test_anonymous_share_and_invite_locale_priority_chain`,
    `test_reminders_fallback_to_en_for_missing_user_locale_and_legacy_schema`,
    or `test_miniapp_js_localizes_home_nav_shell_and_settings_label` as
    known failures. Files were left unchanged.
  - The three checks in `tests/test_i18n_unit.py` pass under
    `pytest -n 4 --dist loadfile` with neighbor files
    (`508 passed`). There is no shared catalog bug.
  - The 600-second full-suite kill stays WISHENKA-285. The full suite
    was not run and is not claimed to finish.
  - No product code was edited. No commit.
  - Awaiting review and the acceptance gate (the gate owner marks `[x]`)
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-283/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-283/20-architecture.md`

### STEP 3: Failing Repro

- N/A — no behavioral change (`ai-tasks/WISHENKA-283/30-failing-repro.md`)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-283/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-283/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-283/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
