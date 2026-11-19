# WISHENKA-157: Hardening Gift-Receipt Notification Tests and Log Contracts

## Goals

WISHENKA-23 delivered gift receipts and giver notifications, leaving a coherent set of non-blocking observability, test-reliability, and log-contract residuals (tracked as item T3 in `ai-tasks/WISHENKA-23/60-tech-debt.md` and `ai-tasks/WISHENKA-23/50-observability.md`).

From a business and operational perspective, this task is needed to:
1. **Protect giver privacy and surprise guarantees**: Ensure that owner-facing and notice-path audit logs never leak reservation presence, giver identity, or unexpected fields, and that closed-field contracts are enforced strictly rather than via partial blacklists.
2. **Ensure accurate operational observability and diagnosability**: Align log events, retry metadata, error-classification semantics, and ambiguity tracking so operators can reliably monitor delivery health, diagnose failures, and derive accurate metrics without misleading counts or false-positive "success" records on rolled-back actions.
3. **Eliminate test flakiness and indirect coverage gaps**: Replace timing-sensitive verification with deterministic checks and add direct verification for corner case CC-13 (bounded busy handling without information leaks).
4. **Keep documentation truthful**: Align operator documentation and test descriptions with actual shutdown logging behavior.

## User Stories

- **As an Operator**, I want retry-scheduled notice events to include the maximum attempts limit so that I can immediately see how close a delivery is to terminal failure without cross-referencing configuration.
- **As an Operator**, I want clear, unambiguous semantics for error-class tracking, ambiguous-delivery flags, and enqueue failures so that operational metrics and troubleshooting reflect true system state without leaking giver presence.
- **As an Operator**, I want receipt-fulfillment logs to reflect only committed business outcomes so that a rolled-back operation is never mistaken for a completed gift receipt.
- **As an Operator**, I want documentation to accurately describe what is logged on worker shutdown so that runbooks and monitoring expectations match reality.
- **As a Wishlist Owner / Giver**, I want the system to uphold the surprise-preservation and no-presence-leak guarantees across all owner-stream events (including item archiving) and under high-concurrency/busy conditions (CC-13).
- **As a Maintainer / QA Engineer**, I want closed-field log checks to verify exact allowed field sets and failure-streak tests to run deterministically without real-time waits, so that regressions are caught reliably and CI never flakes under load.

## Definition of Done

1. **Exact key-set equality in closed-field log checks**: Verification of receipt refusal and inventory-busy log records asserts exact equality against the allowed field set, rather than checking only a blacklist of forbidden fields.
2. **Deterministic worker failure-streak verification**: Verification of failure-streak logging in the notice worker runs deterministically without relying on real-time wall-clock delays.
3. **`max_attempts` on retry-scheduled events**: The retry-scheduled notice event includes the maximum attempts value alongside the current attempt, matching the observability contract.
4. **Enqueue-failure diagnosability decision**: A clear, documented decision is made and applied regarding whether and how notice-enqueue failures are diagnosed while preserving the no-presence-leak requirement.
5. **`last_error_class` and `ambiguous` semantics**: The lifecycle and reporting semantics of `last_error_class` and the `ambiguous` flag are explicitly defined, aligned with operational metric needs, and documented.
6. **`item_archived` `active_reservations_count` contract**: The presence-disclosure risk of `active_reservations_count` on `item_archived` (owner stream) is resolved in accordance with the privacy/surprise contract.
7. **`item_fulfilled` pre-commit logging contract**: The discrepancy where `item_fulfilled` is logged before transaction commit (allowing a log line on rollback) is resolved so that domain logging and committed state are consistent.
8. **Accurate worker-stop wording**: All documentation and test descriptions stating that "a stop writes nothing" are updated to accurately state that stopping emits the informational worker-stopped event without summary counts.
9. **Direct verification of corner case CC-13**: A dedicated automated test directly verifies corner case CC-13 (bounded busy response and no-leak property on the receipt path under concurrent/busy conditions).
10. **Quality gate**: All automated tests and static checks pass with no regressions.

## Task Description

### Problem Statement

During Step 6 (Observability) and Step 7 (Technical Debt Analysis) of WISHENKA-23, nine related gaps were identified across the gift-receipt and notice-delivery observability contract and its test suite:

1. Closed-field assertions for `receipt_refused` and `receipt_inventory_busy` in `tests/test_receipt_observability.py` use a blacklist of forbidden keys instead of asserting exact key-set equality, allowing unintended new fields to pass unnoticed.
2. `test_run_loop_logs_one_error_per_failure_streak` in `tests/test_receipt_notices_extra.py` uses a real-time `asyncio.sleep(0.6)` window, creating a flake risk under load.
3. `receipt_notice_retry_scheduled` omits `max_attempts`, even though the WISHENKA-22 observability specification lists it.
4. Enqueue failures for receipt notices currently emit no distinct diagnostic signal, making them indistinguishable from any receipt rollback (a trade-off made to avoid leaking reservation presence).
5. `last_error_class` is cleared upon subsequent success (preventing failure-by-class totals over time), while `ambiguous` is never cleared (causing the ambiguous gauge to include historical resolved rows unless filtered).
6. The pre-existing `item_archived` event logs `active_reservations_count` on the owner stream, which exposes reservation presence.
7. `item_fulfilled` is logged before commit, so a rolled-back receipt can still leave a fulfillment log record.
8. Documentation and a test docstring inaccurately claim that "a stop writes nothing", whereas stopping emits an informational `receipt_notice_worker_stopped` event (with no summary counts).
9. Corner case CC-13 is covered only indirectly rather than by a dedicated test.

### Programming Language

- **Implementation language**: Python.

### Functional Requirements

- **FR-1 (Exact log field contract)**: Closed-field verification for receipt refusal and inventory-busy events must fail if any unexpected field is present or any expected field is missing.
- **FR-2 (Retry metadata completeness)**: When a notice delivery is scheduled for retry, the observability event must report both the current attempt and the configured maximum attempts.
- **FR-3 (Enqueue-failure diagnosability)**: The system and its observability contract must reflect an explicit, consistent rule for diagnosing notice-enqueue failures without revealing reservation presence to unauthorized actors or owner-facing streams.
- **FR-4 (Error and ambiguity semantics)**: The semantics of `last_error_class` and `ambiguous` must be unambiguous for operators and metric consumers (whether by adjusting lifecycle behavior or defining and enforcing exact query/reporting semantics).
- **FR-5 (Owner-stream privacy on archive)**: The `item_archived` event must comply with the no-presence-leak rule regarding active reservations.
- **FR-6 (Committed-state alignment for fulfillment logs)**: `item_fulfilled` logging must accurately represent committed receipt state (not emitting a misleading success event for a rolled-back transaction).
- **FR-7 (Direct CC-13 coverage)**: Corner case CC-13 must have a direct, dedicated automated verification of its bounded busy behavior and no-leak guarantee.
- **FR-8 (Accurate shutdown documentation)**: Documentation and test docstrings must accurately describe worker-stop logging behavior.

### Non-Functional Requirements

- **NFR-1 (Determinism)**: All automated tests in scope must be deterministic and free of real-time wall-clock sleeps.
- **NFR-2 (Privacy / No-Leak)**: No change may introduce reservation presence, giver identity, or booking counts into owner-facing logs, responses, or unprivileged channels.
- **NFR-3 (Scope discipline)**: Changes must remain focused on the nine items of T3 without expanding into unrelated refactoring (covered by WISHENKA-158 / T4) or exporter implementation (covered by WISHENKA-84).

### Constraints and Assumptions

- Technical design decisions (such as exact event timing, whether `ambiguous` / `last_error_class` semantics are solved via schema/lifecycle changes or query/contract clarification, and how the loop test is decoupled from wall-clock time) are deferred to Step 2 (Architecture).
- Existing external contracts relied upon by WISHENKA-24 (such as route response codes and DTO structures) must remain intact.
- Source context: `ai-tasks/WISHENKA-23/60-tech-debt.md` (item T3) and `ai-tasks/WISHENKA-23/50-observability.md`.

### Main Entities (Business Domain)

- **Gift Receipt**: A record of an owner receiving units of a wish item.
- **Receipt Notice**: An asynchronous notification drafted for a giver when a receipt occurs on a wish with an open promise.
- **Notice Worker**: The background component responsible for delivering notices, retrying transient failures up to a maximum attempt limit, and emitting lifecycle/summary events.
- **Observability Record**: A structured log event or persisted status attribute (`last_error_class`, `ambiguous`) used by operators to monitor system health and diagnose failures.
- **Corner Case CC-13**: The concurrency/over-booked boundary case requiring bounded busy responses and zero information leakage on the receipt path.

## Q&A

- **Q1: Why are these 9 items grouped into a single task?**
  - **A1**: In `ai-tasks/WISHENKA-23/60-tech-debt.md` (item T3), all nine items were identified as a single coherent hardening unit for the gift-receipt observability contract and its test suite, separated from code splitting (T4 / WISHENKA-158) and fail-closed guards (T5 / WISHENKA-159).
- **Q2: Should this task implement a metrics exporter?**
  - **A2**: No. Metrics exporting is tracked separately under WISHENKA-84. This task only hardens the log events, state semantics, tests, and documentation.
- **Q3: What is the expected wording for worker shutdown logging?**
  - **A3**: Per `WISHENKA-23/60-tech-debt.md` (C-9), stopping the worker emits an `INFO` `receipt_notice_worker_stopped` event with no summary counts (unlike "a stop writes nothing").
