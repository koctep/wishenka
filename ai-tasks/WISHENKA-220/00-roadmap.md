# Roadmap: WISHENKA-220

## Task Metadata

- **Implementation language**: Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-220/10-requirements.md`
  - Archiving a wish that is not on the list shows the existing "no longer
    available" list notice, leaves the remaining wishes in place, and does
    not reload the page or look like a crash. The failing check
    `test_unmarked_error_neither_shows_notice_nor_reloads` must match that
    outcome and must not require a receipt-style listener to have seen an
    unmarked error.
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-220/20-architecture.md`
  - The archive of a missing wish already returns the OOB "no longer available" notice and leaves the list in place. `app.js` swaps that HTML and clears `isError`, so `htmx:responseError` never fires. The standing check still waits for that event. The change is the check.
- [x] **STEP 3: Failing Repro Test**
  - N/A for a new test file. The standing node is the red repro:
    `tests/test_receipt_modal_browser.py::test_unmarked_error_neither_shows_notice_nor_reloads`
  - `td-log` was absent, so the else branch ran:

    ```sh
    make test-serial PYTEST_ARGS=\
    "tests/test_receipt_modal_browser.py::test_unmarked_error_neither_shows_notice_nor_reloads"
    ```

  - Result: FAILED in 7.77s (`make test-serial` exit 1).
    `tests.browser_cdp.PageWaitTimeout: timed out after 5s waiting for:
    the unmarked error reached the listener`, last value `False`.
    The wait is `page.wait_for` at
    `tests/test_receipt_modal_browser.py:538` on
    `window.__responseErrors.length > 0`.
    The page stayed on `/web/wishlists/1`. Both item cards stayed in
    `#items-list`. `POST /web/wishlists/1/items/999999/archive` logged
    `ItemNotFoundError` and returned 404. The console was empty.
    Fixtures completed; the failure is that listener timeout.
  - Step 4 assertions were not added. No production edit. Step stays `[/]`.
- [x] **STEP 4: Development**
  - [x] Rewrote `tests/test_receipt_modal_browser.py::test_unmarked_error_neither_shows_notice_nor_reloads` so it opens the archive dialog, posts a missing wish, and asserts the Russian list notice «Желание или вишлист больше недоступны.», a closed dialog, the same card order, and no reload. It does not listen for `htmx:responseError`. Production code unchanged. `td-log run test --task WISHENKA-220 -- make test-serial PYTEST_ARGS="tests/test_receipt_modal_browser.py::test_unmarked_error_neither_shows_notice_nor_reloads"` passed (1 passed in 4.54s).
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-220/40-code-cleanup.md`
  - `make analyze` passed (Ruff check, Ruff format, Mypy, 306 files). The rewritten node needed no edit: no unused names, no debug output, lines within 100 characters, module `pytestmark` timeout 45 already covers it. The node was not re-run.
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-220/50-observability.md`
  - No production logging or metrics. The task only rewrote the browser check. A missing-wish archive already logs `ui_modal_domain_error` at WARNING (`ItemNotFoundError`, status 404) and the request-completion INFO line. A second record would duplicate that.
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-220/60-tech-debt.md`
  - No new follow-up and no blocker. The rewritten check matches the
    existing list notice. Production code is unchanged. Docs that still
    describe the old `htmx:responseError` expectation belong to Step 8.
- [x] **STEP 8: Dev Docs**
  - `doc/dev/testing.md`, `doc/dev/gift-receipt.md`
  - The receipt-modal check is no longer a known failure and no longer
    described as an unmarked error with no notice. It asserts the Russian
    list notice «Желание или вишлист больше недоступны.», a closed dialog,
    the same card order, and no reload, and it does not wait for
    `htmx:responseError`. Production code is unchanged. Left `[/]` for the
    acceptance gate.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-220/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-220/20-architecture.md`

### STEP 3: Failing Repro

- N/A for a new test file. Red node:
  `tests/test_receipt_modal_browser.py::test_unmarked_error_neither_shows_notice_nor_reloads`

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-220/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-220/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-220/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
