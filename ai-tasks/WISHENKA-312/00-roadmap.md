# Roadmap: WISHENKA-312

## Task Metadata

- **Implementation language**: Python (product and tests). The create confirmation stays in
  the existing Mini App.

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-312/10-requirements.md`: one deliberate confirmation of a new wishlist
    creates one list and sends one creation request, including after the creation flow changed
    so the home action only opens the form. Behavior changes only if one such action can still
    create a duplicate list or send a duplicate creation request.
  - Implementation language determined and recorded above.
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-312/20-architecture.md`: one deliberate confirmation already
    creates one list and sends one `POST /api/wishlists`. The home action only opens
    the form. No product change. Step 3 failing repro is N/A — no behavioral change.
- [x] **STEP 3: Failing Repro Test**
  - N/A — no behavioral change. One deliberate confirmation already sends one
    `POST /api/wishlists`: the `showCreate` submit listener returns while
    `submitting` is set, and `withPending` disables Create before `api()`.
    `create_wishlist` inserts once per request. No new test: a passing test
    would not show a missing behavior.
  - Existing lock:
    `tests/test_wishlist_create_form_ui.py::test_submit_burst_sends_exactly_one_post`
    (three submits in one turn, one creation POST).
- [x] **STEP 4: Development**
  - [x] No production change. One deliberate confirmation already creates one list
    and sends one `POST /api/wishlists`. `showCreate` returns while `submitting`
    is set, and `withPending` disables Create before `api()`. The route inserts
    once per request.
  - [x] Re-ran
    `tests/test_wishlist_create_form_ui.py::test_submit_burst_sends_exactly_one_post`
    with `make test-serial`: passed (one creation POST).
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-312/40-code-cleanup.md`: nothing to clean. Steps 1–4
    changed no production code. The in-scope lock already passed. The full
    suite was not re-run; the pre-existing red suite is filed in
    `ai-tasks/WISHENKA-228/40-code-cleanup.md`.
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-312/50-observability.md`: no new signal. One confirmation
    already sends one `POST /api/wishlists`. An operator counts a committed
    creation with INFO `wishlist_mutation_committed`
    (`operation=create_wishlist`) from `execute()` in
    `wishenka/web/routes/wishlists.py` (logger `wishenka.web.wishlists`).
    Existing creation logs stay as they are. No production code changed.
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-312/60-tech-debt.md`: no new debt. One confirmation
    already sends one `POST /api/wishlists`. The lost-response retry stays
    on WISHENKA-322. Pre-existing suite failures stay on their existing
    tickets. User docs unchanged: the owner's experience did not change.
    Nothing blocks close.
- [x] **STEP 8: Dev Docs**
  - `doc/dev/miniapp.md`: one deliberate confirmation of the create-wishlist
    form sends one `POST /api/wishlists`. Repeated taps and Enter while that
    request is in flight do not send another. Opening the form does not
    create a list. The open re-check pointer to WISHENKA-312 is removed.
    A lost-response retry stays on WISHENKA-322.
  - `doc/dev/wishlists.md`: `wishlist_mutation_committed` with
    `operation=create_wishlist` is logged in `execute()` after the handler
    returns and before the repository dependency commits. It is not proof
    the commit succeeded.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-312/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-312/20-architecture.md`

### STEP 3: Failing Repro

- N/A — no behavioral change (see Step 3). Existing lock:
  `tests/test_wishlist_create_form_ui.py::test_submit_burst_sends_exactly_one_post`

### STEP 4: Development

- No production change. Existing lock re-run:
  `tests/test_wishlist_create_form_ui.py::test_submit_burst_sends_exactly_one_post`

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-312/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-312/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-312/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/miniapp.md`
- `doc/dev/wishlists.md`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
