# WISHENKA-181: Retention and Physical Deletion of Private Birthday Data, Inactive Bot Destinations, and Delivery Records

## Goals

Minimize personal data retention and bound operational storage growth in the notification and
reminder system without compromising delivery reliability or idempotence. Specifically:

1. Ensure that when a user removes a private birthday entry, its personal details (label and date)
   are physically deleted or anonymized within a defined retention policy rather than retained
   indefinitely.
2. Prevent unbounded accumulation of obsolete operational records—inactive bot delivery
   destinations, terminal reminder delivery records, and receipt deduplication records—by
   enforcing explicit, deterministic retention policies.
3. Preserve notification idempotence, replay safety, and operational recovery guarantees so that
   cleanup never causes duplicate notices from late or replayed events and never discards
   unresolved or ambiguous (`uncertain`) delivery state.

## User Stories

- **As a user**, when I delete a private birthday entry, I want its private label and date to be
  permanently removed or anonymized within the defined retention policy so that my deleted
  personal notes are not retained indefinitely.
- **As a user**, I want my active bot destination, active birthday entries, and upcoming reminders
  to remain intact during routine cleanup, and I do not want to receive duplicate notifications for
  already-processed reminders or gift receipts.
- **As an operator**, I want inactive bot destinations, terminal reminder records, and expired
  receipt deduplication records to be purged automatically on a bounded schedule so that system
  storage remains controlled.
- **As an operator**, I want in-flight and ambiguous (`uncertain`) delivery records to be preserved
  until resolved or recovered so that cleanup never hides delivery uncertainty or triggers
  unintended duplicate sends during recovery.

## Definition of Done

1. **Deleted birthday data removal/anonymization**: When a user deletes a private birthday entry,
   no further reminders are generated for it, and its stored private values (label and date) are
   physically removed or anonymized within the defined retention policy.
2. **Inactive bot destination purge**: Bot delivery destinations that have been inactive beyond
   the defined retention period are physically removed without disrupting active destinations or
   preventing a user from re-establishing bot delivery later.
3. **Terminal reminder record purge**: Terminal reminder delivery records (such as completed or
   skipped reminders) are physically removed after their defined retention period, while
   preserving protection against re-sending the same reminder occurrence within its active cycle.
4. **Receipt deduplication retention and replay protection**: Receipt notification deduplication
   records are retained for a bounded window sufficient to prevent late or replayed receipt events
   from producing duplicate notices, and are purged once past that retention window.
5. **Protection of active and `uncertain` records**: Pending, retrying, and ambiguous (`uncertain`)
   delivery records are not prematurely purged by retention cleanup; recovery and operator
   resolution workflows continue to work as expected.
6. **Idempotence across cleanup and recovery**: Repeated cleanup runs, service restarts, and late
   or replayed events within the retention window do not produce duplicate notifications or errors.
7. **Automated verification**: Automated tests verify physical removal/anonymization of deleted
   birthday entries, retention-based cleanup of inactive destinations, terminal reminders, and
   deduplication records, preservation of `uncertain` and in-flight rows, and replay-safe
   recovery.

## Task Description

### Problem and Scope

Previously, deleting a private birthday entry only marked it inactive while retaining its label,
date, and owner association indefinitely. Similarly, inactive bot destinations, terminal reminder
delivery records, and receipt deduplication records accumulated without a bounded retention and
physical purge policy.

**Programming language**: Python.

#### In Scope

- Defining and enforcing retention and physical deletion/anonymization policies for:
  - Deleted private birthday entries.
  - Inactive bot delivery destinations.
  - Terminal reminder delivery records.
  - Receipt notification deduplication records.
- Preserving idempotence and preventing late or replayed events from generating duplicate notices.
- Protecting in-flight and `uncertain` delivery records during retention cleanup and recovery.
- Automated tests covering deletion, retention boundaries, recovery, and replay/idempotence
  behavior.

#### Out of Scope

- Full user account deletion across all product domains (tracked separately in `WISHENKA-35`),
  though the retention policies defined here must remain compatible with account deletion.
- User-facing UI changes in the Mini App or new notification categories.
- Real external Telegram provider smoke tests (`WISHENKA-156`).

### Main Business Entities

- **Private Birthday Entry**: A user-owned private occasion containing a label, month/day, owner
  association, and lifecycle state (active or deleted).
- **Bot Delivery Destination**: A user's Telegram bot chat endpoint with reachability/activity
  status and activity timestamps.
- **Reminder Delivery Record**: A scheduled or processed reminder for an approaching occasion,
  carrying lifecycle states (pending/in-flight, terminal such as sent or skipped, or `uncertain`).
- **Receipt Deduplication Record**: A record indicating that a gift receipt notification for a
  specific reservation holder and receipt has already been processed, guarding against duplicate
  notices from late or replayed events.

### Constraints and Non-Functional Requirements

- **Determinism and testability**: Retention periods and cutoff evaluations must be configurable
  and deterministic so they can be verified in automated tests without real-time waiting.
- **Idempotence**: Retention cleanup must be safe to run repeatedly and resilient to interruption.
- **Privacy**: Physically deleted or anonymized private birthday data must not remain recoverable
  or be exposed in operational logs.
- **Safety**: Cleanup must never compromise delivery idempotence or remove unresolved `uncertain`
  delivery state.

## Q&A

- **Q: Why is physical deletion or anonymization required when deleted birthday entries already stop
  generating reminders?**
  - **A**: Retaining private labels, dates, and owner associations indefinitely after user deletion
    conflicts with data minimization and user privacy expectations.
- **Q: Why not delete terminal reminder records and receipt deduplication records immediately after
  delivery?**
  - **A**: Immediate deletion would allow late, retried, or replayed events—or repeated scheduler
    passes within the same occurrence window—to treat an already-handled event as new and send
    duplicate notifications. A bounded retention window preserves idempotence while capping
    storage growth.
- **Q: How should `uncertain` delivery records be treated by retention cleanup?**
  - **A**: `uncertain` records indicate an ambiguous external send outcome and must be preserved
    until resolved or handled by recovery, preventing silent loss of operational visibility or
    accidental duplicate sends.
