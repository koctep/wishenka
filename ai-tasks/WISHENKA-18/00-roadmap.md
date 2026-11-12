# Roadmap: WISHENKA-18

## Task Metadata

- **Implementation language**: Python 3.12+

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-18/10-requirements.md`
  - Client-facing promise actions and per-wish silence for the recipient.
    Quantity exclusion and receipt rules stay with WISHENKA-57. Screens stay
    with WISHENKA-19 and WISHENKA-20.
  - Correction: archive and delete stay as they are today. Actions are refused
    on an archived or deleted list. On an archived wish with an active list,
    only a new promise is refused. List deletion still cancels occupying
    promises. Quantity change is only for an intended or purchased promise. A
    multi-promise wish view stays combined; an action answer is the promise
    just changed.
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-18/20-architecture.md`
  - Five authenticated routes call the existing reservation methods through
    `execute_wish` and `BEGIN IMMEDIATE`. No second lock.
  - A recipient action returns a fixed refusal. The success body is the
    promise just changed, plus the existing gifter wish projection.
- [x] **STEP 3: Failing Repro Test**
  - `tests/test_reservation_actions_api.py`
  - Command: `.venv/bin/pytest tests/test_reservation_actions_api.py -v`
  - Result: 3 failed. List, wish, and the seeded promise were created.
    `test_unauthenticated_create_is_rejected` got 404, not 401.
    `test_gifter_create_returns_the_new_promise` got 404, not 201.
    `test_recipient_cancel_does_not_reveal_the_promise` got
    `{"detail":"Not Found"}`, not `{"detail":"Resource not found"}`.
  - Cause: the client promise routes are not registered. Starlette answers
    404 Not Found. The failure is that missing surface.
  - Deferred to Step 4: quantity floor, a second promise, holder quantity
    change, cancel, purchase, and undo, a non-holder 403, shortage 409,
    archive and delete, and wish reads that already hide bookings.
- [x] **STEP 4: Development**
  - [x] Promise routes call the existing reservation methods through execute_wish.
  - [x] Create refuses a non-positive quantity and an unidentified gifter before an id is stored.
  - [x] Recipient mutations use the same not-found body as a missing promise.
  - [x] Tests cover the quantity floor, a second promise, holder changes,
    a non-holder, shortage, archive and delete, and recipient silence.
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-18/40-code-cleanup.md`
  - Touched files were already formatted. No unused imports, debug prints, or
    dead code were removed.
  - Command: `.venv/bin/pytest tests/test_reservation_actions_api.py`
  - Result: 15 passed, 1 warning. The warning is `StarletteDeprecationWarning`
    from the installed FastAPI package.
  - Command: `make analyze`
  - Result: Ruff check passed, 79 files already formatted, Mypy success on 79
    source files.
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-18/50-observability.md`
  - HTTP promise actions log on `wishenka.web.reservations`.
  - A completed action records operation, item_id, reservation_id, and status.
    The record has no gifter id, name, or token.
  - A recipient refusal is one WARNING for HTTP 403 on create and HTTP 404 on
    mutation. The 404 record matches a missing promise and names no gifter.
  - `InventoryBusyError` on these routes is WARNING and names no gifter.
  - Command: `.venv/bin/pytest tests/test_reservation_actions_api.py`
  - Result: 19 passed, 1 warning in 6.85s. The warning is
    `StarletteDeprecationWarning` from the installed FastAPI package.
  - Command: `make analyze`
  - Result: Ruff check passed, 79 files already formatted, Mypy success on 79
    source files.
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-18/60-tech-debt.md`
  - One non-blocker: a non-positive create is 404 when `execute_wish` cannot
    load the wish, and 400 when the wish loads. HTTP 503 on these routes is
    tested. A closed list is refused before ownership, and that order stays.
  - User documentation: N/A. Step 8 owns `doc/dev/`.
- [x] **STEP 8: Dev Docs**
  - `doc/dev/reservations.md`
  - Documented the five authenticated promise routes, `PromiseActionDTO`,
    401/400/403/404, `execute_wish` with no second lock, and the three route
    log events that omit the gifter id.
  - `doc/dev/architecture.md` was left unchanged. It already describes
    `BEGIN IMMEDIATE` and does not say the client promise API is absent.
  - Correction: HTTP 403 `{"detail":"Forbidden"}` is `PermissionDeniedError`.
    HTTP 409 detail is the exception text for `InsufficientQuantityError`,
    `ReservationError`, and `WishlistArchivedError`. The quantity floor stays
    HTTP 400. Route logs `reservation_permission_denied` and
    `reservation_conflict` carry operation and the path ids and no gifter id.
    `execute_wish` builds a new `WishlistService` per call. The shared write
    is the wish-scoped `BEGIN IMMEDIATE` transaction. Symbol anchors use the
    current start lines.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-18/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-18/20-architecture.md`

### STEP 3: Failing Repro

- `tests/test_reservation_actions_api.py`

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-18/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-18/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-18/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/reservations.md`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
