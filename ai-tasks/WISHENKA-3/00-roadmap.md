# Roadmap: WISHENKA-3

## Task Metadata

- **Implementation language**: Python (FastAPI + aiogram v3 + Jinja2 + HTMX)

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - [x] Document business requirements and acceptance criteria for project infrastructure, Makefile targets, linters, testing framework, containerization, and CI: `ai-tasks/WISHENKA-3/10-requirements.md`
- [x] **STEP 2: High-Level Architecture Design**
  - [x] Design repository structure, packaging (`pyproject.toml`), Makefile targets (`help`, `venv`, `deps`, `build`, `analyze`, `test`, `check`, `run`, `clean`), Ruff & Mypy configs, Pytest harness with `pytest-timeout`, Dockerfile/Compose, and GitHub Actions CI in `ai-tasks/WISHENKA-3/20-architecture.md`
- [x] **STEP 3: Failing Repro Test**
  - [x] Create red automated test in `tests/test_infra.py` asserting package version, settings, and healthcheck
- [x] **STEP 4: Development**
  - [x] Repository skeleton and configuration (`pyproject.toml`, `.gitignore`, `README.md`)
  - [x] Virtual environment and lifecycle automation (`Makefile`)
  - [x] Baseline application package (`wishenka`, `wishenka/config.py`, `wishenka/web/app.py`, `wishenka/main.py`)
  - [x] Containerization & CI/CD (`Dockerfile`, `docker-compose.yml`, `.github/workflows/ci.yml`)
  - [x] Quality gate verification (`make check` -> analyze + test)
- [x] **STEP 5: Code Cleanup**
  - [x] Code formatting, dead code removal, linter/type verification: `ai-tasks/WISHENKA-3/40-code-cleanup.md`
- [x] **STEP 6: Observability**
  - [x] Structured JSON/text logging and request middleware: `ai-tasks/WISHENKA-3/50-observability.md`
- [x] **STEP 7: Technical Debt Analysis**
  - [x] Documented technical debt and follow-up tasks: `ai-tasks/WISHENKA-3/60-tech-debt.md`
- [x] **STEP 8: Dev Docs**
  - [x] Developer infrastructure and lifecycle guide: `doc/dev/infrastructure.md`
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-3/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-3/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-3/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-3/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-3/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
