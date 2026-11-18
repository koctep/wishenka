# Roadmap: WISHENKA-145

## Task Metadata

- **Implementation language**: Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - [x] `ai-tasks/WISHENKA-145/00-roadmap.md`
  - [x] `ai-tasks/WISHENKA-145/10-requirements.md`
- [x] **STEP 2: High-Level Architecture Design**
  - [x] `ai-tasks/WISHENKA-145/20-architecture.md`
  - [x] Research local `htmx` assets, cookie/CSRF middleware, `hx-post` move button, and URL duplication
  - [x] Failing Repro design: `N/A — no behavioral change (pure test-addition debt)`
- [x] **STEP 3: Failing Repro Test**
  - [x] `N/A — no behavioral change (pure test-addition debt)`
- [x] **STEP 4: Development**
  - [x] Extended `tests/browser_cdp.py` with `_real_htmx_bodies()`, `use_real_htmx: bool = False`, and `CdpPage.set_cookie(...)`
  - [x] Extended `tests/conftest.py` (`application_origin` in `wishlist_server`; `auth_mode` and `use_real_htmx` in `_open_page` and `wishlist_page`)
  - [x] Added `tests/test_wishlist_htmx_smoke_browser.py` (`test_real_htmx_move_button_with_cookie_and_csrf` with real `htmx@1.9.12`, cookie session, `GET /api/auth/csrf`, `X-CSRF-Token`, `.btn-move-down` `hx-post`, DOM swap, reload persistence, clean console, offline check)
  - [x] Added `test_browser_cdp_urls_match_base_template()` to `tests/test_browser_prerequisites.py`
  - [x] Verified `ruff check`, `ruff format --check`, `mypy`, and 119 browser/prereq/CSRF/auth tests passing
- [x] **STEP 5: Code Cleanup**
  - [x] `ai-tasks/WISHENKA-145/40-code-cleanup.md`
  - [x] Verified `make analyze` (`ruff check`, `ruff format --check`, `mypy`): 0 issues across 205 files
  - [x] Inspected `tests/browser_cdp.py`, `tests/conftest.py`, `tests/test_browser_prerequisites.py`, `tests/test_wishlist_htmx_smoke_browser.py` (no dead imports, unused helpers, or timeout marker issues)
  - [x] Verified `make test-serial PYTEST_ARGS="tests/test_wishlist_htmx_smoke_browser.py tests/test_browser_prerequisites.py"` (49 passed in 8.71s)
- [x] **STEP 6: Observability**
  - [x] `ai-tasks/WISHENKA-145/50-observability.md`
  - [x] Production runtime logging/metrics: `N/A — test-only change (all changes under tests/; no wishenka/ files modified)`
  - [x] Documented test-level diagnostics (`external_requests`, `assert_clean_console`, HTTP status assertions on `page.requests`, and `test_browser_cdp_urls_match_base_template`)
- [x] **STEP 7: Technical Debt Analysis**
  - [x] `ai-tasks/WISHENKA-145/60-tech-debt.md`
  - [x] Timeout markers & bounded waits verified (`Blocker`: none)
  - [x] Prioritized findings documented (`Low` only, `NON-BLOCKER`, `status: unticketed` for follow-ups)
- [x] **STEP 8: Dev Docs**
  - [x] Updated `doc/dev/testing.md` with `use_real_htmx=True`, `auth_mode="cookie"`, `CdpPage.set_cookie`, `wishlist_server` `application_origin`, and `tests/test_wishlist_htmx_smoke_browser.py` (`htmx@1.9.12`)
  - [x] Documented URL sync guard `test_browser_cdp_urls_match_base_template()` in `tests/test_browser_prerequisites.py` against `wishenka/web/templates/base.html`
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-145/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-145/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-145/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-145/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-145/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
