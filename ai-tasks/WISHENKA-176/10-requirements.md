# WISHENKA-176: Batched Cabinet Loading and Non-Blocking Consistent Reads

## Goals

Keep the giver's reservation cabinet fast, scalable, and internally consistent as a giver's number
of reserved wishes grows, while ensuring that viewing the cabinet does not block or serialize
concurrent updates by other users. Existing cabinet output, availability calculations, and recipient
surprise protections must remain unchanged.

## User Stories

- As a giver with many reservations across multiple wishlists, I can open my reservation cabinet
  quickly without per-item loading delays degrading responsiveness.
- As a giver, I always see a single, internally consistent snapshot of my reservations, wish
  details, availability, and wishlist titles, even when other users are concurrently creating,
  updating, purchasing, or cancelling reservations.
- As an active user modifying wishlists, wishes, or reservations, my updates are not blocked or
  delayed by other givers merely viewing their reservation cabinets.
- As a recipient, I remain protected from any disclosure of other people's reservations or
  purchases.

## Definition of Done

- **Batched related-data loading:** Loading a giver's reservation cabinet retrieves associated
  wish, availability/occupancy, and wishlist details in bounded batches rather than issuing
  separate round trips for each distinct wish or wishlist, while continuing to avoid full scans of
  unrelated reservations.
- **Consistent non-blocking read snapshot:** Reading the cabinet presents a single consistent
  point-in-time view without reserving a write lock or serializing against concurrent writers. If
  a non-blocking read snapshot cannot satisfy consistency guarantees in a given mode, the
  trade-off and chosen behavior are explicitly verified and documented.
- **Response parity:** Cabinet list content, grouping, ordering, response fields, remaining
  availability calculations, active/purchased inclusion, cancelled exclusion, and handling of
  missing or unavailable wishes match existing behavior identically.
- **Concurrent safety:** Concurrent writes (creating, changing, purchasing, cancelling, or
  removing reservations and updating wishes/wishlists) proceed without lock contention from
  cabinet reads, and cabinet reads never observe partial or torn state across related entities.
- **Verified efficiency and latency:** Automated checks validate response parity, concurrent write
  behavior, efficient data-access plans (no full-table scans), and latency under representative
  cabinet sizes. Existing automated checks continue to pass.
- **Invariant preservation:** Existing authorization rules and recipient surprise protections
  remain unchanged.

## Task Description

Following the indexed giver-reservation lookup introduced in WISHENKA-59, loading the giver's
reservation cabinet still gathers related wish details, wish occupancy/availability, and wishlist
headers individually per distinct wish and wishlist, causing the number of data-access round trips
to grow linearly with cabinet size. Additionally, the current read path relies on a write-reserving
snapshot mechanism that serializes read operations with concurrent writers.

This task addresses both concerns:
1. Batch-load related cabinet data (wishes, occupancy/availability, and wishlist headers) for the
   giver's matching reservations.
2. Investigate and adopt a non-blocking read-snapshot approach that preserves a single consistent
   snapshot without acquiring a write-lock reservation.
3. Validate response parity, concurrent write behavior, data-access plans, and latency on
   representative cabinet volumes.

Scope is limited to cabinet data retrieval and read-snapshot consistency/concurrency. It does not
alter the reservation lifecycle, business rules, UI presentation, or visibility policies.

Implementation language: Python.

### Business Entities

- **Giver:** A user who views and manages their own gift reservations.
- **Reservation:** A giver's reserved quantity and status (active, purchased, cancelled) for a wish.
- **Wish:** An item in a wishlist with a target quantity and remaining availability derived from
  reservations on that wish.
- **Wishlist:** A collection of wishes with a title/header and recipient/ownership metadata.
- **Reservation Cabinet:** The aggregated view of a giver's active and purchased reservations,
  enriched with wish details, availability, and wishlist context.

## Q&A

- **Why is this needed?** As a giver's cabinet grows, per-wish and per-wishlist lookups add
  avoidable round-trip overhead, and holding a write-level lock during cabinet reads creates
  unnecessary contention with concurrent writers. Eliminating both bottlenecks keeps the service
  responsive under concurrent traffic without sacrificing data consistency.
- **Are any user-facing fields, ordering, or business rules changing?** No. Output parity with the
  existing cabinet behavior is a strict requirement.
- **What if non-blocking snapshot isolation has constraints in the underlying storage mode?** The
  investigation must explicitly test and verify whether a deferred read snapshot preserves a
  single consistent snapshot without blocking concurrent writers, and confirm parity and latency
  under representative cabinet sizes.
