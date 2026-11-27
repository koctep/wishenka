# Roadmap: WISHENKA-265

## Task Metadata

- **Implementation language**: JavaScript (Mini App giver-card refresh) and Python
  (the existing browser check)

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - [/] `ai-tasks/WISHENKA-265/00-roadmap.md` created from the template
  - [/] Implementation language recorded in Task Metadata: JavaScript and Python
  - [/] `ai-tasks/WISHENKA-265/10-requirements.md` written: a stale giver card
    becomes the existing neutral unavailable card; a still-available wish
    still refreshes and stays open
  - [/] Awaiting review and the acceptance gate (the gate owner marks `[x]`)
- [x] **STEP 2: High-Level Architecture Design**
  - [/] `ai-tasks/WISHENKA-265/20-architecture.md` written
  - [/] Live refresh must call `window.swapWishCard` at event time.
    `app.js` publishes the local swap and must not contain `receipt`
  - [/] Step 3 keeps
    `tests/test_receipt_modal_browser.py::test_stale_giver_card_is_neutral`
    red (sentence still absent; wait stays 5 seconds)
  - [/] Awaiting review and the acceptance gate (the gate owner marks `[x]`)
- [x] **STEP 3: Failing Repro Test**
  - [/] Existing red test kept unchanged: `tests/test_receipt_modal_browser.py::test_stale_giver_card_is_neutral`
  - [/] Still red for the missing neutral sentence. Command: `td-log run test --task WISHENKA-265 -- make test-serial PYTEST_ARGS="tests/test_receipt_modal_browser.py::test_stale_giver_card_is_neutral"` (wrapper exit 2; `make test-serial` Error 1). `tests.browser_cdp.PageWaitTimeout: timed out after 5s waiting for: neutral replacement of the stale card`; last value `False` for `document.body.innerText.includes('Желание больше недоступно. Обновите страницу.')`. The card route returned 404 and the list body contains `{"detail":"Item not found"}`. Collected and ran; not an import or fixture error. Product code and the test were not changed.
- [x] **STEP 4: Development**
  - [x] Published `window.swapWishCard` in `wishenka/web/static/app.js` and
    called that property from the card fetch when the response arrives, so a
    non-card body becomes the neutral unavailable paragraph
- [x] **STEP 5: Code Cleanup**
  - [/] `ai-tasks/WISHENKA-265/40-code-cleanup.md` written
  - [/] `wishenka/web/static/app.js` left unchanged: one publish and a live property call
  - [/] `make analyze` passed; `node --check` on `app.js` passed; browser check not re-run
  - [/] Awaiting review and the acceptance gate (the gate owner marks `[x]`)
- [x] **STEP 6: Observability**
  - [/] `ai-tasks/WISHENKA-265/50-observability.md` written
  - [/] No new log. A missing wish card is already status 404 on
    `RequestLoggingMiddleware` for
    `GET /wishlists/{wishlist_id}/items/{item_id}/card`
  - [/] Client wiring unchanged: a non-card body from that fetch becomes the
    neutral unavailable paragraph
  - [/] Awaiting review and the acceptance gate (the gate owner marks `[x]`)
- [x] **STEP 7: Technical Debt Analysis**
  - [/] `ai-tasks/WISHENKA-265/60-tech-debt.md` written
  - [/] No new technical debt. `app.js` publishes `window.swapWishCard` and
    calls that property when the card fetch returns text. The existing
    `wishlist.js` wrapper writes the neutral sentence. No follow-ups.
  - [/] User documentation under `doc/` left unchanged. A stale developer
    sentence still belongs to Step 8.
  - [/] Awaiting review and the acceptance gate (the gate owner marks `[x]`)
- [x] **STEP 8: Dev Docs**
  - [/] `doc/dev/gift-receipt.md` stale card: `app.js` publishes
    `window.swapWishCard` and the card branch calls that property when the
    response text arrives. `wishlist.js` writes the neutral paragraph when
    the body is not the same card. A matching card still replaces in place.
  - [/] `doc/dev/miniapp.md`: no inline swap in `base.html`. The live call
    goes through `window.swapWishCard`.
  - [/] `doc/dev/reservations.md` wish-card refresh: the listener is in
    `app.js` and calls `window.swapWishCard`. The shared script does not
    write a JSON card body.
  - [/] `doc/dev/testing.md`: `test_stale_giver_card_is_neutral` now passes
    (WISHENKA-265). Other known failures are left as they were.
  - [/] Awaiting review and the acceptance gate (the gate owner marks `[x]`)
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-265/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-265/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-265/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-265/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-265/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
