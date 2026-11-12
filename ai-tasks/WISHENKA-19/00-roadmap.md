# Roadmap: WISHENKA-19

## Task Metadata

- **Implementation language**: Python 3.12+

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-19/10-requirements.md`
  - Giver controls on the existing server-rendered wish card (compact and
    expanded): book, quantity choice, availability, change, cancel, bought,
    and undo of a mistaken bought mark. Promise actions stay WISHENKA-18.
    Quantity rules stay WISHENKA-57. The My reservations cabinet stays
    WISHENKA-20.
  - Step 1 review fix: on a personal list the owner is the recipient of every
    wish and sees no availability or giver controls; on a collaborative list
    the recipient is decided per wish; a display name alone does not make a
    recipient. The own line is always «Забронировано вами (N)». «Куплено» is
    added only when the latest occupying promise is bought and it is the only
    one. «Вернуть в бронь» still acts on the latest promise.
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-19/20-architecture.md`
  - One giver block on the existing card summary. Promise writes stay the
    WISHENKA-18 routes. The card refreshes from the existing card partial.
    No new promise route and no My reservations cabinet.
  - Step 3 red test to add: `tests/test_wish_card_giver_controls.py`
  - Step 2 review fix: a successful refresh restores an expanded card by
    clearing `hidden` on the new details, so edit, move, and archive stay
    visible. A recipient refresh omits `notice`, so the card stays free of
    booking sentences, including «Бронь не изменилась.».
- [x] **STEP 3: Failing Repro Test**
  - `tests/test_wish_card_giver_controls.py`
- [x] **STEP 4: Development**
  - [x] Personal-list owner is the recipient of every wish. The gifter projection now carries the latest occupying size and the occupying count.
  - [x] One giver block on the wish-card summary calls the five existing promise routes and refreshes the same card partial. An expanded card stays open. A recipient refresh omits notice.
  - [x] The refresh script reads position from data attributes, so the share page does not contain editor control names.
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-19/40-code-cleanup.md`
  - Ruff and mypy were already clean. Lines over 100 in the wish-card
    templates were wrapped. Scoped tests: 39 passed.
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-19/50-observability.md`
  - No new logs and no metrics. The mutation log stays on
    `wishenka.web.reservations`. A card refresh reads the existing partial,
    or the browser shows the busy sentence with no second request.
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-19/60-tech-debt.md`
  - One non-blocker: a cookie click before the CSRF fetch omits
    `X-CSRF-Token` and is shown as a refused booking. `json-enc` on
    unpkg and the unrun browser click are accepted by the architecture.
    Pytest timeouts are present. Follow-up:
    [WISHENKA-123](https://pypost.atlassian.net/browse/WISHENKA-123).
- [x] **STEP 8: Dev Docs**
  - `doc/dev/reservations.md` — giver controls on the existing wish-card
    summary: five existing routes, personal-list recipient rule, own line,
    expanded refresh, recipient notice omission, HTTP 503 busy sentence,
    reservation logs, and the current CSRF 403 shown as a refused booking
    (follow-up WISHENKA-123).
  - `doc/dev/wishlists.md` — card partial and `is_recipient` aligned with
    that summary.
  - `doc/dev/items.md` — recipient rule and the gifter fields the card reads.
  - `doc/dev/miniapp.md` — compact and expanded card points at the same
    summary.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-19/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-19/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-19/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-19/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-19/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
