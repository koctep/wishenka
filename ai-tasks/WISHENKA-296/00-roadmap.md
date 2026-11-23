# Roadmap: WISHENKA-296

## Task Metadata

- **Implementation language**: Python, JavaScript, HTML, CSS

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-296/10-requirements.md`: a wishlist is created only after an explicit
    confirmation of a creation form that satisfies its validation rules; leaving or cancelling
    creates nothing; same behaviour in the Mini App and a plain mobile browser; the existing
    double-submit protection remains.
  - Implementation language determined (Python, JavaScript, HTML, CSS) and recorded above.
  - Root cause recorded as a fact in the Q&A; conflict with the "automatic empty list" rule of
    in-docs/spec.md 4.2 and doc/dev/miniapp.md recorded as decisions D1 and D2 (taken in autonomous run, flagged for product-owner confirmation; D2 adds new title validation) for the product
    owner; accepted (gate passed).
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-296/20-architecture.md`: new Mini App creation screen (`showCreate`) with
    client validation, creation-only server model `WishlistCreateInput` (required trimmed title,
    1-255), guard on the Create button shared by taps and Enter, render-token guard for `showHome`,
    explicit focus targets, date/422 handling; awaiting the acceptance gate (revised after review).
- [x] **STEP 3: Failing Repro Test**
  - `tests/test_wishlist_create_validation_api.py`, `tests/test_wishlist_create_form_ui.py`,
    `tests/test_wishlist_create_form_browser.py`: red against unchanged production code (no
    `wishenka/` change); evidence and the list of existing tests to update in Step 4 are in
    `ai-tasks/WISHENKA-296/30-failing-repro.md`; awaiting the review subagent and the gate.
- [x] **STEP 4: Development**
  - [x] Server: `WishlistCreateInput` (required trimmed name, 1-255 code points) on `POST /api/wishlists`; PATCH keeps `WishlistInput`.
  - [x] Mini App: `showCreate()` (before `showHome`), `goHome()`, `homeRenderToken` guard in `showHome`, home Create opens the form, `api()` keeps `err.body`, client validation, 422 mapping, single request via `withPending(createBtn)`, focus rules, success via `showList` with `goHome` fallback.
  - [x] i18n: eight `miniapp.create.*` keys (EN+RU; the tests and the design table list eight, not nine); CSS: `.settings-field-error`, `aria-invalid` border.
  - [x] Existing tests updated: `test_home_overview_ui.py` (stub echoes name, click asserts no POST + form), `test_cross_screen_comfort_browser.py` (burst and failure on the form's Create button), `test_wishlist_api.py` (lines 33/80/186/277/282 use a name; 80 keeps the forced 500), `test_wishlist_management_ui.py:80`, `test_home_overview_browser.py` (untitled list made by PATCH name "").
  - [x] New tests corrected (demonstrably wrong, intent kept): `test_wishlist_create_form_ui.py::test_valid_submit_sends_one_trimmed_post_and_opens_the_list` asserted no FORM at all, but the owner list screen contains its own settings form; now only the `wishlist-create-form` must be gone. `test_wishlist_create_form_browser.py::test_leaving_the_empty_form_creates_nothing[back]` waited for home after a same-document `history.back()`, but the design pushes no history entry, so the screen is unchanged; the home wait is skipped for `back` (zero requests and empty account still asserted). `test_tab_order_follows_the_visual_order` pressed Tab 6 times, but `datetime-local` has several native tab stops; consecutive stops of one field are now collapsed.
  - [x] `api()` stores `err.body` only for status 422 (deviation: design said every error). Parsing bodies of other statuses delayed the 500 path enough to break the timing of `tests/test_history_screen_browser.py::test_load_failure_shows_alert_and_retry_recovers[500]`, whose wait accepts any non-empty status.
  - [x] Verification: `make analyze` clean; three new modules green; full suite 2383 passed, 2 skipped, 17 failed, all in the known pre-existing set except the history case above (fixed, re-run green).
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-296/40-code-cleanup.md`
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-296/50-observability.md`: logs only; no new event; paths pinned by `tests/test_wishlist_create_observability.py`.
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-296/60-tech-debt.md`: no blockers; three follow-ups plus scope additions to
    WISHENKA-312, 313, 319; awaiting the review and the gate.
- [x] **STEP 8: Dev Docs**
  - `ai-tasks/WISHENKA-296/70-dev-docs.md`; `doc/dev/miniapp.md`, `wishlists.md`, `i18n.md`,
    `testing.md`; `in-docs/spec.md`, `in-docs/bot-scenarios.md`; awaiting the gate.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-296/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-296/20-architecture.md`

### STEP 3: Failing Repro

- Red automated test(s) or an `N/A` note
- `ai-tasks/WISHENKA-296/30-failing-repro.md`

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-296/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-296/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-296/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
