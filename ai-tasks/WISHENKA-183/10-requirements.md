# WISHENKA-183: Bounded Batched Cleanup of Finished Notices and Retention Timestamp Evaluation

## Goals

Ensure that periodic retention cleanup of completed notification records remains predictable, non-disruptive to concurrent user and worker activity under large backlogs, and semantically accurate for both gift notices and service/reminder notices.

Specifically, this task addresses two operational and maintainability risks identified in `WISHENKA-60` (`ai-tasks/WISHENKA-60/60-tech-debt.md`, Follow-up 2):

1. **Predictable, bounded cleanup latency:** Prevent large historical backlogs of expired terminal notices (e.g., after prolonged worker downtime or a retention-window reduction) from holding write access for an unbounded duration and blocking concurrent wishlist operations or active notice delivery.
2. **Clear retention-age semantics for service/reminder notices:** Evaluate whether tracking retention age of terminal service/reminder notices via the scheduled-attempt timestamp diverges (or risks diverging) from actual settlement time, and ensure retention eligibility is unambiguously based on when a notice reached its terminal state.

## User Stories

- **As an End User (Wishlist Owner / Giver / Member)**, I want background notification cleanup not to stall or time out my active wishlist, reservation, or gift-marking actions even if a large backlog of old notifications is being purged.
- **As a Platform Operator**, I want finished-notice retention cleanup to process expired records in bounded batches so write-lock contention remains predictable, while still draining accumulated backlogs and reporting accurate purge counts.
- **As a Platform Operator**, I want service/reminder notices to be retained for their configured retention period starting from when they actually finished (sent, skipped, or failed), without relying on ambiguous scheduling timestamps if those concepts diverge.

## Definition of Done

1. **Bounded batched deletion for finished notices:**
   - Retention cleanup deletes expired terminal records from both the gift-notice queue and the service/reminder-notice queue in bounded batches per pass rather than as a single unbounded deletion.
   - When the number of eligible expired records exceeds a single batch, cleanup either iterates across bounded passes or drains within bounded per-pass work without skipping eligible records or exceeding acceptable lock duration.
   - The total number of purged records returned to callers and emitted in cleanup observability events accurately reflects all rows deleted across batches in that cleanup invocation.
2. **Retention-invariant preservation:**
   - Non-terminal notices (pending, in-progress/sending, uncertain) in both queues are never deleted by finished-notice cleanup.
   - Terminal notices whose retention age has not yet expired are preserved.
   - Active-cycle occasion reminders (list and birthday reminders for the current UTC day or future dates) continue to be preserved even when terminal, preventing duplicate occasion reminders within the same cycle.
3. **Retention-age semantics for service/reminder notices evaluated and resolved:**
   - Retention semantics for service/reminder notices are explicitly evaluated against scheduling semantics (`next_attempt_at` vs. dedicated settlement/update timestamp).
   - Either a dedicated last-updated timestamp is introduced and maintained on service/reminder notice lifecycle transitions and used for retention age, or a clear, verified rationale is documented if existing semantics are proven aligned and safe.
4. **Compatibility & Quality:**
   - Existing callers of finished-notice cleanup (periodic background cleanup cycle and operator/test callers) continue to work seamlessly.
   - Automated tests verify batched cleanup across multiple batches, preservation of active-cycle/non-terminal/fresh rows, accurate aggregate purge counts, and the chosen retention-timestamp behavior.

## Task Description

### Programming Language

- **Python** (with existing project stack and conventions).

### Functional Requirements

1. **Batched Deletion of Expired Terminal Gift Notices:**
   - Expired terminal gift notices (`sent`, `skipped`, `failed` past the configured gift-notice retention threshold) must be deleted in bounded batches rather than a single unbounded delete.
2. **Batched Deletion of Expired Terminal Service/Reminder Notices:**
   - Expired terminal service/reminder notices (`sent`, `skipped`, `failed` past the configured reminder retention threshold, excluding active-cycle `list` and `birthday` occasion reminders for today or future UTC dates) must be deleted in bounded batches rather than a single unbounded delete.
3. **Full Backlog Drain & Accurate Reporting:**
   - A cleanup invocation must continue to return the total count of deleted notices across both queues (and log the per-queue counts when any rows are deleted), regardless of how many batches were required.
4. **Retention Timestamp Evaluation for Service/Reminder Notices:**
   - Evaluate whether overloading the next-attempt/scheduling timestamp to represent terminal settlement age in the service/reminder queue causes semantic divergence (e.g., if scheduling/retry metadata must remain distinct from settlement time, or if any terminal path fails to stamp it consistently).
   - If divergence exists or is likely, track a dedicated last-updated timestamp for service/reminder notices and base retention cleanup on it.

### Non-Functional Requirements

- **Concurrency / Lock Duration:** Each individual write transaction during cleanup must be bounded in the number of rows deleted so that concurrent foreground requests and notice worker ticks are not starved.
- **Idempotency & Safety:** Repeated cleanup runs must remain idempotent; interrupted or partial cleanup runs must leave the queues in a consistent state with remaining eligible rows picked up on subsequent passes/runs.
- **Observability:** Existing structured log events (`notice_outbox_purged` and `receipt_notice_rows_purged`) must continue to accurately report deleted counts without noisy log spam when zero rows are deleted.

### Constraints and Assumptions

- **Out of Scope:**
  - Account deletion / anonymization across notification tables (tracked in `WISHENKA-35`).
  - Bounded retention for receipt deduplication keys (`notice_receipt_keys`, tracked in `WISHENKA-181`).
  - Refactoring `claim_reminder` / `refresh_reminder` duplicated eligibility SQL or route-level `_record_shared_event` calls (tracked in `WISHENKA-184`).
  - Refactoring private store coupling in `NoticeWorker` (tracked in `WISHENKA-180`).
- **Assumption:** The existing periodic cleanup schedule (`run_cleanup_cycle`) remains the primary production caller of finished-notice cleanup.

### Main Domain Entities

- **Gift Notice:** A queued notification informing a giver that a reserved wish was marked as received; transitions through active states to a terminal outcome (`sent`, `skipped`, `failed`) with a recorded update time.
- **Service / Reminder Notice:** A queued notification for an occasion reminder (`list`, `birthday`) or a shared-wishlist/reservation event; transitions through active states to a terminal outcome (`sent`, `skipped`, `failed`) and is subject to both retention age and active-cycle occasion-date preservation.
- **Retention Cleanup Pass:** A bounded deletion unit executed by the notice store as part of periodic housekeeping.

## Q&A

- **Q1: Why is batching needed for `NoticeStore.purge_finished`?**
  - **A1:** Under a large historical backlog (e.g., after prolonged worker downtime or a reduction in retention days), deleting all expired terminal rows in a single write transaction holds the database writer lock for an unbounded duration, risking timeouts or stalls for active user requests and notice delivery. Bounding deletions per pass keeps write-lock duration predictable.
- **Q2: Why evaluate a dedicated `updated_at` timestamp for `reminder_outbox`?**
  - **A2:** In `WISHENKA-60`, `reminder_outbox` reused `next_attempt_at` as the settlement timestamp on terminal transitions to avoid a schema migration. If retention semantics diverge from retry-scheduling semantics (or if any transition does not stamp `next_attempt_at` consistently), retention age could be miscalculated. Evaluating this explicitly ensures retention cleanup is grounded in accurate settlement time.
- **Q3: Are there any changes to active-cycle occasion reminder retention rules?**
  - **A3:** No. Terminal `list` and `birthday` reminders for today's UTC date or future dates must still be preserved so the scheduler does not re-enqueue duplicate reminders for the same occasion.
