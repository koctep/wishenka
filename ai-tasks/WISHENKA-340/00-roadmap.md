# Roadmap: WISHENKA-340

## Task Metadata

- **Implementation language**: Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-340/10-requirements.md`
  - History listing and clearing already read and change only the current
    person's visits and the list summaries those rows show. Favorites,
    recently deleted lists, the bot's list choice, and recording a visit
    already start from that person, then open each chosen list in full,
    including wishes and reservations the screen leaves off the page.
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-340/20-architecture.md`
  - Favorites, recently deleted lists, the bot list offer, and recording a
    visit keep the current person's selection, then load list headers
    (and that person's membership where the role or permission needs it).
    They stop opening each chosen list through `get_wishlist`. History
    listing and clearing stay on the WISHENKA-325 path.
- [x] **STEP 3: Failing Repro Test**
  - `tests/test_wishenka_340_personal_hydration_repro.py`
  - Favorites, recently deleted lists, the bot list offer, and recording a
    visit still open each chosen list through `get_wishlist`. The repro
    expects header reads, membership only where the role or permission
    needs it, and no `wl_items` or `wl_reservations` reads. History listing
    and clearing stay outside this repro.
- [x] **STEP 4: Development**
  - [x] Favorites, recently deleted lists, the bot list offer, and
    recording a visit load list headers. Membership is loaded only where
    the role or permission needs this person's row. Wishes and reservations
    stay unread. History listing, history clearing, the one-list save lock,
    and the missing-person refusal stay as they are.
    `tests/test_wishenka_340_personal_hydration_repro.py` passes.
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-340/40-code-cleanup.md`
  - `make analyze` passed. No format, lint, or type edits in the
    WISHENKA-340 diff. Production code was not changed, so the repro
    was not re-run.
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-340/50-observability.md`
  - Favorites, recently deleted lists, the bot list offer, and recording a
    visit now load list headers. A successful header load is not logged.
    Existing refusal and storage-error logs stay. No production change.
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-340/60-tech-debt.md`
  - No new follow-up. The repro module mark is
    `pytestmark = pytest.mark.timeout(30)`. The cabinet list still opens
    each list in full, and this change did not add wishes to that read.
- [x] **STEP 8: Dev Docs**
  - `doc/dev/wishlists.md`
  - `doc/dev/bot-scenarios.md`
  - Favorites, recently deleted lists, the bot list offer, and recording a
    visit load list headers. They do not read `wl_items` or
    `wl_reservations`. Membership is loaded only for favorites, the bot
    offer, and a non-deleted visit. The cabinet list still opens each list
    in full. A successful header load adds no new log.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-340/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-340/20-architecture.md`

### STEP 3: Failing Repro

- `tests/test_wishenka_340_personal_hydration_repro.py`

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-340/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-340/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-340/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/wishlists.md`
- `doc/dev/bot-scenarios.md`
- Favorites, recently deleted lists, the bot list offer, and recording a
  visit load list headers (`get_wishlist_header` /
  `get_wishlist_headers_by_ids`). They do not read `wl_items` or
  `wl_reservations`. Membership is loaded for favorites, the bot offer, and
  a non-deleted visit. Recently deleted lists and a missing or deleted visit
  do not load membership. History listing and clearing stay on the existing
  visit-and-summary path. `GET /api/wishlists` still opens each list in full.
  Recording a visit stays on the write transaction. `get_wishlist_header`
  writes nothing. A successful header load adds no new log.

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
