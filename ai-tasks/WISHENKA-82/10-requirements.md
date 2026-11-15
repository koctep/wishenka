# WISHENKA-82: Concurrent reservation stress coverage

## Goals

Give recipients and givers confidence that many people attempting to reserve the last available
copy cannot create conflicting promises or cause the available quantity to be exceeded.

## User Stories

- As a giver, I want a clear refusal if another giver has already reserved the last copy.
- As a recipient, I want the wish's available quantity respected even during simultaneous demand.
- As a maintainer, I want a bounded automated check of this contention scenario.

## Definition of Done

- Exercise 50 concurrent reservation attempts by distinct givers against one available copy.
- Exactly one attempt succeeds and the other 49 receive a refusal; no overbooking is recorded.
- The completed state reflects exactly one reservation for the copy.
- The automated check has an explicit timeout and completes within it.
- The scenario covers the persistent SQLite configuration using WAL and its busy timeout.
- The check is added to `tests/test_wishlists_sqlite_repo.py` as requested in the issue.
- Existing product behavior is preserved; this task adds coverage rather than product features.

## Task Description

A single remaining copy may attract simultaneous attempts. The project needs a repeatable stress
check that verifies the outcome under this contention and guards against overselling. The test
should distinguish accepted reservations from refusals and inspect the resulting state.

The implementation language is Python. This task does not define broader load or throughput
requirements, change the reservation policy, or require a production behavior change.

## Business Entities and Scope

- **Wish:** an item with one available copy in the scenario.
- **Giver:** a person attempting to reserve the copy; each attempt represents a distinct giver.
- **Reservation:** an accepted promise to provide the copy; at most one may be accepted.
- **Refusal:** an unsuccessful attempt after or during contention for the same copy.

## Q&A

- **Why test this?** To prevent duplicate promises and preserve confidence under simultaneous
  demand for a limited gift.
- **Does this task add a feature?** No. It adds regression coverage for the existing behavior.
- **What counts as a refusal?** An unsuccessful reservation attempt; the test must report any
  unexpected errors separately rather than silently counting them as valid business refusals.
