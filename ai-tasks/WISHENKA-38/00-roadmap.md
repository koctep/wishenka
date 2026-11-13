# Roadmap: WISHENKA-38

## Task Metadata

- **Implementation language**: Python 3.12+

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-38/10-requirements.md`
  - Deliverable is automated tests of the surprise invariant and of role
    separation. The product behavior stays as it is. No notification
    sender is added.
  - Closes verification-matrix rows S5 (recipient answer and the log of
    that same request), S6 (no recipient-facing notification), S8 (one
    walk across those exits), and A3 (a share-link visit creates no
    account).
  - Race and load tests stay on WISHENKA-39 (row R5).
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-38/20-architecture.md`
  - N/A — no behavioral change. The product already hides booking
    facts from the recipient and does not create an account on a
    share visit. No notification sender. R5 stays on WISHENKA-39.
  - Planned checks: `tests/test_surprise_role_context.py`. One walk
    closes S5, S6, and S8. A separate share visit closes A3.
  - Recipient response headers omit the same set as the body: the
    gifter, the reservation, the booked quantity, the free remainder,
    and whether the gift has been bought. Requested quantity and
    received quantity may remain in the body.
- [x] **STEP 3: Failing Repro Test**
  - N/A — no behavioral change. The surprise rule and the
    share-link visit already match the accepted requirements;
    there is no production fix to sequence.
- [x] **STEP 4: Development**
  - [x] Implemented `test_recipient_walk_hides_booking_in_response_log_and_notice`
    in `tests/test_surprise_role_context.py`. One owner GET of a booked
    display-name wish judges the body, the headers, the log of that
    request, and the absence of a recipient-facing notice.
  - [x] Implemented `test_share_link_visit_creates_no_account` in the same
    module. An unidentified `GET /share/{public_token}` leaves the users
    count unchanged, writes no `user_created` log, shows `Доступно:`,
    and does not show `Забронировать`.
- [x] **STEP 5: Code Cleanup**
  - Scope: `tests/test_surprise_role_context.py` only. Product
    behavior stays unchanged.
  - `make analyze`: Ruff check passed, Ruff format check reported
    83 files already formatted, and Mypy reported no issues in 83
    files. No task-introduced warnings to fix.
  - No unused imports, unused variables, commented-out code, debug
    prints, or conflict markers. The longest line is 100 characters,
    the project limit. The test file was not rewritten.
  - `make test PYTEST=".venv/bin/pytest tests/test_surprise_role_context.py"`:
    both tests passed. Module timeout is 30 seconds. The full suite
    was not run.
  - Artifact: `ai-tasks/WISHENKA-38/40-code-cleanup.md`.
- [x] **STEP 6: Observability**
  - No new production logs or metrics. No notification sender.
  - Artifact: `ai-tasks/WISHENKA-38/50-observability.md`.
  - Existing logs judged by `tests/test_surprise_role_context.py`:
    the recipient request window must not name the gifter and must
    not emit a notification, outbox, or push event; the share visit
    must not log `user_created`.
  - The gifter booking audit (`item_reserved`, `reservation_purchased`)
    stays unchanged and outside that window.
  - No product code change. The INFO records on the judged recipient
    read do not name the gifter.
  - Logger names: `WishlistStore._read` and `WishlistStore._write`
    (`wishlist_store_read`, `wishlist_store_write`) are
    `wishenka.wishlists.store` (`logging.getLogger(__name__)` in
    `wishenka/wishlists/store.py`). `wishenka.wishlists` is the
    service logger (`item_reserved`, `reservation_purchased`).
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-38/60-tech-debt.md`
  - No new follow-up. The two checks are the deliverable. R5 stays
    on WISHENKA-39. The verification-matrix pointers stay for Step 8.
  - N/A — no `doc/` edit. This step only records debt. Step 8 owns
    the matrix update.
- [x] **STEP 8: Dev Docs**
  - Updated `doc/dev/verification-matrix.md` and the matrix pointer in
    `doc/dev/architecture.md`. No new `doc/dev` page.
  - S5, S6, and S8 point at
    `tests/test_surprise_role_context.py`
    `test_recipient_walk_hides_booking_in_response_log_and_notice`.
    S6 is the absence of a recipient-facing notification on that walk.
    No notification sender is documented.
  - A3 points at `tests/test_surprise_role_context.py`
    `test_share_link_visit_creates_no_account`.
  - Other rows stay as they were. R5 stays on WISHENKA-39.
  - No product code or test change.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-38/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-38/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-38/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-38/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-38/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
