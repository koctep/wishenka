# Roadmap: WISHENKA-294

## Task Metadata

- **Implementation language**: Python, JavaScript, HTML, CSS

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - [x] `ai-tasks/WISHENKA-294/10-requirements.md`: cross-cutting quality of key screens (phone
    layout, long RU/EN text, loading/empty/error/success feedback, readability and controls,
    preserved familiar actions), screen inventory, coverage of existing tests, gaps for Step 2.
  - [x] Implementation language determined (Python, JavaScript, HTML, CSS) and recorded above.
  - [ ] Acceptance gate review.
- [x] **STEP 2: High-Level Architecture Design**
  - [x] `ai-tasks/WISHENKA-294/20-architecture.md`: corrections to Step 1 Q&A, evidence-based
    audit (probes D1-D9 with positive controls), shared design layer fixes (L1-L8), module and
    interface design, i18n/a11y/privacy/API notes.
  - [x] Step 3 test strategy: one cross-screen parametrized browser module plus shared helper,
    hooks, assertions A1-A10, positive controls, baseline-vs-target table.
  - [ ] Acceptance gate review.
- [x] **STEP 3: Failing Repro Test**
  - [x] Red test `tests/test_cross_screen_comfort_browser.py` (48 tests, hooks documented in its
    module docstring) plus support `tests/browser_screens.py` (moved `provision_user`,
    `open_miniapp`, `telegram_init_data`; geometry/contrast/reachability scripts,
    `seed_comfort_wishlist`, `configured_server`) and `CdpPage.set_viewport` in
    `tests/browser_cdp.py`; the old private helper names in `test_home_overview_browser.py` are
    aliases.
  - [x] Run on unchanged production code (`make test-serial`, 3 runs, identical split): 32 red,
    16 green (positive controls `test_control_*`). Red reasons: D1 overflow of the detail and
    public pages (scrollWidth 2989) and of the archive dialog, D2 quick-add field 18-148 px
    (en green only at 412), D3 content 92-111 px under the bar, D4 store link / giver select /
    "Go to wish" / `summary` under 44 px, D5 `#status` at -2597 px with no `data-kind`, D6 three
    POSTs per burst and no pending/assertive state, D7 JSON instead of a page (404/401), D8
    `:root` font `16px`, D9 no alert and no `aria-busy` for htmx failures, missing catalog keys.
  - [x] `make analyze` clean; `tests/test_browser_prerequisites.py` and the browser tests that
    import the moved helpers pass.
  - [ ] Review subagent verdict and user approval.
- [x] **STEP 4: Development**
  - [x] Iteration 1: shared CSS in `miniapp.css` (L1 root `overflow-wrap`, L2 field rule and
    44px `summary`, L3 wrapping quick-add row and clearance token, L4 sticky `#status` and
    `#feedback` with `data-kind`, L7 relative root font); `btn` class on the store link and
    "Go to wish".
  - [x] Iteration 2: `app.js` clearance observer (`--quick-add-clearance`).
  - [x] Iteration 3: `miniapp.js` `status(message, kind)` with `aria-live`, `withPending()`
    applied to create, favorites, restore, member remove/role, revoke invite, reset link.
  - [x] Iteration 4: unavailable page (`wishenka/web/unavailable.py`, `unavailable.html`,
    handler registered in `app.py`) and the 5 RU/EN catalog keys.
  - [x] Iteration 5: htmx pending/failure feedback (`#feedback` in `base.html`, `app.js`).
  - [x] `tests/test_cross_screen_comfort_browser.py`: 48 of 48 pass; test support fix
    (`CdpPage.clear_cookies`, called by `open_path`): the browser profile shares cookies across
    servers, so anonymous cases were signed in.
  - [x] Fixes for the node-stub DOM harness tests (no `removeAttribute`/`classList`, one
    `htmx:afterRequest` listener slot): `status()`, `withPending()`, `button()` handler gets the
    element, pending release folded into the existing `htmx:afterRequest` handler.
  - [x] Full-suite triage: only pre-existing failures remain when run serially; parallel runs
    show load-only timeouts that pass alone.
- [x] **STEP 5: Code Cleanup**
- [x] **STEP 6: Observability**
- [x] **STEP 7: Technical Debt Analysis**
- [x] **STEP 8: Dev Docs**
  - [x] `ai-tasks/WISHENKA-294/70-dev-docs.md`: updated `doc/dev/miniapp.md`, `i18n.md`,
    `testing.md`.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-294/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-294/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-294/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-294/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-294/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
