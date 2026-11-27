# Roadmap: WISHENKA-267

## Task Metadata

- **Implementation language**: Python (wishlist page behavior and the standing
  browser check)

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-267/00-roadmap.md` created from the template
  - Implementation language recorded in Task Metadata: Python
  - `ai-tasks/WISHENKA-267/10-requirements.md` written: a signed-in giver who
    moves a wish in the real browser, with the session cookie, obtains a CSRF
    token and the move is accepted, inside the existing 5s wait
  - Awaiting review and the acceptance gate (the gate owner marks `[x]`)
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-267/20-architecture.md` written: publish the
    session CSRF token already fetched by `wishenka/web/static/app.js` on
    `window.csrfToken`. The 5s wait sees false because that property is
    never assigned.
  - Awaiting review and the acceptance gate (the gate owner marks `[x]`)
- [x] **STEP 3: Failing Repro Test**
  - Standing red check
    `tests/test_wishlist_htmx_smoke_browser.py::test_real_htmx_move_button_with_cookie_and_csrf`.
    Isolated collection ERRORs on `WishlistStore` (WISHENKA-357, left as-is).
    With `tests/test_receipt_modal_browser.py::test_stale_giver_card_is_neutral`
    collected first, the smoke check fails `PageWaitTimeout` after 5s waiting
    for `CSRF token from /api/auth/csrf`, last value `False`.
    `GET /api/auth/csrf` is 200. Product code and the test are unchanged.
    `ai-tasks/WISHENKA-267/30-failing-repro.md`.
- [x] **STEP 4: Development**
  - [x] Published the fetched CSRF string on `window.csrfToken` in
    `prepareCsrf` when the generation still matches, and cleared
    `window.csrfToken` together with the local cache after an
    `Invalid CSRF token` response (`wishenka/web/static/app.js`).
  - Pytest: `test_stale_giver_card_is_neutral` and
    `test_real_htmx_move_button_with_cookie_and_csrf` — 2 passed in 3.73s.
    `test_shared_app_script_has_no_gift_receipt_reference` — 1 passed in 0.67s.
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-267/40-code-cleanup.md`
  - Product diff left as the two `window.csrfToken` assignments in
    `wishenka/web/static/app.js`. No line exceeds 100 characters, so nothing
    was wrapped. `node --check` and `make analyze` passed.
  - Awaiting review and the acceptance gate (the gate owner marks `[x]`)
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-267/50-observability.md`
  - Publishing `window.csrfToken` is not a new server event. This step adds
    no log and does not log the token value. The existing
    `GET /api/auth/csrf` request line from `RequestLoggingMiddleware`
    (`wishenka.web`) stays as it is, as does `csrf_token_issued` on
    `wishenka.auth`, which records `telegram_id` and not the token.
  - Awaiting review and the acceptance gate (the gate owner marks `[x]`)
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-267/60-tech-debt.md`
  - No new technical debt. The two `window.csrfToken` assignments in
    `wishenka/web/static/app.js` publish the local CSRF cache and clear
    it with the local. The isolated `WishlistStore` collection error
    stays WISHENKA-357 and is not a new follow-up.
  - User documentation under `doc/` was left unchanged.
  - Awaiting review and the acceptance gate (the gate owner marks `[x]`)
- [x] **STEP 8: Dev Docs**
  - `doc/dev/miniapp.md` (`window.prepareCsrf` bridge) and
    `doc/dev/reservations.md` (Cookie CSRF on the card, plus the
    giver-control troubleshooting note): `prepareCsrf` stores the fetched
    string on the local `csrfToken` and assigns `window.csrfToken` to that
    same string when the generation still matches. A wish-card
    `Invalid CSRF token` response clears both. The move check reads
    `Boolean(window.csrfToken)` inside the existing 5 second wait.
  - `doc/dev/testing.md` already says the smoke scenario waits for
    `window.csrfToken`. Left unchanged.
  - `doc/dev/auth.md` does not say the token stays private to the script
    and does not describe the browser property. Left unchanged.
  - Did not claim the WishlistStore import cycle (WISHENKA-357) is fixed.
    `wishenka/web/static/app.js` was not edited. The shared script still
    has no `receipt` substring.
  - Awaiting review and the acceptance gate (the gate owner marks `[x]`)
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-267/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-267/20-architecture.md`

### STEP 3: Failing Repro

- `tests/test_wishlist_htmx_smoke_browser.py::test_real_htmx_move_button_with_cookie_and_csrf` (standing red check)
- `ai-tasks/WISHENKA-267/30-failing-repro.md`

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-267/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-267/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-267/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
