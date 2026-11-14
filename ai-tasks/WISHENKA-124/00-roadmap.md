# Roadmap: WISHENKA-124

## Task Metadata

- **Implementation language**: Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-124/10-requirements.md` written; awaiting acceptance gate
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-124/20-architecture.md` written; awaiting acceptance gate
- [x] **STEP 3: Failing Repro Test**
  - `tests/test_browser_prerequisites.py` (groups A-H per 20-architecture.md); red run: 43 failed, 3 passed.
    Red: A-D (no `tests/browser_support.py`/`tests/conftest.py`; asserts "отсутствует: Step 4 должен создать модуль",
    CLI "No module named tests.browser_support", nested pytest has no helper ERROR text), E (`pyproject.toml`: no
    websockets, no `browser` marker), F (no `deps-browser` target: `make -n` rc 2, no help line, no `.PHONY`),
    G (`ci.yml` has no `make deps-browser`). Green guards (intended): `test_addopts_do_not_deselect_tests`,
    `test_ci_and_makefile_do_not_hide_browser_tests`, `test_deps_browser_is_not_a_prerequisite_of_test_or_check`.
    `make analyze` clean (ruff, format, mypy).
- [x] **STEP 4: Development**
  - [x] `tests/browser_support.py` (find_candidates/probe/check_chromium/missing_message/is_snap_path, CLI exit codes 0/2/3) and session fixture `chromium_executable` in `tests/conftest.py`
  - [x] Both browser tests use the fixture and are marked `browser`; scenarios unchanged
  - [x] `pyproject.toml`: `websockets>=13.0` dev dependency, `browser` marker
  - [x] Makefile `deps-browser` (apt only on Debian with exit 2 and no `WISHENKA_CHROMIUM_BIN`); `ci.yml` step order `make deps`, `make deps-browser`, `make check`; preinstalled runner browser confirmed in the ubuntu-24.04 image list, setup-chrome not added
  - [x] Minimal `doc/dev/testing.md`
  - [x] Green: `tests/test_browser_prerequisites.py` (46 passed), both real browser tests, `make analyze`
- [x] **STEP 5: Code Cleanup**
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-124/50-observability.md` written; production observability N/A (tooling-only change), developer/CI diagnostics verified, no code changes
- [x] **STEP 7: Technical Debt Analysis**
- [x] **STEP 8: Dev Docs**
  - [x] `doc/dev/testing.md` expanded (overview, architecture, usage, configuration, troubleshooting, known limitations)
  - [x] `doc/dev/infrastructure.md` §2.1, §7.2, §8.5 updated; `README.md` links testing.md
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-124/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-124/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-124/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-124/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-124/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
