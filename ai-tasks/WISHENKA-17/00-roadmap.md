# Roadmap: WISHENKA-17

## Task Metadata

- **Implementation language**: Python 3.12+

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
- [x] **STEP 2: High-Level Architecture Design**
- [x] **STEP 3: Failing Repro Test**
- [x] **STEP 4: Development**
- [x] **STEP 5: Code Cleanup**
- [x] **STEP 6: Observability**
- [x] **STEP 7: Technical Debt Analysis**
- [x] **STEP 8: Dev Docs**
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- [x] `ai-tasks/WISHENKA-17/10-requirements.md`

### STEP 2: Architecture

- [x] `ai-tasks/WISHENKA-17/20-architecture.md`

### STEP 3: Failing Repro

- [x] Red repro test: `tests/test_reservations_surprise_invariant.py`
  - Suite: 13 collected tests (11 RED failures, 2 GREEN baseline self-reservation checks).
  - Target failure modes:
    - `AttributeError: 'WishlistService' object has no attribute 'mark_reservation_purchased'`
    - `AttributeError: 'WishlistService' object has no attribute 'revert_reservation_to_active'`
    - `AttributeError: 'WishlistService' object has no attribute 'cancel_reservation'`
    - `AttributeError: 'WishlistService' object has no attribute 'update_reservation_quantity'`
    - `AttributeError: 'WishlistService' object has no attribute 'get_user_reservations'`
    - `AttributeError: 'WishlistService' object has no attribute 'get_user_reservations_summary'`
    - `AssertionError: Gifter view must include my_reservation_status`
    - `AssertionError: WishlistService must have an ItemConcurrencyCoordinator`

### STEP 4: Development

- [x] Extended `ReservationStatus` enum with `PURCHASED` and updated `WishItem.reserved_quantity` to lock both `ACTIVE` and `PURCHASED` units.
- [x] Added `ReservationNotFoundError` exception in `wishenka/wishlists/exceptions.py` and exported in `__init__.py`.
- [x] Extended `WishItemGifterViewDTO` with `my_reservation_status` and `my_reservation_id`; added `MyReservationItemDTO` and `UserReservationsSummaryDTO` in `wishenka/wishlists/schemas.py`.
- [x] Implemented `ItemConcurrencyCoordinator` (`KeyedMutex`) using per-`item_id` `asyncio.Lock` in `wishenka/wishlists/concurrency.py`.
- [x] Implemented reservation lifecycle methods in `WishlistService` (`mark_reservation_purchased`, `revert_reservation_to_active`, `cancel_reservation`, `update_reservation_quantity`) with concurrency synchronization.
- [x] Implemented aggregated queries `get_user_reservations` and `get_user_reservations_summary` supporting archived item retention.
- [x] Enforced multi-quantity reduction lock and Surprise Invariant zero-leak projections across all queries.
- [x] All 83 tests passing in `make check` with 0 linter or type errors.

### STEP 5: Code Cleanup

- [x] `ai-tasks/WISHENKA-17/40-code-cleanup.md`

### STEP 6: Observability

- [x] `ai-tasks/WISHENKA-17/50-observability.md`
  - [x] Structured logging across reservation mutations (item_reserved, reservation_purchased, reservation_reverted, reservation_cancelled, reservation_quantity_updated, item_fulfilled)
  - [x] Warnings on invariant violations (self_reservation_blocked, insufficient_quantity_blocked)
  - [x] Dedicated caplog test suite `tests/test_reservation_observability.py` with 9 automated scenarios adhering to `do-testing` contracts

### STEP 7: Tech Debt

- [x] `ai-tasks/WISHENKA-17/60-tech-debt.md`
  - [x] Verified non-blocking nature of debt items DEBT-1..6 with SAFE TO CLOSE blocker review
  - [x] Ticketed follow-up Jira issues under Epic WISHENKA-16:
    - [x] [WISHENKA-57](https://pypost.atlassian.net/browse/WISHENKA-57): SQLite WAL transactional concurrency & distributed locking engine (5.0 SP)
    - [x] [WISHENKA-58](https://pypost.atlassian.net/browse/WISHENKA-58): Lock dictionary garbage collection & memory eviction in concurrency coordinator (2.0 SP)
    - [x] [WISHENKA-59](https://pypost.atlassian.net/browse/WISHENKA-59): Secondary user-reservation indexes to eliminate O(N) scan overhead (2.0 SP)
    - [x] [WISHENKA-60](https://pypost.atlassian.net/browse/WISHENKA-60): Transactional outbox & notification dispatcher for gift lifecycle events (3.0 SP)
    - [x] [WISHENKA-61](https://pypost.atlassian.net/browse/WISHENKA-61): Client idempotency keys for reservation mutations (3.0 SP)
    - [x] [WISHENKA-62](https://pypost.atlassian.net/browse/WISHENKA-62): High-scale concurrency stress suite and property-based invariant fuzzing (3.0 SP)
  - Pre-existing test failures: None (92 passing)

### STEP 8: Dev Docs

- [x] `doc/dev/reservations.md` created with architecture, lifecycle state machine, concurrency coordinator, runnable examples, observability matrix, and troubleshooting.
- [x] `doc/dev/architecture.md` updated with references to reservation domain and piece accounting.
