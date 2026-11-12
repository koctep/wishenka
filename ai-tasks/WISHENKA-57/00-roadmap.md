# Roadmap: WISHENKA-57

## Task Metadata

- **Implementation language**: Python 3.12+

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - [x] `ai-tasks/WISHENKA-57/10-requirements.md`
  - [x] Business goal: several service copies share one inventory and cannot
    overbook a wish
  - [x] Mechanism named in the ticket (shared write exclusion or a distributed
    lock) is deferred to architecture
  - [x] Sibling scope left in place: WISHENKA-18 API, WISHENKA-49 extra
    isolation, WISHENKA-39 broader race tests
  - [x] Review correction: receipt only adds received units and leaves the
    promise open. WISHENKA-18 is the reservation API. Booking screens are
    WISHENKA-19 and WISHENKA-20. This task keeps the shared quantity outcome.
    WISHENKA-49 covers locking and race stress tests.
  - [x] Review correction: receipt does not close a promise and is limited by
    requested quantity minus units already received. After a successful receipt,
    occupied units plus received units may exceed the requested quantity. A new
    or larger promise still uses the free remainder.
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-57/20-architecture.md`
  - Decision: wish-scoped SQLite WAL `BEGIN IMMEDIATE` write transaction
  - Rejected: Redis Redlock, and `asyncio.Lock` as the shared lock
  - Review correction: the unit of work loads the parent wishlist with
    members (`owner_id`, `is_collaborative`, and the rows `is_recipient`,
    `resolve_context`, and `submit_edit_item` read) and persists only
    changed rows. It does not call `_write` on a partial service.
  - Review correction: a `reservation_id` becomes an item id via
    `SELECT wish_item_id` inside the same `BEGIN IMMEDIATE`.
    `_transactional` and the inventory item routes leave the full-snapshot
    `execute` path.
  - Review correction: the transaction start that runs is
    `Connection.begin()`. `SQLITE_BUSY` is translated to
    `InventoryBusyError` before `execute` maps `SQLAlchemyError` to
    `RuntimeError`.
  - Review correction: `items.py` `execute` and `submit_edit_item` answer
    `InventoryBusyError` with HTTP 503. The edit modal stays open, names no
    gifter, and can be retried. A busy lower-quantity edit is not an
    unhandled 500.
- [x] **STEP 3: Failing Repro Test**
  - [/] `tests/test_shared_inventory_multiprocess.py`
  - Quantity races in that module passed as guards. The red case is the
    busy-lock translation.
  - Observed failure:
    `.venv/bin/pytest tests/test_shared_inventory_multiprocess.py -v`
    — `test_locked_wish_raises_inventory_busy_and_leaves_balance` —
    `AssertionError: expected InventoryBusyError after busy_timeout, got
    RuntimeError: Wishlist storage operation failed`. The wish balance was
    unchanged. `InventoryBusyError` is not defined, and `execute` maps
    `SQLITE_BUSY` through `SQLAlchemyError` to that `RuntimeError`.
- [x] **STEP 4: Development**
  - [x] Iteration 1: wishlist writes start with Connection.begin(). The
    begin listener emits BEGIN IMMEDIATE. SQLITE_BUSY becomes
    InventoryBusyError before the generic storage RuntimeError.
  - [x] Iteration 2: wish-scoped unit of work loads the parent wishlist
    and its members, then persists only the item, changed reservations,
    and the reservation counter. It does not call `_write`.
  - [x] Iteration 3: inventory methods and the item save routes use that
    entry. A busy API save and the edit modal return HTTP 503 and name
    no gifter. Quantity refusals stay HTTP 409.
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-57/40-code-cleanup.md`
  - `make analyze` passed: Ruff, format check, and Mypy reported no issues
  - `tests/test_shared_inventory_multiprocess.py`: 9 passed in 16.36s
  - `make test`: 396 passed in 55.76s
  - English busy sentence in the edit modal left as the architecture string
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-57/50-observability.md`
  - Wish-scoped commit, busy, and rollback logs on `WishlistStore.execute_wish`
  - Levels follow the project logger: INFO, WARNING, and ERROR. It has no
    EMERG, ALERT, or NOTICE level.
  - A domain refusal, including `ValueError` from a quantity or membership
    check, is WARNING. ERROR stays the non-busy database failure.
  - `tests/test_shared_inventory_multiprocess.py`: 13 passed in 15.45s
  - `make analyze` passed: Ruff, format check, and Mypy reported no issues
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-57/60-tech-debt.md`
  - User documentation in `doc/`: N/A. The leftovers are the shared SQLite
    writer, the English edit-modal sentence, missing HTTP 503 route tests,
    and deferred `UserStore` transactions. Developer docs stay on step 8.
- [x] **STEP 8: Dev Docs**
  - `doc/dev/architecture.md` section 2.2: shared inventory exclusion is the wish-scoped SQLite WAL write
  - `doc/dev/items.md`: `execute_wish` transaction, quantity rules, HTTP 503, inventory log events
  - Review correction: non-busy storage logs, open receipt, wish-scoped exclusion,
    and `InventoryBusyError` before `RuntimeError` in `doc/dev/`
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-57/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-57/20-architecture.md`

### STEP 3: Failing Repro

- `tests/test_shared_inventory_multiprocess.py`

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-57/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-57/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-57/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
