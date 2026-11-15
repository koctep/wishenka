# WISHENKA-59: Efficient access to a giver's reservations

## Goals

Keep the giver's reservation cabinet and its summary responsive as the total number of
reservations across all users grows. A giver must continue to see accurate personal reservation
information without compromising the surprise for recipients.

## User Stories

- As a giver, I can open my reservations and see my active and purchased reservations across
  wishlists, even when many other users have reservations.
- As a giver, I can see accurate reservation and distinct-wish counts after my reservations
  change.
- As a recipient, I remain protected from disclosure of other people's reservations or purchases.

## Definition of Done

- Both personal reservation listing and summary select the requested giver's reservations
  without traversing all unrelated reservations. Locating a giver's collection must have
  constant-time lookup behavior; processing the giver's matching results may scale with their
  number.
- Existing list content, ordering, response fields, and handling of missing wishes are preserved.
  Active and purchased reservations remain included; cancelled reservations remain excluded.
- The summary preserves its existing counts of eligible reservations and distinct wishes,
  including existing behavior for reservations whose wish is unavailable.
- Creating, changing, cancelling, purchasing, restoring, or removing reservations cannot leave
  either result stale or attribute a reservation to the wrong giver. Empty results remain correct.
- Correctness is maintained after application restart and in every supported storage mode,
  including operations that fail or are cancelled and concurrent changes.
- Existing authorization and surprise protections remain unchanged; neither result exposes
  another giver's private reservation data to an unauthorized user.
- Automated checks cover lifecycle changes, isolation between givers, relevant storage modes,
  and the absence of a full scan of unrelated reservations. The existing tests continue to pass.

## Task Description

The personal reservation list and summary currently become more expensive as unrelated
reservations accumulate. Improve the selection of each giver's own reservations while retaining
all existing behavior. The work covers both list and summary and the changes needed to keep
personal results correct throughout the reservation lifecycle. It does not change the reservation
workflow, visibility policy, or user-facing interface.

Implementation language: Python.

### Business entities

- **Giver**: a user who creates and manages reservations.
- **Reservation**: a giver's quantity and status for a wish.
- **Wish**: an item in a wishlist that may have multiple reservations.
- **Reservation summary**: counts of a giver's eligible reservations and distinct wishes.

## Q&A

- **Why is this needed?** The cabinet and its badge should remain usable as overall reservation
  volume grows; the current work grows with reservations unrelated to the requesting giver.
- **Does constant-time lookup imply constant-time output?** No. Finding a giver's collection
  should not depend on total unrelated reservations; enumerating or counting its members can
  depend on the size of that collection.
- **Are display rules changing?** No. Existing active and purchased status rules, list ordering,
  counts, and access protections remain the acceptance baseline.
