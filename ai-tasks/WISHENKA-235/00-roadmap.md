# Roadmap: WISHENKA-235

## Task Metadata

- **Implementation language**: Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-235/10-requirements.md`
  - An anonymous visitor of a public share sees how many units are still
    free and does not see a book control. That visitor is not the gift
    recipient. The recipient's card stays silent. An identified giver
    still sees availability and, when units are free, the book control.
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-235/20-architecture.md`
  - Confirmed: `project_wish_item` returns the recipient view when
    `current_user` is `None`. Policy does not. The smallest change is that
    one projection: an anonymous non-recipient gets the giver view with
    empty personal fields. The card already hides «Забронировать» when the
    viewer is not identified.
- [x] **STEP 3: Failing Repro Test**
  - `tests/test_wish_card_giver_controls.py::test_anonymous_share_shows_availability_without_a_book_control`
  - `tests/test_wish_card_giver_controls.py::test_anonymous_share_shows_booked_without_a_book_control`
  - Both red on the omitted giver summary: missing «Доступно: 2 из 2», and missing «Забронировано» after a friend takes the only unit. No harness error. Product code unchanged.
- [x] **STEP 4: Development**
  - [x] Anonymous callers get `WishItemGifterViewDTO` with an empty personal
    promise. Recipient silence and the public-list allowlist stay. Defect
    assertions in `tests/test_wishenka_63_repro.py` match that contract.
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-235/40-code-cleanup.md`
  - No edit to `project_wish_item` or the two test modules. `make analyze`
    passed (306 files). Scoped serial tests: 24 passed.
- [x] **STEP 6: Observability**
  - `public_wishlist_resolved` still used `projection_mode=anonymous_safe`
    for a missing caller. That name was the silent recipient view. The
    anonymous share now uses the giver projection, so the field is
    `anonymous_gifter`. No new event. Wish titles and user lists stay out
    of the log.
  - `ai-tasks/WISHENKA-235/50-observability.md`
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-235/60-tech-debt.md`
  - User documentation was not edited. `in-docs/spec.md` already gives
    an anonymous visitor the free remainder. Stale `anonymous_safe`
    paragraphs in `doc/dev/` stay for Step 8.
  - One leftover assertion still expects the silent recipient payload on
    `GET /api/public/wishlists/{token}/view`:
    `tests/test_bot_entry_repro.py::test_anonymous_public_api_does_not_disclose_reservations`.
    Not fixed in this step. No test still expects `projection_mode`
    `anonymous_safe`. Edited test modules keep
    `pytestmark = pytest.mark.timeout(30)`.
- [x] **STEP 8: Dev Docs**
  - `doc/dev/wishlists.md`
  - `doc/dev/bot-scenarios.md`
  - `project_wish_item(item, None)` is the giver view (free remainder,
    empty personal fields). A missing caller is not the recipient.
    `public_wishlist_resolved` names that caller `anonymous_gifter`.
    `GET /api/public/wishlists/{token}/view` dumps the projected items, so
    an anonymous caller sees aggregate availability. The list endpoint
    `GET /api/public/wishlists/{token}` still uses the allowlist and omits
    `available_quantity`. Share HTML shows «Доступно» or «Забронировано»
    and hides «Забронировать» when the viewer is not identified.
  - `tests/test_bot_entry_repro.py::test_anonymous_public_api_does_not_disclose_reservations`
    still asserts the old silent `/view` payload and currently errors on a
    pre-existing circular import. These docs do not treat that test as
    coverage of the giver payload.
- [ ] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-235/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-235/20-architecture.md`

### STEP 3: Failing Repro

- `tests/test_wish_card_giver_controls.py::test_anonymous_share_shows_availability_without_a_book_control`
- `tests/test_wish_card_giver_controls.py::test_anonymous_share_shows_booked_without_a_book_control`

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-235/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-235/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-235/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/wishlists.md`
- `doc/dev/bot-scenarios.md`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
