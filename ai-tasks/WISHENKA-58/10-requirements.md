# WISHENKA-58: Reclaim inactive item coordination resources

## Goals

Keep the service reliable as the number of wishes processed over its lifetime grows. Resources
used to coordinate work on past wishes must not grow indefinitely with the number of distinct
wishes, while preserving the correctness of concurrent gift and reservation operations.

## User Stories

- As a wish owner, I want concurrent changes to a wish to preserve its valid state.
- As a giver, I want competing reservation operations to preserve availability and avoid
  inconsistent or duplicated outcomes.
- As an operator, I want a long-running service to release coordination resources no longer
  needed, so processing many distinct wishes does not cause unbounded resource retention.

## Definition of Done

- After operations on a wish finish and no operation is waiting to use it, coordination resources
  for that wish can be reclaimed; retained inactive resources do not grow without bound as more
  distinct wishes are processed sequentially.
- Operations on the same wish remain mutually exclusive, including when one or more operations
  are waiting, an operation fails, or a waiting operation is cancelled.
- An operation newly arriving while another operation holds or awaits the same wish cannot enter
  the protected work concurrently with it, even when resource reclamation occurs.
- Independent wishes can continue to make progress concurrently; cleanup does not serialize
  their protected work for its duration.
- Existing reservation, gift, and wish invariants, operation outcomes, and public behavior remain
  unchanged. Reusing a previously inactive wish remains safe.
- Automated verification exercises resource reclamation after many distinct wishes and the
  concurrency, failure, cancellation, and reuse cases above.

## Task Description

The application coordinates work by wish to protect its state. The current lifetime of inactive
coordination resources can track every distinct wish seen by a long-running process, producing
unbounded memory growth. This task changes that lifetime while keeping active and waiting work
safe and preserving established service behavior.

**Scope:** in-process coordination resources for wish operations and their lifecycle. Existing
cross-process transaction guarantees are preserved; changing persistence, deployment topology,
reservation rules, public interfaces, or adding a new distributed coordination service is outside
scope.

**Implementation language:** Python, consistent with the existing coordinator.

**Business entities:** a wish has an identity and availability; a giver may create or change a
reservation for a wish. Concurrent operations may act on one wish or on different wishes.

**Constraints and assumptions:** cleanup must not remove protection needed by an active or
waiting operation. The task does not promise a fixed memory budget or a specific reclamation
latency; it requires that inactive entries do not accumulate indefinitely. Existing process and
transaction boundaries remain in force.

## Q&A

- **Why address this?** Jira identifies unbounded retained coordination resources as a risk when
  hundreds of thousands of wishes are processed by a long-running service.
- **What must remain unchanged?** Wish-scoped concurrency guarantees and existing user-visible
  reservation and gift behavior, including independent progress for different wishes.
- **Is this cross-process coordination?** No. The existing architecture assigns cross-process
  write protection to the persistence layer; this task addresses in-process coordination.
