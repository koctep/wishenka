# Roadmap: WISHENKA-20

## Task Metadata

- **Implementation language**: Python 3.12+

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-20/10-requirements.md`
  - Cabinet scope: home card «Мои бронирования» and the caller's own promises,
    grouped by wishlist, with a way to reach edit and purchase. Wish-card
    giver controls stay WISHENKA-19. Promise actions stay WISHENKA-18.
    Quantity rules stay WISHENKA-57.
  - Active count: distinct wishes on which the caller holds at least one
    intended or purchased promise. Cancelled promises do not count. Units
    do not count. A second promise on the same wish does not count again.
  - Step 1 gap fix: stories, functional requirements, and the definition of
    done now agree. The cabinet offers change, cancel, mark purchased, and
    «Вернуть в бронь» when the card has no giver controls and the list is
    active. An archived or deleted list refuses all four. The group header
    shows the wishlist title and, when present, the event title and the
    event date. While giver controls remain, a row offers only «К желанию»;
    WISHENKA-19 edits the latest promise, and an earlier promise is listed
    but not edited from the cabinet.
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-20/20-architecture.md`
  - Home card and cabinet are server-rendered reads of
    `get_user_reservations` and `get_user_reservations_summary`.
    The badge is `total_distinct_items`. Writes stay on the five
    WISHENKA-18 routes. Per-promise actions appear only for an
    archived wish on an active list. Step 3 red tests live in
    `tests/test_reservations_cabinet_ui.py`.
- [x] **STEP 3: Failing Repro Test**
  - `tests/test_reservations_cabinet_ui.py`
- [x] **STEP 4: Development**
  - [x] Filled recipient name and change ceiling on the caller's reservation DTO.
  - [x] Added the read-only home card, cabinet page, and list partial.
  - [x] Home copies the card in showHome. Success refreshes the list; 503 leaves it.
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-20/40-code-cleanup.md`
  - `make analyze` passed with no issues. No source edits. Cabinet UI tests:
    11 passed.
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-20/50-observability.md`
  - No new log. The cabinet GET is a read. Promise writes already log on
    `wishenka.web.reservations`. The card and page INFO lines that recorded
    the caller's telegram id were removed. No metrics exporter.
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-20/60-tech-debt.md`
  - No new follow-up. The cabinet uses the same `base.html` CSRF
    listener already tracked as WISHENKA-123. Pytest timeouts are
    present. The architecture requires no browser; the cabinet tests
    cover the served page and the served scripts.
- [x] **STEP 8: Dev Docs**
  - `doc/dev/reservations.md`
  - `doc/dev/miniapp.md`
  - Home card «Мои бронирования» and badge `total_distinct_items`.
    Cabinet lists the caller's occupying promises. Four actions only
    for an archived wish on an active list. Cabinet GET adds no
    mutation log. CSRF window stays the `base.html` listener
    (WISHENKA-123).
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-20/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-20/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)
- `tests/test_reservations_cabinet_ui.py`

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-20/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-20/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-20/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/reservations.md`
- `doc/dev/miniapp.md`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
